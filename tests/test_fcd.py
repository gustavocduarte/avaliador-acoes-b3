import pytest

from avaliador_b3.config import (
    ALIQUOTA_IR_CSLL_PADRAO,
    MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE,
    MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA,
    MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX,
    MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO,
    MOTIVO_FCD_FLUXO_NAO_POSITIVO,
    MOTIVO_FCD_HOLDING_FINANCEIRA,
    MOTIVO_FCD_SEGURADORA,
    MOTIVO_RECEITA_NAO_LIDA,
    MOTIVO_RECEITA_NAO_POSITIVA,
    PREMIO_RISCO_MERCADO_BRASIL,
    SPREAD_CREDITO_PADRAO,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
)
from avaliador_b3.modelos import fcd


def _capex(valor):
    status = "identificado" if valor is not None else "nao_identificado"
    return {"status": status, "valor": valor, "linhas": []}


def _juros(valor):
    return {"valor": valor, "linhas": []}


def test_fluxo_fcd_desconta_capex_e_soma_juros_liquidos_de_imposto():
    fluxo = fcd.calcular_fluxo_caixa_fcd(1_000.0, _capex(300.0), _juros(100.0))

    assert fluxo == pytest.approx(1_000.0 - 300.0 + 100.0 * (1 - ALIQUOTA_IR_CSLL_PADRAO))


def test_fluxo_fcd_sem_juros_e_so_caixa_operacional_menos_capex():
    assert fcd.calcular_fluxo_caixa_fcd(1_000.0, _capex(300.0), _juros(0.0)) == pytest.approx(700.0)


def test_fluxo_fcd_nao_e_calculado_sem_capex_identificado():
    assert fcd.calcular_fluxo_caixa_fcd(1_000.0, _capex(None), _juros(100.0)) is None


def _resultado_cvm(capex_atual=300.0, capex_base=100.0):
    return {
        "cfo_atual": 1_000.0,
        "capex_atual": _capex(capex_atual),
        "juros_pagos_atual": _juros(0.0),
        "cfo_ha_n_anos": 500.0,
        "capex_ha_n_anos": _capex(capex_base),
        "juros_pagos_ha_n_anos": _juros(0.0),
    }


def test_montar_fluxos_fcd_calcula_os_dois_anos():
    fluxos = fcd.montar_fluxos_fcd(_resultado_cvm())

    assert fluxos["fcf_atual"] == pytest.approx(700.0)
    assert fluxos["fcf_ha_n_anos"] == pytest.approx(400.0)
    assert fluxos["motivo_sem_fcf_atual"] is None
    assert fluxos["motivo_sem_fcf_ha_n_anos"] is None


def test_montar_fluxos_fcd_sem_capex_no_ano_de_referencia_traz_o_motivo():
    fluxos = fcd.montar_fluxos_fcd(_resultado_cvm(capex_atual=None))

    assert fluxos["fcf_atual"] is None
    assert fluxos["motivo_sem_fcf_atual"] == MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO


def test_montar_fluxos_fcd_sem_capex_no_ano_base_so_perde_o_crescimento():
    fluxos = fcd.montar_fluxos_fcd(_resultado_cvm(capex_base=None))

    assert fluxos["fcf_atual"] == pytest.approx(700.0)
    assert fluxos["fcf_ha_n_anos"] is None
    assert fluxos["motivo_sem_fcf_ha_n_anos"] == MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX


def test_montar_fluxos_fcd_sem_demonstracao_do_ano_base():
    resultado = _resultado_cvm()
    resultado.update(cfo_ha_n_anos=None, capex_ha_n_anos=None, juros_pagos_ha_n_anos=None)

    fluxos = fcd.montar_fluxos_fcd(resultado)

    assert fluxos["fcf_ha_n_anos"] is None
    assert fluxos["motivo_sem_fcf_ha_n_anos"] == MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE


def test_montar_fluxos_fcd_sem_dado_da_cvm_devolve_tudo_nulo():
    assert fcd.montar_fluxos_fcd(None) == {
        "fcf_atual": None,
        "fcf_ha_n_anos": None,
        "motivo_sem_fcf_atual": None,
        "motivo_sem_fcf_ha_n_anos": None,
        "receita_atual": None,
        "receita_ha_n_anos": None,
        "motivo_sem_receita": None,
    }


def test_fcd_usa_o_motivo_recebido_quando_nao_ha_fluxo_de_referencia():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=None,
        numero_acoes=1_000.0,
        selic_meta=14.0,
        ipca_12m=4.0,
        motivo_sem_fcf_atual=MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO,
    )

    assert resultado["aplicavel"] is False
    assert resultado["motivo_nao_aplicavel"] == MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO


