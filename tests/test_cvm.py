from pathlib import Path

import pytest
import requests

from avaliador_b3.ingest import cvm

DIRETORIO_FIXTURES = Path(__file__).parent / "fixtures"
ZIP_AMOSTRA = DIRETORIO_FIXTURES / "cvm_dfp_2024_amostra.zip"

CNPJ_PETROBRAS = "33.000.167/0001-01"
CNPJ_ITAU = "60.872.504/0001-23"
CNPJ_SINTETICO_SO_INDIVIDUAL = "00.000.000/0001-00"
CNPJ_SINTETICO_DFC_MI_IND = "00.000.000/0002-00"
CNPJ_SINTETICO_DFC_MD_CON = "00.000.000/0003-00"


class _RespostaStreamFalsa:
    def __init__(self, conteudo: bytes, status_ok: bool = True):
        self._conteudo = conteudo
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Client Error")

    def iter_content(self, chunk_size):
        for inicio in range(0, len(self._conteudo), chunk_size):
            yield self._conteudo[inicio : inicio + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _linha(cd_conta, ds_conta, valor="100.0000000000", ordem="ÚLTIMO", escala="MIL"):
    return {
        "CNPJ_CIA": CNPJ_PETROBRAS,
        "CD_CVM": "009512",
        "DENOM_CIA": "PETROLEO BRASILEIRO S.A. PETROBRAS",
        "ESCALA_MOEDA": escala,
        "ORDEM_EXERC": ordem,
        "DT_FIM_EXERC": "2024-12-31",
        "CD_CONTA": cd_conta,
        "DS_CONTA": ds_conta,
        "VL_CONTA": valor,
    }


def test_normalizar_cnpj():
    assert cvm._normalizar_cnpj("33.000.167/0001-01") == "33000167000101"
    assert cvm._normalizar_cnpj("33000167000101") == "33000167000101"


def test_linha_lucro_liquido_localiza_conta_correta_estilo_nao_financeira():
    linhas = [
        _linha("3.01", "Receita de Venda de Bens e/ou Serviços"),
        _linha("3.10", "Resultado Líquido de Operações Descontinuadas"),
        _linha("3.11", "Lucro/Prejuízo do Período", valor="36606000.0000000000"),
        _linha("3.99", "Lucro por Ação - (Reais / Ação)", valor="0.0000000000"),
    ]
    linha = cvm._linha_lucro_liquido(linhas)
    assert linha["CD_CONTA"] == "3.11"


def test_linha_lucro_liquido_localiza_conta_correta_estilo_banco():
    linhas = [
        _linha("3.01", "Receitas da Intermediação Financeira"),
        _linha("3.08", "Resultado Líquido de Operações Descontinuadas"),
        _linha("3.09", "Lucro/Prejuízo Consolidado do Período", valor="33877000.0000000000"),
        _linha("3.99", "Lucro por Ação - (R$ / Ação)", valor="0.0000000000"),
    ]
    linha = cvm._linha_lucro_liquido(linhas)
    assert linha["CD_CONTA"] == "3.09"


def test_linha_lucro_liquido_levanta_erro_sem_candidatas():
    linhas = [_linha("3.99", "Lucro por Ação - (Reais / Ação)")]
    with pytest.raises(cvm.ContaLucroNaoEncontrada, match="Nenhuma conta"):
        cvm._linha_lucro_liquido(linhas)


def test_linha_lucro_liquido_levanta_erro_quando_descricao_nao_bate():
    linhas = [_linha("3.05", "Resultado Antes do Resultado Financeiro e dos Tributos")]
    with pytest.raises(cvm.ContaLucroNaoEncontrada, match="descrição inesperada"):
        cvm._linha_lucro_liquido(linhas)


@pytest.mark.parametrize(
    ("valor", "escala", "esperado"),
    [
        ("36606000.0000000000", "MIL", 36606000000.0),
        ("150.0000000000", "UNIDADE", 150.0),
    ],
)
def test_valor_conta(valor, escala, esperado):
    linha = _linha("3.11", "Lucro/Prejuízo do Período", valor, escala=escala)
    assert cvm._valor_conta(linha) == esperado


def test_valor_conta_levanta_erro_para_escala_desconhecida():
    with pytest.raises(cvm.ContaLucroNaoEncontrada, match="Escala monetária"):
        cvm._valor_conta(_linha("3.11", "Lucro/Prejuízo do Período", escala="BILHOES"))


def test_linhas_da_empresa_contra_fixture_real_consolidado():
    cnpj_petrobras = cvm._normalizar_cnpj(CNPJ_PETROBRAS)
    linhas_petrobras = cvm._linhas_da_empresa(ZIP_AMOSTRA, 2024, "con", cnpj_petrobras)
    assert len(linhas_petrobras) > 0
    assert all(linha["CNPJ_CIA"] == CNPJ_PETROBRAS for linha in linhas_petrobras)

    cnpj_itau = cvm._normalizar_cnpj(CNPJ_ITAU)
    linhas_itau = cvm._linhas_da_empresa(ZIP_AMOSTRA, 2024, "con", cnpj_itau)
    assert len(linhas_itau) > 0


def test_linhas_da_empresa_cnpj_ausente_devolve_lista_vazia():
    linhas = cvm._linhas_da_empresa(ZIP_AMOSTRA, 2024, "con", "99999999999999")
    assert linhas == []


def test_linhas_da_empresa_membro_inexistente_levanta_erro_claro():
    with pytest.raises(cvm.ContaLucroNaoEncontrada, match="não existe no zip"):
        cvm._linhas_da_empresa(ZIP_AMOSTRA, 1999, "con", cvm._normalizar_cnpj(CNPJ_PETROBRAS))


def test_montar_resultado_contra_fixture_real_petrobras():
    linhas = cvm._linhas_da_empresa(ZIP_AMOSTRA, 2024, "con", cvm._normalizar_cnpj(CNPJ_PETROBRAS))
    resultado = cvm._montar_resultado(2024, "con", linhas)

    assert resultado["cnpj"] == CNPJ_PETROBRAS
    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["conta_lucro_liquido"] == "3.11"
    assert resultado["lucro_liquido_atual"] == 37009000000.0
    assert resultado["lucro_liquido_anterior"] == 125166000000.0
    assert resultado["crescimento_lucro_percentual"] == pytest.approx(-70.432, abs=0.001)


def test_obter_lucro_liquido_prefere_consolidado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_lucro_liquido(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["lucro_liquido_atual"] == 37009000000.0


def test_obter_lucro_liquido_cai_para_individual_quando_falta_consolidado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_lucro_liquido(
        CNPJ_SINTETICO_SO_INDIVIDUAL, 2024, diretorio_cache=tmp_path
    )

    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["lucro_liquido_atual"] == 150000.0
    assert resultado["lucro_liquido_anterior"] == 100000.0
    assert resultado["crescimento_lucro_percentual"] == pytest.approx(50.0)


def test_obter_lucro_liquido_levanta_cnpj_nao_encontrado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    with pytest.raises(cvm.CnpjNaoEncontrado):
        cvm.obter_lucro_liquido("11.111.111/1111-11", 2024, diretorio_cache=tmp_path)


def test_obter_lucro_liquido_usa_cache_e_nao_chama_baixar_zip_de_novo(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    def baixar_falso(*args, **kwargs):
        chamadas["contador"] += 1
        return ZIP_AMOSTRA

    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar_falso)

    cvm.obter_lucro_liquido(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)
    cvm.obter_lucro_liquido(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    assert (tmp_path / "cvm" / "lucro_33000167000101_2024.json").exists()


def test_obter_lucro_liquido_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    def baixar_falso(*args, **kwargs):
        chamadas["contador"] += 1
        return ZIP_AMOSTRA

    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar_falso)

    cvm.obter_lucro_liquido(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)
    cvm.obter_lucro_liquido(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2


def test_baixar_zip_ano_grava_arquivo_via_streaming(tmp_path, monkeypatch):
    conteudo = ZIP_AMOSTRA.read_bytes()
    monkeypatch.setattr(
        cvm.requests, "get", lambda url, timeout, stream: _RespostaStreamFalsa(conteudo)
    )

    caminho = cvm._baixar_zip_ano(2024, tmp_path, forcar_atualizacao=False)

    assert caminho.read_bytes() == conteudo
    assert caminho == tmp_path / "cvm" / "dfp_cia_aberta_2024.zip"


def test_baixar_zip_ano_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    conteudo = ZIP_AMOSTRA.read_bytes()
    chamadas = {"contador": 0}

    def get_falso(url, timeout, stream):
        chamadas["contador"] += 1
        return _RespostaStreamFalsa(conteudo)

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    cvm._baixar_zip_ano(2024, tmp_path, forcar_atualizacao=False)
    cvm._baixar_zip_ano(2024, tmp_path, forcar_atualizacao=False)

    assert chamadas["contador"] == 1


def test_baixar_zip_ano_propaga_erro_quando_fora_do_ar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cvm.requests,
        "get",
        lambda url, timeout, stream: _RespostaStreamFalsa(b"", status_ok=False),
    )

    with pytest.raises(requests.HTTPError):
        cvm._baixar_zip_ano(2024, tmp_path, forcar_atualizacao=False)


def test_linha_por_codigo_caminho_feliz():
    linhas = [
        {"CD_CONTA": "6.01", "VL_CONTA": "100", "ESCALA_MOEDA": "MIL"},
        {"CD_CONTA": "6.02", "VL_CONTA": "-20", "ESCALA_MOEDA": "MIL"},
    ]
    linha = cvm._linha_por_codigo(linhas, "6.02")
    assert linha["VL_CONTA"] == "-20"


def test_linha_por_codigo_levanta_erro_quando_nao_encontrada():
    with pytest.raises(cvm.ContaFluxoCaixaNaoEncontrada, match="6.01"):
        cvm._linha_por_codigo([], "6.01")


def test_fcf_do_periodo_soma_cfo_e_cfi():
    linhas = [
        {"CD_CONTA": "6.01", "VL_CONTA": "204037000.0000000000", "ESCALA_MOEDA": "MIL"},
        {"CD_CONTA": "6.02", "VL_CONTA": "-72363000.0000000000", "ESCALA_MOEDA": "MIL"},
    ]
    assert cvm._fcf_do_periodo(linhas) == pytest.approx(131674000000.0)


def test_linhas_da_empresa_dfc_contra_fixture_real_mi_con():
    cnpj_petrobras = cvm._normalizar_cnpj(CNPJ_PETROBRAS)
    linhas = cvm._linhas_da_empresa_dfc(ZIP_AMOSTRA, 2024, "MI", "con", cnpj_petrobras)
    assert len(linhas) > 0
    assert all(linha["CNPJ_CIA"] == CNPJ_PETROBRAS for linha in linhas)


def test_linhas_da_empresa_dfc_membro_inexistente_levanta_erro_claro():
    cnpj_petrobras = cvm._normalizar_cnpj(CNPJ_PETROBRAS)
    with pytest.raises(cvm.ContaFluxoCaixaNaoEncontrada, match="não existe no zip"):
        cvm._linhas_da_empresa_dfc(ZIP_AMOSTRA, 1999, "MI", "con", cnpj_petrobras)


def test_montar_resultado_fcf_contra_fixture_real_petrobras():
    cnpj_petrobras = cvm._normalizar_cnpj(CNPJ_PETROBRAS)
    linhas = cvm._linhas_da_empresa_dfc(ZIP_AMOSTRA, 2024, "MI", "con", cnpj_petrobras)
    resultado = cvm._montar_resultado_fcf(2024, "con", "MI", linhas)

    assert resultado["cnpj"] == CNPJ_PETROBRAS
    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["metodo_dfc"] == "MI"
    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)
    assert resultado["fcf_anterior"] == pytest.approx(176201000000.0)


def test_obter_fluxo_caixa_livre_prefere_mi_consolidado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["metodo_dfc"] == "MI"
    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)


