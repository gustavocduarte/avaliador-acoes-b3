"""Monitor de conflitos: escopo de países relevantes por ação (a partir do
setor) e filtragem dos eventos de conflito do GDELT (`ingest.gdelt`) pra
esses países. Lógica pura — não busca dado nenhum, recebe o DataFrame de
eventos já buscado e o segmento setorial já resolvido.

Regra de escopo (documentação completa, com fontes, em config.py): toda
ação tem o Brasil como país relevante por padrão — risco doméstico afeta
qualquer setor. Ações de petróleo/gás ou de mineração de
metálicos/siderurgia ganham, além do Brasil, os principais países
produtores/exportadores daquela commodity.
"""

from __future__ import annotations

import pandas as pd

from avaliador_b3.config import (
    CODIGO_GDELT_BRASIL,
    PAISES_PRODUTORES_MINERIO_FERRO_GDELT,
    PAISES_PRODUTORES_PETROLEO_GDELT,
    SEGMENTOS_SETORIAIS_MINERACAO_METALICOS,
    SEGMENTOS_SETORIAIS_PETROLEO_GAS,
)

# Nomes legíveis dos códigos de país usados em PAISES_PRODUTORES_* — só pra
# exibição na interface (ex: "monitorando Brasil + ... (Estados Unidos,
# Rússia, ...)"), não pra filtragem. Ver a fonte de cada código em
# config.py.
NOMES_PAISES_GDELT = {
    "BR": "Brasil",
    "US": "Estados Unidos",
    "RS": "Rússia",
    "SA": "Arábia Saudita",
    "CA": "Canadá",
    "IZ": "Iraque",
    "CH": "China",
    "IR": "Irã",
    "AE": "Emirados Árabes Unidos",
    "KU": "Kuwait",
    "NO": "Noruega",
    "NI": "Nigéria",
    "KZ": "Cazaquistão",
    "AS": "Austrália",
    "IN": "Índia",
    "SF": "África do Sul",
    "UP": "Ucrânia",
}


def determinar_paises_relevantes(segmento_setorial: str | None) -> set[str]:
    """Devolve o conjunto de códigos de país (formato GDELT/FIPS 10-4)
    relevantes pra uma ação, a partir do seu segmento setorial (B3).

    O Brasil está sempre incluso, qualquer que seja o setor — inclusive
    quando `segmento_setorial` é `None` (ex: classificação setorial não
    pôde ser resolvida pra aquele ticker) — é uma regra de risco
    doméstico, não depende de identificar a commodity certa."""
    paises = {CODIGO_GDELT_BRASIL}

    if segmento_setorial in SEGMENTOS_SETORIAIS_PETROLEO_GAS:
        paises |= PAISES_PRODUTORES_PETROLEO_GDELT
    if segmento_setorial in SEGMENTOS_SETORIAIS_MINERACAO_METALICOS:
        paises |= PAISES_PRODUTORES_MINERIO_FERRO_GDELT

    return paises


def filtrar_eventos_por_paises(eventos: pd.DataFrame, paises_relevantes: set[str]) -> pd.DataFrame:
    """Filtra o DataFrame de eventos de conflito (ver
    `ingest.gdelt.obter_eventos_conflito`) pelos países relevantes,
    devolvendo só as linhas cujo `ActionGeo_CountryCode` está no
    conjunto.

    Um resultado vazio é válido e esperado boa parte do tempo — o GDELT
    só cobre uma janela de 15 minutos por snapshot, então é bem provável
    que nenhum evento de conflito tenha acontecido justo nos países
    relevantes pra uma ação específica nesse intervalo curto."""
    return eventos[eventos["ActionGeo_CountryCode"].isin(paises_relevantes)].reset_index(
        drop=True
    )


def eventos_relevantes_para_acao(
    eventos: pd.DataFrame, segmento_setorial: str | None
) -> pd.DataFrame:
    """Combina `determinar_paises_relevantes` e `filtrar_eventos_por_paises`
    — atalho pro caso comum de já ter os eventos e o segmento setorial em
    mãos e só querer o resultado filtrado."""
    paises_relevantes = determinar_paises_relevantes(segmento_setorial)
    return filtrar_eventos_por_paises(eventos, paises_relevantes)


def descrever_escopo_paises(segmento_setorial: str | None) -> str:
    """Frase legível descrevendo quais países estão sendo monitorados pra
    uma ação, a partir do seu segmento setorial — pra deixar claro na
    interface o motivo do que aparece (ou não) na lista de eventos,
    nunca uma lista escondida."""
    partes = ["Brasil (sempre)"]

    if segmento_setorial in SEGMENTOS_SETORIAIS_PETROLEO_GAS:
        nomes = ", ".join(
            sorted(NOMES_PAISES_GDELT[codigo] for codigo in PAISES_PRODUTORES_PETROLEO_GDELT)
        )
        partes.append(f"principais produtores/exportadores de petróleo ({nomes})")

    if segmento_setorial in SEGMENTOS_SETORIAIS_MINERACAO_METALICOS:
        nomes = ", ".join(
            sorted(NOMES_PAISES_GDELT[codigo] for codigo in PAISES_PRODUTORES_MINERIO_FERRO_GDELT)
        )
        partes.append(f"principais produtores/exportadores de minério de ferro ({nomes})")

    return " + ".join(partes)
