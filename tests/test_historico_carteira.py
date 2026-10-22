import pandas as pd
import pytest

from avaliador_b3.historico_carteira import montar_historico, serie_cdi, serie_ipca


def _historico(precos: list[float], fim: str = "2026-10-22") -> pd.DataFrame:
    datas = pd.bdate_range(end=fim, periods=len(precos))
    return pd.DataFrame({"data": datas, "Close": precos})


def _historico_de_um_ano(inicio_preco: float, fim_preco: float, dias: int = 261) -> pd.DataFrame:
    precos = [inicio_preco + (fim_preco - inicio_preco) * i / (dias - 1) for i in range(dias)]
    return _historico(precos)


def test_cada_acao_comeca_no_valor_inicial_com_todo_o_dinheiro_nela():
    historicos = {"AAA3": _historico_de_um_ano(10.0, 20.0), "BBB4": _historico_de_um_ano(5.0, 2.5)}

    resultado = montar_historico(historicos, {"AAA3": 0.5, "BBB4": 0.5}, 1000.0, 1, 7)

    assert resultado.por_acao["AAA3"].iloc[0] == pytest.approx(1000.0)
    assert resultado.por_acao["BBB4"].iloc[0] == pytest.approx(1000.0)
    assert resultado.por_acao["AAA3"].iloc[-1] == pytest.approx(2000.0)  # dobrou
    assert resultado.por_acao["BBB4"].iloc[-1] == pytest.approx(500.0)  # caiu pela metade


def test_carteira_compra_as_proporcoes_de_hoje_no_inicio_sem_rebalancear():
    historicos = {"AAA3": _historico_de_um_ano(10.0, 20.0), "BBB4": _historico_de_um_ano(5.0, 2.5)}

    resultado = montar_historico(historicos, {"AAA3": 0.75, "BBB4": 0.25}, 1000.0, 1, 7)

    carteira = resultado.carteira
    assert carteira.iloc[0] == pytest.approx(1000.0)
    # 750 em AAA3 (dobra: 1.500) e 250 em BBB4 (metade: 125), sem rebalanceamento no caminho.
    assert carteira.iloc[-1] == pytest.approx(1500.0 + 125.0)
    assert resultado.na_carteira == ["AAA3", "BBB4"]
    assert resultado.fora_da_carteira == [] and resultado.sem_historico == []


def test_acao_com_historico_menor_tem_linha_propria_mas_fica_fora_da_carteira():
    historicos = {
        "LONGA3": _historico_de_um_ano(10.0, 20.0),
        "NOVA3": _historico(list(range(10, 70))),  # só 60 pregões
    }

    resultado = montar_historico(historicos, {"LONGA3": 0.6, "NOVA3": 0.4}, 1000.0, 1, 7)

    assert resultado.fora_da_carteira == ["NOVA3"]
    assert resultado.na_carteira == ["LONGA3"]
    nova = resultado.por_acao["NOVA3"]
    assert len(nova) == 60 and nova.iloc[0] == pytest.approx(
        1000.0
    )  # começa quando o histórico começa
    assert nova.index[0] > resultado.por_acao["LONGA3"].index[0]
    # Pesos refeitos entre as que ficaram: a carteira vira só a LONGA3, ainda partindo de 1.000.
    assert resultado.carteira.iloc[0] == pytest.approx(1000.0)
    assert resultado.carteira.iloc[-1] == pytest.approx(2000.0)


def test_sem_nenhuma_acao_com_historico_completo_nao_ha_carteira():
    resultado = montar_historico(
        {"NOVA3": _historico(list(range(10, 40)))}, {"NOVA3": 1.0}, 500.0, 1, 7
    )

    assert resultado.carteira is None
    assert resultado.fora_da_carteira == ["NOVA3"]
    assert "NOVA3" in resultado.por_acao


def test_acao_sem_preco_nenhum_fica_em_sem_historico():
    vazio = pd.DataFrame({"data": pd.to_datetime([]), "Close": []})

    resultado = montar_historico(
        {"AAA3": _historico_de_um_ano(10.0, 12.0), "ZZZ3": vazio}, {"AAA3": 1.0}, 100.0, 1, 7
    )

    assert resultado.sem_historico == ["ZZZ3"]
    assert "ZZZ3" not in resultado.por_acao


def test_periodo_de_dois_anos_corta_nos_dois_anos_anteriores_a_ultima_data():
    historicos = {"AAA3": _historico([10.0 + i * 0.01 for i in range(700)])}

    um = montar_historico(historicos, {"AAA3": 1.0}, 100.0, 1, 7)
    dois = montar_historico(historicos, {"AAA3": 1.0}, 100.0, 2, 7)

    assert len(dois.por_acao["AAA3"]) > len(um.por_acao["AAA3"])
    assert um.por_acao["AAA3"].index[0] >= pd.Timestamp("2025-10-22")
    assert dois.por_acao["AAA3"].index[0] >= pd.Timestamp("2024-10-22")


def _ipca(*taxas: tuple[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"data": pd.to_datetime([t[0] for t in taxas]), "valor": [t[1] for t in taxas]}
    )


def test_ipca_corrige_geometricamente_dentro_do_mes_e_acumula_entre_os_meses():
    ipca = _ipca(("2026-08-01", 1.0), ("2026-09-01", 2.0))
    datas = pd.DatetimeIndex(["2026-07-31", "2026-08-31", "2026-09-30"])

    serie = serie_ipca(ipca, datas, 1000.0)

    assert serie.iloc[0] == pytest.approx(1000.0)  # 31/07: antes da série, índice 1
    assert serie.iloc[1] == pytest.approx(1000.0 * 1.01)  # agosto inteiro
    assert serie.iloc[2] == pytest.approx(1000.0 * 1.01 * 1.02)  # mais setembro inteiro


