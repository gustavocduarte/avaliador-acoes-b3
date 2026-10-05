"""Propriedades de finitude: nenhuma entrada NaN ou infinita vira valor justo, e o
combinado, a carteira e o valor de mercado nunca propagam NaN."""

import itertools
import math

import pandas as pd
import pytest

from avaliador_b3.carteira import derivar_cenarios_ticker, simular_investimento_ticker
from avaliador_b3.empresa.valor_mercado import calcular_valor_mercado_e_firma
from avaliador_b3.modelos import fcd
from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin
from avaliador_b3.modelos.combinado import calcular_divergencia_metodos, calcular_valor_combinado
from avaliador_b3.modelos.graham import calcular_valor_justo_graham, reescalar_lpa_vpa
from avaliador_b3.numeros import campos_nao_finitos, nao_finito, numero_finito

NAO_FINITOS = [float("nan"), float("inf"), float("-inf")]
EXTREMOS_FINITOS = [1e308, -1e308, 1e-308, 0.0, -0.0]


def _finito_ou_ausente(valor) -> bool:
    return valor is None or math.isfinite(valor)


def _aplicavel_so_com_valor_finito(resultado: dict, chave: str) -> bool:
    if not resultado["aplicavel"]:
        return resultado[chave] is None and bool(resultado["motivo_nao_aplicavel"])
    return math.isfinite(resultado[chave])


# --- numeros ---


@pytest.mark.parametrize("valor", [1, 1.5, 0, -3.2, 1e308])
def test_numero_finito_aceita_numeros_reais(valor):
    assert numero_finito(valor)
    assert not nao_finito(valor)


@pytest.mark.parametrize("valor", [None, *NAO_FINITOS, "abc", pd.NA])
def test_numero_finito_recusa_ausente_e_invalido(valor):
    assert not numero_finito(valor)


def test_ausente_nao_e_dado_corrompido_mas_nan_e_infinito_e_texto_sao():
    assert not nao_finito(None)
    assert all(nao_finito(v) for v in (*NAO_FINITOS, "abc", pd.NA))


def test_campos_nao_finitos_lista_so_os_invalidos_presentes():
    assert campos_nao_finitos({"a": 1.0, "b": float("nan"), "c": None, "d": float("inf")}) == [
        "b",
        "d",
    ]


# --- Graham ---


@pytest.mark.parametrize(
    ("lpa", "vpa"),
    list(itertools.product([*NAO_FINITOS, *EXTREMOS_FINITOS, 5.0], repeat=2)),
)
def test_graham_nunca_devolve_valor_nao_finito(lpa, vpa):
    resultado = calcular_valor_justo_graham(lpa, vpa)

    assert _aplicavel_so_com_valor_finito(resultado, "valor_justo")


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_graham_com_lpa_ou_vpa_invalido_fica_nao_aplicavel_e_nomeia_o_campo(invalido):
    assert "LPA" in calcular_valor_justo_graham(invalido, 10.0)["motivo_nao_aplicavel"]
    assert "VPA" in calcular_valor_justo_graham(5.0, invalido)["motivo_nao_aplicavel"]


@pytest.mark.parametrize(
    ("acoes_fundamentus", "acoes_em_circulacao"),
    list(itertools.product([*NAO_FINITOS, 100.0], [*NAO_FINITOS, 80.0])),
)
def test_reescalar_nunca_cria_valor_nao_finito_a_partir_de_acoes_invalidas(
    acoes_fundamentus, acoes_em_circulacao
):
    lpa, vpa = reescalar_lpa_vpa(5.0, 20.0, acoes_fundamentus, acoes_em_circulacao)

    assert math.isfinite(lpa) and math.isfinite(vpa)


# --- Bazin ---


def _dividendos_validos() -> pd.DataFrame:
    anos = range(2021, 2027)
    return pd.DataFrame(
        {"data": [pd.Timestamp(year=a, month=6, day=1) for a in anos], "dividendo": [1.0] * 6}
    )


REFERENCIA_BAZIN = pd.Timestamp("2026-10-04")


@pytest.mark.parametrize("posicao", [0, 2, 5])
@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_bazin_com_dividendo_invalido_nos_anos_usados_fica_nao_aplicavel(posicao, invalido):
    dividendos = _dividendos_validos()
    dividendos.loc[posicao, "dividendo"] = invalido

    resultado = calcular_preco_teto_bazin(dividendos, REFERENCIA_BAZIN)

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None
    assert "inválido" in resultado["motivo_nao_aplicavel"]


def test_bazin_ignora_dividendo_invalido_fora_da_janela_usada():
    dividendos = pd.concat(
        [
            pd.DataFrame({"data": [pd.Timestamp("2005-06-01")], "dividendo": [float("nan")]}),
            _dividendos_validos(),
        ],
        ignore_index=True,
    )

    resultado = calcular_preco_teto_bazin(dividendos, REFERENCIA_BAZIN)

    assert resultado["aplicavel"] is True
    assert math.isfinite(resultado["preco_teto"])


# --- FCD ---

