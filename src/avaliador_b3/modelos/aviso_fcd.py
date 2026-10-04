"""Aviso do cartão do FCD quando o valor é extremo em relação ao preço, com a causa provável
tirada das entradas do modelo (só números que o cálculo já tem). É só informativo: não altera o
valor do FCD nem o valor combinado. Limites e textos em `config.py`."""

from avaliador_b3.config import (
    AVISO_FCD_ABERTURA_ALTO,
    AVISO_FCD_ABERTURA_BAIXO,
    AVISO_FCD_ABERTURA_NEGATIVO,
    AVISO_FCD_CAUSA_CRESCIMENTO_NO_PISO,
    AVISO_FCD_CAUSA_CRESCIMENTO_NO_TETO,
    AVISO_FCD_CAUSA_CRESCIMENTO_PERTO_DO_PISO,
    AVISO_FCD_CAUSA_DEDUCOES_ACIMA_DO_VALOR,
    AVISO_FCD_CAUSA_DEDUCOES_PERTO_DO_VALOR,
    AVISO_FCD_CAUSA_FLUXO_ALTO,
    AVISO_FCD_CAUSA_PERPETUIDADE,
    AVISO_FCD_CAUSA_SEM_IDENTIFICAR,
    AVISO_FCD_CAUSA_WACC_BAIXO,
    AVISO_FCD_FECHAMENTO_ALTO,
    AVISO_FCD_FECHAMENTO_FLUXO_PONTUAL,
    AVISO_FCD_NOMES_DEDUCOES,
    AVISO_FCD_NOMES_DEDUCOES_COM_ARTIGO,
    FCD_EXTREMO_CRESCIMENTO_PERTO_DO_PISO,
    FCD_EXTREMO_DEDUCOES_PERTO_DO_VALOR,
    FCD_EXTREMO_FLUXO_SOBRE_VALOR_DE_MERCADO,
    FCD_EXTREMO_PESO_PERPETUIDADE,
    FCD_EXTREMO_RAZAO_MAXIMA,
    FCD_EXTREMO_RAZAO_MINIMA,
    FCD_EXTREMO_WACC_BAIXO,
    HORIZONTE_PROJECAO_FCD_ANOS,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
)

# Ordem em que as causas aparecem no texto.
ORDEM_CAUSAS = ("K1", "K1b", "K5", "K2a", "K2b", "K6", "K3")
TOLERANCIA_LIMITE_DA_FAIXA = 1e-9


def _numero(valor: float, casas: int) -> str:
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _reais(valor: float) -> str:
    return ("−" if valor < 0 else "") + f"R$ {_numero(abs(valor), 2)}"


def _reais_abreviado(valor: float) -> str:
    """ "R$ 3,6 bi" a partir de R$ 1 bilhão, "R$ 420,3 mi" a partir de R$ 1 milhão."""
    if abs(valor) >= 1e9:
        return f"R$ {_numero(valor / 1e9, 1)} bi"
    if abs(valor) >= 1e6:
        return f"R$ {_numero(valor / 1e6, 1)} mi"
    return _reais(valor)


def _vezes(razao: float) -> str:
    return _numero(razao, 0 if razao >= 10 else 1)


def _pct(fracao: float, casas: int | None = None) -> str:
    if casas is None:
        casas = 1 if abs(fracao) < 0.10 else 0
    return f"{_numero(fracao * 100, casas)}%"


def _gatilho(valor_justo: float, preco: float | None) -> str | None:
    if valor_justo <= 0:
        return "negativo"
    if preco is None or preco <= 0:
        return None
    razao = valor_justo / preco
    if razao >= FCD_EXTREMO_RAZAO_MAXIMA:
        return "alto"
    if razao <= FCD_EXTREMO_RAZAO_MINIMA:
        return "baixo"
    return None


def _deducoes(resultado: dict) -> dict[str, float]:
    """Deduções que o cálculo de fato fez (valor zero fica de fora), por nome."""
    chaves = {
        "divida_liquida": "deducao_divida_liquida",
        "arrendamento": "deducao_arrendamento",
        "nao_controladores": "deducao_nao_controladores",
    }
    valores = {nome: resultado.get(chave) or 0.0 for nome, chave in chaves.items()}
    return {nome: valor for nome, valor in valores.items() if valor != 0.0}


def _causas(resultado: dict, preco: float | None) -> list[str]:
    valor_empresa = resultado["valor_empresa"]
    deducoes = sum(_deducoes(resultado).values())
    causas = []
    if valor_empresa > 0:
        razao_deducoes = deducoes / valor_empresa
        if razao_deducoes >= 1:
            causas.append("K1")
        elif razao_deducoes >= FCD_EXTREMO_DEDUCOES_PERTO_DO_VALOR:
            causas.append("K1b")
        if preco is not None and preco > 0:
            valor_de_mercado = preco * resultado["acoes_utilizadas"]
            if (
                resultado["fluxo_base"] / valor_de_mercado
                >= FCD_EXTREMO_FLUXO_SOBRE_VALOR_DE_MERCADO
            ):
                causas.append("K5")
        if (
            resultado["valor_presente_perpetuidade"] / valor_empresa
            >= FCD_EXTREMO_PESO_PERPETUIDADE
        ):
            causas.append("K3")
    if not resultado.get("motivo_crescimento_ipca"):
        taxa = resultado["taxa_crescimento_explicita"]
        if taxa >= TAXA_CRESCIMENTO_FCD_MAXIMA - TOLERANCIA_LIMITE_DA_FAIXA:
            causas.append("K2a")
        elif taxa <= FCD_EXTREMO_CRESCIMENTO_PERTO_DO_PISO:
            causas.append("K2b")
    if resultado["wacc"] <= FCD_EXTREMO_WACC_BAIXO:
        causas.append("K6")
    return sorted(causas, key=ORDEM_CAUSAS.index)


