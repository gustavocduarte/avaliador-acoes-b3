import io
import zipfile

import pandas as pd
import pytest
import requests

from avaliador_b3.config import COLUNAS_EVENTO_GDELT
from avaliador_b3.ingest import gdelt


@pytest.fixture(autouse=True)
def _sem_delay_gdelt(monkeypatch):
    """Por padrão os testes não esperam o DELAY_GDELT_SEGUNDOS real entre
    requisições — só um teste específico (abaixo) substitui esse patch
    localmente pra inspecionar o delay em si."""
    monkeypatch.setattr(gdelt.time, "sleep", lambda segundos: None)


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


def test_filtrar_eventos_conflito_exclui_codigos_coerce_ruido():
    # 172 (sanção administrativa) e 173 (prisão/ação legal) são os dois
    # códigos confirmados como majoritariamente ruído dentro de COERCE (ver
    # investigação em config.py) — devem sumir do resultado. 175 (repressão
    # violenta) é um código de COERCE fora da lista de ruído — permanece.
    linhas = "\n".join(
        [
            _linha_evento(
                GLOBALEVENTID="1",
                EventRootCode="17",
                EventCode="172",
                DATEADDED="20260914073000",
            ),
            _linha_evento(
                GLOBALEVENTID="2",
                EventRootCode="17",
                EventCode="173",
                DATEADDED="20260914073000",
            ),
            _linha_evento(
                GLOBALEVENTID="3",
                EventRootCode="17",
                EventCode="175",
                DATEADDED="20260914073000",
                SOURCEURL="https://example.com/repressao",
            ),
            _linha_evento(
                GLOBALEVENTID="4",
                EventRootCode="19",
                EventCode="193",
                DATEADDED="20260914073000",
                SOURCEURL="https://example.com/combate",
            ),
        ]
    )

    df = gdelt._analisar_arquivo_eventos(linhas)
    resultado = gdelt.filtrar_eventos_conflito(df)

    assert list(resultado["GLOBALEVENTID"]) == [3, 4]


def test_filtrar_eventos_conflito_deduplica_eventos_do_mesmo_artigo():
    # Mesma SOURCEURL, locais (e IDs de evento) diferentes — caso real
    # confirmado: uma notícia local sobre bares em Portland virou um evento
    # de "conflito" por cidade mencionada no texto. Só a primeira ocorrência
    # (cronologicamente) deve sobreviver.
    linhas = "\n".join(
        [
            _linha_evento(
                GLOBALEVENTID="10",
                EventRootCode="17",
                EventCode="171",
                DATEADDED="20260914073000",
                SOURCEURL="https://example.com/artigo-unico",
            ),
            _linha_evento(
                GLOBALEVENTID="11",
                EventRootCode="17",
                EventCode="171",
                DATEADDED="20260914074500",
                SOURCEURL="https://example.com/artigo-unico",
            ),
            _linha_evento(
                GLOBALEVENTID="12",
                EventRootCode="19",
                EventCode="193",
                DATEADDED="20260914073000",
                SOURCEURL="https://example.com/outro-artigo",
            ),
        ]
    )

    df = gdelt._analisar_arquivo_eventos(linhas)
    resultado = gdelt.filtrar_eventos_conflito(df)

    assert list(resultado["GLOBALEVENTID"]) == [10, 12]


def test_deduplicar_por_fonte_mantem_primeira_ocorrencia():
    df = pd.DataFrame(
        {
            "GLOBALEVENTID": [1, 2, 3],
            "SOURCEURL": ["https://a.com", "https://a.com", "https://b.com"],
        }
    )

    resultado = gdelt.deduplicar_por_fonte(df)

    assert list(resultado["GLOBALEVENTID"]) == [1, 3]


def test_deduplicar_por_fonte_nao_colapsa_urls_vazias_entre_si():
    # Duas linhas sem SOURCEURL não são "o mesmo artigo" só por estarem
    # ambas vazias — evita perder eventos legítimos sem URL registrada.
    df = pd.DataFrame(
        {
            "GLOBALEVENTID": [1, 2],
            "SOURCEURL": ["", ""],
        }
    )

    resultado = gdelt.deduplicar_por_fonte(df)

    assert list(resultado["GLOBALEVENTID"]) == [1, 2]


def test_deduplicar_por_fonte_sem_duplicatas_preserva_tudo():
    df = pd.DataFrame(
        {
            "GLOBALEVENTID": [1, 2, 3],
            "SOURCEURL": ["https://a.com", "https://b.com", "https://c.com"],
        }
    )

    resultado = gdelt.deduplicar_por_fonte(df)

    assert list(resultado["GLOBALEVENTID"]) == [1, 2, 3]


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


# --- gerar_timestamps_janela --------------------------------------------