BASE_FCD = {
    "fcf_atual": 700.0,
    "fcf_ha_n_anos": 500.0,
    "numero_acoes": 1_000.0,
    "acoes_em_circulacao": 900.0,
    "selic_meta": 0.10,
    "ipca_12m": 0.04,
    "beta": 1.0,
    "divida_liquida": 100.0,
    "divida_liquida_sobre_patrimonio": 0.3,
    "patrimonio_liquido_total": 2_000.0,
    "nao_controladores": 50.0,
    "arrendamento_fora_da_divida": 20.0,
    "receita_atual": 2_000.0,
    "receita_ha_n_anos": 1_500.0,
}


def test_base_do_fcd_e_aplicavel_com_valor_finito():
    resultado = fcd.calcular_valor_justo_fcd(**BASE_FCD)

    assert resultado["aplicavel"] is True
    assert math.isfinite(resultado["valor_justo"])


@pytest.mark.parametrize("campo", sorted(BASE_FCD))
@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_fcd_com_entrada_invalida_fica_nao_aplicavel(campo, invalido):
    resultado = fcd.calcular_valor_justo_fcd(**{**BASE_FCD, campo: invalido})

    assert resultado["aplicavel"] is False
    assert resultado["valor_justo"] is None
    assert "inválido" in resultado["motivo_nao_aplicavel"]


@pytest.mark.parametrize("campo", sorted(BASE_FCD))
@pytest.mark.parametrize("extremo", EXTREMOS_FINITOS)
def test_fcd_com_entrada_extrema_nunca_devolve_valor_nao_finito(campo, extremo):
    resultado = fcd.calcular_valor_justo_fcd(**{**BASE_FCD, campo: extremo})

    assert _aplicavel_so_com_valor_finito(resultado, "valor_justo")


# --- Combinado e divergência ---


def _metodo(valor, chave):
    return {"aplicavel": True, chave: valor, "motivo_nao_aplicavel": None}


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_combinado_deixa_de_fora_o_metodo_que_diz_aplicavel_com_valor_invalido(invalido):
    resultado = calcular_valor_combinado(
        _metodo(invalido, "valor_justo"),
        {"aplicavel": False, "preco_teto": None},
        _metodo(30.0, "valor_justo"),
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_combinado"] == 30.0
    assert resultado["metodos_utilizados"] == ["fcd"]


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_combinado_sem_nenhum_valor_finito_fica_nao_aplicavel(invalido):
    resultado = calcular_valor_combinado(
        _metodo(invalido, "valor_justo"),
        _metodo(invalido, "preco_teto"),
        {"aplicavel": False, "valor_justo": None},
    )

    assert resultado["aplicavel"] is False
    assert resultado["valor_combinado"] is None


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_divergencia_ignora_preco_invalido(invalido):
    resultado = calcular_divergencia_metodos({"graham": 10.0, "fcd": 20.0}, invalido)

    assert resultado["divergencia_percentual"] is None
    assert resultado["diferenca"] == 10.0


# --- Carteira ---


def _linha(**campos):
    base = {
        "ticker": "AAAA4",
        "preco_atual": 20.0,
        "graham_valor_justo": 25.0,
        "bazin_preco_teto": None,
        "fcd_valor_justo": 30.0,
        "valor_combinado": 27.5,
    }
    return {**base, **campos}


@pytest.mark.parametrize("coluna", ["graham_valor_justo", "fcd_valor_justo", "valor_combinado"])
@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_carteira_nunca_projeta_valor_nao_finito(coluna, invalido):
    linha = _linha(**{coluna: invalido})

    cenarios = derivar_cenarios_ticker(linha)
    simulacao = simular_investimento_ticker(linha, 1_000.0)

    for valor in (cenarios["otimista"], cenarios["base"], cenarios["pessimista"]):
        assert _finito_ou_ausente(valor)
    for chave in ("projecao_base", "projecao_otimista", "projecao_pessimista"):
        assert _finito_ou_ausente(simulacao[chave])
    if coluna == "valor_combinado":
        assert cenarios["aplicavel"] is False


def test_carteira_com_preco_infinito_nao_aplicavel():
    simulacao = simular_investimento_ticker(_linha(preco_atual=float("inf")), 1_000.0)

    assert simulacao["aplicavel"] is False
    assert simulacao["preco_atual"] is None


# --- Valor de mercado ---


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_valor_de_mercado_com_preco_ou_acoes_invalidos_fica_ausente(invalido):
    com_preco = calcular_valor_mercado_e_firma(invalido, 100.0, 10.0)
    com_acoes = calcular_valor_mercado_e_firma(5.0, invalido, 10.0)

    assert com_preco["valor_mercado"] is None and com_preco["valor_firma"] is None
    assert com_acoes["valor_mercado"] is None and com_acoes["valor_firma"] is None


@pytest.mark.parametrize("invalido", NAO_FINITOS)
def test_componente_invalido_do_valor_de_firma_conta_como_ausente(invalido):
    resultado = calcular_valor_mercado_e_firma(5.0, 100.0, invalido, nao_controladores=20.0)

    assert "divida_liquida" in resultado["componentes_ausentes"]
    assert resultado["valor_firma"] == pytest.approx(520.0)
