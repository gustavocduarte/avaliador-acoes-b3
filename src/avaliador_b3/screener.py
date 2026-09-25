"""Screener: roda o pipeline completo de valor justo (Graham, Bazin, FCD,
combinado) para todas as ações do universo do Ibovespa, uma de cada vez, e
devolve uma tabela ordenada por desconto — quanto o preço atual está
abaixo (desconto positivo) ou acima (negativo) do valor justo combinado.

Não reimplementa nenhuma lógica de cálculo: só chama os mesmos
adapters/modelos já usados em app/main.py, orquestrando a busca pra cada
ação. As funções de busca-com-tratamento-de-erro daqui são próprias deste
módulo (não importadas de app/main.py, que é um script Streamlit — não dá
pra importar sem rodar a UI), mas seguem o mesmo padrão.

Processamento incremental (restrição de RAM documentada desde o início do
projeto): cada ação é buscada, calculada e gravada no CSV de saída antes
de passar pra próxima. Nunca acumula os dados intermediários (histórico de
preço, indicadores, etc.) de todas as ~76 ações na memória ao mesmo tempo
— só o resumo final de cada linha (poucos números), que é pequeno mesmo
somado.

Erro numa ação específica (fonte fora do ar, dado insuficiente, ou
qualquer exceção inesperada) não derruba o restante: vira uma linha com
`sucesso=False` e o motivo em `erro`, e o screener segue pras demais.

Fontes compartilhadas entre todas as ações (não buscadas por ação):
- Catálogo de emissores da B3 e universo do Ibovespa — cache sem TTL.
- Zip anual da CVM — cache por ano, reaproveitado entre as ~76 ações que
  precisarem do mesmo ano (só 2 downloads reais no total, não 76×2).
- Selic/IPCA do BCB — independentes de ticker.

O yfinance (histórico de preço, dividendos) é a fonte com risco real de
rate-limit rodando várias dezenas de vezes em sequência — por isso
`ingest.precos` tem `DELAY_PRECOS_SEGUNDOS` aplicado antes de cada
requisição real (decisão alinhada com o usuário antes de implementar).
"""

from __future__ import annotations

import csv
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from avaliador_b3.config import (
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    AVISO_DESCONTO_EXTREMO_GENERICO,
    AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD,
    AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD,
    AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    DESCONTO_EXTREMO_LIMITE_INFERIOR,
    DESCONTO_EXTREMO_LIMITE_SUPERIOR,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    SERIES_BCB_SGS,
)
from avaliador_b3.empresa.comportamento import calcular_beta
from avaliador_b3.ingest.b3_universo import obter_universo_ibovespa
from avaliador_b3.ingest.bcb_sgs import obter_serie
from avaliador_b3.ingest.crosswalk_cnpj import (
    EmissorNaoEncontrado,
    obter_catalogo_emissores,
    resolver_cnpj,
)
from avaliador_b3.ingest.cvm import (
    CnpjNaoEncontrado,
    ContaFluxoCaixaNaoEncontrada,
    obter_fluxo_caixa_livre_com_fallback,
    resolver_ano_mais_recente_disponivel,
)
from avaliador_b3.ingest.fundamentus import (
    EstruturaPaginaMudou,
    TickerNaoEncontrado,
    obter_indicadores,
)
from avaliador_b3.ingest.precos import (
    FalhaFontePreco,
    TickerInvalido,
    obter_dividendos,
    obter_historico,
    obter_historico_ibovespa,
)
from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin
from avaliador_b3.modelos.combinado import calcular_divergencia_metodos, calcular_valor_combinado
from avaliador_b3.modelos.fcd import calcular_valor_justo_fcd
from avaliador_b3.modelos.graham import calcular_valor_justo_graham

CAMINHO_SAIDA_PADRAO = DATA_PROCESSED_DIR / "screener.csv"


class DeteccaoAnoCvmFalhouWarning(UserWarning):
    """Categoria própria (não `UserWarning` genérico) pro aviso que
    `rodar_screener` emite quando `resolver_ano_mais_recente_disponivel`
    falha — permite que `app/main.py` capture especificamente ESSE aviso
    (via `category=DeteccaoAnoCvmFalhouWarning`) e mostre na tela pra
    quem clicou em "Rodar screener agora", sem confundir com os demais
    `warnings.warn` que podem disparar na mesma rodada (ex: cache do zip
    da CVM desatualizado em `ingest.cvm._baixar_zip_ano`), que devem
    continuar indo só pro log, sem mudança de comportamento."""


