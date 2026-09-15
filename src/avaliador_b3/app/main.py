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

from avaliador_b3.carteira import calcular_totais_carteira, montar_tabela_carteira
from avaliador_b3.config import (
    ANO_REFERENCIA_FCD,
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    ANOS_JANELA_CORRELACAO,
    JANELA_MONITOR_CONFLITOS_HORAS,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    SERIES_BCB_SGS,
    TICKER_PETROLEO_BRENT,
)
from avaliador_b3.conflitos import (
    descrever_escopo_paises,
    obter_eventos_relevantes_ultimas_24h,
)
from avaliador_b3.correlacao import calcular_correlacoes_fatores, classificar_magnitude_correlacao
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
from avaliador_b3.graficos import (
    agregar_dividendos_por_ano,
    montar_mapa_conflitos,
    normalizar_base_100,
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


def _buscar_historico(ticker: str, periodo: str) -> tuple[pd.DataFrame | None, str | None]:
    """Histórico de preço da ação. `periodo` varia por uso: a mesma janela
    curta (`PERIODO_HISTORICO_COMPORTAMENTO`) serve pro preço atual (último
    fechamento) e pra volume/volatilidade; Beta usa uma janela própria mais
    longa (`PERIODO_BETA`) — ver o comentário em config.py."""
    try:
        return obter_historico(ticker, periodo=periodo), None
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


@st.cache_data(ttl=300)
def _buscar_eventos_conflito_24h(
    segmento_setorial: str | None,
) -> tuple[pd.DataFrame | None, str | None]:
    """Eventos de conflito relevantes numa janela de 24h (ver
    `conflitos.obter_eventos_relevantes_ultimas_24h`) — cacheado na
    sessão por alguns minutos, bem menos que a janela em si, só pra não
    refazer as ~96 buscas de snapshot a cada abertura da aba. Cada
    snapshot individual também já tem cache próprio em disco sem TTL (é
    dado imutável uma vez publicado pelo GDELT), então mesmo depois desse
    cache daqui expirar, reprocessar a mesma janela de 24h continua
    barato — só os poucos snapshots realmente novos desde a última
    chamada precisam ser baixados de novo. Parametrizado por
    `segmento_setorial` pra cachear corretamente por setor, não por
    ticker (dois tickers do mesmo setor compartilham o resultado)."""
    try:
        return obter_eventos_relevantes_ultimas_24h(segmento_setorial), None
    except Exception as erro:
        return None, f"Falha ao buscar eventos do GDELT: {erro}"


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


def _cartao_metodo(nome: str, resultado: dict, rotulo_valor: str):
    st.metric(nome, f"R$ {resultado[rotulo_valor]:.2f}" if resultado["aplicavel"] else "—")
    if resultado["aplicavel"]:
        st.caption("Aplicável")
    else:
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
    de Screener e de Simulador de carteira — cada uma só varia a instrução
    de como gerar o arquivo, já que o botão que dispara isso só existe na
    aba do Screener."""
    st.info(
        "Nenhum resultado salvo ainda (primeira vez rodando o projeto). "
        f"{instrucao} — vai demorar alguns minutos."
    )


ABA_ANALISAR = "Analisar uma ação"
ABA_SCREENER = "Screener (todas as ações)"
ABA_CARTEIRA = "Simulador de carteira"
ABA_CORRELACAO = "Correlação com fatores externos"
ABA_CONFLITOS = "Monitor de conflitos"

st.set_page_config(page_title="Avaliador B3 (protótipo)", page_icon="📈")
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
aba_analisar, aba_screener, aba_carteira, aba_correlacao, aba_conflitos = st.tabs(
    [ABA_ANALISAR, ABA_SCREENER, ABA_CARTEIRA, ABA_CORRELACAO, ABA_CONFLITOS],
    default=st.session_state["aba_ativa"],
)

with aba_analisar:
    # Buscado aqui em cima (não só depois de "Buscar") porque o dropdown
    # abaixo precisa da lista de opções pra se desenhar — reaproveitado
    # mais adiante na seção "Governança", não buscado de novo lá.
    universo_ibovespa, erro_universo = _buscar_universo_ibovespa()
    usando_dropdown = not (erro_universo or universo_ibovespa is None or universo_ibovespa.empty)

    if usando_dropdown:
        nomes_por_ticker = dict(
            zip(universo_ibovespa["ticker"], universo_ibovespa["nome"], strict=True)
        )
        ticker_selecionado = st.selectbox(
            "Ação (Ibovespa)",
            options=list(nomes_por_ticker.keys()),
            format_func=lambda t: f"{t} — {nomes_por_ticker[t]}",
            index=None,
            placeholder="Selecione uma ação...",
        )
        ticker = ticker_selecionado or ""
    else:
        # Degradação graciosa: a API da B3 pode estar fora do ar — a aba
        # continua usável via texto livre, só sem a lista pronta.
        st.warning(
            "Lista de ações do Ibovespa indisponível "
            f"({erro_universo or 'resultado vazio'}) — digite o ticker manualmente."
        )
        ticker = st.text_input("Ticker (ex: PETR4)", value="").strip().upper()

    buscar = st.button("Buscar", on_click=_ativar_aba, args=(ABA_ANALISAR,))

    if buscar and not ticker:
        st.warning("Selecione uma ação." if usando_dropdown else "Digite um ticker.")

    if buscar and ticker:
        with st.spinner(f"Buscando dados de {ticker}..."):
            historico, erro_historico = _buscar_historico(ticker, PERIODO_HISTORICO_COMPORTAMENTO)
            historico_beta, erro_historico_beta = _buscar_historico(ticker, PERIODO_BETA)
            historico_ibovespa_beta, erro_historico_ibovespa_beta = _buscar_historico_ibovespa(
                PERIODO_BETA
            )
            indicadores, erro_indicadores = _buscar_indicadores_fundamentus(ticker)
            dividendos, erro_dividendos = _buscar_dividendos(ticker)
            cnpj, erro_cnpj = _buscar_cnpj(ticker)
            selic_meta, ipca_12m, erro_macro = _buscar_macro()

            # Erros de FCF não são exibidos à parte — já aparecem no motivo de
            # "não aplicável" do próprio card do FCD.
            fcf_atual = fcf_ha_n_anos = None
            if cnpj:
                ano_anterior = ANO_REFERENCIA_FCD - ANOS_HISTORICO_CRESCIMENTO_FCD
                fcf_atual, _ = _buscar_fcf(cnpj, ANO_REFERENCIA_FCD)
                fcf_ha_n_anos, _ = _buscar_fcf(cnpj, ano_anterior)

        st.subheader(ticker)

        if erro_historico:
            st.error(f"Preço: {erro_historico}")
        else:
            st.metric("Preço atual", f"R$ {historico['Close'].iloc[-1]:.2f}")

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
        coluna_graham, coluna_bazin, coluna_fcd = st.columns(3)
        with coluna_graham:
            _cartao_metodo("Graham", resultado_graham, "valor_justo")
        with coluna_bazin:
            _cartao_metodo("Bazin (preço teto)", resultado_bazin, "preco_teto")
        with coluna_fcd:
            _cartao_metodo("FCD", resultado_fcd, "valor_justo")
            if resultado_fcd["aplicavel"]:
                origem_beta = "calculado, 1a" if beta is not None else "padrão, sem histórico"
                st.caption(f"Beta no WACC: {resultado_fcd['beta_utilizado']:.2f} ({origem_beta})")

        st.divider()
        resultado_combinado = calcular_valor_combinado(
            resultado_graham, resultado_bazin, resultado_fcd
        )
        if resultado_combinado["aplicavel"]:
            st.metric("Valor combinado", f"R$ {resultado_combinado['valor_combinado']:.2f}")
            st.caption(
                "Métodos utilizados: " + ", ".join(resultado_combinado["metodos_utilizados"])
            )
        else:
            st.error(f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']}")

        st.divider()
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
            col_f.metric("Dív. líq./patrim.", _fmt(indicadores["divida_liquida_sobre_patrimonio"]))
            col_g.metric(
                "Cresc. receita (5a)",
                _fmt(indicadores["crescimento_receita_5a_percentual"], "{:.1f}%"),
            )
            st.caption(
                "Indicadores individuais ausentes (\"N/D\") — comum em bancos, onde o "
                "Fundamentus não reporta alguns desses índices no mesmo formato."
            )

        st.divider()
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
                    f"{ticker!r} não está na carteira teórica atual do Ibovespa — essa é a "
                    "única fonte de segmento de listagem que já temos."
                )
        with col_free_float:
            st.metric("Free float", "Pendente")
            st.caption(
                "Nenhum adapter atual extrai free float — nem o universo do Ibovespa "
                "(b3_universo.py) nem o catálogo de emissores (crosswalk_cnpj.py) trazem "
                "esse campo. Fica como pendência explícita, não um valor inventado."
            )

        st.divider()
        st.subheader("Comportamento da ação")
        if erro_historico:
            st.info("Volume/volatilidade indisponíveis — ver aviso de preço acima.")

        col_volume, col_volatilidade, col_beta = st.columns(3)

        if not erro_historico:
            volume_medio = calcular_volume_medio(historico)
            volatilidade = calcular_volatilidade_anualizada(historico)
            col_volume.metric("Volume médio (3m)", f"{volume_medio:,.0f}".replace(",", "."))
            col_volatilidade.metric("Volatilidade anualizada", _fmt(volatilidade, "{:.1%}"))

        with col_beta:
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

        st.divider()
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
                figura_dividendos = go.Figure(
                    go.Bar(x=dividendos_por_ano["ano"], y=dividendos_por_ano["total"])
                )
                figura_dividendos.update_layout(
                    yaxis_title="Total pago no ano (R$/ação)",
                    xaxis_title="Ano",
                    xaxis={"type": "category"},
                    margin={"t": 20},
                )
                st.plotly_chart(figura_dividendos, use_container_width=True)

        st.divider()
        st.subheader("Comparação setorial")
        segmento_setorial, erro_segmento_setorial = _buscar_segmento_setorial(ticker)
        # Guardado em session_state pra aba "Monitor de conflitos" reaproveitar
        # (mesmo ticker escolhido aqui, sem campo de busca próprio).
        st.session_state["ticker_analisado"] = ticker
        st.session_state["segmento_setorial_analisado"] = segmento_setorial
        tabela_screener_setor = _carregar_screener_salvo(CAMINHO_SAIDA_PADRAO)
        if erro_segmento_setorial:
            st.warning(f"Classificação setorial: {erro_segmento_setorial}")
        elif tabela_screener_setor is None:
            _aviso_screener_vazio('Rode o screener primeiro na aba "Screener (todas as ações)"')
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

with aba_correlacao:
    st.caption(
        "Correlação (Pearson) entre o retorno diário da ação e três fatores "
        f"externos — petróleo (Brent), câmbio USD/BRL e risco geopolítico (GPR) — "
        f"numa janela de {ANOS_JANELA_CORRELACAO} anos. Sempre correlaciona a "
        "variação percentual dia a dia de cada série, nunca o nível bruto — "
        "correlacionar séries em tendência infla o número de forma espúria, "
        "sem relação real entre elas."
    )

    ticker_correlacao = (
        st.text_input("Ticker (ex: PETR4)", value="", key="ticker_correlacao").strip().upper()
    )
    buscar_correlacao = st.button(
        "Calcular correlações", on_click=_ativar_aba, args=(ABA_CORRELACAO,)
    )

    if buscar_correlacao and not ticker_correlacao:
        st.warning("Digite um ticker.")

    if buscar_correlacao and ticker_correlacao:
        with st.spinner(f"Buscando dados de {ticker_correlacao} e dos fatores externos..."):
            historico_acao_correlacao, erro_acao_correlacao = _buscar_historico(
                ticker_correlacao, periodo=f"{ANOS_JANELA_CORRELACAO}y"
            )
            historico_petroleo, erro_petroleo = _buscar_historico_petroleo()
            serie_cambio, erro_cambio = _buscar_cambio_correlacao()
            serie_gpr, erro_gpr = _buscar_gpr_diaria()

        if erro_acao_correlacao:
            st.error(f"Preço de {ticker_correlacao}: {erro_acao_correlacao}")
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

            st.divider()
            st.subheader(ticker_correlacao)
            col_petroleo, col_cambio, col_gpr = st.columns(3)
            with col_petroleo:
                _cartao_correlacao("Petróleo (Brent)", resultados_correlacao["petroleo"])
            with col_cambio:
                _cartao_correlacao("Câmbio USD/BRL", resultados_correlacao["cambio"])
            with col_gpr:
                _cartao_correlacao("Risco geopolítico (GPR)", resultados_correlacao["gpr"])

with aba_conflitos:
    st.caption(
        "Eventos de conflito (GDELT, categorias COERCE/ASSAULT/FIGHT) nos "
        "países relevantes pra ação escolhida na aba \"Analisar uma ação\" — "
        f"janela de {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h, ~96 snapshots de 15 "
        "min processados um de cada vez."
    )

    ticker_conflitos = st.session_state.get("ticker_analisado")

    if not ticker_conflitos:
        st.info(
            'Busque uma ação na aba "Analisar uma ação" primeiro — o monitor de '
            "conflitos usa o mesmo ticker escolhido lá, sem campo de busca próprio."
        )
    else:
        # Ticker e escopo de países aparecem sem custo nenhum assim que uma
        # ação é escolhida — só a busca de eventos em si (a parte cara, ~96
        # requisições) fica atrás do botão abaixo, nunca dispara sozinha só
        # porque uma ação foi buscada na aba "Analisar uma ação".
        segmento_setorial_conflitos = st.session_state.get("segmento_setorial_analisado")

        st.subheader(ticker_conflitos)
        st.caption(
            f"Monitorando: {descrever_escopo_paises(segmento_setorial_conflitos)}."
        )

        if st.button(
            f"Buscar eventos das últimas {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h",
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
                eventos_relevantes, erro_eventos_conflito = _buscar_eventos_conflito_24h(
                    segmento_setorial_conflitos
                )
            # Guardado em session_state (não só na variável local) pra
            # continuar visível em reruns futuros causados por qualquer outra
            # interação na página — não some assim que o usuário mexe em
            # outra coisa.
            st.session_state["resultado_conflitos_24h"] = {
                "ticker": ticker_conflitos,
                "eventos": eventos_relevantes,
                "erro": erro_eventos_conflito,
            }

        resultado_salvo = st.session_state.get("resultado_conflitos_24h")

        if resultado_salvo is None or resultado_salvo["ticker"] != ticker_conflitos:
            st.info(
                f'Clique em "Buscar eventos das últimas '
                f'{JANELA_MONITOR_CONFLITOS_HORAS:.0f}h" acima pra carregar os '
                "eventos dessa ação — não busca nada automaticamente."
            )
        elif resultado_salvo["erro"]:
            st.warning(f"GDELT: {resultado_salvo['erro']}")
        else:
            eventos_conflito_mapa = resultado_salvo["eventos"]

            # Visão geral (mapa) primeiro, detalhe linha a linha (tabela)
            # logo abaixo. Globo com projeção ortográfica — arraste pra
            # girar (nativo do Plotly, sem rotação automática programada:
            # instável na comunidade do Plotly, e o arraste manual já
            # entrega o efeito pedido de forma confiável).
            st.plotly_chart(
                montar_mapa_conflitos(eventos_conflito_mapa), use_container_width=True
            )

            if eventos_conflito_mapa.empty:
                st.info(
                    f"Nenhum evento relevante nas últimas {JANELA_MONITOR_CONFLITOS_HORAS:.0f}h "
                    "— pode acontecer, mas é bem menos provável que no caso do snapshot "
                    "único; não é sinal de erro. O mapa acima mostra só os pontos "
                    "estratégicos fixos nesse caso."
                )
            else:
                st.dataframe(
                    eventos_conflito_mapa,
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
