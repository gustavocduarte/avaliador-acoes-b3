import json
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests

from avaliador_b3.config import MOTIVO_RECEITA_SEM_CONTA, MOTIVO_RECEITA_SEM_DRE
from avaliador_b3.ingest import cvm

DIRETORIO_FIXTURES = Path(__file__).parent / "fixtures"
ZIP_AMOSTRA = DIRETORIO_FIXTURES / "cvm_dfp_2024_amostra.zip"

CNPJ_PETROBRAS = "33.000.167/0001-01"
CNPJ_ITAU = "60.872.504/0001-23"
CNPJ_SINTETICO_SO_INDIVIDUAL = "00.000.000/0001-00"
CNPJ_SINTETICO_DFC_MI_IND = "00.000.000/0002-00"
CNPJ_SINTETICO_DFC_MD_CON = "00.000.000/0003-00"

# Campos de capex e juros pagos do resultado do FCF, nos mocks do fallback.
EXTRAS_FCF_MOCK = {
    "capex_atual": {"status": "nao_identificado", "valor": None, "linhas": []},
    "juros_pagos_atual": {"valor": 0.0, "linhas": []},
}


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


def test_normalizar_cnpj_completa_zero_a_esquerda_perdido():
    # Camada defensiva (ver config.py/crosswalk_cnpj.py): o
    # crosswalk da B3 já corrige o zero perdido antes de chamar o adapter
    # da CVM, mas _normalizar_cnpj completa de novo aqui — protege contra
    # qualquer outra fonte futura de CNPJ com o mesmo defeito (número JSON
    # sem zero à esquerda) que chame obter_fluxo_caixa_livre*/
    # obter_lucro_liquido direto, sem passar pelo crosswalk.
    assert cvm._normalizar_cnpj("7526557000100") == "07526557000100"  # AMBEV, 1 zero
    assert cvm._normalizar_cnpj("864214000106") == "00864214000106"  # Energisa, 2 zeros


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


def test_valor_conta_aceita_classe_de_erro_explicita():
    # Regressão: _valor_conta é compartilhada entre o caminho de Lucro
    # Líquido e o de Fluxo de Caixa (_cfo_cfi_do_periodo) — sem aceitar
    # classe_erro, uma escala desconhecida numa conta CFO/CFI levantaria
    # ContaLucroNaoEncontrada (mensagem enganosa, citando "Lucro Líquido"
    # num contexto de Fluxo de Caixa).
    with pytest.raises(cvm.ContaFluxoCaixaNaoEncontrada, match="Escala monetária"):
        cvm._valor_conta(
            _linha("6.01", "Caixa Líquido Atividades Operacionais", escala="BILHOES"),
            cvm.ContaFluxoCaixaNaoEncontrada,
        )


def test_fcf_do_periodo_escala_desconhecida_levanta_erro_de_fluxo_de_caixa_nao_erro_de_lucro():
    linhas = [
        _linha("6.01", "Caixa Líquido Atividades Operacionais", escala="BILHOES"),
        _linha("6.02", "Caixa Líquido Atividades de Investimento", valor="-20"),
    ]
    with pytest.raises(cvm.ContaFluxoCaixaNaoEncontrada, match="Escala monetária"):
        cvm._cfo_cfi_do_periodo(linhas)


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


def test_baixar_zip_ano_do_itr_usa_a_url_e_o_caminho_do_itr(tmp_path, monkeypatch):
    conteudo = ZIP_AMOSTRA.read_bytes()
    urls = []

    def get_falso(url, timeout, stream):
        urls.append(url)
        return _RespostaStreamFalsa(conteudo)

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    caminho = cvm._baixar_zip_ano(2026, tmp_path, forcar_atualizacao=False, documento="itr")

    assert urls == [
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2026.zip"
    ]
    assert caminho == tmp_path / "cvm" / "itr_cia_aberta_2026.zip"
    assert caminho.read_bytes() == conteudo


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


# --- Prazo de validade do cache do zip pro ano em preenchimento — ver
# docs/correcao-ano-fcd-2026-09-23.md e o comentário
# de DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE em config.py.


def _gravar_zip_com_idade(caminho: Path, conteudo: bytes, idade: timedelta, hoje: datetime) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    mtime = (hoje - idade).timestamp()
    os.utime(caminho, (mtime, mtime))


def test_baixar_zip_ano_em_preenchimento_expira_depois_do_prazo_e_baixa_de_novo(
    tmp_path, monkeypatch
):
    hoje = datetime(2027, 1, 1)
    caminho = tmp_path / "cvm" / "dfp_cia_aberta_2026.zip"
    _gravar_zip_com_idade(caminho, b"conteudo antigo", timedelta(days=10), hoje)

    conteudo_novo = ZIP_AMOSTRA.read_bytes()
    chamadas = {"contador": 0}

    def get_falso(url, timeout, stream):
        chamadas["contador"] += 1
        return _RespostaStreamFalsa(conteudo_novo)

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    resultado = cvm._baixar_zip_ano(2026, tmp_path, forcar_atualizacao=False, hoje=hoje)

    assert chamadas["contador"] == 1
    assert resultado.read_bytes() == conteudo_novo


def test_baixar_zip_ano_em_preenchimento_dentro_do_prazo_usa_cache(tmp_path, monkeypatch):
    hoje = datetime(2027, 1, 1)
    caminho = tmp_path / "cvm" / "dfp_cia_aberta_2026.zip"
    _gravar_zip_com_idade(caminho, b"conteudo em cache", timedelta(days=2), hoje)

    def get_falso(*args, **kwargs):
        raise AssertionError("não deveria bater na rede — cache ainda dentro do prazo")

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    resultado = cvm._baixar_zip_ano(2026, tmp_path, forcar_atualizacao=False, hoje=hoje)

    assert resultado.read_bytes() == b"conteudo em cache"


def test_baixar_zip_ano_fechado_nunca_expira_independente_da_idade(tmp_path, monkeypatch):
    hoje = datetime(2027, 1, 1)
    caminho = tmp_path / "cvm" / "dfp_cia_aberta_2020.zip"
    _gravar_zip_com_idade(caminho, b"conteudo antigo de ano fechado", timedelta(days=1000), hoje)

    def get_falso(*args, **kwargs):
        raise AssertionError("ano fechado não deveria bater na rede, não importa a idade")

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    resultado = cvm._baixar_zip_ano(2020, tmp_path, forcar_atualizacao=False, hoje=hoje)

    assert resultado.read_bytes() == b"conteudo antigo de ano fechado"


