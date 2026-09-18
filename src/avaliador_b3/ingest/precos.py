"""Adapter para preço histórico de ações da B3 via yfinance.

yfinance não é uma API oficial do Yahoo Finance — é um wrapper que raspa
endpoints não documentados, então quebra/rate-limita de vez em quando. Esse
adapter trata dois caminhos de falha bem diferentes:

- `TickerInvalido`: o ticker não existe/foi deslistado — não adianta tentar
  de novo, o chamador deve pular essa ação.
- `FalhaFontePreco`: falha transitória (rate limit, erro de rede, resposta
  em formato inesperado) — vale tentar de novo mais tarde.

Cache local em `data/raw/precos/` com TTL curto (minutos, não "para
sempre"): diferente das séries do BCB/GPR, preço de ação fica velho
rápido, e o próprio Yahoo já entrega com delay de ~15 min.

Delay configurável antes de cada requisição real (não em cache hit) — o
screener bate no yfinance várias vezes por ação (histórico em 2 janelas +
dividendos) × ~76 ações do Ibovespa, e essa API não-oficial é conhecida
por limitar taxa agressivamente sem isso.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from avaliador_b3.config import (
    DATA_RAW_DIR,
    DELAY_PRECOS_SEGUNDOS,
    SUFIXO_TICKER_B3,
    TICKER_IBOVESPA,
    TTL_CACHE_DIVIDENDOS_SEGUNDOS,
    TTL_CACHE_PRECOS_SEGUNDOS,
)


class ErroPrecos(Exception):
    """Base para erros do adapter de preços."""


class TickerInvalido(ErroPrecos):
    """O ticker não existe ou foi deslistado — repetir a busca não ajuda."""


class FalhaFontePreco(ErroPrecos):
    """Falha transitória do yfinance (rate limit, erro de rede, formato da
    resposta mudou) — vale a pena tentar de novo mais tarde."""


def _ticker_yahoo(ticker: str) -> str:
    """Normaliza um código B3 (ex: "petr4") para o ticker do Yahoo Finance
    (ex: "PETR4.SA"). Não duplica o sufixo se ele já vier incluso. Tickers
    de índice (prefixo "^", ex: "^BVSP" pro Ibovespa) ou de futuros
    (sufixo "=F", ex: "BZ=F" pro petróleo Brent) não são ação B3 — passam
    direto, sem sufixo, no formato que o Yahoo já usa pra eles."""
    ticker = ticker.strip().upper()
    if ticker.startswith("^") or ticker.endswith("=F") or ticker.endswith(SUFIXO_TICKER_B3):
        return ticker
    return ticker + SUFIXO_TICKER_B3


def _caminho_cache(
    ticker_yahoo: str, periodo: str, diretorio_cache: Path, auto_adjust: bool = True
) -> Path:
    # O período precisa fazer parte da chave de cache — sem isso, pedir o
    # mesmo ticker com períodos diferentes (ex: "3mo" pra volume/
    # volatilidade e "1y" pra Beta) faz uma busca sobrescrever o cache da
    # outra, e uma delas passa a ler dado do período errado silenciosamente.
    # `auto_adjust` também precisa fazer parte da chave, pelo mesmo motivo:
    # preço ajustado (retroativamente por todos os dividendos futuros, bom
    # pra cálculo de retorno/Beta) e preço nominal da época (bom pra
    # Dividend Yield histórico, ver graficos.calcular_dividend_yield_por_ano)
    # são dados BEM diferentes pro mesmo ticker/período — sem isso, uma
    # busca sobrescreveria o cache da outra silenciosamente, igual ao bug
    # de período já corrigido aqui. Sem sufixo no caso padrão (auto_adjust
    # True) pra não invalidar nenhum cache já gravado em disco antes dessa
    # mudança.
    sufixo_ajuste = "" if auto_adjust else "_naoajustado"
    return diretorio_cache / "precos" / f"{ticker_yahoo}_{periodo}{sufixo_ajuste}.csv"


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
    delay_segundos: float = DELAY_PRECOS_SEGUNDOS,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Busca o histórico de preços de uma ação da B3.

    `ticker` é o código B3 (ex: "PETR4"), com ou sem o sufixo ".SA".
    `periodo` segue a convenção do yfinance ("5d", "1mo", "3mo", "1y", ...).

    Levanta `TickerInvalido` se o ticker não existir, ou `FalhaFontePreco`
    se a busca falhar por outro motivo (rate limit, erro de rede, etc.).

    `delay_segundos` é aplicado antes de cada requisição real (não em
    cache hit) — existe pra não bater rápido demais no yfinance quando o
    screener passar por várias dezenas de tickers em sequência.

    `auto_adjust` (padrão `True`, igual ao padrão do yfinance) controla se
    "Close" vem ajustado retroativamente por dividendos (e splits) — bom
    pra cálculo de RETORNO (Beta, volatilidade, "Preço vs. Ibovespa"), já
    que aí o que importa é a variação percentual real pro investidor,
    dividendo incluso. Passar `auto_adjust=False` devolve o preço NOMINAL
    de cada dia (o que realmente foi negociado na época) — necessário pra
    Dividend Yield histórico (`graficos.calcular_dividend_yield_por_ano`):
    usar o preço ajustado ali sub-avalia (às vezes bem) o preço da época,
    porque um ajuste retroativo por TODOS os dividendos futuros também
    "desconta" dividendos que ainda nem tinham sido pagos naquele
    momento — bug real encontrado comparando o Dividend Yield de 2021 da
    PETR4 contra uma fonte de mercado externa (~20% esperado, 73,5%
    calculado com preço ajustado).
    """
    ticker_yahoo = _ticker_yahoo(ticker)
    caminho = _caminho_cache(ticker_yahoo, periodo, diretorio_cache, auto_adjust)

    if usar_cache and not forcar_atualizacao and _cache_valido(caminho, ttl_segundos):
        return pd.read_csv(caminho, parse_dates=["data"])

    if delay_segundos > 0:
        time.sleep(delay_segundos)

    try:
        historico = yf.Ticker(ticker_yahoo).history(period=periodo, auto_adjust=auto_adjust)
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
    # Tickers fora do Brasil (ex: "BZ=F", petróleo, fuso America/New_York)
    # observam horário de verão — um histórico de meses/anos atravessa a
    # transição e mistura offsets diferentes (-04:00/-05:00) na mesma
    # coluna. Igual ao fix já aplicado em obter_dividendos pro mesmo tipo
    # de problema (lá, offsets -03:00/-02:00 do Brasil pré-2019): converte
    # pra UTC antes de cachear, pra nunca gravar um CSV com offsets
    # mistos que pd.read_csv(parse_dates=...) não consegue reler de volta.
    historico["data"] = historico["data"].dt.tz_convert("UTC")

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        historico.to_csv(caminho, index=False)

    return historico


