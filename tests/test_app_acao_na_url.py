"""Página "Analisar uma ação" aberta pelo endereço (`/?acao=PETR4`, o link do ticker no Screener):
ação buscada, parâmetro retirado da URL e aviso para ticker inválido."""

from streamlit.testing.v1 import AppTest

from avaliador_b3.config import TITULO_PAGINA_ANALISAR
from tests import test_app_main as app


def _preparar(monkeypatch, universo_disponivel: bool = True) -> None:
    def universo(**kwargs):
        if not universo_disponivel:
            raise RuntimeError("B3 fora do ar (simulado)")
        return app._universo_falso()

    monkeypatch.setattr("avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", universo)
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)


def _abrir(acao: str | None) -> AppTest:
    at = AppTest.from_file(app.CAMINHO_APP)
    if acao is not None:
        at.query_params["acao"] = acao
    at.run(timeout=60)
    assert not at.exception
    return at


def _subtitulos(at) -> list[str]:
    return [s.value for s in at.subheader]


def _avisos_da_url(at) -> list[str]:
    return [w.value for w in at.warning if "do endereço não foi encontrada" in w.value]


def test_acao_valida_na_url_e_buscada_no_lugar_da_padrao(monkeypatch):
    _preparar(monkeypatch)

    at = _abrir("vale3")

    assert at.sidebar.selectbox[0].value == "VALE3"
    assert _subtitulos(at) == ["VALE3 · VALE S.A."]  # a busca automática da PETR4 não acontece
    assert not _avisos_da_url(at)


def test_o_parametro_sai_da_url_depois_de_usado(monkeypatch):
    _preparar(monkeypatch)

    at = _abrir("VALE3")

    assert "acao" not in at.query_params


def test_acao_invalida_na_url_avisa_e_abre_a_pagina_como_sem_parametro(monkeypatch):
    _preparar(monkeypatch)

    at = _abrir("XYZW9")

    avisos = _avisos_da_url(at)
    assert len(avisos) == 1
    assert "A ação “XYZW9” do endereço não foi encontrada no Ibovespa" in avisos[0]
    assert _subtitulos(at) == ["PETR4 · PETROBRAS"]  # a abertura normal, com a ação padrão
    assert "acao" not in at.query_params


def test_texto_da_url_nunca_vira_formatacao_no_aviso(monkeypatch):
    _preparar(monkeypatch)

    at = _abrir("<b>**x**</b>$$")

    avisos = _avisos_da_url(at)
    assert len(avisos) == 1
    assert not any(caractere in avisos[0] for caractere in "<>*$`")
    assert "“BXB”" in avisos[0]


def test_parametro_vazio_ou_so_com_simbolos_avisa_sem_quebrar(monkeypatch):
    _preparar(monkeypatch)

    for acao in ("", "   ", "@@@"):
        at = _abrir(acao)
        assert len(_avisos_da_url(at)) == 1
        assert "acao" not in at.query_params


def test_sem_a_lista_do_ibovespa_vale_o_formato_de_ticker_da_b3(monkeypatch):
    _preparar(monkeypatch, universo_disponivel=False)

    valida = _abrir("bbas3")
    assert valida.sidebar.text_input[0].value == "BBAS3"
    assert _subtitulos(valida) == ["BBAS3"]
    assert not _avisos_da_url(valida)

    invalida = _abrir("123")
    assert len(_avisos_da_url(invalida)) == 1
    assert _subtitulos(invalida) == []


def test_sem_o_parametro_a_abertura_continua_com_a_acao_padrao(monkeypatch):
    _preparar(monkeypatch)

    at = _abrir(None)

    assert _subtitulos(at) == ["PETR4 · PETROBRAS"]
    assert not _avisos_da_url(at)
    assert TITULO_PAGINA_ANALISAR  # a página de análise é a padrão, na raiz
