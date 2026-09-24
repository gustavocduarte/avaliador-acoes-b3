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

Cache em disco protegido por dois mecanismos independentes (ver
`VERSAO_SCHEMA_FUNDAMENTUS`/`TTL_CACHE_FUNDAMENTUS_SEGUNDOS` em config.py,
e `_cache_valido`/`_ler_cache_com_schema_atual` abaixo): versionamento de
schema e TTL — um não substitui o outro, ver docstring de
`obter_indicadores`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from avaliador_b3.config import (
    CABECALHOS_FUNDAMENTUS,
    CAMPOS_FUNDAMENTUS,
    CAMPOS_FUNDAMENTUS_OPCIONAIS,
    DATA_RAW_DIR,
    DELAY_FUNDAMENTUS_SEGUNDOS,
    ROTULO_FUNDAMENTUS_DATA_BALANCO,
    TTL_CACHE_FUNDAMENTUS_SEGUNDOS,
    URL_FUNDAMENTUS_DETALHES,
    VERSAO_SCHEMA_FUNDAMENTUS,
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


def _parse_data(texto: str | None) -> str | None:
    """Converte uma data no formato do Fundamentus (dd/mm/aaaa) pra ISO
    (aaaa-mm-dd) — usado só pro campo de "Últ balanço processado"
    (ROTULO_FUNDAMENTUS_DATA_BALANCO em config.py), que não é numérico,
    então não passa por `_parse_numero`. Devolve `None` se o campo não
    veio (`texto is None` — ausente da página) ou não bate no formato
    esperado, sem levantar erro: um problema nesse campo específico não
    deveria derrubar a extração dos demais indicadores."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


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
    # Data do balanço-base dos indicadores acima — parsing próprio (data,
    # não número), ver ROTULO_FUNDAMENTUS_DATA_BALANCO em config.py.
    # `.get(...)` sem default (vira None) porque _parse_data já trata
    # None como "campo ausente", mesmo padrão dos opcionais acima.
    indicadores["data_balanco_fundamentus"] = _parse_data(
        rotulos_valores.get(ROTULO_FUNDAMENTUS_DATA_BALANCO)
    )
    return indicadores


def _caminho_cache(ticker: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "fundamentus" / f"{ticker}.json"


def _cache_valido(caminho: Path, ttl_segundos: int) -> bool:
    """TTL do cache (mesmo padrão de `ingest.precos._cache_valido`) — rede
    de segurança geral, independente do versionamento de schema abaixo
    (ver `_ler_cache_com_schema_atual` e `VERSAO_SCHEMA_FUNDAMENTUS` em
    config.py): protege contra dado desatualizado mesmo quando o schema
    não mudou (indicador fundamentalista muda no máximo por trimestre de
    resultado)."""
    if not caminho.exists():
        return False
    idade_segundos = time.time() - caminho.stat().st_mtime
    return idade_segundos < ttl_segundos


def _ler_cache_com_schema_atual(caminho: Path) -> dict | None:
    """Lê o cache só se a versão de schema gravada bater com
    `VERSAO_SCHEMA_FUNDAMENTUS` atual — devolve `None` (tratado como cache
    miss por `obter_indicadores`, força busca nova) se a versão não bater
    ou o envelope estiver em formato inesperado. Existe pra evitar repetir
    o bug real já acontecido nesta sessão: quando `CAMPOS_FUNDAMENTUS`/
    `CAMPOS_FUNDAMENTUS_OPCIONAIS` ganharam um campo novo, um JSON já
    cacheado (no formato antigo, sem envelope de versão nenhum) continuava
    sendo servido sem esse campo, e o primeiro código que tentasse ler a
    chave nova quebrava com KeyError."""
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if bruto.get("versao_schema") != VERSAO_SCHEMA_FUNDAMENTUS:
        return None
    return bruto.get("indicadores")


def obter_indicadores(
    ticker: str,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    delay_segundos: float = DELAY_FUNDAMENTUS_SEGUNDOS,
    ttl_segundos: int = TTL_CACHE_FUNDAMENTUS_SEGUNDOS,
) -> dict:
    """Busca os indicadores fundamentalistas de uma ação no Fundamentus:
    ROE, margem líquida, LPA, VPA, liquidez corrente, dívida líquida/
    patrimônio, crescimento de receita em 5 anos, número de ações e
    patrimônio líquido (ver `CAMPOS_FUNDAMENTUS` em config.py), dívida
    líquida em valor absoluto (`CAMPOS_FUNDAMENTUS_OPCIONAIS` — ausente
    pra bancos, vira `None`, não erro), e `data_balanco_fundamentus`
    (ISO, `aaaa-mm-dd`) — a data-base "Últ balanço processado" que o
    próprio Fundamentus usa pra todo o resto (ver
    `ROTULO_FUNDAMENTUS_DATA_BALANCO` em config.py); também vira `None`
    se ausente ou em formato inesperado, sem derrubar os demais campos.

    Levanta `TickerNaoEncontrado` se o papel não existir no Fundamentus, ou
    `EstruturaPaginaMudou` se a página existir mas faltar algum campo
    esperado (sinal de mudança no HTML do site, não de ticker inválido).

    `delay_segundos` é aplicado antes de cada requisição real (não em
    leituras de cache) — existe para não bater rápido demais no site
    quando o screener passar por várias dezenas de tickers em sequência.

    O cache em disco (`data/raw/fundamentus/{ticker}.json`) é protegido
    por DOIS mecanismos independentes (ver comentário completo em
    config.py, junto de `VERSAO_SCHEMA_FUNDAMENTUS`/
    `TTL_CACHE_FUNDAMENTUS_SEGUNDOS`): versionamento de schema (invalida o
    cache se `CAMPOS_FUNDAMENTUS`/`CAMPOS_FUNDAMENTUS_OPCIONAIS` mudou
    desde que foi gravado) e TTL de `ttl_segundos` (invalida por idade,
    mesmo sem mudança de schema). Os dois precisam passar pra um cache
    contar como válido.
    """
    ticker = ticker.strip().upper()
    caminho = _caminho_cache(ticker, diretorio_cache)

    if usar_cache and not forcar_atualizacao and _cache_valido(caminho, ttl_segundos):
        indicadores_cache = _ler_cache_com_schema_atual(caminho)
        if indicadores_cache is not None:
            return indicadores_cache
        # Schema mudou desde que esse arquivo foi gravado — ignora o cache
        # e cai pro fetch novo abaixo, como se fosse cache miss.

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
        envelope = {"versao_schema": VERSAO_SCHEMA_FUNDAMENTUS, "indicadores": indicadores}
        caminho.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

    return indicadores
