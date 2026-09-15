"""Funções puras de preparação de dado pros gráficos do dashboard — não
desenham nada (isso fica em `app/main.py`, com plotly), só transformam o
dado já buscado no formato que o gráfico precisa.
"""

from __future__ import annotations

import pandas as pd


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
