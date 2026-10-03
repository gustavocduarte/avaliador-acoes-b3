import math

import pytest

from avaliador_b3.modelos.graham import calcular_valor_justo_graham, reescalar_lpa_vpa


def test_aplicavel_com_lpa_e_vpa_positivos():
    resultado = calcular_valor_justo_graham(lpa=10.35, vpa=37.32)

    assert resultado["aplicavel"] is True
    assert resultado["motivo_nao_aplicavel"] is None
    assert resultado["valor_justo"] == pytest.approx(math.sqrt(22.5 * 10.35 * 37.32))


@pytest.mark.parametrize(
    ("lpa", "vpa"),
    [
        (-1.0, 37.32),
        (10.35, -1.0),
        (0.0, 37.32),
        (10.35, 0.0),
        (-1.0, -1.0),
    ],
)
def test_nao_aplicavel_quando_lpa_ou_vpa_nao_positivo(lpa, vpa):
    resultado = calcular_valor_justo_graham(lpa=lpa, vpa=vpa)

    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert resultado["motivo_nao_aplicavel"] is not None
    assert "LPA>0 e VPA>0" in resultado["motivo_nao_aplicavel"]


@pytest.mark.parametrize(("lpa", "vpa"), [(None, 37.32), (10.35, None), (None, None)])
def test_nao_aplicavel_quando_lpa_ou_vpa_ausente(lpa, vpa):
    resultado = calcular_valor_justo_graham(lpa=lpa, vpa=vpa)

    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert "indisponível" in resultado["motivo_nao_aplicavel"]


def test_nao_levanta_excecao_para_produto_negativo():
    # Garantia explícita: mesmo com produto positivo por dois negativos
    # se cancelarem (LPA<0 e VPA<0), a fórmula não deve "funcionar" —
    # cada fator precisa ser positivo individualmente, não só o produto.
    resultado = calcular_valor_justo_graham(lpa=-10.0, vpa=-5.0)
    assert resultado["aplicavel"] is False


def test_reescalar_lpa_vpa_multiplica_pela_razao_entre_os_numeros_de_acoes():
    lpa, vpa = reescalar_lpa_vpa(5.0, 20.0, acoes_fundamentus=100.0, acoes_em_circulacao=80.0)

    assert lpa == pytest.approx(6.25)
    assert vpa == pytest.approx(25.0)


def test_graham_com_lpa_e_vpa_reescalados_muda_na_mesma_proporcao_do_numero_de_acoes():
    base = calcular_valor_justo_graham(5.0, 20.0)["valor_justo"]
    reescalado = calcular_valor_justo_graham(
        *reescalar_lpa_vpa(5.0, 20.0, acoes_fundamentus=100.0, acoes_em_circulacao=80.0)
    )["valor_justo"]

    assert reescalado == pytest.approx(base * 100 / 80)


@pytest.mark.parametrize(
    ("acoes_fundamentus", "acoes_em_circulacao"),
    [(None, 80.0), (100.0, None), (0.0, 80.0), (100.0, 0.0), (-1.0, 80.0)],
)
def test_reescalar_lpa_vpa_sem_numero_valido_devolve_como_veio(
    acoes_fundamentus, acoes_em_circulacao
):
    assert reescalar_lpa_vpa(5.0, 20.0, acoes_fundamentus, acoes_em_circulacao) == (5.0, 20.0)


def test_reescalar_lpa_vpa_preserva_o_que_estiver_indisponivel():
    assert reescalar_lpa_vpa(None, 20.0, 100.0, 80.0) == (None, pytest.approx(25.0))
    assert reescalar_lpa_vpa(5.0, None, 100.0, 80.0) == (pytest.approx(6.25), None)
