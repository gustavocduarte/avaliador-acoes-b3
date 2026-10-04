"""Dashboard (Streamlit) do Avaliador de Ações da B3 — ferramenta de
avaliação de valor justo para ações principais da B3 (bolsa brasileira),
com projeções apresentadas sempre como cenários (pessimista/base/
otimista), nunca como um número único. Só chama os adapters/modelos que
já existem e organiza o resultado na tela; nenhuma lógica de cálculo é
reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

# O projeto não está instalado como pacote (sem pyproject [project]/pip
# install -e . ainda) — `streamlit run` não adiciona src/ ao sys.path
# sozinho como o pytest faz via pythonpath, então isso resolve na mão.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from avaliador_b3.carteira import (
    calcular_totais_carteira,
    montar_tabela_carteira,
)
from avaliador_b3.config import (
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    ANOS_JANELA_CORRELACAO,
    AVISO_MACRO_ARQUIVO_REFERENCIA,
    AVISO_MACRO_IPCA_FONTE,
    AVISO_MACRO_MESMA_FONTE,
    AVISO_MACRO_SELIC_FONTE,
    AVISO_PRECO_INDISPONIVEL,
    AVISO_SIMULADOR_SEM_PREVISAO,
    COR_GRAFICO_CONTEXTO,
    COR_GRAFICO_FUNDO,
    COR_GRAFICO_GRADE,
    COR_GRAFICO_PROTAGONISTA,
    COR_GRAFICO_TEXTO,
    FRASE_FONTE_MACRO,
    FRASE_RESUMO_SIMULADOR,
    JANELAS_COMPARACAO_PETROLEO,
    LEGENDA_REINVESTIMENTO_CAPEX,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    PERIODO_PRECO_ATUAL,
    PREFIXO_FONTE_ARQUIVO_REFERENCIA,
    RAZAO_DIVIDENDOS_ATIPICA_BAZIN,
    ROTULO_POTENCIAL,
    ROTULOS_COMPONENTES_VALOR_FIRMA,
    ROTULOS_POTENCIAL_CENARIO,
    ROTULOS_TOTAL_AO_CONVERGIR,
    ROTULOS_VALOR_AO_CONVERGIR,
    SERIES_BCB_SGS,
    SUBTITULO_POTENCIAL_CARTEIRA,
    TEXTO_ABERTURA_SIMULADOR,
    TEXTO_COMPLEMENTO_SEM_METODO,
    TEXTO_CRESCIMENTO_IPCA,
    TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA,
    TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA,
    TEXTO_EXPANDER_SIMULADOR,
    TEXTO_FCD_AJUSTES_DO_BALANCO,
    TEXTO_FIRMA_SEM_COMPONENTES,
    TEXTO_RISCO_SACADO_RECLASSIFICADO,
    TEXTO_RODADA_DESCARTADA,
    TEXTO_SCREENER_CONCLUIDO,
    TEXTO_SCREENER_CONCLUIDO_COM_FALHAS,
    TEXTO_SEM_ACOES_EM_CIRCULACAO,
    TEXTO_SEM_AJUSTES_DO_BALANCO,
    TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA,
    TEXTO_SEM_DESCONTO_NAO_CONTROLADORES,
    TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS,
    TICKER_PETROLEO_BRENT,
    TITULO_EXPANDER_SIMULADOR,
    TOOLTIP_POTENCIAL_CARTAO,
    TOOLTIP_POTENCIAL_CENARIO,
    TOOLTIP_POTENCIAL_COLUNA,
    TOOLTIP_VALOR_FIRMA,
    YIELD_MINIMO_BAZIN,
)
from avaliador_b3.correlacao import calcular_correlacoes_fatores, classificar_magnitude_correlacao
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
from avaliador_b3.empresa.valor_mercado import calcular_valor_mercado_e_firma
from avaliador_b3.graficos import (
    agregar_dividendos_por_ano,
    calcular_dividend_yield_por_ano,
    normalizar_base_100,
    ticks_mensais_pt_br,
)
from avaliador_b3.ingest.b3_universo import obter_universo_ibovespa
from avaliador_b3.ingest.balanco_cvm import obter_leitura_balanco
from avaliador_b3.ingest.bcb_sgs import (
    ResultadoMacro,
    obter_selic_e_ipca,
    obter_serie_com_fallback,
)
from avaliador_b3.ingest.crosswalk_cnpj import (
    EmissorNaoEncontrado,
    obter_catalogo_emissores,
    resolver_cnpj,
    resolver_segmentos_setoriais,
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
from avaliador_b3.ingest.gpr import obter_gpr
from avaliador_b3.ingest.precos import (
    FalhaFontePreco,
    TickerInvalido,
    obter_dividendos,
    obter_historico,
    obter_historico_ibovespa,
    preco_valido,
)
from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin
from avaliador_b3.modelos.combinado import calcular_divergencia_metodos, calcular_valor_combinado
from avaliador_b3.modelos.fcd import (
    calcular_caixa_operacional_fcd,
    calcular_proporcao_capex_caixa_operacional_percentual,
    calcular_valor_justo_fcd,
    montar_ajustes_balanco,
    montar_fluxos_fcd,
)
from avaliador_b3.modelos.graham import calcular_valor_justo_graham, reescalar_lpa_vpa
from avaliador_b3.screener import (
    CAMINHO_SAIDA_PADRAO,
    DeteccaoAnoCvmFalhouWarning,
    FundamentusIndisponivelWarning,
    MacroIndisponivelWarning,
    RodadaScreenerRejeitada,
    rodar_screener,
)

MENSAGEM_MACRO_INDISPONIVEL_CURTA = "Selic/IPCA indisponíveis agora — veja o aviso no topo."

COLUNAS_TABELA_SCREENER = [
    "ticker",
    "preco_atual",
    "valor_combinado",
    "desconto_percentual",
    "divergencia_percentual_metodos",
    "bazin_razao_dividendos_percentual",
    "proporcao_reinvestimento_percentual",
    "metodos_utilizados",
    "aviso_desconto_extremo",
    "erro",
]

COLUNAS_TABELA_CARTEIRA = [
    "ticker",
    "valor_investido",
    "preco_atual",
    "projecao_pessimista",
    "retorno_pessimista_percentual",
    "projecao_base",
    "retorno_base_percentual",
    "projecao_otimista",
    "retorno_otimista_percentual",
]


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
    historico = obter_historico(ticker, periodo=periodo, auto_adjust=auto_adjust)
    if historico.empty:
        raise FalhaFontePreco(f"Histórico de {ticker!r} veio vazio — tente de novo mais tarde.")
    return historico


def _buscar_historico_ibovespa(periodo: str) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico do Ibovespa — mesmo tratamento de "vazio sem exceção
    vira erro" que `_buscar_historico` (ver docstring lá), pelo mesmo
    motivo defensivo."""
    try:
        historico = obter_historico_ibovespa(periodo=periodo)
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
    return obter_serie_com_fallback(
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
    return obter_gpr(serie="diaria")


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
    return obter_universo_ibovespa()


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
        return obter_indicadores(ticker), None
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
        return obter_dividendos(ticker), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


def _buscar_cnpj(ticker: str) -> tuple[str | None, str | None]:
    """CNPJ da empresa via crosswalk ticker -> catálogo de emissores da
    B3 (`ingest.crosswalk_cnpj`) — usado pra buscar dados da CVM
    (`_buscar_fcf_fcd` abaixo). `EmissorNaoEncontrado` (ticker sem emissor
    correspondente no catálogo) vira o par `(None, motivo)`."""
    try:
        catalogo = obter_catalogo_emissores()
        return resolver_cnpj(ticker, catalogo)["cnpj"], None
    except EmissorNaoEncontrado as erro:
        return None, str(erro)


def _buscar_segmento_setorial(ticker: str) -> tuple[str | None, str | None]:
    """Classificação setorial oficial da B3 (campo "segment" do catálogo
    de emissores — ver a nota de investigação em ingest/crosswalk_cnpj.py),
    não confundir com o segmento de LISTAGEM (Novo Mercado/N1/N2) mostrado
    em "Governança" mais abaixo."""
    try:
        catalogo = obter_catalogo_emissores()
        return resolver_cnpj(ticker, catalogo)["segmento_setorial"], None
    except EmissorNaoEncontrado as erro:
        return None, str(erro)


@st.cache_data(ttl=3600)
def _buscar_ano_fcd_mais_recente_cacheado() -> int:
    return resolver_ano_mais_recente_disponivel()


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
        resultado = obter_fluxo_caixa_livre_com_fallback(
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


def _buscar_leitura_balanco(cnpj: str, indicadores: dict | None) -> dict:
    """Leitura única do balanço da CVM na data-base do Fundamentus. Falha de
    rede ou da CVM não derruba a página: vira "indisponível" com o motivo, e o
    FCD segue sem os ajustes que dependem dela."""
    if indicadores is None:
        return {"disponivel": False, "motivo": "indicadores do Fundamentus indisponíveis."}
    try:
        return obter_leitura_balanco(
            cnpj,
            indicadores["data_balanco_fundamentus"],
            indicadores["numero_acoes"],
            indicadores["acoes_por_cotacao"],
        )
    except Exception as erro:  # zip da CVM indisponível, erro de rede, etc.
        return {"disponivel": False, "motivo": f"falha ao buscar dados da CVM: {erro}"}


@st.cache_data(ttl=3600)
def _buscar_macro_cacheado() -> ResultadoMacro:
    return obter_selic_e_ipca()


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


def _widget_avancado_tradingview(ticker: str) -> str:
    """HTML do widget "Advanced Chart" do TradingView (embutido via
    st.components.v1.html), símbolo montado dinamicamente a partir do
    ticker buscado na tela — ver
    https://br.tradingview.com/widget/advanced-chart/. Puramente
    HTML/JS estático interpolado, sem lógica Python nossa por trás; se o
    JavaScript não carregar (rede/ambiente restrito), o widget só fica em
    branco, sem quebrar o resto da página."""
    return f"""
    <style>html, body {{ height: 100%; margin: 0; }}</style>
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget"
        style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
        async>
      {{
        "autosize": true,
        "symbol": "BMFBOVESPA:{ticker}",
        "interval": "D",
        "timezone": "America/Sao_Paulo",
        "theme": "dark",
        "style": "1",
        "locale": "br",
        "allow_symbol_change": true,
        "support_host": "https://www.tradingview.com"
      }}
      </script>
    </div>
    """


def _grafico_comparacao_normalizada(
    serie_a: pd.DataFrame, nome_a: str, serie_b: pd.DataFrame, nome_b: str
) -> tuple[go.Figure | None, list[str]]:
    """Gráfico de linha com duas séries de preço normalizadas pra base 100
    (`graficos.normalizar_base_100`) — necessário pra sobrepor séries de
    escala bruta muito diferente (ação em R$ dezenas vs. Ibovespa em
    ~130 mil pontos, ou vs. petróleo Brent em US$ dezenas) no mesmo eixo
    sem uma delas virar uma linha reta ilegível. Compartilhado entre
    "Preço vs. Ibovespa" e "Comparando com Petróleo (Brent)", que só
    diferem nas séries/nomes passados.

    Devolve `(figura, nomes_sem_dados)`. `nomes_sem_dados` lista
    `nome_a`/`nome_b` cuja série não teve "base 100" calculável (ver
    `graficos.normalizar_base_100`); `figura` vem `None` sempre que essa
    lista não for vazia — mesmo com a outra série ainda válida, uma
    figura com uma das linhas invisível não é útil sem dizer por quê, e
    quem chama decide a mensagem a partir de `nomes_sem_dados`."""
    normalizado_a = normalizar_base_100(serie_a["Close"])
    normalizado_b = normalizar_base_100(serie_b["Close"])
    nomes_sem_dados = [
        nome
        for nome, normalizado in ((nome_a, normalizado_a), (nome_b, normalizado_b))
        if normalizado.isna().all()
    ]
    if nomes_sem_dados:
        return None, nomes_sem_dados

    figura = go.Figure()
    figura.add_trace(
        go.Scatter(
            x=serie_a["data"],
            y=normalizado_a,
            name=nome_a,
            line={"color": COR_GRAFICO_PROTAGONISTA},
        )
    )
    figura.add_trace(
        go.Scatter(
            x=serie_b["data"],
            y=normalizado_b,
            name=nome_b,
            line={"color": COR_GRAFICO_CONTEXTO},
        )
    )
    figura.update_layout(
        yaxis_title="Desempenho (base 100 no início do período)",
        xaxis_title="Data",
        hovermode="x unified",
        margin={"t": 20},
        paper_bgcolor=COR_GRAFICO_FUNDO,
        plot_bgcolor=COR_GRAFICO_FUNDO,
        font={"color": COR_GRAFICO_TEXTO},
    )
    tickvals, ticktext = ticks_mensais_pt_br(serie_a["data"])
    figura.update_xaxes(
        gridcolor=COR_GRAFICO_GRADE, tickmode="array", tickvals=tickvals, ticktext=ticktext
    )
    figura.update_yaxes(gridcolor=COR_GRAFICO_GRADE)
    return figura, []


def _mensagem_grafico_comparacao_sem_dados(nomes_sem_dados: list[str]) -> str:
    """Mensagem mostrada no lugar do gráfico quando `_grafico_comparacao_
    normalizada` devolve `figura=None` — nomeia a série sem dados quando
    só uma falhou, pra não esconder que a outra está ok."""
    if len(nomes_sem_dados) == 1:
        return f"Sem dados suficientes de {nomes_sem_dados[0]} para montar este gráfico."
    return "Sem dados suficientes para montar este gráfico."


def _delta_percentual_upside(valor: float, preco_atual: float | None) -> str | None:
    """Diferença percentual entre `valor` (valor justo de um método) e o
    preço atual — (valor - preco_atual) / preco_atual × 100, pro
    parâmetro `delta` do st.metric. Cor padrão do Streamlit, SEM inverter
    (`delta_color="normal"`, o default): aqui valor justo maior que o
    preço é upside, sinal bom = verde — diferente de outros deltas do
    projeto onde "maior é pior" e por isso usam `delta_color="inverse"`.

    `None` (sem delta nenhum, não um "0%" inventado) quando `preco_atual`
    não está disponível — st.metric já trata `delta=None` como "não
    mostrar o indicador"."""
    if preco_atual is None:
        return None
    return _fmt_percentual((valor - preco_atual) / preco_atual * 100)


def _cartao_metodo(
    nome: str, resultado: dict, rotulo_valor: str, preco_atual: float | None
) -> None:
    """Renderiza um cartão de método de valor justo (Graham/Bazin/FCD):
    `st.metric` com o valor e delta de upside contra `preco_atual` quando
    `resultado["aplicavel"]`, ou "—" com o motivo em `st.caption` quando
    não. `resultado` é o dict padrão `{"aplicavel", rotulo_valor,
    "motivo_nao_aplicavel"}` que os três modelos já devolvem —
    `rotulo_valor` é o nome da chave do valor em si (`"valor_justo"` pra
    Graham/FCD, `"preco_teto"` pro Bazin, já que os métodos não usam o
    mesmo nome de campo).

    `resultado.get("divida_liquida_deduzida")` só existe no dict do FCD
    (ver modelos/fcd.py) — quando presente e `False`, mostra um aviso no
    lugar de "Aplicável": o valor não teve dívida líquida deduzida (dado
    ausente pra essa empresa específica — banco nunca chega aqui, já é
    "não aplicável" antes, ver
    config.SEGMENTOS_FCD_NAO_APLICAVEL), então aproxima Enterprise Value
    como Equity Value em vez do valor real por ação."""
    if resultado["aplicavel"]:
        st.metric(
            nome,
            _fmt_bilhoes(resultado[rotulo_valor]),
            delta=_delta_percentual_upside(resultado[rotulo_valor], preco_atual),
            help=TOOLTIP_POTENCIAL_CARTAO,
        )
        if resultado.get("divida_liquida_deduzida") is False:
            st.caption(
                "Dívida líquida indisponível pra essa empresa — sem ela pra "
                "deduzir, este valor não desconta a dívida da empresa, então "
                "tende a ficar mais alto do que se a dedução fosse possível."
            )
        else:
            st.caption("Aplicável")
        # Sem balanço da CVM, os três ajustes que dependem dele ficam de fora pelo mesmo
        # motivo: uma legenda só, em vez de três iguais.
        motivo_sem_nao_controladores = resultado.get("motivo_sem_nao_controladores")
        motivo_sem_arrendamento = resultado.get("motivo_sem_arrendamento")
        motivo_sem_patrimonio_total = resultado.get("motivo_sem_patrimonio_total")
        motivos_do_balanco = {
            motivo_sem_nao_controladores,
            motivo_sem_arrendamento,
            motivo_sem_patrimonio_total,
        }
        balanco_inteiro_indisponivel = (
            len(motivos_do_balanco) == 1 and None not in motivos_do_balanco
        )
        if balanco_inteiro_indisponivel:
            st.caption(TEXTO_SEM_AJUSTES_DO_BALANCO.format(motivo=motivo_sem_nao_controladores))
        elif motivo_sem_nao_controladores:
            st.caption(
                TEXTO_SEM_DESCONTO_NAO_CONTROLADORES.format(motivo=motivo_sem_nao_controladores)
            )
        motivo_sem_acoes = resultado.get("motivo_sem_acoes_em_circulacao")
        if motivo_sem_acoes:
            st.caption(TEXTO_SEM_ACOES_EM_CIRCULACAO.format(motivo=motivo_sem_acoes))
        if motivo_sem_arrendamento and not balanco_inteiro_indisponivel:
            st.caption(TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA.format(motivo=motivo_sem_arrendamento))
        if motivo_sem_patrimonio_total and not balanco_inteiro_indisponivel:
            st.caption(
                TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS.format(motivo=motivo_sem_patrimonio_total)
            )
        motivo_crescimento_ipca = resultado.get("motivo_crescimento_ipca")
        if motivo_crescimento_ipca:
            st.caption(TEXTO_CRESCIMENTO_IPCA.format(motivo=motivo_crescimento_ipca))
        if resultado.get("crescimento_limitado_pela_receita"):
            st.caption(
                TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA.format(
                    taxa=_fmt_percentual(resultado["taxa_crescimento_receita"] * 100, 1)
                )
            )
        elif resultado.get("motivo_sem_limite_da_receita"):
            st.caption(
                TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA.format(
                    motivo=resultado["motivo_sem_limite_da_receita"]
                )
            )
    else:
        st.metric(nome, "—")
        st.caption(f"Não aplicável: {resultado['motivo_nao_aplicavel']}")


def _cartao_correlacao(nome: str, resultado: dict) -> None:
    """Renderiza um cartão de correlação (petróleo/câmbio/GPR):
    `st.metric` com o coeficiente e a leitura de magnitude
    (`correlacao.classificar_magnitude_correlacao`) quando
    `resultado["aplicavel"]`, ou "—" com o motivo quando não — mesmo
    formato de dict que `correlacao.calcular_correlacao` devolve."""
    if not resultado["aplicavel"]:
        st.metric(nome, "—")
        st.caption(f"Indisponível: {resultado['motivo_nao_aplicavel']}")
        return

    magnitude = classificar_magnitude_correlacao(resultado["correlacao"])
    st.metric(nome, _fmt(resultado["correlacao"]))
    st.caption(f"Correlação {magnitude} ({resultado['observacoes']} observações)")


def _pt_br(texto: str) -> str:
    """Converte um texto já formatado no padrão americano (ponto decimal,
    vírgula de milhar) pra convenção brasileira (vírgula decimal, ponto de
    milhar) — troca em três passos com um placeholder intermediário pra
    "," e "." não se pisarem (ex: "1,234.56" -> "1_234.56" -> "1_234,56"
    -> "1.234,56"). Não depende de locale de sistema/navegador (idem
    `graficos.ticks_mensais_pt_br` pros meses do eixo dos gráficos) —
    Python/JS não garantem qual locale está instalado em produção."""
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt(valor: float | None, template: str = "{:.2f}") -> str:
    """Formata um número, na convenção brasileira (vírgula decimal), ou
    "N/D" se ausente — indicador individual faltando (ex: banco sem Dív
    Líq/Patrim no Fundamentus) não deve quebrar a tela nem virar um "None"
    cru na tela. `pd.isna` (não `is None`) porque também roda sobre
    valores vindos direto de coluna de DataFrame/CSV (tabelas com
    NumberColumn convertidas pra texto) — lá, ausente é NaN, não None."""
    return _pt_br(template.format(valor)) if not pd.isna(valor) else "N/D"


def _fmt_percentual(valor: float | None, casas: int = 1) -> str:
    """Formata um percentual na convenção brasileira (vírgula decimal,
    ponto de milhar acima de 1.000%) — usado pros deltas de upside dos
    cartões de Valor Justo e pelas colunas de potencial; não passa por
    `_fmt` porque não é só "número + template fixo" (delta é opcional/
    `None`, o potencial já vem multiplicado por 100 antes de chamar).
    "N/D" se ausente (`pd.isna`, ver `_fmt`)."""
    if pd.isna(valor):
        return "N/D"
    return _pt_br(f"{valor:,.{casas}f}%")


def _fmt_bilhoes(valor: float | None) -> str:
    """Formata um valor monetário — Valor de Mercado/Firma, Dívida Líquida
    ("Saúde financeira"), e os totais da carteira ("Total da carteira") —
    abreviando a partir de R$ 1 milhão (em módulo, então um valor negativo
    grande — ex: dívida líquida em posição de caixa líquido — também abrevia
    com o sinal preservado): "X,X bi" a partir de R$ 1 bilhão, "X,X mi" de
    R$ 1 milhão até ali. Abaixo de R$ 1 milhão mostra o valor completo,
    formatado por extenso ("R$ X.XXX,XX", convenção brasileira de milhar/
    decimal) — não faz sentido abreviar R$ 1.000 pra "R$ 0,0 mi". "N/D" se
    ausente.

    Sem essa abreviação (ou com o piso baixo demais), valores grandes seriam
    truncados com reticências pelo st.metric dentro das colunas estreitas de 4
    do projeto (ex: "R$ 625,1..." em "Saúde financeira"). "N/D" se ausente
    (`pd.isna`, ver `_fmt`)."""
    if valor is None or pd.isna(valor):
        return "N/D"
    if abs(valor) >= 1e9:
        return _pt_br(f"R$ {valor / 1e9:.1f} bi")
    if abs(valor) >= 1e6:
        return _pt_br(f"R$ {valor / 1e6:.1f} mi")
    return _pt_br(f"R$ {valor:,.2f}")


def _fmt_bilhoes_md(valor: float | None) -> str:
    """`_fmt_bilhoes` com o "$" escapado (`\\$`) — pra uso dentro de
    `st.caption`/`st.markdown`, nunca em `st.metric` (que exibe o valor
    cru, sem markdown — a barra invertida apareceria literalmente na
    tela). Sem isso, DUAS chamadas de `_fmt_bilhoes` na mesma caption
    (ex: "de R$ X a R$ Y") criam um par de "$" que o Streamlit interpreta
    como abre/fecha de fórmula LaTeX: o
    trecho entre os dois cifrões virava matemática renderizada, cortando
    o texto ("R" de um lado, o valor seguinte do outro). Escapar os dois
    "$" resolve sem precisar reescrever o texto pra evitar o padrão."""
    return _fmt_bilhoes(valor).replace("$", "\\$")


def _aviso_fonte_macro(macro: ResultadoMacro) -> str:
    """Texto sobre a origem da Selic e do IPCA quando algum veio de fonte que não é a API
    REST do Banco Central; vazio quando ambos vieram dela (ou de valor guardado)."""
    if macro.usou_valor_guardado:
        return ""
    frase_selic = FRASE_FONTE_MACRO.get(macro.fonte_selic)
    frase_ipca = FRASE_FONTE_MACRO.get(macro.fonte_ipca)
    if frase_selic and frase_selic == frase_ipca:
        return AVISO_MACRO_MESMA_FONTE.format(frase=frase_selic)
    partes = []
    if frase_selic:
        partes.append(AVISO_MACRO_SELIC_FONTE.format(frase=frase_selic))
    if frase_ipca:
        partes.append(AVISO_MACRO_IPCA_FONTE.format(frase=frase_ipca))
    return " ".join(partes)


def _fmt_data(valor: pd.Timestamp | str | None, template: str = "%d/%m/%Y") -> str:
    """Formata uma data (Timestamp do pandas, vindo direto da coluna
    `data` dos DataFrames de preço, ou string ISO "aaaa-mm-dd", vinda de
    `data_balanco_fundamentus`) no padrão brasileiro, ou "N/D" se ausente
    — mesmo padrão de `_fmt` pra dado faltante. Usado só no bloco "Datas
    de referência dos dados usados" da seção Valor Justo. `template`
    customizável pro caso do IPCA, mensal — só faz sentido mostrar mês/
    ano, não um dia exato que a série não tem."""
    if valor is None or pd.isna(valor):
        return "N/D"
    if isinstance(valor, str):
        valor = datetime.strptime(valor, "%Y-%m-%d")
    return pd.Timestamp(valor).strftime(template)


def _tabela_formatada_pt_br(
    df: pd.DataFrame,
    colunas_moeda: dict[str, str],
    colunas_percentual: dict[str, str] | None = None,
    ajudas: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Pré-formata colunas monetárias/percentuais de `df` como texto em
    convenção brasileira (`_fmt_bilhoes`/`_fmt_percentual`) e monta o
    `column_config` correspondente, pronto pra passar pro `st.dataframe`
    — devolve `(df_formatado, column_config)`. `colunas_moeda`/
    `colunas_percentual` são dicts `{nome_da_coluna: rótulo_exibido}`;
    `ajudas` (opcional) é `{nome_da_coluna: tooltip}`.

    Por que texto pré-formatado, não `st.column_config.NumberColumn
    (format=...)`: o `format` do NumberColumn é sprintf-js/d3-format por
    baixo, nenhum dos dois tem vírgula decimal brasileira em qualquer
    locale, e a opção `format="localized"` do Streamlit usa
    `Intl.NumberFormat` com o locale do NAVEGADOR de quem visita (não do
    nosso código) — mesmo anti-padrão já rejeitado pro locale de mês dos
    gráficos (ver `graficos.ticks_mensais_pt_br`), não dá pra garantir
    pt-BR pra todo visitante.

    Custo aceito: clicar no cabeçalho de uma coluna formatada por aqui
    pra reordenar ordena como TEXTO (alfabético, ex: "R$ 1.000,00" antes
    de "R$ 618,70"), não numericamente — as demais colunas da tabela
    (que não passam por aqui) continuam ordenando normal. Usado nas 4
    tabelas do projeto que mostram R$/%: Comparação Setorial, Screener,
    Simulador de carteira, Ganho nominal vs. real."""
    colunas_percentual = colunas_percentual or {}
    ajudas = ajudas or {}
    df_formatado = df.assign(**{coluna: df[coluna].apply(_fmt_bilhoes) for coluna in colunas_moeda})
    if colunas_percentual:
        df_formatado = df_formatado.assign(
            **{coluna: df_formatado[coluna].apply(_fmt_percentual) for coluna in colunas_percentual}
        )
    column_config = {
        coluna: st.column_config.TextColumn(rotulo, alignment="right", help=ajudas.get(coluna))
        for coluna, rotulo in {**colunas_moeda, **colunas_percentual}.items()
    }
    return df_formatado, column_config


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
    """Mensagem de "sem resultado salvo ainda" compartilhada entre as abas
    que dependem do resultado do screener (Analisar uma ação, Screener,
    Simulador de carteira) — cada chamada só varia a instrução de como
    gerá-lo (rodar na própria aba Screener, via botão "Rodar screener
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
        _aviso_screener_vazio(instrucao)
    return tabela


ABA_ANALISAR = "Analisar uma ação"
ABA_SCREENER = "Screener (todas as ações)"
ABA_CARTEIRA = "Simulador de carteira"

# Ticker pré-selecionado e buscado automaticamente só na primeira abertura da
# sessão (ver `busca_inicial_automatica_feita` em session_state, mais abaixo)
# — mostra um resultado de exemplo de cara, sem exigir clique em "Buscar".
TICKER_PADRAO_PRIMEIRA_ABERTURA = "PETR4"

st.set_page_config(page_title="Avaliador B3 (protótipo)", page_icon="📈", layout="wide")
st.title("Avaliador de Ações da B3")
st.caption(
    "Ferramenta de avaliação de valor justo para ações principais da B3 (bolsa "
    "brasileira), com projeções apresentadas sempre como cenários "
    "(pessimista/base/otimista) — nunca como um número único."
)


def _ativar_aba(aba: str) -> None:
    """Callback de on_click: roda ANTES do script recarregar (diferente de
    só checar o retorno de st.button, que só teria efeito no rerun
    seguinte) — por isso é a forma certa de fixar a aba ativa a tempo do
    st.tabs() abaixo já nascer com o valor certo neste mesmo rerun."""
    st.session_state["aba_ativa"] = aba


# `default` fixa qual aba aparece selecionada neste rerun — sem isso, todo
# st.rerun() (ex: ao terminar "Rodar screener agora") volta pra primeira aba,
# mesmo que a pessoa estivesse vendo a outra. Guardamos a aba "atual" em
# session_state, atualizada via on_click nos botões que disparam rerun.
st.session_state.setdefault("aba_ativa", ABA_ANALISAR)
aba_analisar, aba_screener, aba_carteira = st.tabs(
    [ABA_ANALISAR, ABA_SCREENER, ABA_CARTEIRA],
    default=st.session_state["aba_ativa"],
)

with aba_analisar:
    # Buscado aqui em cima (não só depois de "Buscar") porque o dropdown
    # abaixo precisa da lista de opções pra se desenhar — reaproveitado
    # mais adiante na seção "Governança", não buscado de novo lá.
    universo_ibovespa, erro_universo = _buscar_universo_ibovespa()
    usando_dropdown = not (erro_universo or universo_ibovespa is None or universo_ibovespa.empty)

    busca_inicial_ja_feita = st.session_state.get("busca_inicial_automatica_feita", False)

    if usando_dropdown:
        assert universo_ibovespa is not None, "o dropdown só é usado com o universo carregado"
        nomes_por_ticker = dict(
            zip(universo_ibovespa["ticker"], universo_ibovespa["nome"], strict=True)
        )
        opcoes_ticker = list(nomes_por_ticker.keys())
        # Pré-seleciona o ticker padrão só na primeira abertura da sessão
        # (session_state ainda sem a flag) — nas próximas reruns, `index`
        # deixa de forçar nada e o dropdown segue 100% manual, preservando
        # o que a pessoa escolher por conta própria. `key` explícita e
        # ESTÁVEL é essencial aqui: sem ela, o Streamlit deriva a
        # identidade do widget (entre outras coisas) do próprio `index` —
        # como `index` muda de 0 pra None entre reruns, um widget sem
        # `key` fixa "reseta" nesse ponto e perde a seleção do usuário.
        indice_inicial = (
            opcoes_ticker.index(TICKER_PADRAO_PRIMEIRA_ABERTURA)
            if not busca_inicial_ja_feita and TICKER_PADRAO_PRIMEIRA_ABERTURA in opcoes_ticker
            else None
        )
        ticker_selecionado = st.selectbox(
            "Ação (Ibovespa)",
            options=opcoes_ticker,
            format_func=lambda t: f"{t} — {nomes_por_ticker[t]}",
            key="dropdown_ticker_analisar",
            index=indice_inicial,
            placeholder="Selecione uma ação...",
        )
        ticker = ticker_selecionado or ""
    else:
        # Degradação graciosa: a API da B3 pode estar fora do ar — a aba
        # continua usável via texto livre, só sem a lista pronta. Sem
        # dropdown não há como pré-selecionar nada, então a busca
        # automática da primeira abertura não se aplica nesse caminho.
        st.warning(
            "Lista de ações do Ibovespa indisponível "
            f"({erro_universo or 'resultado vazio'}) — digite o ticker manualmente."
        )
        ticker = st.text_input("Ticker (ex: PETR4)", value="").strip().upper()

    buscar_clicado = st.button("Buscar", on_click=_ativar_aba, args=(ABA_ANALISAR,))

    # Dispara a busca automaticamente só na primeira abertura da sessão,
    # equivalente a já ter clicado em "Buscar" uma vez — marca a flag em
    # session_state antes de qualquer coisa pra garantir que isso não se
    # repete em nenhum rerun futuro (troca de aba, outra busca, etc.).
    busca_automatica_primeira_abertura = (
        usando_dropdown and not busca_inicial_ja_feita and ticker == TICKER_PADRAO_PRIMEIRA_ABERTURA
    )
    if busca_automatica_primeira_abertura:
        st.session_state["busca_inicial_automatica_feita"] = True
    buscar = buscar_clicado or busca_automatica_primeira_abertura

    if buscar and not ticker:
        st.warning("Selecione uma ação." if usando_dropdown else "Digite um ticker.")

    if buscar and ticker:
        st.session_state["ticker_com_resultado_exibido"] = ticker

    # "Sticky": uma vez buscado com sucesso, o resultado continua visível em
    # reruns disparados por outros widgets DENTRO da seção de resultado (ex:
    # as pills de "Comparando com Petróleo" mais abaixo) — sem isso, só trocar
    # a janela de comparação apagaria a página inteira, já que qualquer
    # widget com estado dispara um rerun do zero e `buscar` sozinho só é True
    # no exato rerun do clique em "Buscar". As buscas abaixo já têm cache
    # próprio (disco com TTL, ou st.cache_data), então reexecutá-las num
    # rerun "sticky" é barato — não bate na rede de novo.
    mostrar_resultado = bool(ticker) and (
        buscar or ticker == st.session_state.get("ticker_com_resultado_exibido")
    )

    if mostrar_resultado:
        with st.spinner(f"Buscando dados de {ticker}..."):
            historico, erro_historico = _buscar_historico(ticker, PERIODO_HISTORICO_COMPORTAMENTO)
            # Busca separada (não reaproveita `historico`) só pro card "Preço
            # atual": o endpoint de histórico diário do yfinance (o mesmo por
            # trás de PERIODO_HISTORICO_COMPORTAMENTO) atrasa um pregão
            # inteiro, mesmo já encerrado — period="1d" traz o fechamento
            # mais recente disponível de verdade. Ver o comentário em
            # config.py com a investigação completa (discrepância real
            # encontrada contra o TradingView).
            historico_preco_atual, erro_preco_atual = _buscar_historico(ticker, PERIODO_PRECO_ATUAL)
            historico_beta, erro_historico_beta = _buscar_historico(ticker, PERIODO_BETA)
            historico_ibovespa_beta, erro_historico_ibovespa_beta = _buscar_historico_ibovespa(
                PERIODO_BETA
            )
            indicadores, erro_indicadores = _buscar_indicadores_fundamentus(ticker)
            dividendos, erro_dividendos = _buscar_dividendos(ticker)
            cnpj, erro_cnpj = _buscar_cnpj(ticker)
            # Buscado aqui (cedo, perto do cnpj) pra alimentar o FCD logo
            # abaixo — não decide se o FCD se aplica com nenhum outro dado
            # já buscado (ver config.SEGMENTOS_FCD_NAO_APLICAVEL), só o
            # segmento setorial. "Comparação setorial" mais abaixo
            # reaproveita esse mesmo resultado, não busca de novo.
            segmento_setorial, erro_segmento_setorial = _buscar_segmento_setorial(ticker)
            macro, erro_macro = _buscar_macro()
            selic_meta = macro.selic_meta if macro else None
            ipca_12m = macro.ipca_12m if macro else None
            data_ipca = macro.data_ipca if macro else None
            macro_usou_valor_guardado = macro.usou_valor_guardado if macro else False
            macro_data_busca = macro.data_busca if macro else None
            ano_fcd_mais_recente, erro_ano_fcd = _buscar_ano_fcd_mais_recente()
            # Pro card "Correlação com fatores externos" mais abaixo — custo
            # parecido com o resto (mais duas séries de 2 anos e uma leitura
            # de arquivo do GPR), por isso já busca aqui junto, sem exigir
            # clique extra.
            historico_acao_correlacao, erro_acao_correlacao = _buscar_historico(
                ticker, periodo=f"{ANOS_JANELA_CORRELACAO}y"
            )
            historico_petroleo, erro_petroleo = _buscar_historico_petroleo()
            serie_cambio, erro_cambio = _buscar_cambio_correlacao()
            serie_gpr, erro_gpr = _buscar_gpr_diaria()

            # Erros de FCF não são exibidos à parte — já aparecem no motivo de
            # "não aplicável" do próprio card do FCD. `erro_ano_fcd` (detecção
            # do ano em si falhando, ex: CVM fora do ar) tem o mesmo destino:
            # sem `ano_fcd_mais_recente`, fcf_atual segue None e o card cai no
            # "não aplicável" do jeito de sempre, sem aviso à parte.
            fluxos_fcd = montar_fluxos_fcd(None)
            ano_fcd_utilizado = None
            fcd_usou_fallback = False
            caixa_fcd_utilizado = capex_fcd_utilizado = risco_sacado_fcd_utilizado = None
            if cnpj and ano_fcd_mais_recente is not None:
                (
                    fluxos_fcd,
                    ano_fcd_utilizado,
                    fcd_usou_fallback,
                    caixa_fcd_utilizado,
                    capex_fcd_utilizado,
                    risco_sacado_fcd_utilizado,
                    _,
                ) = _buscar_fcf_fcd(cnpj, ano_fcd_mais_recente)
            leitura_balanco = _buscar_leitura_balanco(cnpj, indicadores) if cnpj else None

        st.subheader(ticker)

        # st.error (preço) vs. st.warning (indicadores/dividendos/CNPJ/
        # macro abaixo) não é inconsistência: investigado e confirmado que
        # a distinção é funcional, não sobre "o resto da página trava"
        # (não trava — Graham/Bazin/FCD continuam computáveis sem preço,
        # só o delta de upside some; Saúde financeira só perde Valor de
        # Mercado/Firma, o resto continua). É sobre o dado em si: "Preço
        # atual" é o único número desta seção sem NENHUM fallback visual
        # quando falta — some por completo, só o erro fica no lugar. Já
        # indicadores/dividendos/CNPJ/macro alimentam seções que já têm
        # "N/D"/"indisponível" dedicado (ver `_fmt`, "Saúde financeira",
        # cartões de método) — a ausência delas já aparece refletida com
        # um fallback claro mais abaixo, não como um vazio nu.
        if erro_preco_atual:
            st.error(f"Preço: {erro_preco_atual}")
            preco_atual = None
        else:
            assert historico_preco_atual is not None, "sem erro de preço, o histórico existe"
            preco_atual = float(historico_preco_atual["Close"].iloc[-1])
            if preco_valido(preco_atual):
                st.metric("Preço atual", _fmt_bilhoes(preco_atual))
            else:
                st.warning(AVISO_PRECO_INDISPONIVEL)
                preco_atual = None

        if erro_indicadores:
            st.warning(f"Fundamentus: {erro_indicadores}")
        if erro_dividendos:
            st.warning(f"Dividendos: {erro_dividendos}")
        if erro_cnpj:
            st.warning(f"CNPJ (CVM): {erro_cnpj}")
        if erro_macro:
            st.warning(erro_macro)
        elif (
            macro is not None
            and macro_usou_valor_guardado
            and macro.fonte_selic.startswith(PREFIXO_FONTE_ARQUIVO_REFERENCIA)
        ):
            st.warning(AVISO_MACRO_ARQUIVO_REFERENCIA.format(data=_fmt_data(macro_data_busca)))
        elif macro_usou_valor_guardado:
            st.warning(
                "Banco Central indisponível agora. Usando a Selic e o IPCA "
                f"obtidos em {_fmt_data(macro_data_busca)}."
            )
        elif macro and (aviso_fonte_macro := _aviso_fonte_macro(macro)):
            st.info(aviso_fonte_macro)
        if erro_ano_fcd:
            st.warning(erro_ano_fcd)
        # Número de ações do Fundamentus que não bate com a CVM (oferta, bonificação ou
        # cancelamento depois da data-base) ou número da CVM descartado por divergir demais.
        if leitura_balanco and leitura_balanco.get("aviso_divergencia_acoes"):
            st.warning(leitura_balanco["aviso_divergencia_acoes"])
        elif leitura_balanco and leitura_balanco.get("detalhe_acoes", {}).get(
            "descartada_por_divergencia"
        ):
            st.warning(leitura_balanco["motivo_acoes"])

        lpa = indicadores["lpa"] if indicadores else None
        vpa = indicadores["vpa"] if indicadores else None
        numero_acoes = indicadores["numero_acoes"] if indicadores else None
        divida_liquida_sobre_patrimonio = (
            indicadores["divida_liquida_sobre_patrimonio"] if indicadores else None
        )
        # Dívida líquida em valor ABSOLUTO (campo próprio do Fundamentus,
        # ausente pra bancos — ver CAMPOS_FUNDAMENTUS_OPCIONAIS), não a
        # mesma coisa que divida_liquida_sobre_patrimonio acima (a
        # proporção). Usada pro Valor de Firma mais abaixo e pra converter
        # o FCD de Enterprise Value pra Equity Value (ver modelos/fcd.py).
        divida_liquida = indicadores["divida_liquida"] if indicadores else None

        # Beta real (janela de 1 ano, calculada uma vez e reaproveitada no WACC
        # do FCD e no card de "Comportamento da ação" abaixo). None quando não
        # calculável — calcular_wacc cai pro BETA_PADRAO sozinho nesse caso,
        # não é tratado aqui.
        beta = None
        if not erro_historico_beta and not erro_historico_ibovespa_beta:
            beta = calcular_beta(historico_beta, historico_ibovespa_beta)

        # Graham é chamado direto (calcular_valor_justo_graham aceita
        # lpa/vpa como `float | None` e já trata ausência internamente).
        # Bazin e FCD, abaixo, precisam desse pré-check aqui em main.py
        # porque as duas funções EXIGEM tipo não-None nesses parâmetros
        # específicos — calcular_preco_teto_bazin quer um `pd.DataFrame`
        # de verdade (não `None`, mesmo vazio serve) pra `dividendos`, e
        # calcular_valor_justo_fcd declara `selic_meta`/`ipca_12m` como
        # `float`, não `float | None` — chamar qualquer uma direto com
        # `None` nesses parâmetros quebraria com AttributeError/TypeError
        # antes mesmo de chegar nos guards que elas já têm pra OUTROS
        # parâmetros (ex: fcf_atual/numero_acoes no FCD, que já são
        # `float | None` e tratados lá dentro). Não é duplicação evitável
        # — é a mesma forma de guard que os dois modelos já fazem
        # internamente pros parâmetros que aceitam None, só que aqui pros
        # que não aceitam.
        ajustes_balanco = montar_ajustes_balanco(leitura_balanco)
        resultado_graham = calcular_valor_justo_graham(
            *reescalar_lpa_vpa(lpa, vpa, numero_acoes, ajustes_balanco["acoes_em_circulacao"])
        )
        resultado_bazin: dict = (
            calcular_preco_teto_bazin(dividendos)
            if dividendos is not None
            else {
                "aplicavel": False,
                "preco_teto": None,
                "motivo_nao_aplicavel": erro_dividendos or "Histórico de dividendos indisponível.",
            }
        )
        if selic_meta is not None and ipca_12m is not None:
            resultado_fcd = calcular_valor_justo_fcd(
                **fluxos_fcd,
                **ajustes_balanco,
                numero_acoes=numero_acoes,
                selic_meta=selic_meta,
                ipca_12m=ipca_12m,
                divida_liquida_sobre_patrimonio=divida_liquida_sobre_patrimonio,
                beta=beta,
                divida_liquida=divida_liquida,
                segmento_setorial=segmento_setorial,
                ticker=ticker,
            )
        else:
            resultado_fcd = {
                "aplicavel": False,
                "valor_justo": None,
                "motivo_nao_aplicavel": MENSAGEM_MACRO_INDISPONIVEL_CURTA,
            }

        st.divider()
        st.subheader("Valor Justo")
        resultado_combinado = calcular_valor_combinado(
            resultado_graham, resultado_bazin, resultado_fcd
        )
        coluna_graham, coluna_bazin, coluna_fcd, coluna_combinado = st.columns(4)
        with coluna_graham:
            _cartao_metodo("Graham", resultado_graham, "valor_justo", preco_atual)
        with coluna_bazin:
            _cartao_metodo("Bazin (preço teto)", resultado_bazin, "preco_teto", preco_atual)
            razao_dividendos_bazin = resultado_bazin.get("razao_dividendos_12m_vs_mediana_5a")
            if (
                razao_dividendos_bazin is not None
                and razao_dividendos_bazin > RAZAO_DIVIDENDOS_ATIPICA_BAZIN
            ):
                st.caption(
                    "Dividendos dos últimos 12 meses em "
                    f"{razao_dividendos_bazin * 100:.0f}% da mediana dos 5 anos "
                    "anteriores. Pode ser crescimento real dos pagamentos ou um "
                    "pagamento extraordinário — a fonte não permite distinguir. "
                    "Se for extraordinário, o preço teto está inflado."
                )
        with coluna_fcd:
            _cartao_metodo("FCD", resultado_fcd, "valor_justo", preco_atual)
            if resultado_fcd["aplicavel"]:
                origem_beta = "calculado, 1a" if beta is not None else "padrão, sem histórico"
                st.caption(f"Beta no WACC: {_fmt(resultado_fcd['beta_utilizado'])} ({origem_beta})")
                # Rótulo específico do FCD (não da página toda) — só o FCD vem
                # da DFP anual da CVM; "Saúde financeira" abaixo vem do
                # Fundamentus (últimos 12 meses), sem relação com esse ano.
                # Caso normal (sem fallback) não tem legenda própria aqui —
                # o ano já aparece no bloco "Datas de referência dos dados
                # usados" (pra reduzir texto repetido); a
                # variante de fallback fica, porque diz algo específico
                # dessa ação que não está em lugar nenhum.
                if fcd_usou_fallback:
                    st.caption(
                        f"FCD calculado com a demonstração financeira anual de "
                        f"{ano_fcd_utilizado} (CVM) — a de {ano_fcd_mais_recente} "
                        "ainda não foi entregue por essa empresa."
                    )
                if risco_sacado_fcd_utilizado:
                    st.caption(
                        TEXTO_RISCO_SACADO_RECLASSIFICADO.format(
                            ano=ano_fcd_utilizado,
                            valor=_fmt_bilhoes_md(abs(risco_sacado_fcd_utilizado)),
                        )
                    )
                if caixa_fcd_utilizado is not None and capex_fcd_utilizado is not None:
                    proporcao_reinvestimento = (
                        calcular_proporcao_capex_caixa_operacional_percentual(
                            caixa_fcd_utilizado, capex_fcd_utilizado
                        )
                    )
                    # Sem capex identificado, sem legenda (o FCD nem é calculado).
                    if proporcao_reinvestimento is not None:
                        st.caption(
                            LEGENDA_REINVESTIMENTO_CAPEX.format(
                                ano=ano_fcd_utilizado, proporcao=proporcao_reinvestimento
                            )
                        )
        with coluna_combinado:
            if resultado_combinado["aplicavel"]:
                st.metric(
                    "Valor combinado",
                    _fmt_bilhoes(resultado_combinado["valor_combinado"]),
                    delta=_delta_percentual_upside(
                        resultado_combinado["valor_combinado"], preco_atual
                    ),
                    help=TOOLTIP_POTENCIAL_CARTAO,
                )
                st.caption(
                    "Métodos utilizados: " + ", ".join(resultado_combinado["metodos_utilizados"])
                )
                divergencia = calcular_divergencia_metodos(
                    resultado_combinado["valores_por_metodo"], preco_atual
                )
                if divergencia["aplicavel"]:
                    if divergencia["divergencia_percentual"] is not None:
                        st.caption(
                            "Os métodos aplicáveis vão de "
                            f"{_fmt_bilhoes_md(divergencia['menor'])} a "
                            f"{_fmt_bilhoes_md(divergencia['maior'])}: uma diferença "
                            f"equivalente a {divergencia['divergencia_percentual']:.0f}% do "
                            "preço atual. Quanto maior essa diferença, menos os métodos "
                            "concordam entre si."
                        )
                    else:
                        st.caption(
                            "Os métodos aplicáveis vão de "
                            f"{_fmt_bilhoes_md(divergencia['menor'])} a "
                            f"{_fmt_bilhoes_md(divergencia['maior'])} "
                            f"({_fmt_bilhoes_md(divergencia['diferenca'])} de diferença)."
                        )
            else:
                st.info(
                    f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']} "
                    f"{TEXTO_COMPLEMENTO_SEM_METODO}"
                )

        st.caption(
            "Os valores acima são calculados a partir de fórmulas de valuation "
            "públicas e conhecidas (Graham, Bazin, FCD) aplicadas aos dados "
            "reais da empresa — isto não é uma recomendação de compra ou "
            "venda, apenas uma referência de estudo."
        )

        with st.expander("Datas de referência dos dados usados"):
            # Preço/Beta vêm da coluna "data" que obter_historico já traz
            # (ver ingest.precos) — só não era extraída até aqui. Balanço
            # vem de indicadores (Fundamentus, "Últ balanço processado",
            # ver ingest.fundamentus). FCD reaproveita ano_fcd_utilizado,
            # já calculado acima pro cartão do FCD. IPCA reaproveita
            # data_ipca de _buscar_macro. Selic normalmente não tem uma
            # data própria pra mostrar — é recalculada com a data de hoje
            # a cada busca — exceto
            # quando o Banco Central está fora do ar e o valor guardado
            # entra em uso: aí a data que importa é a da última busca com
            # sucesso, não a de hoje. Dividendos do Bazin continuam
            # sempre com a data de hoje.
            texto_selic_referencia = (
                f"último valor obtido em {_fmt_data(macro_data_busca)} "
                "(Banco Central indisponível agora)"
                if macro_usou_valor_guardado
                else "calculada com a data de hoje"
            )
            data_preco_referencia = None
            if not erro_preco_atual:
                assert historico_preco_atual is not None, "sem erro de preço, o histórico existe"
                data_preco_referencia = historico_preco_atual["data"].iloc[-1]
            data_beta_referencia = None
            if not erro_historico_beta:
                assert historico_beta is not None, "sem erro de Beta, o histórico existe"
                data_beta_referencia = historico_beta["data"].iloc[-1]
            data_balanco_referencia = (
                indicadores["data_balanco_fundamentus"] if indicadores else None
            )
            texto_fcd_referencia = (
                f"demonstração financeira anual de {ano_fcd_utilizado} (CVM)"
                if resultado_fcd["aplicavel"]
                else "não aplicável"
            )
            st.markdown(
                "Comparar o preço de hoje com o último balanço disponível é o "
                "padrão de mercado — cada dado abaixo tem uma data-base "
                "diferente por natureza (o balanço de uma empresa sempre sai "
                "com atraso), não por inconsistência:\n\n"
                f"- **Preço** — último fechamento: {_fmt_data(data_preco_referencia)}.\n"
                "- **Indicadores fundamentalistas** (Fundamentus) — balanço de "
                f"{_fmt_data(data_balanco_referencia)}: lucro, receita e margens "
                "somam os 12 meses até essa data; patrimônio, dívida e número "
                "de ações são a posição nessa data.\n"
                f"- **FCD** — {texto_fcd_referencia}.\n"
                f"- **Beta** — 1 ano de pregões até {_fmt_data(data_beta_referencia)}.\n"
                f"- **IPCA (12 meses)** — acumulado até {_fmt_data(data_ipca, '%m/%Y')}.\n"
                f"- **Selic** — {texto_selic_referencia}.\n"
                "- **Dividendos do método Bazin** (últimos 12 meses) — sempre "
                "calculados com a data de hoje."
            )

        with st.expander("Como funciona esse cálculo?"):
            st.markdown(
                "**Graham** — fórmula de Benjamin Graham (mentor de Warren Buffett): "
                "valor justo = raiz quadrada de (22,5 × LPA × VPA). Só se aplica a "
                "empresas com lucro e patrimônio líquido positivos.\n\n"
                "**Bazin (preço teto)** — método do investidor Décio Bazin, focado em "
                "dividendos: calcula o preço máximo que garantiria um retorno de "
                f"{YIELD_MINIMO_BAZIN:.0%} ao ano só em dividendos, baseado no histórico "
                "de pagamento da empresa. Só se aplica a quem tem histórico consistente "
                "de dividendo. A fonte dos dividendos (Yahoo Finance) não distingue "
                "pagamentos ordinários de extraordinários: um provento pontual grande "
                "(como um dividendo especial) entra na mesma soma dos últimos 12 meses "
                "e pode inflar o preço teto.\n\n"
                "**FCD (Fluxo de Caixa Descontado)** — projeta os fluxos de caixa "
                "futuros da empresa e traz isso a valor presente, descontando pelo "
                "custo de capital (WACC). O custo do capital próprio parte da Selic "
                "menos o spread de default do Brasil (que a Selic já embute) mais o "
                "Beta da ação vezes o prêmio de risco do país; o custo da dívida é a "
                "Selic mais 2 pontos percentuais. Esse valor presente é o da empresa como um "
                "todo, dívida incluída — por isso a dívida líquida é deduzida antes "
                "de dividir pelo número de ações, chegando no valor que sobra pros "
                "acionistas; quando a dívida líquida não está disponível pra uma "
                "empresa, o cálculo usa o valor da empresa inteira como aproximação, "
                "sem deduzir nada, e mostra um aviso na tela. Não se aplica a bancos "
                "— a dívida e os depósitos são a própria operação do banco, não "
                "financiamento externo — nem a seguradoras e à Itaúsa, cujo caixa "
                "vem de prêmios e de dividendos de participações; nesses casos a "
                "lógica de custo de capital do FCD não tem interpretação econômica "
                "válida (Graham e Bazin continuam funcionando normalmente). Também "
                "não é calculado quando o caixa livre do último ano foi zero ou "
                "negativo: projetar um fluxo assim não estima valor. Fora esses "
                "casos, funciona mesmo para empresas sem lucro contábil no "
                "momento, já que olha geração de caixa, não resultado contábil "
                "passado. O fluxo de caixa usado é o caixa gerado pela operação "
                "menos o que a empresa gastou em imobilizado e intangível "
                "(máquinas, obras, sistemas) no ano, mais os juros pagos sobre a "
                "dívida, já descontado o imposto: os juros voltam ao fluxo porque "
                "o custo da dívida já entra no custo de capital e na dedução da "
                "dívida líquida. Quando a empresa paga os fornecedores por um convênio "
                "com banco (risco sacado ou similar) e registra o pagamento ao banco no "
                "caixa de financiamento, esse valor é tratado como operacional, porque "
                "substitui o pagamento ao fornecedor; sem isso o caixa operacional "
                "pareceria maior do que a geração de caixa, e o cartão avisa quando o "
                "ajuste é aplicado. Ficam de fora as aplicações financeiras, a compra "
                "e venda de participações e de ativos e o pagamento de "
                "arrendamentos (aluguéis de longo prazo). Se o gasto em "
                "imobilizado e intangível não puder ser identificado na "
                "demonstração da empresa, o FCD não é calculado, e o mesmo vale "
                "quando o fluxo do último ano é zero ou negativo. O crescimento do "
                "fluxo nos cinco anos projetados é medido entre o ano mais recente e "
                "cinco anos antes, limitado ao crescimento da receita líquida no "
                "mesmo período (um fluxo não cresce mais que a receita por cinco "
                "anos, o que assume margem constante) e à faixa de −20% a +30% ao "
                "ano; sem receita utilizável, vale o crescimento do fluxo, e o cartão "
                "diz o motivo. Esse crescimento converge gradualmente, ano a ano, "
                "para o de longo prazo (a inflação, IPCA) em vez de saltar no sexto "
                "ano. Quando o fluxo de cinco anos atrás não pode ser usado, o "
                "crescimento passa a ser a inflação (IPCA) e o cartão avisa. Por "
                "isso, empresas em fase de "
                "investimento pesado (comuns em energia e saneamento) ou com "
                "dívida muito alta tendem a ter FCD bem abaixo dos outros "
                "métodos, mesmo quando são saudáveis. Separar o investimento que "
                "só mantém a empresa do que a faz crescer exigiria um dado que a "
                "fonte não informa de forma padronizada. No cartão do FCD, a "
                "porcentagem reinvestida no ano aparece logo abaixo do valor. "
                f"{TEXTO_FCD_AJUSTES_DO_BALANCO}\n\n"
                "**Valor combinado** — média simples só dos métodos que se aplicam à "
                "empresa (se só um se aplica, o combinado é ele mesmo). É uma "
                "heurística: os pesos são iguais por simplicidade, não porque exista "
                "evidência de que os três acertam igualmente — definir pesos melhores "
                "exigiria testar os métodos contra o histórico de preços, o que este "
                "projeto ainda não faz. Os três também medem coisas diferentes: Graham "
                "e FCD estimam quanto a ação vale (um pelo lucro e patrimônio, outro "
                "pelo fluxo de caixa futuro), enquanto o Bazin é um preço teto de "
                f"compra — o máximo a pagar para receber {YIELD_MINIMO_BAZIN:.0%} ao "
                "ano em dividendos, não uma estimativa de valor. Por isso, leia o "
                "combinado junto com os valores individuais, não sozinho.\n\n"
                "**Limitações conhecidas de cada método**: Graham usa o valor "
                "patrimonial (VPA) na fórmula, então tende a ficar menos "
                "representativo para empresas com poucos ativos físicos mas alto "
                "valor de marca ou tecnologia — e não é calculável se VPA for "
                "negativo. Bazin depende de histórico consistente de dividendo, "
                "então fica indisponível para empresas de crescimento que "
                "reinvestem o lucro em vez de distribuir. FCD é o mais sensível a "
                "premissas (taxa de desconto e crescimento futuro) — pequenas "
                "mudanças nessas variáveis podem alterar bastante o resultado, "
                "especialmente quando a taxa de crescimento é estimada a partir de "
                "poucos anos de histórico."
            )

        st.divider()
        coluna_saude, coluna_governanca = st.columns(2)
        with coluna_saude:
            st.subheader("Saúde financeira")
            if indicadores is None:
                st.info("Indisponível — ver aviso do Fundamentus acima.")
            else:
                # 2 colunas por linha (não 3 ou 4) — testado manualmente em
                # 1024/1366/1920px: valores abreviados como "R$ 618,7 bi"
                # precisam de ~188px, e só a largura de coluna de uma grade
                # 2x cabe isso sem cortar nas larguras de notebook comuns.
                col_a, col_b = st.columns(2)
                col_a.metric("ROE", _fmt(indicadores["roe_percentual"], "{:.1f}%"))
                col_b.metric(
                    "Margem líquida", _fmt(indicadores["margem_liquida_percentual"], "{:.1f}%")
                )
                col_c, col_d = st.columns(2)
                col_c.metric("LPA", _fmt(indicadores["lpa"], "R$ {:.2f}"))
                col_d.metric("VPA", _fmt(indicadores["vpa"], "R$ {:.2f}"))
                col_e, col_f = st.columns(2)
                col_e.metric("Liquidez corrente", _fmt(indicadores["liquidez_corrente"]))
                col_f.metric(
                    "Dív. líq./patrim.", _fmt(indicadores["divida_liquida_sobre_patrimonio"])
                )
                acoes_em_circulacao = ajustes_balanco["acoes_em_circulacao"]
                valores_mercado_firma = calcular_valor_mercado_e_firma(
                    preco_atual,
                    acoes_em_circulacao if acoes_em_circulacao is not None else numero_acoes,
                    divida_liquida,
                    ajustes_balanco["nao_controladores"],
                    ajustes_balanco["arrendamento_fora_da_divida"],
                )
                col_g, col_h = st.columns(2)
                col_g.metric(
                    "Cresc. receita (5a)",
                    _fmt(indicadores["crescimento_receita_5a_percentual"], "{:.1f}%"),
                )
                col_h.metric(
                    "Valor de mercado", _fmt_bilhoes(valores_mercado_firma["valor_mercado"])
                )
                col_i, col_j = st.columns(2)
                col_i.metric(
                    "Dívida líquida", _fmt_bilhoes(valores_mercado_firma["divida_liquida"])
                )
                col_j.metric(
                    "Valor de firma",
                    _fmt_bilhoes(valores_mercado_firma["valor_firma"]),
                    help=TOOLTIP_VALOR_FIRMA,
                )
                if valores_mercado_firma["componentes_ausentes"]:
                    st.caption(
                        TEXTO_FIRMA_SEM_COMPONENTES.format(
                            componentes=", ".join(
                                ROTULOS_COMPONENTES_VALOR_FIRMA[nome]
                                for nome in valores_mercado_firma["componentes_ausentes"]
                            )
                        )
                    )
                if leitura_balanco and ajustes_balanco["motivo_sem_acoes_em_circulacao"]:
                    st.caption(
                        TEXTO_SEM_ACOES_EM_CIRCULACAO.format(
                            motivo=ajustes_balanco["motivo_sem_acoes_em_circulacao"]
                        )
                    )
                st.caption(
                    'Indicadores individuais ausentes ("N/D") — comum em bancos, onde o '
                    "Fundamentus não reporta alguns desses índices no mesmo formato."
                )

        with coluna_governanca:
            st.subheader("Governança")
            linha_universo = (
                universo_ibovespa[universo_ibovespa["ticker"] == ticker]
                if universo_ibovespa is not None
                else None
            )
            col_segmento, col_free_float = st.columns(2)
            with col_segmento:
                if erro_universo:
                    st.warning(f"Segmento de listagem: {erro_universo}")
                elif linha_universo is not None and not linha_universo.empty:
                    st.metric("Segmento de listagem", linha_universo.iloc[0]["segmento_listagem"])
                else:
                    st.metric("Segmento de listagem", "—")
                    st.caption(
                        f"{ticker!r} não está na carteira teórica atual do Ibovespa — essa é "
                        "a única fonte de segmento de listagem que já temos."
                    )
            with col_free_float:
                st.metric("Free float", "Pendente")
                st.caption(
                    "Nenhum adapter atual extrai free float — nem o universo do Ibovespa "
                    "(b3_universo.py) nem o catálogo de emissores (crosswalk_cnpj.py) "
                    "trazem esse campo. Fica como pendência explícita, não um valor "
                    "inventado."
                )

        st.divider()
        coluna_comportamento, coluna_grafico_preco = st.columns([1, 2])
        with coluna_comportamento:
            st.subheader("Comportamento da ação")
            if erro_historico:
                st.info("Volume/volatilidade indisponíveis — ver aviso de preço acima.")
            else:
                volume_medio = calcular_volume_medio(historico)
                volatilidade = calcular_volatilidade_anualizada(historico)
                # calcular_volume_medio pode devolver None (histórico
                # vazio) — _fmt já trata isso como "N/D" no resto do
                # arquivo; sem essa checagem, f"{None:,.0f}" levantaria
                # TypeError. _fmt já converte pro padrão brasileiro
                # (milhar com ponto), sem replace() extra aqui.
                st.metric("Volume médio (3m)", _fmt(volume_medio, "{:,.0f}"))
                st.metric("Volatilidade anualizada", _fmt(volatilidade, "{:.1%}"))

            # Beta usa uma janela própria mais longa (PERIODO_BETA) que
            # volume/volatilidade, de propósito — ver comentário em config.py.
            # Reaproveita o `beta` já calculado acima (mesmo valor usado no
            # WACC do FCD), não recalcula.
            if erro_historico_beta:
                st.metric("Beta (vs. Ibovespa, 1a)", "—")
                st.caption(f"Preço indisponível: {erro_historico_beta}")
            elif erro_historico_ibovespa_beta:
                st.metric("Beta (vs. Ibovespa, 1a)", "—")
                st.caption(f"Ibovespa indisponível: {erro_historico_ibovespa_beta}")
            else:
                st.metric("Beta (vs. Ibovespa, 1a)", _fmt(beta))
                if beta is None:
                    st.caption("Histórico curto demais pra calcular (poucas datas em comum).")

        with coluna_grafico_preco:
            st.subheader("Preço vs. Ibovespa (1 ano, base 100)")
            if erro_historico_beta or erro_historico_ibovespa_beta:
                st.info(
                    "Gráfico indisponível — histórico de preço ou do Ibovespa não pôde ser "
                    "buscado (ver avisos acima)."
                )
            else:
                # Reaproveita historico_beta/historico_ibovespa_beta (PERIODO_BETA,
                # 1 ano) já buscados pro cálculo de Beta acima — não busca dado
                # novo. Normalizado pra base 100 (ver graficos.py): plotar preço
                # bruto da ação ao lado dos ~130 mil pontos do Ibovespa deixaria a
                # ação uma linha reta ilegível.
                figura_preco, nomes_sem_dados_preco = _grafico_comparacao_normalizada(
                    historico_beta, ticker, historico_ibovespa_beta, "Ibovespa"
                )
                if figura_preco is None:
                    st.info(_mensagem_grafico_comparacao_sem_dados(nomes_sem_dados_preco))
                else:
                    st.plotly_chart(figura_preco, use_container_width=True)

        st.divider()
        st.subheader("Comparando com Petróleo (Brent)")
        janela_petroleo_selecionada = st.pills(
            "Janela de comparação",
            options=list(JANELAS_COMPARACAO_PETROLEO.keys()),
            default="2 anos",
            key="janela_comparacao_petroleo",
        )
        if not janela_petroleo_selecionada:
            st.info("Selecione uma janela acima pra ver o gráfico.")
        else:
            periodo_petroleo = JANELAS_COMPARACAO_PETROLEO[janela_petroleo_selecionada]
            with st.spinner(
                f"Buscando histórico de {ticker} e do petróleo (Brent) em "
                f"{janela_petroleo_selecionada}..."
            ):
                historico_acao_petroleo, erro_acao_petroleo = _buscar_historico(
                    ticker, periodo=periodo_petroleo
                )
                historico_petroleo_janela, erro_petroleo_janela = _buscar_historico_petroleo(
                    periodo=periodo_petroleo
                )

            if erro_acao_petroleo:
                st.error(f"Preço de {ticker}: {erro_acao_petroleo}")
            elif erro_petroleo_janela:
                st.error(f"Petróleo (Brent): {erro_petroleo_janela}")
            else:
                figura_petroleo, nomes_sem_dados_petroleo = _grafico_comparacao_normalizada(
                    historico_acao_petroleo, ticker, historico_petroleo_janela, "Petróleo (Brent)"
                )
                if figura_petroleo is None:
                    st.info(_mensagem_grafico_comparacao_sem_dados(nomes_sem_dados_petroleo))
                else:
                    st.plotly_chart(figura_petroleo, use_container_width=True)

        st.divider()
        st.subheader("Gráfico avançado (TradingView)")
        st.caption(
            "Widget ao vivo do TradingView — dado direto deles, sem nenhum "
            "processamento nosso (diferente do gráfico acima, calculado por "
            "aqui a partir do histórico buscado via yfinance). Em ambientes "
            "com JavaScript bloqueado/restrito, o gráfico ao vivo pode não "
            "carregar."
        )
        components.html(_widget_avancado_tradingview(ticker), height=520)

        st.divider()
        coluna_dividendos, coluna_comparacao_setorial = st.columns(2)
        with coluna_dividendos:
            st.subheader("Histórico de dividendos por ano")
            if erro_dividendos:
                st.info("Gráfico indisponível — ver aviso de dividendos acima.")
            else:
                # Reaproveita `dividendos` já buscado pro método de Bazin acima —
                # não busca dado novo.
                dividendos_por_ano = agregar_dividendos_por_ano(dividendos)
                if dividendos_por_ano.empty:
                    st.info("Nenhum dividendo pago no histórico disponível.")
                else:
                    # period="max" (não reaproveita o histórico de 1 ano já
                    # buscado pro Beta/gráfico de preço acima) porque o Dividend
                    # Yield por ano precisa do preço médio de TODOS os anos com
                    # dividendo pago, que podem ir bem além de 1 ano atrás.
                    # auto_adjust=False: preço NOMINAL da época, não ajustado
                    # retroativamente por dividendos futuros — ver docstring de
                    # _buscar_historico/ingest.precos.obter_historico.
                    historico_max, erro_historico_max = _buscar_historico(
                        ticker, "max", auto_adjust=False
                    )
                    dividend_yield_por_ano = calcular_dividend_yield_por_ano(
                        dividendos_por_ano,
                        historico_max
                        if not erro_historico_max
                        else pd.DataFrame(columns=["data", "Close"]),
                    )

                    figura_dividendos = go.Figure()
                    # text/hovertemplate pré-formatados com _fmt_bilhoes/
                    # _fmt_percentual (não "%{text:.2f}"/"%{y:.1f}%" do
                    # Plotly) — o d3-format que o Plotly usa por trás desses
                    # especificadores também não tem vírgula decimal
                    # brasileira sem um locale registrado, mesmo problema do
                    # ponto vs. vírgula resolvido em _fmt_bilhoes/_fmt.
                    figura_dividendos.add_trace(
                        go.Bar(
                            x=dividendos_por_ano["ano"],
                            y=dividendos_por_ano["total"],
                            name="Dividendos",
                            text=dividendos_por_ano["total"].apply(_fmt_bilhoes),
                            texttemplate="%{text}",
                            textposition="outside",
                            hovertemplate="%{text}<extra></extra>",
                            marker={"color": COR_GRAFICO_PROTAGONISTA},
                        )
                    )
                    if not dividend_yield_por_ano.empty:
                        figura_dividendos.add_trace(
                            go.Scatter(
                                x=dividend_yield_por_ano["ano"],
                                y=dividend_yield_por_ano["yield_percentual"],
                                name="Dividend Yield",
                                mode="lines+markers+text",
                                text=dividend_yield_por_ano["yield_percentual"].apply(
                                    _fmt_percentual
                                ),
                                texttemplate="%{text}",
                                textposition="top center",
                                yaxis="y2",
                                hovertemplate="%{text}<extra></extra>",
                                line={"color": COR_GRAFICO_CONTEXTO},
                                marker_color=COR_GRAFICO_CONTEXTO,
                            )
                        )
                    figura_dividendos.update_layout(
                        yaxis_title="Total pago no ano (R$/ação)",
                        xaxis_title="Ano",
                        xaxis={"type": "category"},
                        yaxis2={
                            "title": "Dividend Yield (%)",
                            "overlaying": "y",
                            "side": "right",
                            "showgrid": False,
                        },
                        hovermode="x unified",
                        legend={
                            "orientation": "h",
                            "yanchor": "bottom",
                            "y": 1.02,
                            "xanchor": "left",
                            "x": 0,
                        },
                        margin={"t": 40},
                        paper_bgcolor=COR_GRAFICO_FUNDO,
                        plot_bgcolor=COR_GRAFICO_FUNDO,
                        font={"color": COR_GRAFICO_TEXTO},
                    )
                    figura_dividendos.update_xaxes(gridcolor=COR_GRAFICO_GRADE)
                    figura_dividendos.update_yaxes(gridcolor=COR_GRAFICO_GRADE)
                    st.plotly_chart(figura_dividendos, use_container_width=True)

                    # Degradação transparente: yield ausente ou parcial não é
                    # erro, mas merece uma linha explicando o motivo — mesmo
                    # padrão de aviso nomeado usado no resto do projeto.
                    if erro_historico_max:
                        st.caption(f"Dividend Yield indisponível: {erro_historico_max}")
                    elif dividend_yield_por_ano.empty:
                        st.caption(
                            "Dividend Yield indisponível — sem preço histórico "
                            "suficiente pros anos com dividendo pago."
                        )
                    else:
                        if len(dividend_yield_por_ano) < len(dividendos_por_ano):
                            st.caption(
                                "Dividend Yield mostrado só pros anos com preço "
                                "histórico disponível — ação listada há menos "
                                "tempo que o histórico de dividendos."
                            )
                        # Limitação conhecida da FONTE (yfinance), não do
                        # cálculo — mesmo padrão de transparência já usado pra
                        # outras limitações do yfinance no projeto (ver
                        # ingest/precos.py). Quando a empresa fragmenta o
                        # dividendo de uma mesma data em várias parcelas (comum
                        # na Petrobras, dividendo + JCP anunciados juntos), o
                        # yfinance às vezes só captura parte do valor total
                        # daquele dia — confirmado comparando PETR4 2022 contra
                        # uma fonte de mercado externa (dadosdemercado.com.br):
                        # yfinance perdeu ~R$1,61/ação de um único dia
                        # (22/11/2022) por esse motivo. Não é um remendo
                        # perseguível caso a caso, só uma limitação a avisar.
                        st.caption(
                            "Dividend Yield histórico pode ficar um pouco "
                            "subestimado em anos com dividendo pago em várias "
                            "parcelas no mesmo dia — limitação de completude de "
                            "dado do yfinance, não do cálculo."
                        )

        with coluna_comparacao_setorial:
            st.subheader("Comparação setorial")
            # segmento_setorial/erro_segmento_setorial já buscados mais
            # acima (perto do cnpj, pro FCD) — reaproveitado aqui, sem
            # busca nova.
            if erro_segmento_setorial:
                st.warning(f"Classificação setorial: {erro_segmento_setorial}")
            else:
                tabela_screener_setor = _carregar_screener_ou_avisar(
                    CAMINHO_SAIDA_PADRAO,
                    'Rode o screener primeiro na aba "Screener (todas as ações)"',
                )
                if tabela_screener_setor is not None:
                    try:
                        catalogo_setorial = obter_catalogo_emissores()
                    except Exception as erro:
                        st.warning(f"Catálogo de emissores da B3: {erro}")
                    else:
                        # Resolve o segmento setorial de cada ticker do screener já
                        # salvo (dado local, sem nova busca de rede além do catálogo
                        # já cacheado) pra achar os pares do mesmo setor da ação
                        # buscada. Os números da tabela (preço, valor combinado,
                        # potencial) vêm direto do screener — não são recalculados.
                        segmentos_screener = resolver_segmentos_setoriais(
                            list(tabela_screener_setor["ticker"]), catalogo_setorial
                        )
                        tickers_do_setor = segmentos_screener[
                            segmentos_screener["segmento_setorial"] == segmento_setorial
                        ]["ticker"]
                        tabela_pares = tabela_screener_setor[
                            tabela_screener_setor["ticker"].isin(tickers_do_setor)
                        ]
                        if tabela_pares.empty:
                            st.info(
                                f"Nenhuma outra ação do segmento setorial {segmento_setorial!r} "
                                "encontrada no resultado salvo do screener."
                            )
                        else:
                            st.caption(f"Segmento setorial (B3): {segmento_setorial}")
                            tabela_pares_fmt, colunas_pares_fmt = _tabela_formatada_pt_br(
                                tabela_pares,
                                colunas_moeda={
                                    "preco_atual": "Preço atual",
                                    "valor_combinado": "Valor combinado",
                                },
                                colunas_percentual={"desconto_percentual": ROTULO_POTENCIAL},
                                ajudas={"desconto_percentual": TOOLTIP_POTENCIAL_COLUNA},
                            )
                            st.dataframe(
                                tabela_pares_fmt,
                                column_order=[
                                    "ticker",
                                    "preco_atual",
                                    "valor_combinado",
                                    "desconto_percentual",
                                ],
                                column_config={"ticker": "Ticker", **colunas_pares_fmt},
                                hide_index=True,
                                use_container_width=True,
                            )

        st.divider()
        st.subheader("Correlação com fatores externos")
        st.caption(
            "Correlação (Pearson) entre o retorno diário da ação e três fatores "
            f"externos — petróleo (Brent), câmbio USD/BRL e risco geopolítico (GPR) — "
            f"numa janela de {ANOS_JANELA_CORRELACAO} anos. Sempre correlaciona a "
            "variação percentual dia a dia de cada série, nunca o nível bruto — "
            "correlacionar séries em tendência infla o número de forma espúria, "
            "sem relação real entre elas."
        )
        if erro_acao_correlacao:
            st.error(f"Preço de {ticker} (janela de correlação): {erro_acao_correlacao}")
        else:
            if erro_petroleo:
                st.warning(f"Petróleo (Brent): {erro_petroleo}")
            if erro_cambio:
                st.warning(f"Câmbio USD/BRL: {erro_cambio}")
            if erro_gpr:
                st.warning(f"GPR: {erro_gpr}")

            resultados_correlacao = calcular_correlacoes_fatores(
                historico_acao=historico_acao_correlacao,
                historico_petroleo=historico_petroleo,
                serie_cambio=serie_cambio,
                serie_gpr=serie_gpr,
            )

            col_petroleo, col_cambio, col_gpr = st.columns(3)
            with col_petroleo:
                _cartao_correlacao("Petróleo (Brent)", resultados_correlacao["petroleo"])
            with col_cambio:
                _cartao_correlacao("Câmbio USD/BRL", resultados_correlacao["cambio"])
            with col_gpr:
                _cartao_correlacao("Risco geopolítico (GPR)", resultados_correlacao["gpr"])
                if serie_gpr is not None and not serie_gpr.empty:
                    st.caption(f"Último dado do GPR: {_fmt_data(serie_gpr['data'].max())}.")

with aba_screener:
    st.caption(
        "Ranking pelo potencial de valorização até o valor combinado (média "
        "simples dos métodos aplicáveis a cada ação). Veja abaixo como ler "
        "cada coluna."
    )
    with st.expander("Como ler esta tabela"):
        st.markdown(
            "- **Potencial** — quanto o valor justo combinado está acima (+) "
            "ou abaixo (−) do preço atual (valor justo ÷ preço − 1). O valor "
            "combinado é a média simples de Graham, Bazin e FCD aplicáveis, "
            "com pesos iguais por simplicidade — veja 'Como funciona esse "
            "cálculo?' na aba Analisar uma ação. A tabela vem ordenada do "
            "maior para o menor potencial.\n"
            "- **Divergência** — mostra o quanto os métodos discordam entre "
            "si. Divergência vazia significa que só um método se aplica "
            "àquela ação.\n"
            "- **Dividendos vs. histórico** — mostra os dividendos dos "
            "últimos 12 meses em relação à mediana dos 5 anos anteriores; "
            "valores bem acima de 100% deixam o preço teto do Bazin menos "
            "confiável. Dividendos vs. histórico vazio significa que o Bazin "
            "não se aplica àquela ação (ou, raramente, que os anos "
            "anteriores não têm pagamento para comparar).\n"
            "- **Reinvestimento** — mostra quanto do caixa gerado pela "
            "operação foi para o investimento em imobilizado e intangível "
            "(o mesmo usado no cálculo do FCD) no ano, sobre o mesmo caixa "
            "operacional que o FCD usa (com os juros somados de volta e o ajuste de "
            "risco sacado); valores altos puxam o FCD para baixo. Vazio quando "
            "o FCD não se aplica, o investimento não foi identificado ou o "
            "caixa operacional foi negativo.\n"
            "- **Aviso** — aparece quando o potencial está fora da faixa "
            "considerada confiável (valor justo muito acima ou muito abaixo "
            "do preço); a causa provável varia de uma ação para outra, "
            "conforme o texto de cada aviso. Vazio significa potencial dentro "
            "da faixa normal."
        )

    if st.button("Rodar screener agora", on_click=_ativar_aba, args=(ABA_SCREENER,)):
        st.warning(
            "Isso faz ~228 requisições reais (preço, dividendos e Beta de cada "
            "uma das ~76 ações, com delay entre chamadas) — leva de 5 a 15 "
            "minutos. Não feche esta aba enquanto roda."
        )
        # Captura os avisos emitidos durante a rodada pra poder mostrar na
        # tela os de DeteccaoAnoCvmFalhouWarning especificamente (sem isso,
        # quem clica no botão só veria a coluna do FCD inteira vazia, sem
        # nenhuma explicação — o aviso de rodar_screener ia só pro log do
        # servidor, invisível na UI). `record=True` intercepta TODOS os
        # avisos da rodada (inclusive o de cache do zip da CVM desatualizado,
        # categoria diferente) — por isso, ao sair do bloco, cada um é
        # reemitido pro canal normal antes de filtrar só os de detecção do
        # ano, preservando o comportamento de log de todos os outros.
        resultado_rodada = rodada_rejeitada = None
        with warnings.catch_warnings(record=True) as avisos_capturados:
            warnings.simplefilter("always")
            with st.spinner("Rodando o screener — isso leva alguns minutos..."):
                try:
                    resultado_rodada = rodar_screener()
                except RodadaScreenerRejeitada as erro:
                    rodada_rejeitada = erro
        for aviso in avisos_capturados:
            warnings.warn_explicit(aviso.message, aviso.category, aviso.filename, aviso.lineno)
        # Mesmo tratamento pros avisos "globais" (afetam a rodada inteira,
        # não uma linha) que rodar_screener pode emitir: detecção do ano da
        # CVM, busca de Selic/IPCA do BCB e Fundamentus indisponível.
        avisos_globais = [
            str(aviso.message)
            for aviso in avisos_capturados
            if issubclass(
                aviso.category,
                (
                    DeteccaoAnoCvmFalhouWarning,
                    MacroIndisponivelWarning,
                    FundamentusIndisponivelWarning,
                ),
            )
        ]
        if avisos_globais:
            # st.rerun() logo abaixo descarta qualquer coisa renderizada
            # nesta mesma execução — guarda em session_state pra mostrar
            # DEPOIS do rerun, não aqui.
            st.session_state["avisos_screener_globais"] = avisos_globais
        if rodada_rejeitada is not None:
            # Sem rerun: a mensagem fica na tela, e a tabela abaixo continua com o
            # resultado anterior, que a rodada descartada não substituiu.
            st.error(
                TEXTO_RODADA_DESCARTADA.format(
                    motivo=rodada_rejeitada.motivo, caminho=rodada_rejeitada.caminho_rejeitado
                )
            )
        else:
            falhas_de_fonte = getattr(resultado_rodada, "attrs", {}).get("falhas_de_fonte", {})
            if falhas_de_fonte:
                acoes_com_falha = ", ".join(
                    f"{ticker} ({', '.join(fontes)})"
                    for ticker, fontes in sorted(falhas_de_fonte.items())
                )
                mensagem = TEXTO_SCREENER_CONCLUIDO_COM_FALHAS.format(acoes=acoes_com_falha)
            else:
                mensagem = TEXTO_SCREENER_CONCLUIDO
            st.session_state["mensagem_rodada_screener"] = mensagem
            st.rerun()

    mensagem_rodada = st.session_state.pop("mensagem_rodada_screener", None)
    if mensagem_rodada:
        st.success(mensagem_rodada)

    for aviso in st.session_state.pop("avisos_screener_globais", []):
        st.warning(aviso)

    tabela_screener = _carregar_screener_ou_avisar(
        CAMINHO_SAIDA_PADRAO,
        f'Clique em "Rodar screener agora" acima pra gerar {CAMINHO_SAIDA_PADRAO.name}',
    )

    if tabela_screener is not None:
        atualizado_em = datetime.fromtimestamp(CAMINHO_SAIDA_PADRAO.stat().st_mtime)
        st.caption(
            f"Última atualização: {atualizado_em.strftime('%d/%m/%Y %H:%M')} — "
            "dado salvo em disco, não ao vivo. Use o botão acima pra atualizar."
        )

        linhas_com_aviso = (tabela_screener["aviso_desconto_extremo"] != "").sum()
        if linhas_com_aviso:
            st.warning(
                f"{linhas_com_aviso} ação(ões) com potencial fora do comum (valor "
                "justo muito acima ou muito abaixo do preço) — veja a coluna "
                '"Aviso" na tabela: a causa provável varia de uma ação para outra.'
            )

        tabela_screener_fmt, colunas_screener_fmt = _tabela_formatada_pt_br(
            tabela_screener,
            colunas_moeda={"preco_atual": "Preço atual", "valor_combinado": "Valor combinado"},
            colunas_percentual={"desconto_percentual": ROTULO_POTENCIAL},
            ajudas={"desconto_percentual": TOOLTIP_POTENCIAL_COLUNA},
        )
        st.dataframe(
            tabela_screener_fmt,
            column_order=COLUNAS_TABELA_SCREENER,
            column_config={
                "ticker": "Ticker",
                **colunas_screener_fmt,
                # NUMÉRICA de propósito, não texto pré-formatado como as
                # demais colunas de `colunas_screener_fmt` acima — sem
                # casa decimal não existe o problema de vírgula brasileira
                # que forçou o resto da tabela a virar texto (ver
                # `_tabela_formatada_pt_br`), então clicar no cabeçalho
                # continua ordenando numericamente de verdade, que é o
                # motivo desta coluna existir (filtrar por concordância
                # entre os métodos).
                "divergencia_percentual_metodos": st.column_config.NumberColumn(
                    "Divergência", format="%d%%"
                ),
                # NUMÉRICA pelo mesmo motivo da Divergência acima — ordenar
                # pelo cabeçalho precisa continuar numérico de verdade.
                "bazin_razao_dividendos_percentual": st.column_config.NumberColumn(
                    "Dividendos vs. histórico", format="%d%%"
                ),
                # NUMÉRICA pelo mesmo motivo acima.
                "proporcao_reinvestimento_percentual": st.column_config.NumberColumn(
                    "Reinvestimento", format="%d%%"
                ),
                "metodos_utilizados": "Métodos utilizados",
                "aviso_desconto_extremo": "Aviso",
                "erro": "Observação",
            },
            hide_index=True,
            use_container_width=True,
        )

with aba_carteira:
    st.caption(TEXTO_ABERTURA_SIMULADOR)

    tabela_screener_carteira = _carregar_screener_ou_avisar(
        CAMINHO_SAIDA_PADRAO,
        'Rode o screener primeiro na aba "Screener (todas as ações)"',
    )

    if tabela_screener_carteira is not None:
        tickers_disponiveis = sorted(tabela_screener_carteira["ticker"])
        tickers_selecionados = st.multiselect(
            "Ações da carteira (restrito às ações com dado no screener salvo)",
            options=tickers_disponiveis,
        )

        investimentos: dict[str, float] = {}
        if tickers_selecionados:
            st.caption("Quanto investir em cada ação:")
            for ticker in tickers_selecionados:
                investimentos[ticker] = st.number_input(
                    f"{ticker} (R$)",
                    min_value=0.0,
                    value=1000.0,
                    step=100.0,
                    key=f"investimento_{ticker}",
                )

        if not tickers_selecionados:
            st.info("Selecione ao menos uma ação pra simular.")
        else:
            tabela_carteira = montar_tabela_carteira(tabela_screener_carteira, investimentos)

            # Ações sem nenhum método aplicável (ex: HAPV3/MRVE3 no screener
            # real) não entram na tabela de projeção — mostrar zero ali seria
            # um valor inventado. Em vez disso, cada uma ganha um aviso
            # explícito, nomeando a ação e o motivo, nunca ignorada em
            # silêncio.
            linhas_sem_cenario = tabela_carteira[~tabela_carteira["aplicavel"]]
            for _, linha_sem_cenario in linhas_sem_cenario.iterrows():
                st.warning(
                    f"{linha_sem_cenario['ticker']}: "
                    f"{_fmt_bilhoes(linha_sem_cenario['valor_investido'])} "
                    f"investidos, mas sem cenário — {linha_sem_cenario['motivo_nao_aplicavel']}"
                )

            # Cenário com valor de método ≤ 0 (ex: FCD negativo) é limitado a
            # perda total (R$0, -100%) em vez de projeção negativa — ver
            # carteira.simular_investimento_ticker. Avisa qual(is) cenário(s)
            # de cada ação foram limitados, pra não esconder que o número
            # exibido não é a conta "crua".
            for _, linha_com_cenario in tabela_carteira[tabela_carteira["aplicavel"]].iterrows():
                cenarios_limitados = linha_com_cenario["cenarios_limitados_perda_total"]
                if cenarios_limitados:
                    rotulos = ", ".join(c.capitalize() for c in cenarios_limitados)
                    st.caption(
                        f"{linha_com_cenario['ticker']}: cenário(s) {rotulos} limitado(s) a "
                        "perda total (R$ 0, -100%) — o método correspondente deu um valor "
                        "abaixo do preço atual o bastante pra resultar numa perda maior que "
                        "100%, o que não existe economicamente."
                    )

            tabela_carteira_aplicavel = tabela_carteira[tabela_carteira["aplicavel"]]
            if not tabela_carteira_aplicavel.empty:
                tc_fmt, colunas_tc_fmt = _tabela_formatada_pt_br(
                    tabela_carteira_aplicavel,
                    colunas_moeda={
                        "valor_investido": "Investido",
                        "preco_atual": "Preço atual",
                        "projecao_pessimista": ROTULOS_VALOR_AO_CONVERGIR["pessimista"],
                        "projecao_base": ROTULOS_VALOR_AO_CONVERGIR["base"],
                        "projecao_otimista": ROTULOS_VALOR_AO_CONVERGIR["otimista"],
                    },
                    colunas_percentual={
                        "retorno_pessimista_percentual": ROTULOS_POTENCIAL_CENARIO["pessimista"],
                        "retorno_base_percentual": ROTULOS_POTENCIAL_CENARIO["base"],
                        "retorno_otimista_percentual": ROTULOS_POTENCIAL_CENARIO["otimista"],
                    },
                    ajudas={
                        coluna: TOOLTIP_POTENCIAL_CENARIO
                        for coluna in (
                            "retorno_pessimista_percentual",
                            "retorno_base_percentual",
                            "retorno_otimista_percentual",
                        )
                    },
                )
                st.dataframe(
                    tc_fmt,
                    column_order=COLUNAS_TABELA_CARTEIRA,
                    column_config={"ticker": "Ticker", **colunas_tc_fmt},
                    hide_index=True,
                    use_container_width=True,
                )

            totais_carteira = calcular_totais_carteira(tabela_carteira)
            st.divider()
            st.subheader("Total da carteira")
            if tabela_carteira_aplicavel.empty:
                st.info(
                    "Nenhuma das ações selecionadas tem cenário disponível — sem "
                    "projeção pra somar (ver avisos acima)."
                )
            else:
                col_investido, col_pessimista, col_base, col_otimista = st.columns(4)
                col_investido.metric("Investido", _fmt_bilhoes(totais_carteira["soma_investida"]))
                col_pessimista.metric(
                    ROTULOS_TOTAL_AO_CONVERGIR["pessimista"],
                    _fmt_bilhoes(totais_carteira["total_pessimista"]),
                )
                col_base.metric(
                    ROTULOS_TOTAL_AO_CONVERGIR["base"], _fmt_bilhoes(totais_carteira["total_base"])
                )
                col_otimista.metric(
                    ROTULOS_TOTAL_AO_CONVERGIR["otimista"],
                    _fmt_bilhoes(totais_carteira["total_otimista"]),
                )
                if totais_carteira["quantidade_sem_cenario"]:
                    st.caption(
                        f"{totais_carteira['quantidade_sem_cenario']} ação(ões) sem cenário "
                        "não entram nos totais por cenário, mas o valor investido nelas está "
                        'incluído em "Investido".'
                    )

                st.divider()
                st.subheader(SUBTITULO_POTENCIAL_CARTEIRA)
                st.caption(AVISO_SIMULADOR_SEM_PREVISAO)

                soma_investida = totais_carteira["soma_investida"]
                soma_investida_com_cenario = totais_carteira["soma_investida_com_cenario"]
                # `_fmt_bilhoes_md` escapa o "$" (st.write renderiza markdown, e
                # "$...$" vira LaTeX). A base é soma_investida_com_cenario, não
                # soma_investida: os valores por cenário só somam os tickers com
                # cenário, então a frase compara o mesmo universo.
                st.write(
                    FRASE_RESUMO_SIMULADOR.format(
                        investido=_fmt_bilhoes_md(soma_investida_com_cenario),
                        pessimista=_fmt_bilhoes_md(totais_carteira["total_pessimista"]),
                        otimista=_fmt_bilhoes_md(totais_carteira["total_otimista"]),
                    )
                )
                if totais_carteira["quantidade_sem_cenario"]:
                    valor_fora_da_conta = soma_investida - soma_investida_com_cenario
                    st.caption(
                        f"De um total de {_fmt_bilhoes_md(soma_investida)} investidos, "
                        f"{_fmt_bilhoes_md(valor_fora_da_conta)} "
                        f"({totais_carteira['quantidade_sem_cenario']} ação(ões)) "
                        "ficaram de fora desse cálculo — ver avisos acima."
                    )

                with st.expander(TITULO_EXPANDER_SIMULADOR):
                    st.markdown(TEXTO_EXPANDER_SIMULADOR)

# Nota de rodapé, fora de qualquer aba (aparece nas três) — Streamlit
# Community Cloud "adormece" apps sem acesso recente. Diferente do que se
# poderia supor, não é uma tela em branco automática: a plataforma mostra
# sua própria página de "app dormindo", com um botão que o visitante
# precisa clicar pra acordar o container (confirmado contra a documentação
# oficial, 2026-09-21) — só depois disso começa a espera de carregamento.
# Sem esse aviso, o clique extra pareceria um link quebrado.
st.divider()
st.caption(
    'Hospedado no Streamlit Community Cloud — se o app estiver "dormindo", '
    "vai aparecer uma tela pedindo um clique pra acordar; depois disso, "
    "leva cerca de 1 minuto pra carregar."
)
