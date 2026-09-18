"""Adapter para o universo de "ações principais" da B3 e seu segmento de
listagem.

Fonte: a carteira teórica do Ibovespa (~76-79 ativos, revisada
quadrimestralmente) é usada como definição operacional de "ações
principais" — exclui FIIs e small caps por construção.

API usada: `indexProxy/indexCall/GetPortfolioDay` da B3, não-documentada mas
pública (usada por vários projetos open-source da comunidade). Recebe os
parâmetros como um JSON codificado em base64 na própria URL. Cada resultado
já traz o segmento de listagem embutido no campo "type" (ex: "ON      NM"),
como o último token — evita precisar de uma segunda fonte (ex: scraping de
site de terceiros) só para o segmento de listagem.

Paginação (mecanismo de busca-por-página + delay entre páginas) reaproveita
`ingest._paginacao`, compartilhado com `crosswalk_cnpj.py` — outro endpoint
da mesma família da B3, com parâmetros de requisição próprios (por isso
`_montar_url` continua local a cada módulo).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from avaliador_b3.config import (
    DATA_RAW_DIR,
    DELAY_PAGINACAO_B3_SEGUNDOS,
    SEGMENTO_LISTAGEM_PADRAO,
    SEGMENTOS_LISTAGEM_B3,
    TAMANHO_PAGINA_API_B3_UNIVERSO,
    URL_B3_PORTFOLIO_DIA,
)
from avaliador_b3.ingest._paginacao import buscar_registros_paginados, parametros_base64

CAMPOS_OBRIGATORIOS_REGISTRO = {"cod", "asset", "type", "part"}


def _montar_url(pagina: int, tamanho_pagina: int) -> str:
    parametros = {
        "language": "pt-br",
        "pageNumber": pagina,
        "pageSize": tamanho_pagina,
        "index": "IBOV",
        "segment": "1",
    }
    return URL_B3_PORTFOLIO_DIA.format(parametros_base64=parametros_base64(parametros))


def _segmento_listagem(tipo: str) -> str:
    """Extrai o segmento de listagem do campo "type" (ex: "ON      NM" ->
    "Novo Mercado"). O segmento é sempre o último token; sua ausência
    (ex: "ON", "UNT") significa segmento Tradicional."""
    tokens = tipo.split()
    if not tokens:
        return SEGMENTO_LISTAGEM_PADRAO
    return SEGMENTOS_LISTAGEM_B3.get(tokens[-1], SEGMENTO_LISTAGEM_PADRAO)


def _registro_para_linha(registro: dict) -> dict:
    faltando = CAMPOS_OBRIGATORIOS_REGISTRO - registro.keys()
    if faltando:
        raise ValueError(
            "Formato da carteira teórica do Ibovespa mudou: campos "
            f"{sorted(faltando)} não encontrados no registro {registro}."
        )
    return {
        "ticker": registro["cod"],
        "nome": registro["asset"],
        "segmento_listagem": _segmento_listagem(registro["type"]),
        "tipo_bruto": registro["type"].strip(),
        "peso_percentual": float(registro["part"].replace(",", ".")),
    }


def _caminho_cache(diretorio_cache: Path) -> Path:
    return diretorio_cache / "b3" / "universo_ibovespa.csv"


def obter_universo_ibovespa(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    tamanho_pagina: int = TAMANHO_PAGINA_API_B3_UNIVERSO,
    delay_segundos: float = DELAY_PAGINACAO_B3_SEGUNDOS,
) -> pd.DataFrame:
    """Busca a carteira teórica vigente do Ibovespa e devolve um DataFrame
    com `ticker`, `nome`, `segmento_listagem`, `tipo_bruto` e
    `peso_percentual`, ordenado por ticker.

    A carteira é revisada só a cada quadrimestre, então o cache (em
    `data/raw/b3/universo_ibovespa.csv`) não tem TTL — vale até ser
    explicitamente atualizado com `forcar_atualizacao=True`.

    `delay_segundos` só importa se esse endpoint chegar a precisar de mais
    de uma página (hoje os 76 ativos do Ibovespa cabem numa só, ver
    TAMANHO_PAGINA_API_B3_UNIVERSO em config.py) — ver
    `ingest._paginacao.buscar_registros_paginados`.
    """
    caminho = _caminho_cache(diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho)

    registros = buscar_registros_paginados(
        montar_url=lambda pagina: _montar_url(pagina, tamanho_pagina),
        contexto="carteira teórica da B3",
        delay_segundos=delay_segundos,
    )

    linhas = [_registro_para_linha(registro) for registro in registros]
    df = pd.DataFrame(linhas).sort_values("ticker").reset_index(drop=True)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df
