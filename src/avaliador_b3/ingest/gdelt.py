"""Adapter para a GDELT Event Database (formato 2.0).

Fonte: https://data.gdeltproject.org/gdeltv2/lastupdate.txt aponta para os
três arquivos mais recentes (eventos, menções, GKG), atualizados a cada 15
minutos. Este adapter usa só o de eventos (`.export.CSV.zip`) — a base GKG
completa é grande demais para uma máquina com pouca RAM (não é usada aqui).

Por padrão busca só a janela recente (o snapshot de 15 min mais atual),
nunca o histórico completo — mas também expõe funções pra buscar um
snapshot passado específico pelo timestamp (o nome de arquivo do GDELT
segue um padrão previsível, ver `INTERVALO_SNAPSHOT_GDELT_MINUTOS` em
config.py), usadas por `conflitos.obter_eventos_relevantes_ultimas_24h`
pra montar uma janela maior processando um snapshot de cada vez. Filtra
pelas categorias CAMEO de conflito (17=COERCE, 18=ASSAULT, 19=FIGHT) e
extrai localização geográfica e Goldstein Score.
"""

from __future__ import annotations

import io
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import (
    CATEGORIAS_CONFLITO_CAMEO,
    COLUNAS_EVENTO_GDELT,
    DATA_RAW_DIR,
    DELAY_GDELT_SEGUNDOS,
    INTERVALO_SNAPSHOT_GDELT_MINUTOS,
    URL_GDELT_LASTUPDATE,
)

TIMEOUT_SEGUNDOS = 30
FORMATO_TIMESTAMP_GDELT = "%Y%m%d%H%M%S"
URL_GDELT_BASE = "https://data.gdeltproject.org/gdeltv2"

COLUNAS_NUMERICAS = [
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    "ActionGeo_Lat",
    "ActionGeo_Long",
]

COLUNAS_RESULTADO = [
    "GLOBALEVENTID",
    "data",
    "EventRootCode",
    "categoria_cameo",
    "EventCode",
    "GoldsteinScale",
    "NumMentions",
    "NumArticles",
    "AvgTone",
    "ActionGeo_FullName",
    "ActionGeo_CountryCode",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "SOURCEURL",
]

# Ao reler o cache em CSV, essas colunas precisam ser forçadas como texto —
# senão o pandas infere int64 e "05" (EventRootCode) vira 5, perdendo o zero
# à esquerda que distingue os códigos CAMEO.
DTYPES_LEITURA_CACHE = {
    "GLOBALEVENTID": "int64",
    "EventRootCode": str,
    "categoria_cameo": str,
    "EventCode": str,
    "ActionGeo_FullName": str,
    "ActionGeo_CountryCode": str,
    "SOURCEURL": str,
}


def _url_evento_mais_recente(conteudo_lastupdate: str) -> str:
    """Extrai a URL do arquivo de eventos (.export.CSV.zip) de lastupdate.txt.

    O arquivo tem 3 linhas — eventos, menções e GKG — no formato
    "<tamanho> <md5> <url>". Levanta ValueError se nenhuma linha apontar
    para um .export.CSV.zip, sinal de que o formato do índice mudou.
    """
    for linha in conteudo_lastupdate.strip().splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[2].endswith(".export.CSV.zip"):
            # O host sempre redireciona http -> https (confirmado em 2026-09-14);
            # usar https direto evita um round-trip a mais.
            return partes[2].replace("http://", "https://", 1)
    raise ValueError(
        "Não encontrei a linha do arquivo de eventos (.export.CSV.zip) em "
        "lastupdate.txt — formato do índice do GDELT pode ter mudado."
    )


def _timestamp_do_url(url: str) -> str:
    nome_arquivo = url.rsplit("/", 1)[-1]
    return nome_arquivo.split(".", 1)[0]


def _url_evento_por_timestamp(timestamp: str) -> str:
    """Monta a URL do arquivo de eventos pra um timestamp específico
    (formato GDELT, `%Y%m%d%H%M%S`) — o mesmo padrão de nome de arquivo
    usado pelo snapshot mais recente, confirmado contra 96 timestamps
    passados reais em 2026-09-16 (ver comentário em config.py)."""
    return f"{URL_GDELT_BASE}/{timestamp}.export.CSV.zip"


