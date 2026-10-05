import json
import zipfile
from pathlib import Path

import pytest
import requests

from avaliador_b3.config import UNITS_COMPOSICAO, VERSAO_SCHEMA_CVM_BALANCO
from avaliador_b3.ingest import balanco_cvm

CNPJ = "12.345.678/0001-90"
CNPJ_OUTRA = "98.765.432/0001-10"
CABECALHO_BPP = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;"
    "CD_CONTA;DS_CONTA;VL_CONTA"
)
CABECALHO_CAPITAL = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;"
    "QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO"
)


def _linha_bpp(codigo, descricao, valor, data="2026-06-30", versao=1, cnpj=CNPJ, ordem="ÚLTIMO"):
    return f"{cnpj};{data};{versao};EMPRESA;MIL;{ordem};{data};{codigo};{descricao};{valor}"


def _linha_capital(on, pn, tesouro, data="2026-06-30", versao=1, cnpj=CNPJ):
    return f"{cnpj};{data};{versao};EMPRESA;{on};{pn};{on + pn};0;0;{tesouro}"


def _zip(tmp_path, documento, ano, linhas_bpp, linhas_capital):
    caminho = tmp_path / f"{documento}_{ano}.zip"
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr(
            f"{documento}_cia_aberta_BPP_con_{ano}.csv",
            "\n".join([CABECALHO_BPP, *linhas_bpp]).encode("iso-8859-1"),
        )
        arquivo.writestr(
            f"{documento}_cia_aberta_composicao_capital_{ano}.csv",
            "\n".join([CABECALHO_CAPITAL, *linhas_capital]).encode("iso-8859-1"),
        )
    return caminho


@pytest.fixture
def baixados(monkeypatch):
    """Registra os documentos pedidos a `_baixar_zip_ano` e serve o zip configurado."""
    estado = {"zips": {}, "pedidos": []}

    def baixar(ano, diretorio_cache, forcar_atualizacao, hoje=None, documento="dfp"):
        estado["pedidos"].append((documento, ano))
        return estado["zips"][(documento, ano)]

    monkeypatch.setattr(balanco_cvm, "_baixar_zip_ano", baixar)
    return estado


BALANCO_BASE = [
    _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 31910),
    _linha_bpp("2.03.01", "Capital Social Realizado", 10000),
    _linha_bpp("2.03.09", "Participação dos Acionistas Não Controladores", 26942),
]


def test_le_o_balanco_de_30_06_no_itr(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(
        tmp_path, "itr", 2026, BALANCO_BASE, [_linha_capital(900, 100, 50)]
    )

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert baixados["pedidos"] == [("itr", 2026)]
    assert r["disponivel"] is True
    assert r["data_base"] == "2026-06-30"
    assert r["fonte"] == "ITR de 30/06/2026 (versão 1)"
    assert r["patrimonio_liquido_total"] == pytest.approx(31910 * 1000.0)
    assert r["nao_controladores"] == pytest.approx(26942 * 1000.0)
    assert r["capital"] == {
        "ordinarias": 900.0,
        "preferenciais": 100.0,
        "integralizado": 1000.0,
        "tesouraria": 50.0,
        "versao": 1,
    }


@pytest.mark.parametrize("data_base", ["2026-03-31", "2026-09-30"])
def test_outros_fins_de_trimestre_tambem_vem_do_itr(tmp_path, baixados, data_base):
    linhas = [_linha_bpp("2.03", "Patrimônio Líquido Consolidado", 500, data=data_base)]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, data_base, diretorio_cache=tmp_path)

    assert baixados["pedidos"] == [("itr", 2026)]
    assert r["patrimonio_liquido_total"] == pytest.approx(500_000.0)


def test_le_o_balanco_de_31_12_no_dfp(tmp_path, baixados):
    linhas = [_linha_bpp("2.03", "Patrimônio Líquido Consolidado", 800, data="2025-12-31")]
    baixados["zips"][("dfp", 2025)] = _zip(
        tmp_path, "dfp", 2025, linhas, [_linha_capital(10, 0, 0, data="2025-12-31")]
    )

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2025-12-31", diretorio_cache=tmp_path)

    assert baixados["pedidos"] == [("dfp", 2025)]
    assert r["fonte"] == "DFP de 31/12/2025 (versão 1)"
    assert r["patrimonio_liquido_total"] == pytest.approx(800_000.0)


