import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import _paginacao, crosswalk_cnpj


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


def _linha_catalogo(
    emissor="PETR",
    codigo_cvm="009512",
    cnpj="33000167000101",
    nome="PETROBRAS",
    segmento_setorial="Exploração. Refino e Distribuição",
):
    return {
        "codigo_emissor": emissor,
        "codigo_cvm": codigo_cvm,
        "cnpj": cnpj,
        "nome_empresa": nome,
        "segmento_setorial": segmento_setorial,
    }


def _catalogo_petr_vale() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _linha_catalogo(),
            _linha_catalogo(
                "VALE", "4170", "33592510000154", "VALE S.A.", "Minerais Metálicos"
            ),
        ]
    )


def _catalogo_so_petr() -> pd.DataFrame:
    return pd.DataFrame([_linha_catalogo()])


def _registro(issuing="PETR", code_cvm="9512", cnpj="33000167000101", nome="PETROBRAS"):
    return {
        "codeCVM": code_cvm,
        "issuingCompany": issuing,
        "companyName": nome,
        "tradingName": nome[:12],
        "cnpj": cnpj,
        "marketIndicator": "17",
        "typeBDR": "",
        "dateListing": "27/08/1968",
        "status": "A",
        "segment": "Exploração",
        "segmentEng": "Exploration",
        "type": "1",
        "market": "N2",
    }


@pytest.mark.parametrize(
    ("ticker", "esperado"),
    [
        ("PETR4", "PETR"),
        ("VALE3", "VALE"),
        ("TAEE11", "TAEE"),
        ("BPAC11", "BPAC"),
        ("B3SA3", "B3SA"),
    ],
)
def test_codigo_emissor(ticker, esperado):
    assert crosswalk_cnpj._codigo_emissor(ticker) == esperado


def test_registro_para_linha_caminho_feliz():
    linha = crosswalk_cnpj._registro_para_linha(_registro())
    assert linha == {
        "codigo_emissor": "PETR",
        "codigo_cvm": "009512",
        "cnpj": "33000167000101",
        "nome_empresa": "PETROBRAS",
        "segmento_setorial": "Exploração",
    }


def test_registro_para_linha_forca_codigo_cvm_pra_string_mesmo_vindo_como_numero():
    # Regressão: o JSON bruto da API devolve "codeCVM" como número — sem
    # forçar str() aqui, resolver_cnpj() devolvia um "codigo_cvm" com tipo
    # diferente (int) do que vem do cache lido em disco (que já usa
    # dtype=str explicitamente, ver obter_catalogo_emissores), uma
    # inconsistência de tipo latente entre execução fresca e com cache.
    linha = crosswalk_cnpj._registro_para_linha(_registro(code_cvm=9512))
    assert linha["codigo_cvm"] == "009512"
    assert isinstance(linha["codigo_cvm"], str)


def test_registro_para_linha_completa_codigo_cvm_com_zeros_a_esquerda():
    # Bug real encontrado em 2026-09-25 (ver config.py, TAMANHO_CODIGO_CVM):
    # str() sozinho (teste acima) corrige o TIPO mas não devolve o zero que
    # a API já tinha perdido ao mandar "codeCVM" como número JSON — um
    # código CVM sempre tem 6 dígitos, então precisa completar com zero.
    linha = crosswalk_cnpj._registro_para_linha(_registro(code_cvm=9512))
    assert linha["codigo_cvm"] == "009512"


def test_registro_para_linha_completa_cnpj_com_um_zero_a_esquerda_caso_ambev():
    # Achado real investigando o FCD do ABEV3 (2026-09-25): a API da B3
    # devolvia cnpj=7526557000100 (13 dígitos, número JSON) pro CNPJ real
    # da AMBEV S.A., 07.526.557/0001-00 (confirmado contra a CVM) — o zero
    # à esquerda já se perde na resposta da API, antes de qualquer
    # normalização nossa rodar.
    linha = crosswalk_cnpj._registro_para_linha(_registro(cnpj=7526557000100))
    assert linha["cnpj"] == "07526557000100"


def test_registro_para_linha_completa_cnpj_com_dois_zeros_a_esquerda_caso_energisa():
    # Mesmo bug, confirmando que pode faltar mais de um zero: CNPJ real da
    # Energisa S.A. é 00.864.214/0001-06 (dois zeros); a API da B3 devolvia
    # 864214000106 (12 dígitos).
    linha = crosswalk_cnpj._registro_para_linha(_registro(cnpj=864214000106))
    assert linha["cnpj"] == "00864214000106"


def test_registro_para_linha_levanta_erro_quando_campo_falta():
    with pytest.raises(ValueError, match="Formato do catálogo"):
        crosswalk_cnpj._registro_para_linha({"issuingCompany": "PETR"})


