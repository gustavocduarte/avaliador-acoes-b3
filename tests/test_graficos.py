import pandas as pd
import pytest

from avaliador_b3 import graficos

# --- ticks_mensais_pt_br ------------------------------------------------------
#
# Ver docstring de `graficos.ticks_mensais_pt_br` pro histórico completo dos
# dois bugs reais (mês em inglês, depois espaçamento irregular) que essa
# função corrige. Os testes abaixo verificam `tickvals[-1]` (a âncora, sempre
# a data mais recente) em vez de `tickvals[0]`, porque o passo em meses anda
# de trás pra frente a partir do fim — o primeiro tick gerado não é mais
# garantido bater exatamente com a primeira data da série.


def test_ticks_mensais_pt_br_traduz_mes_em_portugues():
    datas = pd.Series(pd.to_datetime(["2025-05-01", "2025-09-01"]))

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas, max_ticks=2)

    # 4 meses de intervalo, max_ticks=2 -> passo de 3 meses (menor passo
    # "redondo" que mantém a contagem <= 2): Jun/25, Set/25 (ancorado no
    # fim, Set/25 — não em Mai/25, o início).
    assert ticktext == ["Jun/25", "Set/25"]
    assert tickvals[-1] == pd.Timestamp("2025-09-01")
    assert all("May" not in texto and "Sep" not in texto for texto in ticktext)


def test_ticks_mensais_pt_br_ignora_nulos():
    datas = pd.Series([None, pd.Timestamp("2025-01-01"), pd.NaT, pd.Timestamp("2025-12-01")])

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas)

    # Âncora sempre na data mais recente válida (None/NaT não contam).
    assert tickvals[-1] == pd.Timestamp("2025-12-01")
    assert ticktext[-1] == "Dez/25"
    # O primeiro tick gerado não pode ficar antes da primeira data válida.
    assert tickvals[0] >= pd.Timestamp("2025-01-01")


def test_ticks_mensais_pt_br_serie_vazia_devolve_listas_vazias():
    tickvals, ticktext = graficos.ticks_mensais_pt_br(pd.Series([], dtype="datetime64[ns]"))

    assert tickvals == []
    assert ticktext == []


def test_ticks_mensais_pt_br_data_unica_nao_quebra():
    datas = pd.Series(pd.to_datetime(["2025-07-04"]))

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas)

    assert tickvals == [pd.Timestamp("2025-07-04")]


def _passos_em_meses(tickvals: list) -> list[int]:
    return [
        (depois.year - antes.year) * 12 + (depois.month - antes.month)
        for antes, depois in zip(tickvals, tickvals[1:])
    ]


def test_ticks_mensais_pt_br_passo_constante_janela_de_1_ano():
    # Mesma janela usada em "Preço vs. Ibovespa" (1 ano) — a que mostrou o
    # pulo inconsistente 2/2/1/2/2/1/2 no bug real.
    datas = pd.Series(pd.to_datetime(["2025-09-22", "2026-09-22"]))

    tickvals, _ = graficos.ticks_mensais_pt_br(datas, max_ticks=8)

    passos = _passos_em_meses(tickvals)
    assert len(set(passos)) == 1, f"passo inconsistente entre ticks: {passos}"
    assert tickvals[-1] == pd.Timestamp("2026-09-22")


def test_ticks_mensais_pt_br_passo_constante_janela_de_2_anos():
    # Mesma janela padrão do seletor "Comparando com Petróleo" (2 anos) —
    # a que mostrou o pulo inconsistente 4/3/4/3/3/4/3 no bug real.
    datas = pd.Series(pd.to_datetime(["2024-09-22", "2026-09-22"]))

    tickvals, _ = graficos.ticks_mensais_pt_br(datas, max_ticks=8)

    passos = _passos_em_meses(tickvals)
    assert len(set(passos)) == 1, f"passo inconsistente entre ticks: {passos}"
    assert tickvals[-1] == pd.Timestamp("2026-09-22")


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


