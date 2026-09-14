"""Adapter para o SGS (Sistema Gerenciador de Séries Temporais) do Banco
Central do Brasil.

Fonte: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados
Documentação: https://dadosabertos.bcb.gov.br/

A API não retorna um código HTTP de erro para código de série inválido —
devolve HTTP 200 com uma página HTML de erro no lugar do JSON esperado.
Por isso a resposta é sempre validada como JSON antes de virar DataFrame.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import DATA_RAW_DIR

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
TIMEOUT_SEGUNDOS = 30


def _montar_url(codigo: int, data_inicial: str | None, data_final: str | None) -> str:
    """Monta a URL da API. Datas no formato dd/mm/aaaa, igual à API do BCB."""
    url = BASE_URL.format(codigo=codigo) + "?formato=json"
    if data_inicial:
        url += f"&dataInicial={data_inicial}"
    if data_final:
        url += f"&dataFinal={data_final}"
    return url


def _parsear_resposta(texto: str, codigo: int) -> list[dict]:
    """Converte o corpo da resposta em uma lista de {"data": ..., "valor": ...}.

    Levanta ValueError com mensagem clara se o corpo não for JSON válido —
    isso acontece quando o código de série não existe, mesmo com HTTP 200.
    """
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ValueError(
            f"Resposta da API do BCB para a série {codigo} não é JSON válido "
            "(código de série provavelmente inexistente)."
        ) from erro


def _registros_para_dataframe(registros: list[dict]) -> pd.DataFrame:
    """Converte os registros brutos da API em um DataFrame tipado e ordenado."""
    df = pd.DataFrame(registros, columns=["data", "valor"])
    if df.empty:
        return df.assign(
            data=pd.to_datetime(df["data"]), valor=df["valor"].astype(float)
        )
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = df["valor"].astype(float)
    return df.sort_values("data").reset_index(drop=True)


def _caminho_cache(codigo: int, diretorio_cache: Path) -> Path:
    return diretorio_cache / "bcb" / f"serie_{codigo}.csv"


def obter_serie(
    codigo: int,
    data_inicial: str | None = None,
    data_final: str | None = None,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Busca uma série do SGS do Banco Central e devolve um DataFrame com
    colunas `data` (datetime64) e `valor` (float), ordenado por data.

    Por padrão usa um cache local em disco (`data/raw/bcb/serie_{codigo}.csv`)
    para evitar bater na API repetidamente — séries históricas do SGS raramente
    mudam, só o valor mais recente pode ser revisado. Use `forcar_atualizacao=True`
    para ignorar o cache e buscar de novo.
    """
    caminho = _caminho_cache(codigo, diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho, parse_dates=["data"])

    url = _montar_url(codigo, data_inicial, data_final)
    resposta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    registros = _parsear_resposta(resposta.text, codigo)
    df = _registros_para_dataframe(registros)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df