def test_baixar_zip_ano_prazo_vencido_download_falha_usa_cache_existente_com_aviso(
    tmp_path, monkeypatch
):
    hoje = datetime(2027, 1, 1)
    caminho = tmp_path / "cvm" / "dfp_cia_aberta_2026.zip"
    _gravar_zip_com_idade(caminho, b"conteudo em cache, desatualizado", timedelta(days=10), hoje)

    monkeypatch.setattr(
        cvm.requests,
        "get",
        lambda url, timeout, stream: _RespostaStreamFalsa(b"", status_ok=False),
    )

    with pytest.warns(UserWarning, match="cache"):
        resultado = cvm._baixar_zip_ano(2026, tmp_path, forcar_atualizacao=False, hoje=hoje)

    assert resultado.read_bytes() == b"conteudo em cache, desatualizado"


def test_baixar_zip_ano_prazo_vencido_download_falha_sem_cache_propaga_erro(tmp_path, monkeypatch):
    hoje = datetime(2027, 1, 1)
    monkeypatch.setattr(
        cvm.requests,
        "get",
        lambda url, timeout, stream: _RespostaStreamFalsa(b"", status_ok=False),
    )

    with pytest.raises(requests.HTTPError):
        cvm._baixar_zip_ano(2026, tmp_path, forcar_atualizacao=False, hoje=hoje)


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


def test_cfo_cfi_do_periodo_devolve_os_dois_componentes_separados():
    # _cfo_cfi_do_periodo devolve os dois componentes separados (não só a soma),
    # usados pra calcular a proporção reinvestida (ver modelos.fcd.calcular_
    # proporcao_capex_caixa_operacional_percentual).
    linhas = [
        {"CD_CONTA": "6.01", "VL_CONTA": "204037000.0000000000", "ESCALA_MOEDA": "MIL"},
        {"CD_CONTA": "6.02", "VL_CONTA": "-72363000.0000000000", "ESCALA_MOEDA": "MIL"},
    ]
    cfo, cfi = cvm._cfo_cfi_do_periodo(linhas)
    assert cfo == pytest.approx(204037000000.0)
    assert cfi == pytest.approx(-72363000000.0)
    assert cfo + cfi == pytest.approx(131674000000.0)


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


CNPJ_SINTETICO_ZERADA = "00.000.000/0004-00"
CABECALHO_DFC = (
    "CNPJ_CIA;CD_CVM;DENOM_CIA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA"
)


def _zip_dfc_sintetico(caminho: Path, ano: int, membros: dict) -> Path:
    """Zip mínimo só com os quatro CSVs da DFC (vazios, exceto os de
    `membros`: (método, tipo) -> lista de (CD_CONTA, VL_CONTA), em MIL)."""
    with zipfile.ZipFile(caminho, "w") as arquivo_zip:
        for metodo in ("MI", "MD"):
            for tipo in ("con", "ind"):
                linhas = [CABECALHO_DFC]
                for codigo, valor in membros.get((metodo, tipo), []):
                    linhas.append(
                        f"{CNPJ_SINTETICO_ZERADA};000001;EMPRESA SINTETICA S.A.;MIL;ÚLTIMO;"
                        f"{ano}-12-31;{codigo};Conta {codigo};{valor}"
                    )
                arquivo_zip.writestr(
                    f"dfp_cia_aberta_DFC_{metodo}_{tipo}_{ano}.csv",
                    "\n".join(linhas).encode("iso-8859-1"),
                )
    return caminho


def _fluxo_com_zip(tmp_path, monkeypatch, membros):
    caminho_zip = _zip_dfc_sintetico(tmp_path / "dfp_sintetico.zip", 2024, membros)
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: caminho_zip)
    return cvm.obter_fluxo_caixa_livre(CNPJ_SINTETICO_ZERADA, 2024, diretorio_cache=tmp_path)


def test_obter_fluxo_caixa_livre_consolidada_zerada_usa_a_individual(tmp_path, monkeypatch):
    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "0"), ("6.02", "0")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
    )

    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)


def test_obter_fluxo_caixa_livre_consolidada_sem_6_01_e_6_02_usa_a_individual(
    tmp_path, monkeypatch
):
    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.03", "-80")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
    )

    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)


def test_obter_fluxo_caixa_livre_consolidada_valida_continua_sendo_a_escolhida(
    tmp_path, monkeypatch
):
    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "900"), ("6.02", "-300")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
    )

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["fcf_atual"] == pytest.approx(600.0 * 1000)


def test_obter_fluxo_caixa_livre_consolidada_com_so_um_dos_dois_zerado_nao_e_pulada(
    tmp_path, monkeypatch
):
    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "0"), ("6.02", "-100")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
    )

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["fcf_atual"] == pytest.approx(-100.0 * 1000)


def test_obter_fluxo_caixa_livre_as_duas_zeradas_mantem_a_consolidada(tmp_path, monkeypatch):
    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "0"), ("6.02", "0")],
            ("MI", "ind"): [("6.01", "0"), ("6.02", "0")],
        },
    )

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["fcf_atual"] == 0.0


def test_obter_fluxo_caixa_livre_ignora_cache_da_versao_anterior_do_schema(tmp_path, monkeypatch):
    # Cache de uma versão anterior do schema (escolha de demonstração com
    # consolidada zerada) não pode ser servido.
    caminho_cache = tmp_path / "cvm" / "fcf_00000000000400_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text(
        json.dumps({"versao_schema": 1, "resultado": {"fcf_atual": 0.0}}), encoding="utf-8"
    )

    resultado = _fluxo_com_zip(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "0"), ("6.02", "0")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
    )

    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)


def test_obter_fluxo_caixa_livre_levanta_cnpj_nao_encontrado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    with pytest.raises(cvm.CnpjNaoEncontrado):
        cvm.obter_fluxo_caixa_livre("11.111.111/1111-11", 2024, diretorio_cache=tmp_path)