def test_normalizar_base_100_serie_vazia_devolve_serie_vazia():
    serie = pd.Series([], dtype=float)

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.empty


def test_normalizar_base_100_serie_toda_nan_devolve_nan_no_mesmo_indice():
    serie = pd.Series([float("nan"), float("nan"), float("nan")], index=[10, 20, 30])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.index.equals(serie.index)
    assert normalizada.isna().all()


def test_normalizar_base_100_primeiro_valor_zero_devolve_nan_no_mesmo_indice():
    serie = pd.Series([0.0, 10.0, 20.0])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.index.equals(serie.index)
    assert normalizada.isna().all()


def test_normalizar_base_100_zero_nao_lider_ainda_conta_como_primeiro_valor_valido():
    # O zero em si (não um NaN) é o primeiro valor NÃO-NULO da série —
    # ainda dispara o mesmo caso acima, mesmo vindo depois de um NaN
    # líder.
    serie = pd.Series([None, 0.0, 10.0])

    normalizada = graficos.normalizar_base_100(serie)

    assert normalizada.isna().all()


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


# --- calcular_dividend_yield_por_ano ------------------------------------------


def _historico_precos(pares: list[tuple[str, float]]) -> pd.DataFrame:
    # tz-aware igual ao que obter_historico devolve de verdade (ver
    # ingest/precos.py) — .dt.year precisa funcionar igual nesse caso.
    datas = pd.to_datetime([data for data, _ in pares], utc=True)
    fechamentos = [fechamento for _, fechamento in pares]
    return pd.DataFrame({"data": datas, "Close": fechamentos})


def test_yield_e_dividendo_do_ano_dividido_pelo_preco_medio_do_ano():
    dividendos_por_ano = pd.DataFrame({"ano": [2024], "total": [2.0]})
    # Preço médio de 2024 = (20 + 30 + 40) / 3 = 30.0
    historico = _historico_precos(
        [("2024-01-01", 20.0), ("2024-06-01", 30.0), ("2024-12-01", 40.0)]
    )

    yield_por_ano = graficos.calcular_dividend_yield_por_ano(dividendos_por_ano, historico)

    assert list(yield_por_ano["ano"]) == [2024]
    assert yield_por_ano["yield_percentual"].iloc[0] == pytest.approx(2.0 / 30.0 * 100)


def test_omite_ano_de_dividendo_sem_preco_historico_disponivel():
    # Ação listada há menos tempo que o histórico de dividendos — 2020 não
    # tem nenhum candle no histórico de preço (ex: period="max" mais curto
    # que o histórico de dividendos) — deve sumir do resultado, não virar
    # um yield com denominador inventado.
    dividendos_por_ano = pd.DataFrame({"ano": [2020, 2024], "total": [1.0, 2.0]})
    historico = _historico_precos([("2024-06-01", 25.0)])

    yield_por_ano = graficos.calcular_dividend_yield_por_ano(dividendos_por_ano, historico)

    assert list(yield_por_ano["ano"]) == [2024]


def test_sem_nenhum_dividendo_devolve_yield_vazio_sem_erro():
    dividendos_por_ano = pd.DataFrame(columns=["ano", "total"])
    historico = _historico_precos([("2024-06-01", 25.0)])

    yield_por_ano = graficos.calcular_dividend_yield_por_ano(dividendos_por_ano, historico)

    assert yield_por_ano.empty
    assert list(yield_por_ano.columns) == ["ano", "yield_percentual"]


def test_sem_nenhum_preco_historico_devolve_yield_vazio_sem_erro():
    # Falha/ausência total do histórico "max" (não só de um ano isolado)
    # não pode quebrar o cálculo — mesmo critério de degradação graciosa
    # usado no resto do projeto.
    dividendos_por_ano = pd.DataFrame({"ano": [2024], "total": [2.0]})
    historico_vazio = pd.DataFrame(columns=["data", "Close"])

    yield_por_ano = graficos.calcular_dividend_yield_por_ano(dividendos_por_ano, historico_vazio)

    assert yield_por_ano.empty

