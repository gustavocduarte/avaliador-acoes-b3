import pytest

from avaliador_b3.empresa.valor_mercado import calcular_valor_mercado_e_firma


def test_valor_mercado_e_preco_vezes_numero_de_acoes():
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=48.65, numero_acoes=12_888_700_000.0, divida_liquida=312_769_000_000.0
    )

    assert resultado["valor_mercado"] == pytest.approx(48.65 * 12_888_700_000.0)


def test_valor_de_firma_e_valor_de_mercado_mais_divida_liquida():
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=48.65, numero_acoes=12_888_700_000.0, divida_liquida=312_769_000_000.0
    )

    assert resultado["divida_liquida"] == pytest.approx(312_769_000_000.0)
    assert resultado["valor_firma"] == pytest.approx(
        resultado["valor_mercado"] + 312_769_000_000.0
    )


def test_divida_liquida_negativa_posicao_de_caixa_liquido_e_um_valor_real():
    # Empresa com mais caixa que dívida (posição de caixa líquido) tem
    # dívida líquida negativa — um valor real, não tratado como ausente.
    # Valor de Firma fica menor que o Valor de Mercado nesse caso.
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=10.0, numero_acoes=1_000.0, divida_liquida=-500.0
    )

    assert resultado["divida_liquida"] == pytest.approx(-500.0)
    assert resultado["valor_firma"] == pytest.approx(10_000.0 - 500.0)
    assert resultado["valor_firma"] < resultado["valor_mercado"]


def test_sem_preco_atual_nenhum_valor_e_calculavel():
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=None, numero_acoes=1_000.0, divida_liquida=500.0
    )

    assert resultado["valor_mercado"] is None
    assert resultado["valor_firma"] is None
    # Dívida líquida em si não depende de preço nem número de ações —
    # continua disponível mesmo sem Valor de Mercado calculável.
    assert resultado["divida_liquida"] == pytest.approx(500.0)


def test_sem_numero_de_acoes_nenhum_valor_e_calculavel():
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=10.0, numero_acoes=None, divida_liquida=500.0
    )

    assert resultado["valor_mercado"] is None
    assert resultado["valor_firma"] is None


def test_sem_divida_liquida_banco_valor_de_mercado_fica_calculavel_mas_nao_o_de_firma():
    # Caso real: banco (ex: ITUB4) sem "Dív. Líquida" na página do
    # Fundamentus — Valor de Mercado não depende dela, continua
    # calculável; só o Valor de Firma fica indisponível (nunca um valor
    # inventado com peça faltando).
    resultado = calcular_valor_mercado_e_firma(
        preco_atual=10.0, numero_acoes=1_000.0, divida_liquida=None
    )

    assert resultado["valor_mercado"] == pytest.approx(10_000.0)
    assert resultado["divida_liquida"] is None
    assert resultado["valor_firma"] is None
