import pandas as pd
import pytest

from avaliador_b3 import correlacao


def _precos(
    retornos: list[float], preco_inicial: float = 100.0, dia_inicial: int = 0
) -> pd.DataFrame:
    """Constrói uma série de preços cujo retorno diário exato é `retornos`
    — permite montar casos de teste com correlação conhecida de antemão,
    em vez de confiar em dado aleatório."""
    datas = pd.date_range("2025-01-01", periods=len(retornos) + 1, freq="D") + pd.Timedelta(
        days=dia_inicial
    )
    precos = [preco_inicial]
    for retorno in retornos:
        precos.append(precos[-1] * (1 + retorno))
    return pd.DataFrame({"data": datas, "valor": precos})


def _serie_por_offsets(
    offsets: list[int], valores: list[float], coluna: str = "valor"
) -> pd.DataFrame:
    """Série com datas escolhidas por deslocamento (em dias) a partir de
    uma data-base — usada pra simular calendários que não batem
    exatamente entre duas fontes (ex: feriados diferentes)."""
    base = pd.Timestamp("2025-01-01")
    datas = [base + pd.Timedelta(days=offset) for offset in offsets]
    return pd.DataFrame({"data": datas, coluna: valores})


def _serie_ondulada(n: int = 35, base: float = 100.0, coluna: str = "valor") -> pd.DataFrame:
    """Série sintética de ~n dias com variação dia a dia clara (zigue-
    zague + leve tendência), usada nos testes que só precisam de dado
    "normal" (não degenerado) em quantidade suficiente pro mínimo de
    observações padrão."""
    datas = pd.date_range("2025-01-01", periods=n, freq="D")
    valores = [base + ((i % 5) - 2) * 0.7 + i * 0.05 for i in range(n)]
    return pd.DataFrame({"data": datas, coluna: valores})


# --- calcular_correlacao: casos com resposta conhecida de antemão ----------


def test_series_identicas_tem_correlacao_um():
    retornos = [0.01, -0.02, 0.015, -0.005, 0.02, 0.0, -0.01, 0.03]
    df = _precos(retornos)

    resultado = correlacao.calcular_correlacao(df, "valor", df, "valor", minimo_observacoes=3)

    assert resultado["aplicavel"] is True
    assert resultado["correlacao"] == pytest.approx(1.0)
    assert resultado["observacoes"] == len(retornos)


def test_series_opostas_tem_correlacao_menos_um():
    retornos = [0.01, -0.02, 0.015, -0.005, 0.02, 0.01, -0.01, 0.03]
    df_a = _precos(retornos)
    df_b = _precos([-r for r in retornos])

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor", minimo_observacoes=3)

    assert resultado["aplicavel"] is True
    assert resultado["correlacao"] == pytest.approx(-1.0)


# --- alinhamento de datas não coincidentes ----------------------------------


def test_alinhamento_usa_so_as_datas_em_comum():
    # A tem preços nos dias [0,1,2,3] -> retornos nos dias [1,2,3].
    # B tem preços nos dias [0,2,3,4] -> retornos nos dias [2,3,4].
    # Overlap dos retornos: dias {2,3} -> 2 observações, não 3 nem 4.
    df_a = _serie_por_offsets([0, 1, 2, 3], [100.0, 101.0, 99.0, 103.0])
    df_b = _serie_por_offsets([0, 2, 3, 4], [50.0, 52.0, 51.0, 53.0])

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor", minimo_observacoes=2)

    assert resultado["aplicavel"] is True
    assert resultado["observacoes"] == 2


def test_alinhamento_funciona_com_fusos_e_resolucoes_diferentes():
    # Reproduz o formato real das fontes: o yfinance (ação, petróleo)
    # devolve "data" com fuso horário (America/Sao_Paulo); o BCB e o GPR
    # devolvem sem fuso, em resolução diferente. Sem normalizar antes do
    # merge, pandas levanta ValueError por dtypes datetime64
    # incompatíveis — bug real encontrado testando contra PETR4 no
    # navegador, não só um caso hipotético.
    datas_com_fuso = pd.to_datetime(
        ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]
    ).tz_localize("America/Sao_Paulo")
    df_a = pd.DataFrame({"data": datas_com_fuso, "valor": [100.0, 101.0, 99.0, 103.0]})

    datas_sem_fuso = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"])
    df_b = pd.DataFrame({"data": datas_sem_fuso, "valor": [50.0, 52.0, 51.0, 53.0]})

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor", minimo_observacoes=2)

    assert resultado["aplicavel"] is True
    assert resultado["observacoes"] == 3


