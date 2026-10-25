"""Acesso do app aos dados: busca e cache de preços, indicadores, macro e screener salvo."""

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from avaliador_b3 import config, rodada
from avaliador_b3.app.formatacao import _fmt_data
from avaliador_b3.config import (
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    ANOS_JANELA_CORRELACAO,
    SERIES_BCB_SGS,
    TEXTO_INDICE_INDISPONIVEL,
    TEXTO_SCREENER_AINDA_NAO_GERADO,
    TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW,
    TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA,
    TEXTO_SPINNER_CATALOGO_COMPLETO,
    TICKER_PETROLEO_BRENT,
    VALORES_PERMITIR_RODAR_SCREENER,
    VARIAVEL_PERMITIR_RODAR_SCREENER,
)
from avaliador_b3.ingest import (
    b3_universo,
    balanco_cvm,
    bcb_sgs,
    crosswalk_cnpj,
    cvm,
    fundamentus,
    gpr,
    precos,
)
from avaliador_b3.ingest.bcb_sgs import ResultadoMacro
from avaliador_b3.ingest.crosswalk_cnpj import EmissorNaoEncontrado
from avaliador_b3.ingest.cvm import CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada
from avaliador_b3.ingest.fundamentus import EstruturaPaginaMudou, TickerNaoEncontrado
from avaliador_b3.ingest.precos import FalhaFontePreco, TickerInvalido
from avaliador_b3.modelos.fcd import calcular_caixa_operacional_fcd, montar_fluxos_fcd


def _buscar_historico(
    ticker: str, periodo: str, auto_adjust: bool = True
) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico de preço da ação. `periodo` varia por uso: a janela curta
    `PERIODO_HISTORICO_COMPORTAMENTO` serve pra volume/volatilidade; Beta
    usa uma janela própria mais longa (`PERIODO_BETA`); o card "Preço
    atual" usa `PERIODO_PRECO_ATUAL`, separado dos outros dois — ver o
    comentário em config.py (o histórico diário mais longo atrasa um
    pregão inteiro, até já encerrado).

    `auto_adjust=True` (padrão) pra tudo que é cálculo de RETORNO (Beta,
    volatilidade, "Preço vs. Ibovespa"). O Dividend Yield histórico é a
    única exceção — precisa do preço NOMINAL da época, não ajustado
    retroativamente por dividendos futuros — ver o docstring de
    `ingest.precos.obter_historico`.

    Um histórico vazio SEM exceção (teoricamente possível só com um cache
    em disco corrompido/truncado — `ingest.precos.obter_historico` já
    levanta `TickerInvalido` se vier vazio no caminho de busca nova, antes
    de gravar cache) é tratado aqui como erro, igual a uma exceção — os
    ~7 pontos que consomem esse retorno neste arquivo confiam que "sem
    erro" implica "tem pelo menos uma linha", sem precisar checar
    `.empty` em cada um deles separadamente."""
    try:
        return _buscar_historico_ou_levanta(ticker, periodo, auto_adjust), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


def _buscar_historico_ou_levanta(
    ticker: str, periodo: str, auto_adjust: bool = True
) -> pd.DataFrame:
    historico = precos.obter_historico(ticker, periodo=periodo, auto_adjust=auto_adjust)
    if historico.empty:
        raise FalhaFontePreco(f"Histórico de {ticker!r} veio vazio — tente de novo mais tarde.")
    return historico


def _buscar_historico_ibovespa(periodo: str) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico do Ibovespa — mesmo tratamento de "vazio sem exceção
    vira erro" que `_buscar_historico` (ver docstring lá), pelo mesmo
    motivo defensivo."""
    try:
        historico = precos.obter_historico_ibovespa(periodo=periodo)
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)
    if historico.empty:
        return None, "Histórico do Ibovespa veio vazio — tente de novo mais tarde."
    return historico, None


@st.cache_data(ttl=3600)
def _buscar_historico_petroleo_cacheado(periodo: str) -> pd.DataFrame:
    return _buscar_historico_ou_levanta(TICKER_PETROLEO_BRENT, periodo=periodo)


