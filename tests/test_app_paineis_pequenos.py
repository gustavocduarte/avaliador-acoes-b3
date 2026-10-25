"""Painéis pequenos da análise: Governança e Comportamento da ação na grade de indicadores."""

import re

from streamlit.testing.v1 import AppTest

from avaliador_b3.app.paginas.analise_blocos import _html_indicador
from tests import test_app_main as app


def _abrir(monkeypatch) -> AppTest:
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception
    return at


def _grade_com(at: AppTest, rotulo: str) -> str:
    grades = [e.proto.body for e in at.get("html") if "ab-grade" in e.proto.body]
    return next(g for g in grades if rotulo in g)


def _indicador(grade: str, rotulo: str) -> str:
    return re.search(
        rf'<div class="ab-ind">(?:(?!<div class="ab-ind">).)*?{rotulo}.*?</div>', grade
    ).group(0)


def test_ajuda_do_indicador_vira_o_ponto_de_interrogacao_do_rotulo():
    com = _html_indicador("Free float", "—", ajuda='Diz "x" & y')
    assert '<span class="ab-ajuda" title="Diz &quot;x&quot; &amp; y">?</span>' in com
    assert com.index("Free float") < com.index("ab-ajuda") < com.index("ab-ind-valor")
    assert "ab-ajuda" not in _html_indicador("Free float", "—")


def test_governanca_usa_a_grade_com_free_float_indisponivel_e_a_legenda_no_ponto_de_interrogacao(
    monkeypatch,
):
    at = _abrir(monkeypatch)

    grade = _grade_com(at, "Free float")
    free_float = _indicador(grade, "Free float")
    assert 'class="ab-ind-valor ab-cor-texto">—<' in free_float
    assert 'title="Dado não disponível nas fontes usadas."' in free_float
    assert "Segmento de listagem" in grade
    assert not any(m.label in ("Segmento de listagem", "Free float") for m in at.metric)
    assert "Dado não disponível nas fontes usadas." not in [c.value for c in at.caption]


def test_comportamento_usa_a_grade_com_volume_volatilidade_e_beta(monkeypatch):
    at = _abrir(monkeypatch)

    grade = _grade_com(at, "Volume médio (3m)")
    for rotulo in ("Volatilidade anualizada", "Beta (vs. Ibovespa, 1a)"):
        assert rotulo in grade
    rotulos_antigos = {"Volume médio (3m)", "Volatilidade anualizada", "Beta (vs. Ibovespa, 1a)"}
    assert not any(m.label in rotulos_antigos for m in at.metric)