def test_obter_catalogo_emissores_uma_pagina(tmp_path, monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 100, "totalRecords": 2, "totalPages": 1},
        "results": [
            _registro(issuing="VALE", code_cvm="4170", cnpj="33592510000154", nome="VALE S.A."),
            _registro(),
        ],
    }
    monkeypatch.setattr(_paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(dados))

    df = crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)

    assert list(df["codigo_emissor"]) == ["PETR", "VALE"]  # ordenado por emissor
    assert (tmp_path / "b3" / "catalogo_emissores.csv").exists()


def test_obter_catalogo_emissores_pagina_quando_ha_mais_de_uma_pagina(tmp_path, monkeypatch):
    pagina1 = {
        "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(issuing="VALE", code_cvm="4170", cnpj="33592510000154")],
    }
    pagina2 = {
        "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro()],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(pagina1 if chamadas["contador"] == 1 else pagina2)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    # delay_segundos=0 explícito — sem isso, o padrão viria de
    # DELAY_PAGINACAO_B3_SEGUNDOS (1.5s) e o teste dormiria de verdade
    # entre as 2 páginas.
    df = crosswalk_cnpj.obter_catalogo_emissores(
        diretorio_cache=tmp_path, tamanho_pagina=1, delay_segundos=0
    )

    assert chamadas["contador"] == 2
    assert sorted(df["codigo_emissor"]) == ["PETR", "VALE"]


def test_obter_catalogo_emissores_aplica_delay_entre_paginas(tmp_path, monkeypatch):
    # crosswalk_cnpj.py é o call site que mais importa pro delay entre
    # páginas: pagina até ~36 vezes pro catálogo completo (ver
    # TAMANHO_PAGINA_API_B3_CATALOGO em config.py), diferente de
    # b3_universo.py (tudo cabe numa página hoje).
    pagina1 = {
        "page": {"pageNumber": 1, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro(issuing="VALE", code_cvm="4170", cnpj="33592510000154")],
    }
    pagina2 = {
        "page": {"pageNumber": 2, "pageSize": 1, "totalRecords": 2, "totalPages": 2},
        "results": [_registro()],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(pagina1 if chamadas["contador"] == 1 else pagina2)

    esperas = []
    monkeypatch.setattr(_paginacao.requests, "get", get_falso)
    monkeypatch.setattr(_paginacao.time, "sleep", lambda segundos: esperas.append(segundos))

    crosswalk_cnpj.obter_catalogo_emissores(
        diretorio_cache=tmp_path, tamanho_pagina=1, delay_segundos=2.0
    )

    assert esperas == [2.0]  # 2 páginas -> 1 espera, entre elas


def test_obter_catalogo_emissores_levanta_erro_quando_json_invalido(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(json_invalido=True)
    )
    with pytest.raises(ValueError, match="não é JSON válido"):
        crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)


def test_obter_catalogo_emissores_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    dados = {
        "page": {"pageNumber": 1, "pageSize": 100, "totalRecords": 1, "totalPages": 1},
        "results": [_registro()],
    }
    chamadas = {"contador": 0}

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return _RespostaFalsa(dados)

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)
    crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1


def test_obter_catalogo_emissores_corrige_cache_antigo_sem_zero_a_esquerda(tmp_path, monkeypatch):
    # O cache não tem TTL (comentário no docstring da função) — um arquivo
    # salvo em disco ANTES da correção de 2026-09-25 continuaria com
    # "cnpj"/"codigo_cvm" sem o(s) zero(s) perdido(s) pra sempre, sem essa
    # normalização também na leitura. Escreve o CSV já no formato "sujo"
    # (como um cache real gravado antes da correção) e confirma que a
    # leitura devolve os valores já corrigidos — SEM bater na rede de novo
    # (get_falso levantaria se fosse chamado), já que o objetivo é corrigir
    # o cache existente sem precisar re-baixar as ~36 páginas da API.
    caminho_cache = tmp_path / "b3" / "catalogo_emissores.csv"
    caminho_cache.parent.mkdir(parents=True)
    pd.DataFrame(
        [_linha_catalogo(codigo_cvm="23264", cnpj="7526557000100", nome="AMBEV S.A.")]
    ).to_csv(caminho_cache, index=False)

    def get_falso(url, timeout):
        raise AssertionError("não deveria bater na rede pra corrigir um cache já em disco")

    monkeypatch.setattr(_paginacao.requests, "get", get_falso)

    df = crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)

    assert df.iloc[0]["cnpj"] == "07526557000100"
    assert df.iloc[0]["codigo_cvm"] == "023264"


def test_obter_catalogo_emissores_propaga_erro_http(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _paginacao.requests, "get", lambda url, timeout: _RespostaFalsa(status_ok=False)
    )
    with pytest.raises(requests.HTTPError):
        crosswalk_cnpj.obter_catalogo_emissores(diretorio_cache=tmp_path)


