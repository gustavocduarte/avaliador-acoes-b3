"""Simulador de carteira: projeta cenários pessimista/base/otimista pra um
conjunto de ações e valores investidos, a partir do resultado já salvo do
screener (data/processed/screener.csv) — não recalcula nada ao vivo, só
reorganiza os valores por método que o screener já grava por ação.

Cenários por ação (não são três variáveis novas, é reorganizar o que o
screener já grava em `graham_valor_justo`, `bazin_preco_teto`,
`fcd_valor_justo` e `valor_combinado`):
- Otimista: o maior valor entre os métodos aplicáveis (Graham, Bazin, FCD).
- Base: `valor_combinado` (média dos métodos aplicáveis, já calculada pelo
  combinador em `modelos.combinado`).
- Pessimista: o menor valor entre os métodos aplicáveis.

Uma ação sem nenhum método aplicável (ex: HAPV3/MRVE3 no screener real) não
tem cenário nenhum — é sinalizada explicitamente como tal (`aplicavel`
False e um `motivo_nao_aplicavel`), nunca recebe um zero disfarçado de
valor real.
"""

from __future__ import annotations

import pandas as pd

COLUNAS_METODOS = ("graham_valor_justo", "bazin_preco_teto", "fcd_valor_justo")
CENARIOS = ("otimista", "base", "pessimista")


def _valor_valido(valor) -> bool:
    return not pd.isna(valor)


def derivar_cenarios_ticker(linha: dict) -> dict:
    """Deriva otimista/base/pessimista a partir das colunas por método que
    o screener já grava pra uma linha (dict ou `pandas.Series`, ex: uma
    linha de `data/processed/screener.csv` já lido).

    Devolve `aplicavel=False` (com `motivo_nao_aplicavel`) se nenhum dos
    três métodos foi aplicável àquela ação — não há cenário nenhum pra
    projetar, e o chamador deve tratar isso explicitamente, não ignorar.
    """
    valores_aplicaveis = [
        float(linha[coluna]) for coluna in COLUNAS_METODOS if _valor_valido(linha.get(coluna))
    ]

    if not valores_aplicaveis:
        return {
            "aplicavel": False,
            "otimista": None,
            "base": None,
            "pessimista": None,
            "motivo_nao_aplicavel": (
                "Nenhum método (Graham, Bazin, FCD) aplicável — sem cenário pra projetar."
            ),
        }

    return {
        "aplicavel": True,
        "otimista": max(valores_aplicaveis),
        "base": float(linha["valor_combinado"]),
        "pessimista": min(valores_aplicaveis),
        "motivo_nao_aplicavel": None,
    }


def simular_investimento_ticker(linha_screener: dict, valor_investido: float) -> dict:
    """Projeta o valor investido numa ação nos três cenários, em R$ e em %
    de retorno sobre o valor investido. `linha_screener` é uma linha da
    tabela do screener (precisa de `ticker`, `preco_atual` e as colunas
    de `derivar_cenarios_ticker`).

    Quando a ação não tem cenário aplicável (`derivar_cenarios_ticker`) ou
    não tem preço atual disponível, devolve `aplicavel=False` com o motivo
    — as colunas de projeção/retorno ficam `None`, nunca um valor
    projetado a partir de um cenário inexistente.
    """
    ticker = linha_screener["ticker"]
    preco_atual = linha_screener.get("preco_atual")
    cenarios = derivar_cenarios_ticker(linha_screener)

    linha = {
        "ticker": ticker,
        "valor_investido": valor_investido,
        "preco_atual": preco_atual if _valor_valido(preco_atual) else None,
    }

    if not cenarios["aplicavel"] or not _valor_valido(preco_atual):
        linha["aplicavel"] = False
        linha["motivo_nao_aplicavel"] = cenarios["motivo_nao_aplicavel"] or (
            "Preço atual indisponível — não dá pra projetar retorno sem ele."
        )
        for cenario in CENARIOS:
            linha[f"projecao_{cenario}"] = None
            linha[f"retorno_{cenario}_percentual"] = None
        return linha

    linha["aplicavel"] = True
    linha["motivo_nao_aplicavel"] = None
    for cenario in CENARIOS:
        valor_cenario = cenarios[cenario]
        linha[f"projecao_{cenario}"] = valor_investido * (valor_cenario / preco_atual)
        linha[f"retorno_{cenario}_percentual"] = (valor_cenario / preco_atual - 1) * 100

    return linha


def montar_tabela_carteira(
    tabela_screener: pd.DataFrame, investimentos: dict[str, float]
) -> pd.DataFrame:
    """Monta a tabela da carteira simulada: uma linha por ticker
    selecionado, na mesma ordem de `investimentos` (a ordem em que a
    pessoa selecionou no multiselect).

    `investimentos` é um dict ticker -> valor investido em R$. Cada
    ticker precisa existir em `tabela_screener` — a UI restringe o
    multiselect aos tickers presentes no screener, então isso nunca
    deveria falhar na prática.
    """
    # drop=False: mantém "ticker" também como coluna, não só como índice —
    # simular_investimento_ticker espera `linha_screener["ticker"]`.
    tabela_por_ticker = tabela_screener.set_index("ticker", drop=False)
    linhas = [
        simular_investimento_ticker(tabela_por_ticker.loc[ticker], valor_investido)
        for ticker, valor_investido in investimentos.items()
    ]
    return pd.DataFrame(linhas)


def calcular_totais_carteira(tabela_carteira: pd.DataFrame) -> dict:
    """Totais da carteira: soma investida (todos os tickers selecionados,
    mesmo os sem cenário — o dinheiro foi alocado do mesmo jeito) e o
    total projetado em cada cenário (soma simples das projeções
    individuais; `pandas.Series.sum` já ignora os `None`/NaN dos tickers
    sem cenário aplicável, então eles não entram na soma projetada)."""
    return {
        "soma_investida": float(tabela_carteira["valor_investido"].sum()),
        "total_otimista": float(tabela_carteira["projecao_otimista"].sum()),
        "total_base": float(tabela_carteira["projecao_base"].sum()),
        "total_pessimista": float(tabela_carteira["projecao_pessimista"].sum()),
        "quantidade_sem_cenario": int((~tabela_carteira["aplicavel"]).sum()),
    }
