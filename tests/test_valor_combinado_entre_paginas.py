"""O valor combinado de uma mesma ação é o mesmo na página de análise (que recalcula ao vivo), no
Screener e no Simulador (que leem o resultado salvo), quando os três recebem os mesmos dados."""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import carteira, screener
from avaliador_b3.app.dados import _carregar_screener_salvo
from avaliador_b3.app.paginas.screener import _tabela_ranking_screener
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app

PRECO = 50.0
DIVIDA_LIQUIDA = 50_000.0
SELIC_META = 0.105
IPCA_12M = 1.003**12 - 1
ANO_FCD = app.ANO_FCD_MOCK


def _historico_constante(*args, **kwargs) -> pd.DataFrame:
    return pd.DataFrame(
        {"data": pd.to_datetime(["2026-09-15"]), "Close": [PRECO], "Volume": [30_000_000]}
    )


def _linha_do_screener(monkeypatch, tmp_path) -> dict:
    """Linha de PETR4 calculada pelo screener com as mesmas entradas que `_preparar_fcd_aplicavel`
    entrega à página de análise."""
    monkeypatch.setattr(screener, "obter_historico", _historico_constante)
    monkeypatch.setattr(
        screener,
        "obter_indicadores",
        lambda *a, **kw: {
            "lpa": 5.0,
            "vpa": 20.0,
            "numero_acoes": 100.0,
            "divida_liquida_sobre_patrimonio": 0.5,
            "divida_liquida": DIVIDA_LIQUIDA,
            "data_balanco_fundamentus": "2026-06-30",
            "acoes_por_cotacao": 1,
        },
    )
    monkeypatch.setattr(
        screener,
        "obter_dividendos",
        lambda *a, **kw: pd.DataFrame(
            {"data": pd.to_datetime([]), "dividendo": pd.Series(dtype=float)}
        ),
    )
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        lambda ticker, catalogo: {
            "cnpj": "33000167000101",
            "segmento_setorial": "Petróleo, Gás e Biocombustíveis",
        },
    )
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano, anos, **kw: {
            **app._resultado_fcf_mock(1_200_000.0, 200_000.0),
            "fcf_ha_n_anos": 800_000.0,
            "cfo_ha_n_anos": 1_000_000.0,
            "capex_ha_n_anos": {"status": "identificado", "valor": 200_000.0, "linhas": []},
            "juros_pagos_ha_n_anos": {"valor": 0.0, "linhas": []},
            "risco_sacado_ha_n_anos": {"valor": 0.0, "saldo": 0.0, "linhas": []},
            "ano_referencia_utilizado": ano,
            "ano_mais_recente_disponivel": ano,
            "usou_fallback": False,
        },
    )
    monkeypatch.setattr(
        screener, "obter_leitura_balanco", lambda *a, **kw: app._leitura_balanco_mock()
    )
    return screener._calcular_linha_ticker(
        "PETR4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=None,
        selic_meta=SELIC_META,
        ipca_12m=IPCA_12M,
        ano_mais_recente_fcd=ANO_FCD,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )


def _valor_combinado_da_pagina_de_analise(monkeypatch) -> float:
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=DIVIDA_LIQUIDA)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        lambda *a, **kw: _historico_constante(),
    )
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception
    texto = app._kpi_por_rotulo(at, "Valor combinado")["valor"]
    return float(texto.removeprefix("R$").strip().replace(".", "").replace(",", "."))


def test_valor_combinado_igual_na_analise_no_screener_e_no_simulador(monkeypatch, tmp_path):
    linha = _linha_do_screener(monkeypatch, tmp_path)
    combinado_screener = linha["valor_combinado"]
    assert "fcd" in linha["metodos_utilizados"] and "graham" in linha["metodos_utilizados"]

    # A página de análise mostra duas casas decimais.
    assert _valor_combinado_da_pagina_de_analise(monkeypatch) == pytest.approx(
        combinado_screener, abs=0.005
    )

    caminho_csv = tmp_path / "screener.csv"
    pd.DataFrame([linha], columns=COLUNAS_RESULTADO).to_csv(caminho_csv, index=False)
    tabela = _carregar_screener_salvo(caminho_csv)
    estilo, _ = _tabela_ranking_screener(tabela)
    assert estilo.data["valor_combinado"].iloc[0] == pytest.approx(combinado_screener)

    quantidade = 7
    resumo = carteira.resumir_carteira(tabela, {"PETR4": quantidade})
    assert resumo["valor_justo"] / quantidade == pytest.approx(combinado_screener)
    simulacao = carteira.simular_investimento_ticker(linha, quantidade * PRECO)
    assert simulacao["projecao_base"] / quantidade == pytest.approx(combinado_screener)