@pytest.mark.parametrize(
    "fcf_ha_n_anos, motivo_recebido, esperado",
    [
        (None, MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX, MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX),
        (None, None, MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE),
        (-50.0, None, MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA),
        (400.0, None, None),
    ],
)
def test_fcd_informa_por_que_o_crescimento_caiu_para_o_ipca(
    fcf_ha_n_anos, motivo_recebido, esperado
):
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=700.0,
        numero_acoes=1_000.0,
        selic_meta=14.0,
        ipca_12m=4.0,
        fcf_ha_n_anos=fcf_ha_n_anos,
        motivo_sem_fcf_ha_n_anos=motivo_recebido,
    )

    assert resultado["aplicavel"] is True
    assert resultado["motivo_crescimento_ipca"] == esperado


def test_proporcao_capex_sobre_caixa_operacional_caso_normal():
    assert fcd.calcular_proporcao_capex_caixa_operacional_percentual(
        1_000.0, _capex(200.0)
    ) == pytest.approx(20.0)


def test_proporcao_capex_sobre_caixa_operacional_pode_passar_de_100_por_cento():
    assert fcd.calcular_proporcao_capex_caixa_operacional_percentual(
        500.0, _capex(2_500.0)
    ) == pytest.approx(500.0)


def test_proporcao_capex_sobre_caixa_operacional_nula_sem_capex_identificado():
    assert fcd.calcular_proporcao_capex_caixa_operacional_percentual(1_000.0, _capex(None)) is None


@pytest.mark.parametrize("caixa_operacional", [0.0, -100.0])
def test_proporcao_capex_sobre_caixa_operacional_nula_com_caixa_nao_positivo(caixa_operacional):
    assert (
        fcd.calcular_proporcao_capex_caixa_operacional_percentual(caixa_operacional, _capex(50.0))
        is None
    )


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


def test_taxa_do_ano_comeca_na_taxa_calculada_e_chega_na_da_perpetuidade_no_ano_final():
    ano_final = fcd.ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD

    assert fcd._taxa_do_ano(1, 0.30, 0.04) == pytest.approx(0.30)
    assert fcd._taxa_do_ano(ano_final, 0.30, 0.04) == pytest.approx(0.04)
    # Passos iguais entre o primeiro e o último ano (convergência linear).
    taxas = [fcd._taxa_do_ano(ano, 0.30, 0.04) for ano in range(1, ano_final + 1)]
    passos = [taxas[i + 1] - taxas[i] for i in range(len(taxas) - 1)]
    assert passos == pytest.approx([passos[0]] * len(passos))
    assert passos[0] < 0


def test_taxa_do_ano_negativa_converge_para_cima_ate_a_da_perpetuidade():
    taxas = [fcd._taxa_do_ano(ano, -0.10, 0.04) for ano in range(1, 6)]

    assert taxas[0] == pytest.approx(-0.10)
    assert taxas[-1] == pytest.approx(0.04)
    assert taxas == sorted(taxas)  # sobe a cada ano


def test_taxa_do_ano_igual_a_da_perpetuidade_nao_muda_nada():
    assert [fcd._taxa_do_ano(ano, 0.04, 0.04) for ano in range(1, 8)] == pytest.approx([0.04] * 7)


def test_taxa_do_ano_depois_do_ano_final_fica_na_da_perpetuidade():
    assert fcd._taxa_do_ano(fcd.ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD + 3, 0.30, 0.04) == (
        pytest.approx(0.04)
    )


def _valor_justo_esperado_com_taxas(fcf_atual, taxas_por_ano, wacc, g_perpetuidade, acoes):
    fcf = fcf_atual
    pv_explicito = 0.0
    for ano, taxa in enumerate(taxas_por_ano, start=1):
        fcf *= 1 + taxa
        pv_explicito += fcf / (1 + wacc) ** ano
    terminal = fcf * (1 + g_perpetuidade) / (wacc - g_perpetuidade)
    return (pv_explicito + terminal / (1 + wacc) ** len(taxas_por_ano)) / acoes


def test_fcd_com_crescimento_positivo_converge_para_a_perpetuidade_e_vale_menos_que_sem_convergir():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=500.0,  # CAGR de 14,9% ao ano
        divida_liquida_sobre_patrimonio=None,
    )
    g0, g_inf, wacc = (
        resultado["taxa_crescimento_explicita"],
        resultado["taxa_crescimento_perpetuidade"],
        resultado["wacc"],
    )
    taxas = [g0 + (g_inf - g0) * (ano - 1) / 4 for ano in range(1, 6)]

    assert resultado["valor_justo"] == pytest.approx(
        _valor_justo_esperado_com_taxas(1000.0, taxas, wacc, g_inf, 100.0)
    )
    sem_convergencia = _valor_justo_esperado_com_taxas(1000.0, [g0] * 5, wacc, g_inf, 100.0)
    assert resultado["valor_justo"] < sem_convergencia