def gerar_timestamps_janela(
    timestamp_mais_recente: str,
    horas: float,
    intervalo_minutos: int = INTERVALO_SNAPSHOT_GDELT_MINUTOS,
) -> list[str]:
    """Gera a lista de timestamps de snapshot (formato GDELT) que cobrem
    uma janela de `horas` horas terminando em `timestamp_mais_recente`
    (incluso), espaçados por `intervalo_minutos` — o mesmo intervalo em
    que o GDELT publica um novo snapshot. Do mais recente pro mais
    antigo, já que é assim que a janela é consumida (ver
    `conflitos.obter_eventos_relevantes_ultimas_24h`)."""
    ancora = datetime.strptime(timestamp_mais_recente, FORMATO_TIMESTAMP_GDELT)
    total_passos = round(horas * 60 / intervalo_minutos)
    return [
        (ancora - timedelta(minutes=intervalo_minutos * passo)).strftime(FORMATO_TIMESTAMP_GDELT)
        for passo in range(total_passos)
    ]


def obter_timestamp_mais_recente() -> str:
    """Consulta `lastupdate.txt` e devolve só o timestamp do snapshot
    mais recente (sem baixar o arquivo de eventos em si, que é bem maior)
    — usado como âncora pra `gerar_timestamps_janela`."""
    resposta_indice = requests.get(URL_GDELT_LASTUPDATE, timeout=TIMEOUT_SEGUNDOS)
    resposta_indice.raise_for_status()
    url_evento = _url_evento_mais_recente(resposta_indice.text)
    return _timestamp_do_url(url_evento)


