"""Helper privado compartilhado de validade de cache por idade do arquivo
— usado por b3_universo.py, gpr.py e crosswalk_cnpj.py. Mesmo raciocínio
(idade do arquivo em disco) do zip anual da CVM
(ingest.cvm._cache_zip_expirado), que mantém sua própria versão por ter
uma regra adicional (anos fechados nunca expiram).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def cache_expirado(caminho: Path, dias_validade: int, hoje: datetime) -> bool:
    idade = hoje - datetime.fromtimestamp(caminho.stat().st_mtime)
    return idade.days >= dias_validade