def _lista_deducoes(resultado: dict) -> str:
    itens = [
        f"{AVISO_FCD_NOMES_DEDUCOES[nome]} {_reais_abreviado(valor)}"
        for nome, valor in _deducoes(resultado).items()
    ]
    return ", ".join(itens[:-1]) + " e " + itens[-1] if len(itens) > 1 else itens[0]


def _texto_da_causa(codigo: str, resultado: dict, preco: float | None) -> str:
    valor_empresa = resultado["valor_empresa"]
    deducoes = _deducoes(resultado)
    total_deducoes = sum(deducoes.values())
    if codigo in ("K1", "K1b"):
        if codigo == "K1b":
            return AVISO_FCD_CAUSA_DEDUCOES_PERTO_DO_VALOR.format(
                deducoes=_reais_abreviado(total_deducoes),
                lista=_lista_deducoes(resultado),
                percentual=_pct(total_deducoes / valor_empresa, 0),
                valor_empresa=_reais_abreviado(valor_empresa),
            )
        maior = max(deducoes, key=lambda nome: deducoes[nome])
        return AVISO_FCD_CAUSA_DEDUCOES_ACIMA_DO_VALOR.format(
            deducoes=_reais_abreviado(total_deducoes),
            lista=_lista_deducoes(resultado),
            vezes=_vezes(total_deducoes / valor_empresa),
            valor_empresa=_reais_abreviado(valor_empresa),
            maior=AVISO_FCD_NOMES_DEDUCOES_COM_ARTIGO[maior],
            percentual_maior=_pct(deducoes[maior] / total_deducoes, 0),
        )
    if codigo == "K5":
        assert preco is not None
        return AVISO_FCD_CAUSA_FLUXO_ALTO.format(
            fluxo=_reais_abreviado(resultado["fluxo_base"]),
            percentual=_pct(resultado["fluxo_base"] / (preco * resultado["acoes_utilizadas"]), 0),
        )
    if codigo == "K2a":
        return AVISO_FCD_CAUSA_CRESCIMENTO_NO_TETO.format(
            taxa=_pct(TAXA_CRESCIMENTO_FCD_MAXIMA, 0), anos=HORIZONTE_PROJECAO_FCD_ANOS
        )
    if codigo == "K2b":
        taxa = resultado["taxa_crescimento_explicita"]
        no_piso = taxa <= TAXA_CRESCIMENTO_FCD_MINIMA + TOLERANCIA_LIMITE_DA_FAIXA
        modelo = (
            AVISO_FCD_CAUSA_CRESCIMENTO_NO_PISO
            if no_piso
            else AVISO_FCD_CAUSA_CRESCIMENTO_PERTO_DO_PISO
        )
        return modelo.format(
            taxa=_pct(abs(taxa), 0),
            piso=_pct(abs(TAXA_CRESCIMENTO_FCD_MINIMA), 0),
            anos=HORIZONTE_PROJECAO_FCD_ANOS,
        )
    if codigo == "K6":
        return AVISO_FCD_CAUSA_WACC_BAIXO.format(wacc=_pct(resultado["wacc"], 1))
    return AVISO_FCD_CAUSA_PERPETUIDADE.format(
        percentual=_pct(resultado["valor_presente_perpetuidade"] / valor_empresa, 0),
        valor_empresa=_reais_abreviado(valor_empresa),
    )


def avaliar_fcd_extremo(resultado_fcd: dict, preco_atual: float | None) -> dict | None:
    """`None` se o FCD não se aplica ou o valor não é extremo. Senão, um dict com `gatilho`
    ("negativo", "alto" ou "baixo"), `causas` (códigos, em ordem de aparição no texto) e
    `texto` (o aviso completo)."""
    if not resultado_fcd.get("aplicavel"):
        return None
    valor_justo = resultado_fcd["valor_justo"]
    gatilho = _gatilho(valor_justo, preco_atual)
    if gatilho is None:
        return None
    causas = _causas(resultado_fcd, preco_atual)

    if gatilho == "negativo":
        abertura = AVISO_FCD_ABERTURA_NEGATIVO.format(valor=_reais(valor_justo))
    elif preco_atual is None:  # "alto" e "baixo" só disparam com preço
        return None
    elif gatilho == "alto":
        abertura = AVISO_FCD_ABERTURA_ALTO.format(
            valor=_reais(valor_justo),
            vezes=_vezes(valor_justo / preco_atual),
            preco=_reais(preco_atual),
        )
    else:
        abertura = AVISO_FCD_ABERTURA_BAIXO.format(
            valor=_reais(valor_justo),
            percentual=_pct(valor_justo / preco_atual),
            preco=_reais(preco_atual),
        )

    frases = [_texto_da_causa(c, resultado_fcd, preco_atual) for c in causas]
    if not frases:
        frases = [AVISO_FCD_CAUSA_SEM_IDENTIFICAR]
    if "K5" in causas:
        frases.append(AVISO_FCD_FECHAMENTO_FLUXO_PONTUAL)
    if gatilho == "alto":
        frases.append(AVISO_FCD_FECHAMENTO_ALTO)
    return {"gatilho": gatilho, "causas": causas, "texto": " ".join([abertura, *frases])}
