"""Navegação por barra lateral: as três páginas, a padrão, a caixa da ação só na análise, a ação
mantida ao trocar de página e o rodapé."""

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.config import (
    CHAVE_BARRA_ANALISAR,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_BARRA_RODAPE,
    CHAVE_BARRA_SCREENER,
    SUFIXO_BARRA_ATIVA,
    TEXTO_ABERTURA_SIMULADOR,
    TEXTO_RODAPE_APP_DORMINDO,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    URL_REPOSITORIO,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina, blocos_da_barra, paginas_do_menu

ROTULO_CAIXA_DA_ACAO = "Ação (Ibovespa)"


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    st.cache_data.clear()
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: app._universo_falso(),
    )
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.bcb_sgs.carregar_macro_referencia",
        lambda: {"data_busca": pd.Timestamp("2026-10-03 22:30")},
    )
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
    yield
    st.cache_data.clear()


def _app_aberto() -> AppTest:
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception
    return at


def _tem_caixa_da_acao(at: AppTest) -> bool:
    return any(caixa.label == ROTULO_CAIXA_DA_ACAO for caixa in at.sidebar.selectbox)


def test_menu_tem_as_tres_paginas_na_ordem_com_icones_material_e_urls():
    at = _app_aberto()

    assert paginas_do_menu(at) == [
        ("Analisar uma ação", ":material/search:", ""),
        ("Screener", ":material/table_chart:", "screener"),
        ("Simulador de carteira", ":material/account_balance_wallet:", "simulador"),
    ]


def _links_do_menu(filhos: list) -> list[str]:
    return [f.proto.label for f in filhos if f.type == "page_link"]


def test_menu_tem_um_bloco_por_pagina_com_o_link_e_o_rodape_separado():
    at = _app_aberto()

    blocos = blocos_da_barra(at)

    chaves = [chave.removesuffix(SUFIXO_BARRA_ATIVA) for chave, _ in blocos]
    assert chaves == [
        CHAVE_BARRA_ANALISAR,
        CHAVE_BARRA_SCREENER,
        CHAVE_BARRA_CARTEIRA,
        CHAVE_BARRA_RODAPE,
    ]
    assert [_links_do_menu(filhos) for _, filhos in blocos[:3]] == [
        [TITULO_PAGINA_ANALISAR],
        [TITULO_PAGINA_SCREENER],
        [TITULO_PAGINA_CARTEIRA],
    ]
    assert _links_do_menu(blocos[3][1]) == []


def test_caixa_e_buscar_ficam_no_bloco_da_analise_logo_abaixo_do_link():
    at = _app_aberto()

    _, filhos = blocos_da_barra(at)[0]

    assert [f.type for f in filhos] == ["page_link", "selectbox", "button"]
    assert filhos[1].label == ROTULO_CAIXA_DA_ACAO
    assert filhos[2].label == "Buscar"


def test_so_o_bloco_da_pagina_aberta_ganha_o_destaque():
    at = _app_aberto()
    destacados = lambda: [  # noqa: E731
        chave for chave, _ in blocos_da_barra(at) if chave.endswith(SUFIXO_BARRA_ATIVA)
    ]
    assert destacados() == [CHAVE_BARRA_ANALISAR + SUFIXO_BARRA_ATIVA]

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    assert destacados() == [CHAVE_BARRA_SCREENER + SUFIXO_BARRA_ATIVA]

    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    assert destacados() == [CHAVE_BARRA_CARTEIRA + SUFIXO_BARRA_ATIVA]


def test_blocos_fora_da_analise_tem_so_o_link():
    at = _app_aberto()
    abrir_pagina(at, TITULO_PAGINA_SCREENER)

    _, filhos = blocos_da_barra(at)[0]

    assert [f.type for f in filhos] == ["page_link"]


def test_a_pagina_padrao_e_a_analise_com_resultado_de_exemplo():
    at = _app_aberto()

    assert any(subheader.value == "PETR4" for subheader in at.subheader)
    assert _tem_caixa_da_acao(at)


def test_caixa_da_acao_so_aparece_na_pagina_de_analise():
    at = _app_aberto()
    assert _tem_caixa_da_acao(at)
    assert "Buscar" in [botao.label for botao in at.sidebar.button]

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    assert not _tem_caixa_da_acao(at)
    assert "Buscar" not in [botao.label for botao in at.button]

    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    assert not _tem_caixa_da_acao(at)
    assert "Buscar" not in [botao.label for botao in at.button]

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    assert _tem_caixa_da_acao(at)


