"""Adapter para o SGS (Sistema Gerenciador de Séries Temporais) do Banco
Central do Brasil.

Fonte principal: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados
Documentação: https://dadosabertos.bcb.gov.br/
Segunda fonte, as mesmas séries pelo serviço SOAP do SGS no www3 (ver `obter_serie_soap`).

A API não retorna um código HTTP de erro para código de série inválido —
devolve HTTP 200 com uma página HTML de erro no lugar do JSON esperado.
Por isso a resposta é sempre validada como JSON antes de virar DataFrame.
"""

from __future__ import annotations

import json
import logging
import re
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from avaliador_b3.config import (
    CAMINHO_MACRO_REFERENCIA,
    DATA_RAW_DIR,
    FONTE_ARQUIVO_REFERENCIA,
    FONTE_BCB_API,
    FONTE_BCB_SOAP,
    FONTE_IBGE,
    FONTE_VALOR_GUARDADO,
    JANELA_BUSCA_IPCA_DIAS,
    JANELA_BUSCA_SELIC_DIAS,
    JANELA_BUSCA_SELIC_SOAP_DIAS,
    MESES_BUSCA_IPCA_SIDRA,
    MESES_IPCA_ACUMULADO,
    PAUSAS_RETRY_FONTE_SECUNDARIA_SEGUNDOS,
    PAUSAS_RETRY_SEGUNDOS,
    SERIES_BCB_SGS,
    SUFIXO_ORIGEM_FONTE_GUARDADA,
    TIMEOUT_SEGUNDOS_BCB_SGS,
    TIMEOUT_SEGUNDOS_BCB_SOAP,
    URL_BCB_SOAP,
    VALIDADE_MACRO_GUARDADO_DIAS,
    VALIDADE_MACRO_REFERENCIA_DIAS,
)
from avaliador_b3.ingest._cache import (
    gravar_csv_atomico,
    gravar_json_atomico,
    ler_csv_cache,
    ler_json_cache,
)
from avaliador_b3.ingest._retry import get_com_retry, post_com_retry
from avaliador_b3.ingest.ibge_sidra import obter_ipca_mensal_sidra

_log = logging.getLogger(__name__)

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
    """IPCA voltou com menos leituras que MESES_IPCA_ACUMULADO: o acumulado sairia
    subestimado em silêncio (menos meses multiplicados), então o cálculo é recusado.
    Conta como falha daquela fonte (a cadeia tenta a próxima); só sobe se nenhuma
    fonte nem o valor guardado trouxer os 12 meses."""


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
        return df.assign(data=pd.to_datetime(df["data"]), valor=df["valor"].astype(float))
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = df["valor"].astype(float)
    return df.sort_values("data").reset_index(drop=True)


def _caminho_cache(
    codigo: int, data_inicial: str | None, data_final: str | None, diretorio_cache: Path
) -> Path:
    # data_inicial/data_final fazem parte da chave de cache: um chamador com
    # janela ROLANTE (ex: app/main.py recalcula "hoje - N dias" a "hoje" a cada
    # execução) ficaria preso à janela do primeiro fetch, já que a única
    # checagem de validade é `caminho.exists()`. Mesma ideia da chave por
    # `periodo` em ingest/precos.py. As datas trocam "/" por "-" pra virarem
    # nome de arquivo válido. Sem sufixo quando as duas são None (série
    # inteira), caso só usado em teste (todo chamador real passa datas).
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
        em_cache = ler_csv_cache(caminho, ("data", "valor"), parse_dates=["data"])
        if em_cache is not None:
            return em_cache

    url = _montar_url(codigo, data_inicial, data_final)
    resposta = _get_com_retry(url)
    registros = _parsear_resposta(resposta.text, codigo)
    df = _registros_para_dataframe(registros)

    if usar_cache:
        gravar_csv_atomico(df, caminho)

    return df


# --- Segunda fonte: serviço SOAP do SGS no www3 do BCB -----------------------