def test_fcd_com_crescimento_negativo_converge_para_cima_e_vale_mais_que_sem_convergir():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=1500.0,  # CAGR de −8,0% ao ano
        divida_liquida_sobre_patrimonio=None,
    )
    g0, g_inf, wacc = (
        resultado["taxa_crescimento_explicita"],
        resultado["taxa_crescimento_perpetuidade"],
        resultado["wacc"],
    )
    assert g0 < 0
    taxas = [g0 + (g_inf - g0) * (ano - 1) / 4 for ano in range(1, 6)]

    assert resultado["valor_justo"] == pytest.approx(
        _valor_justo_esperado_com_taxas(1000.0, taxas, wacc, g_inf, 100.0)
    )
    sem_convergencia = _valor_justo_esperado_com_taxas(1000.0, [g0] * 5, wacc, g_inf, 100.0)
    assert resultado["valor_justo"] > sem_convergencia


def test_fcd_com_crescimento_igual_ao_da_perpetuidade_nao_muda_com_a_convergencia():
    # Sem histórico, o crescimento explícito é o IPCA, igual ao da perpetuidade.
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        divida_liquida_sobre_patrimonio=None,
    )
    g_inf, wacc = resultado["taxa_crescimento_perpetuidade"], resultado["wacc"]
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(g_inf)

    assert resultado["valor_justo"] == pytest.approx(
        _valor_justo_esperado_com_taxas(1000.0, [g_inf] * 5, wacc, g_inf, 100.0)
    )


def test_taxa_crescimento_receita_calcula_o_cagr():
    assert fcd._taxa_crescimento_receita(1610.51, 1000.0) == pytest.approx(0.10)


@pytest.mark.parametrize(
    ("receita_atual", "receita_ha_n_anos"),
    [(None, 1000.0), (1000.0, None), (0.0, 1000.0), (1000.0, 0.0), (-5.0, 1000.0)],
)
def test_taxa_crescimento_receita_none_quando_falta_ou_nao_e_positiva(
    receita_atual, receita_ha_n_anos
):
    assert fcd._taxa_crescimento_receita(receita_atual, receita_ha_n_anos) is None


def _fcd_com_receita(
    receita_atual, receita_ha_n_anos, fcf_atual=372.0, fcf_ha_n_anos=100.0, **extra
):
    # fluxo de 100 para 372 em 5 anos: CAGR de 30% ao ano (no teto atual)
    return fcd.calcular_valor_justo_fcd(
        fcf_atual=fcf_atual,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=fcf_ha_n_anos,
        divida_liquida_sobre_patrimonio=None,
        receita_atual=receita_atual,
        receita_ha_n_anos=receita_ha_n_anos,
        **extra,
    )


def test_receita_limita_o_crescimento_do_fluxo():
    resultado = _fcd_com_receita(receita_atual=1610.51, receita_ha_n_anos=1000.0)  # 10% ao ano

    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.10)
    assert resultado["crescimento_limitado_pela_receita"] is True
    assert resultado["taxa_crescimento_receita"] == pytest.approx(0.10)
    assert resultado["motivo_sem_limite_da_receita"] is None
    # O valor bate com o cálculo manual com crescimento de 10% convergindo para a perpetuidade.
    g_inf, wacc = resultado["taxa_crescimento_perpetuidade"], resultado["wacc"]
    taxas = [0.10 + (g_inf - 0.10) * (ano - 1) / 4 for ano in range(1, 6)]
    assert resultado["valor_justo"] == pytest.approx(
        _valor_justo_esperado_com_taxas(372.0, taxas, wacc, g_inf, 100.0)
    )


def test_receita_acima_do_crescimento_do_fluxo_nao_muda_nada():
    sem_receita = _fcd_com_receita(receita_atual=None, receita_ha_n_anos=None)
    com_receita = _fcd_com_receita(receita_atual=5000.0, receita_ha_n_anos=1000.0)  # ~38% ao ano

    assert com_receita["crescimento_limitado_pela_receita"] is False
    assert com_receita["taxa_crescimento_explicita"] == pytest.approx(
        sem_receita["taxa_crescimento_explicita"]
    )
    assert com_receita["valor_justo"] == pytest.approx(sem_receita["valor_justo"])
    assert com_receita["motivo_sem_limite_da_receita"] is None


def test_receita_indisponivel_mantem_a_regra_atual_e_traz_o_motivo():
    resultado = _fcd_com_receita(
        receita_atual=None, receita_ha_n_anos=1000.0, motivo_sem_receita="DRE ausente"
    )

    assert resultado["taxa_crescimento_explicita"] == pytest.approx(TAXA_CRESCIMENTO_FCD_MAXIMA)
    assert resultado["crescimento_limitado_pela_receita"] is False
    assert resultado["motivo_sem_limite_da_receita"] == "DRE ausente"