def test_obter_fluxo_caixa_livre_devolve_cfo_e_cfi_separados(tmp_path, monkeypatch):
    # cfo_atual/cfi_atual são expostos separados no resultado, pra calcular a
    # proporção reinvestida (ver modelos.fcd.calcular_
    # proporcao_capex_caixa_operacional_percentual) — mesmos números que compõem
    # fcf_atual em test_obter_fluxo_caixa_livre_prefere_mi_
    # consolidado (204037000000 + (-72363000000) = 131674000000).
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["cfo_atual"] == pytest.approx(204037000000.0)
    assert resultado["cfi_atual"] == pytest.approx(-72363000000.0)
    assert resultado["cfo_atual"] + resultado["cfi_atual"] == pytest.approx(resultado["fcf_atual"])


def test_obter_fluxo_caixa_livre_ignora_cache_em_formato_antigo_sem_envelope(tmp_path, monkeypatch):
    # Mesmo padrão de fundamentus._ler_cache_com_schema_atual: um cache em
    # formato sem o envelope {"versao_schema": ..., "resultado": ...} precisa ser
    # tratado como cache miss, não devolvido sem as chaves cfo_atual/cfi_atual.
    caminho_cache = tmp_path / "cvm" / "fcf_33000167000101_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text('{"fcf_atual": 999.0}', encoding="utf-8")

    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    # Buscou de novo (não devolveu o 999.0 do cache antigo) e já regrava
    # no formato novo, com envelope de versão.
    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)
    assert resultado["cfo_atual"] == pytest.approx(204037000000.0)
    envelope = json.loads(caminho_cache.read_text(encoding="utf-8"))
    assert envelope["versao_schema"] == cvm.VERSAO_SCHEMA_CVM_FCF


def test_obter_fluxo_caixa_livre_ignora_cache_com_versao_diferente(tmp_path, monkeypatch):
    caminho_cache = tmp_path / "cvm" / "fcf_33000167000101_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text(
        json.dumps({"versao_schema": 0, "resultado": {"fcf_atual": 999.0}}), encoding="utf-8"
    )

    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)


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


# --- Detecção automática do ano de referência -------------------------------
# Ver docs/correcao-ano-fcd-2026-09-23.md: o ano é detectado em dois níveis,
# sem constante fixa. Os testes
# abaixo mockam `_baixar_zip_ano`/`obter_fluxo_caixa_livre` diretamente (não
# `requests.get`) porque testam a ORQUESTRAÇÃO da detecção, não o download
# ou o parsing em si (já cobertos acima).


def _erro_http_404() -> requests.HTTPError:
    """Réplica o formato real de `Response.raise_for_status()` (erro com
    `.response.status_code` preenchido) — a fake `_RespostaStreamFalsa`
    usada nos testes de `_baixar_zip_ano` acima não preenche `.response`,
    então não serve pra testar a distinção 404 vs. outros erros aqui."""
    erro = requests.HTTPError("404 Client Error: Not Found")
    erro.response = requests.Response()
    erro.response.status_code = 404
    return erro


def test_resolver_ano_mais_recente_disponivel_usa_ano_candidato_quando_zip_existe(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda ano, *a, **k: ZIP_AMOSTRA)

    ano = cvm.resolver_ano_mais_recente_disponivel(
        diretorio_cache=tmp_path, hoje=datetime(2026, 6, 1)
    )

    assert ano == 2025


def test_resolver_ano_mais_recente_disponivel_cai_pro_ano_anterior_quando_404(
    tmp_path, monkeypatch
):
    def baixar_falso(ano, diretorio_cache, forcar_atualizacao):
        if ano == 2026:
            raise _erro_http_404()
        return ZIP_AMOSTRA

    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar_falso)

    ano = cvm.resolver_ano_mais_recente_disponivel(
        diretorio_cache=tmp_path, hoje=datetime(2027, 2, 15)
    )

    assert ano == 2025


def test_resolver_ano_mais_recente_disponivel_janela_transicao_fevereiro_zip_ja_disponivel(
    tmp_path, monkeypatch
):
    # Mesma janela jan-mar do teste acima, mas com o zip do ano candidato JÁ
    # publicado — não deve cair pro ano anterior só por estar na janela.
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda ano, *a, **k: ZIP_AMOSTRA)

    ano = cvm.resolver_ano_mais_recente_disponivel(
        diretorio_cache=tmp_path, hoje=datetime(2027, 2, 15)
    )

    assert ano == 2026


def test_resolver_ano_mais_recente_disponivel_propaga_erro_que_nao_e_404(tmp_path, monkeypatch):
    def baixar_falso(*args, **kwargs):
        raise requests.ConnectionError("rede fora do ar")

    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar_falso)

    with pytest.raises(requests.ConnectionError):
        cvm.resolver_ano_mais_recente_disponivel(
            diretorio_cache=tmp_path, hoje=datetime(2027, 2, 15)
        )


def test_obter_fluxo_caixa_livre_com_fallback_usa_ano_mais_recente_quando_empresa_esta_nele(
    tmp_path, monkeypatch
):
    chamadas = []

    def obter_falso(cnpj, ano, *a, **k):
        chamadas.append(ano)
        if ano == 2025:
            return {"fcf_atual": 100.0, "cfo_atual": 60.0, "cfi_atual": -30.0, **EXTRAS_FCF_MOCK}
        return {"fcf_atual": 80.0, "cfo_atual": 50.0, **EXTRAS_FCF_MOCK}

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS,
        ano_mais_recente=2025,
        anos_historico_crescimento=5,
        diretorio_cache=tmp_path,
    )

    assert resultado["ano_referencia_utilizado"] == 2025
    assert resultado["usou_fallback"] is False
    assert resultado["fcf_atual"] == 100.0
    assert resultado["fcf_ha_n_anos"] == 80.0
    assert resultado["cfo_atual"] == 60.0
    assert resultado["cfi_atual"] == -30.0
    assert chamadas == [2025, 2020]  # ano base = 2025 - 5


