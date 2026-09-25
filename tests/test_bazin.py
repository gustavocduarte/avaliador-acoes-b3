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


def test_razao_dividendos_acima_do_corte():
    # 2021-2024: R$1,00/ano (mediana). 2025 (últimos 12 meses): R$3,00 —
    # razão = 3,00/1,00 = 3,0, acima do corte de 2,0 (config.RAZAO_
    # DIVIDENDOS_ATIPICA_BAZIN).
    dividendos = _dividendos(
        [
            ("2021-12-01", 1.0),
            ("2022-12-01", 1.0),
            ("2023-12-01", 1.0),
            ("2024-12-01", 1.0),
            ("2025-12-01", 3.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is True
    assert resultado["razao_dividendos_12m_vs_mediana_5a"] == pytest.approx(3.0)


def test_razao_dividendos_abaixo_do_corte():
    # Últimos 12 meses (R$1,20) próximo da mediana dos 5 anos anteriores
    # (R$1,00) — razão = 1,2, abaixo do corte de 2,0.
    dividendos = _dividendos(
        [
            ("2021-12-01", 1.0),
            ("2022-12-01", 1.0),
            ("2023-12-01", 1.0),
            ("2024-12-01", 1.0),
            ("2025-12-01", 1.2),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is True
    assert resultado["razao_dividendos_12m_vs_mediana_5a"] == pytest.approx(1.2)


def test_razao_dividendos_nula_quando_bazin_nao_aplicavel():
    dividendos = _dividendos(
        [
            ("2023-12-01", 1.0),
            ("2024-12-01", 1.0),
            ("2025-12-01", 1.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is False
    assert resultado["razao_dividendos_12m_vs_mediana_5a"] is None


def test_razao_dividendos_nula_quando_mediana_dos_5_anos_e_zero():
    # Um pagamento de R$0,00 em cada um dos 5 anos exigidos satisfaz a
    # regra de "histórico sem lacuna" (_anos_com_dividendo não olha o
    # valor, só a presença de um registro), mas deixa a mediana dos totais
    # anuais em zero — a razão não pode dividir por isso, mesmo com o
    # método aplicável (o único pagamento real, >0, cai fora dessa janela
    # de 5 anos, dentro dos últimos 12 meses).
    dividendos = _dividendos(
        [
            ("2021-07-01", 0.0),
            ("2022-07-01", 0.0),
            ("2023-07-01", 0.0),
            ("2024-07-01", 0.0),
            ("2025-07-01", 0.0),
            ("2026-01-01", 1.0),
        ]
    )

    resultado = calcular_preco_teto_bazin(dividendos, data_referencia=DATA_REFERENCIA)

    assert resultado["aplicavel"] is True
    assert resultado["razao_dividendos_12m_vs_mediana_5a"] is None


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
