"""Bloco de "comportamento da ação" da especificação: volatilidade, beta
(vs. Ibovespa) e volume médio negociado. Cálculos puros sobre os
DataFrames de histórico de preço já existentes (ver
`ingest.precos.obter_historico`/`obter_historico_ibovespa`) — este módulo
não busca dado nenhum sozinho.

Pensado pra ser cruzado com o bloco de saúde financeira depois: sinalizar
quando o preço sobe sem sustentação em resultado real (lucro/ROE não
acompanhando a alta do preço) é um trabalho de outra camada, que consome
a saída daqui.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_UTEIS_POR_ANO = 252


def calcular_volume_medio(historico: pd.DataFrame) -> float:
    """Volume médio diário negociado no período coberto pelo histórico."""
    return float(historico["Volume"].mean())


def calcular_volatilidade_anualizada(historico: pd.DataFrame) -> float | None:
    """Desvio padrão dos retornos diários de fechamento, anualizado
    (× sqrt(252) dias úteis/ano — convenção padrão de mercado). Devolve
    None se o histórico não tiver pelo menos 2 preços (não dá pra calcular
    nem um retorno)."""
    retornos = historico["Close"].pct_change().dropna()
    if retornos.empty:
        return None
    return float(retornos.std() * np.sqrt(DIAS_UTEIS_POR_ANO))


def calcular_beta(historico_acao: pd.DataFrame, historico_ibovespa: pd.DataFrame) -> float | None:
    """Beta da ação em relação ao Ibovespa: Cov(retorno_ação,
    retorno_Ibovespa) / Var(retorno_Ibovespa), sobre os retornos diários
    nas datas em comum entre os dois históricos.

    Devolve None se sobrarem menos de 2 retornos pareados após alinhar as
    datas (histórico curto demais ou sem sobreposição), ou se a variância
    do Ibovespa no período for exatamente zero (não dá pra dividir).
    """
    combinado = pd.merge(
        historico_acao[["data", "Close"]],
        historico_ibovespa[["data", "Close"]],
        on="data",
        suffixes=("_acao", "_ibov"),
    ).sort_values("data")

    pareados = pd.DataFrame(
        {
            "acao": combinado["Close_acao"].pct_change(),
            "ibov": combinado["Close_ibov"].pct_change(),
        }
    ).dropna()

    if len(pareados) < 2:
        return None

    variancia_ibov = pareados["ibov"].var()
    if variancia_ibov == 0:
        return None

    covariancia = pareados["acao"].cov(pareados["ibov"])
    return float(covariancia / variancia_ibov)
