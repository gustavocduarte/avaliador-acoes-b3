"""Valor de Mercado e Valor de Firma — métricas de tamanho da empresa
calculadas a partir de dados já buscados (preço atual, número de ações e
dívida líquida absoluta do Fundamentus), não um modelo de valor JUSTO
como os em `modelos/` (Graham/Bazin/FCD): aqui não há estimativa
nenhuma, só multiplicação/soma de números já conhecidos.
"""

from __future__ import annotations


def calcular_valor_mercado_e_firma(
    preco_atual: float | None,
    numero_acoes: float | None,
    divida_liquida: float | None,
) -> dict:
    """Valor de Mercado = preço atual × número de ações. Valor de Firma =
    Valor de Mercado + dívida líquida absoluta (campo "Dív. Líquida" do
    Fundamentus — ausente pra bancos, ver
    `config.CAMPOS_FUNDAMENTUS_OPCIONAIS`).

    Cada peça ausente (preço, número de ações, ou dívida líquida) deixa
    o valor dependente como `None`, nunca um número inventado com peça
    faltando — ex: banco sem "Dív. Líquida" na página tem Valor de
    Mercado calculável normalmente, mas Valor de Firma fica `None`.
    `divida_liquida` negativa (empresa em posição de caixa líquido, mais
    caixa que dívida) é um valor real, não tratada como ausente.
    """
    valor_mercado = (
        preco_atual * numero_acoes
        if preco_atual is not None and numero_acoes is not None
        else None
    )
    valor_firma = (
        valor_mercado + divida_liquida
        if valor_mercado is not None and divida_liquida is not None
        else None
    )
    return {
        "valor_mercado": valor_mercado,
        "divida_liquida": divida_liquida,
        "valor_firma": valor_firma,
    }
