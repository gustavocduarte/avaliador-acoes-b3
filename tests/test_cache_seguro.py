"""Leitura segura (arquivo corrompido vira cache ausente) e gravação atômica dos
caches em disco. Nenhum teste acessa a rede nem grava fora de `tmp_path`."""

import os

import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import (
    _cache,
    b3_universo,
    balanco_cvm,
    bcb_sgs,
    crosswalk_cnpj,
    cvm,
    fundamentus,
    gpr,
    precos,
)

CNPJ = "00.000.000/0001-91"
CNPJ_NORMALIZADO = "00000000000191"


class Rebuscou(Exception):
    """Sinal de que o adapter tratou o cache como ausente e foi buscar de novo."""


def _rebusca(*args, **kwargs):
    raise Rebuscou


def _deve_rebuscar(chamar):
    """A chamada falha só porque o adapter foi buscar de novo (alguns adapters
    embrulham a exceção da fonte numa própria)."""
    with pytest.raises(Exception) as info:
        chamar()
    erro = info.value
    while erro is not None and not isinstance(erro, Rebuscou):
        erro = erro.__cause__ or erro.__context__
    assert erro is not None, f"não rebuscou: {info.value!r}"


JSON_TRUNCADO = '{"versao_schema": 1, "indicadores": {"lpa": 1.'
JSON_FORA_DO_FORMATO = "[1, 2, 3]"
CSV_ULTIMA_LINHA_CORTADA = "data,Close\n2026-01-02,10.5\n2026-01-03,1"
CSV_VAZIO = ""
CSV_BINARIO = "\x00\x00\x00\n"
CSV_SEM_AS_COLUNAS = "x,y\n1,2\n"

CONTEUDOS_JSON = [JSON_TRUNCADO, JSON_FORA_DO_FORMATO, "", "\x00\x01"]
CONTEUDOS_CSV = [CSV_ULTIMA_LINHA_CORTADA, CSV_VAZIO, CSV_BINARIO, CSV_SEM_AS_COLUNAS]


# --- helpers ---


def test_gravar_texto_atomico_cria_pastas_e_nao_deixa_temporario(tmp_path):
    caminho = tmp_path / "a" / "b" / "cache.json"

    _cache.gravar_texto_atomico(caminho, "conteudo")

    assert caminho.read_text(encoding="utf-8") == "conteudo"
    assert list(caminho.parent.iterdir()) == [caminho]


def test_falha_na_troca_preserva_o_arquivo_anterior_e_remove_o_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / "cache.csv"
    caminho.write_text("antigo\n", encoding="utf-8")

    def troca_falha(origem, destino):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", troca_falha)

    with pytest.raises(OSError):
        _cache.gravar_texto_atomico(caminho, "novo\n")

    assert caminho.read_text(encoding="utf-8") == "antigo\n"
    assert list(tmp_path.iterdir()) == [caminho]


def test_falha_ao_serializar_nao_toca_no_arquivo_anterior(tmp_path):
    caminho = tmp_path / "cache.json"
    caminho.write_text('{"ok": true}', encoding="utf-8")

    with pytest.raises(TypeError):
        _cache.gravar_json_atomico(caminho, {"x": object()})

    assert caminho.read_text(encoding="utf-8") == '{"ok": true}'
    assert list(tmp_path.iterdir()) == [caminho]


def test_gravar_csv_atomico_termina_com_quebra_de_linha(tmp_path):
    caminho = tmp_path / "cache.csv"

    _cache.gravar_csv_atomico(pd.DataFrame({"a": [1, 2]}), caminho)

    assert caminho.read_bytes().endswith(b"\n")
    assert list(pd.read_csv(caminho)["a"]) == [1, 2]


@pytest.mark.parametrize("conteudo", CONTEUDOS_JSON)
def test_ler_json_cache_devolve_none_para_arquivo_invalido(tmp_path, conteudo):
    caminho = tmp_path / "cache.json"
    caminho.write_text(conteudo, encoding="utf-8")

    assert _cache.ler_json_cache(caminho) is None


def test_ler_json_cache_devolve_o_objeto_valido(tmp_path):
    caminho = tmp_path / "cache.json"
    caminho.write_text('{"a": 1}', encoding="utf-8")

    assert _cache.ler_json_cache(caminho) == {"a": 1}


