import os
import time

import pandas as pd
import pytest
import yfinance as yf

from avaliador_b3.ingest import precos


@pytest.fixture(autouse=True)
def _sem_delay_yfinance(monkeypatch):
    """Por padrão, os testes não esperam o DELAY_PRECOS_SEGUNDOS real entre
    requisições — só os testes que verificam o delay em si (abaixo)
    substituem esse patch localmente pra inspecionar as chamadas."""
    monkeypatch.setattr(precos.time, "sleep", lambda segundos: None)


class _TickerFalso:
    def __init__(
        self,
        resultado=None,
        excecao=None,
        dividendos_resultado=None,
        dividendos_excecao=None,
    ):
        self._resultado = resultado
        self._excecao = excecao
        self._dividendos_resultado = dividendos_resultado
        self._dividendos_excecao = dividendos_excecao
        self.chamadas = 0
        self.chamadas_dividendos = 0

    def history(self, period):
        self.chamadas += 1
        if self._excecao is not None:
            raise self._excecao
        return self._resultado

    @property
    def dividends(self):
        self.chamadas_dividendos += 1
        if self._dividendos_excecao is not None:
            raise self._dividendos_excecao
        return self._dividendos_resultado


def _historico_falso() -> pd.DataFrame:
    indice = pd.DatetimeIndex(["2026-09-10", "2026-09-11"], name="Date", tz="America/Sao_Paulo")
    return pd.DataFrame(
        {
            "Open": [48.9, 48.5],
            "High": [49.6, 49.1],
            "Low": [48.5, 48.1],
            "Close": [49.1, 49.0],
            "Volume": [43955800, 27610000],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 0.0],
        },
        index=indice,
    )


def _dividendos_falsos() -> pd.Series:
    indice = pd.DatetimeIndex(["2025-08-22", "2026-04-23"], name="Date", tz="America/Sao_Paulo")
    return pd.Series([0.671924, 0.663103], index=indice, name="Dividends")


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("petr4", "PETR4.SA"),
        ("PETR4", "PETR4.SA"),
        ("PETR4.SA", "PETR4.SA"),
        (" vale3 ", "VALE3.SA"),
        ("^bvsp", "^BVSP"),
        ("^BVSP", "^BVSP"),
    ],
)
def test_ticker_yahoo_normaliza(entrada, esperado):
    assert precos._ticker_yahoo(entrada) == esperado


def test_obter_historico_caminho_feliz_grava_cache(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    df = precos.obter_historico("PETR4", diretorio_cache=tmp_path)

    assert list(df.columns[:1]) == ["data"]
    assert len(df) == 2
    assert (tmp_path / "precos" / "PETR4.SA_3mo.csv").exists()


def test_obter_historico_usa_cache_dentro_do_ttl(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)
    precos.obter_historico("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)

    assert ticker_falso.chamadas == 1


def test_obter_historico_refaz_busca_quando_cache_expira(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)

    caminho = tmp_path / "precos" / "PETR4.SA_3mo.csv"
    dez_minutos_atras = time.time() - 600
    os.utime(caminho, (dez_minutos_atras, dez_minutos_atras))

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, ttl_segundos=300)

    assert ticker_falso.chamadas == 2


def test_obter_historico_cache_nao_mistura_periodos_diferentes(tmp_path, monkeypatch):
    # Regressão: pedir o mesmo ticker com períodos diferentes (ex: "3mo"
    # pra volume/volatilidade e "1y" pra Beta) não pode fazer uma busca
    # sobrescrever o cache da outra nem ler o período errado de volta.
    historico_3mo = _historico_falso()
    historico_1y = _historico_falso()
    chamadas_por_periodo = {"3mo": 0, "1y": 0}

    class _TickerFalsoPorPeriodo:
        def history(self, period):
            chamadas_por_periodo[period] += 1
            return historico_3mo if period == "3mo" else historico_1y

    monkeypatch.setattr(precos.yf, "Ticker", lambda t: _TickerFalsoPorPeriodo())

    precos.obter_historico("PETR4", periodo="3mo", diretorio_cache=tmp_path)
    precos.obter_historico("PETR4", periodo="1y", diretorio_cache=tmp_path)
    # Refazer a busca de "3mo" precisa vir do cache do "3mo", não do "1y"
    # que foi buscado depois.
    precos.obter_historico("PETR4", periodo="3mo", diretorio_cache=tmp_path)

    assert chamadas_por_periodo == {"3mo": 1, "1y": 1}
    assert (tmp_path / "precos" / "PETR4.SA_3mo.csv").exists()
    assert (tmp_path / "precos" / "PETR4.SA_1y.csv").exists()


def test_obter_historico_forcar_atualizacao_ignora_cache_valido(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)
    precos.obter_historico(
        "PETR4", diretorio_cache=tmp_path, ttl_segundos=3600, forcar_atualizacao=True
    )

    assert ticker_falso.chamadas == 2


def test_obter_historico_levanta_ticker_invalido_quando_resultado_vazio(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=pd.DataFrame())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.TickerInvalido, match="TICKERINVALIDO.SA"):
        precos.obter_historico("TICKERINVALIDO", diretorio_cache=tmp_path)