def test_obter_fluxo_caixa_livre_itau_via_mi_consolidado(tmp_path, monkeypatch):
    # Confere que o mesmo par de contas (6.01/6.02) funciona pra um banco.
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_ITAU, 2024, diretorio_cache=tmp_path)

    assert resultado["fcf_atual"] == pytest.approx(14037000000.0)
    assert resultado["fcf_anterior"] == pytest.approx(46263000000.0)


def test_obter_fluxo_caixa_livre_cai_para_mi_individual(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(
        CNPJ_SINTETICO_DFC_MI_IND, 2024, diretorio_cache=tmp_path
    )

    assert resultado["metodo_dfc"] == "MI"
    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)  # 600 + (-150), em MIL


def test_obter_fluxo_caixa_livre_cai_para_md_quando_nao_esta_em_mi(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(
        CNPJ_SINTETICO_DFC_MD_CON, 2024, diretorio_cache=tmp_path
    )

    assert resultado["metodo_dfc"] == "MD"
    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)


def test_obter_fluxo_caixa_livre_levanta_cnpj_nao_encontrado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    with pytest.raises(cvm.CnpjNaoEncontrado):
        cvm.obter_fluxo_caixa_livre("11.111.111/1111-11", 2024, diretorio_cache=tmp_path)


def test_obter_fluxo_caixa_livre_usa_cache_e_nao_chama_baixar_zip_de_novo(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    def baixar_falso(*args, **kwargs):
        chamadas["contador"] += 1
        return ZIP_AMOSTRA

    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar_falso)

    cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)
    cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    assert (tmp_path / "cvm" / "fcf_33000167000101_2024.json").exists()
