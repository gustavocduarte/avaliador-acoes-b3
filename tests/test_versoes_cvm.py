"""Reapresentações da CVM: só a maior VERSAO de cada empresa e data entra nos cálculos, sem
misturar valores de duas versões nem somar linhas de capex, juros e risco sacado das duas."""

import zipfile

import pytest

from avaliador_b3.ingest import cvm
from avaliador_b3.ingest.cvm import so_a_maior_versao

CNPJ = "00.000.000/0004-00"
OUTRO_CNPJ = "11.111.111/0001-11"
CABECALHO = (
    "CNPJ_CIA;DT_REFER;VERSAO;CD_CVM;DENOM_CIA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;"
    "CD_CONTA;DS_CONTA;VL_CONTA"
)


def _linha(versao, codigo, descricao, valor, ordem="ÚLTIMO", cnpj=CNPJ, dt_refer="2025-12-31"):
    return {
        "CNPJ_CIA": cnpj,
        "DT_REFER": dt_refer,
        "VERSAO": str(versao),
        "CD_CVM": "000001",
        "DENOM_CIA": "EMPRESA SINTETICA S.A.",
        "ESCALA_MOEDA": "UNIDADE",
        "ORDEM_EXERC": ordem,
        "DT_FIM_EXERC": dt_refer,
        "CD_CONTA": codigo,
        "DS_CONTA": descricao,
        "VL_CONTA": str(valor),
    }


def _csv(linhas):
    colunas = CABECALHO.split(";")
    corpo = [";".join(linha[coluna] for coluna in colunas) for linha in linhas]
    return "\n".join([CABECALHO, *corpo]).encode("iso-8859-1")


def _dfc_da_versao(versao, cfo, cfi, capex, juros, sacado, cfo_anterior=50, cfi_anterior=-5):
    contas = [
        ("6.01", "Caixa Líquido Atividades Operacionais", cfo),
        ("6.01.05", "Juros pagos de empréstimos e financiamentos", juros),
        ("6.02", "Caixa Líquido Atividades de Investimento", cfi),
        ("6.02.01", "Aquisições de ativos imobilizados e intangíveis", capex),
        ("6.03.07", "Operações de risco sacado (convênio com fornecedores)", sacado),
    ]
    linhas = [_linha(versao, codigo, descricao, valor) for codigo, descricao, valor in contas]
    linhas.append(
        _linha(versao, "6.01", "Caixa Líquido Atividades Operacionais", cfo_anterior, "PENÚLTIMO")
    )
    linhas.append(
        _linha(
            versao, "6.02", "Caixa Líquido Atividades de Investimento", cfi_anterior, "PENÚLTIMO"
        )
    )
    return linhas


V1 = _dfc_da_versao(1, cfo=100, cfi=-10, capex=-8, juros=-4, sacado=-6, cfo_anterior=40)
V2 = _dfc_da_versao(2, cfo=200, cfi=-20, capex=-15, juros=-9, sacado=-12, cfo_anterior=60)


def _zip(tmp_path, dfc=None, dre=None):
    caminho = tmp_path / "dfp_2025.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr("dfp_cia_aberta_DFC_MI_con_2025.csv", _csv(dfc or []))
        for metodo, tipo in (("MI", "ind"), ("MD", "con"), ("MD", "ind")):
            arquivo.writestr(f"dfp_cia_aberta_DFC_{metodo}_{tipo}_2025.csv", _csv([]))
        for tipo in ("con", "ind"):
            linhas = (dre or []) if tipo == "con" else []
            arquivo.writestr(f"dfp_cia_aberta_DRE_{tipo}_2025.csv", _csv(linhas))
    return caminho


def _usar_zip(monkeypatch, caminho):
    monkeypatch.setattr(cvm, "_baixar_zip_ano", lambda *args, **kwargs: caminho)


# --- so_a_maior_versao ---


def test_so_a_maior_versao_descarta_as_anteriores_na_mesma_empresa_e_data():
    linhas = [_linha(1, "6.01", "a", 1), _linha(2, "6.01", "a", 2), _linha(3, "6.01", "a", 3)]

    assert [linha["VL_CONTA"] for linha in so_a_maior_versao(linhas)] == ["3"]


def test_so_a_maior_versao_nao_depende_da_ordem_das_linhas():
    linhas = [_linha(2, "6.01", "a", 2), _linha(1, "6.01", "a", 1), _linha(2, "6.02", "b", 9)]

    assert [linha["VL_CONTA"] for linha in so_a_maior_versao(linhas)] == ["2", "9"]


def test_so_a_maior_versao_trata_cada_empresa_e_cada_data_por_si():
    linhas = [
        _linha(1, "6.01", "a", 10),
        _linha(2, "6.01", "a", 20),
        _linha(3, "6.01", "a", 30, cnpj=OUTRO_CNPJ),
        _linha(1, "6.01", "a", 40, dt_refer="2024-12-31"),
    ]

    valores = sorted(linha["VL_CONTA"] for linha in so_a_maior_versao(linhas))

    assert valores == ["20", "30", "40"]


