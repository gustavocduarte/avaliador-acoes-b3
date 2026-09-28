import pandas as pd
import pytest

from avaliador_b3.config import DATA_RAW_DIR
from avaliador_b3.ingest import bcb_sgs


def test_busca_bem_sucedida_nao_toca_o_data_raw_real(monkeypatch):
    # Mock de rede que "dá certo" com dado fabricado, chamando
    # obter_selic_e_ipca SEM diretorio_cache explícito — se a fixture
    # autouse de tests/conftest.py não redirecionar o default da função,
    # isso grava Selic/IPCA fabricados no data/raw/ real do projeto.
    caminho_real = DATA_RAW_DIR / "bcb" / "ultimo_macro.json"
    assert not caminho_real.exists()

    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-09-01")], "valor": [10.5]})
    ipca_df = pd.DataFrame(
        {"data": pd.date_range("2025-01-01", periods=12, freq="MS"), "valor": [0.3] * 12}
    )

    def obter_serie_falso(codigo, **kwargs):
        return selic_df if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"] else ipca_df

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)

    resultado = bcb_sgs.obter_selic_e_ipca()

    assert resultado.selic_meta == pytest.approx(0.105)
    assert not caminho_real.exists()