def test_ipca_no_meio_do_mes_aplica_so_a_fracao_geometrica():
    ipca = _ipca(("2026-09-01", 2.0))
    datas = pd.DatetimeIndex(["2026-08-31", "2026-09-15"])

    serie = serie_ipca(ipca, datas, 100.0)

    assert serie.iloc[1] == pytest.approx(100.0 * 1.02 ** (15 / 30))


def test_ipca_depois_do_ultimo_mes_publicado_fica_parado():
    ipca = _ipca(("2026-08-01", 1.0))
    datas = pd.DatetimeIndex(["2026-08-31", "2026-10-15", "2026-10-22"])

    serie = serie_ipca(ipca, datas, 1000.0)

    assert serie.iloc[0] == pytest.approx(serie.iloc[1]) == pytest.approx(serie.iloc[2])


def test_ipca_e_cdi_sem_dado_ou_sem_datas_devolvem_none():
    vazio = pd.DataFrame({"data": pd.to_datetime([]), "valor": []})
    datas = pd.DatetimeIndex(["2026-10-01"])

    assert serie_ipca(vazio, datas, 100.0) is None
    assert serie_cdi(vazio, datas, 100.0) is None
    assert serie_ipca(_ipca(("2026-09-01", 1.0)), pd.DatetimeIndex([]), 100.0) is None
    assert (
        serie_cdi(
            pd.DataFrame({"data": pd.to_datetime(["2026-10-01"]), "valor": [0.05]}),
            pd.DatetimeIndex([]),
            1.0,
        )
        is None
    )


def test_cdi_acumula_a_taxa_diaria_e_parte_do_valor_inicial():
    cdi = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]),
            "valor": [0.05, 0.05, 0.05, 0.05],
        }
    )
    datas = pd.DatetimeIndex(["2026-10-01", "2026-10-02", "2026-10-06"])

    serie = serie_cdi(cdi, datas, 1000.0)

    assert serie.iloc[0] == pytest.approx(1000.0)
    assert serie.iloc[1] == pytest.approx(1000.0 * 1.0005)
    assert serie.iloc[2] == pytest.approx(1000.0 * 1.0005**3)  # 02, 05 e 06 depois do dia 01


def test_cdi_realista_252_dias_uteis_a_0_0551_por_cento_ao_dia_dao_cerca_de_14_9_por_cento():
    datas = pd.bdate_range("2025-10-22", periods=253)
    cdi = pd.DataFrame({"data": datas, "valor": [0.0551] * len(datas)})

    serie = serie_cdi(cdi, datas, 1000.0)

    assert serie.iloc[0] == pytest.approx(1000.0)
    assert serie.iloc[-1] / serie.iloc[0] - 1 == pytest.approx(1.000551**252 - 1)  # 252 dias úteis
    assert serie.iloc[-1] / serie.iloc[0] - 1 == pytest.approx(0.149, abs=0.001)


def test_ipca_realista_12_meses_a_0_4_por_cento_ao_mes_dao_cerca_de_4_9_por_cento():
    meses = pd.date_range("2025-10-01", periods=13, freq="MS")
    ipca = pd.DataFrame({"data": meses, "valor": [0.4] * len(meses)})
    datas = pd.DatetimeIndex(["2025-10-31", "2026-10-31"])

    serie = serie_ipca(ipca, datas, 1000.0)

    # De 31/10/2025 a 31/10/2026: novembro a outubro, 12 meses de 0,4%.
    assert serie.iloc[-1] / serie.iloc[0] - 1 == pytest.approx(1.004**12 - 1)
    assert serie.iloc[-1] / serie.iloc[0] - 1 == pytest.approx(0.049, abs=0.001)


def test_datas_com_fuso_do_yahoo_nao_zeram_o_cdi_nem_o_ipca():
    datas = pd.bdate_range("2025-10-22", periods=253, tz="UTC")  # como vêm do yfinance
    cdi = pd.DataFrame({"data": pd.bdate_range("2025-10-22", periods=253), "valor": 0.0551})
    ipca = pd.DataFrame(
        {"data": pd.date_range("2025-10-01", periods=13, freq="MS"), "valor": [0.4] * 13}
    )

    serie_c = serie_cdi(cdi, datas, 1000.0)
    serie_i = serie_ipca(ipca, datas, 1000.0)

    assert serie_c.iloc[-1] > 1100.0 and serie_i.iloc[-1] > 1040.0  # não ficam retas em 1.000
    assert serie_c.index.equals(datas) and serie_i.index.equals(datas)  # mesmas datas de entrada


def test_cdi_depois_do_fim_da_serie_fica_parado_e_antes_do_comeco_devolve_none():
    cdi = pd.DataFrame(
        {"data": pd.to_datetime(["2020-01-02", "2020-01-03"]), "valor": [0.05, 0.05]}
    )

    depois = serie_cdi(cdi, pd.DatetimeIndex(["2026-10-01", "2026-10-02"]), 1000.0)
    antes = serie_cdi(cdi, pd.DatetimeIndex(["2019-01-02", "2019-01-03"]), 1000.0)

    assert depois.iloc[0] == pytest.approx(depois.iloc[-1])  # segue a última taxa acumulada
    assert antes is None  # sem taxa nenhuma nas datas: melhor sem a linha do que uma reta
