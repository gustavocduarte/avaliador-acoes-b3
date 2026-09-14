"""Adapter para a GDELT Event Database (formato 2.0).

Fonte: https://data.gdeltproject.org/gdeltv2/lastupdate.txt aponta para os
três arquivos mais recentes (eventos, menções, GKG), atualizados a cada 15
minutos. Este adapter usa só o de eventos (`.export.CSV.zip`) — a base GKG
completa é grande demais para uma máquina com pouca RAM (não é usada aqui).

Baixa sempre a janela recente (o snapshot de 15 min mais atual), nunca o
histórico completo. Filtra pelas categorias CAMEO de conflito (17=COERCE,
18=ASSAULT, 19=FIGHT) e extrai localização geográfica e Goldstein Score.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import (
    CATEGORIAS_CONFLITO_CAMEO,
    COLUNAS_EVENTO_GDELT,
    DATA_RAW_DIR,
    URL_GDELT_LASTUPDATE,
)

TIMEOUT_SEGUNDOS = 30

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
    específico, ou se `forcar_atualizacao=True`.
    """
    resposta_indice = requests.get(URL_GDELT_LASTUPDATE, timeout=TIMEOUT_SEGUNDOS)
    resposta_indice.raise_for_status()
    url_evento = _url_evento_mais_recente(resposta_indice.text)
    timestamp = _timestamp_do_url(url_evento)

    caminho = _caminho_cache(timestamp, diretorio_cache)
    if usar_cache and not forcar_atualizacao and caminho.exists():
        return _ler_cache(caminho)

    resposta_evento = requests.get(url_evento, timeout=TIMEOUT_SEGUNDOS)
    resposta_evento.raise_for_status()
    conteudo_csv = _extrair_csv_do_zip(resposta_evento.content)
    df = _analisar_arquivo_eventos(conteudo_csv)
    eventos_conflito = filtrar_eventos_conflito(df)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        eventos_conflito.to_csv(caminho, index=False)

    return eventos_conflito