def obter_historico_ibovespa(
    periodo: str = "3mo",
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    ttl_segundos: int = TTL_CACHE_PRECOS_SEGUNDOS,
    diretorio_cache: Path = DATA_RAW_DIR,
    delay_segundos: float = DELAY_PRECOS_SEGUNDOS,
) -> pd.DataFrame:
    """Histórico do índice Ibovespa (mesmo formato de `obter_historico`,
    reaproveitando cache/tratamento de erro) — usado pro cálculo de Beta
    (`empresa.comportamento`) e, futuramente, pra sobreposição no gráfico
    de preço da ação."""
    return obter_historico(
        TICKER_IBOVESPA,
        periodo=periodo,
        usar_cache=usar_cache,
        forcar_atualizacao=forcar_atualizacao,
        ttl_segundos=ttl_segundos,
        diretorio_cache=diretorio_cache,
        delay_segundos=delay_segundos,
    )


def _caminho_cache_dividendos(ticker_yahoo: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "precos" / f"{ticker_yahoo}_dividendos.csv"


def obter_dividendos(
    ticker: str,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    ttl_segundos: int = TTL_CACHE_DIVIDENDOS_SEGUNDOS,
    diretorio_cache: Path = DATA_RAW_DIR,
    delay_segundos: float = DELAY_PRECOS_SEGUNDOS,
) -> pd.DataFrame:
    """Busca o histórico completo de dividendos pagos por uma ação da B3
    (todas as datas disponíveis no Yahoo Finance — ex: PETR4 tem registros
    desde 2005), devolvendo um DataFrame com colunas `data` e `dividendo`.

    Uma ação que nunca pagou dividendo devolve um DataFrame vazio — isso
    **não** é erro, é um resultado válido (comum em empresas de
    crescimento) usado por métodos como o de Bazin para concluir que o
    método não é aplicável àquela ação.

    Levanta `TickerInvalido` se o ticker não existir, ou `FalhaFontePreco`
    se a busca falhar por outro motivo. Diferente de `obter_historico`, um
    ticker inválido aqui faz o yfinance levantar `AttributeError` (em vez
    de devolver um resultado vazio) — comportamento observado e tratado
    explicitamente, não documentado pela biblioteca.
    """
    ticker_yahoo = _ticker_yahoo(ticker)
    caminho = _caminho_cache_dividendos(ticker_yahoo, diretorio_cache)

    if usar_cache and not forcar_atualizacao and _cache_valido(caminho, ttl_segundos):
        df_cache = pd.read_csv(caminho)
        df_cache["data"] = pd.to_datetime(df_cache["data"], utc=True)
        return df_cache

    if delay_segundos > 0:
        time.sleep(delay_segundos)

    try:
        serie = yf.Ticker(ticker_yahoo).dividends
    except yf.exceptions.YFTickerMissingError as erro:
        raise TickerInvalido(
            f"Ticker {ticker_yahoo!r} não encontrado no Yahoo Finance."
        ) from erro
    except AttributeError as erro:
        raise TickerInvalido(
            f"Ticker {ticker_yahoo!r} não encontrado no Yahoo Finance "
            "(yfinance falhou internamente ao buscar dividendos de um "
            "ticker inexistente)."
        ) from erro
    except Exception as erro:
        raise FalhaFontePreco(
            f"Falha ao buscar dividendos de {ticker_yahoo!r} via yfinance — "
            "pode ser rate limit, erro de rede, ou mudança na resposta da "
            "API não-oficial do Yahoo. Tente de novo mais tarde."
        ) from erro

    if serie is None:
        # Outra variação do mesmo comportamento não documentado: em vez de
        # levantar AttributeError (tratado acima), às vezes `.dividends`
        # simplesmente devolve None pra ticker inexistente, sem exceção
        # nenhuma. Observado rodando o app manualmente contra um ticker
        # inválido, não coberto pelos testes originais.
        raise TickerInvalido(
            f"Ticker {ticker_yahoo!r} não encontrado no Yahoo Finance "
            "(dividends veio None, sem levantar exceção)."
        )

    dividendos = serie.rename_axis("data").reset_index(name="dividendo")
    if not dividendos.empty:
        # O histórico vai até 2005 e atravessa mudanças de horário de verão
        # no Brasil (offsets -03:00/-02:00 misturados na mesma coluna) —
        # normalizar pra UTC evita ambiguidade ao reler o cache depois.
        dividendos["data"] = dividendos["data"].dt.tz_convert("UTC")

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        dividendos.to_csv(caminho, index=False)

    return dividendos