def test_usa_a_versao_mais_recente_do_documento(tmp_path, baixados):
    linhas = [
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 100, versao=1),
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 200, versao=2),
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 999, cnpj=CNPJ_OUTRA, versao=3),
    ]
    capital = [_linha_capital(10, 0, 1, versao=1), _linha_capital(20, 0, 2, versao=2)]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, capital)

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["fonte"] == "ITR de 30/06/2026 (versão 2)"
    assert r["patrimonio_liquido_total"] == pytest.approx(200_000.0)
    assert r["capital"]["integralizado"] == 20.0


def test_ignora_o_periodo_penultimo_do_mesmo_documento(tmp_path, baixados):
    linhas = [
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 100),
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 777, ordem="PENÚLTIMO"),
    ]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["patrimonio_liquido_total"] == pytest.approx(100_000.0)


def test_data_que_a_empresa_nao_tem_na_cvm_fica_indisponivel_sem_cair_para_outra(
    tmp_path, baixados
):
    # Só há 31/03; a data-base pedida é 30/06.
    linhas = [_linha_bpp("2.03", "Patrimônio Líquido Consolidado", 100, data="2026-03-31")]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["disponivel"] is False
    assert r["motivo"] == "A empresa não tem balanço consolidado de 30/06/2026 no ITR da CVM."
    assert "patrimonio_liquido_total" not in r


def test_sem_balanco_consolidado_a_composicao_do_capital_continua_disponivel(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, [], [_linha_capital(900, 0, 0)])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["disponivel"] is False
    assert r["capital"]["integralizado"] == 900.0
    assert (
        not list((tmp_path / "cvm").glob("balanco_*.json")) if (tmp_path / "cvm").exists() else True
    )


def test_data_fora_de_fim_de_trimestre_e_data_ausente_ficam_indisponiveis(tmp_path):
    fora = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-05-15", diretorio_cache=tmp_path)
    ausente = balanco_cvm.obter_balanco_cvm(CNPJ, None, diretorio_cache=tmp_path)

    assert fora["disponivel"] is False
    assert "não é um fim de trimestre" in fora["motivo"]
    assert ausente["disponivel"] is False
    assert ausente["motivo"] == "A data-base do balanço não está disponível."


def test_arquivo_ainda_nao_publicado_vira_indisponivel(tmp_path, monkeypatch):
    def baixar(*args, **kwargs):
        resposta = type("Resposta", (), {"status_code": 404})()
        raise requests.HTTPError("404", response=resposta)

    monkeypatch.setattr(balanco_cvm, "_baixar_zip_ano", baixar)

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2027-03-31", diretorio_cache=tmp_path)

    assert r["disponivel"] is False
    assert r["motivo"] == "O arquivo ITR da CVM de 2027 ainda não foi publicado."


def test_erro_de_rede_ao_baixar_propaga(tmp_path, monkeypatch):
    def baixar(*args, **kwargs):
        raise requests.ConnectionError("fora do ar")

    monkeypatch.setattr(balanco_cvm, "_baixar_zip_ano", baixar)

    with pytest.raises(requests.ConnectionError):
        balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)


def test_empresa_sem_nao_controladores_tem_zero(tmp_path, baixados):
    linhas = [
        _linha_bpp("2.03", "Patrimônio Líquido Consolidado", 7291),
        _linha_bpp("2.03.01", "Capital Social Realizado", 1000),
    ]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["nao_controladores"] == 0.0


def test_arrendamento_dentro_da_divida_do_fundamentus_nao_entra_no_passivo_de_fora(
    tmp_path, baixados
):
    linhas = [
        _linha_bpp("2.01.04", "Empréstimos e Financiamentos", 1000),
        _linha_bpp("2.01.04.03", "Financiamento por Arrendamento", 300),
        _linha_bpp("2.02.01", "Empréstimos e Financiamentos", 5000),
        _linha_bpp("2.02.01.04", "Financiamento por Arrendamento", 4000),
    ]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["arrendamento_na_divida"] == pytest.approx(4300 * 1000.0)
    assert r["arrendamento_fora_da_divida"] == 0.0
    assert r["linhas_arrendamento_fora"] == []