def test_obter_fluxo_caixa_livre_com_fallback_devolve_o_fluxo_do_ano_base_para_o_fcd(
    tmp_path, monkeypatch
):
    def obter_falso(cnpj, ano, *a, **k):
        if ano == 2025:
            return {"fcf_atual": 100.0, "cfo_atual": 60.0, "cfi_atual": -30.0, **EXTRAS_FCF_MOCK}
        if ano == 2020:
            return {
                "fcf_atual": 80.0,
                "cfo_atual": 50.0,
                "capex_atual": {"status": "identificado", "valor": 20.0, "linhas": []},
                "juros_pagos_atual": {"valor": 5.0, "linhas": []},
            }
        raise cvm.CnpjNaoEncontrado("sem demonstração")

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS, 2025, 5, diretorio_cache=tmp_path
    )

    assert resultado["cfo_ha_n_anos"] == 50.0
    assert resultado["capex_ha_n_anos"]["valor"] == 20.0
    assert resultado["juros_pagos_ha_n_anos"]["valor"] == 5.0

    # Sem demonstração do ano-base, tudo do ano-base fica None.
    resultado_sem_base = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS, 2025, 6, diretorio_cache=tmp_path
    )
    assert resultado_sem_base["cfo_ha_n_anos"] is None
    assert resultado_sem_base["capex_ha_n_anos"] is None


def _fallback_com_dois_zips(tmp_path, monkeypatch, membros_2025, membros_2020):
    zips = {
        2025: _zip_dfc_sintetico(tmp_path / "dfp_2025.zip", 2025, membros_2025),
        2020: _zip_dfc_sintetico(tmp_path / "dfp_2020.zip", 2020, membros_2020),
    }
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda ano, *a, **k: zips[ano])
    return cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_SINTETICO_ZERADA, 2025, 5, diretorio_cache=tmp_path
    )


def test_fallback_usa_no_ano_base_o_mesmo_tipo_do_ano_de_referencia(tmp_path, monkeypatch):
    # 2025: consolidada zerada, vale a individual. 2020: as duas têm valores
    # e a consolidada ganharia por prioridade, mas o crescimento usa a individual.
    resultado = _fallback_com_dois_zips(
        tmp_path,
        monkeypatch,
        {
            ("MI", "con"): [("6.01", "0"), ("6.02", "0")],
            ("MI", "ind"): [("6.01", "600"), ("6.02", "-150")],
        },
        {
            ("MI", "con"): [("6.01", "200"), ("6.02", "-50")],
            ("MI", "ind"): [("6.01", "300"), ("6.02", "-100")],
        },
    )

    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)
    assert resultado["fcf_ha_n_anos"] == pytest.approx(200.0 * 1000)


def test_fallback_mantem_o_tipo_do_ano_base_quando_o_do_ano_de_referencia_nao_existe_nele(
    tmp_path, monkeypatch
):
    resultado = _fallback_com_dois_zips(
        tmp_path,
        monkeypatch,
        {("MI", "ind"): [("6.01", "600"), ("6.02", "-150")]},
        {("MI", "con"): [("6.01", "200"), ("6.02", "-50")]},
    )

    assert resultado["fcf_ha_n_anos"] == pytest.approx(150.0 * 1000)


def test_fallback_nao_troca_o_tipo_do_ano_base_quando_o_do_ano_de_referencia_esta_zerado_nele(
    tmp_path, monkeypatch
):
    resultado = _fallback_com_dois_zips(
        tmp_path,
        monkeypatch,
        {("MI", "ind"): [("6.01", "600"), ("6.02", "-150")]},
        {
            ("MI", "con"): [("6.01", "200"), ("6.02", "-50")],
            ("MI", "ind"): [("6.01", "0"), ("6.02", "0")],
        },
    )

    assert resultado["fcf_ha_n_anos"] == pytest.approx(150.0 * 1000)


def test_fallback_com_o_mesmo_tipo_nos_dois_anos_nao_muda_nada(tmp_path, monkeypatch):
    resultado = _fallback_com_dois_zips(
        tmp_path,
        monkeypatch,
        {("MI", "con"): [("6.01", "600"), ("6.02", "-150")]},
        {
            ("MI", "con"): [("6.01", "200"), ("6.02", "-50")],
            ("MI", "ind"): [("6.01", "300"), ("6.02", "-100")],
        },
    )

    assert resultado["fcf_ha_n_anos"] == pytest.approx(150.0 * 1000)


def test_obter_fluxo_caixa_livre_do_tipo_devolve_so_a_demonstracao_pedida(tmp_path, monkeypatch):
    caminho_zip = _zip_dfc_sintetico(
        tmp_path / "dfp.zip",
        2024,
        {
            ("MI", "con"): [("6.01", "200"), ("6.02", "-50")],
            ("MI", "ind"): [("6.01", "300"), ("6.02", "-100")],
        },
    )
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: caminho_zip)

    resultado = cvm.obter_fluxo_caixa_livre_do_tipo(
        CNPJ_SINTETICO_ZERADA, 2024, "MI", "ind", diretorio_cache=tmp_path
    )

    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["fcf_atual"] == pytest.approx(200.0 * 1000)
    assert (
        cvm.obter_fluxo_caixa_livre_do_tipo(
            CNPJ_SINTETICO_ZERADA, 2024, "MD", "con", diretorio_cache=tmp_path
        )
        is None
    )


def test_obter_fluxo_caixa_livre_com_fallback_cai_um_ano_so_pra_empresa_ausente(
    tmp_path, monkeypatch
):
    def obter_falso(cnpj, ano, *a, **k):
        if ano == 2025:
            raise cvm.CnpjNaoEncontrado("não encontrado em 2025")
        if ano == 2024:
            return {"fcf_atual": 100.0, "cfo_atual": 70.0, "cfi_atual": -20.0, **EXTRAS_FCF_MOCK}
        if ano == 2019:
            return {"fcf_atual": 80.0, "cfo_atual": 50.0, **EXTRAS_FCF_MOCK}
        raise AssertionError(f"ano inesperado: {ano}")

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS,
        ano_mais_recente=2025,
        anos_historico_crescimento=5,
        diretorio_cache=tmp_path,
    )

    # Empresa não aparece em 2025 -> cai pra 2024, e o ano-base do
    # crescimento cai JUNTO (2019, não 2020) — continua 5 anos de intervalo.
    assert resultado["ano_referencia_utilizado"] == 2024
    assert resultado["usou_fallback"] is True
    assert resultado["fcf_atual"] == 100.0
    assert resultado["fcf_ha_n_anos"] == 80.0
    # cfo_atual/cfi_atual são do ano EFETIVAMENTE usado (2024, pós-
    # fallback), não do ano_mais_recente original (2025) nem do ano_base
    # (2019).
    assert resultado["cfo_atual"] == 70.0
    assert resultado["cfi_atual"] == -20.0


