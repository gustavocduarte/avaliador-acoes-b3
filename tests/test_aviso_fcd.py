import pytest

from avaliador_b3.config import (
    AVISO_FCD_CAUSA_SEM_IDENTIFICAR,
    AVISO_FCD_FECHAMENTO_ALTO,
    AVISO_FCD_FECHAMENTO_FLUXO_PONTUAL,
)
from avaliador_b3.modelos.aviso_fcd import avaliar_fcd_extremo


def _resultado(**ajustes):
    """FCD aplicável e sem nada fora do comum: valor da empresa de R$ 10 bi, deduções de
    R$ 3 bi (30%), perpetuidade em 50%, WACC de 16%, crescimento de 5%, preço de R$ 20."""
    base = {
        "aplicavel": True,
        "valor_justo": 17.5,
        "valor_empresa": 10e9,
        "valor_presente_perpetuidade": 5e9,
        "deducao_divida_liquida": 3e9,
        "deducao_arrendamento": 0.0,
        "deducao_nao_controladores": 0.0,
        "fluxo_base": 1e9,
        "acoes_utilizadas": 400e6,
        "wacc": 0.16,
        "taxa_crescimento_explicita": 0.05,
        "motivo_crescimento_ipca": None,
    }
    return {**base, **ajustes}


PRECO = 20.0


def test_valor_normal_nao_gera_aviso():
    assert avaliar_fcd_extremo(_resultado(), PRECO) is None


def test_fcd_nao_aplicavel_nao_gera_aviso():
    assert avaliar_fcd_extremo({"aplicavel": False, "valor_justo": None}, PRECO) is None


@pytest.mark.parametrize(
    ("valor_justo", "gatilho"),
    [
        (-0.01, "negativo"),
        (0.0, "negativo"),
        (60.0, "alto"),
        (2.0, "baixo"),
        (2.01, None),
        (59.9, None),
    ],
)
def test_gatilhos_pela_razao_ao_preco(valor_justo, gatilho):
    # Preço de R$ 20: 3 vezes é R$ 60 e 10% é R$ 2.
    resultado = avaliar_fcd_extremo(_resultado(valor_justo=valor_justo), PRECO)

    assert (resultado["gatilho"] if resultado else None) == gatilho


def test_sem_preco_so_o_valor_negativo_dispara():
    assert avaliar_fcd_extremo(_resultado(valor_justo=500.0), None) is None
    assert avaliar_fcd_extremo(_resultado(valor_justo=-1.0), None)["gatilho"] == "negativo"


def _causas(**ajustes):
    return avaliar_fcd_extremo(_resultado(valor_justo=60.0, **ajustes), PRECO)["causas"]


def test_causa_deducoes_acima_do_valor_da_empresa():
    assert _causas(deducao_divida_liquida=10e9) == ["K1"]


def test_causa_deducoes_perto_do_valor_da_empresa():
    assert _causas(deducao_divida_liquida=7.5e9) == ["K1b"]
    assert _causas(deducao_divida_liquida=7.4e9) == []


def test_causa_fluxo_alto_sobre_o_valor_de_mercado():
    # Valor de mercado de R$ 2 bi (preço 20 x 100 mi de ações): fluxo de R$ 1 bi é 50%.
    assert _causas(acoes_utilizadas=100e6) == ["K5"]


def test_causa_perpetuidade_pesada():
    assert _causas(valor_presente_perpetuidade=7e9) == ["K3"]
    assert _causas(valor_presente_perpetuidade=6.9e9) == []


def test_causa_wacc_baixo():
    assert _causas(wacc=0.12) == ["K6"]
    assert _causas(wacc=0.121) == []


def test_causas_de_crescimento_no_teto_e_no_piso_ou_perto_dele():
    assert _causas(taxa_crescimento_explicita=0.30) == ["K2a"]
    assert _causas(taxa_crescimento_explicita=-0.15) == ["K2b"]
    assert _causas(taxa_crescimento_explicita=-0.20) == ["K2b"]
    assert _causas(taxa_crescimento_explicita=-0.149) == []


