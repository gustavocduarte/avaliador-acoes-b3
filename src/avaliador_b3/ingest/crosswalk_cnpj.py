"""Crosswalk ticker (B3) <-> CNPJ (CVM) — a peça que faltava para conectar
`b3_universo.py` (universo de ações, indexado por ticker) a `cvm.py`
(demonstrações financeiras, indexado por CNPJ).

Investigação feita antes de implementar:

1. A resposta de `indexProxy/indexCall/GetPortfolioDay` (usada em
   b3_universo.py) só traz `cod`/`asset`/`type`/`part`/`partAcum`/
   `theoricalQty` — nenhum identificador além de ticker e nome.
2. Outro endpoint não-documentado da B3, `listedCompaniesProxy/CompanyCall/
   GetInitialCompanies`, traz o catálogo completo de emissores (~3500
   registros) com CNPJ, código CVM e nome — já suficiente sozinho, sem
   precisar do dataset de cadastro da CVM. O CNPJ dessa resposta foi
   conferido manualmente contra o cadastro de companhias abertas da CVM
   (dados.cvm.gov.br) para três empresas reais e bateu nos três casos —
   ver o comentário em config.py com os detalhes.

Chave usada: o código do emissor (4 letras, campo "issuingCompany"), que é
sempre o prefixo do ticker sem o dígito de classe final. Validado contra os
76 tickers reais do Ibovespa: 100% resolvidos por essa chave — não foi
preciso cair para casamento de nome (frágil, evitado de propósito).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import DATA_RAW_DIR, URL_B3_CATALOGO_EMISSORES
from avaliador_b3.ingest.b3_universo import obter_universo_ibovespa

TIMEOUT_SEGUNDOS = 30
CAMPOS_OBRIGATORIOS_REGISTRO = {"issuingCompany", "codeCVM", "cnpj", "companyName"}
PADRAO_SUFIXO_CLASSE = re.compile(r"\d+$")


class ErroCrosswalk(Exception):
    """Base para erros do crosswalk ticker <-> CNPJ."""


class EmissorNaoEncontrado(ErroCrosswalk):
    """O código de emissor derivado do ticker não está no catálogo da B3."""


def _codigo_emissor(ticker: str) -> str:
    """Deriva o código do emissor removendo o sufixo numérico de classe do
    final do ticker. Ex: "PETR4" -> "PETR", "TAEE11" -> "TAEE", "B3SA3" ->
    "B3SA" (só o último dígito sai, não o "3" no meio do código)."""
    return PADRAO_SUFIXO_CLASSE.sub("", ticker)


def _montar_url(pagina: int, tamanho_pagina: int) -> str:
    parametros = {"language": "pt-br", "pageNumber": pagina, "pageSize": tamanho_pagina}
    parametros_base64 = base64.b64encode(json.dumps(parametros).encode()).decode()
    return URL_B3_CATALOGO_EMISSORES.format(parametros_base64=parametros_base64)


def _baixar_pagina(pagina: int, tamanho_pagina: int) -> dict:
    url = _montar_url(pagina, tamanho_pagina)
    resposta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    try:
        return resposta.json()
    except ValueError as erro:  # requests.exceptions.JSONDecodeError é subclasse de ValueError
        raise ValueError(
            "Resposta do catálogo de emissores da B3 não é JSON válido — "
            "a API não-documentada pode ter mudado."
        ) from erro


def _registro_para_linha(registro: dict) -> dict:
    faltando = CAMPOS_OBRIGATORIOS_REGISTRO - registro.keys()
    if faltando:
        raise ValueError(
            "Formato do catálogo de emissores da B3 mudou: campos "
            f"{sorted(faltando)} não encontrados no registro {registro}."
        )
    return {
        "codigo_emissor": registro["issuingCompany"],
        "codigo_cvm": registro["codeCVM"],
        "cnpj": registro["cnpj"],
        "nome_empresa": registro["companyName"],
    }


def _caminho_cache_catalogo(diretorio_cache: Path) -> Path:
    return diretorio_cache / "b3" / "catalogo_emissores.csv"


def obter_catalogo_emissores(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    tamanho_pagina: int = 100,
) -> pd.DataFrame:
    """Busca o catálogo completo de emissores da B3 (todos os tipos de
    ativo — ações, BDRs, ETFs, etc., não só o Ibovespa) e devolve um
    DataFrame com `codigo_emissor`, `codigo_cvm`, `cnpj` e `nome_empresa`.

    É um catálogo de referência que muda pouco, então o cache (em
    `data/raw/b3/catalogo_emissores.csv`) não tem TTL.
    """
    caminho = _caminho_cache_catalogo(diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho, dtype=str)

    primeira_pagina = _baixar_pagina(1, tamanho_pagina)
    if "results" not in primeira_pagina or "page" not in primeira_pagina:
        raise ValueError(
            "Formato da resposta do catálogo de emissores da B3 mudou: "
            "campos 'results'/'page' não encontrados. Chaves presentes: "
            f"{list(primeira_pagina.keys())}"
        )

    registros = list(primeira_pagina["results"])
    total_paginas = primeira_pagina["page"]["totalPages"]
    for pagina in range(2, total_paginas + 1):
        registros.extend(_baixar_pagina(pagina, tamanho_pagina)["results"])

    linhas = [_registro_para_linha(registro) for registro in registros]
    df = pd.DataFrame(linhas).sort_values("codigo_emissor").reset_index(drop=True)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df


def resolver_cnpj(ticker: str, catalogo: pd.DataFrame) -> dict:
    """Resolve um ticker isolado no catálogo de emissores (já carregado em
    `catalogo`, ver `obter_catalogo_emissores`). Levanta
    `EmissorNaoEncontrado` se o código do emissor derivado do ticker não
    estiver no catálogo."""
    codigo_emissor = _codigo_emissor(ticker)
    linhas = catalogo[catalogo["codigo_emissor"] == codigo_emissor]
    if linhas.empty:
        raise EmissorNaoEncontrado(
            f"Ticker {ticker!r} (emissor {codigo_emissor!r}) não encontrado "
            "no catálogo de emissores da B3."
        )
    linha = linhas.iloc[0]
    return {
        "ticker": ticker,
        "codigo_emissor": codigo_emissor,
        "cnpj": linha["cnpj"],
        "codigo_cvm": linha["codigo_cvm"],
        "nome_empresa": linha["nome_empresa"],
    }


def _caminho_cache_crosswalk(diretorio_cache: Path) -> Path:
    return diretorio_cache / "b3" / "crosswalk_ibovespa.csv"


def obter_crosswalk_ibovespa(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Cruza o universo do Ibovespa (`b3_universo.obter_universo_ibovespa`)
    com o catálogo de emissores da B3, devolvendo um DataFrame com
    `ticker`, `codigo_emissor`, `cnpj`, `codigo_cvm` e `nome_empresa` para
    cada ação do índice.

    Levanta `EmissorNaoEncontrado` se algum ticker do Ibovespa não resolver
    para um emissor conhecido — tratado como um problema a investigar, não
    como uma linha a pular silenciosamente (na validação contra os 76
    tickers reais em 2026-09-14, isso nunca aconteceu).
    """
    caminho = _caminho_cache_crosswalk(diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho, dtype=str)

    universo = obter_universo_ibovespa(
        usar_cache=usar_cache,
        forcar_atualizacao=forcar_atualizacao,
        diretorio_cache=diretorio_cache,
    )
    catalogo = obter_catalogo_emissores(
        usar_cache=usar_cache,
        forcar_atualizacao=forcar_atualizacao,
        diretorio_cache=diretorio_cache,
    )

    linhas = [resolver_cnpj(ticker, catalogo) for ticker in universo["ticker"]]
    df = pd.DataFrame(linhas)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df