def test_arrendamento_fora_da_divida_soma_circulante_e_nao_circulante(tmp_path, baixados):
    linhas = [
        _linha_bpp("2.01.04", "Empréstimos e Financiamentos", 1000),
        _linha_bpp("2.01.05.02.05", "Arrendamentos a Pagar", 1025),
        _linha_bpp("2.02.02.02.04", "Arrendamentos a pagar", 4115),
        _linha_bpp("2.01.05", "Outras Obrigações", 9000),
        _linha_bpp("2.03.01", "Locação de ativos", 55),
    ]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["arrendamento_fora_da_divida"] == pytest.approx((1025 + 4115) * 1000.0)
    assert [c["codigo"] for c in r["linhas_arrendamento_fora"]] == [
        "2.01.05.02.05",
        "2.02.02.02.04",
    ]
    assert r["arrendamento_na_divida"] == 0.0


def test_arrendamento_com_linha_pai_e_filha_nao_conta_duas_vezes(tmp_path, baixados):
    linhas = [
        _linha_bpp("2.02.02.02", "Arrendamentos a pagar", 600),
        _linha_bpp("2.02.02.02.01", "Arrendamentos a pagar - imóveis", 400),
    ]
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, linhas, [])

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["arrendamento_fora_da_divida"] == pytest.approx(600 * 1000.0)


def test_segunda_chamada_usa_o_cache_sem_reabrir_o_zip(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, BALANCO_BASE, [])

    primeira = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)
    segunda = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert segunda == primeira
    assert len(baixados["pedidos"]) == 1
    assert (
        tmp_path
        / "cvm"
        / f"balanco_{CNPJ.replace('.', '').replace('/', '').replace('-', '')}_2026-06-30.json"
    ).exists()