def test_obter_fluxo_caixa_livre_com_fallback_propaga_conta_fluxo_caixa_nao_encontrada_sem_fallback(
    tmp_path, monkeypatch
):
    chamadas = []

    def obter_falso(cnpj, ano, *a, **k):
        chamadas.append(ano)
        raise cvm.ContaFluxoCaixaNaoEncontrada("layout mudou")

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    with pytest.raises(cvm.ContaFluxoCaixaNaoEncontrada):
        cvm.obter_fluxo_caixa_livre_com_fallback(
            CNPJ_PETROBRAS,
            ano_mais_recente=2025,
            anos_historico_crescimento=5,
            diretorio_cache=tmp_path,
        )

    # Não tentou 2024 — layout mudado não é "ainda não publicado".
    assert chamadas == [2025]


def test_obter_fluxo_caixa_livre_com_fallback_propaga_cnpj_nao_encontrado_nos_dois_anos(
    tmp_path, monkeypatch
):
    def obter_falso(cnpj, ano, *a, **k):
        raise cvm.CnpjNaoEncontrado(f"não encontrado em {ano}")

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    with pytest.raises(cvm.CnpjNaoEncontrado):
        cvm.obter_fluxo_caixa_livre_com_fallback(
            CNPJ_PETROBRAS,
            ano_mais_recente=2025,
            anos_historico_crescimento=5,
            diretorio_cache=tmp_path,
        )


# --- Capex e juros pagos por descrição das subcontas -------------------------
#
# Descrições reais (DFP 2025) citadas na investigação do FCD; valores em MIL.


def _linhas_com_subcontas(*subcontas):
    base = [
        _linha("6.01", "Caixa Líquido Atividades Operacionais", "1000"),
        _linha("6.02", "Caixa Líquido Atividades de Investimento", "-300"),
    ]
    return base + [_linha(codigo, descricao, valor) for codigo, descricao, valor in subcontas]