def test_receita_nao_informada_traz_o_motivo_padrao():
    resultado = _fcd_com_receita(receita_atual=None, receita_ha_n_anos=None)

    assert resultado["motivo_sem_limite_da_receita"] == MOTIVO_RECEITA_NAO_LIDA


def test_receita_nao_positiva_mantem_a_regra_atual_com_o_motivo():
    resultado = _fcd_com_receita(receita_atual=-10.0, receita_ha_n_anos=1000.0)

    assert resultado["taxa_crescimento_explicita"] == pytest.approx(TAXA_CRESCIMENTO_FCD_MAXIMA)
    assert resultado["motivo_sem_limite_da_receita"] == MOTIVO_RECEITA_NAO_POSITIVA


def test_faixa_externa_prevalece_sobre_a_receita_muito_negativa():
    # Receita caindo 40% ao ano: o crescimento fica no piso de −20%, não em −40%.
    resultado = _fcd_com_receita(receita_atual=77.76, receita_ha_n_anos=1000.0)

    assert resultado["taxa_crescimento_receita"] < TAXA_CRESCIMENTO_FCD_MINIMA
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(TAXA_CRESCIMENTO_FCD_MINIMA)
    assert resultado["crescimento_limitado_pela_receita"] is True


def test_sem_cagr_do_fluxo_o_ipca_vale_e_a_receita_nao_interfere():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=-400.0,
        divida_liquida_sobre_patrimonio=None,
        receita_atual=2000.0,
        receita_ha_n_anos=1000.0,
    )

    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.04)
    assert resultado["crescimento_limitado_pela_receita"] is False
    assert resultado["motivo_sem_limite_da_receita"] is None


def test_montar_fluxos_fcd_traz_as_receitas_e_o_motivo_da_que_falta():
    resultado = _resultado_cvm()
    resultado["receita_atual"] = {"valor": 2000.0, "versao": 1, "motivo": None}
    resultado["receita_ha_n_anos"] = {"valor": None, "versao": None, "motivo": "sem DRE de 2020"}

    fluxos = fcd.montar_fluxos_fcd(resultado)

    assert fluxos["receita_atual"] == pytest.approx(2000.0)
    assert fluxos["receita_ha_n_anos"] is None
    assert fluxos["motivo_sem_receita"] == "sem DRE de 2020"


def test_montar_fluxos_fcd_sem_receita_lida_usa_o_motivo_padrao():
    fluxos = fcd.montar_fluxos_fcd(_resultado_cvm())  # resultado sem as chaves de receita

    assert fluxos["receita_atual"] is None
    assert fluxos["motivo_sem_receita"] == MOTIVO_RECEITA_NAO_LIDA


@pytest.mark.parametrize("fcf_atual", [-500.0, 0.0])
def test_calcular_valor_justo_fcd_fcf_do_ano_de_referencia_nao_positivo_e_nao_aplicavel(
    fcf_atual,
):
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=fcf_atual,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=400.0,
        divida_liquida_sobre_patrimonio=None,
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert resultado["motivo_nao_aplicavel"] == MOTIVO_FCD_FLUXO_NAO_POSITIVO


def test_calcular_valor_justo_fcd_ano_base_negativo_continua_caindo_para_o_ipca():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=-400.0,
        divida_liquida_sobre_patrimonio=None,
    )
    assert resultado["aplicavel"] is True
    assert resultado["taxa_crescimento_explicita"] == pytest.approx(0.04)


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


# --- EV -> Equity Value via dedução de dívida líquida — ver justificativa
# completa em config.py e no docstring de `calcular_valor_justo_fcd`. Caso
# fabricado equivalente ao verificado à mão pra PETR4 (dívida líquida
# ~R$312,8 bi, ~12,89 bi ações, FCD
# caindo de ~R$118,99 pra ~R$94,72) — não precisa bater esses números
# exatos, só confirmar que a subtração em si está correta.


def test_calcular_valor_justo_fcd_deduz_divida_liquida_do_valor_justo():
    parametros_comuns = dict(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        divida_liquida_sobre_patrimonio=None,
        beta=1.0,
    )
    resultado_sem_divida = fcd.calcular_valor_justo_fcd(**parametros_comuns, divida_liquida=None)
    resultado_com_divida = fcd.calcular_valor_justo_fcd(**parametros_comuns, divida_liquida=5000.0)

    assert resultado_com_divida["aplicavel"] is True
    assert resultado_com_divida["divida_liquida_deduzida"] is True
    # Subtrair dívida líquida do Enterprise Value ANTES de dividir por
    # número de ações reduz o valor justo por ação em exatamente
    # divida_liquida / numero_acoes — propriedade linear, independente
    # das outras premissas (WACC, crescimento) do cálculo.
    assert resultado_com_divida["valor_justo"] == pytest.approx(
        resultado_sem_divida["valor_justo"] - 5000.0 / 100.0
    )


