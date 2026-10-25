"""Gráfico "Histórico de dividendos por ano": barras do dividend yield em eixo único, janela de
10 anos, rótulos, ano corrente parcial e notas no "?" do título; e a barra de ferramentas do
Plotly escondida em todos os gráficos."""

import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3.config import (
    ANOS_JANELA_DIVIDENDOS,
    NOTA_DIVIDEND_YIELD_SUBESTIMADO,
    NOTA_DIVIDENDOS_ANO_PARCIAL,
    OPACIDADE_BARRA_PARCIAL,
    TITULO_PAINEL_DIVIDENDOS,
)
from tests import test_app_main as app

ANO_ATUAL = pd.Timestamp.now().year
PRECO_MEDIO = 50.0


def _preparar(monkeypatch, datas_e_valores: list[tuple[str, float]], primeiro_ano_preco: int):
    """App com a ação aplicável, dividendos controlados e preço de R$ 50 em todos os anos a
    partir de `primeiro_ano_preco` (o yield de um ano é o total pago dividido por 50)."""
    app._preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    por_periodo = app._historico_por_periodo(
        {"1d": 50.0, "3mo": 50.0, "1y": 50.0, "5y": 50.0, "10y": 50.0, "2y": 50.0}
    )

    def historico(ticker, periodo="3mo", auto_adjust=True, **kwargs):
        if periodo != "max":
            return por_periodo(ticker, periodo=periodo, auto_adjust=auto_adjust, **kwargs)
        anos = range(primeiro_ano_preco, ANO_ATUAL + 1)
        return pd.DataFrame(
            {
                "data": pd.to_datetime([f"{ano}-06-15" for ano in anos], utc=True),
                "Close": [PRECO_MEDIO] * len(anos),
                "Volume": [1_000_000] * len(anos),
            }
        )

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", historico)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "data": pd.to_datetime([data for data, _ in datas_e_valores]),
                "dividendo": [valor for _, valor in datas_e_valores],
            }
        ),
    )


