"""Cartões do topo do Simulador: valor investido, valor justo da carteira, potencial e concentração
(números de `carteira.resumir_carteira`)."""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.paginas.carteira import _html_kpis_carteira
from avaliador_b3.carteira import resumir_carteira
from avaliador_b3.config import TITULO_PAGINA_CARTEIRA
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina, adicionar_a_carteira


def _tabela() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA3", "BBB4", "CCC3", "DDD3", "EEE3"],
            "preco_atual": [10.0, 20.0, 5.0, None, 8.0],
            "valor_combinado": [15.0, 10.0, None, 9.0, 8.0],
            "segmento_setorial": ["Bancos", "Bancos", "Energia Elétrica", "Bancos", None],
        }
    )


def test_resumo_soma_quantidade_vezes_preco_e_vezes_valor_combinado():
    resumo = resumir_carteira(_tabela(), {"AAA3": 100, "BBB4": 50})

    assert resumo["investido_total"] == pytest.approx(100 * 10 + 50 * 20)
    assert resumo["investido_com_combinado"] == pytest.approx(2000.0)
    assert resumo["valor_justo"] == pytest.approx(100 * 15 + 50 * 10)
    assert resumo["potencial_percentual"] == pytest.approx((2000 / 2000 - 1) * 100)
    assert resumo["diferenca_reais"] == pytest.approx(0.0)
    assert resumo["quantidade_posicoes"] == 2 and resumo["quantidade_sem_combinado"] == 0


def test_potencial_compara_so_o_que_tem_valor_combinado():
    resumo = resumir_carteira(_tabela(), {"AAA3": 100, "CCC3": 200})

    # CCC3 (sem valor combinado) conta no investido, mas fica fora do valor justo e do potencial.
    assert resumo["investido_total"] == pytest.approx(1000 + 1000)
    assert resumo["investido_com_combinado"] == pytest.approx(1000.0)
    assert resumo["valor_justo"] == pytest.approx(1500.0)
    assert resumo["potencial_percentual"] == pytest.approx(50.0)
    assert resumo["diferenca_reais"] == pytest.approx(500.0)
    assert resumo["quantidade_sem_combinado"] == 1
    assert resumo["investido_sem_combinado"] == pytest.approx(1000.0)


def test_posicao_sem_preco_nao_conta_nada_e_vira_sem_combinado():
    resumo = resumir_carteira(_tabela(), {"DDD3": 10, "AAA3": 10})

    assert resumo["investido_total"] == pytest.approx(100.0)
    assert resumo["quantidade_sem_combinado"] == 1
    assert resumo["valor_justo"] == pytest.approx(150.0)


def test_sem_nenhuma_posicao_com_valor_combinado_nao_ha_potencial():
    resumo = resumir_carteira(_tabela(), {"CCC3": 10})

    assert resumo["potencial_percentual"] is None
    assert resumo["valor_justo"] == 0.0
    assert resumo["investido_total"] == pytest.approx(50.0)


def test_concentracao_e_o_peso_do_maior_setor_no_dinheiro_alocado():
    resumo = resumir_carteira(_tabela(), {"AAA3": 100, "BBB4": 50, "CCC3": 200, "EEE3": 10})

    # Bancos 1.000 + 1.000 = 2.000; Energia 1.000; EEE3 sem setor fica fora do cálculo do peso.
    assert resumo["setor_de_maior_peso"] == "Bancos"
    assert resumo["peso_do_maior_setor_percentual"] == pytest.approx(2000 / 3000 * 100)


def test_sem_setor_no_screener_nao_ha_concentracao():
    sem_setor = _tabela().drop(columns="segmento_setorial")

    resumo = resumir_carteira(sem_setor, {"AAA3": 10})

    assert resumo["setor_de_maior_peso"] is None
    assert resumo["peso_do_maior_setor_percentual"] is None


def _resumo(**mudancas) -> dict:
    return resumir_carteira(_tabela(), {"AAA3": 100, "BBB4": 50}) | mudancas


def test_cartoes_formatam_os_numeros_e_as_cores():
    html = _html_kpis_carteira(resumir_carteira(_tabela(), {"AAA3": 100, "CCC3": 200}))

    assert 'ab-valor ab-cor-texto">R$ 2.000,00<' in html
    assert "1 sem valor combinado (R$ 1.000,00)" in html
    assert 'ab-valor ab-cor-principal">R$ 1.500,00<' in html
    assert "sobre R$ 1.000,00 com valor combinado" in html
    assert 'ab-valor ab-cor-positivo">+50,0%<' in html
    assert 'ab-linha ab-cor-positivo">+R$ 500,00<' in html
    # Bancos 1.000 e Energia 1.000: 50% não passa de 50%, então sem amarelo.
    assert 'ab-valor ab-cor-texto">50,0%<' in html
    assert ">Bancos<" in html or "Bancos" in html


def test_potencial_negativo_fica_rosa_com_a_diferenca_em_reais():
    html = _html_kpis_carteira(resumir_carteira(_tabela(), {"BBB4": 100}))

    assert 'ab-valor ab-cor-negativo">-50,0%<' in html
    assert 'ab-linha ab-cor-negativo">R$ -1.000,00<' in html