@pytest.mark.parametrize("conteudo", CONTEUDOS_CSV)
def test_ler_csv_cache_devolve_none_para_arquivo_invalido(tmp_path, conteudo):
    caminho = tmp_path / "cache.csv"
    caminho.write_text(conteudo, encoding="utf-8")

    assert _cache.ler_csv_cache(caminho, ("data", "Close")) is None


def test_ler_csv_cache_recusa_ultima_linha_cortada_mesmo_com_colunas_corretas(tmp_path):
    caminho = tmp_path / "cache.csv"
    caminho.write_text("data,Close\n2026-01-02,10.5\n2026-01-03,1", encoding="utf-8")

    assert _cache.ler_csv_cache(caminho, ("data", "Close")) is None


def test_ler_csv_cache_devolve_none_se_falta_coluna_esperada(tmp_path):
    caminho = tmp_path / "cache.csv"
    caminho.write_text("data\n2026-01-02\n", encoding="utf-8")

    assert _cache.ler_csv_cache(caminho, ("data", "Close")) is None


def test_ler_csv_cache_aceita_arquivo_so_com_cabecalho(tmp_path):
    caminho = tmp_path / "cache.csv"
    caminho.write_text("data,dividendo\n", encoding="utf-8")

    df = _cache.ler_csv_cache(caminho, ("data", "dividendo"))

    assert df is not None and df.empty


def test_ler_csv_cache_repassa_as_opcoes_de_leitura(tmp_path):
    caminho = tmp_path / "cache.csv"
    caminho.write_text("data,Close\n2026-01-02,10.5\n", encoding="utf-8")

    df = _cache.ler_csv_cache(caminho, ("data",), parse_dates=["data"])

    assert df is not None and str(df["data"].dtype).startswith("datetime64")


# --- adapters de JSON: cache corrompido vira busca nova ---


def _fundamentus(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentus, "get_com_retry", _rebusca)
    return fundamentus._caminho_cache("ABEV3", tmp_path), lambda: fundamentus.obter_indicadores(
        "ABEV3", diretorio_cache=tmp_path, delay_segundos=0
    )


def _fcf(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", _rebusca)
    return (
        tmp_path / "cvm" / f"fcf_{CNPJ_NORMALIZADO}_2025.json",
        lambda: cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path),
    )


def _lucro(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", _rebusca)
    return cvm._caminho_cache_resultado(
        CNPJ_NORMALIZADO, 2025, tmp_path
    ), lambda: cvm.obter_lucro_liquido(CNPJ, 2025, diretorio_cache=tmp_path)


def _balanco(tmp_path, monkeypatch):
    monkeypatch.setattr(balanco_cvm, "_baixar_zip_ano", _rebusca)
    return balanco_cvm._caminho_cache(
        CNPJ_NORMALIZADO, "2026-06-30", tmp_path
    ), lambda: balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)


@pytest.mark.parametrize("montar", [_fundamentus, _fcf, _lucro, _balanco])
@pytest.mark.parametrize("conteudo", CONTEUDOS_JSON)
def test_cache_json_corrompido_e_tratado_como_ausente(tmp_path, monkeypatch, montar, conteudo):
    caminho, chamar = montar(tmp_path, monkeypatch)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")

    _deve_rebuscar(chamar)


def test_macro_guardado_corrompido_e_tratado_como_ausente(tmp_path):
    caminho = bcb_sgs._caminho_ultimo_macro(tmp_path)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    for conteudo in (*CONTEUDOS_JSON, '{"selic_meta": 0.1'):
        caminho.write_text(conteudo, encoding="utf-8")

        assert bcb_sgs._carregar_ultimo_macro(tmp_path) is None


def test_macro_gravado_e_relido_sem_temporario(tmp_path):
    bcb_sgs._salvar_ultimo_macro(
        tmp_path, 0.1, 0.04, pd.Timestamp("2026-08-01"), pd.Timestamp("2026-10-03").to_pydatetime()
    )

    macro = bcb_sgs._carregar_ultimo_macro(tmp_path)

    assert macro is not None and macro["selic_meta"] == pytest.approx(0.1)
    assert [p.name for p in tmp_path.rglob("*.tmp")] == []


