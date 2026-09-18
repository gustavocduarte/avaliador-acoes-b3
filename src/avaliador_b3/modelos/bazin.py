"""Método Bazin (Preço Teto).

preco_teto = dividendos pagos nos últimos 12 meses / yield mínimo desejado
(6% a.a. — o valor clássico usado por Décio Bazin, `config.YIELD_MINIMO_BAZIN`).

Só aplicável se a empresa tiver "histórico de dividendo relevante". Critério
usado, confirmado em 2026-09-14 em
https://investilize.com.br/blog/metodo-bazin-preco-teto/ ("a empresa deve
ter distribuído lucros ininterruptamente nos últimos 5 anos"): pelo menos
um pagamento em cada um dos últimos `config.ANOS_HISTORICO_MINIMO_BAZIN`
anos civis, sem lacuna. Quando não aplicável, o resultado diz isso
explicitamente em vez de forçar um preço teto sem sentido para uma empresa
que não paga dividendo de forma consistente.
"""

from __future__ import annotations

import pandas as pd

from avaliador_b3.config import ANOS_HISTORICO_MINIMO_BAZIN, YIELD_MINIMO_BAZIN


def _anos_com_dividendo(dividendos: pd.DataFrame, data_referencia: pd.Timestamp) -> set[int]:
    limite = data_referencia - pd.DateOffset(years=ANOS_HISTORICO_MINIMO_BAZIN)
    recentes = dividendos[dividendos["data"] >= limite]
    return set(recentes["data"].dt.year.unique())


def _tem_historico_relevante(dividendos: pd.DataFrame, data_referencia: pd.Timestamp) -> bool:
    """A empresa precisa ter pago dividendo em CADA um dos últimos
    `ANOS_HISTORICO_MINIMO_BAZIN` anos civis — sem lacuna."""
    if dividendos.empty:
        return False
    anos_esperados = {data_referencia.year - i for i in range(1, ANOS_HISTORICO_MINIMO_BAZIN + 1)}
    return anos_esperados.issubset(_anos_com_dividendo(dividendos, data_referencia))


def _dividendos_ultimos_12_meses(dividendos: pd.DataFrame, data_referencia: pd.Timestamp) -> float:
    limite = data_referencia - pd.DateOffset(years=1)
    recentes = dividendos[(dividendos["data"] > limite) & (dividendos["data"] <= data_referencia)]
    return float(recentes["dividendo"].sum())


def calcular_preco_teto_bazin(
    dividendos: pd.DataFrame, data_referencia: pd.Timestamp | None = None
) -> dict:
    """Calcula o preço teto pelo método Bazin.

    `dividendos` é um DataFrame com colunas `data` (datetime) e `dividendo`
    (float) — tipicamente vindo de `ingest.precos.obter_dividendos`.
    `data_referencia` é a data-base para "últimos 12 meses"/"últimos N
    anos"; usa a data atual se não informada (parâmetro existe para permitir
    testes determinísticos).

    Devolve um dict com `aplicavel` (bool), `preco_teto` (float ou None) e
    `motivo_nao_aplicavel` (str ou None, preenchido só quando não aplicável).
    """
    # `ingest.precos.obter_dividendos` devolve datas com timezone (vêm do
    # yfinance); normaliza pra naive aqui, já que só a granularidade de dia
    # importa pra esse cálculo — comparar tz-aware com tz-naive levanta
    # TypeError no pandas.
    #
    # `not dividendos.empty and` é defensivo, não correção de um bug
    # observado: o único produtor real (`ingest.precos.obter_dividendos`)
    # sempre garante a coluna "data" mesmo com o DataFrame vazio (empresa
    # sem nenhum dividendo pago) — mas sem esse guard, um chamador futuro
    # que violasse esse contrato (DataFrame vazio SEM a coluna "data")
    # quebraria aqui com KeyError antes mesmo de chegar no `.empty` já
    # checado dentro de `_tem_historico_relevante`, logo abaixo.
    dividendos = dividendos.copy()
    if not dividendos.empty and isinstance(dividendos["data"].dtype, pd.DatetimeTZDtype):
        dividendos["data"] = dividendos["data"].dt.tz_localize(None)

    if data_referencia is None:
        data_referencia = pd.Timestamp.now()
    elif data_referencia.tzinfo is not None:
        data_referencia = data_referencia.tz_localize(None)

    if not _tem_historico_relevante(dividendos, data_referencia):
        return {
            "aplicavel": False,
            "preco_teto": None,
            "motivo_nao_aplicavel": (
                "Empresa não distribuiu dividendos em cada um dos últimos "
                f"{ANOS_HISTORICO_MINIMO_BAZIN} anos — histórico não é "
                "relevante o suficiente para o método Bazin."
            ),
        }

    dividendo_12_meses = _dividendos_ultimos_12_meses(dividendos, data_referencia)
    if dividendo_12_meses <= 0:
        return {
            "aplicavel": False,
            "preco_teto": None,
            "motivo_nao_aplicavel": "Nenhum dividendo pago nos últimos 12 meses.",
        }

    preco_teto = dividendo_12_meses / YIELD_MINIMO_BAZIN
    return {"aplicavel": True, "preco_teto": preco_teto, "motivo_nao_aplicavel": None}
