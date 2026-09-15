import pandas as pd
import pytest

from avaliador_b3 import graficos

# --- normalizar_base_100 -----------------------------------------------------


def test_normalizar_base_100_primeiro_valor_vira_100():
    serie = pd.Series([50.0, 55.0, 45.0])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.iloc[0] == pytest.approx(100.0)


def test_normalizar_base_100_preserva_variacao_percentual():
    # +10% e -10% em relação ao primeiro valor devem virar 110 e 90,
    # não importa a escala bruta (aqui 50; no Ibovespa seria ~130.000).
    serie = pd.Series([50.0, 55.0, 45.0])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.iloc[1] == pytest.approx(110.0)
    assert normalizada.iloc[2] == pytest.approx(90.0)


def test_normalizar_base_100_funciona_em_escalas_bem_diferentes():
    # Mesma variação percentual (ida a +5%, volta à base), escalas bem
    # diferentes (ação ~R$30, índice ~130.000 pontos) -> normalizadas
    # devem bater ponto a ponto.
    acao = pd.Series([30.0, 31.5, 30.0])
    indice = pd.Series([130_000.0, 136_500.0, 130_000.0])

    acao_normalizada = graficos.normalizar_base_100(acao)
    indice_normalizado = graficos.normalizar_base_100(indice)

    assert list(acao_normalizada) == pytest.approx(list(indice_normalizado))


def test_normalizar_base_100_ignora_nulos_iniciais_pro_primeiro_valor():
    # Um NaN líder (ex: primeiro pregão sem fechamento por algum motivo)
    # não deve virar a base — a base é o primeiro valor REAL.
    serie = pd.Series([None, 50.0, 55.0])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.iloc[1] == pytest.approx(100.0)
    assert normalizada.iloc[2] == pytest.approx(110.0)


# --- agregar_dividendos_por_ano ----------------------------------------------


def _dividendos(pares: list[tuple[str, float]]) -> pd.DataFrame:
    datas = pd.to_datetime([data for data, _ in pares])
    valores = [valor for _, valor in pares]
    return pd.DataFrame({"data": datas, "dividendo": valores})


def test_agregar_dividendos_por_ano_soma_pagamentos_do_mesmo_ano():
    dividendos = _dividendos(
        [
            ("2024-03-01", 0.5),
            ("2024-09-01", 0.7),
            ("2025-03-01", 1.0),
        ]
    )

    agregado = graficos.agregar_dividendos_por_ano(dividendos)

    assert list(agregado["ano"]) == [2024, 2025]
    assert list(agregado["total"]) == pytest.approx([1.2, 1.0])


def test_agregar_dividendos_por_ano_ordena_cronologicamente():
    # Histórico fora de ordem (ex: como pode vir de fontes diferentes) —
    # o resultado agregado deve sair ordenado mesmo assim.
    dividendos = _dividendos(
        [
            ("2025-01-01", 1.0),
            ("2023-01-01", 0.5),
            ("2024-01-01", 0.8),
        ]
    )

    agregado = graficos.agregar_dividendos_por_ano(dividendos)

    assert list(agregado["ano"]) == [2023, 2024, 2025]


def test_agregar_dividendos_por_ano_sem_historico_devolve_tabela_vazia():
    # Ação que nunca pagou dividendo (ex: empresa de crescimento) — não é
    # erro, mesmo critério já usado no Bazin.
    dividendos = pd.DataFrame({"data": pd.to_datetime([]), "dividendo": pd.Series(dtype=float)})

    agregado = graficos.agregar_dividendos_por_ano(dividendos)

    assert agregado.empty
    assert list(agregado.columns) == ["ano", "total"]


def test_agregar_dividendos_por_ano_com_fuso_horario():
    # obter_dividendos normaliza a coluna "data" pra UTC (tz-aware) —
    # .dt.year precisa funcionar igual nesse caso.
    dividendos = pd.DataFrame(
        {
            "data": pd.to_datetime(["2024-06-01", "2024-12-01"], utc=True),
            "dividendo": [0.3, 0.4],
        }
    )

    agregado = graficos.agregar_dividendos_por_ano(dividendos)

    assert list(agregado["ano"]) == [2024]
    assert agregado["total"].iloc[0] == pytest.approx(0.7)
