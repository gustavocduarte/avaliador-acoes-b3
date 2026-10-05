"""Widget do TradingView: só ticker no formato da B3 entra no HTML, e a configuração
vai como JSON serializado."""

import ast
import json
import logging
import re
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

from avaliador_b3.config import MENSAGEM_TRADINGVIEW_TICKER_INVALIDO, PADRAO_TICKER_B3
from tests import test_app_main as app

CAMINHO_APP = Path(app.CAMINHO_APP)


def _funcao_do_widget():
    """A função do app, sem importar `app/main.py` (que executa a tela inteira)."""
    arvore = ast.parse(CAMINHO_APP.read_text(encoding="utf-8"))
    funcao = next(
        no
        for no in arvore.body
        if isinstance(no, ast.FunctionDef) and no.name == "_widget_avancado_tradingview"
    )
    espaco = {"re": re, "json": json, "PADRAO_TICKER_B3": PADRAO_TICKER_B3}
    exec(compile(ast.Module([funcao], []), str(CAMINHO_APP), "exec"), espaco)
    return espaco["_widget_avancado_tradingview"]


widget = _funcao_do_widget()

TICKERS_VALIDOS = ["PETR4", "VALE3", "BPAC11", "B3SA3", "ITSA4", "BOVA11", "MGLU3"]
TICKERS_INVALIDOS = [
    "",
    " ",
    "petr4",
    "PETR",
    "PETR4 ",
    "PETR444",
    "PETR4.SA",
    "^BVSP",
    "BZ=F",
    'X","symbol":"NASDAQ:AAPL',
    "</script><img src=x onerror=alert(1)>",
    "PETR4\nPETR3",
    "PETR4;alert(1)",
]


def _configuracao_do_html(html: str) -> dict:
    corpo = html.split("async>", 1)[1].split("</script>", 1)[0]
    return json.loads(corpo)


@pytest.mark.parametrize("ticker", TICKERS_VALIDOS)
def test_ticker_valido_gera_o_widget_com_o_simbolo_da_b3(ticker):
    html = widget(ticker)

    assert html is not None
    assert _configuracao_do_html(html)["symbol"] == f"BMFBOVESPA:{ticker}"


@pytest.mark.parametrize("ticker", TICKERS_INVALIDOS)
def test_ticker_fora_do_formato_da_b3_nao_gera_html(ticker):
    assert widget(ticker) is None


def test_a_configuracao_do_widget_e_um_json_valido_com_as_opcoes_fixas():
    configuracao = _configuracao_do_html(widget("PETR4"))

    assert configuracao["autosize"] is True
    assert configuracao["allow_symbol_change"] is True
    assert configuracao["interval"] == "D"
    assert configuracao["locale"] == "br"


def test_o_html_desliga_a_rolagem_do_iframe():
    assert "overflow: hidden" in widget("PETR4")


def test_o_html_gerado_tem_um_unico_fechamento_de_script():
    assert widget("PETR4").count("</script>") == 1


def _abrir_com_catalogo_fora_do_ar(monkeypatch):
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    def sem_catalogo(**kwargs):
        raise requests.ConnectionError("B3 fora do ar (simulado)")

    monkeypatch.setattr("avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", sem_catalogo)
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)
    return at


def _buscar(at, ticker):
    at.text_input[0].set_value(ticker)
    [botao for botao in at.button if botao.label == "Buscar"][0].click()
    at.run(timeout=60)


def test_na_tela_ticker_digitado_invalido_nao_injeta_nada_e_avisa(monkeypatch):
    at = _abrir_com_catalogo_fora_do_ar(monkeypatch)

    _buscar(at, "</script><img src=x onerror=alert(1)>")

    assert not at.exception
    assert all("onerror" not in (e.proto.srcdoc or "") for e in at.get("iframe"))
    assert MENSAGEM_TRADINGVIEW_TICKER_INVALIDO in [info.value for info in at.info]


def test_na_tela_ticker_digitado_valido_mostra_o_widget(monkeypatch):
    at = _abrir_com_catalogo_fora_do_ar(monkeypatch)

    _buscar(at, "PETR4")

    assert not at.exception
    assert any('"symbol": "BMFBOVESPA:PETR4"' in (e.proto.srcdoc or "") for e in at.get("iframe"))
    assert MENSAGEM_TRADINGVIEW_TICKER_INVALIDO not in [info.value for info in at.info]


def test_a_tela_nao_usa_apis_depreciadas_do_streamlit(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert [r.getMessage() for r in caplog.records if "Please replace" in r.getMessage()] == []
    assert at.get("iframe"), "o widget deveria ter sido renderizado"
