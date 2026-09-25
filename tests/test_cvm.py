import json
import os
from datetime import datetime, timedelta
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


def test_normalizar_cnpj_completa_zero_a_esquerda_perdido():
    # Camada defensiva (2026-09-25, ver config.py/crosswalk_cnpj.py): o
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
    # Líquido e o de Fluxo de Caixa (_fcf_do_periodo) — antes de aceitar
    # classe_erro, uma escala desconhecida numa conta CFO/CFI levantava
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


# --- Prazo de validade do cache do zip pro ano em preenchimento (correção
# de 2026-09-23) — ver docs/correcao-ano-fcd-2026-09-23.md e o comentário
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
    # Regressão (2026-09-25): _fcf_do_periodo virou _cfo_cfi_do_periodo —
    # devolve os dois componentes separados (não só a soma), usados pra
    # calcular a proporção reinvestida (ver modelos.fcd.calcular_
    # proporcao_reinvestimento_percentual).
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


def test_obter_fluxo_caixa_livre_levanta_cnpj_nao_encontrado(tmp_path, monkeypatch):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    with pytest.raises(cvm.CnpjNaoEncontrado):
        cvm.obter_fluxo_caixa_livre("11.111.111/1111-11", 2024, diretorio_cache=tmp_path)


def test_obter_fluxo_caixa_livre_devolve_cfo_e_cfi_separados(tmp_path, monkeypatch):
    # 2026-09-25: cfo_atual/cfi_atual expostos separados no resultado, pra
    # calcular a proporção reinvestida (ver modelos.fcd.calcular_
    # proporcao_reinvestimento_percentual) — mesmos números que já
    # compunham fcf_atual em test_obter_fluxo_caixa_livre_prefere_mi_
    # consolidado (204037000000 + (-72363000000) = 131674000000).
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *a, **k: ZIP_AMOSTRA)

    resultado = cvm.obter_fluxo_caixa_livre(CNPJ_PETROBRAS, 2024, diretorio_cache=tmp_path)

    assert resultado["cfo_atual"] == pytest.approx(204037000000.0)
    assert resultado["cfi_atual"] == pytest.approx(-72363000000.0)
    assert resultado["cfo_atual"] + resultado["cfi_atual"] == pytest.approx(resultado["fcf_atual"])


def test_obter_fluxo_caixa_livre_ignora_cache_em_formato_antigo_sem_envelope(
    tmp_path, monkeypatch
):
    # Regressão (2026-09-25, mesmo padrão de
    # fundamentus._ler_cache_com_schema_atual): um cache gravado ANTES da
    # versão com cfo_atual/cfi_atual (formato antigo, sem o envelope
    # {"versao_schema": ..., "resultado": ...}) precisa ser tratado como
    # cache miss, não devolvido sem essas chaves novas.
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


# --- Detecção automática do ano de referência (correção de 2026-09-23) ---
# Ver docs/correcao-ano-fcd-2026-09-23.md: constante fixa ANO_REFERENCIA_FCD
# removida de config.py, substituída por detecção em dois níveis. Os testes
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
            return {"fcf_atual": 100.0, "cfo_atual": 60.0, "cfi_atual": -30.0}
        return {"fcf_atual": 80.0}

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


def test_obter_fluxo_caixa_livre_com_fallback_cai_um_ano_so_pra_empresa_ausente(
    tmp_path, monkeypatch
):
    def obter_falso(cnpj, ano, *a, **k):
        if ano == 2025:
            raise cvm.CnpjNaoEncontrado("não encontrado em 2025")
        if ano == 2024:
            return {"fcf_atual": 100.0, "cfo_atual": 70.0, "cfi_atual": -20.0}
        if ano == 2019:
            return {"fcf_atual": 80.0}
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