def test_crescimento_estimado_pelo_ipca_nao_conta_como_causa():
    assert _causas(taxa_crescimento_explicita=-0.20, motivo_crescimento_ipca="sem base") == []


def test_causas_aparecem_na_ordem_do_texto():
    causas = _causas(
        deducao_divida_liquida=7.5e9,
        acoes_utilizadas=100e6,
        taxa_crescimento_explicita=-0.17,
        wacc=0.11,
        valor_presente_perpetuidade=7.2e9,
    )

    assert causas == ["K1b", "K5", "K2b", "K6", "K3"]


def test_sem_causa_identificada_usa_o_texto_reserva():
    resultado = avaliar_fcd_extremo(_resultado(valor_justo=60.0), PRECO)

    assert resultado["causas"] == []
    assert AVISO_FCD_CAUSA_SEM_IDENTIFICAR in resultado["texto"]
    assert resultado["texto"].endswith(AVISO_FCD_FECHAMENTO_ALTO)


def test_fechamento_do_fluxo_pontual_so_com_a_causa_do_fluxo():
    com = avaliar_fcd_extremo(_resultado(valor_justo=60.0, acoes_utilizadas=100e6), PRECO)
    sem = avaliar_fcd_extremo(_resultado(valor_justo=60.0), PRECO)

    assert AVISO_FCD_FECHAMENTO_FLUXO_PONTUAL in com["texto"]
    assert AVISO_FCD_FECHAMENTO_FLUXO_PONTUAL not in sem["texto"]


# --- Textos dos quatro exemplos, com as entradas reais de 04/10/2026 ----------------------


def test_texto_beef3_valor_muito_acima_do_preco():
    resultado = _resultado(
        valor_justo=37.861979,
        valor_empresa=52579350599.36,
        valor_presente_perpetuidade=37837584989.46,
        deducao_divida_liquida=14362600000.0,
        deducao_arrendamento=86912000.0,
        deducao_nao_controladores=603222000.0,
        fluxo_base=3563239000.0,
        acoes_utilizadas=991142507.0,
        wacc=0.113192,
        taxa_crescimento_explicita=0.044287,
    )

    aviso = avaliar_fcd_extremo(resultado, 3.88)

    assert aviso["gatilho"] == "alto"
    assert aviso["causas"] == ["K5", "K6", "K3"]
    assert aviso["texto"] == (
        "Valor muito acima do preço. O FCD de R$ 37,86 é 9,8 vezes o preço de R$ 3,88. "
        "Causa provável, nas entradas do modelo. "
        "O fluxo de caixa do ano (R$ 3,6 bi) equivale a 93% do valor de mercado. "
        "O WACC é baixo (11,3%), o que eleva o valor. "
        "72% do valor da empresa (R$ 52,6 bi) está na perpetuidade, depois do 5º ano. "
        "Se o caixa do ano foi pontual (capital de giro ou um ganho não recorrente), o valor "
        "fica inflado. Não é necessariamente uma oportunidade."
    )


def test_texto_goau4_valor_negativo():
    resultado = _resultado(
        valor_justo=-24.839465,
        valor_empresa=11401864102.06,
        valor_presente_perpetuidade=5935383243.6,
        deducao_divida_liquida=8086870000.0,
        deducao_arrendamento=1612345000.0,
        deducao_nao_controladores=34562145000.0,
        fluxo_base=2095239020.0,
        acoes_utilizadas=1322874548.0,
        wacc=0.176901,
        taxa_crescimento_explicita=-0.113887,
    )

    aviso = avaliar_fcd_extremo(resultado, 11.75)

    assert aviso["gatilho"] == "negativo"
    assert aviso["causas"] == ["K1"]
    assert aviso["texto"] == (
        "Valor negativo. O FCD de −R$ 24,84 não quer dizer que a ação valha menos que zero. "
        "Causa provável, nas entradas do modelo. "
        "As deduções somam R$ 44,3 bi (dívida líquida R$ 8,1 bi, arrendamento R$ 1,6 bi e "
        "participação dos não controladores R$ 34,6 bi), 3,9 vezes o valor da empresa pelo "
        "fluxo de caixa (R$ 11,4 bi). O maior peso é a participação dos não controladores "
        "(78% das deduções)."
    )