PARAMETROS_FCD_BASE = dict(
    fcf_atual=1000.0,
    numero_acoes=100.0,
    selic_meta=0.10,
    ipca_12m=0.04,
    fcf_ha_n_anos=900.0,
    divida_liquida_sobre_patrimonio=None,
    beta=1.0,
    divida_liquida=5000.0,
)


def test_fcd_desconta_os_nao_controladores_junto_com_a_divida_liquida():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    com_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, nao_controladores=2000.0)

    assert com_ajuste["nao_controladores_deduzidos"] is True
    assert com_ajuste["motivo_sem_nao_controladores"] is None
    # Desconto fixo por ação, independente do WACC e do crescimento.
    assert com_ajuste["valor_justo"] == pytest.approx(sem_ajuste["valor_justo"] - 2000.0 / 100.0)


def test_fcd_com_nao_controladores_zero_nao_muda_o_valor():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    com_zero = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, nao_controladores=0.0)

    assert com_zero["valor_justo"] == pytest.approx(sem_ajuste["valor_justo"])
    assert com_zero["nao_controladores_deduzidos"] is True


def test_fcd_sem_leitura_do_balanco_mantem_o_calculo_e_traz_o_motivo():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    resultado = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, motivo_sem_nao_controladores="A empresa não tem balanço."
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_justo"] == pytest.approx(sem_ajuste["valor_justo"])
    assert resultado["nao_controladores_deduzidos"] is False
    assert resultado["motivo_sem_nao_controladores"] == "A empresa não tem balanço."


def test_fcd_negativo_depois_do_ajuste_nao_e_limitado_a_zero():
    resultado = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, nao_controladores=1e9)

    assert resultado["aplicavel"] is True
    assert resultado["valor_justo"] < 0
    assert resultado["valor_justo"] == pytest.approx(
        fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)["valor_justo"] - 1e9 / 100.0
    )


def test_ajustes_do_balanco_com_leitura_disponivel_trazem_nao_controladores_e_patrimonio_total():
    leitura = {
        "disponivel": True,
        "nao_controladores": 26_942.0,
        "patrimonio_liquido_total": 31_910.0,
        "arrendamento_fora_da_divida": 5_140.0,
        "acoes_em_circulacao": 960.0,
    }

    assert fcd.montar_ajustes_balanco(leitura) == {
        "acoes_em_circulacao": 960.0,
        "motivo_sem_acoes_em_circulacao": None,
        "nao_controladores": 26_942.0,
        "motivo_sem_nao_controladores": None,
        "arrendamento_fora_da_divida": 5_140.0,
        "motivo_sem_arrendamento": None,
        "patrimonio_liquido_total": 31_910.0,
        "motivo_sem_patrimonio_total": None,
    }


def test_ajustes_do_balanco_sem_patrimonio_total_na_leitura_trazem_o_motivo_dele():
    leitura = {"disponivel": True, "nao_controladores": 100.0, "patrimonio_liquido_total": None}

    ajustes = fcd.montar_ajustes_balanco(leitura)

    assert ajustes["nao_controladores"] == 100.0
    assert ajustes["patrimonio_liquido_total"] is None
    assert "patrimônio líquido total não encontrado" in ajustes["motivo_sem_patrimonio_total"]


def test_ajustes_do_balanco_com_leitura_indisponivel_trazem_o_motivo():
    leitura = {"disponivel": False, "motivo": "A empresa não tem balanço consolidado."}

    assert fcd.montar_ajustes_balanco(leitura) == {
        "acoes_em_circulacao": None,
        "motivo_sem_acoes_em_circulacao": "A empresa não tem balanço consolidado.",
        "nao_controladores": None,
        "motivo_sem_nao_controladores": "A empresa não tem balanço consolidado.",
        "arrendamento_fora_da_divida": None,
        "motivo_sem_arrendamento": "A empresa não tem balanço consolidado.",
        "patrimonio_liquido_total": None,
        "motivo_sem_patrimonio_total": "A empresa não tem balanço consolidado.",
    }


def test_ajustes_do_balanco_sem_leitura_trazem_o_motivo_de_nao_lido():
    ajustes = fcd.montar_ajustes_balanco(None)

    assert ajustes["nao_controladores"] is None
    assert "não foi lido" in ajustes["motivo_sem_nao_controladores"]


def test_fcd_soma_o_arrendamento_fora_da_divida_a_divida_liquida():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    com_arrendamento = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, arrendamento_fora_da_divida=3000.0
    )

    assert com_arrendamento["arrendamento_deduzido"] is True
    assert com_arrendamento["motivo_sem_arrendamento"] is None
    assert com_arrendamento["valor_justo"] == pytest.approx(
        sem_ajuste["valor_justo"] - 3000.0 / 100.0
    )


