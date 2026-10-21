"""Dashboard (Streamlit) do Avaliador de Ações da B3 — valor justo das ações do
Ibovespa por Graham, Bazin e fluxo de caixa descontado, com o valor combinado
e o simulador de carteira em três cenários (pessimista/base/otimista). Só chama
os adapters/modelos que já existem e organiza o resultado na tela; nenhuma lógica
de cálculo é reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import json
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from string import Template

# O projeto não está instalado como pacote (sem pyproject [project]/pip
# install -e . ainda) — `streamlit run` não adiciona src/ ao sys.path
# sozinho como o pytest faz via pythonpath, então isso resolve na mão.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.errors import StreamlitSecretNotFoundError

from avaliador_b3.carteira import (
    calcular_totais_carteira,
    montar_tabela_carteira,
)
from avaliador_b3.config import (
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    ANOS_JANELA_CORRELACAO,
    ANOS_JANELA_DIVIDENDOS,
    AVISO_MACRO_ARQUIVO_REFERENCIA,
    AVISO_MACRO_IPCA_FONTE,
    AVISO_MACRO_MESMA_FONTE,
    AVISO_MACRO_SELIC_FONTE,
    AVISO_PRECO_INDISPONIVEL,
    AVISO_SIMULADOR_SEM_PREVISAO,
    CHAVE_BARRA_ANALISAR,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_BARRA_RODAPE,
    CHAVE_BARRA_SCREENER,
    CHAVE_DROPDOWN_TICKER,
    CHAVE_TEXTO_TICKER,
    CHAVE_TICKER_GUARDADO,
    CONFIG_PLOTLY,
    COR_ALERTA,
    COR_BORDA,
    COR_FUNDO_PAGINA,
    COR_FUNDO_PAINEL,
    COR_GRADE,
    COR_NEGATIVO,
    COR_NEUTRO,
    COR_POSITIVO,
    COR_PRINCIPAL,
    COR_TEXTO,
    COR_TEXTO_SECUNDARIO,
    CORRECOES_EXIBICAO_SEGMENTO_SETORIAL,
    FOLGA_ROTULO_BARRA,
    FRASE_FONTE_MACRO,
    FRASE_RESUMO_SIMULADOR,
    ICONE_PAGINA_ANALISAR,
    ICONE_PAGINA_CARTEIRA,
    ICONE_PAGINA_SCREENER,
    JANELAS_COMPARACAO_PETROLEO,
    LARGURA_CARACTERE_ROTULO_BARRA,
    LEGENDA_REINVESTIMENTO_CAPEX,
    LIMITE_BARRA_POTENCIAL,
    LIMITE_DIVERGENCIA_METODOS_ALTA,
    LIMITE_LIQUIDEZ_CORRENTE_BAIXA,
    LIMITE_SINAL_INDICADOR,
    MENSAGEM_TRADINGVIEW_TICKER_INVALIDO,
    NOMES_FATORES_CORRELACAO,
    NOMES_METODOS,
    NOTA_DIVIDEND_YIELD_SUBESTIMADO,
    NOTA_DIVIDENDOS_ANO_PARCIAL,
    OPACIDADE_BARRA_PARCIAL,
    PADRAO_TICKER_B3,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    PERIODO_PRECO_ATUAL,
    PREFIXO_FONTE_ARQUIVO_REFERENCIA,
    RAZAO_DIVIDENDOS_ATIPICA_BAZIN,
    ROTULO_ANO_PARCIAL,
    ROTULO_COMBINADO_GRAFICO,
    ROTULO_JANELA_DIVIDENDOS_COMPLETA,
    ROTULO_JANELA_DIVIDENDOS_CURTA,
    ROTULO_POTENCIAL,
    ROTULOS_COMPONENTES_VALOR_FIRMA,
    ROTULOS_METODOS_GRAFICO,
    ROTULOS_POTENCIAL_CENARIO,
    ROTULOS_TOTAL_AO_CONVERGIR,
    ROTULOS_VALOR_AO_CONVERGIR,
    SEQUENCIA_CORES_SERIES,
    SERIES_BCB_SGS,
    SUBTITULO_APP,
    SUBTITULO_POTENCIAL_CARTEIRA,
    SUFIXO_BARRA_ATIVA,
    TEXTO_ABERTURA_SIMULADOR,
    TEXTO_AJUDA_CORRELACAO,
    TEXTO_AJUDA_INDICADORES_AUSENTES,
    TEXTO_AJUDA_TRADINGVIEW,
    TEXTO_COMPLEMENTO_SEM_METODO,
    TEXTO_CRESCIMENTO_IPCA,
    TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA,
    TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA,
    TEXTO_DIVERGENCIA_NENHUM_METODO,
    TEXTO_DIVERGENCIA_UM_METODO,
    TEXTO_EXPANDER_SIMULADOR,
    TEXTO_FCD_AJUSTES_DO_BALANCO,
    TEXTO_FIRMA_SEM_COMPONENTES,
    TEXTO_NENHUM_METODO_SE_APLICA,
    TEXTO_OBSERVACOES_CORRELACAO,
    TEXTO_RISCO_SACADO_RECLASSIFICADO,
    TEXTO_RODADA_DESCARTADA,
    TEXTO_RODAPE_LINK_REPOSITORIO,
    TEXTO_RODAPE_SCREENER_ATUALIZADO,
    TEXTO_SCREENER_AINDA_NAO_GERADO,
    TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW,
    TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA,
    TEXTO_SCREENER_CONCLUIDO,
    TEXTO_SCREENER_CONCLUIDO_COM_FALHAS,
    TEXTO_SEM_ACOES_EM_CIRCULACAO,
    TEXTO_SEM_AJUSTES_DO_BALANCO,
    TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA,
    TEXTO_SEM_DESCONTO_NAO_CONTROLADORES,
    TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS,
    TEXTO_ULTIMO_DADO_GPR,
    TICKER_PETROLEO_BRENT,
    TITULO_EXPANDER_SIMULADOR,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    TITULO_PAINEL_DIVIDENDOS,
    TOOLTIP_DIVERGENCIA_METODOS,
    TOOLTIP_POTENCIAL_CARTAO,
    TOOLTIP_POTENCIAL_CENARIO,
    TOOLTIP_POTENCIAL_COLUNA,
    TOOLTIP_VALOR_FIRMA,
    URL_PAGINA_ANALISAR,
    URL_PAGINA_CARTEIRA,
    URL_PAGINA_SCREENER,
    URL_REPOSITORIO,
    VALORES_PERMITIR_RODAR_SCREENER,
    VARIAVEL_PERMITIR_RODAR_SCREENER,
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
    carregar_macro_referencia,
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
from avaliador_b3.modelos.aviso_fcd import avaliar_fcd_extremo
from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin
from avaliador_b3.modelos.combinado import (
    calcular_divergencia_metodos,
    calcular_valor_combinado,
    linhas_motivos_metodos,
)
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


def _buscar_leitura_balanco(cnpj: str, indicadores: dict | None, ticker: str) -> dict:
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
            ticker=ticker,
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


def _widget_avancado_tradingview(ticker: str) -> str | None:
    """HTML do widget "Advanced Chart" do TradingView (embutido via
    st.iframe), símbolo montado dinamicamente a partir do
    ticker buscado na tela — ver
    https://br.tradingview.com/widget/advanced-chart/. Só aceita ticker no formato
    da B3 (`PADRAO_TICKER_B3`); qualquer outro texto devolve `None`, sem HTML. A
    configuração vai como JSON serializado (`json.dumps`), nunca por interpolação.
    Se o JavaScript não carregar (rede/ambiente restrito), o widget só fica em
    branco, sem quebrar o resto da página."""
    if not re.fullmatch(PADRAO_TICKER_B3, ticker):
        return None
    configuracao = json.dumps(
        {
            "autosize": True,
            "symbol": f"BMFBOVESPA:{ticker}",
            "interval": "D",
            "timezone": "America/Sao_Paulo",
            "theme": "dark",
            "style": "1",
            "locale": "br",
            "allow_symbol_change": True,
            "support_host": "https://www.tradingview.com",
        }
    ).replace("<", "\\u003c")
    return f"""
    <style>html, body {{ height: 100%; margin: 0; overflow: hidden; }}</style>
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget"
        style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
        async>
      {configuracao}
      </script>
    </div>
    """


def aplicar_template_grafico(figura: go.Figure) -> go.Figure:
    """Template único dos gráficos: fundo transparente (o painel da página
    aparece por trás), grade discreta, fonte e sequência de cores do tema."""
    figura.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COR_TEXTO},
        colorway=list(SEQUENCIA_CORES_SERIES),
        hoverlabel={"bgcolor": COR_FUNDO_PAINEL, "bordercolor": COR_BORDA},
    )
    figura.update_xaxes(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE, linecolor=COR_BORDA)
    figura.update_yaxes(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE, linecolor=COR_BORDA)
    return figura


def exibir_grafico(figura: go.Figure) -> None:
    """Único ponto de `st.plotly_chart` do app: tema do Plotly (não o do Streamlit), largura
    total e sem a barra de ferramentas."""
    st.plotly_chart(figura, width="stretch", theme=None, config=CONFIG_PLOTLY)


def _figura_dividendos(
    dividendos_por_ano: pd.DataFrame, dividend_yield_por_ano: pd.DataFrame, ano_inicial: int | None
) -> go.Figure:
    """Barras do dividend yield (%) de cada ano, em eixo único; o yield e o total pago (R$/ação)
    ficam no hover. Com `ano_inicial`, mostra só dele em diante e escreve o % sobre cada barra
    (anos sem dividendo ficam sem rótulo); sem ele, o histórico todo, com rótulo só no hover. O
    ano corrente, incompleto, tem barra clara com hachura e asterisco no rótulo do eixo."""
    anos = dividendos_por_ano.merge(dividend_yield_por_ano, on="ano")
    if ano_inicial is not None:
        anos = anos[anos["ano"] >= ano_inicial]
    rotulos_x = [
        ROTULO_ANO_PARCIAL.format(ano=int(ano)) if parcial else str(int(ano))
        for ano, parcial in zip(anos["ano"], anos["parcial"], strict=True)
    ]
    # Formatado em Python: o d3-format do Plotly não tem vírgula decimal sem um locale registrado.
    percentuais = [_fmt_percentual(y) for y in anos["yield_percentual"]]
    totais = list(anos["total"])
    hover = [[pct, _fmt_bilhoes(total)] for pct, total in zip(percentuais, totais, strict=True)]
    rotulos = [pct if total > 0 else "" for pct, total in zip(percentuais, totais, strict=True)]
    figura = go.Figure(
        go.Bar(
            x=rotulos_x,
            y=anos["yield_percentual"],
            text=rotulos,
            textposition="outside" if ano_inicial is not None else "none",
            textfont={"color": COR_TEXTO},
            cliponaxis=False,
            customdata=hover,
            hovertemplate="Dividend Yield: %{customdata[0]}<br>Total pago: %{customdata[1]}"
            "<extra></extra>",
            marker={
                "color": COR_PRINCIPAL,
                "opacity": [OPACIDADE_BARRA_PARCIAL if p else 1.0 for p in anos["parcial"]],
                "line": {"color": COR_PRINCIPAL, "width": 2},
                "pattern": {
                    "shape": ["/" if p else "" for p in anos["parcial"]],
                    "fgcolor": COR_PRINCIPAL,
                    "bgcolor": COR_FUNDO_PAINEL,
                },
            },
        )
    )
    figura.update_layout(
        xaxis={"type": "category"},
        yaxis={"ticksuffix": "%", "rangemode": "tozero"},
        showlegend=False,
        margin={"t": 20, "b": 10, "l": 10, "r": 10},
    )
    figura.update_xaxes(automargin=True)
    figura.update_yaxes(automargin=True)
    return aplicar_template_grafico(figura)


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
            line={"color": COR_PRINCIPAL},
        )
    )
    figura.add_trace(
        go.Scatter(
            x=serie_b["data"],
            y=normalizado_b,
            name=nome_b,
            line={"color": COR_NEUTRO},
        )
    )
    figura.update_layout(
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "top", "y": -0.12, "xanchor": "left", "x": 0},
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
    )
    aplicar_template_grafico(figura)
    tickvals, ticktext = ticks_mensais_pt_br(serie_a["data"])
    figura.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
    # Margem esquerda pequena: o eixo Y cresce sozinho para caber os números.
    figura.update_yaxes(automargin=True)
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


def _html_kpi(
    rotulo: str,
    valor: str,
    classe_cor: str,
    linha: str = "",
    classe_linha: str = "ab-cor-secundario",
    ajuda: str | None = None,
) -> str:
    """Cartão de número de destaque (HTML com as classes `.ab-*` de `_CSS_DA_PAGINA`);
    `st.metric` não deixa colorir o número. `ajuda` vira o "?" com tooltip."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    return (
        '<div class="ab-kpi">'
        f'<div class="ab-titulo">{escape(rotulo)}{marca_ajuda}</div>'
        f'<div class="ab-valor {classe_cor}">{escape(valor)}</div>'
        f'<div class="ab-linha {classe_linha}">{escape(linha)}</div>'
        "</div>"
    )


