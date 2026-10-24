"""Distribuição do potencial (histograma) e cartões "Atenção" da página Screener."""

import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import (
    _faixa_do_potencial,
    _figura_distribuicao_potencial,
    _html_atencao_screener,
    _posicao_no_histograma,
)
from avaliador_b3.config import AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD, TITULO_PAGINA_SCREENER
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina


@pytest.mark.parametrize(
    ("valor", "faixa"),
    [
        (-282.1, 0),
        (-100.0, 0),
        (-80.0, 1),
        (-0.1, 4),
        (0.0, 5),
        (99.9, 9),
        (100.0, 9),
        (100.1, 10),
        (409.7, 10),
    ],
)
def test_faixa_do_potencial(valor, faixa):
    assert _faixa_do_potencial(valor) == faixa


@pytest.mark.parametrize(
    ("valor", "posicao"), [(-150.0, -0.5), (-100.0, -0.5), (0.0, 4.5), (100.0, 9.5), (409.7, 10.0)]
)
def test_posicao_no_histograma(valor, posicao):
    assert _posicao_no_histograma(valor) == pytest.approx(posicao)


def test_histograma_conta_por_faixa_pinta_rosa_e_verde_e_marca_a_mediana():
    potencial = pd.Series([-150.0, -90.0, -10.0, 5.0, 30.0, 409.7, None])

    figura = _figura_distribuicao_potencial(potencial)

    barras = figura.data[0]
    assert list(barras.y) == [2, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1]
    assert list(barras.marker.color) == [config.COR_NEGATIVO] * 5 + [config.COR_POSITIVO] * 6
    assert list(barras.customdata)[0] == "-100 a -80%"
    assert list(barras.customdata)[-1] == ">100%"
    zero, mediana = figura.layout.shapes
    assert zero.x0 == pytest.approx(4.5)
    assert zero.line.width == 1
    assert mediana.line.dash == "dash"
    assert mediana.line.color == config.COR_ALERTA
    assert mediana.x0 == pytest.approx(_posicao_no_histograma(-2.5))
    assert [a.text for a in figura.layout.annotations] == ["mediana -2,5%"]
    assert figura.layout.separators == ",."


def test_eixo_x_tem_rotulos_curtos_horizontais_nas_bordas_e_o_percentual_so_no_titulo():
    figura = _figura_distribuicao_potencial(pd.Series([10.0, -10.0]))

    eixo = figura.layout.xaxis
    assert list(eixo.ticktext) == [
        "-100",
        "-80",
        "-60",
        "-40",
        "-20",
        "0",
        "+20",
        "+40",
        "+60",
        "+80",
        ">100",
    ]
    assert list(eixo.tickvals)[:3] == pytest.approx([-0.5, 0.5, 1.5])
    assert list(eixo.tickvals)[-1] == 10
    assert eixo.tickangle == 0
    assert eixo.title.text == "Potencial (%)"
    assert not any("%" in texto for texto in eixo.ticktext)


def _html_com_avisos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["BEEF3", "AAA3", "CSNA3", "NATU3"],
            "desconto_percentual": [409.7, 10.0, None, None],
            "valor_combinado": [22.0, 11.0, None, None],
            "aviso_desconto_extremo": [AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD, "", "", ""],
        }
    )


def test_atencao_tem_um_cartao_por_aviso_e_um_para_as_sem_metodo():
    html = _html_atencao_screener(_html_com_avisos())

    assert html.count("ab-atencao-cartao") == 2
    assert "BEEF3" in html and "+409,7%" in html
    # Linha curta no cartão; o texto completo só no "?".
    assert (
        '<div class="ab-atencao-texto">Potencial extremo: confira as premissas do FCD</div>' in html
    )
    assert f'title="{AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD}"' in html
    assert html.count("provavelmente vem da taxa de crescimento") == 1
    assert "AAA3" not in html
    assert "Sem método aplicável" in html
    assert "2 ações sem nenhum método aplicável: CSNA3, NATU3." in html


def test_atencao_sem_alerta_nenhum_mostra_so_a_frase():
    tabela = _html_com_avisos().iloc[[1]]

    html = _html_atencao_screener(tabela)

    assert "ab-atencao-cartao" not in html
    assert "Nenhum alerta nesta rodada." in html


def _abrir_screener(monkeypatch, tmp_path) -> AppTest:
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
        "segmento_setorial": "Bancos",
    }
    linhas = [
        base
        | {"ticker": "BEEF3", "valor_combinado": 22.0, "desconto_percentual": 409.7}
        | {"aviso_desconto_extremo": AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD}
        | {"metodos_utilizados": "graham,fcd"},
        base | {"ticker": "AAA3", "valor_combinado": 11.0, "desconto_percentual": 10.0},
        base | {"ticker": "BBB4", "valor_combinado": 8.0, "desconto_percentual": -30.0},
        base | {"ticker": "CSNA3", "metodos_utilizados": ""},
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    assert not at.exception
    return at


def _contagens_do_histograma(at) -> list[int]:
    for grafico in at.get("plotly_chart"):
        figura = json.loads(grafico.proto.spec)
        if figura["data"] and figura["data"][0].get("customdata", [None])[-1] == ">100%":
            return figura["data"][0]["y"]
    raise AssertionError("histograma não encontrado")


def test_pagina_mostra_o_histograma_e_a_atencao_no_lugar_do_aviso_amarelo(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    assert sum(_contagens_do_histograma(at)) == 3
    assert not [w for w in at.warning if "potencial fora do comum" in w.value]
    corpos = [h.proto.body for h in at.get("html")]
    atencao = next(c for c in corpos if "ab-atencao" in c)
    assert "BEEF3" in atencao and "CSNA3" in atencao
    titulos = [h for h in corpos if "Distribuição do potencial" in h]
    assert titulos and 'class="ab-ajuda"' in titulos[0]


def test_histograma_segue_os_filtros_e_a_atencao_descreve_o_universo_inteiro(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    next(c for c in at.sidebar.checkbox if c.label == "FCD").check().run(timeout=60)

    assert sum(_contagens_do_histograma(at)) == 1
    atencao = next(h.proto.body for h in at.get("html") if "ab-atencao" in h.proto.body)
    assert "BEEF3" in atencao and "CSNA3" in atencao


@pytest.mark.parametrize(
    ("aviso", "resumo"),
    [
        (
            config.AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD,
            "Potencial extremo: confira as premissas do FCD",
        ),
        (
            config.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
            "Potencial extremo: confira Graham e Bazin",
        ),
        (config.AVISO_DESCONTO_EXTREMO_GENERICO, "Potencial fora do comum: confira os métodos"),
        # Texto de um arquivo antigo: o começo, até o primeiro " — " ou ponto.
        (
            "Valor justo zero ou negativo — o FCD saiu negativo. Não quer dizer",
            "Valor justo zero ou negativo",
        ),
        ("Aviso sem separador. Resto", "Aviso sem separador"),
    ],
)
def test_resumo_do_aviso(aviso, resumo):
    from avaliador_b3.app.main import _resumo_do_aviso

    assert _resumo_do_aviso(aviso) == resumo


def test_eixo_y_do_histograma_deixa_folga_acima_da_barra_mais_alta_para_a_mediana():
    figura = _figura_distribuicao_potencial(pd.Series([10.0] * 8 + [-10.0]))

    assert figura.layout.yaxis.range[0] == 0
    assert figura.layout.yaxis.range[1] > max(figura.data[0].y) * config.FOLGA_TOPO_HISTOGRAMA