def test_arrendamento_nao_entra_nos_pesos_do_wacc():
    base = {**PARAMETROS_FCD_BASE, "divida_liquida_sobre_patrimonio": 1.0}
    sem_arrendamento = fcd.calcular_valor_justo_fcd(**base, patrimonio_liquido_total=25_000.0)
    com_arrendamento = fcd.calcular_valor_justo_fcd(
        **base, patrimonio_liquido_total=25_000.0, arrendamento_fora_da_divida=5_000.0
    )

    # Só a dívida líquida (5.000) ÷ patrimônio total (25.000): arrendamento não pesa.
    assert com_arrendamento["divida_liquida_sobre_patrimonio_utilizada"] == pytest.approx(0.2)
    assert com_arrendamento["wacc"] == pytest.approx(sem_arrendamento["wacc"])
    assert com_arrendamento["valor_justo"] == pytest.approx(
        sem_arrendamento["valor_justo"] - 5_000.0 / 100.0
    )


def test_arrendamento_reduz_o_valor_do_acionista_com_os_pesos_do_patrimonio_total():
    sem_arrendamento = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, patrimonio_liquido_total=25_000.0
    )
    com_arrendamento = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE,
        patrimonio_liquido_total=25_000.0,
        arrendamento_fora_da_divida=2_000.0,
    )

    assert com_arrendamento["valor_justo"] < sem_arrendamento["valor_justo"]


def test_arrendamento_nao_muda_os_pesos_quando_so_vale_a_razao_do_fundamentus():
    base = {**PARAMETROS_FCD_BASE, "divida_liquida_sobre_patrimonio": 1.0}

    resultado = fcd.calcular_valor_justo_fcd(**base, arrendamento_fora_da_divida=5_000.0)

    assert resultado["divida_liquida_sobre_patrimonio_utilizada"] == 1.0


def test_arrendamento_zero_nao_muda_o_valor():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    com_zero = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, arrendamento_fora_da_divida=0.0)

    assert com_zero["valor_justo"] == pytest.approx(sem_ajuste["valor_justo"])
    assert com_zero["arrendamento_deduzido"] is True


def test_sem_leitura_do_arrendamento_o_calculo_segue_e_traz_o_motivo():
    sem_ajuste = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    resultado = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, motivo_sem_arrendamento="A empresa não tem balanço."
    )

    assert resultado["valor_justo"] == pytest.approx(sem_ajuste["valor_justo"])
    assert resultado["arrendamento_deduzido"] is False
    assert resultado["motivo_sem_arrendamento"] == "A empresa não tem balanço."


def test_arrendamento_sem_divida_liquida_nao_e_deduzido_e_diz_por_que():
    resultado = fcd.calcular_valor_justo_fcd(
        **{**PARAMETROS_FCD_BASE, "divida_liquida": None}, arrendamento_fora_da_divida=3000.0
    )

    assert resultado["arrendamento_deduzido"] is False
    assert "dívida líquida do Fundamentus indisponível" in resultado["motivo_sem_arrendamento"]


def test_ajustes_do_balanco_sem_arrendamento_na_leitura_trazem_o_motivo_dele():
    leitura = {"disponivel": True, "nao_controladores": 0.0, "patrimonio_liquido_total": 10.0}

    ajustes = fcd.montar_ajustes_balanco(leitura)

    assert ajustes["arrendamento_fora_da_divida"] is None
    assert "passivo de arrendamento não encontrado" in ajustes["motivo_sem_arrendamento"]


def test_fcd_usa_as_acoes_em_circulacao_no_lugar_do_numero_do_fundamentus():
    com_fundamentus = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    em_circulacao = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, acoes_em_circulacao=80.0)

    assert em_circulacao["acoes_em_circulacao_utilizadas"] is True
    assert em_circulacao["motivo_sem_acoes_em_circulacao"] is None
    # Mesmo valor do acionista dividido por 80 em vez de 100 ações.
    assert em_circulacao["valor_justo"] == pytest.approx(com_fundamentus["valor_justo"] * 100 / 80)


def test_fcd_sem_acoes_em_circulacao_usa_o_numero_do_fundamentus_e_traz_o_motivo():
    padrao = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    resultado = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, motivo_sem_acoes_em_circulacao="Tesouraria de 53% do capital."
    )

    assert resultado["valor_justo"] == pytest.approx(padrao["valor_justo"])
    assert resultado["acoes_em_circulacao_utilizadas"] is False
    assert resultado["motivo_sem_acoes_em_circulacao"] == "Tesouraria de 53% do capital."


def test_fcd_ignora_acoes_em_circulacao_nao_positivas():
    padrao = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE)
    resultado = fcd.calcular_valor_justo_fcd(**PARAMETROS_FCD_BASE, acoes_em_circulacao=0.0)

    assert resultado["valor_justo"] == pytest.approx(padrao["valor_justo"])
    assert resultado["acoes_em_circulacao_utilizadas"] is False