def test_obter_historico_levanta_ticker_invalido_quando_yfinance_sinaliza(tmp_path, monkeypatch):
    excecao = yf.exceptions.YFTickerMissingError("PETR4.SA", "não encontrado")
    ticker_falso = _TickerFalso(excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.TickerInvalido):
        precos.obter_historico("PETR4", diretorio_cache=tmp_path)


def test_obter_historico_levanta_falha_fonte_preco_em_rate_limit(tmp_path, monkeypatch):
    excecao = yf.exceptions.YFRateLimitError()
    ticker_falso = _TickerFalso(excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.FalhaFontePreco) as info:
        precos.obter_historico("PETR4", diretorio_cache=tmp_path)
    assert info.value.__cause__ is excecao


def test_obter_historico_levanta_falha_fonte_preco_em_erro_generico(tmp_path, monkeypatch):
    excecao = ConnectionError("biblioteca não-oficial quebrou")
    ticker_falso = _TickerFalso(excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.FalhaFontePreco):
        precos.obter_historico("PETR4", diretorio_cache=tmp_path)


def test_obter_historico_ibovespa_usa_ticker_caret_bvsp_sem_sufixo(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    tickers_pedidos = []

    def construtor_falso(ticker_pedido):
        tickers_pedidos.append(ticker_pedido)
        return ticker_falso

    monkeypatch.setattr(precos.yf, "Ticker", construtor_falso)

    df = precos.obter_historico_ibovespa(diretorio_cache=tmp_path)

    assert tickers_pedidos == ["^BVSP"]
    assert len(df) == 2
    assert (tmp_path / "precos" / "^BVSP_3mo.csv").exists()


def test_obter_historico_aplica_delay_antes_de_requisicao_real_mas_nao_em_cache(
    tmp_path, monkeypatch
):
    ticker_falso = _TickerFalso(resultado=_historico_falso())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    esperas = []
    monkeypatch.setattr(precos.time, "sleep", lambda segundos: esperas.append(segundos))

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]

    precos.obter_historico("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]  # segunda chamada veio do cache, não dormiu de novo


def test_obter_dividendos_caminho_feliz_grava_cache(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(dividendos_resultado=_dividendos_falsos())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    df = precos.obter_dividendos("PETR4", diretorio_cache=tmp_path)

    assert list(df.columns) == ["data", "dividendo"]
    assert len(df) == 2
    assert (tmp_path / "precos" / "PETR4.SA_dividendos.csv").exists()


def test_obter_dividendos_empresa_sem_historico_devolve_vazio_sem_erro(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(dividendos_resultado=pd.Series([], dtype=float, name="Dividends"))
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    df = precos.obter_dividendos("CASH3", diretorio_cache=tmp_path)

    assert df.empty
    assert list(df.columns) == ["data", "dividendo"]


def test_obter_dividendos_usa_cache_dentro_do_ttl(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(dividendos_resultado=_dividendos_falsos())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)
    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)

    assert ticker_falso.chamadas_dividendos == 1


def test_obter_dividendos_forcar_atualizacao_ignora_cache_valido(tmp_path, monkeypatch):
    ticker_falso = _TickerFalso(dividendos_resultado=_dividendos_falsos())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)
    precos.obter_dividendos(
        "PETR4", diretorio_cache=tmp_path, ttl_segundos=3600, forcar_atualizacao=True
    )

    assert ticker_falso.chamadas_dividendos == 2


def test_obter_dividendos_aplica_delay_antes_de_requisicao_real_mas_nao_em_cache(
    tmp_path, monkeypatch
):
    ticker_falso = _TickerFalso(dividendos_resultado=_dividendos_falsos())
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    esperas = []
    monkeypatch.setattr(precos.time, "sleep", lambda segundos: esperas.append(segundos))

    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]

    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]  # segunda chamada veio do cache, não dormiu de novo


