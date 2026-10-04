"""Valor de Mercado e Valor de Firma — métricas de tamanho da empresa
calculadas a partir de dados já buscados (preço atual, número de ações,
dívida líquida, não controladores e arrendamento), não um modelo de valor
JUSTO como os em `modelos/` (Graham/Bazin/FCD): aqui não há estimativa
nenhuma, só multiplicação/soma de números já conhecidos.
"""

from __future__ import annotations

COMPONENTES_VALOR_FIRMA = ("divida_liquida", "nao_controladores", "arrendamento_fora_da_divida")


def calcular_valor_mercado_e_firma(
    preco_atual: float | None,
    numero_acoes: float | None,
    divida_liquida: float | None,
    nao_controladores: float | None = None,
    arrendamento_fora_da_divida: float | None = None,
) -> dict:
    """Valor de Mercado = preço atual × número de ações. Valor de Firma =
    Valor de Mercado + dívida líquida + participação dos não controladores +
    arrendamento fora da dívida: a mesma ponte entre o valor da empresa e o
    do acionista usada no FCD (`modelos.fcd.calcular_valor_justo_fcd`).

    Componente indisponível (`None`) fica de fora da soma e é listado em
    `componentes_ausentes` (chaves de `COMPONENTES_VALOR_FIRMA`), pra tela
    avisar; nunca vira um número inventado. Sem Valor de Mercado, ou com os
    três componentes ausentes (nada a somar, como em banco sem "Dív. Líquida"
    nem balanço), o Valor de Firma fica `None`. Valor negativo (ex.: caixa
    líquido) é um valor real, não ausente.
    """
    valor_mercado = (
        preco_atual * numero_acoes if preco_atual is not None and numero_acoes is not None else None
    )
    componentes = {
        "divida_liquida": divida_liquida,
        "nao_controladores": nao_controladores,
        "arrendamento_fora_da_divida": arrendamento_fora_da_divida,
    }
    ausentes = [nome for nome in COMPONENTES_VALOR_FIRMA if componentes[nome] is None]
    presentes = [valor for valor in componentes.values() if valor is not None]
    valor_firma = (
        valor_mercado + sum(presentes) if valor_mercado is not None and presentes else None
    )
    return {
        "valor_mercado": valor_mercado,
        "divida_liquida": divida_liquida,
        "valor_firma": valor_firma,
        "componentes_ausentes": ausentes if valor_mercado is not None else [],
    }