def test_ajustes_do_balanco_sem_balanco_consolidado_ainda_trazem_as_acoes_em_circulacao():
    leitura = {
        "disponivel": False,
        "motivo": "A empresa não tem balanço consolidado de 30/06/2026 no ITR da CVM.",
        "acoes_em_circulacao": 1338.44e6,
        "motivo_acoes": None,
    }

    ajustes = fcd.montar_ajustes_balanco(leitura)

    assert ajustes["acoes_em_circulacao"] == pytest.approx(1338.44e6)
    assert ajustes["motivo_sem_acoes_em_circulacao"] is None
    assert ajustes["nao_controladores"] is None
    assert "não tem balanço consolidado" in ajustes["motivo_sem_nao_controladores"]


def test_ajustes_do_balanco_com_acoes_descartadas_trazem_o_motivo_da_cvm():
    leitura = {
        "disponivel": True,
        "nao_controladores": 0.0,
        "patrimonio_liquido_total": 10.0,
        "arrendamento_fora_da_divida": 0.0,
        "acoes_em_circulacao": None,
        "motivo_acoes": "Tesouraria de 53% do capital na composição da CVM.",
    }

    ajustes = fcd.montar_ajustes_balanco(leitura)

    assert ajustes["acoes_em_circulacao"] is None
    assert ajustes["motivo_sem_acoes_em_circulacao"].startswith("Tesouraria de 53%")


def test_pesos_do_wacc_usam_divida_liquida_sobre_o_patrimonio_total():
    # Dívida líquida 5.000 sobre patrimônio total 25.000: razão 0,2 (a do Fundamentus, só
    # dos controladores, seria 1,0).
    resultado = fcd.calcular_valor_justo_fcd(
        **{**PARAMETROS_FCD_BASE, "divida_liquida_sobre_patrimonio": 1.0},
        patrimonio_liquido_total=25_000.0,
    )

    assert resultado["divida_liquida_sobre_patrimonio_utilizada"] == pytest.approx(0.2)
    assert resultado["wacc"] == pytest.approx(fcd.calcular_wacc(0.10, 0.2, 1.0))
    assert resultado["wacc"] != pytest.approx(fcd.calcular_wacc(0.10, 1.0, 1.0))
    assert resultado["motivo_sem_patrimonio_total"] is None


def test_patrimonio_total_maior_que_o_dos_controladores_reduz_o_peso_da_divida_e_o_valor():
    base = {**PARAMETROS_FCD_BASE, "divida_liquida_sobre_patrimonio": 1.0}
    so_controladores = fcd.calcular_valor_justo_fcd(**base)
    com_total = fcd.calcular_valor_justo_fcd(**base, patrimonio_liquido_total=25_000.0)

    # Menos peso na dívida barata: WACC maior, valor menor.
    assert com_total["wacc"] > so_controladores["wacc"]
    assert com_total["valor_justo"] < so_controladores["valor_justo"]


@pytest.mark.parametrize(
    ("patrimonio_total", "divida_liquida", "trecho_do_motivo"),
    [
        (None, 5000.0, "patrimônio líquido total não encontrado"),
        (0.0, 5000.0, "zero ou negativo"),
        (-100.0, 5000.0, "zero ou negativo"),
        (25_000.0, None, "dívida líquida do Fundamentus indisponível"),
    ],
)
def test_sem_patrimonio_total_valido_os_pesos_usam_a_razao_do_fundamentus(
    patrimonio_total, divida_liquida, trecho_do_motivo
):
    parametros = {
        **PARAMETROS_FCD_BASE,
        "divida_liquida_sobre_patrimonio": 1.0,
        "divida_liquida": divida_liquida,
    }

    resultado = fcd.calcular_valor_justo_fcd(
        **parametros, patrimonio_liquido_total=patrimonio_total
    )

    assert resultado["divida_liquida_sobre_patrimonio_utilizada"] == 1.0
    assert resultado["wacc"] == pytest.approx(fcd.calcular_wacc(0.10, 1.0, 1.0))
    assert trecho_do_motivo in resultado["motivo_sem_patrimonio_total"]


def test_motivo_recebido_do_chamador_vale_quando_nao_ha_patrimonio_total():
    resultado = fcd.calcular_valor_justo_fcd(
        **PARAMETROS_FCD_BASE, motivo_sem_patrimonio_total="A empresa não tem balanço."
    )

    assert resultado["motivo_sem_patrimonio_total"] == "A empresa não tem balanço."


