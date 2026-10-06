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
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)


def cache_expirado(caminho: Path, dias_validade: int, hoje: datetime) -> bool:
    idade = hoje - datetime.fromtimestamp(caminho.stat().st_mtime)
    return idade.days >= dias_validade


def gravar_texto_atomico(caminho: Path, texto: str, *, estrito: bool = False) -> bool:
    """Grava num temporário de nome único (no mesmo diretório) e troca pelo definitivo:
    uma queda no meio da gravação nunca deixa o cache pela metade, e escritores
    simultâneos não dividem o temporário.

    A gravação é uma tentativa: se falhar (disco cheio, `PermissionError` do
    `os.replace` no Windows com o arquivo aberto por outro processo), registra no log,
    limpa o temporário e devolve `False`, sem derrubar a consulta que já tem o dado. Com
    `estrito=True` (arquivos que são resultado, não cache) o erro é levantado."""
    temporario = caminho.with_name(f"{caminho.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario.write_text(texto, encoding="utf-8", newline="")
        os.replace(temporario, caminho)
    except OSError as erro:
        _log.warning("Não foi possível gravar o cache %s: %s", caminho, erro)
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        if estrito:
            raise
        return False
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    return True


def gravar_json_atomico(caminho: Path, dados: object, *, estrito: bool = False) -> bool:
    return gravar_texto_atomico(caminho, json.dumps(dados, ensure_ascii=False), estrito=estrito)


def gravar_csv_atomico(df: pd.DataFrame, caminho: Path) -> bool:
    return gravar_texto_atomico(caminho, df.to_csv(index=False))


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
