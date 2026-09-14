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
import streamlit as st

from avaliador_b3.config import (
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    SERIES_BCB_SGS,
)
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
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

# Ano de referência pro FCD: 2025 ainda não estava publicado pela CVM na
# época em que isso foi escrito (confirmado no adapter da CVM), então usa
# 2024 como padrão fixo por ora — trocar por uma detecção automática do
# ano mais recente disponível é um refinamento futuro, fora do escopo
# desse protótipo.
ANO_REFERENCIA_FCD = 2024


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


def _fmt(valor: float | None, template: str = "{:.2f}") -> str:
    """Formata um número, ou "N/D" se ausente — indicador individual
    faltando (ex: banco sem Dív Líq/Patrim no Fundamentus) não deve
    quebrar a tela nem virar um "None" cru na tela."""
    return template.format(valor) if valor is not None else "N/D"


st.set_page_config(page_title="Avaliador B3 (protótipo)", page_icon="📈")
st.title("Avaliador de Ações da B3")
st.caption(
    "Protótipo mínimo — teste de integração visual dos adapters e modelos já "
    "implementados, não a versão final do dashboard."
)

ticker = st.text_input("Ticker (ex: PETR4)", value="").strip().upper()
buscar = st.button("Buscar")

if buscar and not ticker:
    st.warning("Digite um ticker.")

if buscar and ticker:
    with st.spinner(f"Buscando dados de {ticker}..."):
        historico, erro_historico = _buscar_historico(ticker, PERIODO_HISTORICO_COMPORTAMENTO)
        historico_beta, erro_historico_beta = _buscar_historico(ticker, PERIODO_BETA)
        historico_ibovespa_beta, erro_historico_ibovespa_beta = _buscar_historico_ibovespa(
            PERIODO_BETA
        )
        universo_ibovespa, erro_universo = _buscar_universo_ibovespa()
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
    resultado_combinado = calcular_valor_combinado(resultado_graham, resultado_bazin, resultado_fcd)
    if resultado_combinado["aplicavel"]:
        st.metric("Valor combinado", f"R$ {resultado_combinado['valor_combinado']:.2f}")
        st.caption("Métodos utilizados: " + ", ".join(resultado_combinado["metodos_utilizados"]))
    else:
        st.error(f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']}")

    st.divider()
    st.subheader("Saúde financeira")
    if indicadores is None:
        st.info("Indisponível — ver aviso do Fundamentus acima.")
    else:
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("ROE", _fmt(indicadores["roe_percentual"], "{:.1f}%"))
        col_b.metric("Margem líquida", _fmt(indicadores["margem_liquida_percentual"], "{:.1f}%"))
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
