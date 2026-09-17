"""Monitor de conflitos: escopo de países monitorados, filtragem dos
eventos de conflito do GDELT (`ingest.gdelt`) pra esses países, e
orquestração da busca numa janela de várias horas.

A maior parte deste módulo é lógica pura (`determinar_paises_relevantes`,
`filtrar_eventos_por_paises`, `descrever_escopo_paises`,
`descrever_paises_monitorados`) — recebe um DataFrame de eventos já
buscado (e, pro caso por setor, o segmento setorial já resolvido), não
busca nada. As exceções são `_buscar_eventos_por_paises` (orquestra
várias chamadas a `ingest.gdelt`, uma por snapshot — colocada aqui, e
não em gdelt.py, porque precisa filtrar por país relevante a cada
snapshot pra manter o uso de memória baixo, ver docstring da função) e
`rodar_monitor_conflitos` (persiste o resultado em disco).

Escopo (2026-09-16): o Monitor de conflitos na interface (app/main.py)
passou a usar um escopo FIXO e universal — `PAISES_MONITORADOS`, união de
todos os países já relevantes pra qualquer ação do projeto (Brasil +
produtores de petróleo + produtores de minério de ferro) — não depende
mais de nenhuma ação/setor escolhido. `determinar_paises_relevantes` (o
escopo por SETOR de uma ação específica) continua aqui como lógica
testada e reaproveitável, só não é mais chamada pela interface.

Regra de escopo por setor (documentação completa, com fontes, em
config.py): toda ação tem o Brasil como país relevante por padrão —
risco doméstico afeta qualquer setor. Ações de petróleo/gás ou de
mineração de metálicos/siderurgia ganham, além do Brasil, os principais
países produtores/exportadores daquela commodity.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from avaliador_b3.config import (
    CODIGO_GDELT_BRASIL,
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    JANELA_MONITOR_CONFLITOS_HORAS,
    PAISES_PRODUTORES_MINERIO_FERRO_GDELT,
    PAISES_PRODUTORES_PETROLEO_GDELT,
    SEGMENTOS_SETORIAIS_MINERACAO_METALICOS,
    SEGMENTOS_SETORIAIS_PETROLEO_GAS,
)
from avaliador_b3.ingest.gdelt import COLUNAS_NUMERICAS as COLUNAS_NUMERICAS_GDELT
from avaliador_b3.ingest.gdelt import COLUNAS_RESULTADO as COLUNAS_RESULTADO_GDELT
from avaliador_b3.ingest.gdelt import DTYPES_LEITURA_CACHE as DTYPES_LEITURA_CACHE_GDELT
from avaliador_b3.ingest.gdelt import (
    deduplicar_por_fonte,
    gerar_timestamps_janela,
    obter_eventos_conflito_do_snapshot,
    obter_timestamp_mais_recente,
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


# País monitorados pelo Monitor de conflitos na interface: escopo FIXO e
# universal, união de todos os países já relevantes pra qualquer ação do
# projeto — não depende de nenhuma ação/setor escolhido (ver docstring do
# módulo). Reaproveita os mesmos conjuntos documentados (com fontes) em
# config.py, não duplica a lista de países.
PAISES_MONITORADOS = (
    {CODIGO_GDELT_BRASIL} | PAISES_PRODUTORES_PETROLEO_GDELT | PAISES_PRODUTORES_MINERIO_FERRO_GDELT
)


def descrever_paises_monitorados() -> str:
    """Frase legível descrevendo o escopo fixo e universal de
    `PAISES_MONITORADOS` — mesmo espírito de `descrever_escopo_paises`,
    mas sem depender de nenhuma ação/setor: é o escopo usado pelo Monitor
    de conflitos na interface."""
    nomes_petroleo = ", ".join(
        sorted(NOMES_PAISES_GDELT[codigo] for codigo in PAISES_PRODUTORES_PETROLEO_GDELT)
    )
    nomes_minerio = ", ".join(
        sorted(NOMES_PAISES_GDELT[codigo] for codigo in PAISES_PRODUTORES_MINERIO_FERRO_GDELT)
    )
    return (
        "Brasil (sempre) + principais produtores/exportadores de petróleo "
        f"({nomes_petroleo}) + principais produtores/exportadores de "
        f"minério de ferro ({nomes_minerio})"
    )


def _buscar_eventos_por_paises(
    paises_relevantes: set[str],
    horas: float,
    diretorio_cache: Path,
) -> pd.DataFrame:
    """Busca os eventos de conflito relevantes pra um conjunto de países
    numa janela de `horas` horas (padrão do chamador: 24h — ~96 snapshots
    de 15 min cada).

    Processa um snapshot do GDELT de cada vez, nunca carregando os ~96
    arquivos brutos na memória ao mesmo tempo: cada snapshot já vem
    filtrado por categoria de conflito (feito dentro de
    `obter_eventos_conflito_do_snapshot`), e este loop filtra também por
    país relevante ANTES de acumular — só o resultado pequeno e já
    filtrado fica em memória entre uma iteração e outra, nunca os
    eventos brutos de todos os snapshots juntos. Mesmo princípio de
    processamento incremental já usado no screener (`screener.py`).

    Um horário específico faltando (gap raro do GDELT) ou qualquer outra
    falha isolada nesse snapshot é pulado — não interrompe a busca da
    janela inteira, mesmo padrão de isolamento de erro já usado no
    screener pra uma ação isolada falhando.

    `filtrar_eventos_conflito` já deduplica por SOURCEURL dentro de CADA
    snapshot (`ingest.gdelt.deduplicar_por_fonte`) — mas o mesmo artigo
    pode aparecer em mais de um snapshot de 15 min (ex: reprocessado pelo
    GDELT, ou republicado), então este loop deduplica de novo depois de
    concatenar a janela inteira, pra pegar também esse caso entre
    snapshots diferentes."""
    timestamp_mais_recente = obter_timestamp_mais_recente()
    timestamps = gerar_timestamps_janela(timestamp_mais_recente, horas=horas)

    partes_filtradas: list[pd.DataFrame] = []
    for timestamp in timestamps:
        try:
            eventos_snapshot = obter_eventos_conflito_do_snapshot(
                timestamp, diretorio_cache=diretorio_cache
            )
        except Exception:
            continue

        parte_relevante = filtrar_eventos_por_paises(eventos_snapshot, paises_relevantes)
        if not parte_relevante.empty:
            partes_filtradas.append(parte_relevante)

    if not partes_filtradas:
        return pd.DataFrame(columns=COLUNAS_RESULTADO_GDELT)

    concatenado = (
        pd.concat(partes_filtradas, ignore_index=True).sort_values("data").reset_index(drop=True)
    )
    return deduplicar_por_fonte(concatenado)


def obter_eventos_relevantes_ultimas_24h(
    segmento_setorial: str | None,
    horas: float = JANELA_MONITOR_CONFLITOS_HORAS,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Busca os eventos de conflito relevantes pra uma ação (escopo por
    SETOR, ver `determinar_paises_relevantes`) numa janela de `horas`
    horas — ver `_buscar_eventos_por_paises` pro processamento
    incremental e isolamento de erro por snapshot."""
    paises_relevantes = determinar_paises_relevantes(segmento_setorial)
    return _buscar_eventos_por_paises(paises_relevantes, horas, diretorio_cache)