def _envelope_soap_valores(codigo: int, data_inicial: str, data_final: str) -> str:
    """Envelope SOAP de `getValoresSeriesXML` para uma série; datas dd/mm/aaaa."""
    return (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:pub="http://publico.ws.casosdeuso.sgs.pec.bcb.gov.br" '
        'xmlns:soapenc="http://schemas.xmlsoap.org/soap/encoding/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><soapenv:Header/><soapenv:Body>'
        "<pub:getValoresSeriesXML>"
        '<in0 soapenc:arrayType="xsd:long[1]" xsi:type="soapenc:Array">'
        f'<item xsi:type="xsd:long">{codigo}</item></in0>'
        f"<in1>{data_inicial}</in1><in2>{data_final}</in2>"
        "</pub:getValoresSeriesXML></soapenv:Body></soapenv:Envelope>"
    )


def _parsear_resposta_soap(texto: str, codigo: int) -> list[dict]:
    """Registros {"data": "dd/mm/aaaa", "valor": "..."} da resposta SOAP, no mesmo
    formato da API REST. O serviço devolve um XML dentro do XML do envelope; a data
    vem como d/m/aaaa nas séries diárias e m/aaaa nas mensais (dia 1).
    Levanta ValueError se a resposta não trouxer valores."""
    try:
        raiz = ET.fromstring(texto)
        retorno = next(
            (el for el in raiz.iter() if el.tag.endswith("getValoresSeriesXMLReturn")), None
        )
        corpo = (retorno.text or "").strip() if retorno is not None else ""
        # A declaração de codificação interna não vale numa string já decodificada.
        serie = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", corpo)) if corpo else None
    except ET.ParseError as erro:
        raise ValueError(f"Resposta SOAP do BCB para a série {codigo} não é XML válido.") from erro
    registros = []
    for item in serie.iter("ITEM") if serie is not None else []:
        partes = (item.findtext("DATA") or "").split("/")
        valor = item.findtext("VALOR")
        if valor is None or len(partes) not in (2, 3):
            continue
        dia, mes, ano = ["1", *partes] if len(partes) == 2 else partes
        registros.append({"data": f"{int(dia):02d}/{int(mes):02d}/{ano}", "valor": valor})
    if not registros:
        raise ValueError(f"Resposta SOAP do BCB sem valores para a série {codigo}.")
    return registros


def obter_serie_soap(codigo: int, data_inicial: str, data_final: str) -> pd.DataFrame:
    """Mesma série de `obter_serie`, pelo serviço SOAP do SGS (www3.bcb.gov.br), com
    colunas `data` e `valor`. Sem cache em disco. Datas dd/mm/aaaa; o serviço pode
    devolver datas posteriores a `data_final` em séries diárias de meta (a Selic vem
    preenchida até a próxima reunião do Copom), então o chamador filtra por hoje."""
    resposta = post_com_retry(
        URL_BCB_SOAP,
        TIMEOUT_SEGUNDOS_BCB_SOAP,
        PAUSAS_RETRY_FONTE_SECUNDARIA_SEGUNDOS,
        data=_envelope_soap_valores(codigo, data_inicial, data_final).encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
    )
    return _registros_para_dataframe(_parsear_resposta_soap(resposta.text, codigo))


