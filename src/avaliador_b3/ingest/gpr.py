"""Adapter para o índice GPR (Geopolitical Risk Index), de Caldara & Iacoviello.

Fonte: https://www.matteoiacoviello.com/gpr.htm
Arquivos brutos (.xls):
  - mensal: https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls
  - diaria: https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls
    (apesar do nome "recent" no arquivo, cobre o histórico completo desde
    1985 até hoje — confirmado em 2026-09-15 checando o range real de
    datas do arquivo baixado, não só o nome do link)

Os dois arquivos trazem, coladas à direita da série temporal, duas colunas de
documentação ("var_name"/"var_label") que listam nome/descrição de cada
variável — mas em linhas que não correspondem às datas daquela linha. Essas
colunas são descartadas explicitamente antes de qualquer uso.
"""

from __future__ import annotations

import io
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import DATA_RAW_DIR, DIAS_VALIDADE_CACHE_GPR_DIARIO, URLS_GPR
from avaliador_b3.ingest._cache import cache_expirado

TIMEOUT_SEGUNDOS = 30

# Nome da coluna de data e de uma coluna que precisa existir para considerar
# o arquivo bem formado, por série.
COLUNA_DATA_POR_SERIE = {"mensal": "month", "diaria": "date"}
COLUNA_OBRIGATORIA_POR_SERIE = {"mensal": "GPR", "diaria": "GPRD"}
COLUNAS_DESCARTADAS = ["var_name", "var_label", "DAY"]


def _limpar_dataframe(df: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Remove colunas de documentação, normaliza a coluna de data para
    `data` e ordena por data. Levanta ValueError se as colunas esperadas
    não existirem — sinal de que o formato do arquivo mudou."""
    coluna_data = COLUNA_DATA_POR_SERIE[serie]
    coluna_obrigatoria = COLUNA_OBRIGATORIA_POR_SERIE[serie]

    colunas_faltando = {coluna_data, coluna_obrigatoria} - set(df.columns)
    if colunas_faltando:
        raise ValueError(
            f"Formato do arquivo GPR ({serie}) mudou: colunas esperadas "
            f"{sorted(colunas_faltando)} não encontradas. "
            f"Colunas presentes: {list(df.columns)}"
        )

    df = df.drop(columns=[c for c in COLUNAS_DESCARTADAS if c in df.columns])
    df = df.rename(columns={coluna_data: "data"})
    df["data"] = pd.to_datetime(df["data"])
    return df.sort_values("data").reset_index(drop=True)


def _caminho_cache(serie: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "gpr" / f"gpr_{serie}.csv"


def obter_gpr(
    serie: str = "mensal",
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    hoje: datetime | None = None,
) -> pd.DataFrame:
    """Baixa (ou lê do cache) o índice GPR e devolve um DataFrame com coluna
    `data` (datetime64) e as demais colunas numéricas da série original
    (GPR, GPRT, GPRA, ... para "mensal"; GPRD, GPRD_ACT, ... para "diaria").

    `serie` é "mensal" (histórico completo, desde 1900/1985 conforme a
    coluna) ou "diaria" (janela recente, atualizada diariamente pela
    fonte). Só a "diaria" tem prazo de validade
    (`DIAS_VALIDADE_CACHE_GPR_DIARIO`) — a correlação usa uma janela de 2
    anos terminando hoje, então uma série diária congelada deixa a ponta
    recente sem dado, sem aviso. A "mensal" continua sem prazo, muda pouco
    e cobre um histórico bem mais longo. Se o prazo da "diaria" venceu mas
    a atualização falha (fonte fora do ar, timeout, erro de rede) e já
    existe um cache em disco, usa o arquivo existente (com aviso via
    `warnings.warn`) em vez de propagar o erro — só propaga se não houver
    nenhum cache pra usar.

    `hoje` é injetável (default `datetime.now()`) pra testes.
    """
    if serie not in URLS_GPR:
        raise ValueError(f"Série GPR desconhecida: {serie!r}. Use 'mensal' ou 'diaria'.")

    hoje = hoje or datetime.now()
    caminho = _caminho_cache(serie, diretorio_cache)
    cache_valido = caminho.exists() and (
        serie != "diaria" or not cache_expirado(caminho, DIAS_VALIDADE_CACHE_GPR_DIARIO, hoje)
    )

    if usar_cache and not forcar_atualizacao and cache_valido:
        return pd.read_csv(caminho, parse_dates=["data"])

    try:
        resposta = requests.get(URLS_GPR[serie], timeout=TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
    except requests.RequestException:
        if caminho.exists():
            warnings.warn(
                f"Falha ao atualizar o GPR ({serie}, cache expirado) — usando "
                "a versão em cache, possivelmente desatualizada.",
                stacklevel=2,
            )
            return pd.read_csv(caminho, parse_dates=["data"])
        raise

    try:
        df_bruto = pd.read_excel(io.BytesIO(resposta.content))
    except Exception as erro:
        raise ValueError(
            f"Não foi possível ler o arquivo Excel do GPR ({serie}) — "
            "o link respondeu, mas o conteúdo não é um Excel válido "
            "(formato pode ter mudado)."
        ) from erro

    df = _limpar_dataframe(df_bruto, serie)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df
