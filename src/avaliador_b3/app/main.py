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

import streamlit as st

from avaliador_b3.config import ANOS_HISTORICO_CRESCIMENTO_FCD, SERIES_BCB_SGS
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


def _buscar_preco_atual(ticker: str) -> tuple[float | None, str | None]:
    try:
        historico = obter_historico(ticker, periodo="5d")
        return float(historico["Close"].iloc[-1]), None
    except (TickerInvalido, FalhaFontePreco) as erro:
        return None, str(erro)


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
        preco_atual, erro_preco = _buscar_preco_atual(ticker)
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

    if erro_preco:
        st.error(f"Preço: {erro_preco}")
    else:
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

    st.divider()
    resultado_combinado = calcular_valor_combinado(resultado_graham, resultado_bazin, resultado_fcd)
    if resultado_combinado["aplicavel"]:
        st.metric("Valor combinado", f"R$ {resultado_combinado['valor_combinado']:.2f}")
        st.caption("Métodos utilizados: " + ", ".join(resultado_combinado["metodos_utilizados"]))
    else:
        st.error(f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']}")
