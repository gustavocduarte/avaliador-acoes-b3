"""Painéis "Cenários" e "Contribuição" do Simulador, e a página sem a informação repetida (o bloco
"Total da carteira" e a seção do potencial com a frase-resumo saíram)."""

import json
import re
from html import unescape

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.paginas.carteira import (
    _ajuda_cenarios_carteira,
    _figura_contribuicao_carteira,
    _figura_faixa_cenarios,
    _html_cenarios_carteira,
)
from avaliador_b3.carteira import calcular_totais_carteira, montar_tabela_carteira
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina, adicionar_a_carteira

TOTAIS = {
    "soma_investida": 2000.0,
    "soma_investida_com_cenario": 1500.0,
    "total_pessimista": 1200.0,
    "total_base": 1800.0,
    "total_otimista": 3000.0,
    "quantidade_sem_cenario": 1,
}


def test_tres_linhas_de_cenario_com_o_base_em_destaque_e_o_potencial_colorido():
    html = _html_cenarios_carteira(TOTAIS)

    assert len(re.findall(r'<div class="ab-cenario( ab-cenario-base)?">', html)) == 3
    assert html.count("ab-cenario-base") == 1
    assert html.index("Pessimista") < html.index("Base") < html.index("Otimista")
    assert "R$ 1.200,00" in html and "R$ 1.800,00" in html and "R$ 3.000,00" in html
    assert 'ab-cenario-valor ab-cor-negativo">-20,0%<' in html  # 1.200 sobre 1.500
    assert 'ab-cenario-valor ab-cor-positivo">+20,0%<' in html  # 1.800 sobre 1.500
    assert 'ab-cenario-valor ab-cor-positivo">+100,0%<' in html


def test_potencial_dos_cenarios_ignora_o_capital_da_acao_sem_cenario():
    tabela = pd.DataFrame(
        {
            "ticker": ["AAAA4", "BBBB4"],
            "preco_atual": [40.0, 10.0],
            "valor_combinado": [50.0, None],
            "graham_valor_justo": [50.0, None],
            "bazin_preco_teto": [None, None],
            "fcd_valor_justo": [50.0, None],
        }
    )
    # R$ 400 na ação com cenário (base +25%) e R$ 1.000 na sem cenário.
    totais = calcular_totais_carteira(
        montar_tabela_carteira(tabela, {"AAAA4": 400.0, "BBBB4": 1000.0})
    )

    html = _html_cenarios_carteira(totais)

    assert totais["soma_investida"] == pytest.approx(1400.0)
    assert 'ab-cenario-valor ab-cor-positivo">+25,0%<' in html


def test_ponto_de_interrogacao_do_painel_junta_abertura_aviso_e_frase_resumo():
    ajuda = _ajuda_cenarios_carteira(TOTAIS)

    assert ajuda.startswith(config.TEXTO_ABERTURA_SIMULADOR)
    assert config.AVISO_SIMULADOR_SEM_PREVISAO in ajuda
    assert ajuda.endswith(
        "R$ 1.500,00 investidos hoje equivaleriam a entre R$ 1.200,00 (pessimista) e "
        "R$ 3.000,00 (otimista) se os preços convergissem aos valores justos, sem prazo definido."
    )
    sem_cenario = _ajuda_cenarios_carteira(TOTAIS | {"soma_investida_com_cenario": 0.0})
    assert "equivaleriam" not in sem_cenario


def test_faixa_vai_do_pessimista_ao_otimista_com_o_ponto_do_base_e_a_linha_do_investido():
    figura = _figura_faixa_cenarios(TOTAIS)

    faixa, base = figura.data
    assert list(faixa.x) == [1200.0, 3000.0]
    assert faixa.line.color == config.COR_PRINCIPAL
    assert list(base.x) == [1800.0] and base.marker.color == config.COR_PRINCIPAL
    linha = figura.layout.shapes[0]
    assert linha.x0 == 1500.0
    assert linha.line.color == config.COR_ALERTA and linha.line.dash == "dash"
    assert [a.text for a in figura.layout.annotations] == ["Investido R$ 1.500,00"]
    assert figura.layout.separators == ",."


def test_contribuicao_ordena_da_maior_para_a_menor_com_verde_e_rosa():
    tabela = pd.DataFrame(
        {
            "ticker": ["BBB4", "AAA3", "CCC3"],
            "valor_investido": [1000.0, 1000.0, 500.0],
            "projecao_base": [900.0, 1500.0, 500.0],
        }
    )

    figura = _figura_contribuicao_carteira(tabela)

    barras = figura.data[0]
    assert list(barras.y) == ["AAA3", "CCC3", "BBB4"]
    assert list(barras.x) == [500.0, 0.0, -100.0]
    assert list(barras.marker.color) == [
        config.COR_POSITIVO,
        config.COR_POSITIVO,
        config.COR_NEGATIVO,
    ]
    assert list(barras.text) == ["+R$ 500,00", "R$ 0,00", "R$ -100,00"]
    assert figura.layout.yaxis.autorange == "reversed"