# --- overlap insuficiente ----------------------------------------------------


def test_overlap_insuficiente_fica_nao_aplicavel():
    # A tem retornos nos dias [1,2,3,4]; B tem retornos nos dias [1,2,20,21]
    # (calendário quase todo diferente) -> só 2 pontos em comum, bem abaixo
    # do mínimo padrão (30).
    df_a = _serie_por_offsets([0, 1, 2, 3, 4], [100.0, 101.0, 99.0, 103.0, 102.0])
    df_b = _serie_por_offsets([0, 1, 2, 20, 21], [50.0, 52.0, 51.0, 60.0, 58.0])

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor")

    assert resultado["aplicavel"] is False
    assert resultado["correlacao"] is None
    assert resultado["observacoes"] == 2
    assert "insuficiente" in resultado["motivo_nao_aplicavel"]
    assert "mínimo 30" in resultado["motivo_nao_aplicavel"]


def test_serie_sem_variacao_fica_nao_aplicavel():
    # B é constante (preço nunca muda) -> retorno sempre zero -> desvio
    # padrão zero -> correlação matematicamente indefinida (NaN).
    df_a = _precos([0.01, -0.02, 0.015, -0.005, 0.02])
    df_b = _precos([0.0, 0.0, 0.0, 0.0, 0.0])

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor", minimo_observacoes=3)

    assert resultado["aplicavel"] is False
    assert resultado["correlacao"] is None
    assert "não varia" in resultado["motivo_nao_aplicavel"]


def test_nivel_zero_num_unico_dia_nao_derruba_a_correlacao_inteira():
    # Bug real encontrado testando contra PETR4 no navegador: o GPR teve
    # uma leitura de 0.0 num único dia (2025-02-09), o que faz o retorno
    # do dia seguinte virar ±infinito (divisão por zero: (novo-0)/0). Um
    # `inf` sozinho contaminava a média/desvio padrão de toda a série e a
    # correlação inteira virava NaN — reportado (incorretamente) como
    # "série sem variação". Aqui, a série B passa por exatamente zero no
    # meio (índice 2), mas varia normalmente antes e depois.
    offsets = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    valores_a = [100.0, 101.0, 99.0, 103.0, 102.0, 105.0, 104.0, 106.0, 108.0]
    valores_b = [50.0, 52.0, 0.0, 48.0, 51.0, 49.0, 53.0, 50.0, 52.0]
    df_a = _serie_por_offsets(offsets, valores_a)
    df_b = _serie_por_offsets(offsets, valores_b)

    resultado = correlacao.calcular_correlacao(df_a, "valor", df_b, "valor", minimo_observacoes=3)

    assert resultado["aplicavel"] is True
    assert resultado["correlacao"] is not None
    # 8 retornos no total, menos o dia contaminado pelo infinito
    # (retorno de 0.0 -> 48.0, indefinido).
    assert resultado["observacoes"] == 7


# --- classificar_magnitude_correlacao ---------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (0.0, "fraca"),
        (0.29, "fraca"),
        (-0.29, "fraca"),
        (0.3, "moderada"),  # limiar exato -> já entra em moderada
        (0.5, "moderada"),
        (0.59, "moderada"),
        (0.6, "forte"),  # limiar exato -> já entra em forte
        (0.9, "forte"),
        (-0.7, "forte"),  # sinal negativo, magnitude que importa é abs()
    ],
)
def test_classificar_magnitude_correlacao(valor, esperado):
    assert correlacao.classificar_magnitude_correlacao(valor) == esperado


# --- calcular_correlacoes_fatores: uma fonte indisponível não trava as outras


def test_uma_fonte_indisponivel_nao_trava_as_outras_duas():
    historico_acao = _serie_ondulada(coluna="Close")
    historico_petroleo = _serie_ondulada(base=80.0, coluna="Close")
    serie_gpr = _serie_ondulada(base=150.0, coluna="GPRD")

    resultados = correlacao.calcular_correlacoes_fatores(
        historico_acao=historico_acao,
        historico_petroleo=historico_petroleo,
        serie_cambio=None,  # simula falha ao buscar o câmbio
        serie_gpr=serie_gpr,
    )

    assert resultados["cambio"]["aplicavel"] is False
    assert "indisponível" in resultados["cambio"]["motivo_nao_aplicavel"]
    assert resultados["petroleo"]["aplicavel"] is True
    assert resultados["gpr"]["aplicavel"] is True
