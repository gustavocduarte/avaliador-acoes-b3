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


def _lab(cor: str) -> tuple[float, float, float]:
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(int(cor[i : i + 2], 16) / 255) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _distancia(a: str, b: str) -> float:
    return sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b), strict=True)) ** 0.5


CORES_COM_SIGNIFICADO = [
    config.COR_PRINCIPAL,
    config.COR_POSITIVO,
    config.COR_NEGATIVO,
    config.COR_ALERTA,
    config.COR_NEUTRO,
    config.COR_DESTAQUE,
    config.COR_TEXTO,
    config.COR_TEXTO_SECUNDARIO,
]


def test_cores_das_acoes_sao_sete_hexadecimais_sem_repeticao():
    cores = config.CORES_ACOES_CARTEIRA
    assert len(cores) == 7 == len({c.upper() for c in cores})
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in cores)


@pytest.mark.parametrize("fundo", [config.COR_FUNDO_PAGINA, config.COR_FUNDO_PAINEL])
@pytest.mark.parametrize("cor", config.CORES_ACOES_CARTEIRA)
def test_cores_das_acoes_tem_contraste_minimo_sobre_os_fundos(cor, fundo):
    assert _contraste(cor, fundo) >= 4.5


@pytest.mark.parametrize("cor", config.CORES_ACOES_CARTEIRA)
def test_cores_das_acoes_ficam_longe_das_cores_com_significado(cor):
    # Distância perceptual (CIE Lab, dE) mínima para não parecer o ciano, o verde, o rosa, o
    # amarelo, o cinza, a lima ou o texto (a linha do CDI).
    assert min(_distancia(cor, reservada) for reservada in CORES_COM_SIGNIFICADO) >= 35


def test_cores_das_acoes_se_distinguem_entre_si():
    cores = config.CORES_ACOES_CARTEIRA
    pares = [(a, b) for i, a in enumerate(cores) for b in cores[i + 1 :]]
    assert min(_distancia(a, b) for a, b in pares) >= 10
