"""IPCA mensal pela API SIDRA do IBGE (tabela 1737, variável 63).

Terceira fonte do IPCA, depois do BCB (API) e do BCB (SOAP): a série do BCB (433) é o
próprio IPCA do IBGE, então os meses e os valores são os mesmos, e o acumulado de 12
meses sai do mesmo cálculo. Só serve ao IPCA; a Selic não tem fonte equivalente aqui.

Fonte: https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/last%20{meses}
"""

from __future__ import annotations

import json

import pandas as pd

from avaliador_b3.config import (
    PAUSAS_RETRY_FONTE_SECUNDARIA_SEGUNDOS,
    TIMEOUT_SEGUNDOS_IBGE,
    URL_IBGE_SIDRA_IPCA_MENSAL,
)
from avaliador_b3.ingest._retry import get_com_retry


def _parsear_resposta_sidra(texto: str) -> pd.DataFrame:
    """DataFrame com `data` (primeiro dia do mês) e `valor` (variação mensal, em %), ordenado.

    A resposta é uma lista JSON cuja primeira linha é o cabeçalho; `D3C` traz o mês como
    AAAAMM e `V` o valor. Meses sem valor numérico (a SIDRA usa "-", "..." e "X") são
    ignorados. Levanta `ValueError` se a resposta não for essa lista ou não trouxer meses."""
    try:
        linhas = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ValueError("Resposta da SIDRA não é JSON válido.") from erro
    if not isinstance(linhas, list) or len(linhas) < 2:
        raise ValueError("Resposta da SIDRA sem meses de IPCA.")
    registros = []
    for linha in linhas[1:]:
        try:
            registros.append(
                {
                    "data": pd.Timestamp(
                        year=int(linha["D3C"][:4]), month=int(linha["D3C"][4:]), day=1
                    ),
                    "valor": float(linha["V"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not registros:
        raise ValueError("Resposta da SIDRA sem meses de IPCA com valor.")
    return pd.DataFrame(registros).sort_values("data").reset_index(drop=True)


def obter_ipca_mensal_sidra(meses: int) -> pd.DataFrame:
    """Últimos `meses` meses do IPCA mensal (% ao mês) pela SIDRA, no mesmo formato de
    `bcb_sgs.obter_serie` (`data`, `valor`). Sem cache em disco."""
    resposta = get_com_retry(
        URL_IBGE_SIDRA_IPCA_MENSAL.format(meses=meses),
        TIMEOUT_SEGUNDOS_IBGE,
        PAUSAS_RETRY_FONTE_SECUNDARIA_SEGUNDOS,
    )
    return _parsear_resposta_sidra(resposta.text)