def test_obter_dividendos_levanta_ticker_invalido_quando_yfinance_sinaliza(tmp_path, monkeypatch):
    excecao = yf.exceptions.YFTickerMissingError("TICKERINVALIDO.SA", "não encontrado")
    ticker_falso = _TickerFalso(dividendos_excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.TickerInvalido):
        precos.obter_dividendos("TICKERINVALIDO", diretorio_cache=tmp_path)


def test_obter_dividendos_levanta_ticker_invalido_na_falha_observada_do_yfinance(
    tmp_path, monkeypatch
):
    # Comportamento real observado: yfinance levanta AttributeError (não um
    # erro documentado) ao buscar .dividends de um ticker inexistente.
    excecao = AttributeError("'NoneType' object has no attribute 'empty'")
    ticker_falso = _TickerFalso(dividendos_excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.TickerInvalido):
        precos.obter_dividendos("TICKERINVALIDO", diretorio_cache=tmp_path)


def test_obter_dividendos_levanta_ticker_invalido_quando_dividends_e_none(tmp_path, monkeypatch):
    # Terceira variação do mesmo comportamento não documentado: às vezes
    # `.dividends` não levanta nada e só devolve None — pego rodando o
    # app manualmente contra um ticker inválido (não coberto até então).
    ticker_falso = _TickerFalso(dividendos_resultado=None)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.TickerInvalido):
        precos.obter_dividendos("TICKERINVALIDO", diretorio_cache=tmp_path)


def test_obter_dividendos_sobrevive_a_offsets_mistos_de_horario_de_verao(tmp_path, monkeypatch):
    # Histórico real (PETR4) vai até 2005 e atravessa mudanças de horário
    # de verão no Brasil — a mesma coluna acaba com offsets -03:00 e -02:00
    # misturados. Regressão: reler o cache não pode virar dtype "string".
    indice = pd.DatetimeIndex(
        ["2006-01-02 10:00:00", "2006-11-01 10:00:00"], name="Date"
    ).tz_localize("America/Sao_Paulo")
    dividendos_mistos = pd.Series([0.259, 0.50075], index=indice, name="Dividends")
    ticker_falso = _TickerFalso(dividendos_resultado=dividendos_mistos)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    precos.obter_dividendos("PETR4", diretorio_cache=tmp_path)
    df_do_cache = precos.obter_dividendos("PETR4", diretorio_cache=tmp_path, ttl_segundos=3600)

    assert pd.api.types.is_datetime64_any_dtype(df_do_cache["data"])
    assert len(df_do_cache) == 2


def test_obter_dividendos_levanta_falha_fonte_preco_em_erro_generico(tmp_path, monkeypatch):
    excecao = ConnectionError("biblioteca não-oficial quebrou")
    ticker_falso = _TickerFalso(dividendos_excecao=excecao)
    monkeypatch.setattr(precos.yf, "Ticker", lambda t: ticker_falso)

    with pytest.raises(precos.FalhaFontePreco):
        precos.obter_dividendos("PETR4", diretorio_cache=tmp_path)
