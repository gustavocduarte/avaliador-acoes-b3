import base64
import json

import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import _paginacao, b3_universo


class _RespostaFalsa:
    def __init__(self, dados: dict | None = None, status_ok: bool = True, json_invalido=False):
        self._dados = dados
        self._status_ok = status_ok
        self._json_invalido = json_invalido

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Client Error")

    def json(self):
        if self._json_invalido:
            raise requests.exceptions.JSONDecodeError("msg", "doc", 0)
        return self._dados


def _registro(cod="PETR4", asset="PETROBRAS", tipo="PN      N2", part="1,000"):
    return {
        "segment": None,
        "cod": cod,
        "asset": asset,
        "type": tipo,
        "part": part,
        "partAcum": None,
    }


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        ("ON      NM", "Novo Mercado"),
        ("PN      N2", "Nível 2"),
        ("ON  EJ  N1", "Nível 1"),
        ("PNA     N1", "Nível 1"),
        ("ON  ERJ NM", "Novo Mercado"),
        ("ON", "Tradicional"),
        ("UNT", "Tradicional"),
        ("", "Tradicional"),
    ],
)
def test_segmento_listagem(tipo, esperado):
    assert b3_universo._segmento_listagem(tipo) == esperado


def test_montar_url_codifica_parametros_em_base64():
    url = b3_universo._montar_url(pagina=2, tamanho_pagina=50)
    prefixo = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
    assert url.startswith(prefixo)

    parametros_base64 = url.removeprefix(prefixo)
    parametros = json.loads(base64.b64decode(parametros_base64))
    assert parametros == {
        "language": "pt-br",
        "pageNumber": 2,
        "pageSize": 50,
        "index": "IBOV",
        "segment": "1",
    }


def test_registro_para_linha_converte_peso_e_deriva_segmento():
    linha = b3_universo._registro_para_linha(_registro())
    assert linha == {
        "ticker": "PETR4",
        "nome": "PETROBRAS",
        "segmento_listagem": "Nível 2",
        "tipo_bruto": "PN      N2",
        "peso_percentual": 1.0,
    }


def test_registro_para_linha_levanta_erro_quando_campo_falta():
    registro_quebrado = {"cod": "PETR4", "asset": "PETROBRAS"}
    with pytest.raises(ValueError, match="Formato da carteira teórica"):
        b3_universo._registro_para_linha(registro_quebrado)


# Busca de fato (requests.get) acontece dentro de ingest._paginacao agora —
# ver tests/test_paginacao.py pro comportamento genérico de paginação
# (erro de JSON inválido, delay entre páginas, etc.). Os testes abaixo
# monkeypatcham `_paginacao.requests`, não `b3_universo.requests`.


def test_obter_universo_ibovespa_caminho_feliz_uma_pagina(tmp_path, monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 120, "totalRecords": 2, "totalPages": 1},
        "results": [
            _registro(cod="VALE3", asset="VALE", tipo="ON      NM", part="10,000"),
            _registro(cod="PETR4", asset="PETROBRAS", tipo="PN      N2", part="5,000"),
        ],
    }
    monkeypatch.setattr(_paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(dados))

    df = b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)

    assert list(df["ticker"]) == ["PETR4", "VALE3"]  # ordenado por ticker
    assert list(df.columns) == [
        "ticker",
        "nome",
        "segmento_listagem",
        "tipo_bruto",
        "peso_percentual",
    ]
    assert (tmp_path / "b3" / "universo_ibovespa.csv").exists()


def test_obter_universo_ibovespa_pagina_quando_ha_mais_de_uma_pagina(tmp_path, monkeypatch):
    pagina1 = {
        "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(cod="VALE3", asset="VALE", tipo="ON      NM", part="10,000")],
    }
    pagina2 = {
        "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(cod="PETR4", asset="PETROBRAS", tipo="PN      N2", part="5,000")],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(pagina1 if chamadas["contador"] == 1 else pagina2)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    # delay_segundos=0 explícito — sem isso, o padrão viria de
    # DELAY_PAGINACAO_B3_SEGUNDOS (1.5s) e o teste dormiria de verdade
    # entre as 2 páginas.
    df = b3_universo.obter_universo_ibovespa(
        diretorio_cache=tmp_path, tamanho_pagina=1, delay_segundos=0
    )

    assert chamadas["contador"] == 2
    assert sorted(df["ticker"]) == ["PETR4", "VALE3"]


def test_obter_universo_ibovespa_aplica_delay_entre_paginas(tmp_path, monkeypatch):
    pagina1 = {
        "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(cod="VALE3")],
    }
    pagina2 = {
        "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(cod="PETR4")],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(pagina1 if chamadas["contador"] == 1 else pagina2)

    esperas = []
    monkeypatch.setattr(_paginacao.requests, "get", get_falso)
    monkeypatch.setattr(_paginacao.time, "sleep", lambda segundos: esperas.append(segundos))

    b3_universo.obter_universo_ibovespa(
        diretorio_cache=tmp_path, tamanho_pagina=1, delay_segundos=3.0
    )

    assert esperas == [3.0]  # 2 páginas -> 1 espera, entre elas


def test_obter_universo_ibovespa_levanta_erro_quando_formato_do_topo_muda(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa({"algo": "diferente"})
    )
    with pytest.raises(ValueError, match="Formato da resposta"):
        b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)


def test_obter_universo_ibovespa_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 120, "totalRecords": 1, "totalPages": 1},
        "results": [_registro()],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(dados)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    df1 = b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)
    df2 = b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    pd.testing.assert_frame_equal(df1, df2)


def test_obter_universo_ibovespa_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 120, "totalRecords": 1, "totalPages": 1},
        "results": [_registro()],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(dados)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)
    b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2


def test_obter_universo_ibovespa_propaga_erro_quando_api_fora_do_ar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(status_ok=False)
    )
    with pytest.raises(requests.HTTPError):
        b3_universo.obter_universo_ibovespa(diretorio_cache=tmp_path)
