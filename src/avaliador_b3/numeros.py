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


def converter_finito(valor: str | float, descricao: str = "valor") -> float:
    """Converte para `float` recusando `NaN` e infinito (que o `float` aceita para "NaN",
    "Infinity" e similares); `ValueError` com a `descricao` se não for um número finito."""
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{descricao} não finito: {valor!r}")
    return numero


def campos_nao_finitos(valores: dict[str, object]) -> list[str]:
    """Nomes dos campos presentes cujo valor não é número finito."""
    return [nome for nome, valor in valores.items() if nao_finito(valor)]


def numero_pt_br(valor: float, casas: int) -> str:
    """ "1.234,5": ponto de milhar e vírgula decimal, sem depender do locale."""
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def decimal_pt_br(valor: float, casas: int = 2) -> str:
    """ "−2,25" / "1.234,50": vírgula decimal e sinal negativo "−"."""
    return f"{'−' if valor < 0 else ''}{numero_pt_br(abs(valor), casas)}"


def percentual_pt_br(fracao: float, casas: int = 2) -> str:
    """ "−0,50%" a partir de uma fração (−0.005)."""
    return f"{decimal_pt_br(fracao * 100, casas)}%"


def reais_abreviado(valor: float) -> str:
    """ "R$ 3,6 bi" a partir de R$ 1 bilhão, "R$ 420,3 mi" a partir de R$ 1 milhão."""
    sinal = "−" if valor < 0 else ""
    if abs(valor) >= 1e9:
        return f"{sinal}R$ {numero_pt_br(abs(valor) / 1e9, 1)} bi"
    if abs(valor) >= 1e6:
        return f"{sinal}R$ {numero_pt_br(abs(valor) / 1e6, 1)} mi"
    return f"{sinal}R$ {numero_pt_br(abs(valor), 2)}"
