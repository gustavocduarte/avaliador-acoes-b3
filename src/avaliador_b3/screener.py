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
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from avaliador_b3.config import (
    ANO_REFERENCIA_FCD,
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    AVISO_DESCONTO_EXTREMO,
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
    obter_fluxo_caixa_livre,
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
from avaliador_b3.modelos.combinado import calcular_valor_combinado
from avaliador_b3.modelos.fcd import calcular_valor_justo_fcd
from avaliador_b3.modelos.graham import calcular_valor_justo_graham

CAMINHO_SAIDA_PADRAO = DATA_PROCESSED_DIR / "screener.csv"

COLUNAS_RESULTADO = [
    "ticker",
    "sucesso",
    "erro",
    "preco_atual",
    "valor_combinado",
    "desconto_percentual",
    "metodos_utilizados",
    "graham_valor_justo",
    "bazin_preco_teto",
    "fcd_valor_justo",
    "beta_utilizado",
    "aviso_desconto_extremo",
]


def _aviso_desconto_extremo(desconto_percentual: float | None) -> str:
    """Sinaliza (sem filtrar) descontos fora da faixa considerada
    confiável — ver a justificativa dos limiares em config.py. A linha
    continua na tabela normalmente, só ganha esse aviso textual."""
    if desconto_percentual is None:
        return ""
    if (
        desconto_percentual > DESCONTO_EXTREMO_LIMITE_SUPERIOR
        or desconto_percentual < DESCONTO_EXTREMO_LIMITE_INFERIOR
    ):
        return AVISO_DESCONTO_EXTREMO
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
    ano_referencia: int,
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

    dividendos = None
    try:
        dividendos = obter_dividendos(ticker, diretorio_cache=diretorio_cache)
    except (TickerInvalido, FalhaFontePreco):
        dividendos = None

    cnpj = None
    try:
        cnpj = resolver_cnpj(ticker, catalogo_emissores)["cnpj"]
    except EmissorNaoEncontrado:
        cnpj = None

    fcf_atual = fcf_ha_n_anos = None
    if cnpj:
        try:
            fcf_atual = obter_fluxo_caixa_livre(
                cnpj, ano_referencia, diretorio_cache=diretorio_cache
            )["fcf_atual"]
        except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada):
            fcf_atual = None
        try:
            ano_anterior = ano_referencia - ANOS_HISTORICO_CRESCIMENTO_FCD
            fcf_ha_n_anos = obter_fluxo_caixa_livre(
                cnpj, ano_anterior, diretorio_cache=diretorio_cache
            )["fcf_atual"]
        except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada):
            fcf_ha_n_anos = None

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
    if selic_meta is not None and ipca_12m is not None:
        resultado_fcd = calcular_valor_justo_fcd(
            fcf_atual=fcf_atual,
            numero_acoes=numero_acoes,
            selic_meta=selic_meta,
            ipca_12m=ipca_12m,
            fcf_ha_n_anos=fcf_ha_n_anos,
            divida_liquida_sobre_patrimonio=divida_liquida_sobre_patrimonio,
            beta=beta,
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

    erro = None if resultado_combinado["aplicavel"] else resultado_combinado["motivo_nao_aplicavel"]
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
        "fcd_valor_justo": resultado_fcd.get("valor_justo"),
        "beta_utilizado": resultado_fcd.get("beta_utilizado"),
        "aviso_desconto_extremo": _aviso_desconto_extremo(desconto_percentual),
    }


def rodar_screener(
    tickers: list[str] | None = None,
    ano_referencia: int = ANO_REFERENCIA_FCD,
    diretorio_cache: Path = DATA_RAW_DIR,
    caminho_saida: Path = CAMINHO_SAIDA_PADRAO,
) -> pd.DataFrame:
    """Roda o screener completo e devolve a tabela ordenada por
    `desconto_percentual` decrescente (ação mais descontada em relação ao
    valor justo combinado primeiro; sem valor combinado ou com erro fica
    no fim).

    `tickers` sobrescreve o universo do Ibovespa (útil pra rodar um
    subconjunto, ex: em teste). Grava incrementalmente em `caminho_saida`
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
                    ano_referencia=ano_referencia,
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