def test_calcular_valor_justo_fcd_divida_liquida_negativa_aumenta_o_valor():
    # Posição de caixa líquido (mais caixa que dívida): dívida líquida
    # negativa SOMA ao valor justo com subtração normal, sem caso
    # especial — mesma convenção de
    # empresa.valor_mercado.calcular_valor_mercado_e_firma
    # (valor_firma = valor_mercado + divida_liquida, a operação inversa).
    parametros_comuns = dict(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        divida_liquida_sobre_patrimonio=None,
    )
    resultado_sem_divida = fcd.calcular_valor_justo_fcd(**parametros_comuns, divida_liquida=None)
    resultado_caixa_liquido = fcd.calcular_valor_justo_fcd(
        **parametros_comuns, divida_liquida=-2000.0
    )

    assert resultado_caixa_liquido["divida_liquida_deduzida"] is True
    assert resultado_caixa_liquido["valor_justo"] > resultado_sem_divida["valor_justo"]
    assert resultado_caixa_liquido["valor_justo"] == pytest.approx(
        resultado_sem_divida["valor_justo"] + 2000.0 / 100.0
    )


def test_calcular_valor_justo_fcd_sem_divida_liquida_continua_aplicavel_sem_deduzir():
    # divida_liquida=None (default) não deduz nada: aplicável normalmente,
    # valor_justo =
    # Enterprise Value / número de ações, sem nenhuma dedução — e o
    # retorno sinaliza isso explicitamente (divida_liquida_deduzida=False)
    # pra app/main.py avisar na UI. Mesmos parâmetros do teste "caminho
    # feliz sem crescimento" acima, pra reaproveitar a fórmula fechada.
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.0,
        fcf_ha_n_anos=1000.0,  # CAGR = 0 exatamente
        divida_liquida_sobre_patrimonio=None,
    )

    assert resultado["aplicavel"] is True
    assert resultado["divida_liquida_deduzida"] is False

    wacc = resultado["wacc"]
    valor_presente_explicito = sum(
        1000.0 / (1 + wacc) ** ano for ano in range(1, fcd.HORIZONTE_PROJECAO_FCD_ANOS + 1)
    )
    valor_terminal = 1000.0 / wacc
    valor_presente_terminal = valor_terminal / (1 + wacc) ** fcd.HORIZONTE_PROJECAO_FCD_ANOS
    valor_justo_esperado = (valor_presente_explicito + valor_presente_terminal) / 100.0

    assert resultado["valor_justo"] == pytest.approx(valor_justo_esperado)


# --- FCD "não aplicável" pra instituições financeiras (segmento "Bancos") ---
# Critério é segmento_setorial (crosswalk_cnpj, campo oficial
# da B3), não divida_liquida is None — ver justificativa completa em
# config.SEGMENTOS_FCD_NAO_APLICAVEL.


def test_calcular_valor_justo_fcd_banco_e_nao_aplicavel():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        segmento_setorial="Bancos",
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert resultado["motivo_nao_aplicavel"] == fcd.MOTIVO_NAO_APLICAVEL_INSTITUICAO_FINANCEIRA


def test_calcular_valor_justo_fcd_seguradora_e_nao_aplicavel():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        segmento_setorial="Seguradoras",
    )
    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert resultado["motivo_nao_aplicavel"] == MOTIVO_FCD_SEGURADORA


def test_calcular_valor_justo_fcd_itausa_e_nao_aplicavel_por_ticker():
    # ITSA4 está no segmento "Holdings Diversificadas": a exclusão é por
    # ticker, então outra holding do mesmo segmento segue aplicável.
    comum = {
        "fcf_atual": 1000.0,
        "numero_acoes": 100.0,
        "selic_meta": 0.10,
        "ipca_12m": 0.04,
        "fcf_ha_n_anos": 900.0,
        "segmento_setorial": "Holdings Diversificadas",
    }
    itausa = fcd.calcular_valor_justo_fcd(**comum, ticker="ITSA4")
    outra_holding = fcd.calcular_valor_justo_fcd(**comum, ticker="XXXX3")

    assert itausa["aplicavel"] is False
    assert itausa["motivo_nao_aplicavel"] == MOTIVO_FCD_HOLDING_FINANCEIRA
    assert outra_holding["aplicavel"] is True


def test_calcular_valor_justo_fcd_bolsa_continua_aplicavel():
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        segmento_setorial="Serviços Financeiros Diversos",
        ticker="B3SA3",
    )
    assert resultado["aplicavel"] is True
    assert resultado["valor_justo"] is not None


def test_calcular_valor_justo_fcd_segmento_none_continua_aplicavel():
    # segmento_setorial=None (não resolvido — ex: falha ao buscar o
    # catálogo de emissores) segue o cálculo normal, não é tratado como
    # exclusão.
    resultado = fcd.calcular_valor_justo_fcd(
        fcf_atual=1000.0,
        numero_acoes=100.0,
        selic_meta=0.10,
        ipca_12m=0.04,
        fcf_ha_n_anos=900.0,
        segmento_setorial=None,
    )
    assert resultado["aplicavel"] is True
    assert resultado["valor_justo"] is not None
