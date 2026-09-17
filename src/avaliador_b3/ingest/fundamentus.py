"""Adapter para indicadores fundamentalistas via scraping do fundamentus.com.br
(sem API oficial).

Cuidados específicos de scraping, diferente dos outros adapters (que são
APIs): o site bloqueia requisições sem um User-Agent de navegador real, é
servido em ISO-8859-1 (não UTF-8 — decodificar errado corrompe acentos sem
dar erro nenhum), e cada indicador precisa ser localizado por posição no
HTML (par de células `<td class="label">`/`<td>`), não por um contrato
formal de API.

Dois caminhos de falha são tratados separadamente:
  - `TickerNaoEncontrado`: a página não tem nenhuma tabela de indicadores —
    é a resposta do site para um papel que não existe.
  - `EstruturaPaginaMudou`: a página tem uma tabela de indicadores, mas
    falta algum dos rótulos que esperamos — sinal de que o site mudou o
    HTML, não que o ticker é inválido. Levanta erro específico em vez de
    devolver um indicador ausente/errado silenciosamente.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from avaliador_b3.config import (
    CABECALHOS_FUNDAMENTUS,
    CAMPOS_FUNDAMENTUS,
    CAMPOS_FUNDAMENTUS_OPCIONAIS,
    DATA_RAW_DIR,
    DELAY_FUNDAMENTUS_SEGUNDOS,
    URL_FUNDAMENTUS_DETALHES,
)

TIMEOUT_SEGUNDOS = 30
CODIFICACAO_FUNDAMENTUS = "iso-8859-1"


class ErroFundamentus(Exception):
    """Base para erros do adapter do Fundamentus."""


class TickerNaoEncontrado(ErroFundamentus):
    """A página não tem nenhuma tabela de indicadores — ticker inexistente."""


class EstruturaPaginaMudou(ErroFundamentus):
    """A página tem indicadores, mas falta algum campo esperado — o HTML
    do site provavelmente mudou de estrutura."""


def _parse_numero(texto: str) -> float | None:
    """Converte um número no formato do Fundamentus (ex: "27,7%",
    "1.844.240.000", "-2,3%") para float. "-" ou vazio vira None
    (indicador não disponível para aquele papel)."""
    texto = texto.strip()
    if texto in ("", "-"):
        return None
    texto = texto.replace("%", "").replace(".", "").replace(",", ".")
    return float(texto)


def _extrair_rotulos_valores(html: str) -> dict[str, str]:
    """Extrai todos os pares rótulo/valor da página de detalhes: cada
    indicador é um <td class="label"> com o rótulo, seguido do <td> irmão
    seguinte com o valor. Devolve um dict vazio se a página não tiver
    nenhum indicador (ticker não encontrado)."""
    soup = BeautifulSoup(html, "html.parser")
    resultado: dict[str, str] = {}
    for celula_rotulo in soup.select("td.label"):
        rotulo_span = celula_rotulo.find("span", class_="txt")
        if rotulo_span is None:
            continue
        rotulo = rotulo_span.get_text(strip=True)

        celula_valor = celula_rotulo.find_next_sibling("td")
        if celula_valor is None:
            continue
        valor_span = celula_valor.find("span", class_="txt")
        valor = valor_span.get_text(strip=True) if valor_span else celula_valor.get_text(strip=True)

        resultado[rotulo] = valor
    return resultado


def _montar_indicadores(ticker: str, rotulos_valores: dict[str, str]) -> dict:
    faltando = set(CAMPOS_FUNDAMENTUS) - rotulos_valores.keys()
    if faltando:
        raise EstruturaPaginaMudou(
            f"Página do Fundamentus para {ticker!r} não tem os campos esperados "
            f"{sorted(faltando)} — o site pode ter mudado a estrutura da página."
        )

    indicadores: dict = {"ticker": ticker}
    for rotulo, nome_campo in CAMPOS_FUNDAMENTUS.items():
        indicadores[nome_campo] = _parse_numero(rotulos_valores[rotulo])
    # Opcionais (ver CAMPOS_FUNDAMENTUS_OPCIONAIS): ausência do rótulo na
    # página (não só valor vazio) é esperada pra certos tipos de empresa
    # — tratada como "-" (vira None via _parse_numero), não como sinal de
    # a página ter mudado de estrutura.
    for rotulo, nome_campo in CAMPOS_FUNDAMENTUS_OPCIONAIS.items():
        indicadores[nome_campo] = _parse_numero(rotulos_valores.get(rotulo, "-"))
    return indicadores


def _caminho_cache(ticker: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "fundamentus" / f"{ticker}.json"


def obter_indicadores(
    ticker: str,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    delay_segundos: float = DELAY_FUNDAMENTUS_SEGUNDOS,
) -> dict:
    """Busca os indicadores fundamentalistas de uma ação no Fundamentus:
    ROE, margem líquida, LPA, VPA, liquidez corrente, dívida líquida/
    patrimônio, crescimento de receita em 5 anos, número de ações e
    patrimônio líquido (ver `CAMPOS_FUNDAMENTUS` em config.py) e dívida
    líquida em valor absoluto (`CAMPOS_FUNDAMENTUS_OPCIONAIS` — ausente
    pra bancos, vira `None`, não erro).

    Levanta `TickerNaoEncontrado` se o papel não existir no Fundamentus, ou
    `EstruturaPaginaMudou` se a página existir mas faltar algum campo
    esperado (sinal de mudança no HTML do site, não de ticker inválido).

    `delay_segundos` é aplicado antes de cada requisição real (não em
    leituras de cache) — existe para não bater rápido demais no site
    quando o screener passar por várias dezenas de tickers em sequência.
    """
    ticker = ticker.strip().upper()
    caminho = _caminho_cache(ticker, diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))

    if delay_segundos > 0:
        time.sleep(delay_segundos)

    resposta = requests.get(
        URL_FUNDAMENTUS_DETALHES,
        params={"papel": ticker},
        headers=CABECALHOS_FUNDAMENTUS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    resposta.raise_for_status()
    resposta.encoding = CODIFICACAO_FUNDAMENTUS

    rotulos_valores = _extrair_rotulos_valores(resposta.text)
    if not rotulos_valores:
        raise TickerNaoEncontrado(f"Ticker {ticker!r} não encontrado no Fundamentus.")

    indicadores = _montar_indicadores(ticker, rotulos_valores)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(indicadores, ensure_ascii=False), encoding="utf-8")

    return indicadores
