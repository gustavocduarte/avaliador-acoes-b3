"""Tabela "Ranking por potencial" do Screener: ordem, colunas, apresentação em pt-BR pelo Styler
(números de verdade por baixo) e cor do potencial."""

import json
import re

import pandas as pd
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import (
    COLUNAS_TABELA_SCREENER,
    _configuracao_colunas_ranking,
    _tabela_ranking_screener,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina


def _tabela(**extras) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA3", "BBB4", "CCC3", "DDD3", "EEE3"],
            "segmento_setorial": [
                "Bancos",
                "Exploração. Refino e Distribuição",
                "Bancos",
                None,
                "Bancos",
            ],
            "preco_atual": [10.0, 1234.56, 5.0, 8.0, 3.0],
            "valor_combinado": [11.0, 1000.0, None, 8.0, 6.0],
            "desconto_percentual": [10.0, -19.0, None, 0.0, 100.0],
            "erro": ["", "", "Nenhum método se aplica a esta empresa.", "", ""],
            "divergencia_percentual_metodos": [12.4, None, None, 3.0, 40.0],
            "bazin_razao_dividendos_percentual": [None, 150.0, None, None, None],
            "proporcao_reinvestimento_percentual": [20.0, None, None, None, None],
            "metodos_utilizados": ["graham,fcd", "bazin", "", "graham", "graham,bazin,fcd"],
            "aviso_desconto_extremo": ["", "", "", "", ""],
        }
        | extras
    )


def _celulas(estilo) -> list[list[str]]:
    """Valores exibidos (já formatados pelo Styler), linha a linha."""
    html = estilo.to_html()
    linhas = re.findall(r"<tr>(.*?)</tr>", html.split("<tbody>")[1], re.DOTALL)
    return [re.findall(r'class="data row\d+ col\d+ *" *>(.*?)</td>', linha) for linha in linhas]


def test_colunas_na_ordem_pedida_sem_graham_bazin_e_fcd_separados():
    _, colunas = _tabela_ranking_screener(_tabela())

    assert colunas == [
        "ticker",
        "segmento_setorial",
        "preco_atual",
        "valor_combinado",
        "desconto_percentual",
        "erro",
        "divergencia_percentual_metodos",
        "bazin_razao_dividendos_percentual",
        "proporcao_reinvestimento_percentual",
        "metodos_utilizados",
        "aviso_desconto_extremo",
    ]
    assert colunas == COLUNAS_TABELA_SCREENER
    assert not {"graham_valor_justo", "bazin_preco_teto", "fcd_valor_justo"} & set(colunas)


def test_coluna_de_setor_so_existe_se_o_arquivo_trouxer():
    _, colunas = _tabela_ranking_screener(_tabela().drop(columns="segmento_setorial"))

    assert "segmento_setorial" not in colunas
    assert colunas[:3] == ["ticker", "preco_atual", "valor_combinado"]


def test_ordena_por_potencial_decrescente_e_deixa_as_sem_combinado_no_fim():
    estilo, _ = _tabela_ranking_screener(_tabela())

    assert list(estilo.data["ticker"]) == ["EEE3", "AAA3", "DDD3", "BBB4", "CCC3"]


def test_mostra_os_numeros_em_pt_br_com_sinal_e_traco_para_o_que_falta():
    estilo, _ = _tabela_ranking_screener(_tabela())

    celulas = {linha[0]: linha for linha in _celulas(estilo)}
    # ticker, setor, preço, combinado, potencial, observação, divergência, dividendos, reinvest.
    assert celulas["AAA3"][1:5] == ["Bancos", "R$ 10,00", "R$ 11,00", "+10,0%"]
    assert celulas["BBB4"][1:5] == [
        "Exploração, Refino e Distribuição",
        "R$ 1.234,56",
        "R$ 1.000,00",
        "-19,0%",
    ]
    assert celulas["CCC3"][3:5] == ["—", "—"]
    assert celulas["DDD3"][1] == "—"
    assert celulas["DDD3"][4] == "0,0%"
    assert celulas["AAA3"][6:9] == ["12%", "—", "20%"]
    assert celulas["BBB4"][8] == "—" and celulas["BBB4"][7] == "150%"
    assert celulas["AAA3"][9] == "Graham, FCD"


def test_o_potencial_leva_cor_so_quando_positivo_ou_negativo():
    estilo, _ = _tabela_ranking_screener(_tabela())

    cores = {}
    for seletores, cor in re.findall(r"([^{}]+)\{\s*color: (#\w+);", estilo.to_html()):
        for linha in re.findall(r"row(\d+)_col4", seletores):
            cores[estilo.data["ticker"].iloc[int(linha)]] = cor
    # Ordem das linhas: EEE3, AAA3, DDD3, BBB4, CCC3; zero e vazio ficam sem cor.
    assert cores == {
        "EEE3": config.COR_POSITIVO,
        "AAA3": config.COR_POSITIVO,
        "BBB4": config.COR_NEGATIVO,
    }


def test_numeros_de_verdade_por_baixo_da_formatacao():
    estilo, _ = _tabela_ranking_screener(_tabela())

    assert pd.api.types.is_float_dtype(estilo.data["preco_atual"])
    assert pd.api.types.is_float_dtype(estilo.data["desconto_percentual"])


def test_configuracao_das_colunas_tem_rotulo_e_a_explicacao_do_potencial():
    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER)

    assert configuracao["segmento_setorial"]["label"] == "Setor"
    assert configuracao["erro"]["label"] == "Observação"
    assert configuracao["desconto_percentual"]["help"] == config.TOOLTIP_POTENCIAL_COLUNA
    assert configuracao["preco_atual"].get("help") is None


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
        | {"ticker": "BAIXO3", "preco_atual": 9.0, "valor_combinado": 5.0}
        | {"desconto_percentual": -44.4},
        base | {"ticker": "SEMM3", "preco_atual": 5.0, "erro": "Nenhum método se aplica."},
        base
        | {"ticker": "ALTO4", "preco_atual": 10.0, "valor_combinado": 20.0}
        | {"desconto_percentual": 100.0},
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, config.TITULO_PAGINA_SCREENER)
    assert not at.exception
    return at


def test_pagina_mostra_o_ranking_ordenado_com_as_sem_combinado_no_fim(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)
    next(c for c in at.sidebar.checkbox if c.label == "Esconder sem valor combinado").uncheck().run(
        timeout=60
    )

    tabelas = [df for df in at.dataframe if "desconto_percentual" in df.value.columns]
    assert len(tabelas) == 1
    assert list(tabelas[0].value["ticker"]) == ["ALTO4", "BAIXO3", "SEMM3"]
    colunas = json.loads(tabelas[0].proto.columns)
    assert colunas["desconto_percentual"]["label"] == "Potencial"
    assert colunas["segmento_setorial"]["label"] == "Setor"


def test_pagina_comeca_nos_cartoes_e_deixa_o_expander_de_leitura_depois_da_tabela(
    monkeypatch, tmp_path
):
    at = _abrir_screener(monkeypatch, tmp_path)

    tipos = [elemento.type for elemento in at.main]
    antes_dos_cartoes = tipos[1 : tipos.index("flex_container")]
    assert set(antes_dos_cartoes) <= {"html", "caption"}  # só o cabeçalho do app
    assert tipos.index("expander") > tipos.index("dataframe")
    assert [c for c in at.caption if c.value.startswith("Ranking pelo potencial")] == []
