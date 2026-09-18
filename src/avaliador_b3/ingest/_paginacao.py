"""Helper privado compartilhado pra paginação contra APIs não-documentadas
da B3 que seguem o mesmo formato de resposta ("results" + "page.totalPages")
— usado por `ingest.b3_universo` (indexProxy/indexCall/GetPortfolioDay) e
`ingest.crosswalk_cnpj` (listedCompaniesProxy/CompanyCall/GetInitialCompanies),
dois ENDPOINTS diferentes da mesma família de API da B3 (hosts iguais, paths
e parâmetros de requisição diferentes — cada um mantém seu próprio
`_montar_url`) — só o mecanismo "parâmetros -> base64 -> valida resposta ->
pagina até acabar" é idêntico entre os dois, então só essa parte foi
extraída aqui.

Prefixo "_" no nome do arquivo segue a convenção do projeto pra módulos
privados de implementação, não pensados pra importação fora de `ingest/`.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable

import requests

TIMEOUT_SEGUNDOS = 30


def parametros_base64(parametros: dict) -> str:
    """Codifica um dict de parâmetros como o base64-de-JSON que as duas
    APIs não-documentadas da B3 usadas no projeto esperam embutido na
    própria URL."""
    return base64.b64encode(json.dumps(parametros).encode()).decode()


def _baixar_pagina(url: str, contexto: str) -> dict:
    resposta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    try:
        return resposta.json()
    except ValueError as erro:  # requests.exceptions.JSONDecodeError é subclasse de ValueError
        raise ValueError(
            f"Resposta de {contexto} não é JSON válido — a API "
            "não-documentada pode ter mudado."
        ) from erro


def buscar_registros_paginados(
    montar_url: Callable[[int], str],
    contexto: str,
    delay_segundos: float = 0.0,
) -> list[dict]:
    """Busca todas as páginas de um endpoint paginado da B3 (formato comum
    "results" + "page.totalPages"), acumulando os registros de "results" de
    cada página. `montar_url(pagina)` monta a URL de uma página específica
    — cada módulo chamador sabe montar a URL certa pro seu próprio endpoint
    (ver `_montar_url` em b3_universo.py/crosswalk_cnpj.py); `contexto` é
    um texto curto (ex: "carteira teórica da B3") usado nas mensagens de
    erro, pra identificar qual busca falhou.

    `delay_segundos` é aplicado ANTES de cada página ALÉM DA PRIMEIRA —
    nada a esperar antes da primeira requisição da sequência, mas esperar
    entre uma página e a próxima evita bater rápido demais numa API
    não-documentada quando o total de páginas é grande (ex: ~36 páginas pro
    catálogo de emissores, ver TAMANHO_PAGINA_API_B3_CATALOGO em config.py)
    — mesmo raciocínio de DELAY_FUNDAMENTUS_SEGUNDOS/DELAY_PRECOS_SEGUNDOS
    pras outras fontes não-oficiais do projeto.

    Levanta ValueError se alguma resposta não for JSON válido, ou se a
    primeira página não tiver os campos 'results'/'page' esperados (sinal
    de que o formato da API mudou).
    """
    primeira_pagina = _baixar_pagina(montar_url(1), contexto)
    if "results" not in primeira_pagina or "page" not in primeira_pagina:
        raise ValueError(
            f"Formato da resposta de {contexto} mudou: campos "
            "'results'/'page' não encontrados. Chaves presentes: "
            f"{list(primeira_pagina.keys())}"
        )

    registros = list(primeira_pagina["results"])
    total_paginas = primeira_pagina["page"]["totalPages"]
    for pagina in range(2, total_paginas + 1):
        if delay_segundos > 0:
            time.sleep(delay_segundos)
        registros.extend(_baixar_pagina(montar_url(pagina), contexto)["results"])

    return registros
