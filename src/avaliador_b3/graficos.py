"""Funções puras de preparação de dado pros gráficos do dashboard — só
transforma o dado já buscado no formato que o gráfico precisa, sem
desenhar nada (isso fica em `app/main.py`, com plotly).
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


def projetar_curva_composta(valor_investido: float, cagr: float, anos: int) -> pd.DataFrame:
    """Curva ano a ano de `valor_investido` crescendo a juros compostos a
    `cagr` (decimal, ver `carteira.calcular_cagr_implicito`) por `anos`
    anos: `valor_investido × (1 + cagr) ^ t`, pra `t` de 0 a `anos`
    (inclusive nas duas pontas — `anos + 1` pontos ao todo).

    Devolve um DataFrame com colunas `ano` e `valor`."""
    anos_lista = list(range(anos + 1))
    return pd.DataFrame(
        {"ano": anos_lista, "valor": [valor_investido * (1 + cagr) ** t for t in anos_lista]}
    )


def projetar_curva_linear(valor_investido: float, valor_destino: float, anos: int) -> pd.DataFrame:
    """Curva ano a ano de `valor_investido` crescendo em linha reta
    (crescimento simples, não composto) até `valor_destino` em `anos`
    anos: `valor_investido + (valor_destino - valor_investido) × t/anos`.

    Mesmo ponto inicial (`valor_investido`, ano 0) e final (`valor_destino`,
    ano `anos`) da curva composta pro mesmo cenário — só a trajetória
    intermediária difere, útil pra visualizar o efeito dos juros
    compostos por contraste direto no mesmo gráfico.

    Com `anos=0`, devolve só o ponto inicial (sem trajetória nenhuma pra
    desenhar) em vez de dividir por zero — não alcançável hoje (o único
    chamador usa HORIZONTE_PROJECAO_FCD_ANOS, fixo em 5), guardado por
    consistência com `carteira.calcular_cagr_implicito`, que já trata
    `anos<=0` explicitamente pro mesmo tipo de entrada. Mesmo valor que
    `projetar_curva_composta` já produz naturalmente pra `anos=0`
    (`(1 + cagr) ** 0 == 1`), preservando a simetria entre as duas
    curvas."""
    if anos == 0:
        return pd.DataFrame({"ano": [0], "valor": [valor_investido]})
    anos_lista = list(range(anos + 1))
    incremento = valor_destino - valor_investido
    return pd.DataFrame(
        {
            "ano": anos_lista,
            "valor": [valor_investido + incremento * t / anos for t in anos_lista],
        }
    )


def projetar_curva_inflacao(valor_investido: float, ipca_anual: float, anos: int) -> pd.DataFrame:
    """Curva de referência: `valor_investido` corrigido pelo IPCA atual
    (12 meses, decimal) composto ano a ano — mesma suposição de "IPCA
    constante" (não uma previsão) documentada no resto do projeto (ver
    `_buscar_macro` em app/main.py). Matematicamente idêntica a
    `projetar_curva_composta` (juros compostos é juros compostos,
    independente da taxa representar retorno de ação ou inflação) — nome
    e uso semanticamente diferentes, por isso uma função própria."""
    return projetar_curva_composta(valor_investido, ipca_anual, anos)


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
