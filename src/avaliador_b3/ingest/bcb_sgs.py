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
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import (
    DATA_RAW_DIR,
    JANELA_BUSCA_IPCA_DIAS,
    JANELA_BUSCA_SELIC_DIAS,
    MESES_IPCA_ACUMULADO,
    PAUSAS_RETRY_SEGUNDOS,
    SERIES_BCB_SGS,
    TIMEOUT_SEGUNDOS_BCB_SGS,
    VALIDADE_MACRO_GUARDADO_DIAS,
)
from avaliador_b3.ingest._retry import get_com_retry

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

MENSAGEM_MACRO_INDISPONIVEL = (
    "O Banco Central não respondeu agora (erro temporário do serviço "
    "deles). O FCD depende da Selic e do IPCA e ficou indisponível; tente "
    "de novo em alguns minutos."
)


class MacroIndisponivelError(Exception):
    """BCB fora do ar (mesmo após as novas tentativas) e sem valor guardado
    recente o bastante (ver VALIDADE_MACRO_GUARDADO_DIAS) pra usar como
    último recurso. Mensagem já pronta pra tela — sem endereço da API; o
    erro técnico original fica só num warnings.warn (vai pro log, não pra
    UI) e encadeado via `raise ... from erro`."""


class DadosMacroInsuficientesError(Exception):
    """IPCA voltou com menos leituras que MESES_IPCA_ACUMULADO — não é
    falha de rede (a API respondeu), por isso não tenta de novo nem cai
    pro valor guardado: o acumulado sairia subestimado em silêncio
    (menos meses multiplicados), então é melhor recusar o cálculo."""


def _montar_url(codigo: int, data_inicial: str | None, data_final: str | None) -> str:
    """Monta a URL da API. Datas no formato dd/mm/aaaa, igual à API do BCB."""
    url = BASE_URL.format(codigo=codigo) + "?formato=json"
    if data_inicial:
        url += f"&dataInicial={data_inicial}"
    if data_final:
        url += f"&dataFinal={data_final}"
    return url


def _get_com_retry(url: str) -> requests.Response:
    return get_com_retry(url, TIMEOUT_SEGUNDOS_BCB_SGS, PAUSAS_RETRY_SEGUNDOS)


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