def _abrir_simulador(monkeypatch, tmp_path) -> AppTest:
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: app._universo_falso(),
    )
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)
    caminho = tmp_path / "screener.csv"
    app._escrever_screener_falso_para_simulador(caminho)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, config.TITULO_PAGINA_CARTEIRA)
    assert not at.exception
    return at


def _montar_carteira(at) -> None:
    adicionar_a_carteira(at, "DOBR4", 25)  # R$ 1.000: base R$ 2.000
    adicionar_a_carteira(at, "SEMC3", 30)  # sem método aplicável
    adicionar_a_carteira(at, "NEGA4", 50)  # R$ 500: pessimista no piso, base R$ 375


def _graficos(at) -> list[dict]:
    return [json.loads(g.proto.spec) for g in at.get("plotly_chart")]


def test_pagina_nao_repete_o_total_da_carteira_nem_a_secao_do_potencial(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    _montar_carteira(at)

    assert not at.exception
    assert not [m for m in at.metric]  # os quatro st.metric do "Total da carteira" saíram
    assert [s.value for s in at.subheader] == []
    textos = [c.value for c in at.caption] + [m.value for m in at.markdown]
    assert not any("Potencial de valorização da carteira" in t for t in textos)
    assert not any("investidos hoje equivaleriam" in t for t in textos)
    # O texto de abertura só aparece na tela quando não há carteira (senão vive no "?").
    assert config.TEXTO_ABERTURA_SIMULADOR not in [c.value for c in at.caption]
    assert [e.label for e in at.expander] == [
        config.TITULO_EXPANDER_CENARIOS_POR_ACAO,
        config.TITULO_EXPANDER_SIMULADOR,
    ]


def test_pagina_mostra_os_paineis_de_cenarios_e_contribuicao(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    _montar_carteira(at)

    cenarios = next(
        unescape(h.proto.body)
        for h in at.get("html")
        if "ab-cenarios" in h.proto.body and "<style>" not in h.proto.body
    )
    # Só DOBR4 e NEGA4 têm cenário: pessimista 2.000 + 0, base 2.000 + 375, otimista 2.000 + 1.000.
    assert "R$ 2.000,00" in cenarios and "R$ 2.375,00" in cenarios and "R$ 3.000,00" in cenarios
    graficos = _graficos(at)
    # Faixa dos cenários, contribuição, rosca da composição (sem setor no CSV, não há o de setor).
    assert len(graficos) == 3
    contribuicao = next(
        g
        for g in graficos
        if g["data"][0].get("orientation") == "h" and g["data"][0]["y"][0] == "DOBR4"
    )
    assert contribuicao["data"][0]["y"] == ["DOBR4", "NEGA4"]
    assert app._valores_plotly(contribuicao["data"][0]["x"]) == [1000.0, -125.0]
    assert "Sem contribuição: SEMC3" in [c.value for c in at.caption]
    # A ação sem cenário é explicada numa legenda só, sem faixa amarela.
    assert not at.warning
    legenda = config.TEXTO_SEM_CENARIO_SINGULAR.format(tickers="SEMC3")
    assert [c.value for c in at.caption].count(legenda) == 1


def test_so_com_acao_sem_cenario_os_paineis_avisam_em_vez_de_desenhar(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    adicionar_a_carteira(at, "SEMC3", 30)

    assert not at.exception
    # Sem cenário não há faixa nem contribuição; só a rosca da composição (dinheiro alocado).
    assert [g["data"][0]["type"] for g in _graficos(at)] == ["pie"]
    avisos = [i.value for i in at.info if i.value == config.TEXTO_NENHUMA_ACAO_COM_CENARIO]
    assert len(avisos) == 2  # um em cada painel
    assert "Sem contribuição: SEMC3" in [c.value for c in at.caption]


@pytest.mark.parametrize("cenario", ["pessimista", "base", "otimista"])
def test_rotulos_dos_cenarios_existem_no_config(cenario):
    assert config.ROTULOS_CENARIOS_CARTEIRA[cenario]


def _ancora_do_investido(**mudancas) -> str:
    return _figura_faixa_cenarios(TOTAIS | mudancas).layout.annotations[0].xanchor


def test_rotulo_do_investido_se_alinha_por_dentro_quando_a_linha_esta_numa_ponta():
    assert _ancora_do_investido(soma_investida_com_cenario=2100.0) == "center"
    assert _ancora_do_investido(soma_investida_com_cenario=9000.0) == "right"
    assert _ancora_do_investido(soma_investida_com_cenario=100.0) == "left"
