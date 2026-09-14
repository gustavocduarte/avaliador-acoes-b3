import pytest

from avaliador_b3.config import (
    ALIQUOTA_IR_CSLL_PADRAO,
    PREMIO_RISCO_MERCADO_BRASIL,
    SPREAD_CREDITO_PADRAO,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
)
from avaliador_b3.modelos import fcd


def test_custo_capital_proprio_capm():
    assert fcd._custo_capital_proprio(selic_meta=0.10, beta=1.0) == pytest.approx(
        0.10 + PREMIO_RISCO_MERCADO_BRASIL
    )
    assert fcd._custo_capital_proprio(selic_meta=0.10, beta=1.5) == pytest.approx(
        0.10 + 1.5 * PREMIO_RISCO_MERCADO_BRASIL
    )


def test_custo_capital_terceiros_pos_imposto():
    esperado = (0.10 + SPREAD_CREDITO_PADRAO) * (1 - ALIQUOTA_IR_CSLL_PADRAO)
    assert fcd._custo_capital_terceiros_pos_imposto(0.10) == pytest.approx(esperado)


@pytest.mark.parametrize(
    ("de", "we_esperado", "wd_esperado"),
    [
        (None, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (-0.5, 1.0, 0.0),  # posição de caixa líquido -> tratado como não alavancado
        (1.0, 0.5, 0.5),
        (0.5, 1 / 1.5, 0.5 / 1.5),
    ],
)
def test_pesos_estrutura_capital(de, we_esperado, wd_esperado):
    we, wd = fcd._pesos_estrutura_capital(de)
    assert we == pytest.approx(we_esperado)
    assert wd == pytest.approx(wd_esperado)


def test_calcular_wacc_empresa_nao_alavancada_e_igual_a_custo_capital_proprio():
    wacc = fcd.calcular_wacc(selic_meta=0.10, divida_liquida_sobre_patrimonio=None)
    assert wacc == pytest.approx(fcd._custo_capital_proprio(0.10, fcd.BETA_PADRAO))


def test_calcular_wacc_pondera_capital_proprio_e_terceiros():
    wacc = fcd.calcular_wacc(selic_meta=0.10, divida_liquida_sobre_patrimonio=1.0, beta=1.0)
    ke = fcd._custo_capital_proprio(0.10, 1.0)
    kd = fcd._custo_capital_terceiros_pos_imposto(0.10)
    assert wacc == pytest.approx(0.5 * ke + 0.5 * kd)


def test_calcular_wacc_beta_none_cai_para_beta_padrao():
    wacc_sem_beta = fcd.calcular_wacc(selic_meta=0.10, divida_liquida_sobre_patrimonio=None)
    wacc_com_beta_padrao = fcd.calcular_wacc(
        selic_meta=0.10, divida_liquida_sobre_patrimonio=None, beta=fcd.BETA_PADRAO
    )
    assert wacc_sem_beta == pytest.approx(wacc_com_beta_padrao)


def test_calcular_wacc_usa_beta_real_quando_fornecido():
    wacc_beta_baixo = fcd.calcular_wacc(
        selic_meta=0.10, divida_liquida_sobre_patrimonio=None, beta=0.5
    )
    wacc_beta_alto = fcd.calcular_wacc(
        selic_meta=0.10, divida_liquida_sobre_patrimonio=None, beta=1.5
    )
    # Beta maior -> Ke maior (CAPM) -> WACC maior, com tudo mais igual.
    assert wacc_beta_baixo < wacc_beta_alto


def test_taxa_crescimento_explicita_calcula_cagr():
    taxa = fcd._taxa_crescimento_explicita(1000.0, 800.0)
    esperado = (1000.0 / 800.0) ** (1 / fcd.ANOS_HISTORICO_CRESCIMENTO_FCD) - 1
    assert taxa == pytest.approx(esperado)


@pytest.mark.parametrize(
    ("fcf_atual", "fcf_ha_n_anos"),
    [
        (1000.0, None),
        (-100.0, 800.0),
        (1000.0, -50.0),
        (1000.0, 0.0),
        (0.0, 800.0),
    ],
)
def test_taxa_crescimento_explicita_none_quando_nao_calculavel(fcf_atual, fcf_ha_n_anos):
    assert fcd._taxa_crescimento_explicita(fcf_atual, fcf_ha_n_anos) is None


def test_taxa_crescimento_explicita_e_limitada_a_faixa_de_bom_senso():
    # CAGR "explosiva" de um ano-base atipicamente baixo é limitada, não
    # projetada como está — evita compor um outlier de 5 pontos por mais
    # 5 anos adiante.
    assert fcd._taxa_crescimento_explicita(1000.0, 1.0) == pytest.approx(
        TAXA_CRESCIMENTO_FCD_MAXIMA
    )
    assert fcd._taxa_crescimento_explicita(1.0, 1000.0) == pytest.approx(
        TAXA_CRESCIMENTO_FCD_MINIMA
    )


def test_taxa_perpetuidade_usa_ipca_quando_confortavelmente_abaixo_do_wacc():
    assert fcd._taxa_perpetuidade(ipca_12m=0.04, wacc=0.15) == pytest.approx(0.04)


def test_taxa_perpetuidade_trava_abaixo_do_wacc_quando_ipca_e_maior():
    resultado = fcd._taxa_perpetuidade(ipca_12m=0.20, wacc=0.15)
    assert resultado == pytest.approx(0.15 - fcd.MARGEM_SEGURANCA_PERPETUIDADE_FCD)
    assert resultado < 0.15


def test_calcular_valor_justo_fcd_nao_aplicavel_sem_fcf():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=None, numero_acoes=1000.0, selic_meta=0.10, ipca_12m=0.04
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert "fluxo de caixa" in resultado["motivo_nao_aplicavel"].lower()


@pytest.mark.parametrize("numero_acoes", [None, 0, -10])
def test_calcular_valor_justo_fcd_nao_aplicavel_sem_numero_acoes(numero_acoes):
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0, numero_acoes=numero_acoes, selic_meta=0.10, ipca_12m=0.04
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert "ações" in resultado["motivo_nao_aplicavel"].lower()


def test_calcular_valor_justo_fcd_nao_aplicavel_com_wacc_nao_positivo():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=1000.0,
        selic_meta=-0.10,  # Selic extremamente negativa, só pra forçar o cenário no teste
        ipca_12m=0.0,
        divida_liquida_sobre_patrimonio=None,  # WACC = Ke, sem diluir com Kd
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert "WACC" in resultado["motivo_nao_aplicavel"]


def test_calcular_valor_justo_fcd_caminho_feliz_sem_crescimento_bate_formula_fechada():
    # Crescimento explícito e de perpetuidade ambos zero -> fórmula fechada
    # de perpetuidade sem crescimento, verificável independentemente.
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.0,
        fcf_ha_n_anos=1000.0,  # CAGR = 0 exatamente
        divida_liquida_sobre_patrimonio=None,
    )

    assert resultado["aplicavel"] is True
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.0)
    assert resultado["taxa_crescimento_perpetuidade"] == pytest.approx(0.0)

    wacc = resultado["wacc"]
    valor_presente_explicito = sum(
        1000.0 / (1 + wacc) ** ano for ano in range(1, fcd.HORIZONTE_PROJECAO_FCD_ANOS + 1)
    )
    valor_terminal = 1000.0 / wacc
    valor_presente_terminal = valor_terminal / (1 + wacc) ** fcd.HORIZONTE_PROJECAO_FCD_ANOS
    valor_justo_esperado = (valor_presente_explicito + valor_presente_terminal) / 100.0

    assert resultado["valor_justo"] == pytest.approx(valor_justo_esperado)