COLUNAS_RESULTADO = [
    "ticker",
    "sucesso",
    "erro",
    "preco_atual",
    "valor_combinado",
    "desconto_percentual",
    "divergencia_percentual_metodos",
    "metodos_utilizados",
    "graham_valor_justo",
    "bazin_preco_teto",
    "bazin_razao_dividendos_percentual",
    "fcd_valor_justo",
    "ano_referencia_fcd",
    "data_balanco_fundamentus",
    "beta_utilizado",
    "aviso_desconto_extremo",
]


def _aviso_desconto_extremo(
    desconto_percentual: float | None, metodos_utilizados: list[str]
) -> str:
    """Sinaliza (sem filtrar) descontos fora da faixa considerada
    confiável — ver a justificativa dos limiares em config.py (esses não
    mudam aqui). O TEXTO do aviso, por outro lado, depende de quais
    métodos entraram no valor combinado daquela ação específica — achado
    real, revisando o Screener publicado (screenshot da aba Screener,
    2026-09-24): um texto único que sempre citava o FCD ficava errado
    pra ações como COGN3, onde só Graham disparava o limiar positivo,
    sem FCD nenhum na conta. Quatro casos, por sinal do
    desconto × presença de "fcd" em `metodos_utilizados`:
    - positivo + FCD: taxa de crescimento de 2 pontos do FCD (o caso mais
      comum, mas não mais o único assumido).
    - positivo + sem FCD: risco que Graham/Bazin não captam.
    - negativo + FCD: FCD saiu negativo (único dos três que pode).
    - negativo + sem FCD: combinação hoje INALCANÇÁVEL — ver comentário
      completo em `config.AVISO_DESCONTO_EXTREMO_GENERICO` pro porquê
      (Graham é raiz quadrada, Bazin só aplicável com dividendo
      positivo) — mantido como reserva genérica, não uma explicação
      inventada, pra não deixar essa combinação muda se algum dos dois
      modelos mudar no futuro e passar a permitir negativo.

    A linha continua na tabela normalmente, só ganha esse aviso textual.
    """
    if desconto_percentual is None:
        return ""

    tem_fcd = "fcd" in metodos_utilizados

    if desconto_percentual > DESCONTO_EXTREMO_LIMITE_SUPERIOR:
        return (
            AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD
            if tem_fcd
            else AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD
        )
    if desconto_percentual < DESCONTO_EXTREMO_LIMITE_INFERIOR:
        return (
            AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD if tem_fcd else AVISO_DESCONTO_EXTREMO_GENERICO
        )
    return ""


def _linha_erro(ticker: str, mensagem: str) -> dict:
    linha = dict.fromkeys(COLUNAS_RESULTADO)
    linha["ticker"] = ticker
    linha["sucesso"] = False
    linha["erro"] = mensagem
    linha["metodos_utilizados"] = ""
    linha["aviso_desconto_extremo"] = ""
    return linha


def _buscar_macro(diretorio_cache: Path) -> tuple[float | None, float | None]:
    """Selic meta (decimal) e IPCA acumulado 12 meses (decimal). Buscado
    uma vez só, fora do loop por ação — é dado macro, não por empresa."""
    hoje = datetime.now()
    selic_df = obter_serie(
        SERIES_BCB_SGS["selic_meta"],
        data_inicial=(hoje - timedelta(days=90)).strftime("%d/%m/%Y"),
        data_final=hoje.strftime("%d/%m/%Y"),
        diretorio_cache=diretorio_cache,
    )
    selic_meta = float(selic_df.iloc[-1]["valor"]) / 100

    ipca_df = obter_serie(
        SERIES_BCB_SGS["ipca_mensal"],
        data_inicial=(hoje - timedelta(days=730)).strftime("%d/%m/%Y"),
        data_final=hoje.strftime("%d/%m/%Y"),
        diretorio_cache=diretorio_cache,
    )
    ipca_12m = float((1 + ipca_df["valor"].tail(12) / 100).prod() - 1)
    return selic_meta, ipca_12m


