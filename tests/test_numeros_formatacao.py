import pytest

from avaliador_b3.numeros import numero_pt_br, reais_abreviado


@pytest.mark.parametrize(
    ("valor", "casas", "texto"),
    [(1234.5, 1, "1.234,5"), (0.5, 2, "0,50"), (1234567.891, 2, "1.234.567,89")],
)
def test_numero_pt_br(valor, casas, texto):
    assert numero_pt_br(valor, casas) == texto


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (74.5e9, "R$ 74,5 bi"),
        (420.3e6, "R$ 420,3 mi"),
        (1234.5, "R$ 1.234,50"),
        (-2.3e9, "−R$ 2,3 bi"),
    ],
)
def test_reais_abreviado(valor, texto):
    assert reais_abreviado(valor) == texto
