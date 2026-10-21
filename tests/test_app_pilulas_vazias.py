"""Sem segmento setorial nem de listagem (texto livre, sem a lista do Ibovespa), a página de
análise abre normalmente, sem a faixa de pílulas."""

from streamlit.testing.v1 import AppTest

from tests import test_app_main as app


def test_busca_sem_nenhum_segmento_nao_quebra_a_pagina(monkeypatch):
    def universo_fora_do_ar(**kwargs):
        raise RuntimeError("B3 fora do ar (simulado)")

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", universo_fora_do_ar
    )
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)

    at.sidebar.text_input[0].set_value("BBAS3")
    next(b for b in at.sidebar.button if b.label == "Buscar").click().run(timeout=60)

    assert not at.exception
    assert [s.value for s in at.subheader] == ["BBAS3"]
    assert not [h for h in at.get("html") if 'class="ab-pilula"' in h.proto.body]