def test_cache_de_outra_versao_do_schema_e_ignorado(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(tmp_path, "itr", 2026, BALANCO_BASE, [])
    caminho = tmp_path / "cvm" / "balanco_12345678000190_2026-06-30.json"
    caminho.parent.mkdir(parents=True)
    caminho.write_text(
        json.dumps(
            {"versao_schema": VERSAO_SCHEMA_CVM_BALANCO - 1, "resultado": {"disponivel": True}}
        ),
        encoding="utf-8",
    )

    r = balanco_cvm.obter_balanco_cvm(CNPJ, "2026-06-30", diretorio_cache=tmp_path)

    assert r["patrimonio_liquido_total"] == pytest.approx(31910 * 1000.0)
    assert len(baixados["pedidos"]) == 1


# --- número de ações em circulação -------------------------------------------


def _capital(integralizado, tesouraria):
    return {
        "ordinarias": integralizado,
        "preferenciais": 0.0,
        "integralizado": integralizado,
        "tesouraria": tesouraria,
        "versao": 1,
    }


def _acoes(capital, fundamentus, fator=1):
    return balanco_cvm.calcular_acoes_em_circulacao(
        capital, fundamentus, fator, "2026-06-30", "ITR"
    )


def test_acoes_em_circulacao_sao_o_integralizado_menos_a_tesouraria():
    r = _acoes(_capital(1000e6, 40e6), 1000e6)

    assert r["acoes"] == pytest.approx(960e6)
    assert r["motivo"] is None
    # O Fundamentus inclui a tesouraria (4%): é explicado por ela, sem aviso.
    assert r["aviso_divergencia"] is None


def test_units_dividem_pelo_fator_de_acoes_por_cotacao():
    r = _acoes(_capital(1500e6, 30e6), 500e6, fator=3)

    assert r["acoes"] == pytest.approx(1470e6 / 3)


def test_composicao_em_milhares_e_normalizada_pela_razao_com_o_fundamentus():
    # A CVM informa 1.000.000 (milhares) e o Fundamentus 1.000.000.000 ações.
    r = _acoes(_capital(1_000_000.0, 10_000.0), 1_000_000_000.0)

    assert r["escala_em_milhares"] is True
    assert r["acoes"] == pytest.approx(990_000_000.0)
    assert r["aviso_divergencia"] is None


def test_tesouraria_acima_do_limite_deixa_o_numero_indisponivel():
    # Caso TEND3: capital em milhares e tesouraria em ações (65.148 virou 65 milhões).
    r = _acoes(_capital(122_578.0, 65_148.0), 122_578_000.0)

    assert r["acoes"] is None
    assert r["motivo"].startswith("Tesouraria de 53% do capital")
    assert "limite de 20%" in r["motivo"]


def test_integralizado_ja_liquido_de_tesouraria_nao_desconta_duas_vezes():
    # Caso VALE3: integralizado 4.255,763 + tesouraria 183,397 = 4.439,160 = Fundamentus.
    r = _acoes(_capital(4255.763e6, 183.397e6), 4439.160e6)

    assert r["integralizado_ja_liquido"] is True
    assert r["acoes"] == pytest.approx(4255.763e6)
    assert r["aviso_divergencia"] is None


def test_tesouraria_menor_que_a_tolerancia_segue_o_padrao_de_subtrair():
    r = _acoes(_capital(1000e6, 2e6), 1000e6)

    assert r["integralizado_ja_liquido"] is False
    assert r["acoes"] == pytest.approx(998e6)


def test_divergencia_acima_do_limite_traz_aviso_com_as_duas_contagens():
    # Caso EGIE3: a oferta de julho/2026 já está no Fundamentus, mas não no balanço de 30/06.
    r = _acoes(_capital(1142.299e6, 0.0), 1416.381e6)

    assert r["acoes"] == pytest.approx(1142.299e6)
    assert "1.416,38 mi" in r["aviso_divergencia"]
    assert "1.142,30 mi" in r["aviso_divergencia"]
    assert "+24,0%" in r["aviso_divergencia"]
    assert "30/06/2026" in r["aviso_divergencia"]


def test_divergencia_pequena_nao_traz_aviso():
    r = _acoes(_capital(2943.22e6, 75.879e6), 2828.64e6)  # AXIA3: -1,3%

    assert r["acoes"] == pytest.approx(2867.341e6)
    assert r["aviso_divergencia"] is None


def test_divergencia_implausivel_deixa_o_numero_indisponivel():
    # Caso IGTI11: a CVM conta ações físicas; a unit é medida pelo peso econômico (fator 7).
    r = _acoes(_capital(1206.361e6, 1.794e6), 296.7286e6, fator=7)

    assert r["acoes"] is None
    assert r["descartada_por_divergencia"] is True
    assert r["motivo"] == (
        "O número de ações da CVM (172,08 mi) difere +72% do do Fundamentus (296,73 mi); "
        "mantido o do Fundamentus. Em units, a diferença pode vir de a CVM contar ações "
        "físicas enquanto a unit é medida pelo peso econômico das ações que a formam."
    )
    assert "erro" not in r["motivo"]


def test_divergencia_implausivel_fora_de_unit_nao_cita_units():
    r = _acoes(_capital(1000e6, 0.0), 3000e6)

    assert r["acoes"] is None
    assert r["motivo"] == (
        "O número de ações da CVM (1.000,00 mi) difere +200% do do Fundamentus (3.000,00 mi); "
        "mantido o do Fundamentus."
    )


def test_sem_composicao_do_capital_o_numero_fica_indisponivel_com_motivo():
    r = _acoes(None, 1000e6)

    assert r["acoes"] is None
    assert r["motivo"] == "A empresa não tem composição do capital de 30/06/2026 no ITR da CVM."


def test_sem_numero_do_fundamentus_nao_da_para_validar_a_escala():
    r = _acoes(_capital(1000e6, 0.0), None)

    assert r["acoes"] is None
    assert "sem ele não dá para validar a escala" in r["motivo"]


def test_leitura_unica_junta_balanco_e_acoes(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(
        tmp_path, "itr", 2026, BALANCO_BASE, [_linha_capital(1_000_000_000, 0, 40_000_000)]
    )

    r = balanco_cvm.obter_leitura_balanco(
        CNPJ, "2026-06-30", 1_000_000_000.0, 1, diretorio_cache=tmp_path
    )

    assert r["disponivel"] is True
    assert r["nao_controladores"] == pytest.approx(26942 * 1000.0)
    assert r["acoes_em_circulacao"] == pytest.approx(960_000_000.0)
    assert r["motivo_acoes"] is None


def test_leitura_unica_sem_balanco_consolidado_ainda_traz_as_acoes(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(
        tmp_path, "itr", 2026, [], [_linha_capital(1_000_000_000, 0, 10_000_000)]
    )

    r = balanco_cvm.obter_leitura_balanco(
        CNPJ, "2026-06-30", 1_000_000_000.0, 1, diretorio_cache=tmp_path
    )

    assert r["disponivel"] is False
    assert r["acoes_em_circulacao"] == pytest.approx(990_000_000.0)


def test_leitura_unica_de_data_fora_do_trimestre_nao_traz_acoes(tmp_path):
    r = balanco_cvm.obter_leitura_balanco(
        CNPJ, "2026-05-15", 1_000_000_000.0, 1, diretorio_cache=Path(tmp_path)
    )

    assert r["disponivel"] is False
    assert r["acoes_em_circulacao"] is None
    assert "não é um fim de trimestre" in r["motivo_acoes"]


# --- Units: conversão da composição da CVM por peso econômico ---------------------------------

IGTI11 = UNITS_COMPOSICAO["IGTI11"]
KLBN11 = UNITS_COMPOSICAO["KLBN11"]


def _capital_on_pn(on, pn, tesouraria):
    return {
        "ordinarias": on,
        "preferenciais": pn,
        "integralizado": on + pn,
        "tesouraria": tesouraria,
        "versao": 1,
    }


def _acoes_unit(capital, fundamentus, fator, composicao):
    return balanco_cvm.calcular_acoes_em_circulacao(
        capital, fundamentus, fator, "2026-06-30", "ITR", composicao_unit=composicao
    )


def test_igti11_converte_a_cvm_por_peso_economico_e_nao_cai_na_trava():
    # 770,99 mi ON + 435,37 mi PN; a PN vale 3 ON e a unit tem 1 ON + 2 PN (7 equivalentes).
    capital = _capital_on_pn(770.992429e6, 435.368756e6, 1.794e6)

    r = _acoes_unit(capital, 296.7286e6, 7, IGTI11)

    esperado = (770.992429e6 + 3 * 435.368756e6 - 1.794e6) / 7
    assert r["acoes"] == pytest.approx(esperado)
    assert r["acoes"] == pytest.approx(296.7286e6, rel=0.003)
    assert r["motivo"] is None
    assert r["aviso_divergencia"] is None
    assert "descartada_por_divergencia" not in r


def test_igti11_sem_a_tabela_continua_caindo_na_trava_de_50_por_cento():
    capital = _capital_on_pn(770.992429e6, 435.368756e6, 1.794e6)

    r = _acoes_unit(capital, 296.7286e6, 7, None)

    assert r["acoes"] is None
    assert r["descartada_por_divergencia"] is True


def test_unit_de_peso_um_converte_igual_a_conversao_fisica():
    # KLBN11: 1 ON + 4 PN com os mesmos direitos; o resultado não muda com a tabela.
    capital = _capital_on_pn(2312.8e6, 3928.7e6, 88.58e6)

    sem_tabela = _acoes_unit(capital, 1248.3e6, 5, None)
    com_tabela = _acoes_unit(capital, 1248.3e6, 5, KLBN11)

    assert com_tabela["acoes"] == pytest.approx(sem_tabela["acoes"])
    assert com_tabela["aviso_divergencia"] == sem_tabela["aviso_divergencia"]


def test_unit_com_composicao_em_milhares_e_pesos_diferentes():
    # Composição em milhares (como SANB11 e TAEE11): 1.000.000 ON + 500.000 PN com PN = 3 ON,
    # unit de 1 ON + 1 PN (4 equivalentes): (1.000.000 + 3 x 500.000) x 1.000 / 4.
    composicao = {"ordinarias": 1, "preferenciais": 1, "peso_preferencial": 3.0}
    capital = _capital_on_pn(1_000_000.0, 500_000.0, 0.0)

    r = _acoes_unit(capital, 625_000_000.0, 4, composicao)

    assert r["escala_em_milhares"] is True
    assert r["acoes"] == pytest.approx(625_000_000.0)


def test_composicao_sem_ordinarias_nem_preferenciais_cai_na_conversao_fisica():
    capital = {"ordinarias": 0.0, "preferenciais": 0.0, "integralizado": 1500e6, "tesouraria": 0.0}

    r = _acoes_unit(capital, 500e6, 3, KLBN11)

    assert r["acoes"] == pytest.approx(500e6)


def test_tabela_de_units_tem_o_fator_de_cada_unit_do_ibovespa():
    fatores = {
        ticker: balanco_cvm._ordinarias_equivalentes_por_unit(composicao)
        for ticker, composicao in UNITS_COMPOSICAO.items()
    }

    assert fatores == {
        "IGTI11": 7.0,
        "KLBN11": 5.0,
        "TAEE11": 3.0,
        "ENGI11": 5.0,
        "SANB11": 2.0,
        "BPAC11": 3.0,
    }
    assert all(c["fonte"] and c["data"] for c in UNITS_COMPOSICAO.values())
    assert all("HIPÓTESE" in UNITS_COMPOSICAO[t]["fonte"] for t in ("SANB11", "BPAC11"))


@pytest.mark.parametrize(
    ("ticker", "fator"), [("IGTI11", 7), ("KLBN11", 5), ("PETR4", 1), ("PETR4", None), (None, 7)]
)
def test_aviso_de_unit_nao_aparece_quando_o_fator_bate_ou_nao_e_unit(ticker, fator):
    assert balanco_cvm.montar_aviso_unit(ticker, fator) is None


def test_aviso_de_unit_quando_o_fator_do_fundamentus_nao_bate_com_a_tabela():
    aviso = balanco_cvm.montar_aviso_unit("IGTI11", 3)

    assert aviso == (
        "O fator de unit do Fundamentus (3) não bate com a composição registrada para IGTI11 "
        "(7 ações ordinárias equivalentes por unit: 1 ordinária(s) e 2 preferencial(is), cada "
        "preferencial valendo 3 da ordinária). O valor por unit pode estar errado; confira a "
        "composição da unit."
    )


def test_aviso_de_unit_com_fator_dentro_da_tolerancia_nao_avisa():
    assert balanco_cvm.montar_aviso_unit("IGTI11", 7.2) is None  # 2,9% de diferença


def test_aviso_de_unit_fora_da_tabela():
    aviso = balanco_cvm.montar_aviso_unit("XPTO11", 3)

    assert aviso == (
        "XPTO11 é uma unit (3 ações por cotação no Fundamentus) que não está na tabela de "
        "composições do app; o número de ações da CVM foi convertido pelo fator do Fundamentus, "
        "que pode não refletir o peso econômico das ações que formam a unit."
    )


def test_leitura_unica_da_igti11_usa_a_tabela_e_nao_descarta_a_cvm(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(
        tmp_path, "itr", 2026, BALANCO_BASE, [_linha_capital(770_992_429, 435_368_756, 1_794_000)]
    )

    r = balanco_cvm.obter_leitura_balanco(
        CNPJ, "2026-06-30", 296_728_571.0, 7, diretorio_cache=tmp_path, ticker="IGTI11"
    )

    assert r["acoes_em_circulacao"] == pytest.approx(
        (770_992_429 + 3 * 435_368_756 - 1_794_000) / 7
    )
    assert r["motivo_acoes"] is None
    assert r["aviso_unit"] is None


def test_leitura_unica_sem_ticker_mantem_a_conversao_fisica_e_avisa_nada(tmp_path, baixados):
    baixados["zips"][("itr", 2026)] = _zip(
        tmp_path, "itr", 2026, BALANCO_BASE, [_linha_capital(770_992_429, 435_368_756, 1_794_000)]
    )

    r = balanco_cvm.obter_leitura_balanco(
        CNPJ, "2026-06-30", 296_728_571.0, 7, diretorio_cache=tmp_path
    )

    assert r["acoes_em_circulacao"] is None
    assert r["aviso_unit"] is None