# --- adapters de CSV ---


def _historico(tmp_path, monkeypatch):
    monkeypatch.setattr(precos.yf, "Ticker", _rebusca)
    return precos._caminho_cache("PETR4.SA", "3mo", tmp_path, True), lambda: precos.obter_historico(
        "PETR4", periodo="3mo", diretorio_cache=tmp_path, delay_segundos=0
    )


def _dividendos(tmp_path, monkeypatch):
    monkeypatch.setattr(precos.yf, "Ticker", _rebusca)
    return precos._caminho_cache_dividendos("PETR4.SA", tmp_path), lambda: precos.obter_dividendos(
        "PETR4", diretorio_cache=tmp_path, delay_segundos=0
    )


def _gpr(tmp_path, monkeypatch):
    monkeypatch.setattr(gpr.requests, "get", _rebusca)
    return gpr._caminho_cache("mensal", tmp_path), lambda: gpr.obter_gpr(
        "mensal", diretorio_cache=tmp_path
    )


def _universo(tmp_path, monkeypatch):
    monkeypatch.setattr(b3_universo, "buscar_registros_paginados", _rebusca)
    return b3_universo._caminho_cache(tmp_path), lambda: b3_universo.obter_universo_ibovespa(
        diretorio_cache=tmp_path
    )


def _catalogo(tmp_path, monkeypatch):
    monkeypatch.setattr(crosswalk_cnpj, "buscar_registros_paginados", _rebusca)
    return crosswalk_cnpj._caminho_cache_catalogo(
        tmp_path
    ), lambda: crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)


def _crosswalk(tmp_path, monkeypatch):
    monkeypatch.setattr(crosswalk_cnpj, "buscar_registros_paginados", _rebusca)
    monkeypatch.setattr(b3_universo, "buscar_registros_paginados", _rebusca)
    return crosswalk_cnpj._caminho_cache_crosswalk(
        tmp_path
    ), lambda: crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)


def _serie_bcb(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_get_com_retry", _rebusca)
    return bcb_sgs._caminho_cache(
        432, "01/01/2026", "01/10/2026", tmp_path
    ), lambda: bcb_sgs.obter_serie(432, "01/01/2026", "01/10/2026", diretorio_cache=tmp_path)


ADAPTERS_CSV = [_historico, _dividendos, _gpr, _universo, _catalogo, _crosswalk, _serie_bcb]


@pytest.mark.parametrize("montar", ADAPTERS_CSV)
@pytest.mark.parametrize("conteudo", CONTEUDOS_CSV)
def test_cache_csv_corrompido_e_tratado_como_ausente(tmp_path, monkeypatch, montar, conteudo):
    caminho, chamar = montar(tmp_path, monkeypatch)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")

    _deve_rebuscar(chamar)


@pytest.mark.parametrize("montar", [_gpr, _universo, _catalogo])
def test_cache_corrompido_com_a_fonte_fora_do_ar_levanta_o_erro_de_rede(
    tmp_path, monkeypatch, montar
):
    caminho, chamar = montar(tmp_path, monkeypatch)
    erro_de_rede = requests.ConnectionError("fora do ar")

    def falha(*args, **kwargs):
        raise erro_de_rede

    monkeypatch.setattr(gpr.requests, "get", falha)
    monkeypatch.setattr(b3_universo, "buscar_registros_paginados", falha)
    monkeypatch.setattr(crosswalk_cnpj, "buscar_registros_paginados", falha)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(CSV_ULTIMA_LINHA_CORTADA, encoding="utf-8")

    with pytest.raises(requests.ConnectionError):
        chamar()


def test_cache_de_dividendos_so_com_cabecalho_continua_valido(tmp_path, monkeypatch):
    caminho, chamar = _dividendos(tmp_path, monkeypatch)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("data,dividendo\n", encoding="utf-8")

    assert chamar().empty


def test_historico_gravado_e_relido_do_cache_sem_rebuscar(tmp_path, monkeypatch):
    caminho, chamar = _historico(tmp_path, monkeypatch)
    df = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-01-02", "2026-01-03"], utc=True),
            "Close": [10.0, 11.0],
        }
    )
    _cache.gravar_csv_atomico(df, caminho)

    assert list(chamar()["Close"]) == [10.0, 11.0]
