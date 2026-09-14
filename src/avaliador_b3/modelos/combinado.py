"""Combinador de valor justo: junta os três métodos (Graham, Bazin, FCD)
numa média — só dos métodos que estiverem `aplicavel` para aquela ação
específica, nunca uma média fixa dos três.

A decisão de aplicabilidade já é feita em cada módulo individual (ver
`modelos.graham`, `modelos.bazin`, `modelos.fcd`); este módulo só consome
o resultado de cada um, não reimplementa nenhuma regra de quando um
método vale ou não.
"""

from __future__ import annotations

# Cada método guarda o valor calculado numa chave diferente — Bazin chama
# o dele de "preço teto", não "valor justo".
CHAVE_VALOR_POR_METODO = {
    "graham": "valor_justo",
    "bazin": "preco_teto",
    "fcd": "valor_justo",
}


def calcular_valor_combinado(
    resultado_graham: dict, resultado_bazin: dict, resultado_fcd: dict
) -> dict:
    """Combina os resultados dos três métodos numa média simples dos que
    estiverem aplicáveis.

    Cada `resultado_*` é o dict devolvido por
    `modelos.graham.calcular_valor_justo_graham`,
    `modelos.bazin.calcular_preco_teto_bazin` e
    `modelos.fcd.calcular_valor_justo_fcd` respectivamente (cada um com
    uma chave `aplicavel`).

    Devolve um dict com `aplicavel` (bool), `valor_combinado` (float ou
    None), `metodos_utilizados` (lista dos nomes que entraram na média —
    importante pra mostrar de forma transparente por que o combinado saiu
    daquele jeito, nunca como caixa-preta) e `valores_por_metodo` (dict
    nome->valor, só dos métodos aplicáveis). Quando nenhum método é
    aplicável, devolve isso explicitamente (`aplicavel=False`), nunca um
    valor None silencioso ou erro.
    """
    resultados_por_metodo = {
        "graham": resultado_graham,
        "bazin": resultado_bazin,
        "fcd": resultado_fcd,
    }

    valores_por_metodo = {
        nome: resultado[CHAVE_VALOR_POR_METODO[nome]]
        for nome, resultado in resultados_por_metodo.items()
        if resultado.get("aplicavel")
    }

    if not valores_por_metodo:
        return {
            "aplicavel": False,
            "valor_combinado": None,
            "metodos_utilizados": [],
            "valores_por_metodo": {},
            "motivo_nao_aplicavel": (
                "Nenhum dos três métodos (Graham, Bazin, FCD) é aplicável a essa ação."
            ),
        }

    valor_combinado = sum(valores_por_metodo.values()) / len(valores_por_metodo)
    return {
        "aplicavel": True,
        "valor_combinado": valor_combinado,
        "metodos_utilizados": list(valores_por_metodo.keys()),
        "valores_por_metodo": valores_por_metodo,
        "motivo_nao_aplicavel": None,
    }