def test_gerar_timestamps_janela_24h_tem_96_passos_de_15_min():
    timestamps = gdelt.gerar_timestamps_janela("20260915083000", horas=24)

    assert len(timestamps) == 96
    assert timestamps[0] == "20260915083000"  # mais recente primeiro
    assert timestamps[1] == "20260915081500"  # 15 min antes
    assert timestamps[-1] == "20260914084500"  # 96º passo: 95*15min = 23h45min antes


def test_gerar_timestamps_janela_janela_pequena():
    # 1h = 4 passos de 15 min, fácil de conferir à mão.
    timestamps = gdelt.gerar_timestamps_janela("20260915083000", horas=1)

    assert timestamps == [
        "20260915083000",
        "20260915081500",
        "20260915080000",
        "20260915074500",
    ]


def test_gerar_timestamps_janela_atravessa_virada_de_dia():
    timestamps = gdelt.gerar_timestamps_janela("20260915000000", horas=0.5)

    assert timestamps == ["20260915000000", "20260914234500"]


# --- obter_timestamp_mais_recente ---------------------------------------


def test_obter_timestamp_mais_recente(monkeypatch):
    monkeypatch.setattr(
        gdelt.requests, "get", lambda url, timeout: _RespostaFalsa(texto=LASTUPDATE_VALIDO)
    )
    assert gdelt.obter_timestamp_mais_recente() == "20260914073000"


# --- obter_eventos_conflito_do_snapshot ----------------------------------


def test_obter_eventos_conflito_do_snapshot_busca_url_do_timestamp_exato(tmp_path, monkeypatch):
    linha = _linha_evento(
        GLOBALEVENTID="1", EventRootCode="19", GoldsteinScale="-10.0", DATEADDED="20260913120000"
    )
    zip_bytes = _zip_bytes("20260913113000.export.CSV", linha)
    urls_chamadas = []

    def get_falso(url, timeout):
        urls_chamadas.append(url)
        return _RespostaFalsa(conteudo=zip_bytes)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    df = gdelt.obter_eventos_conflito_do_snapshot("20260913113000", diretorio_cache=tmp_path)

    assert urls_chamadas == [
        "https://data.gdeltproject.org/gdeltv2/20260913113000.export.CSV.zip"
    ]
    assert list(df["GLOBALEVENTID"]) == [1]


def test_obter_eventos_conflito_do_snapshot_usa_cache_e_nao_baixa_de_novo(tmp_path, monkeypatch):
    linha = _linha_evento(
        GLOBALEVENTID="1", EventRootCode="19", GoldsteinScale="-10.0", DATEADDED="20260913113000"
    )
    zip_bytes = _zip_bytes("20260913113000.export.CSV", linha)
    chamadas = {"zip": 0}

    def get_falso(url, timeout):
        chamadas["zip"] += 1
        return _RespostaFalsa(conteudo=zip_bytes)

    monkeypatch.setattr(gdelt.requests, "get", get_falso)

    gdelt.obter_eventos_conflito_do_snapshot("20260913113000", diretorio_cache=tmp_path)
    gdelt.obter_eventos_conflito_do_snapshot("20260913113000", diretorio_cache=tmp_path)

    assert chamadas["zip"] == 1


def test_obter_eventos_conflito_do_snapshot_propaga_erro_de_horario_faltando(tmp_path, monkeypatch):
    # Gap raro do GDELT: um timestamp específico simplesmente não existe
    # (404) — a função propaga o erro; quem processa uma janela de vários
    # snapshots (conflitos.py) é quem decide pular esse horário.
    monkeypatch.setattr(
        gdelt.requests, "get", lambda url, timeout: _RespostaFalsa(status_ok=False)
    )

    with pytest.raises(requests.HTTPError):
        gdelt.obter_eventos_conflito_do_snapshot("20260913113000", diretorio_cache=tmp_path)


def test_obter_eventos_conflito_do_snapshot_aplica_delay_so_fora_do_cache(tmp_path, monkeypatch):
    linha = _linha_evento(
        GLOBALEVENTID="1", EventRootCode="19", GoldsteinScale="-10.0", DATEADDED="20260913113000"
    )
    zip_bytes = _zip_bytes("20260913113000.export.CSV", linha)
    monkeypatch.setattr(
        gdelt.requests, "get", lambda url, timeout: _RespostaFalsa(conteudo=zip_bytes)
    )

    chamadas_sleep = []
    monkeypatch.setattr(gdelt.time, "sleep", lambda segundos: chamadas_sleep.append(segundos))

    gdelt.obter_eventos_conflito_do_snapshot(
        "20260913113000", diretorio_cache=tmp_path, delay_segundos=0.5
    )
    gdelt.obter_eventos_conflito_do_snapshot(
        "20260913113000", diretorio_cache=tmp_path, delay_segundos=0.5
    )

    assert chamadas_sleep == [0.5]  # só na primeira vez (segunda é cache hit)