def test_extrair_capex_uma_linha_de_imobilizado_e_intangivel():
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisições de ativos imobilizados e intangíveis", "-108714"),
        ("6.02.02", "Aplicações financeiras e recursos vinculados", "-312"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["status"] == "identificado"
    assert capex["valor"] == pytest.approx(108714.0 * 1000)
    assert [linha["codigo"] for linha in capex["linhas"]] == ["6.02.01"]
    assert capex["linhas"][0]["descricao"] == "Aquisições de ativos imobilizados e intangíveis"


def test_extrair_capex_soma_imobilizado_e_intangivel_separados():
    linhas = _linhas_com_subcontas(
        ("6.02.02", "Imobilizado", "-2563"),
        ("6.02.03", "Intangível", "-128"),
        ("6.02.04", "Aplicações no imobilizado, intangível e ativo contratual", "-5644"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["status"] == "identificado"
    assert capex["valor"] == pytest.approx((2563 + 128 + 5644) * 1000.0)
    assert len(capex["linhas"]) == 3


def test_extrair_capex_reconhece_ativo_contratual_e_ativos_de_contrato():
    linhas = _linhas_com_subcontas(
        ("6.02.03", "Adições de ativo contratual", "-4964"),
        ("6.02.04", "Aquisições de ativos de contrato", "-1937"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["valor"] == pytest.approx((4964 + 1937) * 1000.0)


def test_extrair_capex_nao_conta_a_linha_filha_quando_a_pai_ja_entrou():
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisição de imobilizado e intangível", "-500"),
        ("6.02.01.01", "Aquisição de imobilizado", "-400"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["valor"] == pytest.approx(500.0 * 1000)


def test_extrair_capex_ignora_venda_de_imobilizado_como_falso_positivo():
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisição de imobilizado", "-1000"),
        ("6.02.02", "Recebimento pela venda de imobilizado", "300"),
        ("6.02.03", "Alienação de bens do imobilizado e intangível", "64"),
        ("6.02.04", "Caixa recebido na venda de ativos imobilizado e intangível", "9"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["valor"] == pytest.approx(1000.0 * 1000)
    assert len(capex["linhas"]) == 1


def test_extrair_capex_so_venda_de_imobilizado_nao_e_capex():
    linhas = _linhas_com_subcontas(("6.02.01", "Venda de imobilizado", "300"))

    capex = cvm._extrair_capex(linhas)

    assert capex == {"status": "nao_identificado", "valor": None, "linhas": []}


def test_extrair_capex_nao_identificado_quando_a_linha_nao_cita_imobilizado_nem_intangivel():
    # Caso real da IGTI11: "Aquisições de Ativo Não Circulante" mistura imobilizado
    # e propriedades para investimento sem dizer qual — não é identificado.
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisições de Ativo Não Circulante", "-1104"),
        ("6.02.02", "Venda de Ativo Permanente", "310"),
        ("6.02.08", "Aplicações Financeiras Mantidas para Negociação", "264"),
    )

    capex = cvm._extrair_capex(linhas)

    assert capex["status"] == "nao_identificado"
    assert capex["valor"] is None


def test_extrair_capex_ignora_aquisicao_de_participacao():
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisição de controladas, líquido do caixa adquirido", "-616"),
        ("6.02.02", "Aumento de capital em empresas do imobilizado", "-10"),
    )

    assert cvm._extrair_capex(linhas)["status"] == "nao_identificado"


def test_extrair_juros_pagos_linhas_dedicadas_de_6_01():
    linhas = _linhas_com_subcontas(
        ("6.01.03.01", "Encargos de dívidas e debêntures pagos", "-2085"),
        ("6.01.03.02", "Juros pagos sobre empréstimos e financiamentos", "-300"),
    )

    juros = cvm._extrair_juros_pagos_6_01(linhas)

    assert juros["valor"] == pytest.approx(2385.0 * 1000)
    assert len(juros["linhas"]) == 2


def test_extrair_juros_pagos_nao_conta_a_linha_filha_quando_a_pai_ja_entrou():
    linhas = _linhas_com_subcontas(
        ("6.01.03", "Juros pagos", "-300"),
        ("6.01.03.01", "Juros pagos de empréstimos", "-300"),
    )

    assert cvm._extrair_juros_pagos_6_01(linhas)["valor"] == pytest.approx(300.0 * 1000)


def test_extrair_juros_pagos_ignora_juros_de_arrendamento():
    linhas = _linhas_com_subcontas(
        ("6.01.03.03", "Juros de arrendamento por direito de uso pagos", "-279"),
        ("6.01.03.04", "Pagamento de juros de arrendamento mercantil", "-100"),
        (
            "6.01.03.05",
            "Juros pagos de empréstimos, financiamentos, debêntures e arrendamentos",
            "-50",
        ),
    )

    juros = cvm._extrair_juros_pagos_6_01(linhas)

    assert juros == {"valor": 0.0, "linhas": []}


def test_extrair_juros_pagos_ignora_juros_recebidos_rendimentos_jcp_e_linhas_mistas():
    linhas = _linhas_com_subcontas(
        ("6.01.03.01", "Juros recebidos", "50"),
        ("6.01.02.02", "Dividendo e juros sobre o capital próprio recebidos", "285"),
        ("6.01.03.02", "Rendimentos de aplicações financeiras", "10"),
        ("6.01.03.03", "Juros sobre capital próprio pagos", "-40"),
        ("6.01.03.04", "Pagamento de principal e juros de empréstimos", "-900"),
        (
            "6.01.01.05",
            "Encargos de dívidas, juros, variações monetárias e cambiais líquidas",
            "4793",
        ),
    )

    assert cvm._extrair_juros_pagos_6_01(linhas) == {"valor": 0.0, "linhas": []}


def test_extrair_juros_pagos_so_considera_6_01():
    linhas = _linhas_com_subcontas(
        ("6.03.04", "Juros pagos", "-10311"),
        ("6.01.03.01", "Juros pagos", "-200"),
    )

    assert cvm._extrair_juros_pagos_6_01(linhas)["valor"] == pytest.approx(200.0 * 1000)


def test_montar_resultado_fcf_traz_capex_e_juros_pagos():
    linhas = _linhas_com_subcontas(
        ("6.02.01", "Aquisição de imobilizado", "-250"),
        ("6.01.03.01", "Juros pagos", "-80"),
    )

    resultado = cvm._montar_resultado_fcf(2024, "con", "MI", linhas)

    assert resultado["capex_atual"]["valor"] == pytest.approx(250.0 * 1000)
    assert resultado["juros_pagos_atual"]["valor"] == pytest.approx(80.0 * 1000)
    json.dumps(resultado)  # vai pro cache em JSON


def test_obter_fluxo_caixa_livre_ignora_cache_da_versao_2_do_schema(tmp_path, monkeypatch):
    # Cache da versão anterior não tem capex nem juros pagos: tem que ser refeito.
    caminho_cache = tmp_path / "cvm" / "fcf_33000167000101_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text(
        json.dumps({"versao_schema": 2, "resultado": {"fcf_atual": 999.0}}), encoding="utf-8"
    )
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)
    assert "capex_atual" in resultado
    assert "juros_pagos_atual" in resultado


# --- Receita líquida (DRE 3.01) lida junto com a DFC de cada ano ----------------------


def test_receita_do_ano_vem_da_dre_consolidada_na_fixture_real_da_petrobras(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["tipo_demonstracao"] == "consolidado"
    assert resultado["receita_atual"]["valor"] == pytest.approx(490_829_000_000.0)
    assert resultado["receita_atual"]["versao"] == 1
    assert resultado["receita_atual"]["motivo"] is None


CABECALHO_COM_VERSAO = (
    "CNPJ_CIA;VERSAO;CD_CVM;DENOM_CIA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;"
    "VL_CONTA"
)


def _zip_com_dfc_e_dre(caminho: Path, ano: int, dfc: dict, dre: dict) -> Path:
    """Zip sintético com a DFC e a DRE de uma empresa. `dfc`: (método, tipo) -> (versão, [(conta,
    valor)]); `dre`: tipo -> [(versão, ordem, conta, valor)], valores em MIL."""
    with zipfile.ZipFile(caminho, "w") as arquivo_zip:
        for metodo in ("MI", "MD"):
            for tipo in ("con", "ind"):
                linhas = [CABECALHO_COM_VERSAO]
                versao, contas = dfc.get((metodo, tipo), (1, []))
                for conta in contas:
                    codigo, valor = conta[0], conta[1]
                    descricao = conta[2] if len(conta) > 2 else f"Conta {codigo}"
                    linhas.append(
                        f"{CNPJ_SINTETICO_ZERADA};{versao};000001;EMPRESA SINTETICA S.A.;MIL;"
                        f"ÚLTIMO;{ano}-12-31;{codigo};{descricao};{valor}"
                    )
                arquivo_zip.writestr(
                    f"dfp_cia_aberta_DFC_{metodo}_{tipo}_{ano}.csv",
                    "\n".join(linhas).encode("iso-8859-1"),
                )
        for tipo in ("con", "ind"):
            if tipo not in dre:
                continue
            linhas = [CABECALHO_COM_VERSAO]
            for versao, ordem, codigo, valor in dre[tipo]:
                linhas.append(
                    f"{CNPJ_SINTETICO_ZERADA};{versao};000001;EMPRESA SINTETICA S.A.;MIL;{ordem};"
                    f"{ano}-12-31;{codigo};Conta {codigo};{valor}"
                )
            arquivo_zip.writestr(
                f"dfp_cia_aberta_DRE_{tipo}_{ano}.csv", "\n".join(linhas).encode("iso-8859-1")
            )
    return caminho


def _receita_com_zip(tmp_path, monkeypatch, dfc, dre):
    caminho_zip = _zip_com_dfc_e_dre(tmp_path / "dfp_receita.zip", 2024, dfc, dre)
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: caminho_zip)
    return cvm.obter_fluxo_caixa_livre(CNPJ_SINTETICO_ZERADA, 2024, diretorio_cache=tmp_path)


DFC_CON_SIMPLES = {("MI", "con"): (1, [("6.01", "600"), ("6.02", "-150")])}


def test_receita_usa_a_dre_do_mesmo_tipo_da_dfc_escolhida(tmp_path, monkeypatch):
    # A consolidada da DFC está zerada, então a individual é a escolhida: a receita também
    # vem da DRE individual (e não da consolidada).
    dfc = {
        ("MI", "con"): (1, [("6.01", "0"), ("6.02", "0")]),
        ("MI", "ind"): (1, [("6.01", "600"), ("6.02", "-150")]),
    }
    dre = {
        "con": [(1, "ÚLTIMO", "3.01", "9000")],
        "ind": [(1, "ÚLTIMO", "3.01", "4000")],
    }

    resultado = _receita_com_zip(tmp_path, monkeypatch, dfc, dre)

    assert resultado["tipo_demonstracao"] == "individual"
    assert resultado["receita_atual"]["valor"] == pytest.approx(4000.0 * 1000)


def test_receita_usa_a_versao_da_dre_igual_a_da_dfc(tmp_path, monkeypatch):
    dfc = {("MI", "con"): (1, [("6.01", "600"), ("6.02", "-150")])}
    dre = {"con": [(1, "ÚLTIMO", "3.01", "1000"), (2, "ÚLTIMO", "3.01", "1200")]}

    resultado = _receita_com_zip(tmp_path, monkeypatch, dfc, dre)

    assert resultado["receita_atual"]["versao"] == 1
    assert resultado["receita_atual"]["valor"] == pytest.approx(1000.0 * 1000)


def test_receita_sem_a_versao_da_dfc_usa_a_mais_recente_da_dre(tmp_path, monkeypatch):
    dfc = {("MI", "con"): (3, [("6.01", "600"), ("6.02", "-150")])}
    dre = {"con": [(1, "ÚLTIMO", "3.01", "1000"), (2, "ÚLTIMO", "3.01", "1200")]}

    resultado = _receita_com_zip(tmp_path, monkeypatch, dfc, dre)

    assert resultado["receita_atual"]["versao"] == 2
    assert resultado["receita_atual"]["valor"] == pytest.approx(1200.0 * 1000)


def test_receita_ignora_o_periodo_penultimo(tmp_path, monkeypatch):
    dre = {"con": [(1, "PENÚLTIMO", "3.01", "800"), (1, "ÚLTIMO", "3.01", "1000")]}

    resultado = _receita_com_zip(tmp_path, monkeypatch, DFC_CON_SIMPLES, dre)

    assert resultado["receita_atual"]["valor"] == pytest.approx(1000.0 * 1000)


def test_receita_sem_a_dre_do_ano_traz_o_motivo_e_nao_derruba_o_fluxo(tmp_path, monkeypatch):
    resultado = _receita_com_zip(tmp_path, monkeypatch, DFC_CON_SIMPLES, {})

    assert resultado["fcf_atual"] == pytest.approx(450.0 * 1000)
    assert resultado["receita_atual"]["valor"] is None
    assert resultado["receita_atual"]["motivo"] == MOTIVO_RECEITA_SEM_DRE


def test_receita_sem_a_conta_3_01_traz_o_motivo(tmp_path, monkeypatch):
    dre = {"con": [(1, "ÚLTIMO", "3.02", "500")]}

    resultado = _receita_com_zip(tmp_path, monkeypatch, DFC_CON_SIMPLES, dre)

    assert resultado["receita_atual"]["valor"] is None
    assert resultado["receita_atual"]["motivo"] == MOTIVO_RECEITA_SEM_CONTA


def test_receita_e_gravada_no_cache_com_o_schema_novo(tmp_path, monkeypatch):
    dre = {"con": [(1, "ÚLTIMO", "3.01", "1000")]}
    _receita_com_zip(tmp_path, monkeypatch, DFC_CON_SIMPLES, dre)

    cache = tmp_path / "cvm" / "fcf_00000000000400_2024.json"
    envelope = json.loads(cache.read_text(encoding="utf-8"))

    assert envelope["versao_schema"] == cvm.VERSAO_SCHEMA_CVM_FCF
    assert envelope["resultado"]["receita_atual"]["valor"] == pytest.approx(1000.0 * 1000)


def test_obter_fluxo_caixa_livre_ignora_cache_da_versao_3_do_schema_sem_receita(
    tmp_path, monkeypatch
):
    caminho_cache = tmp_path / "cvm" / "fcf_33000167000101_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text(
        json.dumps({"versao_schema": 3, "resultado": {"fcf_atual": 999.0}}), encoding="utf-8"
    )
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)
    assert resultado["receita_atual"]["valor"] == pytest.approx(490_829_000_000.0)


def test_fallback_devolve_a_receita_do_ano_de_referencia_e_a_do_ano_base(tmp_path, monkeypatch):
    def obter_falso(cnpj, ano, *a, **k):
        receita = {"valor": 2000.0 if ano == 2025 else 1000.0, "versao": 1, "motivo": None}
        return {
            "fcf_atual": 100.0,
            "cfo_atual": 60.0,
            "cfi_atual": -30.0,
            "receita_atual": receita,
            **EXTRAS_FCF_MOCK,
        }

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS,
        ano_mais_recente=2025,
        anos_historico_crescimento=5,
        diretorio_cache=tmp_path,
    )

    assert resultado["receita_atual"]["valor"] == pytest.approx(2000.0)
    assert resultado["receita_ha_n_anos"]["valor"] == pytest.approx(1000.0)


