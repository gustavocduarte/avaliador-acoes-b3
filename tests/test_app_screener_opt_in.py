"""Botão "Rodar screener agora": só aparece com o opt-in explícito (variável de ambiente ou
secret `AVALIADOR_B3_PERMITIR_RODAR_SCREENER`), negado por padrão; no app publicado a tela
diz que o workflow atualiza o screener, com a data da última atualização."""

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.config import (
    TEXTO_SCREENER_AINDA_NAO_GERADO,
    TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA,
    VARIAVEL_PERMITIR_RODAR_SCREENER,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app

ROTULO_BOTAO = "Rodar screener agora"
DATA_BUSCA = pd.Timestamp("2026-10-03 22:30")


@pytest.fixture(autouse=True)
def _limpar_cache_streamlit():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def sem_opt_in(monkeypatch):
    monkeypatch.delenv(VARIAVEL_PERMITIR_RODAR_SCREENER, raising=False)


@pytest.fixture
def referencia_de_03_10(monkeypatch):
    macro = {"data_busca": DATA_BUSCA}
    monkeypatch.setattr(
        "avaliador_b3.ingest.bcb_sgs.carregar_macro_referencia", lambda: macro, raising=True
    )


@pytest.fixture
def screener_salvo(tmp_path, monkeypatch):
    linha = {coluna: None for coluna in COLUNAS_RESULTADO} | {
        "ticker": "AAAA4",
        "sucesso": True,
        "preco_atual": 40.0,
        "valor_combinado": 50.0,
        "desconto_percentual": 25.0,
        "metodos_utilizados": "graham",
        "graham_valor_justo": 50.0,
        "aviso_desconto_extremo": "",
    }
    caminho = tmp_path / "screener.csv"
    pd.DataFrame([linha], columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    return caminho


def _abrir():
    at = AppTest.from_file(app.CAMINHO_APP)
    # Isola o teste de um .streamlit/secrets.toml local com o opt-in ligado.
    at.secrets[VARIAVEL_PERMITIR_RODAR_SCREENER] = False
    at.run(timeout=60)
    assert not at.exception
    return at


def _rotulos_dos_botoes(at):
    return [botao.label for botao in at.button]


def _textos_da_tela(at):
    return [elemento.value for elemento in (*at.info, *at.caption, *at.warning, *at.markdown)]


def test_por_padrao_o_botao_nao_aparece_e_a_tela_explica_o_workflow(
    sem_opt_in, referencia_de_03_10, screener_salvo
):
    at = _abrir()

    assert ROTULO_BOTAO not in _rotulos_dos_botoes(at)
    informacoes = [info.value for info in at.info]
    assert any(
        "atualizado automaticamente pelo workflow nos dias úteis" in texto
        and "Última atualização: 03/10/2026" in texto
        for texto in informacoes
    )


def test_no_app_publicado_nenhum_texto_manda_clicar_no_botao(
    sem_opt_in, referencia_de_03_10, screener_salvo
):
    at = _abrir()

    assert not any("botão" in texto.lower() for texto in _textos_da_tela(at))
    assert not any(ROTULO_BOTAO in texto for texto in _textos_da_tela(at))


def test_sem_arquivo_de_referencia_o_aviso_vem_sem_data(monkeypatch, sem_opt_in, screener_salvo):
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.carregar_macro_referencia", lambda: None)

    at = _abrir()

    assert TEXTO_SCREENER_ATUALIZADO_PELO_WORKFLOW_SEM_DATA in [info.value for info in at.info]


def test_no_app_publicado_sem_resultado_salvo_nao_manda_rodar_o_screener(
    monkeypatch, sem_opt_in, referencia_de_03_10, tmp_path
):
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", tmp_path / "nao_existe.csv")

    at = _abrir()

    informacoes = [info.value for info in at.info]
    assert TEXTO_SCREENER_AINDA_NAO_GERADO in informacoes
    assert not any("Clique em" in texto or "Rode o screener" in texto for texto in informacoes)


@pytest.mark.parametrize("valor", ["1", "true", "TRUE", " sim ", "on", "Yes"])
def test_variavel_de_ambiente_ligada_mostra_o_botao(
    monkeypatch, referencia_de_03_10, screener_salvo, valor
):
    monkeypatch.setenv(VARIAVEL_PERMITIR_RODAR_SCREENER, valor)

    at = _abrir()

    assert ROTULO_BOTAO in _rotulos_dos_botoes(at)
    assert not any("atualizado automaticamente" in info.value for info in at.info)


@pytest.mark.parametrize("valor", ["", "0", "false", "nao", "talvez", "2"])
def test_variavel_de_ambiente_desligada_ou_invalida_esconde_o_botao(
    monkeypatch, referencia_de_03_10, screener_salvo, valor
):
    monkeypatch.setenv(VARIAVEL_PERMITIR_RODAR_SCREENER, valor)

    assert ROTULO_BOTAO not in _rotulos_dos_botoes(_abrir())


@pytest.mark.parametrize(("valor", "aparece"), [("true", True), (True, True), (False, False)])
def test_secret_com_o_mesmo_nome_liga_ou_desliga_o_botao(
    sem_opt_in, referencia_de_03_10, screener_salvo, valor, aparece
):
    at = AppTest.from_file(app.CAMINHO_APP)
    at.secrets[VARIAVEL_PERMITIR_RODAR_SCREENER] = valor
    at.run(timeout=60)

    assert not at.exception
    assert (ROTULO_BOTAO in _rotulos_dos_botoes(at)) is aparece


def test_sem_opt_in_a_rodada_nunca_e_chamada(monkeypatch, sem_opt_in, screener_salvo):
    def rodada_proibida(*args, **kwargs):
        raise AssertionError("rodar_screener não pode ser chamado no app publicado")

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodada_proibida)

    at = _abrir()

    assert ROTULO_BOTAO not in _rotulos_dos_botoes(at)
    assert not at.exception


def test_com_opt_in_o_botao_continua_rodando_o_screener(
    monkeypatch, referencia_de_03_10, screener_salvo
):
    monkeypatch.setenv(VARIAVEL_PERMITIR_RODAR_SCREENER, "1")
    chamadas = []

    def rodada_falsa(*args, **kwargs):
        chamadas.append(1)
        return pd.read_csv(screener_salvo)

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodada_falsa)
    at = _abrir()

    next(botao for botao in at.button if botao.label == ROTULO_BOTAO).click().run(timeout=60)

    assert chamadas == [1]
    assert not at.exception
