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

from avaliador_b3.config import FATOR_GRAHAM, MOTIVO_ENTRADA_NAO_FINITA, MOTIVO_RESULTADO_NAO_FINITO
from avaliador_b3.numeros import campos_nao_finitos, numero_finito


def reescalar_lpa_vpa(
    lpa: float | None,
    vpa: float | None,
    acoes_fundamentus: float | None,
    acoes_em_circulacao: float | None,
) -> tuple[float | None, float | None]:
    """LPA e VPA do Fundamentus trocados para o número de ações em circulação.

    O Fundamentus calcula os dois sobre o número de ações dele; com outro número
    (ações em circulação da CVM), LPA e VPA ficam multiplicados pela razão entre
    os dois números, e o Graham muda na mesma proporção. Sem um dos números, ou
    com algum não positivo ou não finito, devolve LPA e VPA como vieram."""
    if not (numero_finito(acoes_fundamentus) and numero_finito(acoes_em_circulacao)):
        return lpa, vpa
    if acoes_fundamentus <= 0 or acoes_em_circulacao <= 0:
        return lpa, vpa
    razao = acoes_fundamentus / acoes_em_circulacao
    return (
        lpa * razao if lpa is not None else None,
        vpa * razao if vpa is not None else None,
    )


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

    invalidos = campos_nao_finitos({"LPA": lpa, "VPA": vpa})
    if invalidos:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": MOTIVO_ENTRADA_NAO_FINITA.format(campos=", ".join(invalidos)),
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
    if not numero_finito(valor_justo):
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": MOTIVO_RESULTADO_NAO_FINITO,
        }
    return {"aplicavel": True, "valor_justo": valor_justo, "motivo_nao_aplicavel": None}