def _caminho_cache(
    codigo: int, data_inicial: str | None, data_final: str | None, diretorio_cache: Path
) -> Path:
    # data_inicial/data_final precisam fazer parte da chave de cache — sem
    # isso, um chamador com janela ROLANTE (ex: app/main.py recalcula
    # "hoje - N dias" a "hoje" a cada execução) fica preso pra sempre na
    # janela do primeiro fetch, porque a única checagem de validade era
    # `caminho.exists()`: qualquer chamada seguinte, em qualquer dia
    # futuro, lia esse mesmo arquivo desatualizado, silenciosamente. Mesmo
    # bug já corrigido em ingest/precos.py pro parâmetro `periodo` (ver
    # comentário lá) — datas trocam "/" por "-" pra virarem nome de
    # arquivo válido. Sem sufixo quando as duas datas são None (== série
    # inteira), pra não invalidar cache já gravado em disco antes dessa
    # mudança nesse caso específico (só usado em teste hoje — todo
    # chamador real sempre passa datas explícitas).
    sufixo_janela = ""
    if data_inicial or data_final:
        inicio = (data_inicial or "inicio").replace("/", "-")
        fim = (data_final or "fim").replace("/", "-")
        sufixo_janela = f"_{inicio}_{fim}"
    return diretorio_cache / "bcb" / f"serie_{codigo}{sufixo_janela}.csv"


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

    Por padrão usa um cache local em disco (`data/raw/bcb/serie_{codigo}
    [_{data_inicial}_{data_final}].csv` — a janela faz parte do nome do
    arquivo, ver `_caminho_cache`) para evitar bater na API repetidamente —
    séries históricas do SGS raramente mudam, só o valor mais recente pode
    ser revisado. Use `forcar_atualizacao=True` para ignorar o cache e
    buscar de novo.
    """
    caminho = _caminho_cache(codigo, data_inicial, data_final, diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho, parse_dates=["data"])

    url = _montar_url(codigo, data_inicial, data_final)
    resposta = _get_com_retry(url)
    registros = _parsear_resposta(resposta.text, codigo)
    df = _registros_para_dataframe(registros)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df


@dataclass
class ResultadoMacro:
    """Selic meta e IPCA acumulado 12 meses, com a proveniência do dado —
    ver `obter_selic_e_ipca`."""

    selic_meta: float
    ipca_12m: float
    data_ipca: pd.Timestamp
    usou_valor_guardado: bool
    data_busca: pd.Timestamp


def _caminho_ultimo_macro(diretorio_cache: Path) -> Path:
    return diretorio_cache / "bcb" / "ultimo_macro.json"


def _salvar_ultimo_macro(
    diretorio_cache: Path,
    selic_meta: float,
    ipca_12m: float,
    data_ipca: pd.Timestamp,
    data_busca: datetime,
) -> None:
    caminho = _caminho_ultimo_macro(diretorio_cache)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(
            {
                "selic_meta": selic_meta,
                "ipca_12m": ipca_12m,
                "data_ipca": data_ipca.strftime("%Y-%m-%d"),
                "data_busca": data_busca.isoformat(),
            }
        )
    )


def _carregar_ultimo_macro(diretorio_cache: Path) -> dict | None:
    caminho = _caminho_ultimo_macro(diretorio_cache)
    if not caminho.exists():
        return None
    try:
        dados = json.loads(caminho.read_text())
        return {
            "selic_meta": float(dados["selic_meta"]),
            "ipca_12m": float(dados["ipca_12m"]),
            "data_ipca": pd.Timestamp(dados["data_ipca"]),
            "data_busca": pd.Timestamp(dados["data_busca"]),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _buscar_selic_e_ipca_do_bcb(
    hoje: datetime, diretorio_cache: Path
) -> tuple[float, float, pd.Timestamp]:
    selic_df = obter_serie(
        SERIES_BCB_SGS["selic_meta"],
        data_inicial=(hoje - timedelta(days=JANELA_BUSCA_SELIC_DIAS)).strftime("%d/%m/%Y"),
        data_final=hoje.strftime("%d/%m/%Y"),
        diretorio_cache=diretorio_cache,
    )
    selic_meta = float(selic_df.iloc[-1]["valor"]) / 100

    ipca_df = obter_serie(
        SERIES_BCB_SGS["ipca_mensal"],
        data_inicial=(hoje - timedelta(days=JANELA_BUSCA_IPCA_DIAS)).strftime("%d/%m/%Y"),
        data_final=hoje.strftime("%d/%m/%Y"),
        diretorio_cache=diretorio_cache,
    )
    if len(ipca_df) < MESES_IPCA_ACUMULADO:
        raise DadosMacroInsuficientesError(
            f"IPCA voltou com {len(ipca_df)} leitura(s), precisa de pelo "
            f"menos {MESES_IPCA_ACUMULADO} pra acumular 12 meses."
        )
    janela_ipca = ipca_df.tail(MESES_IPCA_ACUMULADO)
    ipca_12m = float((1 + janela_ipca["valor"] / 100).prod() - 1)
    data_ipca = janela_ipca["data"].iloc[-1]
    return selic_meta, ipca_12m, data_ipca


def obter_selic_e_ipca(diretorio_cache: Path = DATA_RAW_DIR) -> ResultadoMacro:
    """Selic meta (decimal) e IPCA acumulado 12 meses (decimal) — função
    única usada tanto pelo app quanto pelo screener.

    Em falha temporária (5xx, timeout, conexão — `obter_serie` já tenta de
    novo sozinha, ver `_get_com_retry`), cai pro último valor com sucesso
    guardado em disco (`_caminho_ultimo_macro`), contanto que tenha no
    máximo `VALIDADE_MACRO_GUARDADO_DIAS`. Sem valor guardado recente o
    bastante, levanta `MacroIndisponivelError` com mensagem já pronta pra
    tela. Com o IPCA vindo incompleto a API respondeu, então não é falha
    de rede: levanta `DadosMacroInsuficientesError` direto, sem tentar o
    valor guardado.
    """
    hoje = datetime.now()
    try:
        selic_meta, ipca_12m, data_ipca = _buscar_selic_e_ipca_do_bcb(hoje, diretorio_cache)
    except DadosMacroInsuficientesError:
        raise
    except Exception as erro:
        warnings.warn(f"Falha ao buscar Selic/IPCA do BCB: {erro}", stacklevel=2)
        guardado = _carregar_ultimo_macro(diretorio_cache)
        if guardado is not None:
            idade_dias = (pd.Timestamp(hoje) - guardado["data_busca"]).days
            if idade_dias <= VALIDADE_MACRO_GUARDADO_DIAS:
                return ResultadoMacro(
                    selic_meta=guardado["selic_meta"],
                    ipca_12m=guardado["ipca_12m"],
                    data_ipca=guardado["data_ipca"],
                    usou_valor_guardado=True,
                    data_busca=guardado["data_busca"],
                )
        raise MacroIndisponivelError(MENSAGEM_MACRO_INDISPONIVEL) from erro

    _salvar_ultimo_macro(diretorio_cache, selic_meta, ipca_12m, data_ipca, hoje)
    return ResultadoMacro(
        selic_meta=selic_meta,
        ipca_12m=ipca_12m,
        data_ipca=data_ipca,
        usou_valor_guardado=False,
        data_busca=pd.Timestamp(hoje),
    )