def _calcular_linha_ticker(
    ticker: str,
    catalogo_emissores: pd.DataFrame,
    historico_ibovespa_beta: pd.DataFrame | None,
    selic_meta: float | None,
    ipca_12m: float | None,
    ano_mais_recente_fcd: int | None,
    erro_deteccao_ano_fcd: str | None,
    diretorio_cache: Path,
) -> dict:
    """Roda o pipeline completo (Graham, Bazin, FCD, combinado) pra UM
    ticker. Cada fonte é buscada com tratamento de erro isolado — uma
    fonte faltando degrada aquele método específico pra "não aplicável"
    (ou o Beta pro padrão), não interrompe o cálculo das outras.

    Só levanta exceção pra fora se nem o preço (o dado mais básico, sem o
    qual não dá nem pra montar a linha) puder ser obtido.
    """
    historico = obter_historico(
        ticker, periodo=PERIODO_HISTORICO_COMPORTAMENTO, diretorio_cache=diretorio_cache
    )
    preco_atual = float(historico["Close"].iloc[-1])

    beta = None
    if historico_ibovespa_beta is not None:
        try:
            historico_beta = obter_historico(
                ticker, periodo=PERIODO_BETA, diretorio_cache=diretorio_cache
            )
            beta = calcular_beta(historico_beta, historico_ibovespa_beta)
        except (TickerInvalido, FalhaFontePreco):
            beta = None

    indicadores = None
    try:
        indicadores = obter_indicadores(ticker, diretorio_cache=diretorio_cache)
    except (TickerNaoEncontrado, EstruturaPaginaMudou):
        indicadores = None

    lpa = indicadores["lpa"] if indicadores else None
    vpa = indicadores["vpa"] if indicadores else None
    numero_acoes = indicadores["numero_acoes"] if indicadores else None
    divida_liquida_sobre_patrimonio = (
        indicadores["divida_liquida_sobre_patrimonio"] if indicadores else None
    )
    # Dívida líquida em valor ABSOLUTO (não a proporção acima) — pra
    # converter o FCD de Enterprise Value pra Equity Value, mesmo campo
    # usado em app/main.py (ver modelos/fcd.py).
    divida_liquida = indicadores["divida_liquida"] if indicadores else None
    # Data-base ("Últ balanço processado") dos indicadores acima — varia
    # por empresa (balanços trimestrais saem em datas diferentes), por
    # isso vira coluna própria no Screener. Diferente de preço/beta/IPCA,
    # que são praticamente a mesma data pra todas as ações da mesma
    # rodada (buscadas em sequência, minutos de diferença) — não levadas
    # pro CSV por não variarem o suficiente pra justificar a coluna.
    data_balanco_fundamentus = (
        indicadores["data_balanco_fundamentus"] if indicadores else None
    )

    dividendos = None
    try:
        dividendos = obter_dividendos(ticker, diretorio_cache=diretorio_cache)
    except (TickerInvalido, FalhaFontePreco):
        dividendos = None

    cnpj = None
    segmento_setorial = None
    try:
        registro_cnpj = resolver_cnpj(ticker, catalogo_emissores)
        cnpj = registro_cnpj["cnpj"]
        # Mesmo registro que já traz o cnpj — sem busca extra. Usado só
        # pra decidir se o FCD se aplica (ver config.SEGMENTOS_FCD_NAO_
        # APLICAVEL), instituição financeira não tem interpretação
        # econômica válida pra CFO+CFI descontado pelo WACC.
        segmento_setorial = registro_cnpj["segmento_setorial"]
    except EmissorNaoEncontrado:
        cnpj = None

    # Detecção de ano por empresa (nível seguinte ao do ano mais recente
    # disponível, que já vem resolvido — nível arquivo — de `rodar_screener`
    # e é reaproveitado entre todas as ações): se esse ticker específico
    # ainda não apareceu no zip mais recente, cai um ano só pra ele, com o
    # ano-base do crescimento andando junto. Ver
    # ingest.cvm.obter_fluxo_caixa_livre_com_fallback.
    fcf_atual = fcf_ha_n_anos = ano_referencia_fcd = None
    if cnpj and ano_mais_recente_fcd is not None:
        try:
            resultado_fcf = obter_fluxo_caixa_livre_com_fallback(
                cnpj,
                ano_mais_recente_fcd,
                ANOS_HISTORICO_CRESCIMENTO_FCD,
                diretorio_cache=diretorio_cache,
            )
            fcf_atual = resultado_fcf["fcf_atual"]
            fcf_ha_n_anos = resultado_fcf["fcf_ha_n_anos"]
            ano_referencia_fcd = resultado_fcf["ano_referencia_utilizado"]
        except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada):
            fcf_atual = fcf_ha_n_anos = ano_referencia_fcd = None

    resultado_graham = calcular_valor_justo_graham(lpa, vpa)
    resultado_bazin = (
        calcular_preco_teto_bazin(dividendos)
        if dividendos is not None
        else {
            "aplicavel": False,
            "preco_teto": None,
            "motivo_nao_aplicavel": "Histórico de dividendos indisponível.",
        }
    )
    # A detecção do ano falhando (CVM fora do ar, timeout, etc. — ver
    # rodar_screener) tem prioridade sobre o motivo genérico de "FCF
    # indisponível" que calcular_valor_justo_fcd devolveria com
    # fcf_atual=None: sem essa checagem explícita, a causa real (detecção
    # do ano quebrada) ficava indistinguível de uma empresa que
    # simplesmente não tem FCD na CVM — mascarando um bug de
    # infraestrutura atrás de um motivo que parece só "sem dado".
    if ano_mais_recente_fcd is None and erro_deteccao_ano_fcd is not None and cnpj:
        resultado_fcd = {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": (
                f"Detecção do ano mais recente da CVM falhou: {erro_deteccao_ano_fcd}"
            ),
        }
    elif selic_meta is not None and ipca_12m is not None:
        resultado_fcd = calcular_valor_justo_fcd(
            fcf_atual=fcf_atual,
            numero_acoes=numero_acoes,
            selic_meta=selic_meta,
            ipca_12m=ipca_12m,
            fcf_ha_n_anos=fcf_ha_n_anos,
            divida_liquida_sobre_patrimonio=divida_liquida_sobre_patrimonio,
            beta=beta,
            divida_liquida=divida_liquida,
            segmento_setorial=segmento_setorial,
        )
    else:
        resultado_fcd = {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": "Selic/IPCA indisponíveis.",
        }

    resultado_combinado = calcular_valor_combinado(resultado_graham, resultado_bazin, resultado_fcd)

    desconto_percentual = None
    if resultado_combinado["aplicavel"]:
        desconto_percentual = (
            (resultado_combinado["valor_combinado"] - preco_atual) / preco_atual * 100
        )

    divergencia = calcular_divergencia_metodos(
        resultado_combinado["valores_por_metodo"], preco_atual
    )

    erro = None if resultado_combinado["aplicavel"] else resultado_combinado["motivo_nao_aplicavel"]
    razao_dividendos_bazin = resultado_bazin.get("razao_dividendos_12m_vs_mediana_5a")
    return {
        "ticker": ticker,
        "sucesso": True,
        "erro": erro,
        "preco_atual": preco_atual,
        "valor_combinado": resultado_combinado["valor_combinado"],
        "desconto_percentual": desconto_percentual,
        "metodos_utilizados": ",".join(resultado_combinado["metodos_utilizados"]),
        "graham_valor_justo": resultado_graham.get("valor_justo"),
        "bazin_preco_teto": resultado_bazin.get("preco_teto"),
        "bazin_razao_dividendos_percentual": (
            razao_dividendos_bazin * 100 if razao_dividendos_bazin is not None else None
        ),
        "fcd_valor_justo": resultado_fcd.get("valor_justo"),
        "ano_referencia_fcd": ano_referencia_fcd if resultado_fcd["aplicavel"] else None,
        "data_balanco_fundamentus": data_balanco_fundamentus,
        "divergencia_percentual_metodos": divergencia["divergencia_percentual"],
        "beta_utilizado": resultado_fcd.get("beta_utilizado"),
        "aviso_desconto_extremo": _aviso_desconto_extremo(
            desconto_percentual, resultado_combinado["metodos_utilizados"]
        ),
    }