def _buscar_historico_petroleo(
    periodo: str = f"{ANOS_JANELA_CORRELACAO}y",
) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico do petróleo Brent (BZ=F) — cacheado na sessão por 1h
    (por período: `st.cache_data` já cacheia por combinação de
    argumentos, mesmo padrão de `ingest.precos.obter_historico`), não
    depende da ação buscada. Período padrão é a mesma janela de
    correlação (2 anos); a seção "Comparando com Petróleo (Brent)" passa
    períodos maiores (5/10 anos) explicitamente. A parte cacheada levanta
    em vez de devolver `(None, erro)` — `st.cache_data` guardaria esse
    par por 1h inteira, inclusive quando o erro é transitório."""
    try:
        return _buscar_historico_petroleo_cacheado(periodo), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


@st.cache_data(ttl=3600)
def _buscar_cambio_correlacao_cacheado() -> pd.DataFrame:
    hoje = datetime.now()
    return bcb_sgs.obter_serie_com_fallback(
        SERIES_BCB_SGS["cambio_usd_venda"],
        data_inicial=(hoje - timedelta(days=365 * ANOS_JANELA_CORRELACAO)).strftime("%d/%m/%Y"),
        data_final=hoje.strftime("%d/%m/%Y"),
    )


def _buscar_cambio_correlacao() -> tuple[pd.DataFrame | None, str | None]:
    """Série de câmbio USD/BRL (PTAX venda) na janela de correlação —
    cacheada na sessão por 1h, não depende da ação buscada. A parte
    cacheada levanta em vez de devolver `(None, erro)`, senão um erro
    transitório ficaria preso em cache pela 1h inteira."""
    try:
        return _buscar_cambio_correlacao_cacheado(), None
    except Exception as erro:
        return None, f"Falha ao buscar câmbio USD/BRL do Banco Central: {erro}"


@st.cache_data(ttl=3600)
def _buscar_gpr_diaria_cacheado() -> pd.DataFrame:
    return gpr.obter_gpr(serie="diaria")


def _buscar_gpr_diaria() -> tuple[pd.DataFrame | None, str | None]:
    """Série diária do índice GPR — cacheada na sessão por 1h, não
    depende da ação buscada. `obter_gpr` já tem seu próprio prazo de
    validade em disco por baixo (`DIAS_VALIDADE_CACHE_GPR_DIARIO`), isso
    só evita reler/reparsear o CSV a cada busca dentro da mesma sessão do
    Streamlit. A parte cacheada levanta em vez de devolver `(None, erro)`,
    senão um erro transitório ficaria preso em cache pela 1h inteira."""
    try:
        return _buscar_gpr_diaria_cacheado(), None
    except Exception as erro:
        return None, f"Falha ao buscar índice GPR: {erro}"


@st.cache_data(ttl=3600)
def _buscar_universo_ibovespa_cacheado() -> pd.DataFrame:
    return b3_universo.obter_universo_ibovespa()


def _buscar_universo_ibovespa() -> tuple[pd.DataFrame | None, str | None]:
    """Universo do Ibovespa (ticker/nome/segmento de listagem/peso) —
    cacheado na sessão do Streamlit, não depende do ticker buscado. Um
    ticker fora do Ibovespa simplesmente não aparece nesse universo — não
    é um erro de busca. A parte cacheada levanta em vez de devolver
    `(None, erro)`, senão um erro transitório ficaria preso em cache pela
    1h inteira."""
    try:
        return _buscar_universo_ibovespa_cacheado(), None
    except Exception as erro:
        return None, f"Falha ao buscar universo do Ibovespa: {erro}"


def _buscar_indicadores_fundamentus(ticker: str) -> tuple[dict | None, str | None]:
    """Indicadores fundamentalistas (ROE, margem, LPA/VPA, dívida,
    patrimônio, número de ações — ver `CAMPOS_FUNDAMENTUS`/
    `CAMPOS_FUNDAMENTUS_OPCIONAIS` em config.py) via scraping do
    Fundamentus. `TickerNaoEncontrado`/`EstruturaPaginaMudou` viram erro
    tratado aqui; qualquer outra exceção propaga (sinal de algo não
    previsto, não um "papel sem indicador")."""
    try:
        return fundamentus.obter_indicadores(ticker), None
    except (TickerNaoEncontrado, EstruturaPaginaMudou) as erro:
        return None, str(erro)


def _buscar_dividendos(ticker: str) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico completo de dividendos pagos — usado pelo método Bazin e
    pelo card de Dividend Yield por ano. Uma ação sem nenhum dividendo
    pago devolve um DataFrame vazio (não erro, ver
    `ingest.precos.obter_dividendos`) — só `TickerInvalido`/
    `FalhaFontePreco` viram o par `(None, motivo)` que os call sites
    checam."""
    try:
        return precos.obter_dividendos(ticker), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