def test_resolver_cnpj_caminho_feliz():
    catalogo = _catalogo_petr_vale()
    resolvido = crosswalk_cnpj.resolver_cnpj("PETR4", catalogo)
    assert resolvido == {
        "ticker": "PETR4",
        "codigo_emissor": "PETR",
        "cnpj": "33000167000101",
        "codigo_cvm": "009512",
        "nome_empresa": "PETROBRAS",
        "segmento_setorial": "Exploração. Refino e Distribuição",
    }


def test_resolver_cnpj_levanta_erro_quando_emissor_nao_existe():
    catalogo = pd.DataFrame(
        [_linha_catalogo("VALE", "4170", "33592510000154", "VALE S.A.")]
    )
    with pytest.raises(crosswalk_cnpj.EmissorNaoEncontrado, match="PETR4"):
        crosswalk_cnpj.resolver_cnpj("PETR4", catalogo)


def test_resolver_segmentos_setoriais_resolve_todos_quando_todos_existem():
    catalogo = _catalogo_petr_vale()

    resultado = crosswalk_cnpj.resolver_segmentos_setoriais(["PETR4", "VALE3"], catalogo)

    assert list(resultado["ticker"]) == ["PETR4", "VALE3"]
    assert list(resultado["segmento_setorial"]) == [
        "Exploração. Refino e Distribuição",
        "Minerais Metálicos",
    ]


def test_resolver_segmentos_setoriais_omite_tickers_nao_encontrados_sem_erro():
    catalogo = _catalogo_so_petr()

    resultado = crosswalk_cnpj.resolver_segmentos_setoriais(
        ["PETR4", "TICKERFANTASMA99"], catalogo
    )

    assert list(resultado["ticker"]) == ["PETR4"]


def test_resolver_segmentos_setoriais_lista_vazia_devolve_tabela_vazia():
    catalogo = _catalogo_petr_vale()

    resultado = crosswalk_cnpj.resolver_segmentos_setoriais([], catalogo)

    assert resultado.empty
    assert list(resultado.columns) == ["ticker", "segmento_setorial"]


def test_obter_crosswalk_ibovespa_caminho_feliz(tmp_path, monkeypatch):
    universo = pd.DataFrame({"ticker": ["PETR4", "VALE3"]})
    catalogo = _catalogo_petr_vale()
    monkeypatch.setattr(crosswalk_cnpj, "obter_universo_ibovespa", lambda **kw: universo)
    monkeypatch.setattr(crosswalk_cnpj, "obter_catalogo_emissores", lambda **kw: catalogo)

    df = crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)

    assert list(df["ticker"]) == ["PETR4", "VALE3"]
    assert list(df["cnpj"]) == ["33000167000101", "33592510000154"]
    assert (tmp_path / "b3" / "crosswalk_ibovespa.csv").exists()


def test_obter_crosswalk_ibovespa_propaga_erro_quando_ticker_nao_resolve(tmp_path, monkeypatch):
    universo = pd.DataFrame({"ticker": ["PETR4", "TICKERFANTASMA99"]})
    catalogo = _catalogo_so_petr()
    monkeypatch.setattr(crosswalk_cnpj, "obter_universo_ibovespa", lambda **kw: universo)
    monkeypatch.setattr(crosswalk_cnpj, "obter_catalogo_emissores", lambda **kw: catalogo)

    with pytest.raises(crosswalk_cnpj.EmissorNaoEncontrado):
        crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)


def test_obter_crosswalk_ibovespa_usa_cache_e_nao_chama_fontes_de_novo(tmp_path, monkeypatch):
    universo = pd.DataFrame({"ticker": ["PETR4"]})
    catalogo = _catalogo_so_petr()
    chamadas = {"contador": 0}

    def universo_falso(**kw):
        chamadas["contador"] += 1
        return universo

    monkeypatch.setattr(crosswalk_cnpj, "obter_universo_ibovespa", universo_falso)
    monkeypatch.setattr(crosswalk_cnpj, "obter_catalogo_emissores", lambda **kw: catalogo)

    crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)
    crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1


def test_obter_crosswalk_ibovespa_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    universo = pd.DataFrame({"ticker": ["PETR4"]})
    catalogo = _catalogo_so_petr()
    chamadas = {"contador": 0}

    def universo_falso(**kw):
        chamadas["contador"] += 1
        return universo

    monkeypatch.setattr(crosswalk_cnpj, "obter_universo_ibovespa", universo_falso)
    monkeypatch.setattr(crosswalk_cnpj, "obter_catalogo_emissores", lambda **kw: catalogo)

    crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path)
    crosswalk_cnpj.obter_crosswalk_ibovespa(diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2
