"""Protótipo mínimo do dashboard (Streamlit) — teste de integração visual,
não a versão final. Só chama os adapters/modelos que já existem e organiza
o resultado na tela; nenhuma lógica de cálculo é reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import sys
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
    calcular_cagr_implicito,
    calcular_ganho_nominal_vs_real,
    calcular_totais_carteira,
    montar_tabela_carteira,
)
from avaliador_b3.config import (
    ANO_REFERENCIA_FCD,
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    ANOS_JANELA_CORRELACAO,
    HORIZONTE_PROJECAO_FCD_ANOS,
    JANELA_MONITOR_CONFLITOS_HORAS,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    PERIODO_PRECO_ATUAL,
    SERIES_BCB_SGS,
    TICKER_PETROLEO_BRENT,
)
from avaliador_b3.conflitos import CAMINHO_SAIDA_PADRAO as CAMINHO_SAIDA_CONFLITOS_PADRAO
from avaliador_b3.conflitos import (
    carregar_eventos_conflito_salvos,
    descrever_paises_monitorados,
    rodar_monitor_conflitos,
)
from avaliador_b3.correlacao import calcular_correlacoes_fatores, classificar_magnitude_correlacao
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
from avaliador_b3.graficos import (
    agregar_dividendos_por_ano,
    calcular_dividend_yield_por_ano,
    montar_mapa_conflitos,
    normalizar_base_100,
    projetar_curva_composta,
    projetar_curva_inflacao,
    projetar_curva_linear,
)
from avaliador_b3.ingest.b3_universo import obter_universo_ibovespa
from avaliador_b3.ingest.bcb_sgs import obter_serie
from avaliador_b3.ingest.crosswalk_cnpj import (
    EmissorNaoEncontrado,
    obter_catalogo_emissores,
    resolver_cnpj,
    resolver_segmentos_setoriais,
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
from avaliador_b3.ingest.gpr import obter_gpr
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
from avaliador_b3.screener import CAMINHO_SAIDA_PADRAO, rodar_screener

COLUNAS_TABELA_SCREENER = [
    "ticker",
    "preco_atual",
    "valor_combinado",
    "desconto_percentual",
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
    `ingest.precos.obter_historico`."""
    try:
        return obter_historico(ticker, periodo=periodo, auto_adjust=auto_adjust), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


def _buscar_historico_ibovespa(periodo: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return obter_historico_ibovespa(periodo=periodo), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


@st.cache_data(ttl=3600)
def _buscar_historico_petroleo() -> tuple[pd.DataFrame | None, str | None]:
    """Histórico do petróleo Brent (BZ=F) na janela de correlação —
    cacheado na sessão por 1h, não depende da ação buscada (mesmo padrão
    de _buscar_universo_ibovespa/_buscar_macro)."""
    return _buscar_historico(TICKER_PETROLEO_BRENT, periodo=f"{ANOS_JANELA_CORRELACAO}y")


@st.cache_data(ttl=3600)
def _buscar_cambio_correlacao() -> tuple[pd.DataFrame | None, str | None]:
    """Série de câmbio USD/BRL (PTAX venda) na janela de correlação —
    cacheada na sessão por 1h, não depende da ação buscada."""
    hoje = datetime.now()
    try:
        serie = obter_serie(
            SERIES_BCB_SGS["cambio_usd_venda"],
            data_inicial=(hoje - timedelta(days=365 * ANOS_JANELA_CORRELACAO)).strftime("%d/%m/%Y"),
            data_final=hoje.strftime("%d/%m/%Y"),
        )
        return serie, None
    except Exception as erro:
        return None, f"Falha ao buscar câmbio USD/BRL do Banco Central: {erro}"


@st.cache_data(ttl=3600)
def _buscar_gpr_diaria() -> tuple[pd.DataFrame | None, str | None]:
    """Série diária do índice GPR — cacheada na sessão por 1h, não
    depende da ação buscada. `obter_gpr` já cacheia em disco sem TTL por
    baixo (o arquivo raramente muda), isso só evita reler/reparsear o CSV
    a cada busca dentro da mesma sessão do Streamlit."""
    try:
        return obter_gpr(serie="diaria"), None
    except Exception as erro:
        return None, f"Falha ao buscar índice GPR: {erro}"


@st.cache_data(ttl=3600)
def _buscar_universo_ibovespa() -> tuple[pd.DataFrame | None, str | None]:
    """Universo do Ibovespa (ticker/nome/segmento de listagem/peso) —
    cacheado na sessão do Streamlit, não depende do ticker buscado. Um
    ticker fora do Ibovespa simplesmente não aparece nesse universo — não
    é um erro de busca."""
    try:
        return obter_universo_ibovespa(), None
    except Exception as erro:
        return None, f"Falha ao buscar universo do Ibovespa: {erro}"


def _buscar_indicadores_fundamentus(ticker: str) -> tuple[dict | None, str | None]:
    try:
        return obter_indicadores(ticker), None
    except (TickerNaoEncontrado, EstruturaPaginaMudou) as erro:
        return None, str(erro)


def _buscar_dividendos(ticker: str):
    try:
        return obter_dividendos(ticker), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


def _buscar_cnpj(ticker: str) -> tuple[str | None, str | None]:
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


def _buscar_fcf(cnpj: str, ano: int) -> tuple[float | None, str | None]:
    try:
        return obter_fluxo_caixa_livre(cnpj, ano)["fcf_atual"], None
    except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada) as erro:
        return None, str(erro)
    except Exception as erro:  # zip da CVM indisponível pra esse ano, erro de rede, etc.
        return None, f"Falha ao buscar dados da CVM para {ano}: {erro}"