def _emissor_do_ticker(ticker: str) -> dict:
    """CNPJ e segmento setorial do ticker: primeiro no catálogo enxuto que a rodada do screener
    versiona (`data/processed/catalogo_emissores.csv`); só se o ticker não estiver nele, ou o
    arquivo faltar, no catálogo completo da B3 (36 páginas da API). Levanta
    `EmissorNaoEncontrado` se o ticker não tiver emissor correspondente."""
    emissor = crosswalk_cnpj.buscar_no_catalogo_enxuto(
        ticker, crosswalk_cnpj.ler_catalogo_enxuto(config.CAMINHO_CATALOGO_EMISSORES)
    )
    if emissor is not None:
        return emissor
    with st.spinner(TEXTO_SPINNER_CATALOGO_COMPLETO):
        return crosswalk_cnpj.resolver_cnpj(ticker, crosswalk_cnpj.obter_catalogo_emissores())


def _buscar_cnpj(ticker: str) -> tuple[str | None, str | None]:
    """CNPJ da empresa via crosswalk ticker -> catálogo de emissores da B3 (`_emissor_do_ticker`)
    — usado pra buscar dados da CVM (`_buscar_fcf_fcd` abaixo). `EmissorNaoEncontrado` (ticker
    sem emissor correspondente no catálogo) vira o par `(None, motivo)`."""
    try:
        return _emissor_do_ticker(ticker)["cnpj"], None
    except EmissorNaoEncontrado as erro:
        return None, str(erro)


def _buscar_segmento_setorial(ticker: str) -> tuple[str | None, str | None]:
    """Classificação setorial oficial da B3 (campo "segment" do catálogo
    de emissores — ver a nota de investigação em ingest/crosswalk_cnpj.py),
    não confundir com o segmento de LISTAGEM (Novo Mercado/N1/N2) mostrado
    em "Governança" mais abaixo."""
    try:
        return _emissor_do_ticker(ticker)["segmento_setorial"], None
    except EmissorNaoEncontrado as erro:
        return None, str(erro)


@st.cache_data(ttl=3600)
def _buscar_ano_fcd_mais_recente_cacheado() -> int:
    return cvm.resolver_ano_mais_recente_disponivel()


def _buscar_ano_fcd_mais_recente() -> tuple[int | None, str | None]:
    """Ano mais recente do DFP da CVM disponível pra download — nível
    ARQUIVO (`ingest.cvm.resolver_ano_mais_recente_disponivel`), não
    depende do ticker buscado. Cacheado na sessão do Streamlit por 1h —
    sem isso, cada busca de ticker checaria de novo se o zip do ano
    corrente existe. A parte cacheada levanta em vez de devolver `(None,
    erro)`, senão um erro transitório ficaria preso em cache pela 1h
    inteira."""
    try:
        return _buscar_ano_fcd_mais_recente_cacheado(), None
    except Exception as erro:
        return None, f"Falha ao detectar o ano mais recente do DFP da CVM: {erro}"


