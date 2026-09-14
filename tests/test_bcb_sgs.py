import pandas as pd
import pytest

from avaliador_b3.ingest import bcb_sgs


def test_montar_url_sem_datas():
    url = bcb_sgs._montar_url(11, None, None)
    assert url == "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json"


def test_montar_url_com_datas():
    url = bcb_sgs._montar_url(432, "01/01/2024", "01/03/2024")
    assert "dataInicial=01/01/2024" in url
    assert "dataFinal=01/03/2024" in url


def test_parsear_resposta_valida():
    texto = '[{"data":"01/01/2024","valor":"11.75"}]'
    registros = bcb_sgs._parsear_resposta(texto, codigo=432)
    assert registros == [{"data": "01/01/2024", "valor": "11.75"}]


def test_parsear_resposta_invalida_levanta_erro_claro():
    texto_html = "<html><body>Requisição inválida!</body></html>"
    with pytest.raises(ValueError, match="série 999999999"):
        bcb_sgs._parsear_resposta(texto_html, codigo=999999999)


def test_registros_para_dataframe_tipos_e_ordenacao():
    registros = [
        {"data": "02/01/2024", "valor": "11.25"},
        {"data": "01/01/2024", "valor": "11.75"},
    ]
    df = bcb_sgs._registros_para_dataframe(registros)

    assert list(df["data"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert list(df["valor"]) == [11.75, 11.25]
    assert df["valor"].dtype == float


def test_registros_para_dataframe_vazio():
    df = bcb_sgs._registros_para_dataframe([])
    assert df.empty
    assert list(df.columns) == ["data", "valor"]


def test_obter_serie_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    class RespostaFalsa:
        text = '[{"data":"01/01/2024","valor":"11.75"}]'

        def raise_for_status(self):
            pass

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return RespostaFalsa()

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)

    df1 = bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)
    df2 = bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    pd.testing.assert_frame_equal(df1, df2)
    assert (tmp_path / "bcb" / "serie_432.csv").exists()


def test_obter_serie_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    class RespostaFalsa:
        text = '[{"data":"01/01/2024","valor":"11.75"}]'

        def raise_for_status(self):
            pass

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return RespostaFalsa()

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)

    bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)
    bcb_sgs.obter_serie(432, diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2
