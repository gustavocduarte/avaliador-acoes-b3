import pandas as pd
import pytest

from avaliador_b3 import graficos
from avaliador_b3.config import PONTOS_ESTRATEGICOS_MAPA_CONFLITOS

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


# --- montar_mapa_conflitos ---------------------------------------------------


def _eventos_mapa(linhas: list[dict]) -> pd.DataFrame:
    base = {
        "GLOBALEVENTID": 1,
        "data": pd.Timestamp("2026-09-16 08:00:00"),
        "categoria_cameo": "FIGHT",
        "GoldsteinScale": -5.0,
        "ActionGeo_FullName": "Local de teste",
        "ActionGeo_CountryCode": "RS",
        "ActionGeo_Lat": 55.75,
        "ActionGeo_Long": 37.62,
        "SOURCEURL": "https://example.com",
    }
    return pd.DataFrame([{**base, **linha} for linha in linhas])


def _trace_por_nome(fig, nome: str):
    correspondentes = [trace for trace in fig.data if trace.name == nome]
    assert len(correspondentes) == 1, f"esperava 1 trace chamado {nome!r}, achei {correspondentes}"
    return correspondentes[0]


def test_mapa_com_eventos_tem_duas_camadas():
    eventos = _eventos_mapa(
        [
            {
                "ActionGeo_FullName": "Moscow, Russia",
                "ActionGeo_Lat": 55.75,
                "ActionGeo_Long": 37.62,
            },
            {
                "ActionGeo_FullName": "Tehran, Iran",
                "ActionGeo_Lat": 35.69,
                "ActionGeo_Long": 51.39,
            },
        ]
    )

    fig = graficos.montar_mapa_conflitos(eventos)

    assert len(fig.data) == 2
    trace_eventos = _trace_por_nome(fig, graficos.NOME_TRACE_EVENTOS)
    trace_estrategicos = _trace_por_nome(fig, graficos.NOME_TRACE_PONTOS_ESTRATEGICOS)
    assert trace_eventos.type == "scattergeo"
    assert trace_estrategicos.type == "scattergeo"
    assert list(trace_eventos.lat) == [55.75, 35.69]
    assert list(trace_eventos.lon) == [37.62, 51.39]


def test_mapa_usa_projecao_ortografica():
    fig = graficos.montar_mapa_conflitos(_eventos_mapa([{}]))
    assert fig.layout.geo.projection.type == "orthographic"


def test_mapa_camada_estrategica_tem_os_pontos_de_config():
    fig = graficos.montar_mapa_conflitos(_eventos_mapa([{}]))

    trace_estrategicos = _trace_por_nome(fig, graficos.NOME_TRACE_PONTOS_ESTRATEGICOS)

    assert len(trace_estrategicos.lat) == len(PONTOS_ESTRATEGICOS_MAPA_CONFLITOS)
    assert list(trace_estrategicos.lat) == [p["lat"] for p in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS]
    assert list(trace_estrategicos.lon) == [p["lon"] for p in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS]
    assert list(trace_estrategicos.text) == [p["nome"] for p in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS]
    # símbolo/cor diferentes da camada de eventos — visualmente distinto
    assert trace_estrategicos.marker.symbol == "diamond"


def test_mapa_gravidade_maior_gera_marcador_maior_e_mais_intenso():
    # Goldstein -10 (mais grave) deve ter tamanho/cor de gravidade maior
    # que Goldstein -1 (mais brando) — não precisa ser pixel exato, só a
    # ordem relativa correta.
    eventos = _eventos_mapa(
        [
            {"GLOBALEVENTID": 1, "GoldsteinScale": -10.0},
            {"GLOBALEVENTID": 2, "GoldsteinScale": -1.0},
        ]
    )

    fig = graficos.montar_mapa_conflitos(eventos)
    trace_eventos = _trace_por_nome(fig, graficos.NOME_TRACE_EVENTOS)

    tamanhos = list(trace_eventos.marker.size)
    cores = list(trace_eventos.marker.color)
    assert tamanhos[0] > tamanhos[1]
    assert cores[0] > cores[1]  # cor mapeada pela gravidade (|Goldstein|)


def test_mapa_sem_nenhum_evento_mostra_so_camada_estrategica_sem_erro():
    eventos_vazio = _eventos_mapa([{}]).iloc[0:0]
    assert eventos_vazio.empty

    fig = graficos.montar_mapa_conflitos(eventos_vazio)

    assert len(fig.data) == 1
    assert fig.data[0].name == graficos.NOME_TRACE_PONTOS_ESTRATEGICOS
    assert fig.layout.geo.projection.type == "orthographic"