def obter_serie_com_fallback(
    codigo: int,
    data_inicial: str,
    data_final: str,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """`obter_serie` (API REST) e, se ela falhar (rede, HTTP ou resposta que não é
    JSON), a mesma série pelo SOAP, só com as leituras até hoje. Se o SOAP também
    falhar, levanta o erro da API REST."""
    try:
        return obter_serie(codigo, data_inicial, data_final, diretorio_cache=diretorio_cache)
    except (requests.RequestException, ValueError) as erro_api:
        _log.warning("Falha ao buscar a série %s do %s: %s", codigo, FONTE_BCB_API, erro_api)
        try:
            return _ate_hoje(obter_serie_soap(codigo, data_inicial, data_final), datetime.now())
        except Exception as erro_soap:
            raise erro_api from erro_soap


@dataclass
class ResultadoMacro:
    """Selic meta e IPCA acumulado 12 meses, com a proveniência do dado —
    ver `obter_selic_e_ipca`. `fonte_selic` e `fonte_ipca` dizem de onde veio cada
    valor (ex.: "BCB (API)", "BCB (SOAP)", "valor guardado de 29/09/2026 (origem: BCB (SOAP))")."""

    selic_meta: float
    ipca_12m: float
    data_ipca: pd.Timestamp
    usou_valor_guardado: bool
    data_busca: pd.Timestamp
    fonte_selic: str = FONTE_BCB_API
    fonte_ipca: str = FONTE_BCB_API


def _caminho_ultimo_macro(diretorio_cache: Path) -> Path:
    return diretorio_cache / "bcb" / "ultimo_macro.json"


def _caminho_macro_referencia() -> Path:
    return CAMINHO_MACRO_REFERENCIA


def _gravar_macro(
    caminho: Path,
    selic_meta: float,
    ipca_12m: float,
    data_ipca: pd.Timestamp,
    data_busca: datetime,
    fonte_selic: str,
    fonte_ipca: str,
    estrito: bool = False,
) -> None:
    gravar_json_atomico(
        caminho,
        {
            "selic_meta": selic_meta,
            "ipca_12m": ipca_12m,
            "data_ipca": data_ipca.strftime("%Y-%m-%d"),
            "data_busca": data_busca.isoformat(),
            "fonte_selic": fonte_selic,
            "fonte_ipca": fonte_ipca,
        },
        estrito=estrito,
    )


def _salvar_ultimo_macro(
    diretorio_cache: Path,
    selic_meta: float,
    ipca_12m: float,
    data_ipca: pd.Timestamp,
    data_busca: datetime,
    fonte_selic: str = FONTE_BCB_API,
    fonte_ipca: str = FONTE_BCB_API,
) -> None:
    _gravar_macro(
        _caminho_ultimo_macro(diretorio_cache),
        selic_meta,
        ipca_12m,
        data_ipca,
        data_busca,
        fonte_selic,
        fonte_ipca,
    )


def carregar_macro_referencia() -> dict | None:
    """Selic, IPCA, fontes e data da busca do arquivo de referência versionado (gravado a
    cada rodada aceita do screener); `None` se não existir ou estiver inválido."""
    return _ler_macro(_caminho_macro_referencia())


def salvar_macro_referencia(resultado: ResultadoMacro, caminho: Path) -> None:
    """Grava no arquivo de referência (versionado com o screener.csv) a Selic, o IPCA, as
    fontes e a data da busca de um resultado obtido ao vivo."""
    _gravar_macro(
        caminho,
        resultado.selic_meta,
        resultado.ipca_12m,
        resultado.data_ipca,
        resultado.data_busca.to_pydatetime(),
        resultado.fonte_selic,
        resultado.fonte_ipca,
        estrito=True,
    )


def _carregar_ultimo_macro(diretorio_cache: Path) -> dict | None:
    return _ler_macro(_caminho_ultimo_macro(diretorio_cache))


def _fonte_gravada(valor: object) -> str | None:
    """Fonte registrada na gravação, ou `None` se o arquivo é antigo ou o campo não é texto."""
    return valor if isinstance(valor, str) and valor else None


def _fonte_do_guardado(modelo: str, guardado: dict, chave: str) -> str:
    """Texto da fonte de um valor guardado: o modelo (com a data da busca) e, se o arquivo
    registrou, a fonte de onde o valor veio na busca original."""
    fonte = modelo.format(data=f"{guardado['data_busca']:%d/%m/%Y}")
    origem = guardado.get(chave)
    return fonte + SUFIXO_ORIGEM_FONTE_GUARDADA.format(origem=origem) if origem else fonte


def _ler_macro(caminho: Path) -> dict | None:
    if not caminho.exists():
        return None
    dados = ler_json_cache(caminho)
    if dados is None:
        return None
    try:
        return {
            "selic_meta": float(dados["selic_meta"]),
            "ipca_12m": float(dados["ipca_12m"]),
            "data_ipca": pd.Timestamp(dados["data_ipca"]),
            "data_busca": pd.Timestamp(dados["data_busca"]),
            "fonte_selic": _fonte_gravada(dados.get("fonte_selic")),
            "fonte_ipca": _fonte_gravada(dados.get("fonte_ipca")),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _selic_meta_do_dataframe(selic_df: pd.DataFrame) -> float:
    """Meta Selic (decimal) do último valor da série; `ValueError` se vier vazia."""
    if selic_df.empty:
        raise ValueError("Série da Selic meta voltou vazia.")
    return float(selic_df.iloc[-1]["valor"]) / 100


def _ipca_12m_do_dataframe(ipca_df: pd.DataFrame) -> tuple[float, pd.Timestamp]:
    """IPCA acumulado nos últimos `MESES_IPCA_ACUMULADO` meses (decimal) e o mês da
    última leitura. `DadosMacroInsuficientesError` se a série vier incompleta."""
    if len(ipca_df) < MESES_IPCA_ACUMULADO:
        raise DadosMacroInsuficientesError(
            f"IPCA voltou com {len(ipca_df)} leitura(s), precisa de pelo "
            f"menos {MESES_IPCA_ACUMULADO} pra acumular 12 meses."
        )
    janela_ipca = ipca_df.tail(MESES_IPCA_ACUMULADO)
    ipca_12m = float((1 + janela_ipca["valor"] / 100).prod() - 1)
    return ipca_12m, janela_ipca["data"].iloc[-1]


def _ate_hoje(df: pd.DataFrame, hoje: datetime) -> pd.DataFrame:
    """Só as leituras até hoje: o SOAP pode trazer datas futuras na Selic meta."""
    return df[df["data"] <= pd.Timestamp(hoje.date())].reset_index(drop=True)


def _percorrer_fontes(passos: list, falhas: dict):
    """Primeiro passo (fonte, buscar) que responde: devolve (fonte, resultado). Uma fonte
    que já falhou em outra série é pulada (falha rápida, para não somar esperas). Falha de
    uma fonte, inclusive IPCA com menos de 12 meses, só vai para o log; a próxima fonte
    tenta. Sem nenhuma fonte, levanta o `DadosMacroInsuficientesError` (se alguma trouxe o
    IPCA incompleto) ou a primeira falha."""
    for fonte, buscar in passos:
        if fonte in falhas:
            continue
        try:
            return fonte, buscar()
        except Exception as erro:
            falhas[fonte] = erro
            _log.warning("Falha ao buscar Selic/IPCA do %s: %s", fonte, erro)
    incompleto = next(
        (e for e in falhas.values() if isinstance(e, DadosMacroInsuficientesError)), None
    )
    raise incompleto or next(iter(falhas.values()))


def _buscar_selic_e_ipca(
    hoje: datetime, diretorio_cache: Path
) -> tuple[float, float, pd.Timestamp, str, str]:
    """Selic meta, IPCA 12m, mês do IPCA e a fonte de cada um, pela cadeia: BCB (API),
    BCB (SOAP) e, só para o IPCA, IBGE (SIDRA). Selic e IPCA podem vir de fontes
    diferentes; o mês de referência do IPCA vem junto."""
    falhas: dict = {}
    fmt = "%d/%m/%Y"

    def selic_api() -> float:
        return _selic_meta_do_dataframe(
            obter_serie(
                SERIES_BCB_SGS["selic_meta"],
                data_inicial=(hoje - timedelta(days=JANELA_BUSCA_SELIC_DIAS)).strftime(fmt),
                data_final=hoje.strftime(fmt),
                diretorio_cache=diretorio_cache,
            )
        )

    def selic_soap() -> float:
        inicio = (hoje - timedelta(days=JANELA_BUSCA_SELIC_SOAP_DIAS)).strftime(fmt)
        df = obter_serie_soap(SERIES_BCB_SGS["selic_meta"], inicio, hoje.strftime(fmt))
        return _selic_meta_do_dataframe(_ate_hoje(df, hoje))

    def ipca_api() -> tuple[float, pd.Timestamp]:
        return _ipca_12m_do_dataframe(
            obter_serie(
                SERIES_BCB_SGS["ipca_mensal"],
                data_inicial=(hoje - timedelta(days=JANELA_BUSCA_IPCA_DIAS)).strftime(fmt),
                data_final=hoje.strftime(fmt),
                diretorio_cache=diretorio_cache,
            )
        )

    def ipca_soap() -> tuple[float, pd.Timestamp]:
        inicio = (hoje - timedelta(days=JANELA_BUSCA_IPCA_DIAS)).strftime(fmt)
        df = obter_serie_soap(SERIES_BCB_SGS["ipca_mensal"], inicio, hoje.strftime(fmt))
        return _ipca_12m_do_dataframe(_ate_hoje(df, hoje))

    def ipca_sidra() -> tuple[float, pd.Timestamp]:
        return _ipca_12m_do_dataframe(
            _ate_hoje(obter_ipca_mensal_sidra(MESES_BUSCA_IPCA_SIDRA), hoje)
        )

    fonte_selic, selic_meta = _percorrer_fontes(
        [(FONTE_BCB_API, selic_api), (FONTE_BCB_SOAP, selic_soap)], falhas
    )
    fonte_ipca, (ipca_12m, data_ipca) = _percorrer_fontes(
        [(FONTE_BCB_API, ipca_api), (FONTE_BCB_SOAP, ipca_soap), (FONTE_IBGE, ipca_sidra)],
        falhas,
    )
    return selic_meta, ipca_12m, data_ipca, fonte_selic, fonte_ipca


def obter_selic_e_ipca(diretorio_cache: Path = DATA_RAW_DIR) -> ResultadoMacro:
    """Selic meta (decimal) e IPCA acumulado 12 meses (decimal) — função
    única usada tanto pelo app quanto pelo screener.

    Cadeia de fontes: BCB (API), BCB (SOAP), IBGE (SIDRA, só o IPCA), o valor com sucesso
    guardado em disco (`_caminho_ultimo_macro`, no máximo `VALIDADE_MACRO_GUARDADO_DIAS`) e,
    por último, o arquivo de referência versionado (no máximo `VALIDADE_MACRO_REFERENCIA_DIAS`).
    Os dois últimos vêm com `usou_valor_guardado=True`. Cada fonte tenta de novo sozinha em
    falha temporária (5xx, timeout, conexão — ver `ingest._retry`), e IPCA com menos de 12
    meses conta como falha daquela fonte. Falhas intermediárias só vão para o log. Sem
    nenhuma fonte nem valor guardado, levanta `MacroIndisponivelError` com mensagem já pronta
    pra tela, ou `DadosMacroInsuficientesError` se alguma fonte respondeu com o IPCA incompleto
    e nenhuma trouxe os 12 meses. O resultado diz a fonte de cada valor.
    """
    hoje = datetime.now()
    try:
        selic_meta, ipca_12m, data_ipca, fonte_selic, fonte_ipca = _buscar_selic_e_ipca(
            hoje, diretorio_cache
        )
    except Exception as erro:
        warnings.warn(f"Falha ao buscar Selic/IPCA do BCB: {erro}", stacklevel=2)
        for guardado, validade_dias, modelo_fonte in (
            (
                _carregar_ultimo_macro(diretorio_cache),
                VALIDADE_MACRO_GUARDADO_DIAS,
                FONTE_VALOR_GUARDADO,
            ),
            (
                _ler_macro(_caminho_macro_referencia()),
                VALIDADE_MACRO_REFERENCIA_DIAS,
                FONTE_ARQUIVO_REFERENCIA,
            ),
        ):
            if guardado is None:
                continue
            if (pd.Timestamp(hoje) - guardado["data_busca"]).days <= validade_dias:
                return ResultadoMacro(
                    selic_meta=guardado["selic_meta"],
                    ipca_12m=guardado["ipca_12m"],
                    data_ipca=guardado["data_ipca"],
                    usou_valor_guardado=True,
                    data_busca=guardado["data_busca"],
                    fonte_selic=_fonte_do_guardado(modelo_fonte, guardado, "fonte_selic"),
                    fonte_ipca=_fonte_do_guardado(modelo_fonte, guardado, "fonte_ipca"),
                )
        if isinstance(erro, DadosMacroInsuficientesError):
            raise
        raise MacroIndisponivelError(MENSAGEM_MACRO_INDISPONIVEL) from erro

    _salvar_ultimo_macro(
        diretorio_cache, selic_meta, ipca_12m, data_ipca, hoje, fonte_selic, fonte_ipca
    )
    return ResultadoMacro(
        selic_meta=selic_meta,
        ipca_12m=ipca_12m,
        data_ipca=data_ipca,
        usou_valor_guardado=False,
        data_busca=pd.Timestamp(hoje),
        fonte_selic=fonte_selic,
        fonte_ipca=fonte_ipca,
    )