def _extrair_csv_do_zip(conteudo_zip: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as arquivo_zip:
            nomes = arquivo_zip.namelist()
            if not nomes:
                raise ValueError("Arquivo zip de eventos do GDELT está vazio.")
            return arquivo_zip.read(nomes[0]).decode("utf-8", errors="replace")
    except zipfile.BadZipFile as erro:
        raise ValueError(
            "Não foi possível ler o zip de eventos do GDELT — conteúdo não é "
            "um zip válido (link pode estar fora do ar ou formato mudou)."
        ) from erro


def _analisar_arquivo_eventos(conteudo_csv: str) -> pd.DataFrame:
    """Faz o parsing do CSV bruto (tab-delimited, sem cabeçalho, 61 colunas)
    e devolve um DataFrame com todas as colunas oficiais do GDELT 2.0, mais
    `data` (de DATEADDED) e `categoria_cameo`.
    """
    primeira_linha = conteudo_csv.split("\n", 1)[0]
    n_campos = len(primeira_linha.split("\t"))
    if n_campos != len(COLUNAS_EVENTO_GDELT):
        raise ValueError(
            "Formato do arquivo de eventos do GDELT mudou: esperava "
            f"{len(COLUNAS_EVENTO_GDELT)} colunas, arquivo tem {n_campos}."
        )

    df = pd.read_csv(
        io.StringIO(conteudo_csv),
        sep="\t",
        header=None,
        names=COLUNAS_EVENTO_GDELT,
        dtype=str,
        keep_default_na=False,
    )

    for coluna in COLUNAS_NUMERICAS:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    df["GLOBALEVENTID"] = df["GLOBALEVENTID"].astype("int64")
    df["data"] = pd.to_datetime(df["DATEADDED"], format="%Y%m%d%H%M%S")
    df["categoria_cameo"] = df["EventRootCode"].map(CATEGORIAS_CONFLITO_CAMEO)

    return df


def filtrar_eventos_conflito(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra o DataFrame completo de eventos pelas categorias CAMEO de
    conflito (COERCE/ASSAULT/FIGHT) e seleciona as colunas de localização
    geográfica e Goldstein Score relevantes para o projeto."""
    filtrado = df[df["EventRootCode"].isin(CATEGORIAS_CONFLITO_CAMEO)]
    return filtrado[COLUNAS_RESULTADO].sort_values("data").reset_index(drop=True)


def _caminho_cache(timestamp: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "gdelt" / f"eventos_conflito_{timestamp}.csv"


def _ler_cache(caminho: Path) -> pd.DataFrame:
    """Lê um CSV de cache com a mesma tipagem usada em `_analisar_arquivo_eventos`:
    colunas de código/texto como string (`keep_default_na=False`, senão o
    pandas trata célula vazia como NaN e infere int64 para colunas como
    EventRootCode, perdendo zeros à esquerda como em "05"), e as colunas
    numéricas convertidas explicitamente depois.
    """
    df = pd.read_csv(
        caminho,
        parse_dates=["data"],
        dtype=DTYPES_LEITURA_CACHE,
        keep_default_na=False,
    )
    for coluna in COLUNAS_NUMERICAS:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")
    return df


def _buscar_snapshot(
    timestamp: str,
    url_evento: str,
    usar_cache: bool,
    forcar_atualizacao: bool,
    diretorio_cache: Path,
    delay_segundos: float,
) -> pd.DataFrame:
    """Busca (ou lê do cache) UM snapshot já identificado por timestamp e
    URL — compartilhado por `obter_eventos_conflito` (mais recente) e
    `obter_eventos_conflito_do_snapshot` (timestamp explícito), que só
    diferem em como descobrem esses dois valores.

    `delay_segundos` só se aplica antes de uma requisição real (não em
    cache hit) — mesmo padrão do delay em `ingest.precos`/`ingest.fundamentus`,
    pra não bater rápido demais no GDELT ao processar uma janela de várias
    dezenas de snapshots em sequência.
    """
    caminho = _caminho_cache(timestamp, diretorio_cache)
    if usar_cache and not forcar_atualizacao and caminho.exists():
        return _ler_cache(caminho)

    if delay_segundos > 0:
        time.sleep(delay_segundos)

    resposta_evento = requests.get(url_evento, timeout=TIMEOUT_SEGUNDOS)
    resposta_evento.raise_for_status()
    conteudo_csv = _extrair_csv_do_zip(resposta_evento.content)
    df = _analisar_arquivo_eventos(conteudo_csv)
    eventos_conflito = filtrar_eventos_conflito(df)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        eventos_conflito.to_csv(caminho, index=False)

    return eventos_conflito


def obter_eventos_conflito(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Busca o snapshot de eventos mais recente do GDELT (janela de 15 min,
    nunca o histórico completo) e devolve só os eventos de conflito
    (CAMEO 17/18/19), com localização geográfica e Goldstein Score.

    Cada chamada consulta `lastupdate.txt` (arquivo pequeno) para descobrir
    qual é o snapshot mais recente; o zip de eventos em si (maior) só é
    baixado de novo se ainda não tiver sido cacheado para aquele timestamp
    específico, ou se `forcar_atualizacao=True`. Sem delay — é uma
    requisição isolada, não uma janela de várias em sequência (ver
    `obter_eventos_conflito_do_snapshot` pra esse caso).
    """
    resposta_indice = requests.get(URL_GDELT_LASTUPDATE, timeout=TIMEOUT_SEGUNDOS)
    resposta_indice.raise_for_status()
    url_evento = _url_evento_mais_recente(resposta_indice.text)
    timestamp = _timestamp_do_url(url_evento)

    return _buscar_snapshot(
        timestamp, url_evento, usar_cache, forcar_atualizacao, diretorio_cache, delay_segundos=0
    )


def obter_eventos_conflito_do_snapshot(
    timestamp: str,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    delay_segundos: float = DELAY_GDELT_SEGUNDOS,
) -> pd.DataFrame:
    """Busca (ou lê do cache) UM snapshot específico de eventos do GDELT,
    identificado pelo timestamp exato (formato GDELT — ver
    `gerar_timestamps_janela`), devolvendo só os eventos de conflito já
    filtrados.

    Levanta as mesmas exceções que `obter_eventos_conflito` (erro de
    rede, HTTP não-200, zip inválido) — não tenta adivinhar se aquele
    horário específico "não existe" (gap) ou é outro tipo de falha; quem
    processa uma janela de vários snapshots decide como reagir (ver
    `conflitos.obter_eventos_relevantes_ultimas_24h`, que pula o horário
    e segue pros demais).
    """
    url_evento = _url_evento_por_timestamp(timestamp)
    return _buscar_snapshot(
        timestamp, url_evento, usar_cache, forcar_atualizacao, diretorio_cache, delay_segundos
    )