def test_fallback_sem_demonstracao_do_ano_base_deixa_a_receita_do_ano_base_vazia(
    tmp_path, monkeypatch
):
    def obter_falso(cnpj, ano, *a, **k):
        if ano == 2020:
            raise cvm.CnpjNaoEncontrado("sem 2020")
        return {
            "fcf_atual": 100.0,
            "cfo_atual": 60.0,
            "cfi_atual": -30.0,
            "receita_atual": {"valor": 2000.0, "versao": 1, "motivo": None},
            **EXTRAS_FCF_MOCK,
        }

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS,
        ano_mais_recente=2025,
        anos_historico_crescimento=5,
        diretorio_cache=tmp_path,
    )

    assert resultado["receita_atual"]["valor"] == pytest.approx(2000.0)
    assert resultado["receita_ha_n_anos"] is None


# --- Risco sacado e convênio com fornecedores (6.03) ----------------------------------


def _fluxo_com_6_03(tmp_path, monkeypatch, linhas_6_03):
    """DFC consolidada sintética com 6.01, 6.02 e as linhas de 6.03 dadas, em MIL."""
    contas = [("6.01", "15719"), ("6.02", "-1001"), *linhas_6_03]
    dfc = {("MI", "con"): (1, contas)}
    return _receita_com_zip(tmp_path, monkeypatch, dfc, {})


