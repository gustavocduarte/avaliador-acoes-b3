"""Fórmula de Benjamin Graham ("Graham Number") para valor justo.

VI = sqrt(22,5 × LPA × VPA). O fator 22,5 vem de 15 (P/L máximo que Graham
considerava razoável) × 1,5 (P/VP máximo razoável) — ver The Intelligent
Investor. Constante documentada em `config.FATOR_GRAHAM`.

Só aplicável se LPA > 0 e VPA > 0 — a fórmula quebra matematicamente com
qualquer um dos dois negativo ou zero (raiz de produto negativo não existe
no domínio real). Quando não aplicável, o resultado diz isso explicitamente
em vez de levantar erro ou devolver um número sem sentido.
"""

from __future__ import annotations

import math

from avaliador_b3.config import FATOR_GRAHAM


def calcular_valor_justo_graham(lpa: float | None, vpa: float | None) -> dict:
    """Calcula o valor justo pela fórmula de Graham.

    Devolve um dict com `aplicavel` (bool), `valor_justo` (float ou None) e
    `motivo_nao_aplicavel` (str ou None, preenchido só quando não aplicável).
    """
    if lpa is None or vpa is None:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": "LPA e/ou VPA indisponível.",
        }

    if lpa <= 0 or vpa <= 0:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": (
                f"Fórmula de Graham exige LPA>0 e VPA>0 (LPA={lpa}, VPA={vpa})."
            ),
        }

    valor_justo = math.sqrt(FATOR_GRAHAM * lpa * vpa)
    return {"aplicavel": True, "valor_justo": valor_justo, "motivo_nao_aplicavel": None}