def _kpi_divergencia(divergencia: dict, valores_por_metodo: dict[str, float]) -> dict:
    """Conteúdo do cartão de divergência entre métodos: o número é o
    `divergencia_percentual` de `calcular_divergencia_metodos`, em amarelo a partir de
    `LIMITE_DIVERGENCIA_METODOS_ALTA`; a linha pequena traz o menor e o maior valor justo
    com o nome do método. Sem divergência calculável, "—" e o motivo."""
    if not divergencia["aplicavel"]:
        texto = (
            TEXTO_DIVERGENCIA_UM_METODO
            if len(valores_por_metodo) == 1
            else TEXTO_DIVERGENCIA_NENHUM_METODO
        )
        return {"valor": "—", "classe_cor": "ab-cor-secundario", "linha": texto}
    ordenados = sorted(valores_por_metodo.items(), key=lambda item: item[1])
    menor, maior = ordenados[0], ordenados[-1]
    linha = " · ".join(
        f"{NOMES_METODOS.get(nome, nome)} {_fmt_bilhoes(valor)}" for nome, valor in (menor, maior)
    )
    percentual = divergencia["divergencia_percentual"]
    if percentual is None:
        return {"valor": "—", "classe_cor": "ab-cor-texto", "linha": linha}
    alta = percentual / 100 >= LIMITE_DIVERGENCIA_METODOS_ALTA
    return {
        "valor": f"{percentual:.0f}%",
        "classe_cor": "ab-cor-alerta" if alta else "ab-cor-texto",
        "linha": linha,
    }


def _rotulo_segmento_setorial(segmento: str | None) -> str | None:
    """Texto do segmento setorial para exibir; o dado e o agrupamento usam o original."""
    return CORRECOES_EXIBICAO_SEGMENTO_SETORIAL.get(segmento, segmento) if segmento else segmento


def _html_pilulas(segmento_setorial: str | None, segmento_listagem: str | None) -> str:
    """Pílulas com o segmento setorial e o de listagem; só as que existem. Vazio sem nenhuma."""
    segmento_setorial = _rotulo_segmento_setorial(segmento_setorial)
    pilulas = [
        f'<span class="ab-pilula" title="{escape(titulo)}">{escape(texto)}</span>'
        for titulo, texto in (
            ("Segmento setorial (B3)", segmento_setorial),
            ("Segmento de listagem", segmento_listagem),
        )
        if texto
    ]
    return f'<div class="ab-pilulas">{"".join(pilulas)}</div>' if pilulas else ""


def _notas_do_metodo(resultado: dict) -> tuple[list[str], list[str]]:
    """Legendas de um método aplicável (Graham/Bazin/FCD), em duas listas: as que ficam à
    vista (hoje só o aviso de dívida líquida indisponível, que muda a leitura do valor) e as
    de detalhe, que vão para o expander. `resultado` é o dict padrão dos três modelos.

    `resultado.get("divida_liquida_deduzida")` só existe no dict do FCD (ver modelos/fcd.py):
    `False` significa que o valor não teve a dívida líquida deduzida (dado ausente pra essa
    empresa; banco nunca chega aqui, já é "não aplicável" antes, ver
    config.SEGMENTOS_FCD_NAO_APLICAVEL)."""
    visiveis: list[str] = []
    detalhes: list[str] = []
    if resultado.get("divida_liquida_deduzida") is False:
        visiveis.append(
            "Dívida líquida indisponível pra essa empresa — sem ela pra "
            "deduzir, este valor não desconta a dívida da empresa, então "
            "tende a ficar mais alto do que se a dedução fosse possível."
        )
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
    balanco_inteiro_indisponivel = len(motivos_do_balanco) == 1 and None not in motivos_do_balanco
    if balanco_inteiro_indisponivel:
        detalhes.append(TEXTO_SEM_AJUSTES_DO_BALANCO.format(motivo=motivo_sem_nao_controladores))
    elif motivo_sem_nao_controladores:
        detalhes.append(
            TEXTO_SEM_DESCONTO_NAO_CONTROLADORES.format(motivo=motivo_sem_nao_controladores)
        )
    motivo_sem_acoes = resultado.get("motivo_sem_acoes_em_circulacao")
    if motivo_sem_acoes:
        detalhes.append(TEXTO_SEM_ACOES_EM_CIRCULACAO.format(motivo=motivo_sem_acoes))
    if motivo_sem_arrendamento and not balanco_inteiro_indisponivel:
        detalhes.append(TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA.format(motivo=motivo_sem_arrendamento))
    if motivo_sem_patrimonio_total and not balanco_inteiro_indisponivel:
        detalhes.append(
            TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS.format(motivo=motivo_sem_patrimonio_total)
        )
    motivo_crescimento_ipca = resultado.get("motivo_crescimento_ipca")
    if motivo_crescimento_ipca:
        detalhes.append(TEXTO_CRESCIMENTO_IPCA.format(motivo=motivo_crescimento_ipca))
    if resultado.get("crescimento_limitado_pela_receita"):
        detalhes.append(
            TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA.format(
                taxa=_fmt_percentual(resultado["taxa_crescimento_receita"] * 100, 1)
            )
        )
    elif resultado.get("motivo_sem_limite_da_receita"):
        detalhes.append(
            TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA.format(
                motivo=resultado["motivo_sem_limite_da_receita"]
            )
        )
    return visiveis, detalhes