def test_risco_sacado_so_saida_reduz_o_caixa_operacional_caso_mglu3(tmp_path, monkeypatch):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [
            ("6.03.04", "-1685", "Pagamento de empréstimos e financiamentos"),
            ("6.03.05", "-13469", "Pagamento de fornecedores - convênio"),
        ],
    )

    risco = resultado["risco_sacado_atual"]
    assert risco["valor"] == pytest.approx(-13469.0 * 1000)
    assert risco["saldo"] == pytest.approx(-13469.0 * 1000)
    assert [linha["codigo"] for linha in risco["linhas"]] == ["6.03.05"]
    assert risco["linhas"][0]["descricao"] == "Pagamento de fornecedores - convênio"
    assert resultado["cfo_atual"] == pytest.approx(15719.0 * 1000)  # o caixa lido não muda


def test_risco_sacado_saida_e_entrada_do_mesmo_programa_usa_o_saldo_caso_flry3(
    tmp_path, monkeypatch
):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [
            ("6.03.08", "116", "Novas operações risco sacado"),
            ("6.03.09", "-121", "Liquidação (principal) risco sacado"),
        ],
    )

    risco = resultado["risco_sacado_atual"]
    assert risco["saldo"] == pytest.approx(-5.0 * 1000)
    assert risco["valor"] == pytest.approx(-5.0 * 1000)
    assert len(risco["linhas"]) == 2


def test_risco_sacado_saldo_de_entrada_e_ignorado_caso_viva3(tmp_path, monkeypatch):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [("6.03.08", "146.6", "Captação de financiamentos fornecedores convênio")],
    )

    risco = resultado["risco_sacado_atual"]
    assert risco["saldo"] == pytest.approx(146.6 * 1000)
    assert risco["valor"] == 0.0  # entrada: nada reduz o caixa operacional
    assert len(risco["linhas"]) == 1


def test_risco_sacado_ignora_o_termo_excluido_parcelamento(tmp_path, monkeypatch):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [("6.03.05", "-80", "Pagamento de parcelamento de fornecedores - convênio")],
    )

    assert resultado["risco_sacado_atual"] == {"valor": 0.0, "saldo": 0.0, "linhas": []}


def test_risco_sacado_empresa_sem_a_linha_nao_tem_ajuste(tmp_path, monkeypatch):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [
            ("6.03.03", "-784", "Pagamento de juros sobre empréstimos e financiamentos"),
            ("6.03.04", "-225", "Pagamento de dividendos"),
        ],
    )

    assert resultado["risco_sacado_atual"]["valor"] == 0.0
    assert resultado["risco_sacado_atual"]["linhas"] == []


def test_risco_sacado_so_conta_subcontas_de_primeiro_nivel_do_6_03(tmp_path, monkeypatch):
    # A subconta mais funda (6.03.05.01) detalha a 6.03.05; contar as duas seria dobrar.
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [
            ("6.03.05", "-100", "Pagamento de fornecedores - convênio"),
            ("6.03.05.01", "-100", "Convênio banco X"),
        ],
    )

    assert resultado["risco_sacado_atual"]["valor"] == pytest.approx(-100.0 * 1000)
    assert len(resultado["risco_sacado_atual"]["linhas"]) == 1


def test_risco_sacado_reconhece_risco_sacado_forfait_e_cessao_de_credito(tmp_path, monkeypatch):
    resultado = _fluxo_com_6_03(
        tmp_path,
        monkeypatch,
        [
            ("6.03.05", "-10", "Operação de Risco Sacado"),
            ("6.03.06", "-20", "Forfait"),
            ("6.03.07", "-30", "Cessão de crédito por fornecedores - amortizações"),
        ],
    )

    assert resultado["risco_sacado_atual"]["valor"] == pytest.approx(-60.0 * 1000)


def test_obter_fluxo_caixa_livre_ignora_cache_da_versao_4_do_schema_sem_risco_sacado(
    tmp_path, monkeypatch
):
    caminho_cache = tmp_path / "cvm" / "fcf_33000167000101_2024.json"
    caminho_cache.parent.mkdir(parents=True)
    caminho_cache.write_text(
        json.dumps({"versao_schema": 4, "resultado": {"fcf_atual": 999.0}}), encoding="utf-8"
    )
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["fcf_atual"] == pytest.approx(131674000000.0)
    assert "risco_sacado_atual" in resultado


def test_fallback_devolve_o_risco_sacado_dos_dois_anos(tmp_path, monkeypatch):
    def obter_falso(cnpj, ano, *a, **k):
        saldo = -500.0 if ano == 2025 else -40.0
        return {
            "fcf_atual": 100.0,
            "cfo_atual": 60.0,
            "cfi_atual": -30.0,
            "risco_sacado_atual": {"valor": saldo, "saldo": saldo, "linhas": []},
            **EXTRAS_FCF_MOCK,
        }

    monkeypatch.setattr(cvm, "obter_fluxo_caixa_livre", obter_falso)

    resultado = cvm.obter_fluxo_caixa_livre_com_fallback(
        CNPJ_PETROBRAS,
        ano_mais_recente=2025,
        anos_historico_crescimento=5,
        diretorio_cache=tmp_path,
    )

    assert resultado["risco_sacado_atual"]["valor"] == pytest.approx(-500.0)
    assert resultado["risco_sacado_ha_n_anos"]["valor"] == pytest.approx(-40.0)
