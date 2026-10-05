"""Helpers privados compartilhados dos caches em disco: validade por idade do
arquivo (usada por b3_universo.py, gpr.py e crosswalk_cnpj.py; o zip anual da CVM,
ingest.cvm._cache_zip_expirado, mantém a sua por ter uma regra a mais), gravação
atômica e leitura que trata arquivo corrompido como cache ausente.
"""

from __future__ import annotations

import io
import json
import logging
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)


def cache_expirado(caminho: Path, dias_validade: int, hoje: datetime) -> bool:
    idade = hoje - datetime.fromtimestamp(caminho.stat().st_mtime)
    return idade.days >= dias_validade


def gravar_texto_atomico(caminho: Path, texto: str) -> None:
    """Grava em `<arquivo>.tmp` e troca pelo definitivo: uma queda no meio da
    gravação nunca deixa o cache pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_text(texto, encoding="utf-8", newline="")
        os.replace(temporario, caminho)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def gravar_json_atomico(caminho: Path, dados: object) -> None:
    gravar_texto_atomico(caminho, json.dumps(dados, ensure_ascii=False))


def gravar_csv_atomico(df: pd.DataFrame, caminho: Path) -> None:
    gravar_texto_atomico(caminho, df.to_csv(index=False))


def ler_json_cache(caminho: Path) -> dict | None:
    """Objeto JSON do cache, ou `None` (cache ausente) se o arquivo estiver
    truncado, ilegível ou não for um objeto."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _log.warning("Cache JSON ilegível, será refeito: %s", caminho)
        return None
    if not isinstance(dados, dict):
        _log.warning("Cache JSON em formato inesperado, será refeito: %s", caminho)
        return None
    return dados


def ler_csv_cache(
    caminho: Path, colunas_esperadas: Iterable[str], **opcoes_leitura
) -> pd.DataFrame | None:
    """DataFrame do cache CSV, ou `None` (cache ausente) se o arquivo estiver
    vazio, sem a quebra de linha final (última linha cortada), ilegível ou sem
    alguma das colunas esperadas."""
    try:
        conteudo = caminho.read_bytes()
        if not conteudo.endswith(b"\n"):
            raise ValueError("arquivo sem a linha final completa")
        df = pd.read_csv(io.BytesIO(conteudo), **opcoes_leitura)
        faltando = set(colunas_esperadas) - set(df.columns)
        if faltando:
            raise ValueError(f"colunas faltando: {sorted(faltando)}")
    except (OSError, ValueError) as erro:
        _log.warning("Cache CSV inválido, será refeito (%s): %s", erro, caminho)
        return None
    return df