def test_concentracao_acima_de_cinquenta_por_cento_fica_amarela():
    html = _html_kpis_carteira(resumir_carteira(_tabela(), {"AAA3": 100, "CCC3": 10}))

    assert 'ab-valor ab-cor-alerta">95,2%<' in html


def test_sem_valor_combinado_nenhum_os_cartoes_de_valor_justo_e_potencial_mostram_traco():
    html = _html_kpis_carteira(resumir_carteira(_tabela(), {"CCC3": 10}))

    assert html.count('ab-valor ab-cor-secundario">—<') == 2
    assert "Nenhum método se aplica a esta empresa" in html


def test_sem_setor_o_cartao_de_concentracao_avisa_ate_a_proxima_atualizacao():
    html = _html_kpis_carteira(
        resumir_carteira(_tabela().drop(columns="segmento_setorial"), {"AAA3": 1})
    )

    assert 'ab-valor ab-cor-secundario">—<' in html
    assert "Setor disponível a partir da próxima atualização do screener" in html


def test_cartoes_trazem_a_explicacao_no_ponto_de_interrogacao():
    html = _html_kpis_carteira(_resumo())

    assert html.count('class="ab-ajuda"') == 3  # valor justo, potencial e concentração
    assert "Soma de quantidade × valor combinado" in html


def _abrir_simulador(monkeypatch, tmp_path, com_setor: bool) -> AppTest:
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: app._universo_falso(),
    )
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)
    base = {c: None for c in COLUNAS_RESULTADO} | {
        "sucesso": True,
        "erro": "",
        "aviso_desconto_extremo": "",
        "metodos_utilizados": "graham",
    }
    linhas = [
        base
        | {"ticker": "AAA3", "preco_atual": 10.0, "valor_combinado": 15.0}
        | {"graham_valor_justo": 15.0, "segmento_setorial": "Bancos" if com_setor else None},
        base
        | {"ticker": "BBB4", "preco_atual": 20.0, "valor_combinado": 10.0}
        | {
            "graham_valor_justo": 10.0,
            "segmento_setorial": "Energia Elétrica" if com_setor else None,
        },
        base | {"ticker": "CCC3", "preco_atual": 5.0, "metodos_utilizados": ""},
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    assert not at.exception
    return at


def test_pagina_mostra_os_quatro_cartoes_com_os_numeros_da_carteira(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path, com_setor=True)
    assert app._kpi_por_rotulo(at, "Valor investido") is None  # carteira vazia: sem cartões

    adicionar_a_carteira(at, "AAA3", 100)
    adicionar_a_carteira(at, "BBB4", 50)
    adicionar_a_carteira(at, "CCC3", 40)

    investido = app._kpi_por_rotulo(at, "Valor investido")
    assert investido["valor"] == "R$ 2.200,00"
    assert investido["linha"] == "1 sem valor combinado (R$ 200,00)"
    valor_justo = app._kpi_por_rotulo(at, "Valor justo da carteira")
    assert (valor_justo["valor"], valor_justo["classe"]) == ("R$ 2.000,00", "ab-cor-principal")
    potencial = app._kpi_por_rotulo(at, "Potencial da carteira")
    assert (potencial["valor"], potencial["classe"]) == ("0,0%", "ab-cor-texto")  # zero: sem cor
    concentracao = app._kpi_por_rotulo(at, "Concentração")
    assert concentracao["valor"] == "50,0%"  # Bancos 1.000 de 2.000 (CCC3 sem setor)
    assert concentracao["classe"] == "ab-cor-texto"


def test_pagina_sem_setor_no_screener_antigo_mostra_o_aviso_na_concentracao(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path, com_setor=False)

    adicionar_a_carteira(at, "AAA3", 100)

    concentracao = app._kpi_por_rotulo(at, "Concentração")
    assert concentracao["valor"] == "—"
    assert concentracao["linha"] == "Setor disponível a partir da próxima atualização do screener"


@pytest.mark.parametrize(
    ("peso", "texto", "classe"),
    [
        (49.6, "49,6%", "ab-cor-texto"),
        (50.4, "50,4%", "ab-cor-alerta"),
        (50.0, "50,0%", "ab-cor-texto"),
    ],
)
def test_concentracao_mostra_uma_casa_para_o_corte_de_cinquenta_nao_parecer_errado(
    peso, texto, classe
):
    resumo = _resumo(setor_de_maior_peso="Bancos", peso_do_maior_setor_percentual=peso)

    assert f'ab-valor {classe}">{texto}<' in _html_kpis_carteira(resumo)


def test_cartao_do_valor_investido_usa_singular_com_uma_posicao_e_plural_com_mais():
    uma = _html_kpis_carteira(resumir_carteira(_tabela(), {"AAA3": 100}))
    duas = _html_kpis_carteira(resumir_carteira(_tabela(), {"AAA3": 100, "BBB4": 50}))

    assert "1 posição<" in uma and "1 posições" not in uma
    assert "2 posições<" in duas