def _rotulo_barra_valor_justo(valor: float, preco_atual: float | None) -> str:
    """Rótulo da barra: o valor e, havendo preço, a diferença para ele ("93,22  +60,7%")."""
    texto = _pt_br(f"{valor:,.2f}")
    if preco_atual is None:
        return texto
    diferenca = (valor - preco_atual) / preco_atual * 100
    sinal = "+" if diferenca > 0 else ""
    return f"{texto}\u00a0\u00a0{sinal}{_fmt_percentual(diferenca)}"


def _figura_valor_justo(
    valores_por_metodo: dict[str, float], valor_combinado: float, preco_atual: float | None
) -> go.Figure:
    """Barras horizontais do valor de cada método aplicável e do combinado, com o preço atual
    numa linha tracejada. Verde acima do preço, rosa abaixo; o combinado em ciano; sem preço,
    barras neutras e sem linha."""
    rotulos = [ROTULOS_METODOS_GRAFICO.get(nome, nome) for nome in valores_por_metodo]
    valores = [*valores_por_metodo.values(), valor_combinado]
    rotulos.append(ROTULO_COMBINADO_GRAFICO)

    def cor_da_barra(valor: float) -> str:
        if preco_atual is None:
            return COR_NEUTRO
        return COR_POSITIVO if valor >= preco_atual else COR_NEGATIVO

    cores = [cor_da_barra(valor) for valor in valores[:-1]] + [COR_PRINCIPAL]
    figura = go.Figure(
        go.Bar(
            x=valores,
            y=rotulos,
            orientation="h",
            marker={"color": cores},
            text=[_rotulo_barra_valor_justo(valor, preco_atual) for valor in valores],
            textposition="none",
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    extremos = [0.0, *valores] + ([preco_atual] if preco_atual is not None else [])
    menor, maior = min(extremos), max(extremos)
    amplitude = (maior - menor) or 1.0
    figura.update_xaxes(
        range=[menor - 0.1 * amplitude if menor < 0 else 0, maior + 0.4 * amplitude],
        showticklabels=False,
    )
    limite_x = maior + 0.4 * amplitude
    fora_da_barra = []
    for rotulo, valor, texto in zip(rotulos, valores, figura.data[0].text, strict=True):
        # O valor vai numa anotação com fundo, que cobre a linha do preço quando ela passa por trás.
        figura.add_annotation(
            x=valor,
            y=rotulo,
            text=texto,
            showarrow=False,
            xanchor="left",
            xshift=6,
            bgcolor=COR_FUNDO_PAINEL,
            borderpad=2,
            font={"color": COR_TEXTO},
        )
        largura_necessaria = len(rotulo) * LARGURA_CARACTERE_ROTULO_BARRA + FOLGA_ROTULO_BARRA
        if valor > 0 and valor / limite_x >= largura_necessaria:
            figura.add_annotation(
                x=0,
                y=rotulo,
                text=f"<b>{rotulo}</b>",
                showarrow=False,
                xanchor="left",
                xshift=6,
                font={"color": COR_FUNDO_PAGINA},
            )
        else:
            fora_da_barra.append(rotulo)
    # Nome dentro da barra; o que não cabe fica no eixo, à esquerda (a margem acompanha).
    figura.update_yaxes(
        autorange="reversed",
        tickmode="array",
        tickvals=fora_da_barra,
        ticktext=fora_da_barra,
        showticklabels=bool(fora_da_barra),
        automargin=True,
    )
    if preco_atual is not None:
        figura.add_vline(
            x=preco_atual,
            line_dash="dash",
            line_color=COR_ALERTA,
            annotation_text=f"Preço {_fmt_bilhoes(preco_atual)}",
            annotation_position="top",
            annotation_font_color=COR_ALERTA,
        )
    figura.update_layout(
        height=70 + 46 * len(valores), margin={"t": 36, "b": 10, "l": 10, "r": 10}, showlegend=False
    )
    return aplicar_template_grafico(figura)


def _html_cabecalho_painel(
    titulo: str, selos: list[tuple[str, str]], ajuda: str | None = None
) -> str:
    """Título do painel (pequeno, em caixa alta, com "?" opcional) e, à direita, selos
    `(texto, dica)`."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    html_selos = "".join(
        f'<span class="ab-selo" title="{escape(dica)}">{escape(texto)}</span>'
        for texto, dica in selos
    )
    return (
        f'<div class="ab-cabecalho"><span class="ab-titulo">{escape(titulo)}{marca_ajuda}</span>'
        f'<span class="ab-selos">{html_selos}</span></div>'
    )


def _cor_indicador(valor: float | None, regra: str) -> str:
    """Classe de cor de um indicador da Saúde financeira: `"sinal"` (verde acima de zero, rosa
    abaixo), `"queda"` (rosa abaixo de zero) ou `"liquidez"` (amarelo abaixo do limite). Sem
    cor para zero, dado ausente ou fora dessas regras."""
    if valor is None or pd.isna(valor):
        return "ab-cor-texto"
    if regra == "liquidez":
        return "ab-cor-alerta" if valor < LIMITE_LIQUIDEZ_CORRENTE_BAIXA else "ab-cor-texto"
    if valor < LIMITE_SINAL_INDICADOR:
        return "ab-cor-negativo"
    if valor > LIMITE_SINAL_INDICADOR and regra == "sinal":
        return "ab-cor-positivo"
    return "ab-cor-texto"


def _titulo_painel(titulo: str, ajuda: str | None = None) -> None:
    """Título pequeno de painel, sem âncora (no lugar de `st.subheader`)."""
    st.html(_html_cabecalho_painel(titulo, [], ajuda))


def _html_indicador(
    rotulo: str, valor: str, classe_cor: str = "ab-cor-texto", ajuda: str = ""
) -> str:
    """Um indicador da grade: rótulo pequeno e valor monoespaçado; `ajuda` vira o "?" do rótulo."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    return (
        f'<div class="ab-ind"><span class="ab-ind-rotulo">{escape(rotulo)}{marca_ajuda}</span>'
        f'<span class="ab-ind-valor {classe_cor}">{escape(valor)}</span></div>'
    )


def _html_linha_correlacao(nome: str, resultado: dict, ultimo_gpr: str | None) -> str:
    """Linha de um fator: nome com "?" (observações, data do GPR ou motivo), mini barra de −1 a
    +1 (do centro para a direita se positiva, para a esquerda se negativa), valor e leitura de
    magnitude (`correlacao.classificar_magnitude_correlacao`); sem dado, "—"."""
    if not resultado["aplicavel"]:
        ajuda = f"Indisponível: {resultado['motivo_nao_aplicavel']}"
        trilho = '<span class="ab-div-trilho"></span>'
        valor, classe = "—", ""
    else:
        coeficiente = resultado["correlacao"]
        ajuda = TEXTO_OBSERVACOES_CORRELACAO.format(observacoes=resultado["observacoes"])
        lado = "ab-corr-pos" if coeficiente >= 0 else "ab-corr-neg"
        largura = min(abs(coeficiente), 1.0) * 50
        trilho = (
            '<span class="ab-div-trilho">'
            f'<i class="ab-div-barra {lado}" style="width:{largura:.1f}%"></i></span>'
        )
        valor = _fmt(coeficiente)
        classe = classificar_magnitude_correlacao(coeficiente)
    if ultimo_gpr:
        ajuda += f" · {ultimo_gpr}"
    return (
        '<div class="ab-corr">'
        f'<span class="ab-corr-nome">{escape(nome)}'
        f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span></span>'
        f'{trilho}<span class="ab-div-valor">{escape(valor)}</span>'
        f'<span class="ab-corr-classe">{escape(classe)}</span></div>'
    )


def _html_correlacoes(resultados: dict, ultimo_gpr: str | None) -> str:
    """As linhas dos três fatores; `ultimo_gpr` (data já formatada) entra na dica do GPR."""
    return "".join(
        _html_linha_correlacao(nome, resultados[chave], ultimo_gpr if chave == "gpr" else None)
        for chave, nome in NOMES_FATORES_CORRELACAO.items()
    )


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


def _fmt_potencial(valor: float | None) -> str:
    """Potencial com sinal explícito ("+13,5%", "-21,0%"), como no cartão do topo."""
    texto = _fmt_percentual(valor)
    if valor is None or pd.isna(valor) or valor <= LIMITE_SINAL_INDICADOR:
        return texto
    return f"+{texto}"


def _html_barra_potencial(valor: float | None) -> str:
    """Barra divergente do potencial: verde à direita do centro, rosa à esquerda, cortada em
    `LIMITE_BARRA_POTENCIAL`; o valor exato fica ao lado."""
    if valor is None or pd.isna(valor):
        return (
            '<div class="ab-div"><span class="ab-div-trilho"></span>'
            '<span class="ab-div-valor">—</span></div>'
        )
    classe = "ab-div-pos" if valor > LIMITE_SINAL_INDICADOR else "ab-div-neg"
    largura = min(abs(valor), LIMITE_BARRA_POTENCIAL) / LIMITE_BARRA_POTENCIAL * 50
    return (
        '<div class="ab-div"><span class="ab-div-trilho">'
        f'<i class="ab-div-barra {classe}" style="width:{largura:.1f}%"></i></span>'
        f'<span class="ab-div-valor">{escape(_fmt_potencial(valor))}</span></div>'
    )


def _html_tabela_setorial(tabela: pd.DataFrame, ticker_destacado: str) -> str:
    """Tabela da comparação setorial (ticker, preço, valor combinado e potencial com barra
    divergente); a linha de `ticker_destacado` fica em destaque."""
    linhas = []
    for linha in tabela.itertuples():
        classe = ' class="ab-linha-destaque"' if linha.ticker == ticker_destacado else ""
        linhas.append(
            f"<tr{classe}><td>{escape(str(linha.ticker))}</td>"
            f'<td class="ab-num">{escape(_fmt_bilhoes(linha.preco_atual))}</td>'
            f'<td class="ab-num">{escape(_fmt_bilhoes(linha.valor_combinado))}</td>'
            f"<td>{_html_barra_potencial(linha.desconto_percentual)}</td></tr>"
        )
    ajuda = f'<span class="ab-ajuda" title="{escape(TOOLTIP_POTENCIAL_COLUNA)}">?</span>'
    return (
        '<div class="ab-tabela-caixa"><table class="ab-tabela"><thead><tr>'
        '<th>Ticker</th><th class="ab-num">Preço atual</th>'
        '<th class="ab-num">Valor combinado</th>'
        f"<th>{escape(ROTULO_POTENCIAL)}{ajuda}</th></tr></thead>"
        f"<tbody>{''.join(linhas)}</tbody></table></div>"
    )


def _nomes_dos_metodos(metodos: list[str]) -> str:
    """Nomes dos métodos como aparecem na tela ("Graham, Bazin, FCD"), a partir dos
    identificadores em minúsculas (`resultado_combinado["metodos_utilizados"]`)."""
    return ", ".join(NOMES_METODOS.get(metodo, metodo) for metodo in metodos)


def _nomes_dos_metodos_do_csv(valor: str) -> str:
    """O mesmo para a célula do CSV do screener, onde os métodos vêm separados por vírgula."""
    return _nomes_dos_metodos([m for m in valor.split(",") if m])


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
        return _pt_br(f"R$ {valor / 1e9:,.1f} bi")
    if abs(valor) >= 1e6:
        return _pt_br(f"R$ {valor / 1e6:,.1f} mi")
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
    (que não passam por aqui) continuam ordenando normal. Usado nas
    tabelas do projeto que mostram R$/%: Screener, Simulador de carteira,
    Ganho nominal vs. real."""
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


def _texto_screener_atualizado_pelo_workflow() -> str:
    """Aviso do app publicado, com a data da última rodada ao vivo aceita (a do arquivo de
    referência, gravado a cada rodada); o horário do arquivo no disco seria o do deploy."""
    macro = carregar_macro_referencia()
    if macro is None:
        return TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA
    return TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW.format(data=_fmt_data(macro["data_busca"]))


# Ticker pré-selecionado e buscado automaticamente só na primeira abertura da
# sessão (ver `busca_inicial_automatica_feita` em session_state, mais abaixo)
# — mostra um resultado de exemplo de cara, sem exigir clique em "Buscar".
TICKER_PADRAO_PRIMEIRA_ABERTURA = "PETR4"

_CSS_DA_PAGINA = Template("""<style>
/* Fundo dos painéis: gancho `.st-key-painel_*` gerado pelo `key` de cada st.container. */
[class*="st-key-painel_"] { background-color: $painel; }
/* Blocos da barra lateral: gancho `.st-key-barra_*`; o da página aberta tem o sufixo `_ativa`. */
[class*="st-key-barra_"] { background-color: $painel; }
[class*="st-key-barra_"][class*="_ativa"] { border-color: $principal; }
[class*="st-key-barra_"] a, [class*="st-key-barra_"] a p { font-size: 16px; font-weight: 600; }
[class*="st-key-barra_"][class*="_ativa"] a, [class*="st-key-barra_"][class*="_ativa"] a p {
  color: $principal; }
[class*="st-key-barra_"] label, [class*="st-key-barra_"] label p { font-size: 14px; }
.st-key-barra_rodape { background-color: transparent; }
.st-key-barra_rodape p, .st-key-barra_rodape a { font-size: 14px; }
/* Classes `.ab-*`: números de destaque, títulos e pílulas. Se o Streamlit deixar de aceitar
   este bloco, o conteúdo continua na tela, só sem o estilo. */
.ab-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; }
.ab-kpi { min-width: 0; }
.ab-titulo { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase;
  color: $secundario; }
