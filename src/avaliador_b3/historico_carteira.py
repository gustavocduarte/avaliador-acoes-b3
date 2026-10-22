"""Histórico da carteira: como o valor investido de hoje teria evoluído no passado.

Só reorganiza preços e índices já buscados (nada é buscado aqui). Todas as linhas partem do valor
investido total de hoje no começo do período:

- por ação: todo o valor aplicado só nessa ação, `valor × preço ÷ preço inicial`;
- carteira: as proporções de hoje compradas no início do período, sem rebalancear;
- inflação (IPCA): o valor corrigido pelo IPCA mensal, com interpolação geométrica dentro do mês;
- CDI: o valor corrigido pelo CDI diário.

O preço é o "Close" ajustado por dividendos e desdobramentos do Yahoo Finance; é desempenho
passado, não previsão.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class HistoricoDaCarteira:
    """Resultado de `montar_historico`: as linhas em R$ (índice de datas) e as ações que ficaram
    de fora de alguma delas."""

    por_acao: dict[str, pd.Series] = field(default_factory=dict)
    carteira: pd.Series | None = None
    # Com histórico, mas menor que o período: têm a linha própria e ficam fora da carteira.
    fora_da_carteira: list[str] = field(default_factory=list)
    # Sem nenhum preço no período: sem linha e fora da carteira.
    sem_historico: list[str] = field(default_factory=list)
    # As que entraram na linha "Carteira".
    na_carteira: list[str] = field(default_factory=list)


def _serie_de_precos(historico: pd.DataFrame) -> pd.Series:
    """ "Close" indexado pela data, em ordem, sem datas repetidas nem preço vazio."""
    serie = historico.dropna(subset=["Close"]).set_index(pd.to_datetime(historico["data"]))["Close"]
    return serie[~serie.index.duplicated(keep="last")].sort_index()


def montar_historico(
    historicos: dict[str, pd.DataFrame],
    pesos: dict[str, float],
    valor_inicial: float,
    anos: int,
    tolerancia_dias: int,
) -> HistoricoDaCarteira:
    """Linhas por ação e da carteira para um período de `anos` até a última data com preço.

    `historicos` é ticker -> DataFrame com `data` e `Close`; `pesos` é a proporção de hoje de cada
    ação (investido da ação ÷ investido total); `valor_inicial` é o investido total de hoje. Uma
    ação cujo primeiro preço vem mais de `tolerancia_dias` depois do início do período tem a linha
    própria a partir da primeira data, mas não entra na carteira; a carteira usa só as ações com
    histórico no período todo, com os pesos refeitos entre elas (a linha começa no valor inicial).
    """
    resultado = HistoricoDaCarteira()
    series = {t: _serie_de_precos(h) for t, h in historicos.items()}
    series = {t: s for t, s in series.items() if not s.empty}
    resultado.sem_historico = [t for t in historicos if t not in series]
    if not series:
        return resultado

    fim = max(s.index.max() for s in series.values())
    inicio = fim - pd.DateOffset(years=anos)
    limite_do_inicio = inicio + pd.Timedelta(days=tolerancia_dias)
    no_periodo = {t: s[s.index >= inicio] for t, s in series.items()}
    no_periodo = {t: s for t, s in no_periodo.items() if not s.empty}
    resultado.sem_historico += [t for t in series if t not in no_periodo]

    for ticker, serie in no_periodo.items():
        resultado.por_acao[ticker] = valor_inicial * serie / serie.iloc[0]

    completas = [t for t, s in no_periodo.items() if s.index[0] <= limite_do_inicio]
    resultado.fora_da_carteira = [t for t in no_periodo if t not in completas]
    peso_total = sum(pesos.get(t, 0.0) for t in completas)
    if completas and peso_total > 0:
        precos = pd.concat([no_periodo[t].rename(t) for t in completas], axis=1).sort_index()
        precos = precos.ffill()
        largada = precos.dropna().index[0] if not precos.dropna().empty else precos.index[0]
        precos = precos[precos.index >= largada]
        relativos = precos / precos.iloc[0]
        proporcoes = pd.Series({t: pesos.get(t, 0.0) / peso_total for t in completas})
        resultado.carteira = valor_inicial * (relativos * proporcoes).sum(axis=1)
        resultado.na_carteira = completas
    return resultado


def _sem_fuso(datas: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """As mesmas datas sem fuso horário (o Yahoo entrega as datas em UTC, e o Banco Central e as
    contas por mês usam datas sem fuso), mantendo o dia que aparece."""
    return datas.tz_localize(None) if datas.tz is not None else datas


def serie_ipca(ipca_mensal: pd.DataFrame, datas: pd.DatetimeIndex, valor_inicial: float):
    """Valor inicial corrigido pelo IPCA nas `datas`, a partir da primeira.

    `ipca_mensal` tem `data` (primeiro dia do mês) e `valor` (variação do mês, em %). Dentro do
    mês, a correção cresce de forma geométrica (`(1 + taxa) ^ (dia ÷ dias do mês)`); depois do
    último mês publicado, a linha fica parada. `None` sem dado ou sem datas.
    """
    if ipca_mensal.empty or len(datas) == 0:
        return None
    datas_originais, datas = datas, _sem_fuso(datas)
    taxas = (
        ipca_mensal.assign(mes=pd.to_datetime(ipca_mensal["data"]).dt.to_period("M"))
        .drop_duplicates("mes", keep="last")
        .set_index("mes")["valor"]
        .sort_index()
        / 100
    )
    fatores = 1 + taxas.to_numpy(dtype=float)
    acumulado = np.cumprod(fatores)
    anterior = np.concatenate([[1.0], acumulado[:-1]])
    meses = taxas.index
    periodos = datas.to_period("M")
    posicao = meses.get_indexer(periodos)
    indice = np.ones(len(datas))
    for i, (data, periodo) in enumerate(zip(datas, periodos, strict=True)):
        if posicao[i] >= 0:
            fracao = data.day / data.days_in_month
            indice[i] = anterior[posicao[i]] * fatores[posicao[i]] ** fracao
        elif periodo > meses[-1]:
            indice[i] = acumulado[-1]
    return pd.Series(valor_inicial * indice / indice[0], index=datas_originais)


def serie_cdi(cdi_diario: pd.DataFrame, datas: pd.DatetimeIndex, valor_inicial: float):
    """Valor inicial corrigido pelo CDI nas `datas`, a partir da primeira.

    `cdi_diario` tem `data` e `valor` (taxa do dia, em %). `None` sem dado ou sem datas.
    """
    if cdi_diario.empty or len(datas) == 0:
        return None
    datas_originais, datas = datas, _sem_fuso(datas)
    taxas = cdi_diario.assign(data=pd.to_datetime(cdi_diario["data"])).drop_duplicates(
        "data", keep="last"
    )
    acumulado = (1 + taxas.set_index("data")["valor"].sort_index() / 100).cumprod()
    nas_datas = acumulado.reindex(acumulado.index.union(datas)).ffill().reindex(datas)
    if nas_datas.isna().all():
        return None  # nenhuma das datas tem taxa: melhor sem a linha do que uma linha reta
    nas_datas = nas_datas.fillna(1.0)
    return pd.Series(
        (valor_inicial * nas_datas / nas_datas.iloc[0]).to_numpy(), index=datas_originais
    )
