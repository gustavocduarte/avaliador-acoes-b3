"""O tema do Streamlit (.streamlit/config.toml) repete os tokens de cor de config.py, porque o
TOML não importa Python: este teste falha se os dois divergirem."""

import re
import tomllib
from pathlib import Path

import pytest

from avaliador_b3 import config

CAMINHO_TEMA = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"

TOKENS_NO_TEMA = {
    "primaryColor": config.COR_PRINCIPAL,
    "backgroundColor": config.COR_FUNDO_PAGINA,
    "secondaryBackgroundColor": config.COR_FUNDO_PAINEL,
    "textColor": config.COR_TEXTO,
    "greenColor": config.COR_POSITIVO,
    "redColor": config.COR_NEGATIVO,
    "yellowColor": config.COR_ALERTA,
    "borderColor": config.COR_BORDA,
    "dataframeBorderColor": config.COR_BORDA,
    "dataframeHeaderBackgroundColor": config.COR_FUNDO_PAINEL,
}


@pytest.fixture(scope="module")
def tema():
    return tomllib.loads(CAMINHO_TEMA.read_text(encoding="utf-8"))["theme"]


@pytest.mark.parametrize(("opcao", "token"), TOKENS_NO_TEMA.items())
def test_cor_do_tema_bate_com_o_token_de_config(tema, opcao, token):
    assert tema[opcao].upper() == token.upper()


def test_sequencia_de_series_do_tema_bate_com_a_de_config(tema):
    assert [c.upper() for c in tema["chartCategoricalColors"]] == [
        c.upper() for c in config.SEQUENCIA_CORES_SERIES
    ]


def test_tema_e_escuro(tema):
    assert tema["base"] == "dark"


def _luminancia(cor: str) -> float:
    r, g, b = (int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5))
    canais = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def _contraste(a: str, b: str) -> float:
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


CORES_DE_TEXTO_E_SERIE = [
    config.COR_TEXTO,
    config.COR_TEXTO_SECUNDARIO,
    config.COR_PRINCIPAL,
    config.COR_POSITIVO,
    config.COR_NEGATIVO,
    config.COR_NEUTRO,
    config.COR_DESTAQUE,
    config.COR_ALERTA,
    *config.SEQUENCIA_CORES_SERIES,
]


def test_tokens_sao_cores_hexadecimais():
    tokens = [v for k, v in vars(config).items() if k.startswith("COR_")]
    assert tokens and all(re.fullmatch(r"#[0-9A-Fa-f]{6}", t) for t in tokens)


@pytest.mark.parametrize("fundo", [config.COR_FUNDO_PAGINA, config.COR_FUNDO_PAINEL])
@pytest.mark.parametrize("cor", CORES_DE_TEXTO_E_SERIE)
def test_texto_e_series_tem_contraste_minimo_sobre_os_fundos(cor, fundo):
    assert _contraste(cor, fundo) >= 4.5


def test_template_grafico_fundo_transparente_e_grade_do_tema():
    import plotly.graph_objects as go

    from avaliador_b3.app.main import aplicar_template_grafico

    figura = aplicar_template_grafico(go.Figure(go.Scatter(x=[1, 2], y=[1, 2])))
    assert figura.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figura.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert figura.layout.xaxis.gridcolor == config.COR_GRADE
    assert figura.layout.yaxis.gridcolor == config.COR_GRADE
    assert tuple(figura.layout.colorway) == config.SEQUENCIA_CORES_SERIES
