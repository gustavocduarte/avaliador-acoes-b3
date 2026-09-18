import pandas as pd
import pytest

from avaliador_b3.empresa import comportamento


def _historico(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    datas = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "data": datas,
            "Close": closes,
            "Volume": volumes if volumes is not None else [0] * len(closes),
        }
    )


def test_calcular_volume_medio():
    historico = _historico([10.0, 11.0, 12.0], volumes=[100, 200, 300])
    assert comportamento.calcular_volume_medio(historico) == pytest.approx(200.0)


def test_calcular_volume_medio_none_para_historico_vazio():
    # Regressão: Series.mean() sobre uma Series vazia devolve NaN sem
    # levantar erro — sem o guard, essa função devolvia NaN em vez de
    # None, diferente do padrão das duas funções vizinhas neste módulo.
    assert comportamento.calcular_volume_medio(_historico([])) is None


def test_calcular_volatilidade_anualizada_bate_com_calculo_independente():
    closes = [100.0, 102.0, 99.0, 103.0, 101.0]
    historico = _historico(closes)

    volatilidade = comportamento.calcular_volatilidade_anualizada(historico)

    retornos = pd.Series(closes).pct_change().dropna()
    esperado = retornos.std() * (252**0.5)
    assert volatilidade == pytest.approx(esperado)


def test_calcular_volatilidade_anualizada_none_sem_retorno_suficiente():
    assert comportamento.calcular_volatilidade_anualizada(_historico([100.0])) is None
    assert comportamento.calcular_volatilidade_anualizada(_historico([])) is None


def test_calcular_beta_com_relacao_linear_conhecida():
    ibov_closes = [100, 101, 99, 102, 105, 103]
    ibov = _historico(ibov_closes)

    fator_beta = 2.0
    retornos_ibov = pd.Series(ibov_closes, dtype=float).pct_change().dropna()
    acao_closes = [100.0]
    for retorno in retornos_ibov:
        acao_closes.append(acao_closes[-1] * (1 + fator_beta * retorno))
    acao = _historico(acao_closes)

    beta = comportamento.calcular_beta(acao, ibov)

    assert beta == pytest.approx(fator_beta, abs=1e-9)


def test_calcular_beta_none_quando_ibovespa_sem_variancia():
    ibov = _historico([100.0, 100.0, 100.0, 100.0])
    acao = _historico([50.0, 51.0, 49.0, 52.0])

    assert comportamento.calcular_beta(acao, ibov) is None


def test_calcular_beta_none_quando_poucas_datas_em_comum():
    ibov = _historico([100.0, 101.0])
    acao = _historico([50.0])  # só uma data em comum com o ibov -> 0 retornos pareados

    assert comportamento.calcular_beta(acao, ibov) is None


def test_calcular_beta_alinha_por_data_ignorando_dias_sem_sobreposicao():
    # Ibovespa tem um quinto dia (com um pulo grande de preço) que a ação
    # não tem — precisa alinhar pelas datas em comum e ignorar esse dia
    # por completo, não incluir um retorno desencontrado nem quebrar.
    datas_ibov = pd.date_range("2024-01-01", periods=5, freq="D")
    ibov_closes = [100.0, 101.0, 99.0, 102.0, 200.0]
    ibov = pd.DataFrame({"data": datas_ibov, "Close": ibov_closes})

    fator_beta = 0.5
    retornos_ibov = pd.Series(ibov_closes).pct_change().dropna()
    acao_closes = [50.0]
    for retorno in retornos_ibov:
        acao_closes.append(acao_closes[-1] * (1 + fator_beta * retorno))
    # Fica só com os 4 primeiros dias — o quinto dia do Ibovespa (pulo de
    # 102 pra 200) não tem par na ação.
    acao = pd.DataFrame({"data": datas_ibov[:4], "Close": acao_closes[:4]})

    beta = comportamento.calcular_beta(acao, ibov)

    assert beta is not None
    assert beta == pytest.approx(fator_beta, abs=1e-9)