def _buscar_fcf_fcd(
    cnpj: str, ano_mais_recente: int
) -> tuple[dict, int | None, bool, float | None, dict | None, float | None, str | None]:
    """FCF do FCD com detecção automática de ano POR EMPRESA
    (`ingest.cvm.obter_fluxo_caixa_livre_com_fallback`) — uma chamada só
    que já resolve tanto o ano atual (`ano_mais_recente`, caindo um ano
    só pra essa empresa se ela ainda não apareceu nele) quanto o ano-base
    do crescimento (que anda junto do ano efetivamente usado, não fica
    preso a `ano_mais_recente - ANOS_HISTORICO_CRESCIMENTO_FCD`).

    Devolve (fluxos, ano_utilizado, usou_fallback, caixa_operacional, capex_atual,
    risco_sacado, erro) — `fluxos` é o dict de `modelos.fcd.montar_fluxos_fcd` (fluxo do
    FCD dos dois anos e os motivos de indisponibilidade); `caixa_operacional`
    (o do FCD, ajustado pelo risco sacado e com os juros somados de volta) e
    `capex_atual` (do ano efetivamente usado) alimentam a
    caption de proporção reinvestida no cartão do FCD; `risco_sacado` é a saída líquida
    reclassificada para o caixa operacional nesse ano (negativa, ou zero) (ver
    `modelos.fcd.calcular_proporcao_capex_caixa_operacional_percentual`). Erro
    aqui não é mostrado à parte na tela — já aparece embutido no motivo
    de "não aplicável" do próprio card do FCD (`calcular_valor_
    justo_fcd` trata `fcf_atual=None` internamente)."""
    try:
        resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
            cnpj, ano_mais_recente, ANOS_HISTORICO_CRESCIMENTO_FCD
        )
        return (
            montar_fluxos_fcd(resultado),
            resultado["ano_referencia_utilizado"],
            resultado["usou_fallback"],
            calcular_caixa_operacional_fcd(resultado),
            resultado["capex_atual"],
            (resultado.get("risco_sacado_atual") or {}).get("valor"),
            None,
        )
    except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada) as erro:
        return montar_fluxos_fcd(None), None, False, None, None, None, str(erro)
    except Exception as erro:  # zip da CVM indisponível, erro de rede, etc.
        mensagem = f"Falha ao buscar dados da CVM: {erro}"
        return montar_fluxos_fcd(None), None, False, None, None, None, mensagem


def _buscar_leitura_balanco(cnpj: str, indicadores: dict | None, ticker: str) -> dict:
    """Leitura única do balanço da CVM na data-base do Fundamentus. Falha de
    rede ou da CVM não derruba a página: vira "indisponível" com o motivo, e o
    FCD segue sem os ajustes que dependem dela."""
    if indicadores is None:
        return {"disponivel": False, "motivo": "indicadores do Fundamentus indisponíveis."}
    try:
        return balanco_cvm.obter_leitura_balanco(
            cnpj,
            indicadores["data_balanco_fundamentus"],
            indicadores["numero_acoes"],
            indicadores["acoes_por_cotacao"],
            ticker=ticker,
        )
    except Exception as erro:  # zip da CVM indisponível, erro de rede, etc.
        return {"disponivel": False, "motivo": f"falha ao buscar dados da CVM: {erro}"}


@st.cache_data(ttl=3600)
def _buscar_macro_cacheado() -> ResultadoMacro:
    return bcb_sgs.obter_selic_e_ipca()


def _buscar_macro() -> tuple[ResultadoMacro | None, str | None]:
    """Selic meta, IPCA acumulado 12 meses e a proveniência dos dois (ver
    `ResultadoMacro`), via a função única de `ingest.bcb_sgs`. Cacheado na
    sessão do Streamlit por 1h — não depende do ticker buscado. A parte
    cacheada levanta em vez de devolver `(None, erro)`, senão um erro
    transitório do Banco Central ficaria preso em cache pela 1h inteira,
    contradizendo a própria mensagem de erro ("tente de novo em alguns
    minutos")."""
    try:
        return _buscar_macro_cacheado(), None
    except Exception as erro:
        return None, str(erro)


def _carregar_screener_salvo(caminho: Path) -> pd.DataFrame | None:
    """Lê o resultado do screener já salvo em disco (não roda nada ao
    vivo) — devolve None se o arquivo ainda não existir (primeira vez,
    clone novo do projeto) ou existir só como um arquivo vazio/truncado
    (ex: processo interrompido no meio da escrita), tratado do mesmo jeito
    que "ainda não existe" em vez de quebrar a tela inteira."""
    if not caminho.exists():
        return None

    try:
        tabela = pd.read_csv(caminho)
    except pd.errors.EmptyDataError:
        return None
    # csv.DictWriter grava célula vazia pra string vazia; pd.read_csv, por
    # padrão, lê célula vazia como NaN — sem isso, "sem aviso" viraria NaN
    # em vez de "", que aparece feio na tabela (e detona qualquer checagem
    # tipo `if aviso:` em código futuro, já que NaN é "truthy" em Python).
    for coluna in ("erro", "aviso_desconto_extremo", "metodos_utilizados"):
        tabela[coluna] = tabela[coluna].fillna("")

    return tabela.sort_values(
        "desconto_percentual", ascending=False, na_position="last"
    ).reset_index(drop=True)


