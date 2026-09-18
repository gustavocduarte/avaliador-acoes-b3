import pandas as pd
import pytest

from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin

DATA_REFERENCIA = pd.Timestamp("2026-06-15")


def _dividendos(datas_valores: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data": pd.to_datetime([d for d, _ in datas_valores]),
            "dividendo": [v for _, v in datas_valores],
        }
    )


def test_aplicavel_com_cinco_anos_consecutivos_de_dividendo():
    dividendos = _dividendos(
        [
            ("2021-12-01", 1.0),
            ("2022-12-01", 1.0),
            ("2023-12-01", 1.0),
            ("2024-12-01", 1.0),
            ("2025-12-01", 1.2),  # único pagamento dentro dos últimos 12 meses
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is True
    assert resultado["motivo_nao_aplicavel"] is None
    assert resultado["preco_teto"] == pytest.approx(1.2 / 0.06)


def test_nao_aplicavel_com_menos_de_cinco_anos_de_historico():
    dividendos = _dividendos(
        [
            ("2023-12-01", 1.0),
            ("2024-12-01", 1.0),
            ("2025-12-01", 1.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None
    assert "5 anos" in resultado["motivo_nao_aplicavel"]


def test_nao_aplicavel_com_lacuna_no_historico():
    # Falta 2024 — não é ininterrupto, mesmo cobrindo 5 anos calendário.
    dividendos = _dividendos(
        [
            ("2021-12-01", 1.0),
            ("2022-12-01", 1.0),
            ("2023-12-01", 1.0),
            ("2025-12-01", 1.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None


def test_nao_aplicavel_sem_nenhum_dividendo():
    dividendos = pd.DataFrame({"data": pd.to_datetime([]), "dividendo": pd.Series(dtype=float)})

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None
    assert "5 anos" in resultado["motivo_nao_aplicavel"]


def test_dataframe_vazio_sem_coluna_data_nao_quebra():
    # Guard defensivo, não regressão de um bug observado: o produtor real
    # (ingest.precos.obter_dividendos) sempre garante a coluna "data" mesmo
    # vazio, mas a função não deve quebrar com KeyError se um chamador
    # futuro violar esse contrato — deve cair no mesmo "não aplicável" de
    # qualquer outro histórico vazio, não estourar antes de chegar lá.
    dividendos = pd.DataFrame()

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None


def test_aplicavel_com_datas_com_timezone_igual_ao_yfinance():
    # ingest.precos.obter_dividendos devolve datas tz-aware (vêm do
    # yfinance) — regressão pro TypeError de comparar tz-aware com
    # tz-naive que apareceu na validação manual contra dado real.
    dividendos = pd.DataFrame(
        {
            "data": pd.to_datetime(
                [
                    "2021-12-01",
                    "2022-12-01",
                    "2023-12-01",
                    "2024-12-01",
                    "2025-12-01",
                ]
            ).tz_localize("America/Sao_Paulo"),
            "dividendo": [1.0, 1.0, 1.0, 1.0, 1.2],
        }
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is True
    assert resultado["preco_teto"] == pytest.approx(1.2 / 0.06)


def test_nao_aplicavel_quando_historico_bate_mas_nada_pago_nos_ultimos_12_meses():
    # 5 anos consecutivos cobertos (2021-2025), mas o pagamento mais recente
    # (2025-01-01) fica 2 semanas antes da janela de 12 meses terminando em
    # 2026-01-15 — histórico "relevante" pela regra dos 5 anos, mas sem
    # nenhum pagamento no período usado para calcular o preço teto em si.
    dividendos = _dividendos(
        [
            ("2021-08-01", 1.0),
            ("2022-08-01", 1.0),
            ("2023-08-01", 1.0),
            ("2024-08-01", 1.0),
            ("2025-01-01", 1.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=pd.Timestamp("2026-01-15"))

    assert resultado["aplicavel"] is False
    assert resultado["preco_teto"] is None
    assert "últimos 12 meses" in resultado["motivo_nao_aplicavel"]