def _abrir() -> AppTest:
    at = AppTest.from_file(app.CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception
    return at


def _figura_dividendos(at) -> dict:
    figuras = [json.loads(g.proto.spec) for g in at.get("plotly_chart")]
    candidatas = [f for f in figuras if f["data"] and f["data"][0].get("type") == "bar"]
    candidatas = [f for f in candidatas if f["data"][0].get("orientation") != "h"]
    assert len(candidatas) == 1
    return candidatas[0]


def _barras(at) -> dict:
    return _figura_dividendos(at)["data"][0]


def _lista(valor) -> list:
    return app._valores_plotly(valor)


def _cabecalhos_de_painel(at) -> list[str]:
    return [e.proto.body for e in at.get("html") if "ab-cabecalho" in e.proto.body]


def _anos_com_dividendo(*anos: int) -> list[tuple[str, float]]:
    return [(f"{ano}-05-01", 1.0) for ano in anos]


def test_figura_tem_eixo_unico_com_o_yield_nas_barras_e_o_reais_no_hover(monkeypatch):
    _preparar(
        monkeypatch,
        [(f"{ANO_ATUAL - 3}-05-01", 1.0), (f"{ANO_ATUAL}-02-01", 0.5)],
        primeiro_ano_preco=ANO_ATUAL - 5,
    )

    figura = _figura_dividendos(_abrir())

    assert len(figura["data"]) == 1
    assert "yaxis2" not in figura["layout"]
    assert figura["layout"]["showlegend"] is False
    barras = figura["data"][0]
    assert barras["marker"]["color"] == "#22D3EE"
    assert barras["x"] == [
        str(ANO_ATUAL - 3),
        str(ANO_ATUAL - 2),
        str(ANO_ATUAL - 1),
        f"{ANO_ATUAL}*",
    ]
    assert _lista(barras["y"]) == [2.0, 0.0, 0.0, 1.0]
    # Hover: yield e total pago em R$/ação, com vírgula decimal.
    assert "customdata[0]" in barras["hovertemplate"]
    assert "customdata[1]" in barras["hovertemplate"]
    assert barras["customdata"] == [
        ["2,0%", "R$ 1,00"],
        ["0,0%", "R$ 0,00"],
        ["0,0%", "R$ 0,00"],
        ["1,0%", "R$ 0,50"],
    ]


def test_janela_padrao_mostra_os_ultimos_10_anos_com_o_percentual_acima_das_barras(monkeypatch):
    primeiro = ANO_ATUAL - 15
    _preparar(
        monkeypatch,
        [(f"{ano}-05-01", 1.0) for ano in range(primeiro, ANO_ATUAL)],
        primeiro_ano_preco=primeiro,
    )

    at = _abrir()

    barras = _barras(at)
    assert len(barras["x"]) == ANOS_JANELA_DIVIDENDOS
    assert barras["x"][0] == str(ANO_ATUAL - ANOS_JANELA_DIVIDENDOS + 1)
    assert barras["x"][-1] == f"{ANO_ATUAL}*"
    assert barras["textposition"] == "outside"
    # O ano corrente não teve dividendo: barra zero e sem rótulo; os demais mostram o %.
    assert barras["text"][-1] == ""
    assert barras["text"][:-1] == ["2,0%"] * (ANOS_JANELA_DIVIDENDOS - 1)


def test_controle_de_janela_oferece_10_anos_e_desde_o_primeiro_ano_e_o_completo_so_tem_hover(
    monkeypatch,
):
    primeiro = ANO_ATUAL - 15
    _preparar(
        monkeypatch,
        [(f"{ano}-05-01", 1.0) for ano in range(primeiro, ANO_ATUAL)],
        primeiro_ano_preco=primeiro,
    )
    at = _abrir()

    controle = next(p for p in at.pills if p.label == "Janela do histórico")
    assert list(controle.options) == [f"{ANOS_JANELA_DIVIDENDOS} anos", f"Desde {primeiro}"]
    assert controle.value == f"{ANOS_JANELA_DIVIDENDOS} anos"

    controle.set_value(f"Desde {primeiro}").run(timeout=60)

    assert not at.exception
    barras = _barras(at)
    assert len(barras["x"]) == ANO_ATUAL - primeiro + 1
    assert barras["x"][0] == str(primeiro)
    assert barras["textposition"] == "none"
    assert "customdata[0]" in barras["hovertemplate"]


def test_historico_dentro_da_janela_nao_mostra_o_controle_e_mantem_os_rotulos(monkeypatch):
    _preparar(monkeypatch, _anos_com_dividendo(ANO_ATUAL - 2, ANO_ATUAL - 1), ANO_ATUAL - 4)

    at = _abrir()

    assert not any(p.label == "Janela do histórico" for p in at.pills)
    assert _barras(at)["textposition"] == "outside"


def test_ano_corrente_parcial_tem_barra_clara_hachurada_e_os_demais_sao_opacos(monkeypatch):
    _preparar(
        monkeypatch,
        _anos_com_dividendo(ANO_ATUAL - 1) + [(f"{ANO_ATUAL}-02-01", 0.5)],
        ANO_ATUAL - 3,
    )

    marcador = _barras(_abrir())["marker"]

    assert marcador["opacity"] == [1.0, OPACIDADE_BARRA_PARCIAL]
    assert marcador["pattern"]["shape"] == ["", "/"]


def test_notas_do_ano_parcial_e_da_subestimacao_ficam_no_ponto_de_interrogacao(monkeypatch):
    _preparar(
        monkeypatch,
        _anos_com_dividendo(ANO_ATUAL - 1) + [(f"{ANO_ATUAL}-02-01", 0.5)],
        ANO_ATUAL - 3,
    )

    at = _abrir()

    cabecalho = next(c for c in _cabecalhos_de_painel(at) if TITULO_PAINEL_DIVIDENDOS in c)
    assert NOTA_DIVIDENDOS_ANO_PARCIAL.format(ano=ANO_ATUAL) in cabecalho
    assert NOTA_DIVIDEND_YIELD_SUBESTIMADO in cabecalho
    legendas = [c.value for c in at.caption]
    assert NOTA_DIVIDENDOS_ANO_PARCIAL.format(ano=ANO_ATUAL) not in legendas
    assert NOTA_DIVIDEND_YIELD_SUBESTIMADO not in legendas


def test_ano_corrente_sem_dividendo_tambem_entra_como_parcial_no_grafico(monkeypatch):
    _preparar(monkeypatch, [(f"{ANO_ATUAL - 2}-05-01", 1.0)], ANO_ATUAL - 4)

    barras = _barras(_abrir())

    assert barras["x"][-1] == f"{ANO_ATUAL}*"
    assert _lista(barras["y"])[-1] == 0.0


def test_sem_preco_historico_nao_desenha_o_grafico_e_explica_o_motivo(monkeypatch):
    _preparar(monkeypatch, _anos_com_dividendo(ANO_ATUAL - 1), ANO_ATUAL - 3)
    por_periodo = app._historico_por_periodo(
        {"1d": 50.0, "3mo": 50.0, "1y": 50.0, "5y": 50.0, "10y": 50.0, "2y": 50.0}
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        lambda ticker, periodo="3mo", **kwargs: por_periodo(ticker, periodo=periodo, **kwargs),
    )

    at = _abrir()

    assert any("Dividend Yield indisponível" in c.value for c in at.caption)
    with pytest.raises(AssertionError):
        _figura_dividendos(at)


def test_todos_os_graficos_do_app_escondem_a_barra_de_ferramentas(monkeypatch):
    _preparar(monkeypatch, _anos_com_dividendo(ANO_ATUAL - 1), ANO_ATUAL - 3)

    graficos = _abrir().get("plotly_chart")

    assert len(graficos) >= 3
    for grafico in graficos:
        assert json.loads(grafico.proto.config)["displayModeBar"] is False


def test_so_o_auxiliar_chama_st_plotly_chart_no_app():
    pasta = Path(app.CAMINHO_APP).parent
    fonte = "\n".join(a.read_text(encoding="utf-8") for a in sorted(pasta.rglob("*.py")))

    assert fonte.count("st.plotly_chart(") == 1
