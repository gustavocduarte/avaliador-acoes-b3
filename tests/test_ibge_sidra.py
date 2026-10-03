import json
from pathlib import Path

import pandas as pd
import pytest

from avaliador_b3.ingest import bcb_sgs, ibge_sidra

CAMINHO_FIXTURES = Path(__file__).parent / "fixtures"


def _sidra_texto() -> str:
    return (CAMINHO_FIXTURES / "ibge_sidra_ipca_mensal.json").read_text("utf-8")


def test_parsear_resposta_sidra_traz_um_mes_por_linha_em_ordem():
    df = ibge_sidra._parsear_resposta_sidra(_sidra_texto())

    assert list(df.columns) == ["data", "valor"]
    assert len(df) == 14
    assert df["data"].iloc[0] == pd.Timestamp("2025-07-01")
    assert df["valor"].iloc[0] == pytest.approx(0.26)
    assert df["data"].iloc[-1] == pd.Timestamp("2026-08-01")
    assert df["valor"].iloc[-1] == pytest.approx(-0.32)
    assert df["data"].is_monotonic_increasing


def test_parsear_resposta_sidra_ignora_meses_sem_valor_numerico():
    linhas = json.loads(_sidra_texto())
    linhas[-1]["V"] = "..."  # o último mês ainda não publicado

    df = ibge_sidra._parsear_resposta_sidra(json.dumps(linhas))

    assert len(df) == 13
    assert df["data"].iloc[-1] == pd.Timestamp("2026-07-01")


@pytest.mark.parametrize(
    "texto",
    [
        "isso não é json",
        "[]",
        '[{"V": "Valor"}]',
        '{"erro": "x"}',
        json.dumps([{}, {"V": "-", "D3C": "202608"}]),
    ],
)
def test_parsear_resposta_sidra_sem_meses_levanta_erro_claro(texto):
    with pytest.raises(ValueError, match="SIDRA"):
        ibge_sidra._parsear_resposta_sidra(texto)


def test_obter_ipca_mensal_sidra_pede_os_ultimos_meses_na_tabela_1737_variavel_63(monkeypatch):
    pedidos = []

    class _Resposta:
        text = _sidra_texto()

    def get_falso(url, timeout, pausas, **kwargs):
        pedidos.append((url, timeout, pausas))
        return _Resposta()

    monkeypatch.setattr(ibge_sidra, "get_com_retry", get_falso)

    df = ibge_sidra.obter_ipca_mensal_sidra(14)

    assert len(df) == 14
    url, timeout, pausas = pedidos[0]
    assert url == "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/last%2014"
    assert timeout == 10
    assert pausas == (2,)


def test_acumulado_de_12_meses_da_sidra_bate_com_o_da_serie_433_do_bcb():
    sidra = ibge_sidra._parsear_resposta_sidra(_sidra_texto())
    soap_xml = (CAMINHO_FIXTURES / "bcb_soap_ipca_mensal.xml").read_text("utf-8")
    bcb = bcb_sgs._registros_para_dataframe(bcb_sgs._parsear_resposta_soap(soap_xml, 433))

    ipca_sidra, mes_sidra = bcb_sgs._ipca_12m_do_dataframe(sidra)
    ipca_bcb, mes_bcb = bcb_sgs._ipca_12m_do_dataframe(bcb)

    assert ipca_sidra == pytest.approx(ipca_bcb, abs=1e-12)
    assert ipca_sidra == pytest.approx(0.042234527370682784)
    assert mes_sidra == mes_bcb == pd.Timestamp("2026-08-01")