@st.cache_data(ttl=3600)
def _buscar_macro() -> tuple[float | None, float | None, str | None]:
    """Selic meta (decimal) e IPCA acumulado 12 meses (decimal). Cacheado
    na sessão do Streamlit por 1h — não depende do ticker buscado."""
    hoje = datetime.now()
    try:
        selic_df = obter_serie(
            SERIES_BCB_SGS["selic_meta"],
            data_inicial=(hoje - timedelta(days=90)).strftime("%d/%m/%Y"),
            data_final=hoje.strftime("%d/%m/%Y"),
        )
        selic_meta = float(selic_df.iloc[-1]["valor"]) / 100

        ipca_df = obter_serie(
            SERIES_BCB_SGS["ipca_mensal"],
            data_inicial=(hoje - timedelta(days=730)).strftime("%d/%m/%Y"),
            data_final=hoje.strftime("%d/%m/%Y"),
        )
        ipca_12m = (1 + ipca_df["valor"].tail(12) / 100).prod() - 1
        return selic_meta, ipca_12m, None
    except Exception as erro:
        return None, None, f"Falha ao buscar Selic/IPCA do Banco Central: {erro}"


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
    return f"{(valor - preco_atual) / preco_atual * 100:.1f}%"


def _cartao_metodo(nome: str, resultado: dict, rotulo_valor: str, preco_atual: float | None):
    if resultado["aplicavel"]:
        st.metric(
            nome,
            f"R$ {resultado[rotulo_valor]:.2f}",
            delta=_delta_percentual_upside(resultado[rotulo_valor], preco_atual),
        )
        st.caption("Aplicável")
    else:
        st.metric(nome, "—")
        st.caption(f"Não aplicável: {resultado['motivo_nao_aplicavel']}")


def _cartao_correlacao(nome: str, resultado: dict):
    if not resultado["aplicavel"]:
        st.metric(nome, "—")
        st.caption(f"Indisponível: {resultado['motivo_nao_aplicavel']}")
        return

    magnitude = classificar_magnitude_correlacao(resultado["correlacao"])
    st.metric(nome, f"{resultado['correlacao']:.2f}")
    st.caption(f"Correlação {magnitude} ({resultado['observacoes']} observações)")


