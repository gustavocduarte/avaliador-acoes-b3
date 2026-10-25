import pandas as pd
import pytest

from avaliador_b3 import config
from avaliador_b3.app import dados
from avaliador_b3.ingest import crosswalk_cnpj

CONTEUDO = (
    "ticker,cnpj,segmento_setorial\n"
    "PETR4,33000167000101,Exploração. Refino e Distribuição\n"
    "VALE3,33592510000154,Minerais Metálicos\n"
    "SEMCNPJ3,,Bancos\n"
)


class CatalogoCompleto:
    """Dublê de `obter_catalogo_emissores`: conta as chamadas e devolve um catálogo mínimo."""

    def __init__(self):
        self.chamadas = 0

    def __call__(self, *args, **kwargs):
        self.chamadas += 1
        return pd.DataFrame(
            {
                "codigo_emissor": ["BBAS"],
                "codigo_cvm": ["001023"],
                "cnpj": ["00000000000191"],
                "nome_empresa": ["BANCO DO BRASIL"],
                "segmento_setorial": ["Bancos"],
            }
        )


@pytest.fixture
def api(monkeypatch):
    dubla = CatalogoCompleto()
    monkeypatch.setattr(crosswalk_cnpj, "obter_catalogo_emissores", dubla)
    return dubla


def _gravar(monkeypatch, tmp_path, conteudo=CONTEUDO):
    caminho = tmp_path / "enxuto.csv"
    caminho.write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(config, "CAMINHO_CATALOGO_EMISSORES", caminho)


def test_ticker_no_arquivo_nao_chama_a_api_do_catalogo(api, monkeypatch, tmp_path):
    _gravar(monkeypatch, tmp_path)

    assert dados._buscar_cnpj("PETR4") == ("33000167000101", None)
    assert dados._buscar_segmento_setorial("PETR4") == ("Exploração. Refino e Distribuição", None)
    assert api.chamadas == 0


def test_sem_o_arquivo_chama_a_api_do_catalogo(api, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CAMINHO_CATALOGO_EMISSORES", tmp_path / "nao_existe.csv")

    assert dados._buscar_cnpj("BBAS3") == ("00000000000191", None)
    assert api.chamadas == 1


def test_ticker_fora_do_arquivo_cai_na_api(api, monkeypatch, tmp_path):
    _gravar(monkeypatch, tmp_path)

    assert dados._buscar_segmento_setorial("BBAS3") == ("Bancos", None)
    assert api.chamadas == 1


def test_ticker_com_cnpj_vazio_no_arquivo_cai_na_api(api, monkeypatch, tmp_path):
    _gravar(monkeypatch, tmp_path)

    cnpj, erro = dados._buscar_cnpj("SEMCNPJ3")

    assert cnpj is None and "não encontrado" in erro
    assert api.chamadas == 1


@pytest.mark.parametrize(
    "conteudo",
    [
        "",
        "ticker,cnpj,segmento_setorial\n",
        "ticker,cnpj\nPETR4,33000167000101\n",
        "ticker,cnpj,segmento_setorial\nPETR4,33000167000101,Petróleo",  # sem a quebra final
    ],
)
def test_arquivo_invalido_cai_na_api_sem_erro(api, monkeypatch, tmp_path, conteudo):
    _gravar(monkeypatch, tmp_path, conteudo)

    assert dados._buscar_cnpj("BBAS3") == ("00000000000191", None)
    assert api.chamadas == 1


def test_ticker_sem_emissor_em_lugar_nenhum_vira_o_motivo_de_sempre(api, monkeypatch, tmp_path):
    _gravar(monkeypatch, tmp_path)

    cnpj, erro = dados._buscar_cnpj("XXXX3")

    assert cnpj is None
    assert "XXXX3" in erro and "catálogo de emissores da B3" in erro


def test_cnpj_do_arquivo_sem_o_zero_a_esquerda_volta_com_14_digitos(tmp_path):
    caminho = tmp_path / "enxuto.csv"
    caminho.write_text("ticker,cnpj,segmento_setorial\nABEV3,7526557000100,Bebidas\n")

    catalogo = crosswalk_cnpj.ler_catalogo_enxuto(caminho)

    assert crosswalk_cnpj.buscar_no_catalogo_enxuto("ABEV3", catalogo)["cnpj"] == ("07526557000100")


def test_o_spinner_da_api_avisa_do_tempo_do_catalogo_completo(api, monkeypatch, tmp_path):
    textos = []

    class Spinner:
        def __init__(self, texto):
            textos.append(texto)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(dados.st, "spinner", Spinner)
    monkeypatch.setattr(config, "CAMINHO_CATALOGO_EMISSORES", tmp_path / "nao_existe.csv")

    dados._buscar_cnpj("BBAS3")

    assert textos == [config.TEXTO_SPINNER_CATALOGO_COMPLETO]
    assert "cerca de 1 minuto" in textos[0]
