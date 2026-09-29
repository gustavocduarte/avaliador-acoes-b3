"""Helper privado compartilhado de nova tentativa em falha temporária de
rede (5xx, 429, timeout, conexão) — usado por bcb_sgs.py e fundamentus.py.
Erro 4xx (exceto 429) não repete, é definitivo (ex: código de série/ticker
inexistente).
"""

from __future__ import annotations

import time

import requests

from avaliador_b3.config import TETO_RETRY_AFTER_SEGUNDOS

STATUS_MUITAS_REQUISICOES = 429


def _segundos_retry_after(resposta: requests.Response | None) -> float | None:
    """Valor do cabeçalho Retry-After em segundos, limitado ao teto. Só
    aceita número de segundos; data HTTP ou valor inválido vira `None`."""
    if resposta is None:
        return None
    try:
        segundos = float(resposta.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None
    if segundos < 0:
        return None
    return min(segundos, TETO_RETRY_AFTER_SEGUNDOS)


def get_com_retry(
    url: str,
    timeout_segundos: float,
    pausas_segundos: tuple[float, ...],
    **kwargs,
) -> requests.Response:
    """GET com nova tentativa em erro 5xx, 429, timeout ou falha de
    conexão — uma tentativa extra por valor em `pausas_segundos`, com essa
    pausa antes de cada uma. No 429, um Retry-After maior que a pausa
    prevalece (limitado a `TETO_RETRY_AFTER_SEGUNDOS`). `**kwargs`
    repassado pro `requests.get` (params, headers, etc.)."""
    ultimo_erro: Exception | None = None
    espera_retry_after: float | None = None
    for pausa in (0, *pausas_segundos):
        if pausa:
            time.sleep(max(pausa, espera_retry_after or 0))
        espera_retry_after = None
        try:
            resposta = requests.get(url, timeout=timeout_segundos, **kwargs)
            resposta.raise_for_status()
            return resposta
        except requests.HTTPError as erro:
            status = erro.response.status_code if erro.response is not None else None
            if status is not None and status < 500 and status != STATUS_MUITAS_REQUISICOES:
                raise
            if status == STATUS_MUITAS_REQUISICOES:
                espera_retry_after = _segundos_retry_after(erro.response)
            ultimo_erro = erro
        except (requests.Timeout, requests.ConnectionError) as erro:
            ultimo_erro = erro
    raise ultimo_erro