def test_calcular_valor_justo_fcd_aplicavel_com_fcf_negativo():
    # Empresa com prejuízo atual: o FCD continua aplicável (diferente de
    # Graham/Bazin), só produz um valor justo baixo/negativo.
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=-500.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=-400.0,
        divida_liquida_sobre_patrimonio=None,
    )
    assert resultado["aplicavel"] is True
    assert resultado["valor_justo"] < 0
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.04)  # cai pro IPCA


def test_calcular_valor_justo_fcd_sem_historico_cai_para_ipca():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.05,
        fcf_ha_n_anos=None,
        divida_liquida_sobre_patrimonio=None,
    )
    assert resultado["aplicavel"] is True
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.05)


def test_calcular_valor_justo_fcd_usa_estrutura_de_capital_quando_disponivel():
    resultado_alavancado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        divida_liquida_sobre_patrimonio=0.5,
    )
    resultado_nao_alavancado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        divida_liquida_sobre_patrimonio=None,
    )
    assert resultado_alavancado["wacc"] != resultado_nao_alavancado["wacc"]


def test_calcular_valor_justo_fcd_expoe_beta_utilizado_real_e_padrao():
    resultado_sem_beta = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
    )
    assert resultado_sem_beta["beta_utilizado"] == pytest.approx(fcd.BETA_PADRAO)

    resultado_com_beta = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        beta=0.7,
    )
    assert resultado_com_beta["beta_utilizado"] == pytest.approx(0.7)


def test_calcular_valor_justo_fcd_beta_real_muda_o_valor_justo():
    parametros_comuns = {
        "fcf_atual": 1000.0,
        "numero_acoes": 100.0,
        "selic_meta": 0.10,
        "ipca_12m": 0.04,
        "fcf_ha_n_anos": 900.0,
        "divida_liquida_sobre_patrimonio": None,
    }
    resultado_beta_baixo = fcd.calcular_valor_justo_fcd(**parametros_comuns, beta=0.5)
    resultado_beta_padrao = fcd.calcular_valor_justo_fcd(**parametros_comuns)
    resultado_beta_alto = fcd.calcular_valor_justo_fcd(**parametros_comuns, beta=1.5)

    # Beta menor -> WACC menor -> desconta menos -> valor justo maior, e
    # vice-versa — o valor justo não pode ser igual pra todo mundo mais,
    # já que cada ação tem seu próprio risco em vez de Beta=1,0 fixo.
    assert resultado_beta_baixo["valor_justo"] > resultado_beta_padrao["valor_justo"]
    assert resultado_beta_padrao["valor_justo"] > resultado_beta_alto["valor_justo"]