def test_acao_e_resultado_continuam_valendo_ao_trocar_de_pagina_e_voltar():
    at = _app_aberto()
    at.selectbox[0].select("VALE3").run(timeout=60)
    next(b for b in at.button if b.label == "Buscar").click().run(timeout=60)
    assert any(subheader.value == "VALE3" for subheader in at.subheader)

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    abrir_pagina(at, TITULO_PAGINA_ANALISAR)

    assert not at.exception
    assert at.sidebar.selectbox[0].value == "VALE3"
    assert any(subheader.value == "VALE3" for subheader in at.subheader)
    assert not any(subheader.value == "PETR4" for subheader in at.subheader)


def test_acao_digitada_no_texto_livre_tambem_e_mantida(monkeypatch):
    def universo_fora_do_ar(**kwargs):
        raise RuntimeError("falha simulada de rede")

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", universo_fora_do_ar
    )
    at = _app_aberto()
    at.sidebar.text_input[0].set_value("vale3").run(timeout=60)

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    abrir_pagina(at, TITULO_PAGINA_ANALISAR)

    # Volta normalizado (maiúsculas), como o app já tratava o ticker digitado.
    assert at.sidebar.text_input[0].value == "VALE3"


def test_rodape_da_barra_lateral_tem_a_data_do_screener_e_o_link_do_repositorio():
    at = _app_aberto()

    textos = [e.value for e in (*at.sidebar.caption, *at.sidebar.markdown)]
    assert any("Screener atualizado em 03/10/2026" in texto for texto in textos)
    assert any(URL_REPOSITORIO in texto for texto in textos)

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    textos = [e.value for e in (*at.sidebar.caption, *at.sidebar.markdown)]
    assert any("Screener atualizado em 03/10/2026" in texto for texto in textos)


def test_rodape_sem_arquivo_de_referencia_mostra_so_o_link(monkeypatch):
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.carregar_macro_referencia", lambda: None)
    at = _app_aberto()

    textos = [e.value for e in (*at.sidebar.caption, *at.sidebar.markdown)]
    assert not any("Screener atualizado em" in texto for texto in textos)
    assert any(URL_REPOSITORIO in texto for texto in textos)


@pytest.mark.parametrize(
    "titulo", [TITULO_PAGINA_ANALISAR, TITULO_PAGINA_SCREENER, TITULO_PAGINA_CARTEIRA]
)
def test_rodape_de_toda_pagina_diz_o_tempo_da_primeira_abertura_com_o_catalogo_enxuto(titulo):
    at = abrir_pagina(_app_aberto(), titulo)

    legendas = [c.value for c in at.caption]
    assert TEXTO_RODAPE_APP_DORMINDO in legendas
    assert "cerca de 25 segundos" in TEXTO_RODAPE_APP_DORMINDO
    assert not any("1 minuto" in legenda for legenda in legendas)


def test_abrir_pagina_mostra_um_elemento_caracteristico_de_cada_pagina():
    at = AppTest.from_file(app.CAMINHO_APP)

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    assert any(subheader.value == "PETR4" for subheader in at.subheader)

    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    assert any("Ranking por potencial" in h.proto.body for h in at.get("html"))

    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    assert any(c.value == TEXTO_ABERTURA_SIMULADOR for c in at.caption)


def test_abrir_pagina_lista_os_titulos_quando_o_pedido_nao_existe():
    at = AppTest.from_file(app.CAMINHO_APP)

    with pytest.raises(AssertionError) as erro:
        abrir_pagina(at, "Inexistente")

    mensagem = str(erro.value)
    assert "Inexistente" in mensagem
    for titulo in (TITULO_PAGINA_ANALISAR, TITULO_PAGINA_SCREENER, TITULO_PAGINA_CARTEIRA):
        assert titulo in mensagem


def test_abrir_pagina_avisa_quando_o_apptest_perde_os_atributos_privados():
    class AppTestSemAtributos:
        pass

    with pytest.raises(AssertionError, match="AppTest mudou"):
        abrir_pagina(AppTestSemAtributos(), TITULO_PAGINA_SCREENER)  # type: ignore[arg-type]


def test_texto_de_abertura_do_simulador_fala_da_montagem_por_quantidade():
    assert "quantidade de cada ação" in TEXTO_ABERTURA_SIMULADOR
    assert "valor investido em cada ação" not in TEXTO_ABERTURA_SIMULADOR
    # Não repete a descrição da página nem a instrução do aviso "Adicione ações…".
    assert "Monte" not in TEXTO_ABERTURA_SIMULADOR