.ab-ajuda { cursor: help; margin-left: .4rem; padding: 0 .35rem; border: 1px solid $borda;
  border-radius: 50%; font-size: .65rem; letter-spacing: 0; }
.ab-valor { font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 2.25rem; font-weight: 600; line-height: 1.25; white-space: nowrap; }
.ab-linha { font-size: .8rem; color: $secundario; min-height: 1.2em; }
.ab-cor-texto { color: $texto; }
.ab-cor-principal { color: $principal; }
.ab-cor-positivo { color: $positivo; }
.ab-cor-negativo { color: $negativo; }
.ab-cor-alerta { color: $alerta; }
.ab-cor-secundario { color: $secundario; }
.ab-cabecalho { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: .5rem; margin-bottom: .25rem; }
.ab-selos { display: flex; flex-wrap: wrap; gap: .4rem; }
.ab-selo { padding: .05rem .6rem; border: 1px solid $borda; border-radius: 999px; font-size: .75rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace; color: $texto; cursor: help; }
.ab-grade { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem 1rem; }
.ab-ind { min-width: 0; }
.ab-ind-rotulo { display: block; font-size: .72rem; color: $secundario; }
.ab-ind-valor { font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; font-size: 1.2rem; font-weight: 600; white-space: nowrap; }
/* A tabela da comparação setorial ocupa a altura do painel (que acompanha o vizinho). Se o
   Streamlit renomear as classes .stElementContainer/.stHtml, só o esticamento se perde: a
   tabela continua visível, com a altura do conteúdo. */
.st-key-painel_comparacao_setorial .stElementContainer:has(.ab-tabela-caixa) {
  flex: 1 1 auto; min-height: 0; }
.st-key-painel_comparacao_setorial .stHtml,
.st-key-painel_comparacao_setorial .ab-tabela-caixa,
.st-key-painel_comparacao_setorial .ab-tabela { height: 100%; }
.ab-tabela-caixa { overflow-x: auto; }
.ab-tabela { width: 100%; border-collapse: collapse; font-size: .85rem; }
.ab-tabela th { padding: .35rem .5rem; text-align: left; font-size: .72rem; font-weight: 400;
  letter-spacing: .08em; text-transform: uppercase; color: $secundario;
  border-bottom: 1px solid $borda; }