def test_so_a_maior_versao_normaliza_o_cnpj_ao_agrupar():
    linhas = [
        _linha(1, "6.01", "a", 1, cnpj="00.000.000/0004-00"),
        _linha(2, "6.01", "a", 2, cnpj="00000000000400"),
    ]

    assert [linha["VL_CONTA"] for linha in so_a_maior_versao(linhas)] == ["2"]


def test_so_a_maior_versao_sem_a_coluna_ou_com_valor_invalido_conta_como_versao_zero():
    sem_versao = {k: v for k, v in _linha(1, "6.01", "a", 1).items() if k != "VERSAO"}
    invalida = _linha("x", "6.01", "a", 2)
    com_versao = _linha(1, "6.01", "a", 3)

    assert so_a_maior_versao([sem_versao, invalida, com_versao]) == [com_versao]


def test_so_a_maior_versao_de_lista_vazia():
    assert so_a_maior_versao([]) == []


# --- DFC: fluxo, capex, juros e risco sacado ---


@pytest.mark.parametrize("ordem_no_arquivo", ["v1_primeiro", "v2_primeiro"])
def test_fluxo_usa_so_a_versao_mais_recente_da_dfc(tmp_path, monkeypatch, ordem_no_arquivo):
    linhas = V1 + V2 if ordem_no_arquivo == "v1_primeiro" else V2 + V1
    _usar_zip(monkeypatch, _zip(tmp_path, dfc=linhas))

    r = cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path)

    assert (r["cfo_atual"], r["cfi_atual"], r["fcf_atual"]) == (200.0, -20.0, 180.0)
    assert r["fcf_anterior"] == 55.0


@pytest.mark.parametrize("ordem_no_arquivo", ["v1_primeiro", "v2_primeiro"])
def test_capex_juros_e_risco_sacado_nao_somam_linhas_de_duas_versoes(
    tmp_path, monkeypatch, ordem_no_arquivo
):
    linhas = V1 + V2 if ordem_no_arquivo == "v1_primeiro" else V2 + V1
    _usar_zip(monkeypatch, _zip(tmp_path, dfc=linhas))

    r = cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path)

    assert r["capex_atual"]["valor"] == 15.0
    assert len(r["capex_atual"]["linhas"]) == 1
    assert r["juros_pagos_atual"]["valor"] == 9.0
    assert r["risco_sacado_atual"]["valor"] == -12.0


def test_dfc_com_uma_so_versao_nao_muda(tmp_path, monkeypatch):
    _usar_zip(monkeypatch, _zip(tmp_path, dfc=V2))

    r = cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path)

    assert r["fcf_atual"] == 180.0
    assert r["capex_atual"]["valor"] == 15.0


def test_versao_antiga_de_outra_empresa_nao_interfere(tmp_path, monkeypatch):
    outra = [dict(linha, CNPJ_CIA=OUTRO_CNPJ, VERSAO="9") for linha in V1]
    _usar_zip(monkeypatch, _zip(tmp_path, dfc=V1 + outra))

    r = cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path)

    assert r["fcf_atual"] == 90.0


# --- DRE: lucro líquido e receita ---


def _dre_da_versao(versao, receita, lucro):
    return [
        _linha(versao, "3.01", "Receita de Venda de Bens e/ou Serviços", receita),
        _linha(versao, "3.11", "Lucro/Prejuízo Consolidado do Período", lucro),
        _linha(versao, "3.99", "Lucro por Ação", 1),
    ]


@pytest.mark.parametrize("v1_primeiro", [True, False])
def test_lucro_liquido_usa_so_a_versao_mais_recente_da_dre(tmp_path, monkeypatch, v1_primeiro):
    v1, v2 = _dre_da_versao(1, 1000, 50), _dre_da_versao(2, 1200, 80)
    _usar_zip(monkeypatch, _zip(tmp_path, dre=v1 + v2 if v1_primeiro else v2 + v1))

    r = cvm.obter_lucro_liquido(CNPJ, 2025, diretorio_cache=tmp_path)

    assert r["lucro_liquido_atual"] == 80.0


def test_receita_vem_da_versao_mais_recente_da_dre_mesmo_com_a_dfc_em_versao_anterior(
    tmp_path, monkeypatch
):
    dre = _dre_da_versao(1, 1000, 50) + _dre_da_versao(2, 1200, 80)
    _usar_zip(monkeypatch, _zip(tmp_path, dfc=V1, dre=dre))

    r = cvm.obter_fluxo_caixa_livre(CNPJ, 2025, diretorio_cache=tmp_path)

    assert r["fcf_atual"] == 90.0
    assert r["receita_atual"]["valor"] == 1200.0
    assert r["receita_atual"]["versao"] == 2