def rodar_screener(
    tickers: list[str] | None = None,
    ano_mais_recente_fcd: int | None = None,
    diretorio_cache: Path = DATA_RAW_DIR,
    caminho_saida: Path = CAMINHO_SAIDA_PADRAO,
) -> pd.DataFrame:
    """Roda o screener completo e devolve a tabela ordenada por
    `desconto_percentual` decrescente (ação mais descontada em relação ao
    valor justo combinado primeiro; sem valor combinado ou com erro fica
    no fim).

    `tickers` sobrescreve o universo do Ibovespa (útil pra rodar um
    subconjunto, ex: em teste). `ano_mais_recente_fcd` sobrescreve a
    detecção automática do ano mais recente do DFP da CVM disponível —
    nível ARQUIVO, ver `ingest.cvm.resolver_ano_mais_recente_disponivel`;
    `None` (padrão) detecta em tempo de execução, chamado uma vez só e
    reaproveitado entre todas as ações. Cada ação ainda resolve seu
    PRÓPRIO ano por cima disso — nível EMPRESA, ver `ingest.cvm.
    obter_fluxo_caixa_livre_com_fallback` — caindo um ano só pra quem
    ainda não apareceu no zip mais recente, sem afetar as demais. Grava
    incrementalmente em `caminho_saida`
    durante o processamento — uma linha por ação, assim que calculada, não
    só no final — mas nessa hora ainda na ordem de processamento (universo
    do Ibovespa, alfabética), não por desconto. Depois que o loop termina,
    `caminho_saida` é reescrito de uma vez com a tabela já ordenada, a
    partir dos mesmos dados já calculados em memória (sem reler do disco
    nem bater na rede de novo) — bug real corrigido em 2026-09-21: antes
    disso o arquivo em disco nunca refletia a ordenação, só o retorno da
    função em memória.
    """
    if tickers is None:
        universo = obter_universo_ibovespa(diretorio_cache=diretorio_cache)
        tickers = list(universo["ticker"])

    catalogo_emissores = obter_catalogo_emissores(diretorio_cache=diretorio_cache)

    try:
        historico_ibovespa_beta = obter_historico_ibovespa(
            periodo=PERIODO_BETA, diretorio_cache=diretorio_cache
        )
    except (TickerInvalido, FalhaFontePreco):
        historico_ibovespa_beta = None

    try:
        selic_meta, ipca_12m = _buscar_macro(diretorio_cache)
    except Exception:
        selic_meta = ipca_12m = None

    # Falha aqui é global (afeta o FCD de TODAS as ações da rodada, não uma
    # linha específica) — por isso o aviso é emitido uma vez aqui, não por
    # ticker. `erro_deteccao_ano_fcd` também alimenta o motivo_nao_
    # aplicavel do FCD em _calcular_linha_ticker, pros casos em que ele
    # decide a coluna "erro" da linha (Graham/Bazin também não aplicáveis)
    # — mas isso sozinho não é visível se Graham OU Bazin funcionarem pra
    # alguma ação, daí o aviso global garantir que a causa nunca fique
    # silenciosa mesmo assim.
    erro_deteccao_ano_fcd: str | None = None
    if ano_mais_recente_fcd is None:
        try:
            ano_mais_recente_fcd = resolver_ano_mais_recente_disponivel(
                diretorio_cache=diretorio_cache
            )
        except Exception as erro:
            ano_mais_recente_fcd = None
            erro_deteccao_ano_fcd = str(erro)
            warnings.warn(
                f"Detecção do ano mais recente da CVM falhou — o FCD de todas as "
                f"ações desta rodada ficará indisponível: {erro_deteccao_ano_fcd}",
                category=DeteccaoAnoCvmFalhouWarning,
                stacklevel=2,
            )

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    linhas: list[dict] = []

    with open(caminho_saida, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_RESULTADO)
        escritor.writeheader()

        for ticker in tickers:
            try:
                linha = _calcular_linha_ticker(
                    ticker,
                    catalogo_emissores=catalogo_emissores,
                    historico_ibovespa_beta=historico_ibovespa_beta,
                    selic_meta=selic_meta,
                    ipca_12m=ipca_12m,
                    ano_mais_recente_fcd=ano_mais_recente_fcd,
                    erro_deteccao_ano_fcd=erro_deteccao_ano_fcd,
                    diretorio_cache=diretorio_cache,
                )
            except (TickerInvalido, FalhaFontePreco) as erro:
                linha = _linha_erro(ticker, f"Preço: {erro}")
            except Exception as erro:  # nunca deixa uma ação derrubar o screener inteiro
                linha = _linha_erro(ticker, f"Erro inesperado: {erro}")

            linhas.append(linha)
            escritor.writerow(linha)
            arquivo.flush()

    resultado = pd.DataFrame(linhas, columns=COLUNAS_RESULTADO)
    resultado_ordenado = resultado.sort_values(
        "desconto_percentual", ascending=False, na_position="last"
    ).reset_index(drop=True)

    # Reescreve o arquivo já ordenado — a escrita incremental acima é só
    # proteção de RAM durante o processamento (nunca acumula histórico/
    # indicadores de todas as ações na memória ao mesmo tempo), não
    # precisa refletir a ordem final em disco. Reaproveita `resultado`,
    # já montado a partir de `linhas` — sem nova leitura de disco nem
    # nova chamada de rede.
    resultado_ordenado.to_csv(caminho_saida, index=False)

    return resultado_ordenado
