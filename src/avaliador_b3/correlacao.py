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


def _niveis_por_data(df: pd.DataFrame, coluna_valor: str, sufixo: str) -> pd.DataFrame:
    """Níveis de `coluna_valor` com a coluna `data` normalizada (ver
    `_normalizar_data`) e renomeada pra `valor_{sufixo}`, pronta pra
    alinhar com outra série pela data ANTES de calcular retorno — mesmo
    cuidado de `empresa.comportamento.calcular_beta`, que junta os
    preços primeiro. Calcular o retorno em cada série no seu próprio
    calendário e só depois juntar pela data (como este módulo fazia
    antes) compara variações de períodos diferentes sempre que os dois
    calendários não batem dia a dia — o GPR tem leitura em fins de
    semana, por exemplo."""
    ordenado = df[["data", coluna_valor]].dropna().sort_values("data")
    return pd.DataFrame(
        {"data": _normalizar_data(ordenado["data"]), f"valor_{sufixo}": ordenado[coluna_valor]}
    )


def calcular_correlacao(
    df_a: pd.DataFrame,
    coluna_a: str,
    df_b: pd.DataFrame,
    coluna_b: str,
    minimo_observacoes: int = MINIMO_OBSERVACOES_CORRELACAO,
) -> dict:
    """Correlação de Pearson entre os retornos diários de duas séries. Os
    NÍVEIS são alinhados pela data em comum primeiro, e o retorno
    percentual é calculado só depois, sobre as séries já pareadas — mesmo
    cuidado de `empresa.comportamento.calcular_beta` (ver
    `_niveis_por_data`): calcular o retorno em cada calendário próprio e
    juntar depois compararia variações de períodos diferentes sempre que
    os dois calendários não batem dia a dia.

    Devolve `aplicavel=False` (com `motivo_nao_aplicavel`) se o overlap
    de datas for menor que `minimo_observacoes`, ou se alguma das duas
    séries não variar no período (desvio padrão zero, correlação
    matematicamente indefinida) — nunca um número calculado sobre uma
    amostra pequena ou degenerada demais pra significar algo.
    """
    niveis_a = _niveis_por_data(df_a, coluna_a, "a")
    niveis_b = _niveis_por_data(df_b, coluna_b, "b")
    combinado = niveis_a.merge(niveis_b, on="data").sort_values("data")

    retornos = pd.DataFrame(
        {
            "retorno_a": combinado["valor_a"].pct_change(),
            "retorno_b": combinado["valor_b"].pct_change(),
        }
    )
    # Nível exatamente zero num dia isolado faz o retorno do dia seguinte
    # virar ±infinito (divisão por zero) — tratado como dado ausente
    # daquele dia específico, igual a um NaN comum, em vez de contaminar
    # a média/desvio padrão da série inteira.
    retornos = retornos.replace([float("inf"), float("-inf")], float("nan")).dropna()

    if len(retornos) < minimo_observacoes:
        return {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": len(retornos),
            "motivo_nao_aplicavel": (
                f"Overlap de datas insuficiente pra uma correlação confiável "
                f"({len(retornos)} pontos em comum, mínimo {minimo_observacoes})."
            ),
        }

    correlacao = retornos["retorno_a"].corr(retornos["retorno_b"])
    if pd.isna(correlacao):
        return {
            "aplicavel": False,
            "correlacao": None,
            "observacoes": len(retornos),
            "motivo_nao_aplicavel": (
                "Uma das séries não varia no período (desvio padrão zero) — correlação indefinida."
            ),
        }

    return {
        "aplicavel": True,
        "correlacao": float(correlacao),
        "observacoes": len(retornos),
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


# (chave do resultado, coluna do fator, mensagem quando a fonte vem `None`)
# — estático; as séries em si (histórico_petroleo/serie_cambio/serie_gpr)
# são passadas em runtime pra `calcular_correlacoes_fatores` e pareadas na
# MESMA ORDEM abaixo (petróleo, câmbio, GPR). Mesmo padrão de
# `carteira.CENARIOS`: uma tupla de configuração iterada num loop, em vez
# de repetir o mesmo bloco if/else uma vez por fator.
FATORES_CORRELACAO = (
    ("petroleo", "Close", "Histórico do petróleo (Brent) indisponível."),
    ("cambio", "valor", "Série de câmbio USD/BRL do Banco Central indisponível."),
    ("gpr", "GPRD", "Série diária do índice GPR indisponível."),
)


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
    series_por_fator = (historico_petroleo, serie_cambio, serie_gpr)

    resultados = {}
    for (chave, coluna_fator, mensagem_indisponivel), serie_fator in zip(
        FATORES_CORRELACAO, series_por_fator, strict=True
    ):
        if serie_fator is None:
            resultados[chave] = {
                "aplicavel": False,
                "correlacao": None,
                "observacoes": 0,
                "motivo_nao_aplicavel": mensagem_indisponivel,
            }
        else:
            resultados[chave] = calcular_correlacao(
                historico_acao, "Close", serie_fator, coluna_fator
            )

    return resultados