def _fmt(valor: float | None, template: str = "{:.2f}") -> str:
    """Formata um número, ou "N/D" se ausente — indicador individual
    faltando (ex: banco sem Dív Líq/Patrim no Fundamentus) não deve
    quebrar a tela nem virar um "None" cru na tela."""
    return template.format(valor) if valor is not None else "N/D"


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
    de Screener, Simulador de carteira e Monitor de conflitos — cada uma
    só varia a instrução de como gerar o arquivo (cada uma tem seu
    próprio botão hoje: "Rodar screener agora" ou "Buscar eventos
    agora")."""
    st.info(
        "Nenhum resultado salvo ainda (primeira vez rodando o projeto). "
        f"{instrucao} — vai demorar alguns minutos."
    )


ABA_ANALISAR = "Analisar uma ação"
ABA_SCREENER = "Screener (todas as ações)"
ABA_CARTEIRA = "Simulador de carteira"
ABA_CONFLITOS = "Monitor de conflitos"

# Ticker pré-selecionado e buscado automaticamente só na primeira abertura da
# sessão (ver `busca_inicial_automatica_feita` em session_state, mais abaixo)
# — mostra um resultado de exemplo de cara, sem exigir clique em "Buscar".
TICKER_PADRAO_PRIMEIRA_ABERTURA = "PETR4"

st.set_page_config(page_title="Avaliador B3 (protótipo)", page_icon="📈", layout="wide")
st.title("Avaliador de Ações da B3")
st.caption(
    "Protótipo mínimo — teste de integração visual dos adapters e modelos já "
    "implementados, não a versão final do dashboard."
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
aba_analisar, aba_screener, aba_carteira, aba_conflitos = st.tabs(
    [ABA_ANALISAR, ABA_SCREENER, ABA_CARTEIRA, ABA_CONFLITOS],
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
        with st.spinner(f"Buscando dados de {ticker}..."):
            historico, erro_historico = _buscar_historico(ticker, PERIODO_HISTORICO_COMPORTAMENTO)
            # Busca separada (não reaproveita `historico`) só pro card "Preço
            # atual": o endpoint de histórico diário do yfinance (o mesmo por
            # trás de PERIODO_HISTORICO_COMPORTAMENTO) atrasa um pregão
            # inteiro, mesmo já encerrado — period="1d" traz o fechamento
            # mais recente disponível de verdade. Ver o comentário em
            # config.py com a investigação completa (discrepância real
            # encontrada contra o TradingView).
            historico_preco_atual, erro_preco_atual = _buscar_historico(
                ticker, PERIODO_PRECO_ATUAL
            )
            historico_beta, erro_historico_beta = _buscar_historico(ticker, PERIODO_BETA)
            historico_ibovespa_beta, erro_historico_ibovespa_beta = _buscar_historico_ibovespa(
                PERIODO_BETA
            )
            indicadores, erro_indicadores = _buscar_indicadores_fundamentus(ticker)
            dividendos, erro_dividendos = _buscar_dividendos(ticker)
            cnpj, erro_cnpj = _buscar_cnpj(ticker)
            selic_meta, ipca_12m, erro_macro = _buscar_macro()
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
            # "não aplicável" do próprio card do FCD.
            fcf_atual = fcf_ha_n_anos = None
            if cnpj:
                ano_anterior = ANO_REFERENCIA_FCD - ANOS_HISTORICO_CRESCIMENTO_FCD
                fcf_atual, _ = _buscar_fcf(cnpj, ANO_REFERENCIA_FCD)
                fcf_ha_n_anos, _ = _buscar_fcf(cnpj, ano_anterior)

        st.subheader(ticker)

        if erro_preco_atual:
            st.error(f"Preço: {erro_preco_atual}")
            preco_atual = None
        else:
            preco_atual = float(historico_preco_atual["Close"].iloc[-1])
            st.metric("Preço atual", f"R$ {preco_atual:.2f}")

        if erro_indicadores:
            st.warning(f"Fundamentus: {erro_indicadores}")
        if erro_dividendos:
            st.warning(f"Dividendos: {erro_dividendos}")
        if erro_cnpj:
            st.warning(f"CNPJ (CVM): {erro_cnpj}")
        if erro_macro:
            st.warning(erro_macro)

        lpa = indicadores["lpa"] if indicadores else None
        vpa = indicadores["vpa"] if indicadores else None
        numero_acoes = indicadores["numero_acoes"] if indicadores else None
        divida_liquida_sobre_patrimonio = (
            indicadores["divida_liquida_sobre_patrimonio"] if indicadores else None
        )

        # Beta real (janela de 1 ano, calculada uma vez e reaproveitada no WACC
        # do FCD e no card de "Comportamento da ação" abaixo). None quando não
        # calculável — calcular_wacc cai pro BETA_PADRAO sozinho nesse caso,
        # não é tratado aqui.
        beta = None
        if not erro_historico_beta and not erro_historico_ibovespa_beta:
            beta = calcular_beta(historico_beta, historico_ibovespa_beta)

        resultado_graham = calcular_valor_justo_graham(lpa, vpa)
        resultado_bazin = (
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
                "motivo_nao_aplicavel": erro_macro or "Selic/IPCA indisponíveis.",
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
        with coluna_fcd:
            _cartao_metodo("FCD", resultado_fcd, "valor_justo", preco_atual)
            if resultado_fcd["aplicavel"]:
                origem_beta = "calculado, 1a" if beta is not None else "padrão, sem histórico"
                st.caption(f"Beta no WACC: {resultado_fcd['beta_utilizado']:.2f} ({origem_beta})")
        with coluna_combinado:
            if resultado_combinado["aplicavel"]:
                st.metric(
                    "Valor combinado",
                    f"R$ {resultado_combinado['valor_combinado']:.2f}",
                    delta=_delta_percentual_upside(
                        resultado_combinado["valor_combinado"], preco_atual
                    ),
                )
                st.caption(
                    "Métodos utilizados: " + ", ".join(resultado_combinado["metodos_utilizados"])
                )
            else:
                st.error(f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']}")

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
                "dividendos: calcula o preço máximo que garantiria um retorno de 6% ao "
                "ano só em dividendos, baseado no histórico de pagamento da empresa. Só "
                "se aplica a quem tem histórico consistente de dividendo.\n\n"
                "**FCD (Fluxo de Caixa Descontado)** — projeta os fluxos de caixa "
                "futuros da empresa e traz isso a valor presente, descontando pelo "
                "custo de capital (WACC). É o único dos três que funciona mesmo para "
                "empresas sem lucro no momento, já que olha geração de caixa futura, "
                "não resultado contábil passado.\n\n"
                "**Valor combinado** — média simples apenas dos métodos que se aplicam "
                "à empresa específica analisada, nunca uma média forçada dos três. Se "
                "só um método for aplicável, o combinado é igual a esse método sozinho.\n\n"
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
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.metric("ROE", _fmt(indicadores["roe_percentual"], "{:.1f}%"))
                col_b.metric(
                    "Margem líquida", _fmt(indicadores["margem_liquida_percentual"], "{:.1f}%")
                )
                col_c.metric("LPA", _fmt(indicadores["lpa"], "R$ {:.2f}"))
                col_d.metric("VPA", _fmt(indicadores["vpa"], "R$ {:.2f}"))
                col_e, col_f, col_g, _col_h = st.columns(4)
                col_e.metric("Liquidez corrente", _fmt(indicadores["liquidez_corrente"]))
                col_f.metric(
                    "Dív. líq./patrim.", _fmt(indicadores["divida_liquida_sobre_patrimonio"])
                )
                col_g.metric(
                    "Cresc. receita (5a)",
                    _fmt(indicadores["crescimento_receita_5a_percentual"], "{:.1f}%"),
                )
                st.caption(
                    "Indicadores individuais ausentes (\"N/D\") — comum em bancos, onde o "
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
                    st.metric(
                        "Segmento de listagem", linha_universo.iloc[0]["segmento_listagem"]
                    )
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
                st.metric("Volume médio (3m)", f"{volume_medio:,.0f}".replace(",", "."))
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
                figura_preco = go.Figure()
                figura_preco.add_trace(
                    go.Scatter(
                        x=historico_beta["data"],
                        y=normalizar_base_100(historico_beta["Close"]),
                        name=ticker,
                    )
                )
                figura_preco.add_trace(
                    go.Scatter(
                        x=historico_ibovespa_beta["data"],
                        y=normalizar_base_100(historico_ibovespa_beta["Close"]),
                        name="Ibovespa",
                    )
                )
                figura_preco.update_layout(
                    yaxis_title="Desempenho (base 100 no início do período)",
                    xaxis_title="Data",
                    hovermode="x unified",
                    margin={"t": 20},
                )
                st.plotly_chart(figura_preco, use_container_width=True)

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
                    figura_dividendos.add_trace(
                        go.Bar(
                            x=dividendos_por_ano["ano"],
                            y=dividendos_por_ano["total"],
                            name="Dividendos",
                            text=dividendos_por_ano["total"],
                            texttemplate="R$ %{text:.2f}",
                            textposition="outside",
                            hovertemplate="R$ %{y:.2f}<extra></extra>",
                        )
                    )
                    if not dividend_yield_por_ano.empty:
                        figura_dividendos.add_trace(
                            go.Scatter(
                                x=dividend_yield_por_ano["ano"],
                                y=dividend_yield_por_ano["yield_percentual"],
                                name="Dividend Yield",
                                mode="lines+markers+text",
                                text=dividend_yield_por_ano["yield_percentual"],
                                texttemplate="%{text:.1f}%",
                                textposition="top center",
                                yaxis="y2",
                                hovertemplate="%{y:.1f}%<extra></extra>",
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
                    )
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
            segmento_setorial, erro_segmento_setorial = _buscar_segmento_setorial(ticker)
            tabela_screener_setor = _carregar_screener_salvo(CAMINHO_SAIDA_PADRAO)
            if erro_segmento_setorial:
                st.warning(f"Classificação setorial: {erro_segmento_setorial}")
            elif tabela_screener_setor is None:
                _aviso_screener_vazio(
                    'Rode o screener primeiro na aba "Screener (todas as ações)"'
                )
            else:
                try:
                    catalogo_setorial = obter_catalogo_emissores()
                except Exception as erro:
                    st.warning(f"Catálogo de emissores da B3: {erro}")
                else:
                    # Resolve o segmento setorial de cada ticker do screener já
                    # salvo (dado local, sem nova busca de rede além do catálogo
                    # já cacheado) pra achar os pares do mesmo setor da ação
                    # buscada. Os números da tabela (preço, valor combinado,
                    # desconto) vêm direto do screener — não são recalculados.
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
                        st.dataframe(
                            tabela_pares,
                            column_order=[
                                "ticker",
                                "preco_atual",
                                "valor_combinado",
                                "desconto_percentual",
                            ],
                            column_config={
                                "ticker": "Ticker",
                                "preco_atual": st.column_config.NumberColumn(
                                    "Preço atual", format="R$ %.2f"
                                ),
                                "valor_combinado": st.column_config.NumberColumn(
                                    "Valor combinado", format="R$ %.2f"
                                ),
                                "desconto_percentual": st.column_config.NumberColumn(
                                    "Desconto", format="%.1f%%"
                                ),
                            },
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

with aba_screener:
    st.caption(
        "Ranking de todas as ações do Ibovespa por desconto em relação ao "
        "valor combinado — Graham, Bazin e FCD, conforme aplicável a cada ação."
    )

    if st.button("Rodar screener agora", on_click=_ativar_aba, args=(ABA_SCREENER,)):
        st.warning(
            "Isso faz ~228 requisições reais (preço, dividendos e Beta de cada "
            "uma das ~76 ações, com delay entre chamadas) — leva de 5 a 15 "
            "minutos. Não feche esta aba enquanto roda."
        )
        with st.spinner("Rodando o screener — isso leva alguns minutos..."):
            rodar_screener()
        st.success("Screener concluído — resultado salvo em disco.")
        st.rerun()

    tabela_screener = _carregar_screener_salvo(CAMINHO_SAIDA_PADRAO)

    if tabela_screener is None:
        _aviso_screener_vazio(
            f'Clique em "Rodar screener agora" acima pra gerar {CAMINHO_SAIDA_PADRAO.name}'
        )
    else:
        atualizado_em = datetime.fromtimestamp(CAMINHO_SAIDA_PADRAO.stat().st_mtime)
        st.caption(
            f"Última atualização: {atualizado_em.strftime('%d/%m/%Y %H:%M')} — "
            "dado salvo em disco, não ao vivo. Use o botão acima pra atualizar."
        )

        linhas_com_aviso = (tabela_screener["aviso_desconto_extremo"] != "").sum()
        if linhas_com_aviso:
            st.warning(
                f"{linhas_com_aviso} ação(ões) com desconto extremo — ver "
                "coluna \"aviso_desconto_extremo\" na tabela, provavelmente "
                "reflete sensibilidade do modelo de FCD, não necessariamente "
                "uma oportunidade real."
            )

        st.dataframe(
            tabela_screener,
            column_order=COLUNAS_TABELA_SCREENER,
            column_config={
                "ticker": "Ticker",
                "preco_atual": st.column_config.NumberColumn("Preço atual", format="R$ %.2f"),
                "valor_combinado": st.column_config.NumberColumn(
                    "Valor combinado", format="R$ %.2f"
                ),
                "desconto_percentual": st.column_config.NumberColumn(
                    "Desconto", format="%.1f%%"
                ),
                "metodos_utilizados": "Métodos utilizados",
                "aviso_desconto_extremo": "Aviso",
                "erro": "Erro",
            },
            hide_index=True,
            use_container_width=True,
        )

with aba_carteira:
    st.caption(
        "Projeta quanto cada cenário (pessimista/base/otimista) renderia pro "
        "valor investido em cada ação — a partir do resultado já salvo do "
        "screener, sem recalcular nada ao vivo."
    )

    tabela_screener_carteira = _carregar_screener_salvo(CAMINHO_SAIDA_PADRAO)

    if tabela_screener_carteira is None:
        _aviso_screener_vazio(
            'Rode o screener primeiro na aba "Screener (todas as ações)"'
        )
    else:
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
                    f"{linha_sem_cenario['ticker']}: R$ {linha_sem_cenario['valor_investido']:.2f} "
                    f"investidos, mas sem cenário — {linha_sem_cenario['motivo_nao_aplicavel']}"
                )

            tabela_carteira_aplicavel = tabela_carteira[tabela_carteira["aplicavel"]]
            if not tabela_carteira_aplicavel.empty:
                st.dataframe(
                    tabela_carteira_aplicavel,
                    column_order=COLUNAS_TABELA_CARTEIRA,
                    column_config={
                        "ticker": "Ticker",
                        "valor_investido": st.column_config.NumberColumn(
                            "Investido", format="R$ %.2f"
                        ),
                        "preco_atual": st.column_config.NumberColumn(
                            "Preço atual", format="R$ %.2f"
                        ),
                        "projecao_pessimista": st.column_config.NumberColumn(
                            "Pessimista (R$)", format="R$ %.2f"
                        ),
                        "retorno_pessimista_percentual": st.column_config.NumberColumn(
                            "Pessimista (%)", format="%.1f%%"
                        ),
                        "projecao_base": st.column_config.NumberColumn(
                            "Base (R$)", format="R$ %.2f"
                        ),
                        "retorno_base_percentual": st.column_config.NumberColumn(
                            "Base (%)", format="%.1f%%"
                        ),
                        "projecao_otimista": st.column_config.NumberColumn(
                            "Otimista (R$)", format="R$ %.2f"
                        ),
                        "retorno_otimista_percentual": st.column_config.NumberColumn(
                            "Otimista (%)", format="%.1f%%"
                        ),
                    },
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
                col_investido.metric("Investido", f"R$ {totais_carteira['soma_investida']:.2f}")
                col_pessimista.metric(
                    "Pessimista", f"R$ {totais_carteira['total_pessimista']:.2f}"
                )
                col_base.metric("Base", f"R$ {totais_carteira['total_base']:.2f}")
                col_otimista.metric("Otimista", f"R$ {totais_carteira['total_otimista']:.2f}")
                if totais_carteira["quantidade_sem_cenario"]:
                    st.caption(
                        f"{totais_carteira['quantidade_sem_cenario']} ação(ões) sem cenário "
                        "não entram nos totais projetados, mas o valor investido nelas está "
                        "incluído em \"Investido\"."
                    )

                st.divider()
                st.subheader("Projeção de crescimento")
                st.caption(
                    "Projeção baseada nos modelos de valor justo do próprio projeto "
                    "(Graham/Bazin/FCD) — não é garantia nem previsão de mercado."
                )

                n_anos = HORIZONTE_PROJECAO_FCD_ANOS
                soma_investida = totais_carteira["soma_investida"]
                valor_por_cenario = {
                    "pessimista": totais_carteira["total_pessimista"],
                    "base": totais_carteira["total_base"],
                    "otimista": totais_carteira["total_otimista"],
                }
                cagr_por_cenario = {
                    cenario: calcular_cagr_implicito(soma_investida, valor, n_anos)
                    for cenario, valor in valor_por_cenario.items()
                }
                ROTULO_CENARIO = {
                    "pessimista": "Pessimista",
                    "base": "Base",
                    "otimista": "Otimista",
                }

                # "\$" (não "$" cru): st.write renderiza markdown, e "$...$"
                # vira LaTeX — com 3 "R$" na mesma frase, os dois primeiros
                # formam um par e o Streamlit tenta renderizar o trecho entre
                # eles como fórmula matemática. Bug real encontrado testando
                # essa frase no navegador.
                st.write(
                    f"R\\$ {soma_investida:.2f} investidos hoje podem valer entre "
                    f"R\\$ {valor_por_cenario['pessimista']:.2f} (pessimista) e "
                    f"R\\$ {valor_por_cenario['otimista']:.2f} (otimista) em {n_anos} anos."
                )
                for cenario, rotulo in ROTULO_CENARIO.items():
                    cagr = cagr_por_cenario[cenario]
                    if cagr is not None:
                        st.caption(f"{rotulo}: equivale a {cagr * 100:.1f}% ao ano.")
                    else:
                        # Cenário com valor projetado não positivo (possível com
                        # FCD muito sensível numa ação específica) não tem taxa
                        # composta real — ver docstring de calcular_cagr_implicito.
                        st.caption(
                            f"{rotulo}: sem taxa composta real (valor projetado "
                            "não positivo)."
                        )

                with st.expander("Como funciona essa projeção?"):
                    st.markdown(
                        "Os valores pessimista, base e otimista vêm dos mesmos três "
                        "cenários calculados para cada ação (o menor, a média, e o "
                        "maior entre os métodos de valor justo aplicáveis — Graham, "
                        "Bazin e FCD). A partir do valor investido hoje e do valor de "
                        "cada cenário, calculamos a taxa de crescimento anual que "
                        f"levaria de um até o outro em {n_anos} anos — essa é a curva "
                        "'Com juros compostos'. A versão 'Sem juros compostos' "
                        "distribui o mesmo crescimento total do período de forma "
                        "linear, ano a ano, só para comparação visual. A linha de "
                        "inflação projeta o mesmo valor investido corrigido pelo IPCA "
                        "dos últimos 12 meses, mantido constante — não é uma previsão "
                        "de inflação futura, é uma suposição de referência."
                    )

                # IPCA já é buscado (e cacheado por 1h) na aba "Analisar uma
                # ação" pro WACC do FCD — reaproveita a mesma busca aqui, não
                # dispara nada novo se já tiver rodado nessa sessão.
                _, ipca_12m_carteira, erro_macro_carteira = _buscar_macro()

                SELECAO_JUROS_COMPOSTOS = "Com juros compostos"
                SELECAO_LINEAR = "Sem juros compostos (linear)"
                SELECAO_INFLACAO = "Inflação (IPCA)"
                CORES_CENARIO = {
                    "pessimista": "#EF553B",
                    "base": "#636EFA",
                    "otimista": "#00CC96",
                }

                opcoes_selecionadas = (
                    st.pills(
                        "Mostrar no gráfico",
                        options=[SELECAO_JUROS_COMPOSTOS, SELECAO_LINEAR, SELECAO_INFLACAO],
                        selection_mode="multi",
                        default=[SELECAO_JUROS_COMPOSTOS],
                    )
                    or []
                )

                if not opcoes_selecionadas:
                    st.info("Selecione ao menos uma opção acima pra ver o gráfico.")
                else:
                    fig_projecao = go.Figure()

                    if SELECAO_JUROS_COMPOSTOS in opcoes_selecionadas:
                        for cenario, rotulo in ROTULO_CENARIO.items():
                            cagr = cagr_por_cenario[cenario]
                            if cagr is None:
                                continue
                            curva = projetar_curva_composta(soma_investida, cagr, n_anos)
                            fig_projecao.add_trace(
                                go.Scatter(
                                    x=curva["ano"],
                                    y=curva["valor"],
                                    mode="lines",
                                    name=f"{rotulo} (composto)",
                                    line={"color": CORES_CENARIO[cenario]},
                                    hovertemplate="R$ %{y:.2f}<extra></extra>",
                                )
                            )

                    if SELECAO_LINEAR in opcoes_selecionadas:
                        for cenario, rotulo in ROTULO_CENARIO.items():
                            curva = projetar_curva_linear(
                                soma_investida, valor_por_cenario[cenario], n_anos
                            )
                            fig_projecao.add_trace(
                                go.Scatter(
                                    x=curva["ano"],
                                    y=curva["valor"],
                                    mode="lines",
                                    name=f"{rotulo} (linear)",
                                    line={"color": CORES_CENARIO[cenario], "dash": "dash"},
                                    hovertemplate="R$ %{y:.2f}<extra></extra>",
                                )
                            )

                    if SELECAO_INFLACAO in opcoes_selecionadas:
                        if ipca_12m_carteira is None:
                            st.caption(f"Inflação (IPCA) indisponível: {erro_macro_carteira}")
                        else:
                            curva_ipca = projetar_curva_inflacao(
                                soma_investida, ipca_12m_carteira, n_anos
                            )
                            fig_projecao.add_trace(
                                go.Scatter(
                                    x=curva_ipca["ano"],
                                    y=curva_ipca["valor"],
                                    mode="lines",
                                    name="Inflação (IPCA, suposição constante)",
                                    line={"color": "#00d4ff", "dash": "dot"},
                                    hovertemplate="R$ %{y:.2f}<extra></extra>",
                                )
                            )

                    if fig_projecao.data:
                        fig_projecao.update_layout(
                            xaxis_title="Anos",
                            yaxis_title="Valor projetado (R$)",
                            hovermode="x unified",
                            margin={"t": 20},
                        )
                        st.plotly_chart(fig_projecao, use_container_width=True)
                    else:
                        st.info(
                            "Nada pra mostrar — os cenários selecionados não têm dado "
                            "disponível (ver avisos acima)."
                        )

                if ipca_12m_carteira is None:
                    st.caption(
                        f"Ganho real (descontado o IPCA) indisponível: {erro_macro_carteira}"
                    )
                else:
                    st.caption(f"Ganho nominal vs. real (descontado o IPCA) em {n_anos} anos:")
                    tabela_ganho = pd.DataFrame(
                        [
                            {
                                "cenario": rotulo,
                                **calcular_ganho_nominal_vs_real(
                                    soma_investida,
                                    valor_por_cenario[cenario],
                                    ipca_12m_carteira,
                                    n_anos,
                                ),
                            }
                            for cenario, rotulo in ROTULO_CENARIO.items()
                        ]
                    )
                    st.dataframe(
                        tabela_ganho,
                        column_order=["cenario", "ganho_nominal", "ganho_real"],
                        column_config={
                            "cenario": "Cenário",
                            "ganho_nominal": st.column_config.NumberColumn(
                                "Ganho nominal", format="R$ %.2f"
                            ),
                            "ganho_real": st.column_config.NumberColumn(
                                "Ganho real (IPCA)", format="R$ %.2f"
                            ),
                        },
                        hide_index=True,
                        use_container_width=True,
                    )

with aba_conflitos:
    st.caption(
        "Eventos de conflito (GDELT, categorias COERCE/ASSAULT/FIGHT) — "
        f"janela de {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h, ~96 snapshots de 15 "
        "min processados um de cada vez."
    )
    # Escopo fixo e universal (não depende de nenhuma ação/setor escolhido
    # em outra aba) — ver conflitos.PAISES_MONITORADOS.
    st.caption(f"Monitorando: {descrever_paises_monitorados()}.")

    if st.button(
        "Buscar eventos agora",
        on_click=_ativar_aba,
        args=(ABA_CONFLITOS,),
    ):
        st.warning(
            f"Isso busca ~96 snapshots do GDELT (janela de "
            f"{JANELA_MONITOR_CONFLITOS_HORAS:.0f}h, 15 em 15 min) — na primeira "
            "vez, sem nada em cache ainda, leva minutos. Não feche esta aba "
            "enquanto roda."
        )
        with st.spinner(
            f"Buscando eventos das últimas {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h no "
            "GDELT — isso demora mais que um snapshot único, é esperado..."
        ):
            rodar_monitor_conflitos()
        st.success("Busca concluída — resultado salvo em disco.")
        st.rerun()

    eventos_conflito_salvos = carregar_eventos_conflito_salvos(CAMINHO_SAIDA_CONFLITOS_PADRAO)

    if eventos_conflito_salvos is None:
        _aviso_screener_vazio(
            'Clique em "Buscar eventos agora" acima pra gerar '
            f"{CAMINHO_SAIDA_CONFLITOS_PADRAO.name}"
        )
    else:
        atualizado_em = datetime.fromtimestamp(CAMINHO_SAIDA_CONFLITOS_PADRAO.stat().st_mtime)
        st.caption(
            f"Última atualização: {atualizado_em.strftime('%d/%m/%Y %H:%M')} — "
            "dado salvo em disco, não ao vivo. Use o botão acima pra atualizar."
        )

        # Visão geral (mapa) primeiro, detalhe linha a linha (tabela) logo
        # abaixo. Globo com projeção ortográfica — arraste pra girar
        # (nativo do Plotly, sem rotação automática programada: instável
        # na comunidade do Plotly, e o arraste manual já entrega o efeito
        # pedido de forma confiável).
        st.plotly_chart(
            montar_mapa_conflitos(eventos_conflito_salvos), use_container_width=True
        )

        if eventos_conflito_salvos.empty:
            st.info(
                f"Nenhum evento relevante nas últimas {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h "
                "— pode acontecer, mas é bem menos provável que no caso do snapshot "
                "único; não é sinal de erro. O mapa acima mostra só os pontos "
                "estratégicos fixos nesse caso."
            )
        else:
            st.dataframe(
                eventos_conflito_salvos,
                column_order=[
                    "data",
                    "ActionGeo_FullName",
                    "ActionGeo_CountryCode",
                    "categoria_cameo",
                    "GoldsteinScale",
                    "SOURCEURL",
                ],
                column_config={
                    "data": st.column_config.DatetimeColumn(
                        "Data", format="DD/MM/YYYY HH:mm"
                    ),
                    "ActionGeo_FullName": "Local",
                    "ActionGeo_CountryCode": "País (código)",
                    "categoria_cameo": "Tipo",
                    "GoldsteinScale": st.column_config.NumberColumn(
                        "Goldstein Score", format="%.1f"
                    ),
                    "SOURCEURL": st.column_config.LinkColumn("Fonte"),
                },
                hide_index=True,
                use_container_width=True,
            )
