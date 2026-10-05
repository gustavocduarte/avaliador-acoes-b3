"""Funções puras de preparação de dado pros gráficos do dashboard — só
transforma o dado já buscado no formato que o gráfico precisa, sem
desenhar nada (isso fica em `app/main.py`, com plotly).
"""

from __future__ import annotations

import pandas as pd

MESES_ABREVIADOS_PT_BR = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


# Passos "redondos" candidatos, em meses, pro espaçamento dos ticks —
# só valores que uma pessoa lê como intervalo natural (mensal, bimestral,
# trimestral, semestral, anual, bienal, cada 5 anos), nunca um número
# quebrado tipo "a cada 7 meses".
PASSOS_MENSAIS_CANDIDATOS = (1, 2, 3, 6, 12, 24, 60)


def ticks_mensais_pt_br(datas: pd.Series, max_ticks: int = 8) -> tuple[list, list[str]]:
    """Gera `(tickvals, ticktext)` pro eixo X de um gráfico de série
    temporal do Plotly, com abreviação de mês em português ("Mai/25") em
    vez do padrão em inglês ("May") que o Plotly usa quando não
    configurado — o bundle de Plotly.js que o Streamlit empacota só traz
    o locale en-US (nenhum outro registrado), então passar
    `config={"locale": "pt-BR"}` pro `st.plotly_chart` não teria efeito
    nenhum. Mesmo princípio já usado pra vírgula decimal (`_fmt_bilhoes`
    em app/main.py): não depender de locale automático de sistema/
    biblioteca, traduzir explicitamente no nosso código.

    O passo entre ticks é calculado em MESES, não em dias — usar
    `pd.date_range(periods=...)` (dias corridos) produzia ticks com pulo
    de mês inconsistente (ex: 2/2/1/2/2/1/2 meses num gráfico de 1 ano),
    porque meses têm tamanho diferente. Em vez disso: acha o menor passo
    "redondo" (`PASSOS_MENSAIS_CANDIDATOS`) que mantém a contagem de
    ticks dentro de `max_ticks`, depois anda de `passo` em `passo` meses
    a partir da ÚLTIMA data (a mais recente, geralmente "hoje") pra trás
    — a data mais recente fica sempre como âncora à direita do eixo e o
    espaçamento das anteriores é regular. Datas não precisam corresponder a candles reais do
    histórico, são só posições no eixo contínuo de tempo. Série vazia
    (após remover nulos) devolve duas listas vazias.
    """
    datas_validas = pd.to_datetime(datas).dropna().sort_values()
    if datas_validas.empty:
        return [], []
    inicio, fim = datas_validas.iloc[0], datas_validas.iloc[-1]

    total_meses = (fim.year - inicio.year) * 12 + (fim.month - inicio.month)
    passo = PASSOS_MENSAIS_CANDIDATOS[-1]
    for candidato in PASSOS_MENSAIS_CANDIDATOS:
        if total_meses // candidato + 1 <= max_ticks:
            passo = candidato
            break

    tickvals = []
    atual = fim
    while atual >= inicio:
        tickvals.append(atual)
        atual = atual - pd.DateOffset(months=passo)
    tickvals.reverse()

    ticktext = [f"{MESES_ABREVIADOS_PT_BR[data.month]}/{data.strftime('%y')}" for data in tickvals]
    return tickvals, ticktext


def normalizar_base_100(serie: pd.Series) -> pd.Series:
    """Normaliza uma série de preços pra base 100 no primeiro valor não
    nulo — desempenho relativo, não preço bruto.

    Necessário pra sobrepor duas séries de escalas muito diferentes (ex:
    uma ação de R$ 30 e o Ibovespa em ~130.000 pontos) no mesmo eixo:
    plotadas em escala bruta, a ação ficaria uma linha reta ilegível ao
    lado do índice.

    Três casos sem um "desempenho relativo" bem definido, tratados
    explicitamente:
    - Série vazia: devolve a própria série vazia — nada pra normalizar.
    - Série sem nenhum valor não-nulo: não há primeiro valor pra servir
      de base.
    - Primeiro valor não-nulo igual a zero: base zero tornaria a divisão
      indefinida.

    Nos dois últimos casos, devolve uma série de `NaN` do mesmo índice —
    nunca a série original sem normalizar, pra esta função nunca
    devolver algo que pareça "base 100" sem ser de verdade."""
    if serie.empty:
        return serie
    valores_validos = serie.dropna()
    if valores_validos.empty or valores_validos.iloc[0] == 0:
        return pd.Series(float("nan"), index=serie.index)
    primeiro_valor = valores_validos.iloc[0]
    return serie / primeiro_valor * 100


def agregar_dividendos_por_ano(
    dividendos: pd.DataFrame, ano_corrente: int | None = None
) -> pd.DataFrame:
    """Soma os dividendos pagos por ano civil (ano da data de pagamento),
    devolvendo um DataFrame com colunas `ano` (int), `total` (float) e `parcial`
    (bool), ordenado cronologicamente.

    A série vai do primeiro ano com dividendo até o último (ou até `ano_corrente`, se
    informado e maior): anos sem dividendo no meio aparecem com total zero, em vez de
    sumir. `parcial` marca o ano corrente, que ainda está em andamento.

    Uma ação sem nenhum dividendo no histórico devolve uma tabela vazia
    (mesmas colunas, zero linhas) — não é um erro, é um resultado válido
    (mesmo critério já usado no método de Bazin: ver `modelos.bazin`).
    """
    if dividendos.empty:
        return pd.DataFrame(columns=["ano", "total", "parcial"])

    por_ano = dividendos.assign(ano=dividendos["data"].dt.year).groupby("ano")["dividendo"].sum()
    ultimo_ano = max(int(por_ano.index.max()), ano_corrente or 0)
    anos = range(int(por_ano.index.min()), ultimo_ano + 1)
    agregado = por_ano.reindex(anos, fill_value=0.0).rename("total").rename_axis("ano")
    agregado = agregado.reset_index()
    agregado["total"] = agregado["total"].astype(float)
    agregado["parcial"] = agregado["ano"] == ano_corrente
    return agregado


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
