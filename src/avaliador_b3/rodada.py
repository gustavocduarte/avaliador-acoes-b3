"""Data e hora da última rodada aceita do screener, gravada ao lado do `screener.csv`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from avaliador_b3 import config
from avaliador_b3.ingest._cache import gravar_json_atomico, ler_json_cache


def agora_da_rodada() -> datetime:
    return datetime.now(ZoneInfo(config.FUSO_RODADA))


def salvar_data_rodada(caminho: Path, momento: datetime) -> None:
    """Grava o momento da rodada (com o fuso); se a gravação falhar, levanta o erro."""
    gravar_json_atomico(
        caminho, {"data_rodada": momento.isoformat(timespec="seconds")}, estrito=True
    )


def carregar_data_rodada(caminho: Path | None = None) -> pd.Timestamp | None:
    """Momento da última rodada aceita, ou `None` se o arquivo não existir ou for inválido."""
    dados = ler_json_cache(caminho or config.CAMINHO_RODADA)
    if dados is None:
        return None
    try:
        momento = pd.Timestamp(dados["data_rodada"])
    except (KeyError, ValueError, TypeError):
        return None
    return None if pd.isna(momento) else momento