def obter_eventos_conflito_ultimas_24h(
    horas: float = JANELA_MONITOR_CONFLITOS_HORAS,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Busca os eventos de conflito no escopo universal e fixo
    (`PAISES_MONITORADOS`) numa janela de `horas` horas — usada pelo
    Monitor de conflitos na interface, que não depende mais de nenhuma
    ação/setor escolhido. Ver `_buscar_eventos_por_paises` pro
    processamento incremental e isolamento de erro por snapshot."""
    return _buscar_eventos_por_paises(PAISES_MONITORADOS, horas, diretorio_cache)


CAMINHO_SAIDA_PADRAO = DATA_PROCESSED_DIR / "conflitos_24h.csv"


def rodar_monitor_conflitos(
    horas: float = JANELA_MONITOR_CONFLITOS_HORAS,
    diretorio_cache: Path = DATA_RAW_DIR,
    caminho_saida: Path = CAMINHO_SAIDA_PADRAO,
) -> pd.DataFrame:
    """Busca os eventos de conflito no escopo universal
    (`obter_eventos_conflito_ultimas_24h`) e grava o resultado em
    `caminho_saida`, sobrescrevendo qualquer busca anterior — mesmo
    padrão de persistência do screener (`screener.rodar_screener`): dado
    "salvo em disco, não ao vivo", carregado por padrão na interface
    (`carregar_eventos_conflito_salvos`), atualizado só sob demanda via
    botão explícito. Zero eventos na janela é um resultado válido e
    também é salvo (não é erro — ver `filtrar_eventos_por_paises`)."""
    eventos = obter_eventos_conflito_ultimas_24h(horas=horas, diretorio_cache=diretorio_cache)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    eventos.to_csv(caminho_saida, index=False)
    return eventos


def carregar_eventos_conflito_salvos(
    caminho: Path = CAMINHO_SAIDA_PADRAO,
) -> pd.DataFrame | None:
    """Lê o resultado da última busca de 24h já salvo em disco (não busca
    nada ao vivo) — devolve `None` se o arquivo ainda não existir
    (primeira vez rodando o projeto) ou existir só como um arquivo
    vazio/truncado (ex: processo interrompido no meio da escrita),
    tratado do mesmo jeito que "ainda não existe" (mesmo padrão de
    `app.main._carregar_screener_salvo`).

    Mesma tipagem de leitura usada pro cache de snapshot em
    `ingest.gdelt` (`DTYPES_LEITURA_CACHE`/`COLUNAS_NUMERICAS`), pelo
    mesmo motivo: sem forçar colunas de código como texto, o pandas
    perderia o zero à esquerda de `EventRootCode` (ex: "05" -> 5)."""
    if not caminho.exists():
        return None

    try:
        eventos = pd.read_csv(
            caminho,
            parse_dates=["data"],
            dtype=DTYPES_LEITURA_CACHE_GDELT,
            keep_default_na=False,
        )
    except pd.errors.EmptyDataError:
        return None

    for coluna in COLUNAS_NUMERICAS_GDELT:
        if coluna in eventos.columns:
            eventos[coluna] = pd.to_numeric(eventos[coluna], errors="coerce")

    return eventos
