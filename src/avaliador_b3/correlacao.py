"""Correlação estatística entre o retorno diário de uma ação e três
fatores externos — petróleo (Brent), câmbio USD/BRL e risco geopolítico
(GPR) — numa janela de 2 anos. Lógica pura: não busca dado nenhum, só
recebe séries já buscadas (por `app/main.py`) e calcula.

Sempre correlaciona RETORNOS/VARIAÇÕES diárias (variação percentual dia a
dia), nunca o nível bruto das séries. Duas séries em tendência (ex: duas
coisas que só sobem com o tempo, ou uma ação em alta e um índice que só
cresce) produzem uma correlação de nível alta e espúria, sem relação real
nenhuma entre elas — a mesma armadilha estatística vale pro GPR, que não
é um preço, mas também tem tendência de longo prazo.
"""

from __future__ import annotations

import pandas as pd

from avaliador_b3.config import (
    LIMIAR_CORRELACAO_FORTE,
    LIMIAR_CORRELACAO_FRACA,
    MINIMO_OBSERVACOES_CORRELACAO,
)


def _normalizar_data(coluna_data: pd.Series) -> pd.Series:
    """Reduz a coluna `data` a um dtype uniforme (datetime64[ns], sem
    fuso, sem hora) antes de qualquer merge entre fontes.

    As quatro fontes deste painel trazem `data` em formatos diferentes:
    o yfinance (ação, petróleo) devolve datetime com fuso
    "America/Sao_Paulo" e resolução de segundos; o BCB e o GPR devolvem
    datetime "naive" (sem fuso) em outra resolução. `DataFrame.merge`
    levanta `ValueError` ao juntar colunas datetime64 com fuso/resolução
    diferentes — normalizar pra um formato comum antes de alinhar as
    séries evita isso, e hora/fuso não importam mesmo pra uma correlação
    de granularidade diária."""
    coluna_data = pd.to_datetime(coluna_data)
    if coluna_data.dt.tz is not None:
        coluna_data = coluna_data.dt.tz_localize(None)
    return coluna_data.dt.normalize().astype("datetime64[ns]")


def _retornos_diarios(df: pd.DataFrame, coluna_valor: str) -> pd.DataFrame:
    """Variação percentual dia a dia de `coluna_valor`, com a coluna
    `data` correspondente (normalizada — ver `_normalizar_data`). A
    primeira linha (sem retorno anterior pra comparar) e quaisquer linhas
    sem valor são descartadas.

    Um nível exatamente zero num único dia (ex: GPR já teve uma leitura
    de 0.0 num dia isolado, 2025-02-09) faz o retorno do dia seguinte
    virar ±infinito (divisão por zero) — um valor `inf` sozinho contamina
    a média/desvio padrão da série inteira e derruba a correlação inteira
    com um "NaN" enganoso. Tratado como dado ausente daquele dia
    específico (não da série toda), igual a um NaN comum."""
    ordenado = df[["data", coluna_valor]].dropna().sort_values("data")
    data_normalizada = _normalizar_data(ordenado["data"])
    retorno = ordenado[coluna_valor].pct_change()
    retorno = retorno.replace([float("inf"), float("-inf")], float("nan"))
    return pd.DataFrame({"data": data_normalizada, "retorno": retorno}).dropna()


def calcular_correlacao(
    df_a: pd.DataFrame,
    coluna_a: str,
    df_b: pd.DataFrame,
    coluna_b: str,
    minimo_observacoes: int = MINIMO_OBSERVACOES_CORRELACAO,
) -> dict:
    """Correlação de Pearson entre os retornos diários de duas séries,
    alinhadas pelas datas em comum (mesmo cuidado já aplicado no cálculo
    de Beta — nem todo calendário de negociação/publicação bate
    exatamente entre duas fontes diferentes).

    Devolve `aplicavel=False` (com `motivo_nao_aplicavel`) se o overlap
    de datas for menor que `minimo_observacoes`, ou se alguma das duas
    séries não variar no período (desvio padrão zero, correlação
    matematicamente indefinida) — nunca um número calculado sobre uma
    amostra pequena ou degenerada demais pra significar algo.
    """
    retornos_a = _retornos_diarios(df_a, coluna_a)
    retornos_b = _retornos_diarios(df_b, coluna_b)

    alinhado = retornos_a.merge(retornos_b, on="data", suffixes=("_a", "_b"))

    if len(alinhado) < minimo_observacoes:
        return {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": len(alinhado),
            "motivo_nao_aplicavel": (
                f"Overlap de datas insuficiente pra uma correlação confiável "
                f"({len(alinhado)} pontos em comum, mínimo {minimo_observacoes})."
            ),
        }

    correlacao = alinhado["retorno_a"].corr(alinhado["retorno_b"])
    if pd.isna(correlacao):
        return {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": len(alinhado),
            "motivo_nao_aplicavel": (
                "Uma das séries não varia no período (desvio padrão zero) — "
                "correlação indefinida."
            ),
        }

    return {
        "aplicavel": True,
        "correlacao": float(correlacao),
        "observacoes": len(alinhado),
        "motivo_nao_aplicavel": None,
    }


def classificar_magnitude_correlacao(correlacao: float) -> str:
    """Lê o valor absoluto da correlação como "fraca", "moderada" ou
    "forte" — cortes documentados em `config.LIMIAR_CORRELACAO_FRACA` e
    `config.LIMIAR_CORRELACAO_FORTE`. Um heurístico de leitura rápida,
    não um teste estatístico."""
    magnitude = abs(correlacao)
    if magnitude >= LIMIAR_CORRELACAO_FORTE:
        return "forte"
    if magnitude >= LIMIAR_CORRELACAO_FRACA:
        return "moderada"
    return "fraca"


def calcular_correlacoes_fatores(
    historico_acao: pd.DataFrame,
    historico_petroleo: pd.DataFrame | None,
    serie_cambio: pd.DataFrame | None,
    serie_gpr: pd.DataFrame | None,
) -> dict:
    """Calcula as três correlações (petróleo, câmbio, GPR) contra o
    retorno diário da ação. Cada uma é independente — uma fonte
    indisponível (`None`, ex: falha ao buscar) ou sem overlap suficiente
    não trava as outras duas, cada resultado carrega seu próprio
    `aplicavel`/`motivo_nao_aplicavel`.
    """
    resultados = {}

    if historico_petroleo is None:
        resultados["petroleo"] = {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": 0,
            "motivo_nao_aplicavel": "Histórico do petróleo (Brent) indisponível.",
        }
    else:
        resultados["petroleo"] = calcular_correlacao(
            historico_acao, "Close", historico_petroleo, "Close"
        )

    if serie_cambio is None:
        resultados["cambio"] = {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": 0,
            "motivo_nao_aplicavel": "Série de câmbio USD/BRL do Banco Central indisponível.",
        }
    else:
        resultados["cambio"] = calcular_correlacao(historico_acao, "Close", serie_cambio, "valor")

    if serie_gpr is None:
        resultados["gpr"] = {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": 0,
            "motivo_nao_aplicavel": "Série diária do índice GPR indisponível.",
        }
    else:
        resultados["gpr"] = calcular_correlacao(historico_acao, "Close", serie_gpr, "GPRD")

    return resultados