def test_texto_ggbr4_valor_positivo_minusculo():
    resultado = _resultado(
        valor_justo=0.138728,
        valor_empresa=10192487847.4,
        valor_presente_perpetuidade=5280920565.8,
        deducao_divida_liquida=8117600000.0,
        deducao_arrendamento=1612345000.0,
        deducao_nao_controladores=190194000.0,
        fluxo_base=2098970020.0,
        acoes_utilizadas=1963180639.0,
        wacc=0.173855,
        taxa_crescimento_explicita=-0.169595,
    )

    aviso = avaliar_fcd_extremo(resultado, 26.10)

    assert aviso["gatilho"] == "baixo"
    assert aviso["causas"] == ["K1b", "K2b"]
    assert aviso["texto"] == (
        "Valor muito abaixo do preço. O FCD de R$ 0,14 é 0,5% do preço de R$ 26,10. "
        "Causa provável, nas entradas do modelo. "
        "As deduções (R$ 9,9 bi: dívida líquida R$ 8,1 bi, arrendamento R$ 1,6 bi e "
        "participação dos não controladores R$ 190,2 mi) consomem 97% do valor da empresa "
        "pelo fluxo de caixa (R$ 10,2 bi); sobra pouco para o acionista, e o resultado oscila "
        "muito com pequenas mudanças nas premissas. "
        "O crescimento do fluxo começa em −17% ao ano (perto do piso da faixa, −20%) e converge "
        "para o da perpetuidade em 5 anos."
    )


def test_texto_engi11_valor_negativo_com_crescimento_no_piso():
    resultado = _resultado(
        valor_justo=-68.696355,
        valor_empresa=2306222503.01,
        valor_presente_perpetuidade=1330191948.76,
        deducao_divida_liquida=33228800000.0,
        deducao_arrendamento=151365000.0,
        deducao_nao_controladores=3484877000.0,
        fluxo_base=421394000.0,
        acoes_utilizadas=503066277.0,
        wacc=0.149139,
        taxa_crescimento_explicita=-0.2,
    )

    aviso = avaliar_fcd_extremo(resultado, 55.15)

    assert aviso["gatilho"] == "negativo"
    assert aviso["causas"] == ["K1", "K2b"]
    assert aviso["texto"] == (
        "Valor negativo. O FCD de −R$ 68,70 não quer dizer que a ação valha menos que zero. "
        "Causa provável, nas entradas do modelo. "
        "As deduções somam R$ 36,9 bi (dívida líquida R$ 33,2 bi, arrendamento R$ 151,4 mi e "
        "participação dos não controladores R$ 3,5 bi), 16 vezes o valor da empresa pelo "
        "fluxo de caixa (R$ 2,3 bi). O maior peso é a dívida líquida (90% das deduções). "
        "O crescimento do fluxo começa em −20% ao ano (o piso da faixa) e converge para o da "
        "perpetuidade em 5 anos."
    )


def test_texto_das_causas_de_crescimento_diz_que_o_ritmo_converge_para_a_perpetuidade():
    teto = avaliar_fcd_extremo(_resultado(valor_justo=60.0, taxa_crescimento_explicita=0.30), PRECO)

    assert (
        "O crescimento do fluxo começa em +30% ao ano (o teto da faixa) e converge para o da "
        "perpetuidade em 5 anos." in teto["texto"]
    )
