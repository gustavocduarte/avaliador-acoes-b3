"""Checagem de finitude das entradas e saídas dos modelos.

`x <= 0` e `x is None` não pegam `NaN` (`nan <= 0` é falso) nem o infinito
positivo; as validações dos modelos passam por aqui.
"""

from __future__ import annotations

import math
from typing import TypeGuard


def numero_finito(valor: object) -> TypeGuard[float]:
    """`True` só para um número real finito; `None`, `NaN`, infinito e texto dão `False`."""
    try:
        return math.isfinite(valor)  # type: ignore[arg-type]  # TypeError tratado abaixo
    except (TypeError, ValueError):
        return False


def nao_finito(valor: object) -> bool:
    """`True` para um valor presente que não é número finito (`NaN`, infinito ou texto).
    `None` é ausência, não dado corrompido, e dá `False`."""
    return valor is not None and not numero_finito(valor)


def campos_nao_finitos(valores: dict[str, object]) -> list[str]:
    """Nomes dos campos presentes cujo valor não é número finito."""
    return [nome for nome, valor in valores.items() if nao_finito(valor)]
