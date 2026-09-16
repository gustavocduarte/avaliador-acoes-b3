"""Funções puras de preparação de dado pros gráficos do dashboard — a
maioria só transforma o dado já buscado no formato que o gráfico precisa,
sem desenhar nada (isso fica em `app/main.py`, com plotly). A exceção é
`montar_mapa_conflitos`, que já devolve a figura pronta (não só dado
preparado) — assim a lógica de montagem (as duas camadas, cor/tamanho por
gravidade) fica testável por estrutura, sem precisar renderizar nada.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from avaliador_b3.config import GOLDSTEIN_SCALE_MINIMO, PONTOS_ESTRATEGICOS_MAPA_CONFLITOS


def normalizar_base_100(serie: pd.Series) -> pd.Series:
    """Normaliza uma série de preços pra base 100 no primeiro valor não
    nulo — desempenho relativo, não preço bruto.

    Necessário pra sobrepor duas séries de escalas muito diferentes (ex:
    uma ação de R$ 30 e o Ibovespa em ~130.000 pontos) no mesmo eixo:
    plotadas em escala bruta, a ação ficaria uma linha reta ilegível ao
    lado do índice.
    """
    primeiro_valor = serie.dropna().iloc[0]
    return serie / primeiro_valor * 100


def agregar_dividendos_por_ano(dividendos: pd.DataFrame) -> pd.DataFrame:
    """Soma os dividendos pagos por ano civil (ano da data de pagamento),
    devolvendo um DataFrame com colunas `ano` (int) e `total` (float),
    ordenado cronologicamente.

    Uma ação sem nenhum dividendo no histórico devolve uma tabela vazia
    (mesmas colunas, zero linhas) — não é um erro, é um resultado válido
    (mesmo critério já usado no método de Bazin: ver `modelos.bazin`).
    """
    if dividendos.empty:
        return pd.DataFrame(columns=["ano", "total"])

    agregado = (
        dividendos.assign(ano=dividendos["data"].dt.year)
        .groupby("ano", as_index=False)["dividendo"]
        .sum()
        .rename(columns={"dividendo": "total"})
    )
    return agregado.sort_values("ano").reset_index(drop=True)


def calcular_dividend_yield_por_ano(
    dividendos_por_ano: pd.DataFrame, historico_precos: pd.DataFrame
) -> pd.DataFrame:
    """Dividend Yield por ano civil: soma de dividendos pagos no ano
    (`dividendos_por_ano`, ver `agregar_dividendos_por_ano`) dividida pelo
    preço médio de fechamento da ação NESSE MESMO ano — não o preço atual
    —, calculado a partir de `historico_precos` (mesmo formato de
    `ingest.precos.obter_historico`, tipicamente `period="max"` pra cobrir
    todos os anos com dividendo pago).

    Devolve um DataFrame com colunas `ano` e `yield_percentual`, contendo
    só os anos de `dividendos_por_ano` que TÊM preço disponível em
    `historico_precos` — um ano sem nenhum candle nesse histórico (ação
    listada há menos tempo que o histórico de dividendos, ou o preço
    "max" veio vazio/indisponível) é omitido, não vira um yield inventado
    com denominador ausente.
    """
    if dividendos_por_ano.empty or historico_precos.empty:
        return pd.DataFrame(columns=["ano", "yield_percentual"])

    preco_medio_por_ano = (
        historico_precos.assign(ano=historico_precos["data"].dt.year)
        .groupby("ano", as_index=False)["Close"]
        .mean()
        .rename(columns={"Close": "preco_medio"})
    )

    yield_por_ano = dividendos_por_ano.merge(preco_medio_por_ano, on="ano", how="inner")
    yield_por_ano["yield_percentual"] = yield_por_ano["total"] / yield_por_ano["preco_medio"] * 100
    return yield_por_ano[["ano", "yield_percentual"]].sort_values("ano").reset_index(drop=True)


NOME_TRACE_PONTOS_ESTRATEGICOS = "Estreitos/canais estratégicos"
NOME_TRACE_EVENTOS = "Eventos de conflito"


def montar_mapa_conflitos(eventos: pd.DataFrame) -> go.Figure:
    """Monta o mapa (globo interativo, projeção ortográfica — rotação por
    clique e arraste nativa do Plotly, sem rotação automática programada)
    do monitor de conflitos, com duas camadas:

    1. Pontos estratégicos (estreitos/canais, ver
       `PONTOS_ESTRATEGICOS_MAPA_CONFLITOS` em config.py) — contexto
       fixo, sempre presente, sem dado ao vivo.
    2. Eventos de conflito do período (`eventos`, mesmo formato de
       `ingest.gdelt.obter_eventos_conflito*`), se houver — cor e
       tamanho do marcador variam pela gravidade (`|GoldsteinScale|`,
       0 a 10; quanto mais próximo de 10 — ou seja, quanto mais negativo
       o Goldstein original —, mais grave, maior e mais intenso o
       marcador).

    Zero eventos não é erro: o mapa mostra só a camada de pontos
    estratégicos nesse caso, sem quebrar."""
    if eventos.empty:
        fig = go.Figure()
    else:
        eventos_mapa = eventos.assign(
            gravidade=eventos["GoldsteinScale"].abs(),
            # Piso de 1.0 só pro TAMANHO do marcador (não pra cor) — um
            # evento com Goldstein bem perto de zero não pode virar um
            # marcador de tamanho zero, invisível no mapa.
            tamanho_marcador=eventos["GoldsteinScale"].abs().clip(lower=1.0),
        )
        fig = px.scatter_geo(
            eventos_mapa,
            lat="ActionGeo_Lat",
            lon="ActionGeo_Long",
            color="gravidade",
            size="tamanho_marcador",
            size_max=18,
            color_continuous_scale="YlOrRd",
            range_color=[0, abs(GOLDSTEIN_SCALE_MINIMO)],
            hover_name="ActionGeo_FullName",
            hover_data={
                "data": True,
                "categoria_cameo": True,
                "GoldsteinScale": ":.1f",
                "gravidade": False,
                "tamanho_marcador": False,
                "ActionGeo_Lat": False,
                "ActionGeo_Long": False,
            },
            labels={
                "data": "Data",
                "categoria_cameo": "Tipo",
                "GoldsteinScale": "Goldstein Score",
                "gravidade": "Gravidade (|Goldstein|)",
            },
        )
        fig.data[0].name = NOME_TRACE_EVENTOS

    fig.add_trace(
        go.Scattergeo(
            lat=[ponto["lat"] for ponto in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS],
            lon=[ponto["lon"] for ponto in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS],
            text=[ponto["nome"] for ponto in PONTOS_ESTRATEGICOS_MAPA_CONFLITOS],
            mode="markers",
            marker={
                "symbol": "diamond",
                "size": 11,
                "color": "#00d4ff",
                "line": {"width": 1, "color": "white"},
            },
            name=NOME_TRACE_PONTOS_ESTRATEGICOS,
            hovertemplate="%{text}<extra></extra>",
        )
    )

    fig.update_geos(
        projection_type="orthographic",
        showland=True,
        landcolor="#2b2b2b",
        showocean=True,
        oceancolor="#0e1117",
        showcountries=True,
        countrycolor="#454545",
        showframe=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 0.0, "xanchor": "left", "x": 0.0},
    )
    return fig
