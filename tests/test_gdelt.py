import io
import zipfile

import pandas as pd
import pytest
import requests

from avaliador_b3.config import COLUNAS_EVENTO_GDELT
from avaliador_b3.ingest import gdelt


def _linha_evento(**overrides: str) -> str:
    """Monta uma linha crua (tab-delimited) de evento do GDELT, com todas as
    61 colunas vazias por padrão, exceto as passadas em `overrides`."""
    campos = {nome: "" for nome in COLUNAS_EVENTO_GDELT}
    campos.update(overrides)
    return "\t".join(campos[nome] for nome in COLUNAS_EVENTO_GDELT)


def _zip_bytes(nome_membro: str, conteudo: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        arquivo_zip.writestr(nome_membro, conteudo)
    return buffer.getvalue()


class _RespostaFalsa:
    def __init__(self, texto: str = "", conteudo: bytes = b"", status_ok: bool = True):
        self.text = texto
        self.content = conteudo
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Client Error")


LASTUPDATE_VALIDO = (
    "61360 5773b97bad7b42fbe20621e5be39b5ef "
    "http://data.gdeltproject.org/gdeltv2/20260914073000.export.CSV.zip\n"
    "68827 5625594c795eb9b0003ead644a57568f "
    "http://data.gdeltproject.org/gdeltv2/20260914073000.mentions.CSV.zip\n"
    "3336942 73433c026e477ea2d46fc47d511225f3 "
    "http://data.gdeltproject.org/gdeltv2/20260914073000.gkg.csv.zip\n"
)


def test_url_evento_mais_recente_converte_para_https():
    url = gdelt._url_evento_mais_recente(LASTUPDATE_VALIDO)
    assert url == "https://data.gdeltproject.org/gdeltv2/20260914073000.export.CSV.zip"


def test_url_evento_mais_recente_levanta_erro_quando_formato_muda():
    with pytest.raises(ValueError, match="lastupdate.txt"):
        gdelt._url_evento_mais_recente("conteúdo completamente diferente\nsem urls aqui\n")


def test_timestamp_do_url():
    url = "https://data.gdeltproject.org/gdeltv2/20260914073000.export.CSV.zip"
    assert gdelt._timestamp_do_url(url) == "20260914073000"


def test_extrair_csv_do_zip_valido():
    zip_bytes = _zip_bytes("20260914073000.export.CSV", "conteudo\tfake")
    assert gdelt._extrair_csv_do_zip(zip_bytes) == "conteudo\tfake"


def test_extrair_csv_do_zip_invalido_levanta_erro_claro():
    with pytest.raises(ValueError, match="não é um zip válido"):
        gdelt._extrair_csv_do_zip(b"isso nao e um zip")


def test_analisar_arquivo_eventos_tipa_colunas_e_deriva_data_e_categoria():
    linha = _linha_evento(
        GLOBALEVENTID="1322918512",
        EventRootCode="19",
        EventCode="193",
        GoldsteinScale="-10.0",
        NumMentions="4",
        NumArticles="1",
        AvgTone="-4.78229835831549",
        ActionGeo_FullName="Uruapan, Michoacán de Ocampo, Mexico",
        ActionGeo_CountryCode="MX",
        ActionGeo_Lat="19.4167",
        ActionGeo_Long="-102.067",
        DATEADDED="20260914073000",
        SOURCEURL="https://example.com/noticia",
    )

    df = gdelt._analisar_arquivo_eventos(linha)

    assert df.loc[0, "GLOBALEVENTID"] == 1322918512
    assert df["GLOBALEVENTID"].dtype == "int64"
    assert df.loc[0, "GoldsteinScale"] == -10.0
    assert df.loc[0, "ActionGeo_Lat"] == 19.4167
    assert df.loc[0, "data"] == pd.Timestamp("2026-09-14 07:30:00")
    assert df.loc[0, "categoria_cameo"] == "FIGHT"


def test_analisar_arquivo_eventos_levanta_erro_quando_numero_de_colunas_muda():
    linha_quebrada = "1322918512\t20260914\t202609"  # só 3 campos, não 61
    with pytest.raises(ValueError, match="Formato do arquivo de eventos"):
        gdelt._analisar_arquivo_eventos(linha_quebrada)


def test_filtrar_eventos_conflito_mantem_so_categorias_de_conflito_e_ordena():
    linhas = "\n".join(
        [
            _linha_evento(
                GLOBALEVENTID="2",
                EventRootCode="05",  # não é conflito
                DATEADDED="20260914073000",
            ),
            _linha_evento(
                GLOBALEVENTID="3",
                EventRootCode="19",  # FIGHT
                GoldsteinScale="-10.0",
                DATEADDED="20260914071500",
            ),
            _linha_evento(
                GLOBALEVENTID="4",
                EventRootCode="18",  # ASSAULT
                GoldsteinScale="-9.0",
                DATEADDED="20260914073000",
            ),
        ]
    )

    df = gdelt._analisar_arquivo_eventos(linhas)
    resultado = gdelt.filtrar_eventos_conflito(df)

    assert list(resultado["GLOBALEVENTID"]) == [3, 4]
    assert list(resultado["categoria_cameo"]) == ["FIGHT", "ASSAULT"]
    assert list(resultado.columns) == gdelt.COLUNAS_RESULTADO


def test_obter_eventos_conflito_usa_cache_e_nao_baixa_zip_de_novo(tmp_path, monkeypatch):
    chamadas = {"lastupdate": 0, "zip": 0}
    linha = _linha_evento(
        GLOBALEVENTID="1",
        EventRootCode="19",
        GoldsteinScale="-10.0",
        DATEADDED="20260914073000",
    )
    zip_bytes = _zip_bytes("20260914073000.export.CSV", linha)

    def get_falso(url, timeout):
        if url == gdelt.URL_GDELT_LASTUPDATE:
            chamadas["lastupdate"] += 1
            return _RespostaFalsa(texto=LASTUPDATE_VALIDO)
        chamadas["zip"] += 1
        return _RespostaFalsa(conteudo=zip_bytes)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    df1 = gdelt.obter_eventos_conflito(diretorio_cache=tmp_path)
    df2 = gdelt.obter_eventos_conflito(diretorio_cache=tmp_path)

    assert chamadas["lastupdate"] == 2  # sempre consulta o índice, é leve
    assert chamadas["zip"] == 1  # mas só baixa o zip uma vez para o mesmo timestamp
    pd.testing.assert_frame_equal(df1, df2)
    assert (tmp_path / "gdelt" / "eventos_conflito_20260914073000.csv").exists()


def test_obter_eventos_conflito_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    chamadas = {"zip": 0}
    linha = _linha_evento(
        GLOBALEVENTID="1",
        EventRootCode="19",
        GoldsteinScale="-10.0",
        DATEADDED="20260914073000",
    )
    zip_bytes = _zip_bytes("20260914073000.export.CSV", linha)

    def get_falso(url, timeout):
        if url == gdelt.URL_GDELT_LASTUPDATE:
            return _RespostaFalsa(texto=LASTUPDATE_VALIDO)
        chamadas["zip"] += 1
        return _RespostaFalsa(conteudo=zip_bytes)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    gdelt.obter_eventos_conflito(diretorio_cache=tmp_path)
    gdelt.obter_eventos_conflito(diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["zip"] == 2


def test_obter_eventos_conflito_propaga_erro_quando_indice_fora_do_ar(tmp_path, monkeypatch):
    def get_falso(url, timeout):
        return _RespostaFalsa(status_ok=False)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    with pytest.raises(requests.HTTPError):
        gdelt.obter_eventos_conflito(diretorio_cache=tmp_path)


def test_obter_eventos_conflito_propaga_erro_quando_zip_fora_do_ar(tmp_path, monkeypatch):
    def get_falso(url, timeout):
        if url == gdelt.URL_GDELT_LASTUPDATE:
            return _RespostaFalsa(texto=LASTUPDATE_VALIDO)
        return _RespostaFalsa(status_ok=False)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    with pytest.raises(requests.HTTPError):
        gdelt.obter_eventos_conflito(diretorio_cache=tmp_path)
