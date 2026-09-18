import base64
import json

import pytest
import requests

from avaliador_b3.ingest import _paginacao


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


def test_parametros_base64_decodifica_de_volta_pro_dict_original():
    parametros = {"language": "pt-br", "pageNumber": 2, "pageSize": 50}
    codificado = _paginacao.parametros_base64(parametros)
    assert json.loads(base64.b64decode(codificado)) == parametros


def test_baixar_pagina_levanta_erro_claro_quando_json_invalido(monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(json_invalido=True)
    )
    with pytest.raises(ValueError, match="teste.*não é JSON válido"):
        _paginacao._baixar_pagina("https://example.com", contexto="teste")


def test_buscar_registros_paginados_uma_pagina_sem_delay(monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 10, "totalRecords": 2, "totalPages": 1},
        "results": [{"id": 1}, {"id": 2}],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(dados)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    registros = _paginacao.buscar_registros_paginados(
        montar_url=lambda pagina: f"https://example.com?pagina={pagina}",
        contexto="teste",
    )

    assert registros == [{"id": 1}, {"id": 2}]
    assert chamadas["contador"] == 1


def test_buscar_registros_paginados_multiplas_paginas_acumula_registros(monkeypatch):
    pagina1 = {
        "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [{"id": 1}],
    }
    pagina2 = {
        "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [{"id": 2}],
    }
    urls_chamadas = []

    def get_falso(url, timeout):
        urls_chamadas.append(url)
        return _RespostaFalsa(pagina1 if len(urls_chamadas) == 1 else pagina2)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    registros = _paginacao.buscar_registros_paginados(
        montar_url=lambda pagina: f"https://example.com?pagina={pagina}",
        contexto="teste",
    )

    assert registros == [{"id": 1}, {"id": 2}]
    assert urls_chamadas == ["https://example.com?pagina=1", "https://example.com?pagina=2"]


def test_buscar_registros_paginados_aplica_delay_entre_paginas_mas_nao_antes_da_primeira(
    monkeypatch,
):
    # Regressão: b3_universo.py/crosswalk_cnpj.py não tinham NENHUM delay
    # entre páginas antes dessa mudança, apesar de crosswalk_cnpj.py
    # paginar até ~36 vezes contra a API da B3 (ver
    # TAMANHO_PAGINA_API_B3_CATALOGO em config.py). Confirma que o delay é
    # aplicado só ENTRE páginas, não antes da primeira requisição da
    # sequência.
    paginas = {
        1: {
            "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 3, "totalPages": 3},
            "results": [{"id": 1}],
        },
        2: {
            "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 3, "totalPages": 3},
            "results": [{"id": 2}],
        },
        3: {
            "page": {"pageNumber": 3, "pageSize": 1, "totalRecords": 3, "totalPages": 3},
            "results": [{"id": 3}],
        },
    }
    contador = {"pagina_atual": 0}

    def get_falso(url, timeout):
        contador["pagina_atual"] += 1
        return _RespostaFalsa(paginas[contador["pagina_atual"]])

    esperas = []
    monkeypatch.setattr(_paginacao.requests, "get", get_falso)
    monkeypatch.setattr(_paginacao.time, "sleep", lambda segundos: esperas.append(segundos))

    _paginacao.buscar_registros_paginados(
        montar_url=lambda pagina: f"https://example.com?pagina={pagina}",
        contexto="teste",
        delay_segundos=2.5,
    )

    # 3 páginas -> 2 esperas (entre 1-2 e entre 2-3), nunca antes da 1ª.
    assert esperas == [2.5, 2.5]


def test_buscar_registros_paginados_levanta_erro_quando_formato_do_topo_muda(monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa({"algo": "diferente"})
    )

    with pytest.raises(ValueError, match="Formato da resposta de teste mudou"):
        _paginacao.buscar_registros_paginados(
            montar_url=lambda pagina: "https://example.com",
            contexto="teste",
        )


def test_buscar_registros_paginados_propaga_http_error(monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests,
        "get",
        lambda url, timeout: _RespostaFalsa(status_ok=False),
    )

    with pytest.raises(requests.HTTPError):
        _paginacao.buscar_registros_paginados(
            montar_url=lambda pagina: "https://example.com",
            contexto="teste",
        )
