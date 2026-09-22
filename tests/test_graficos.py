import pandas as pd
import pytest

from avaliador_b3 import carteira, graficos

# --- ticks_mensais_pt_br ------------------------------------------------------
#
# Bug real (2026-09-22, confirmado por screenshot): o eixo X dos gráficos
# "Preço vs. Ibovespa" e "Comparando com Petróleo" mostrava abreviação de mês
# em inglês ("May", "Sep", "Oct") — o Plotly usa o locale en-US por padrão, e
# o bundle de Plotly.js que o Streamlit empacota não traz nenhum outro locale
# registrado, então `config={"locale": "pt-BR"}` não teria efeito. Corrigido
# gerando tickvals/ticktext explicitamente, com mês traduzido em Python.


def test_ticks_mensais_pt_br_traduz_mes_em_portugues():
    datas = pd.Series(pd.to_datetime(["2025-05-10", "2025-09-20"]))

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas, max_ticks=2)

    assert len(tickvals) == 2
    assert ticktext[0] == "Mai/25"
    assert ticktext[-1] == "Set/25"
    assert all("May" not in texto and "Sep" not in texto for texto in ticktext)


def test_ticks_mensais_pt_br_ignora_nulos():
    datas = pd.Series([None, pd.Timestamp("2025-01-01"), pd.NaT, pd.Timestamp("2025-12-31")])

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas)

    assert tickvals[0] == pd.Timestamp("2025-01-01")
    assert tickvals[-1] == pd.Timestamp("2025-12-31")
    assert ticktext[0] == "Jan/25"
    assert ticktext[-1] == "Dez/25"


def test_ticks_mensais_pt_br_serie_vazia_devolve_listas_vazias():
    tickvals, ticktext = graficos.ticks_mensais_pt_br(pd.Series([], dtype="datetime64[ns]"))

    assert tickvals == []
    assert ticktext == []


def test_ticks_mensais_pt_br_data_unica_nao_quebra():
    datas = pd.Series(pd.to_datetime(["2025-07-04"]))

    tickvals, ticktext = graficos.ticks_mensais_pt_br(datas)

    assert tickvals == [pd.Timestamp("2025-07-04")]
    assert ticktext == ["Jul/25"]


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


# --- projetar_curva_composta / projetar_curva_linear / projetar_curva_inflacao


def test_curva_composta_tem_anos_mais_1_pontos_com_extremos_corretos():
    curva = graficos.projetar_curva_composta(1000.0, 0.10, 5)

    assert list(curva["ano"]) == [0, 1, 2, 3, 4, 5]
    assert curva["valor"].iloc[0] == pytest.approx(1000.0)
    assert curva["valor"].iloc[-1] == pytest.approx(1000.0 * 1.10**5)


def test_curva_composta_e_curva_linear_tem_mesmo_ponto_inicial_e_final():
    # Mesmo início/fim, trajetória diferente — é o contraste que o
    # gráfico quer mostrar (efeito dos juros compostos).
    valor_investido, valor_destino, anos = 1000.0, 2000.0, 5
    cagr = carteira.calcular_cagr_implicito(valor_investido, valor_destino, anos)
    assert cagr is not None

    composta = graficos.projetar_curva_composta(valor_investido, cagr, anos)
    linear = graficos.projetar_curva_linear(valor_investido, valor_destino, anos)

    assert composta["valor"].iloc[0] == pytest.approx(linear["valor"].iloc[0])
    assert composta["valor"].iloc[-1] == pytest.approx(linear["valor"].iloc[-1])


def test_curva_composta_e_linear_diferem_nos_pontos_intermediarios():
    # Juros compostos crescem mais devagar no início e aceleram depois —
    # no meio do horizonte, o valor composto fica ABAIXO do linear quando
    # o destino é maior que o investido (convexidade da curva exponencial).
    valor_investido, valor_destino, anos = 1000.0, 2000.0, 5
    cagr = 2 ** (1 / 5) - 1

    composta = graficos.projetar_curva_composta(valor_investido, cagr, anos)
    linear = graficos.projetar_curva_linear(valor_investido, valor_destino, anos)

    meio = 2  # ano intermediário, nem ponta nem fim
    assert composta["valor"].iloc[meio] != pytest.approx(linear["valor"].iloc[meio])
    assert composta["valor"].iloc[meio] < linear["valor"].iloc[meio]


def test_curva_linear_funciona_com_destino_negativo():
    # Cenário pessimista de valor combinado negativo (possível no
    # projeto) não tem CAGR real, mas a reta linear é sempre calculável.
    curva = graficos.projetar_curva_linear(1000.0, -200.0, 5)

    assert curva["valor"].iloc[0] == pytest.approx(1000.0)
    assert curva["valor"].iloc[-1] == pytest.approx(-200.0)
    assert curva["valor"].is_monotonic_decreasing


def test_curva_linear_com_zero_anos_devolve_so_o_ponto_inicial():
    # Regressão defensiva: incremento * t / anos levantaria ZeroDivisionError
    # com anos=0 (mesmo com t=0, numerador zero) — não alcançável hoje (único
    # chamador usa HORIZONTE_PROJECAO_FCD_ANOS=5), mas carteira.py já guarda
    # o mesmo tipo de entrada em calcular_cagr_implicito.
    curva = graficos.projetar_curva_linear(1000.0, 2000.0, 0)

    assert list(curva["ano"]) == [0]
    assert curva["valor"].iloc[0] == pytest.approx(1000.0)


def test_curva_linear_e_composta_zero_anos_produzem_o_mesmo_ponto():
    # Mesma simetria de "mesmo início/fim" que as duas já têm pra anos>0.
    composta = graficos.projetar_curva_composta(1000.0, 0.10, 0)
    linear = graficos.projetar_curva_linear(1000.0, 2000.0, 0)

    pd.testing.assert_frame_equal(composta, linear)


def test_curva_inflacao_e_composta_com_a_taxa_do_ipca():
    curva_inflacao = graficos.projetar_curva_inflacao(1000.0, 0.05, 5)
    curva_composta_equivalente = graficos.projetar_curva_composta(1000.0, 0.05, 5)

    pd.testing.assert_frame_equal(curva_inflacao, curva_composta_equivalente)


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