.ab-tabela td { padding: .45rem .5rem; border-bottom: 1px solid $borda; }
.ab-tabela .ab-num { text-align: right; font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.ab-tabela tr.ab-linha-destaque td { font-weight: 600; background: $borda; }
.ab-tabela tr.ab-linha-destaque td:first-child { color: $principal;
  box-shadow: inset 3px 0 $principal; }
.ab-div { display: flex; align-items: center; gap: .5rem; min-width: 11rem; }
.ab-div-trilho { position: relative; flex: 1; height: .6rem; }
.ab-div-trilho::before { content: ""; position: absolute; left: 50%; top: -.15rem;
  bottom: -.15rem; width: 1px; background: $secundario; }
.ab-div-barra { position: absolute; top: 0; bottom: 0; border-radius: 2px; }
.ab-div-pos { left: 50%; background: $positivo; }
.ab-div-neg { right: 50%; background: $negativo; }
.ab-div-valor { min-width: 4.2rem; text-align: right; white-space: nowrap;
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ab-corr { display: grid; grid-template-columns: 8.5rem minmax(3rem, 1fr) 4.2rem 5.2rem;
  align-items: center; gap: .6rem; padding: .45rem 0; }
.ab-corr-nome { font-size: .85rem; }
.ab-corr-classe { font-size: .75rem; color: $secundario; }
.ab-corr-pos { left: 50%; background: $principal; }
.ab-corr-neg { right: 50%; background: $principal; }
.ab-pilulas { display: flex; flex-wrap: wrap; gap: .5rem; margin: .25rem 0 .75rem; }
.ab-pilula { padding: .1rem .75rem; border: 1px solid $borda; border-radius: 999px;
  font-size: .78rem; color: $secundario; }
</style>""").substitute(
    painel=COR_FUNDO_PAINEL,
    secundario=COR_TEXTO_SECUNDARIO,
    borda=COR_BORDA,
    texto=COR_TEXTO,
    principal=COR_PRINCIPAL,
    positivo=COR_POSITIVO,
    negativo=COR_NEGATIVO,
    alerta=COR_ALERTA,
)

st.set_page_config(page_title="Avaliador B3 (protótipo)", page_icon="📈", layout="wide")
# Único bloco de CSS da página (ver `_CSS_DA_PAGINA`).
st.html(_CSS_DA_PAGINA)
st.title("Avaliador de Ações da B3")
st.caption(SUBTITULO_APP)


def pagina_analisar() -> None:
    # Buscado aqui em cima (não só depois de "Buscar") porque o dropdown
    # abaixo precisa da lista de opções pra se desenhar — reaproveitado
    # mais adiante na seção "Governança", não buscado de novo lá.
    universo_ibovespa, erro_universo = _buscar_universo_ibovespa()
    usando_dropdown = not (erro_universo or universo_ibovespa is None or universo_ibovespa.empty)

    busca_inicial_ja_feita = st.session_state.get("busca_inicial_automatica_feita", False)

    # A ação escolhida fica guardada à parte: o Streamlit apaga o estado de um widget que não é
    # desenhado numa rodada (ao sair da página), e a seleção é restaurada ao voltar.
    ticker_guardado = st.session_state.get(CHAVE_TICKER_GUARDADO)
    with _bloco_barra_analisar:
        if usando_dropdown:
            assert universo_ibovespa is not None, "o dropdown só é usado com o universo carregado"
            nomes_por_ticker = dict(
                zip(universo_ibovespa["ticker"], universo_ibovespa["nome"], strict=True)
            )
            opcoes_ticker = list(nomes_por_ticker.keys())
            if CHAVE_DROPDOWN_TICKER not in st.session_state and ticker_guardado in opcoes_ticker:
                st.session_state[CHAVE_DROPDOWN_TICKER] = ticker_guardado
            # Pré-seleciona o ticker padrão só na primeira abertura da sessão; depois, o
            # dropdown segue 100% manual. A `key` fixa preserva a escolha entre reruns.
            indice_inicial = (
                opcoes_ticker.index(TICKER_PADRAO_PRIMEIRA_ABERTURA)
                if not busca_inicial_ja_feita and TICKER_PADRAO_PRIMEIRA_ABERTURA in opcoes_ticker
                else None
            )
            ticker_selecionado = st.selectbox(
                "Ação (Ibovespa)",
                options=opcoes_ticker,
                format_func=lambda t: f"{t} — {nomes_por_ticker[t]}",
                key=CHAVE_DROPDOWN_TICKER,
                index=indice_inicial,
                placeholder="Selecione uma ação...",
            )
            ticker = ticker_selecionado or ""
        else:
            # Degradação graciosa: a API da B3 pode estar fora do ar; texto livre, sem a lista.
            # Sem dropdown não há pré-seleção, então a busca automática não se aplica.
            st.warning(
                "Lista de ações do Ibovespa indisponível "
                f"({erro_universo or 'resultado vazio'}) — digite o ticker manualmente."
            )
            if CHAVE_TEXTO_TICKER not in st.session_state and ticker_guardado:
                st.session_state[CHAVE_TEXTO_TICKER] = ticker_guardado
            ticker = st.text_input("Ticker (ex: PETR4)", value="", key=CHAVE_TEXTO_TICKER)
            ticker = ticker.strip().upper()
        st.session_state[CHAVE_TICKER_GUARDADO] = ticker

        buscar_clicado = st.button("Buscar")
    # Preenchido depois da busca, quando o segmento setorial já foi obtido.
    espaco_pilulas = st.container()

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
            leitura_balanco = _buscar_leitura_balanco(cnpj, indicadores, ticker) if cnpj else None

        st.subheader(ticker)
        # Números de destaque: preenchido mais abaixo, quando o valor combinado já existe.
        painel_destaque = st.container(border=True, key="painel_destaque")

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
            if not preco_valido(preco_atual):
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
        if leitura_balanco and leitura_balanco.get("aviso_unit"):
            st.warning(leitura_balanco["aviso_unit"])
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

        resultado_combinado = calcular_valor_combinado(
            resultado_graham, resultado_bazin, resultado_fcd
        )
        divergencia_metodos = calcular_divergencia_metodos(
            resultado_combinado["valores_por_metodo"], preco_atual
        )
        cartoes_destaque = []
        if preco_atual is not None:
            cartoes_destaque.append(
                _html_kpi("Preço atual", _fmt_bilhoes(preco_atual), "ab-cor-texto")
            )
        if resultado_combinado["aplicavel"]:
            valor_combinado = resultado_combinado["valor_combinado"]
            cartoes_destaque.append(
                _html_kpi("Valor combinado", _fmt_bilhoes(valor_combinado), "ab-cor-principal")
            )
            if preco_atual is not None:
                acima_do_preco = valor_combinado >= preco_atual
                cor_potencial = "ab-cor-positivo" if acima_do_preco else "ab-cor-negativo"
                cartoes_destaque.append(
                    _html_kpi(
                        ROTULO_POTENCIAL,
                        ("+" if valor_combinado > preco_atual else "")
                        + (_delta_percentual_upside(valor_combinado, preco_atual) or ""),
                        cor_potencial,
                        "▲ valor acima do preço" if acima_do_preco else "▼ valor abaixo do preço",
                        cor_potencial,
                        ajuda=TOOLTIP_POTENCIAL_CARTAO,
                    )
                )
        else:
            motivos_metodos = "\n".join(
                linhas_motivos_metodos(resultado_graham, resultado_bazin, resultado_fcd)
            )
            rotulos_sem_valor = ["Valor combinado"]
            if preco_atual is not None:
                rotulos_sem_valor.append(ROTULO_POTENCIAL)
            for rotulo_cartao in rotulos_sem_valor:
                cartoes_destaque.append(
                    _html_kpi(
                        rotulo_cartao,
                        "—",
                        "ab-cor-secundario",
                        TEXTO_NENHUM_METODO_SE_APLICA,
                        ajuda=motivos_metodos,
                    )
                )
        cartoes_destaque.append(
            _html_kpi(
                "Divergência entre métodos",
                **_kpi_divergencia(divergencia_metodos, resultado_combinado["valores_por_metodo"]),
                ajuda=TOOLTIP_DIVERGENCIA_METODOS,
            )
        )
        with painel_destaque:
            st.html(f'<div class="ab-kpis">{"".join(cartoes_destaque)}</div>')

        linha_listagem = (
            universo_ibovespa[universo_ibovespa["ticker"] == ticker]
            if universo_ibovespa is not None
            else None
        )
        segmento_listagem = (
            linha_listagem.iloc[0]["segmento_listagem"]
            if linha_listagem is not None and not linha_listagem.empty
            else None
        )
        with espaco_pilulas:
            st.html(_html_pilulas(segmento_setorial, segmento_listagem))

        proporcao_reinvestimento = None
        selos_valor_justo: list[tuple[str, str]] = []
        if resultado_fcd["aplicavel"]:
            origem_beta = "calculado, 1a" if beta is not None else "padrão, sem histórico"
            beta_wacc = _fmt(resultado_fcd["beta_utilizado"])
            selos_valor_justo.append(
                (f"Beta {beta_wacc}", f"Beta no WACC: {beta_wacc} ({origem_beta})")
            )
            if caixa_fcd_utilizado is not None and capex_fcd_utilizado is not None:
                proporcao_reinvestimento = calcular_proporcao_capex_caixa_operacional_percentual(
                    caixa_fcd_utilizado, capex_fcd_utilizado
                )
            # Sem capex identificado, sem selo (o FCD nem é calculado).
            if proporcao_reinvestimento is not None:
                selos_valor_justo.append(
                    (
                        f"Reinvestimento {proporcao_reinvestimento:.0f}%",
                        LEGENDA_REINVESTIMENTO_CAPEX.format(
                            ano=ano_fcd_utilizado, proporcao=proporcao_reinvestimento
                        ),
                    )
                )

        metodos_painel = (
            ("graham", resultado_graham),
            ("bazin", resultado_bazin),
            ("fcd", resultado_fcd),
        )
        coluna_valor_justo, coluna_saude = st.columns([3, 2])
        with (
            coluna_valor_justo,
            st.container(border=True, key="painel_valor_justo", height="stretch"),
        ):
            st.html(_html_cabecalho_painel("Valor justo por método", selos_valor_justo))
            if resultado_combinado["aplicavel"]:
                exibir_grafico(
                    _figura_valor_justo(
                        resultado_combinado["valores_por_metodo"],
                        resultado_combinado["valor_combinado"],
                        preco_atual,
                    )
                )
            else:
                st.info(
                    f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']} "
                    f"{TEXTO_COMPLEMENTO_SEM_METODO}"
                )
            # Método fora do gráfico: legenda com o motivo.
            for chave, resultado in metodos_painel:
                nome = ROTULOS_METODOS_GRAFICO[chave]
                if not resultado["aplicavel"]:
                    motivo = resultado["motivo_nao_aplicavel"].replace("$", "\\$")
                    st.caption(f"{nome} — Não aplicável: {motivo}")
                elif chave not in resultado_combinado["valores_por_metodo"]:
                    st.caption(f"{nome} — Valor indisponível.")

            razao_dividendos_bazin = resultado_bazin.get("razao_dividendos_12m_vs_mediana_5a")
            if (
                resultado_bazin["aplicavel"]
                and razao_dividendos_bazin is not None
                and razao_dividendos_bazin > RAZAO_DIVIDENDOS_ATIPICA_BAZIN
            ):
                st.caption(
                    "Dividendos dos últimos 12 meses em "
                    f"{razao_dividendos_bazin * 100:.0f}% da mediana dos 5 anos "
                    "anteriores. Pode ser crescimento real dos pagamentos ou um "
                    "pagamento extraordinário — a fonte não permite distinguir. "
                    "Se for extraordinário, o preço teto está inflado."
                )
            if resultado_fcd["aplicavel"]:
                aviso_fcd_extremo = avaliar_fcd_extremo(resultado_fcd, preco_atual)
                if aviso_fcd_extremo is not None:
                    st.warning(aviso_fcd_extremo["texto"].replace("$", "\\$"))
            notas_por_metodo = {
                chave: _notas_do_metodo(resultado)
                for chave, resultado in metodos_painel
                if resultado["aplicavel"]
            }
            for visiveis, _detalhes in notas_por_metodo.values():
                for nota in visiveis:
                    st.caption(nota)

            with st.expander("Métodos utilizados"):
                if resultado_combinado["aplicavel"]:
                    st.caption(
                        "Métodos utilizados: "
                        + _nomes_dos_metodos(resultado_combinado["metodos_utilizados"])
                    )
                    divergencia = divergencia_metodos
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
                for chave, (_visiveis, detalhes) in notas_por_metodo.items():
                    if detalhes:
                        st.markdown(f"**{ROTULOS_METODOS_GRAFICO[chave]}**")
                    for nota in detalhes:
                        st.caption(nota)
                if resultado_fcd["aplicavel"]:
                    # Só o FCD vem da DFP anual da CVM; "Saúde financeira" vem do Fundamentus
                    # (últimos 12 meses), sem relação com esse ano. Sem fallback, o ano já
                    # aparece em "Datas de referência dos dados usados".
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

            st.caption(
                "Os valores acima são calculados a partir de fórmulas de valuation "
                "públicas e conhecidas (Graham, Bazin, FCD) aplicadas aos dados "
                "reais da empresa — isto não é uma recomendação de compra ou "
                "venda, apenas uma referência de estudo."
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
                "custo de capital (WACC).\n\n"
                "*Taxa de desconto*\n\n"
                "O custo do capital próprio parte da Selic menos o spread de default "
                "do Brasil (que a Selic já embute) mais o Beta da ação vezes o prêmio "
                "de risco do país; o custo da dívida é a Selic mais 2 pontos "
                "percentuais.\n\n"
                "*Fluxo de caixa*\n\n"
                "O fluxo de caixa usado é o caixa gerado pela operação menos o que a "
                "empresa gastou em imobilizado e intangível (máquinas, obras, "
                "sistemas) no ano, mais os juros pagos sobre a dívida, já descontado "
                "o imposto: os juros voltam ao fluxo porque o custo da dívida já "
                "entra no custo de capital e na dedução da dívida líquida.\n\n"
                "Quando a empresa paga os fornecedores por um convênio com banco "
                "(risco sacado ou similar) e registra o pagamento ao banco no caixa "
                "de financiamento, esse valor é tratado como operacional, porque "
                "substitui o pagamento ao fornecedor; sem isso o caixa operacional "
                "pareceria maior do que a geração de caixa, e o cartão avisa quando "
                "o ajuste é aplicado.\n\n"
                "Ficam de fora as aplicações financeiras, a compra e venda de "
                "participações e de ativos e o pagamento de arrendamentos (aluguéis "
                "de longo prazo).\n\n"
                "*Crescimento*\n\n"
                "O crescimento do fluxo nos cinco anos projetados é medido entre o "
                "ano mais recente e cinco anos antes, limitado ao crescimento da "
                "receita líquida no mesmo período (um fluxo não cresce mais que a "
                "receita por cinco anos, o que assume margem constante) e à faixa "
                "de −20% a +30% ao ano; sem receita utilizável, vale o crescimento "
                "do fluxo, e o cartão diz o motivo. Esse crescimento converge "
                "gradualmente, ano a ano, para o de longo prazo (a inflação, IPCA) "
                "em vez de saltar no sexto ano. Quando o fluxo de cinco anos atrás "
                "não pode ser usado, o crescimento passa a ser a inflação (IPCA) e "
                "o cartão avisa.\n\n"
                "Por isso, empresas em fase de investimento pesado (comuns em "
                "energia e saneamento) ou com dívida muito alta tendem a ter FCD "
                "bem abaixo dos outros métodos, mesmo quando são saudáveis. Separar "
                "o investimento que só mantém a empresa do que a faz crescer "
                "exigiria um dado que a fonte não informa de forma padronizada. No "
                "cartão do FCD, a porcentagem reinvestida no ano aparece logo abaixo "
                "do valor.\n\n"
                "*Do valor da empresa ao valor por ação*\n\n"
                "Esse valor presente é o da empresa como um todo, dívida incluída — "
                "por isso a dívida líquida é deduzida antes de dividir pelo número "
                "de ações, chegando no valor que sobra pros acionistas; quando a "
                "dívida líquida não está disponível pra uma empresa, o cálculo usa "
                "o valor da empresa inteira como aproximação, sem deduzir nada, e "
                "mostra um aviso na tela.\n\n"
                f"{TEXTO_FCD_AJUSTES_DO_BALANCO}\n\n"
                "*Quando o FCD não se aplica*\n\n"
                "Não se aplica a bancos — a dívida e os depósitos são a própria "
                "operação do banco, não financiamento externo — nem a seguradoras "
                "e à Itaúsa, cujo caixa vem de prêmios e de dividendos de "
                "participações; nesses casos a lógica de custo de capital do FCD "
                "não tem interpretação econômica válida (Graham e Bazin continuam "
                "funcionando normalmente). Também não é calculado quando o caixa "
                "livre do último ano foi zero ou negativo: projetar um fluxo assim "
                "não estima valor. Se o gasto em imobilizado e intangível não puder "
                "ser identificado na demonstração da empresa, o FCD não é "
                "calculado, e o mesmo vale quando o fluxo do último ano é zero ou "
                "negativo.\n\n"
                "Fora esses casos, funciona mesmo para empresas sem lucro contábil "
                "no momento, já que olha geração de caixa, não resultado contábil "
                "passado.\n\n"
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

        with coluna_saude, st.container(border=True, key="painel_saude"):
            _titulo_painel("Saúde financeira", TEXTO_AJUDA_INDICADORES_AUSENTES)
            if indicadores is None:
                st.info("Indisponível — ver aviso do Fundamentus acima.")
            else:
                acoes_em_circulacao = ajustes_balanco["acoes_em_circulacao"]
                valores_mercado_firma = calcular_valor_mercado_e_firma(
                    preco_atual,
                    acoes_em_circulacao if acoes_em_circulacao is not None else numero_acoes,
                    divida_liquida,
                    ajustes_balanco["nao_controladores"],
                    ajustes_balanco["arrendamento_fora_da_divida"],
                )
                # Grade de 2 colunas: "R$ 618,7 bi" cabe sem cortar nas larguras de notebook.
                st.html(
                    '<div class="ab-grade">'
                    + _html_indicador(
                        "ROE",
                        _fmt(indicadores["roe_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["roe_percentual"], "sinal"),
                    )
                    + _html_indicador(
                        "Margem líquida",
                        _fmt(indicadores["margem_liquida_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["margem_liquida_percentual"], "sinal"),
                    )
                    + _html_indicador("LPA", _fmt(indicadores["lpa"], "R$ {:.2f}"))
                    + _html_indicador("VPA", _fmt(indicadores["vpa"], "R$ {:.2f}"))
                    + _html_indicador(
                        "Liquidez corrente",
                        _fmt(indicadores["liquidez_corrente"]),
                        _cor_indicador(indicadores["liquidez_corrente"], "liquidez"),
                    )
                    + _html_indicador(
                        "Dív. líq./patrim.", _fmt(indicadores["divida_liquida_sobre_patrimonio"])
                    )
                    + _html_indicador(
                        "Cresc. receita (5a)",
                        _fmt(indicadores["crescimento_receita_5a_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["crescimento_receita_5a_percentual"], "queda"),
                    )
                    + _html_indicador(
                        "Valor de mercado", _fmt_bilhoes(valores_mercado_firma["valor_mercado"])
                    )
                    + _html_indicador(
                        "Dívida líquida", _fmt_bilhoes(valores_mercado_firma["divida_liquida"])
                    )
                    + _html_indicador(
                        "Valor de firma",
                        _fmt_bilhoes(valores_mercado_firma["valor_firma"]),
                        ajuda=TOOLTIP_VALOR_FIRMA,
                    )
                    + "</div>"
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

        with st.container(border=True, key="painel_grafico_preco"):
            _titulo_painel("Preço vs. Ibovespa (1 ano, base 100)")
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
                    exibir_grafico(figura_preco)

        with coluna_saude, st.container(border=True, key="painel_governanca"):
            _titulo_painel("Governança")
            linha_universo = (
                universo_ibovespa[universo_ibovespa["ticker"] == ticker]
                if universo_ibovespa is not None
                else None
            )
            indicadores_governanca = []
            if erro_universo:
                st.warning(f"Segmento de listagem: {erro_universo}")
            elif linha_universo is not None and not linha_universo.empty:
                indicadores_governanca.append(
                    _html_indicador(
                        "Segmento de listagem", str(linha_universo.iloc[0]["segmento_listagem"])
                    )
                )
            else:
                indicadores_governanca.append(
                    _html_indicador(
                        "Segmento de listagem",
                        "—",
                        ajuda=(
                            f"{ticker!r} não está na carteira teórica atual do Ibovespa — essa é "
                            "a única fonte de segmento de listagem que já temos."
                        ),
                    )
                )
            indicadores_governanca.append(
                _html_indicador("Free float", "—", ajuda="Dado não disponível nas fontes usadas.")
            )
            st.html('<div class="ab-grade">' + "".join(indicadores_governanca) + "</div>")

        coluna_comportamento, coluna_correlacao = st.columns(2)
        with (
            coluna_comportamento,
            st.container(border=True, key="painel_comportamento", height="stretch"),
        ):
            _titulo_painel("Comportamento da ação")
            indicadores_comportamento = []
            if erro_historico:
                st.info("Volume/volatilidade indisponíveis — ver aviso de preço acima.")
            else:
                indicadores_comportamento += [
                    _html_indicador(
                        "Volume médio (3m)", _fmt(calcular_volume_medio(historico), "{:,.0f}")
                    ),
                    _html_indicador(
                        "Volatilidade anualizada",
                        _fmt(calcular_volatilidade_anualizada(historico), "{:.1%}"),
                    ),
                ]

            # Beta usa uma janela própria mais longa (PERIODO_BETA) que volume/volatilidade, de
            # propósito (ver config.py); reaproveita o `beta` já calculado para o WACC do FCD.
            motivo_beta = ""
            if erro_historico_beta:
                motivo_beta = f"Preço indisponível: {erro_historico_beta}"
            elif erro_historico_ibovespa_beta:
                motivo_beta = f"Ibovespa indisponível: {erro_historico_ibovespa_beta}"
            elif beta is None:
                motivo_beta = "Histórico curto demais pra calcular (poucas datas em comum)."
            indicadores_comportamento.append(
                _html_indicador(
                    "Beta (vs. Ibovespa, 1a)",
                    "—" if motivo_beta else _fmt(beta),
                    ajuda=motivo_beta,
                )
            )
            st.html('<div class="ab-grade">' + "".join(indicadores_comportamento) + "</div>")

        with (
            coluna_correlacao,
            st.container(border=True, key="painel_correlacao", height="stretch"),
        ):
            _titulo_painel(
                "Correlação com fatores externos",
                TEXTO_AJUDA_CORRELACAO.format(anos=ANOS_JANELA_CORRELACAO),
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

                ultimo_gpr = None
                if serie_gpr is not None and not serie_gpr.empty:
                    ultimo_gpr = TEXTO_ULTIMO_DADO_GPR.format(
                        data=_fmt_data(serie_gpr["data"].max())
                    )
                st.html(_html_correlacoes(resultados_correlacao, ultimo_gpr))

        with st.container(border=True, key="painel_petroleo"):
            _titulo_painel("Comparando com Petróleo (Brent) · base 100")
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
                        historico_acao_petroleo,
                        ticker,
                        historico_petroleo_janela,
                        "Petróleo (Brent)",
                    )
                    if figura_petroleo is None:
                        st.info(_mensagem_grafico_comparacao_sem_dados(nomes_sem_dados_petroleo))
                    else:
                        exibir_grafico(figura_petroleo)

        with st.container(border=True, key="painel_tradingview"):
            _titulo_painel("Gráfico avançado (TradingView)", TEXTO_AJUDA_TRADINGVIEW)
            html_tradingview = _widget_avancado_tradingview(ticker)
            if html_tradingview is None:
                st.info(MENSAGEM_TRADINGVIEW_TICKER_INVALIDO)
            else:
                st.iframe(html_tradingview.strip(), height=520)

        coluna_dividendos, coluna_comparacao_setorial = st.columns(2)
        with (
            coluna_dividendos,
            st.container(border=True, key="painel_dividendos", height="stretch"),
        ):
            if erro_dividendos:
                _titulo_painel(TITULO_PAINEL_DIVIDENDOS)
                st.info("Gráfico indisponível — ver aviso de dividendos acima.")
            else:
                ano_corrente = datetime.now().year
                # Reaproveita `dividendos` já buscado pro método de Bazin acima —
                # não busca dado novo.
                dividendos_por_ano = agregar_dividendos_por_ano(
                    dividendos, ano_corrente=ano_corrente
                )
                if dividendos_por_ano.empty:
                    _titulo_painel(TITULO_PAINEL_DIVIDENDOS)
                    st.info("Nenhum dividendo pago no histórico disponível.")
                else:
                    # period="max" porque o Dividend Yield por ano precisa do preço médio de
                    # TODOS os anos com dividendo pago. auto_adjust=False: preço NOMINAL da
                    # época, não ajustado por dividendos futuros (ver `_buscar_historico`).
                    historico_max, erro_historico_max = _buscar_historico(
                        ticker, "max", auto_adjust=False
                    )
                    dividend_yield_por_ano = calcular_dividend_yield_por_ano(
                        dividendos_por_ano,
                        historico_max
                        if not erro_historico_max
                        else pd.DataFrame(columns=["data", "Close"]),
                    )
                    notas = []
                    if dividendos_por_ano["parcial"].any():
                        notas.append(NOTA_DIVIDENDOS_ANO_PARCIAL.format(ano=ano_corrente))
                    if not dividend_yield_por_ano.empty:
                        notas.append(NOTA_DIVIDEND_YIELD_SUBESTIMADO)
                    _titulo_painel(TITULO_PAINEL_DIVIDENDOS, " ".join(notas) or None)

                    if not dividend_yield_por_ano.empty:
                        ano_inicial_janela = ano_corrente - ANOS_JANELA_DIVIDENDOS + 1
                        primeiro_ano = int(dividend_yield_por_ano["ano"].min())
                        rotulo_janela_curta = ROTULO_JANELA_DIVIDENDOS_CURTA.format(
                            anos=ANOS_JANELA_DIVIDENDOS
                        )
                        janela_dividendos = rotulo_janela_curta
                        # Com o histórico todo dentro da janela curta, não há o que escolher.
                        if primeiro_ano < ano_inicial_janela:
                            janela_dividendos = (
                                st.pills(
                                    "Janela do histórico",
                                    options=[
                                        rotulo_janela_curta,
                                        ROTULO_JANELA_DIVIDENDOS_COMPLETA.format(ano=primeiro_ano),
                                    ],
                                    default=rotulo_janela_curta,
                                    key="janela_dividendos",
                                )
                                or rotulo_janela_curta
                            )
                        exibir_grafico(
                            _figura_dividendos(
                                dividendos_por_ano,
                                dividend_yield_por_ano,
                                ano_inicial=(
                                    ano_inicial_janela
                                    if janela_dividendos == rotulo_janela_curta
                                    else None
                                ),
                            )
                        )

                    # Degradação transparente: yield ausente ou parcial não é erro, mas merece
                    # uma linha explicando o motivo.
                    if erro_historico_max:
                        st.caption(f"Dividend Yield indisponível: {erro_historico_max}")
                    elif dividend_yield_por_ano.empty:
                        st.caption(
                            "Dividend Yield indisponível — sem preço histórico "
                            "suficiente pros anos com dividendo pago."
                        )
                    elif len(dividend_yield_por_ano) < len(dividendos_por_ano):
                        st.caption(
                            "Dividend Yield mostrado só pros anos com preço "
                            "histórico disponível — ação listada há menos "
                            "tempo que o histórico de dividendos."
                        )

        with (
            coluna_comparacao_setorial,
            st.container(border=True, key="painel_comparacao_setorial", height="stretch"),
        ):
            _titulo_painel("Comparação setorial")
            # segmento_setorial/erro_segmento_setorial já buscados mais
            # acima (perto do cnpj, pro FCD) — reaproveitado aqui, sem
            # busca nova.
            if erro_segmento_setorial:
                st.warning(f"Classificação setorial: {erro_segmento_setorial}")
            else:
                tabela_screener_setor = _carregar_screener_ou_avisar(
                    CAMINHO_SAIDA_PADRAO,
                    'Rode o screener primeiro na página "Screener"',
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
                                f"Nenhuma outra ação do segmento setorial "
                                f"{_rotulo_segmento_setorial(segmento_setorial)!r} "
                                "encontrada no resultado salvo do screener."
                            )
                        else:
                            nome_segmento = _rotulo_segmento_setorial(segmento_setorial)
                            st.caption(f"Segmento setorial (B3): {nome_segmento}")
                            st.html(_html_tabela_setorial(tabela_pares, ticker))

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


def pagina_screener() -> None:
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
            "cálculo?' na página Analisar uma ação. A tabela vem ordenada do "
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

    rodar_screener_permitido = _rodar_screener_permitido()
    if not rodar_screener_permitido:
        st.info(_texto_screener_atualizado_pelo_workflow())

    if rodar_screener_permitido and st.button("Rodar screener agora"):
        st.warning(
            "Isso faz ~228 requisições reais (preço, dividendos e Beta de cada "
            "uma das ~76 ações, com delay entre chamadas) — leva de 5 a 15 "
            "minutos. Não feche esta página enquanto roda."
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
        if rodar_screener_permitido:
            atualizado_em = datetime.fromtimestamp(CAMINHO_SAIDA_PADRAO.stat().st_mtime)
            st.caption(
                f"Última atualização: {atualizado_em.strftime('%d/%m/%Y %H:%M')} — "
                "dado salvo em disco, não ao vivo. Use o botão acima pra atualizar."
            )

        macro_referencia = carregar_macro_referencia()
        with st.container(border=True, key="painel_destaque_screener"):
            col_universo, col_fcd, col_mediana, col_selic, col_data = st.columns(5)
            col_universo.metric("Ações no universo", len(tabela_screener))
            col_fcd.metric("Ações com FCD", int(tabela_screener["fcd_valor_justo"].notna().sum()))
            col_mediana.metric(
                "Mediana do potencial",
                _fmt_percentual(tabela_screener["desconto_percentual"].median()),
                help=TOOLTIP_POTENCIAL_COLUNA,
            )
            selic = macro_referencia.get("selic_meta") if macro_referencia else None
            col_selic.metric("Selic", "N/D" if selic is None else _fmt_percentual(selic * 100, 2))
            data_busca = macro_referencia.get("data_busca") if macro_referencia else None
            col_data.metric("Atualizado em", _fmt_data(data_busca))

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
        tabela_screener_fmt["metodos_utilizados"] = tabela_screener_fmt["metodos_utilizados"].map(
            _nomes_dos_metodos_do_csv
        )
        with st.container(border=True, key="painel_tabela_screener"):
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
                width="stretch",
            )


def pagina_carteira() -> None:
    st.caption(TEXTO_ABERTURA_SIMULADOR)

    tabela_screener_carteira = _carregar_screener_ou_avisar(
        CAMINHO_SAIDA_PADRAO,
        'Rode o screener primeiro na página "Screener"',
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
                    width="stretch",
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


def _rodape_da_barra_lateral() -> None:
    """Data da última atualização do screener (a `data_busca` do arquivo de referência, a mesma
    do cartão "Atualizado em") e o link do repositório."""
    macro = carregar_macro_referencia()
    with st.sidebar.container(key=CHAVE_BARRA_RODAPE):
        if macro is not None:
            st.caption(TEXTO_RODAPE_SCREENER_ATUALIZADO.format(data=_fmt_data(macro["data_busca"])))
        st.markdown(f"[{TEXTO_RODAPE_LINK_REPOSITORIO}]({URL_REPOSITORIO})")


_paginas = {
    CHAVE_BARRA_ANALISAR: st.Page(
        pagina_analisar,
        title=TITULO_PAGINA_ANALISAR,
        icon=ICONE_PAGINA_ANALISAR,
        url_path=URL_PAGINA_ANALISAR,
        default=True,
    ),
    CHAVE_BARRA_SCREENER: st.Page(
        pagina_screener,
        title=TITULO_PAGINA_SCREENER,
        icon=ICONE_PAGINA_SCREENER,
        url_path=URL_PAGINA_SCREENER,
    ),
    CHAVE_BARRA_CARTEIRA: st.Page(
        pagina_carteira,
        title=TITULO_PAGINA_CARTEIRA,
        icon=ICONE_PAGINA_CARTEIRA,
        url_path=URL_PAGINA_CARTEIRA,
    ),
}
_ROTULOS_DO_MENU = [
    (TITULO_PAGINA_ANALISAR, ICONE_PAGINA_ANALISAR),
    (TITULO_PAGINA_SCREENER, ICONE_PAGINA_SCREENER),
    (TITULO_PAGINA_CARTEIRA, ICONE_PAGINA_CARTEIRA),
]
# Menu próprio (um bloco por página), no lugar do menu padrão do Streamlit.
pagina_atual = st.navigation(list(_paginas.values()), position="hidden")
_blocos_barra: dict[str, DeltaGenerator] = {}
for (_chave, _pagina), (_titulo, _icone) in zip(_paginas.items(), _ROTULOS_DO_MENU, strict=True):
    _ativa = _pagina is pagina_atual
    _blocos_barra[_chave] = st.sidebar.container(
        border=True, key=_chave + (SUFIXO_BARRA_ATIVA if _ativa else "")
    )
    with _blocos_barra[_chave]:
        st.page_link(_pagina, label=_titulo, icon=_icone)
# A caixa da ação e o Buscar entram no bloco da análise, só quando a página de análise roda.
_bloco_barra_analisar = _blocos_barra[CHAVE_BARRA_ANALISAR]
pagina_atual.run()
_rodape_da_barra_lateral()

st.caption(
    'Hospedado no Streamlit Community Cloud — se o app estiver "dormindo", '
    "vai aparecer uma tela pedindo um clique pra acordar; depois disso, "
    "leva cerca de 1 minuto pra carregar."
)
