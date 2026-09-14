"""Adapter para preço histórico de ações da B3 via yfinance.

yfinance não é uma API oficial do Yahoo Finance — é um wrapper que raspa
endpoints não documentados, então quebra/rate-limita de vez em quando. Esse
adapter trata dois caminhos de falha bem diferentes:

- `TickerInvalido`: o ticker não existe/foi deslistado — não adianta tentar
  de novo, o chamador deve pular essa ação.
- `FalhaFontePreco`: falha transitória (rate limit, erro de rede, resposta
  em formato inesperado) — vale tentar de novo mais tarde.

Cache local em `data/raw/precos/` com TTL curto (minutos, não "para
sempre"): diferente das séries do BCB/GPR/GDELT, preço de ação fica velho
rápido, e o próprio Yahoo já entrega com delay de ~15 min.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from avaliador_b3.config import DATA_RAW_DIR, SUFIXO_TICKER_B3, TTL_CACHE_PRECOS_SEGUNDOS


class ErroPrecos(Exception):
    """Base para erros do adapter de preços."""


class TickerInvalido(ErroPrecos):
    """O ticker não existe ou foi deslistado — repetir a busca não ajuda."""


class FalhaFontePreco(ErroPrecos):
    """Falha transitória do yfinance (rate limit, erro de rede, formato da
    resposta mudou) — vale a pena tentar de novo mais tarde."""


def _ticker_yahoo(ticker: str) -> str:
    """Normaliza um código B3 (ex: "petr4") para o ticker do Yahoo Finance
    (ex: "PETR4.SA"). Não duplica o sufixo se ele já vier incluso."""
    ticker = ticker.strip().upper()
    if ticker.endswith(SUFIXO_TICKER_B3):
        return ticker
    return ticker + SUFIXO_TICKER_B3


def _caminho_cache(ticker_yahoo: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "precos" / f"{ticker_yahoo}.csv"


def _cache_valido(caminho: Path, ttl_segundos: int) -> bool:
    if not caminho.exists():
        return False
    idade_segundos = time.time() - caminho.stat().st_mtime
    return idade_segundos < ttl_segundos


def obter_historico(
    ticker: str,
    periodo: str = "3mo",
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    ttl_segundos: int = TTL_CACHE_PRECOS_SEGUNDOS,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Busca o histórico de preços de uma ação da B3.

    `ticker` é o código B3 (ex: "PETR4"), com ou sem o sufixo ".SA".
    `periodo` segue a convenção do yfinance ("5d", "1mo", "3mo", "1y", ...).

    Levanta `TickerInvalido` se o ticker não existir, ou `FalhaFontePreco`
    se a busca falhar por outro motivo (rate limit, erro de rede, etc.).
    """
    ticker_yahoo = _ticker_yahoo(ticker)
    caminho = _caminho_cache(ticker_yahoo, diretorio_cache)

    if usar_cache and not forcar_atualizacao and _cache_valido(caminho, ttl_segundos):
        return pd.read_csv(caminho, parse_dates=["data"])

    try:
        historico = yf.Ticker(ticker_yahoo).history(period=periodo)
    except yf.exceptions.YFTickerMissingError as erro:
        raise TickerInvalido(
            f"Ticker {ticker_yahoo!r} não encontrado no Yahoo Finance."
        ) from erro
    except Exception as erro:
        raise FalhaFontePreco(
            f"Falha ao buscar {ticker_yahoo!r} via yfinance — pode ser rate "
            "limit, erro de rede, ou mudança na resposta da API não-oficial "
            "do Yahoo. Tente de novo mais tarde."
        ) from erro

    if historico.empty:
        raise TickerInvalido(
            f"Nenhum dado retornado para {ticker_yahoo!r} — ticker inválido "
            "ou deslistado."
        )

    historico = historico.reset_index().rename(columns={"Date": "data"})

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        historico.to_csv(caminho, index=False)

    return historico