def _aviso_screener_vazio(instrucao: str) -> None:
    """Mensagem de "sem resultado salvo ainda" compartilhada entre as páginas
    que dependem do resultado do screener (Analisar uma ação, Screener,
    Simulador de carteira) — cada chamada só varia a instrução de como
    gerá-lo (rodar na própria página Screener, via botão "Rodar screener
    agora", ou apontar pra lá)."""
    st.info(
        "Nenhum resultado salvo ainda (primeira vez rodando o projeto). "
        f"{instrucao} — vai demorar alguns minutos."
    )


def _carregar_screener_ou_avisar(caminho: Path, instrucao: str) -> pd.DataFrame | None:
    """Encapsula o par "carregar (`_carregar_screener_salvo`) + checar
    None + avisar (`_aviso_screener_vazio`)" repetido nas 3 seções que
    dependem do resultado salvo do screener (Analisar uma ação, Screener,
    Simulador de carteira) — cada call site só precisa checar o retorno
    uma vez; o aviso já é mostrado aqui dentro quando não há nada salvo."""
    tabela = _carregar_screener_salvo(caminho)
    if tabela is None:
        if _rodar_screener_permitido():
            _aviso_screener_vazio(instrucao)
        else:
            st.info(TEXTO_SCREENER_AINDA_NAO_GERADO)
    return tabela


def _opt_in_ligado(valor: object) -> bool:
    """Valor de variável de ambiente ou de secret que liga o opt-in (`True`, "1", "true",
    "yes", "sim" ou "on", sem diferenciar maiúsculas)."""
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in VALORES_PERMITIR_RODAR_SCREENER


def _rodar_screener_permitido() -> bool:
    """O botão "Rodar screener agora" só existe quando quem opera o servidor liga
    `VARIAVEL_PERMITIR_RODAR_SCREENER` (variável de ambiente ou secret); sem isso, como no
    app publicado, o screener só é atualizado pelo workflow."""
    if _opt_in_ligado(os.environ.get(VARIAVEL_PERMITIR_RODAR_SCREENER)):
        return True
    try:
        return _opt_in_ligado(st.secrets.get(VARIAVEL_PERMITIR_RODAR_SCREENER))
    except StreamlitSecretNotFoundError:
        return False


def _data_da_ultima_rodada() -> pd.Timestamp | str | None:
    """Data da última rodada aceita do screener (o `rodada.json`); sem ele, a data da busca da
    Selic e do IPCA do arquivo de referência, e `None` se nenhum dos dois existir."""
    data_rodada = rodada.carregar_data_rodada()
    if data_rodada is not None:
        return data_rodada
    macro = bcb_sgs.carregar_macro_referencia()
    return None if macro is None else macro["data_busca"]


def _texto_screener_atualizado_pelo_workflow() -> str:
    """Aviso do app publicado, com a data da última rodada aceita; o horário do arquivo no
    disco seria o do deploy."""
    data_rodada = _data_da_ultima_rodada()
    if data_rodada is None:
        return TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA
    return TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW.format(data=_fmt_data(data_rodada))


@st.cache_data(ttl=3600)
def _buscar_serie_bcb_cacheada(codigo: int, data_inicial: str, data_final: str) -> pd.DataFrame:
    return bcb_sgs.obter_serie_com_fallback(
        codigo, data_inicial=data_inicial, data_final=data_final
    )


def _buscar_serie_bcb(
    chave: str, nome: str, inicio: datetime
) -> tuple[pd.DataFrame | None, str | None]:
    """IPCA mensal ou CDI diário (`SERIES_BCB_SGS[chave]`) desde `inicio`, cacheado na sessão por
    1h; a parte cacheada levanta em vez de devolver `(None, erro)`, para um erro transitório não
    ficar preso em cache."""
    hoje = datetime.now()
    try:
        serie = _buscar_serie_bcb_cacheada(
            SERIES_BCB_SGS[chave], inicio.strftime("%d/%m/%Y"), hoje.strftime("%d/%m/%Y")
        )
    except Exception as erro:
        return None, TEXTO_INDICE_INDISPONIVEL.format(nome=nome, motivo=erro)
    return serie, None
