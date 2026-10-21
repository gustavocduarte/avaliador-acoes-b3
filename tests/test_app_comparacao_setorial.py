"""Painel "Comparação setorial": tabela em HTML com barra divergente de potencial (verde à direita
do centro, rosa à esquerda, cortada em ±50%), sinal "+" e linha da ação analisada em destaque."""

import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import (
    _fmt_potencial,
    _html_barra_potencial,
    _html_linha_correlacao,
    _html_tabela_setorial,
)
from avaliador_b3.config import LIMITE_BARRA_POTENCIAL
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app

SEGMENTO = "Petróleo, Gás e Biocombustíveis"


def _largura(html: str) -> float:
    return float(re.search(r'style="width:([\d.]+)%"', html).group(1))


@pytest.mark.parametrize(
    ("valor", "texto"),
    [(13.5, "+13,5%"), (-21.04, "-21,0%"), (0.0, "0,0%"), (float("nan"), "N/D"), (None, "N/D")],
)
def test_potencial_tem_sinal_de_mais_so_quando_positivo(valor, texto):
    assert _fmt_potencial(valor) == texto


def test_barra_positiva_cresce_para_a_direita_em_verde_com_o_valor_exato():
    html = _html_barra_potencial(25.0)

    assert "ab-div-pos" in html
    assert "ab-div-neg" not in html
    assert _largura(html) == 25.0  # 25 de 50 pontos = metade do semi-eixo de 50%
    assert "+25,0%" in html


def test_barra_negativa_cresce_para_a_esquerda_em_rosa():
    html = _html_barra_potencial(-10.0)

    assert "ab-div-neg" in html
    assert "ab-div-pos" not in html
    assert _largura(html) == 10.0
    assert "-10,0%" in html


def test_barra_e_cortada_no_limite_mas_o_valor_ao_lado_continua_exato():
    assert LIMITE_BARRA_POTENCIAL == 50.0
    for valor, texto in [(180.0, "+180,0%"), (-180.1, "-180,1%")]:
        html = _html_barra_potencial(valor)
        assert _largura(html) == 50.0
        assert texto in html


def test_potencial_ausente_nao_desenha_barra():
    html = _html_barra_potencial(float("nan"))

    assert "ab-div-barra" not in html
    assert "—" in html


def _tabela() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["PETR4", "PETR3", "CSAN3"],
            "preco_atual": [58.0, 64.54, 5.11],
            "valor_combinado": [65.82, 65.85, -4.09],
            "desconto_percentual": [13.5, 2.0, -180.1],
        }
    )


def test_tabela_destaca_so_a_linha_da_acao_analisada_e_formata_os_valores():
    html = _html_tabela_setorial(_tabela(), "PETR4")

    assert html.count("ab-linha-destaque") == 1
    assert re.search(r'<tr class="ab-linha-destaque"><td>PETR4</td>', html)
    assert "R$ 58,00" in html and "R$ -4,09" in html
    assert html.count("ab-div-barra") == 3
    assert "+13,5%" in html and "-180,1%" in html
    assert "Potencial" in html and 'class="ab-ajuda"' in html


def test_tabela_sem_a_acao_analisada_nao_destaca_nenhuma_linha():
    assert "ab-linha-destaque" not in _html_tabela_setorial(_tabela(), "VALE3")


def test_painel_mostra_a_tabela_html_com_a_acao_buscada_em_destaque(monkeypatch, tmp_path):
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    base = {c: None for c in COLUNAS_RESULTADO} | {
        "sucesso": True,
        "erro": "",
        "aviso_desconto_extremo": "",
        "metodos_utilizados": "graham",
    }

    def linha(ticker, preco, valor, potencial):
        return base | {
            "ticker": ticker,
            "preco_atual": preco,
            "valor_combinado": valor,
            "desconto_percentual": potencial,
        }

    linhas = [
        linha("PETR4", 58.0, 65.82, 13.5),
        linha("BRAV3", 20.0, 14.0, -30.0),
        linha("VALE3", 60.0, 90.0, 50.0),
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *a, **k: app._catalogo_emissores_vazio(),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.resolver_segmentos_setoriais",
        lambda tickers, catalogo: pd.DataFrame(
            {
                "ticker": list(tickers),
                "segmento_setorial": [SEGMENTO if t != "VALE3" else "Mineração" for t in tickers],
            }
        ),
    )

    monkeypatch.setattr(
        "avaliador_b3.ingest.bcb_sgs.carregar_macro_referencia",
        lambda: {"selic_meta": 0.1475, "data_busca": pd.Timestamp("2026-10-19")},
    )

    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert "Preços e potenciais do screener de 19/10/2026" in [c.value for c in at.caption]
    tabelas = [e.proto.body for e in at.get("html") if "<table" in e.proto.body]
    assert len(tabelas) == 1
    html = tabelas[0]
    assert re.search(r'<tr class="ab-linha-destaque"><td>PETR4</td>', html)
    assert "BRAV3" in html and "VALE3" not in html
    assert "+13,5%" in html and "-30,0%" in html
    # A tabela antiga (st.dataframe) saiu do painel.
    assert not any("desconto_percentual" in df.value.columns for df in at.dataframe)


def _resultado_corr(valor, observacoes=500):
    return {"aplicavel": True, "correlacao": valor, "observacoes": observacoes}


def test_barra_de_correlacao_vai_de_menos_um_a_mais_um_com_valor_e_classificacao():
    html = _html_linha_correlacao("Câmbio USD/BRL", _resultado_corr(-0.5), None)

    assert "ab-corr-neg" in html and "ab-corr-pos" not in html
    assert _largura(html) == 25.0  # metade do semi-eixo
    assert "-0,50" in html and ">moderada<" in html
    assert "500 observações" in html


def test_barra_de_correlacao_positiva_cresce_para_a_direita_e_corta_em_um():
    html = _html_linha_correlacao("Petróleo (Brent)", _resultado_corr(1.0), None)

    assert "ab-corr-pos" in html
    assert _largura(html) == 50.0
    assert ">forte<" in html


def test_correlacao_indisponivel_mostra_traco_com_o_motivo_na_dica():
    html = _html_linha_correlacao(
        "Risco geopolítico (GPR)",
        {"aplicavel": False, "motivo_nao_aplicavel": "Série indisponível."},
        None,
    )

    assert "ab-div-barra" not in html
    assert 'ab-div-valor">—<' in html
    assert "Indisponível: Série indisponível." in html


def test_dica_do_gpr_traz_a_data_do_ultimo_dado_junto_das_observacoes():
    html = _html_linha_correlacao(
        "Risco geopolítico (GPR)", _resultado_corr(0.1, 120), "Último dado do GPR: 25/09/2026."
    )

    assert "120 observações · Último dado do GPR: 25/09/2026." in html


def test_dica_do_gpr_indisponivel_tambem_traz_a_data_do_ultimo_dado():
    html = _html_linha_correlacao(
        "Risco geopolítico (GPR)",
        {"aplicavel": False, "motivo_nao_aplicavel": "Sem sobreposição."},
        "Último dado do GPR: 25/09/2026.",
    )

    assert "Indisponível: Sem sobreposição. · Último dado do GPR: 25/09/2026." in html
