import io

import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import gpr


def _bytes_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


class _RespostaFalsa:
    def __init__(self, content: bytes, status_ok: bool = True):
        self.content = content
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Client Error")


def test_limpar_dataframe_mensal_remove_metadados_e_normaliza_data():
    df_bruto = pd.DataFrame(
        {
            "month": ["2024-02-01", "2024-01-01"],
            "GPR": [120.5, 110.2],
            "GPRT": [130.0, 115.0],
            "var_name": ["month", "GPR"],
            "var_label": ["Date (year/month)", "Recent GPR"],
        }
    )

    df = gpr._limpar_dataframe(df_bruto, "mensal")

    assert list(df.columns) == ["data", "GPR", "GPRT"]
    assert list(df["data"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]
    assert list(df["GPR"]) == [110.2, 120.5]


def test_limpar_dataframe_diaria_remove_day_e_metadados():
    df_bruto = pd.DataFrame(
        {
            "DAY": [20240102, 20240101],
            "date": ["2024-01-02", "2024-01-01"],
            "GPRD": [95.0, 90.0],
            "var_name": ["DAY", "date"],
            "var_label": ["dia", "data"],
        }
    )

    df = gpr._limpar_dataframe(df_bruto, "diaria")

    assert list(df.columns) == ["data", "GPRD"]
    assert list(df["data"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]


def test_limpar_dataframe_levanta_erro_quando_coluna_esperada_falta():
    df_bruto = pd.DataFrame({"month": ["2024-01-01"], "OUTRA_COISA": [1.0]})

    with pytest.raises(ValueError, match="Formato do arquivo GPR"):
        gpr._limpar_dataframe(df_bruto, "mensal")


def test_obter_gpr_serie_desconhecida_nao_bate_na_rede(monkeypatch):
    def get_falso(*args, **kwargs):
        raise AssertionError("não deveria fazer requisição para série inválida")

    monkeypatch.setattr(gpr.requests, "get", get_falso)

    with pytest.raises(ValueError, match="Série GPR desconhecida"):
        gpr.obter_gpr(serie="semanal")


def test_obter_gpr_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    chamadas = {"contador": 0}
    conteudo = _bytes_excel(pd.DataFrame({"month": ["2024-01-01"], "GPR": [100.0]}))

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(conteudo)

    monkeypatch.setattr(gpr.requests, "get", get_falso)

    df1 = gpr.obter_gpr(diretorio_cache=tmp_path)
    df2 = gpr.obter_gpr(diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    pd.testing.assert_frame_equal(df1, df2)
    assert (tmp_path / "gpr" / "gpr_mensal.csv").exists()


def test_obter_gpr_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    chamadas = {"contador": 0}
    conteudo = _bytes_excel(pd.DataFrame({"month": ["2024-01-01"], "GPR": [100.0]}))

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(conteudo)

    monkeypatch.setattr(gpr.requests, "get", get_falso)

    gpr.obter_gpr(diretorio_cache=tmp_path)
    gpr.obter_gpr(diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2


def test_obter_gpr_propaga_erro_quando_link_fora_do_ar(tmp_path, monkeypatch):
    def get_falso(url, timeout):
        return _RespostaFalsa(b"", status_ok=False)

    monkeypatch.setattr(gpr.requests, "get", get_falso)

    with pytest.raises(requests.HTTPError):
        gpr.obter_gpr(diretorio_cache=tmp_path)


def test_obter_gpr_levanta_erro_claro_quando_conteudo_nao_e_excel(tmp_path, monkeypatch):
    def get_falso(url, timeout):
        return _RespostaFalsa(b"isso nao e um arquivo excel")

    monkeypatch.setattr(gpr.requests, "get", get_falso)

    with pytest.raises(ValueError, match="não é um Excel válido"):
        gpr.obter_gpr(diretorio_cache=tmp_path)
