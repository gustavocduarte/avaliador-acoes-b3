"""Painel "Histórico da carteira" do Simulador: seletor de período, linhas por ação, carteira,
IPCA e CDI, avisos de histórico curto ou ausente e as cores das ações."""

import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.config import (
    CHAVE_CARTEIRA_POSICOES,
    CHAVE_PERIODO_HISTORICO_CARTEIRA,
    CORES_ACOES_CARTEIRA,
    SERIES_BCB_SGS,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina

DIAS_POR_ANO = {"1y": 261, "2y": 522, "5y": 1305}


def _precos(ticker: str, periodo: str, curto: bool = False) -> pd.DataFrame:
    dias = 60 if curto else DIAS_POR_ANO[periodo]
    # Com fuso (UTC), como o yfinance entrega; o CDI e o IPCA do Banco Central vêm sem fuso.
    datas = pd.bdate_range(end="2026-10-22", periods=dias, tz="UTC")
    base = 10.0 + (hash(ticker) % 7)
    return pd.DataFrame({"data": datas, "Close": [base + i * 0.01 for i in range(dias)]})


def _ipca() -> pd.DataFrame:
    meses = pd.date_range("2021-09-01", "2026-09-01", freq="MS")
    return pd.DataFrame({"data": meses, "valor": [0.4] * len(meses)})


def _cdi() -> pd.DataFrame:
    datas = pd.bdate_range("2021-09-01", "2026-10-22")
    return pd.DataFrame({"data": datas, "valor": [0.05] * len(datas)})


def _preparar(monkeypatch, tmp_path, tickers, curtos=(), sem_historico=(), sem_ipca=False):
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
        | {"ticker": t, "preco_atual": 10.0, "valor_combinado": 12.0, "graham_valor_justo": 12.0}
        for t in tickers
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)

    pedidos: list[tuple[str, str]] = []

    def historico(ticker, periodo="3mo", **kwargs):
        pedidos.append((ticker, periodo))
        if ticker in sem_historico:
            raise precos_mod.FalhaFontePreco(f"{ticker} sem preço (simulado)")
        return _precos(ticker, periodo, curto=ticker in curtos)

    def serie(codigo, data_inicial=None, data_final=None, **kwargs):
        if codigo == SERIES_BCB_SGS["ipca_mensal"]:
            if sem_ipca:
                raise RuntimeError("BCB fora do ar (simulado)")
            return _ipca()
        if codigo == SERIES_BCB_SGS["cdi_diaria"]:
            return _cdi()
        raise AssertionError(f"série inesperada: {codigo}")

    from avaliador_b3.ingest import precos as precos_mod

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", historico)
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie_com_fallback", serie)
    return pedidos


def _abrir(monkeypatch, tmp_path, posicoes: dict[str, int], **opcoes):
    pedidos = _preparar(monkeypatch, tmp_path, list(posicoes), **opcoes)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, config.TITULO_PAGINA_CARTEIRA)
    at.session_state[CHAVE_CARTEIRA_POSICOES] = posicoes
    at.run(timeout=120)
    assert not at.exception
    return at, pedidos


def _grafico_do_historico(at) -> dict:
    for grafico in at.get("plotly_chart"):
        figura = json.loads(grafico.proto.spec)
        nomes = [t.get("name") for t in figura["data"]]
        if "Carteira" in nomes:
            return figura
    raise AssertionError("gráfico do histórico não encontrado")


def _linhas_por_nome(figura: dict) -> dict[str, dict]:
    return {t["name"]: t for t in figura["data"]}


def test_painel_mostra_uma_linha_por_acao_a_carteira_a_inflacao_e_o_cdi(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 300, "BBB4": 200, "CCC3": 100})

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    assert list(linhas) == ["AAA3", "BBB4", "CCC3", "Carteira", "Inflação (IPCA)", "CDI"]
    carteira, ipca, cdi = linhas["Carteira"], linhas["Inflação (IPCA)"], linhas["CDI"]
    assert carteira["line"] == {"color": config.COR_PRINCIPAL, "width": 4}
    assert ipca["line"]["color"] == config.COR_NEUTRO and ipca["line"]["dash"] == "dot"
    assert cdi["line"]["color"] == config.COR_TEXTO and cdi["line"]["dash"] == "dash"
    assert carteira["line"]["width"] > linhas["AAA3"]["line"]["width"]


def test_todas_as_linhas_comecam_no_valor_investido_total_de_hoje(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 300, "BBB4": 200})  # 3.000 + 2.000 = 5.000

    figura = _grafico_do_historico(at)

    for nome, linha in _linhas_por_nome(figura).items():
        primeiro = app._valores_plotly(linha["y"])[0]
        assert primeiro == pytest.approx(5000.0), nome


def test_cada_acao_usa_a_cor_da_sequencia_pela_ordem_do_peso(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"PEQ3": 100, "GRA4": 500, "MED3": 300})

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    assert linhas["GRA4"]["line"]["color"] == CORES_ACOES_CARTEIRA[0]
    assert linhas["MED3"]["line"]["color"] == CORES_ACOES_CARTEIRA[1]
    assert linhas["PEQ3"]["line"]["color"] == CORES_ACOES_CARTEIRA[2]


def test_comeca_em_um_ano_e_trocar_o_periodo_busca_de_novo_com_o_novo_periodo(
    monkeypatch, tmp_path
):
    at, pedidos = _abrir(monkeypatch, tmp_path, {"AAA3": 100})

    assert at.pills(key=CHAVE_PERIODO_HISTORICO_CARTEIRA).value == "1 ano"
    assert {p for _, p in pedidos if p in DIAS_POR_ANO} == {"1y"}

    at.pills(key=CHAVE_PERIODO_HISTORICO_CARTEIRA).set_value("5 anos").run(timeout=120)

    assert ("AAA3", "5y") in pedidos
    assert (
        len(_grafico_do_historico(at)["data"][0]["x"]) > 261
    )  # o período de 5 anos tem mais pregões


def test_com_mais_de_sete_acoes_so_as_sete_maiores_tem_linha_e_as_demais_so_na_carteira(
    monkeypatch, tmp_path
):
    posicoes = {f"A{i}": 100 + 10 * i for i in range(9)}  # A8 é a maior e A0 a menor
    at, _ = _abrir(monkeypatch, tmp_path, posicoes)

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    acoes = [n for n in linhas if n not in ("Carteira", "Inflação (IPCA)", "CDI")]
    assert sorted(acoes) == sorted(f"A{i}" for i in range(2, 9))
    cores = [linhas[a]["line"]["color"] for a in acoes]
    assert len(set(cores)) == 7  # nenhuma cor se repete
    legenda = [c.value for c in at.caption if c.value.startswith("Demais ações incluídas")]
    assert legenda == ["Demais ações incluídas na carteira: A1, A0"]


def test_acao_com_historico_curto_tem_linha_propria_e_fica_fora_da_carteira_com_aviso(
    monkeypatch, tmp_path
):
    at, _ = _abrir(monkeypatch, tmp_path, {"LONGA3": 300, "NOVA4": 200}, curtos=("NOVA4",))

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    assert "NOVA4" in linhas and len(linhas["NOVA4"]["x"]) == 60
    avisos = [w.value for w in at.warning if "ficaram de fora da linha" in w.value]
    assert avisos == ['Sem histórico no período todo, ficaram de fora da linha "Carteira": NOVA4.']
    # A carteira ainda parte do investido total (5.000), só com a ação de histórico completo.
    assert app._valores_plotly(linhas["Carteira"]["y"])[0] == pytest.approx(5000.0)


def test_acao_sem_preco_nenhum_fica_listada_e_sem_linha(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 300, "ZZZ3": 100}, sem_historico=("ZZZ3",))

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    assert "ZZZ3" not in linhas and "AAA3" in linhas
    assert [w.value for w in at.warning if "Sem histórico de preços" in w.value] == [
        "Sem histórico de preços para: ZZZ3."
    ]


def test_sem_nenhum_historico_a_pagina_avisa_em_vez_de_desenhar(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"ZZZ3": 100}, sem_historico=("ZZZ3",))

    assert not any(
        "Carteira" in [t.get("name") for t in json.loads(g.proto.spec)["data"]]
        for g in at.get("plotly_chart")
    )
    assert [i.value for i in at.info if i.value == config.TEXTO_NENHUM_HISTORICO_DA_CARTEIRA]


def test_inflacao_indisponivel_avisa_e_o_resto_do_grafico_continua(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 100}, sem_ipca=True)

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    assert "Inflação (IPCA)" not in linhas and "CDI" in linhas and "Carteira" in linhas
    assert any(w.value.startswith("Inflação (IPCA) indisponível agora:") for w in at.warning)


def test_titulo_traz_o_texto_de_desempenho_passado_e_o_painel_vem_depois_das_posicoes(
    monkeypatch, tmp_path
):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 100})

    corpos = [h.proto.body for h in at.get("html")]
    ordem = [
        i for i, c in enumerate(corpos) if "Histórico da carteira" in c and "ab-cabecalho" in c
    ]
    posicoes = [i for i, c in enumerate(corpos) if "ab-tabela-posicoes" in c]
    assert ordem and posicoes and ordem[0] > posicoes[0]
    cabecalho = corpos[ordem[0]]
    assert "Desempenho passado, não é previsão." in cabecalho
    assert "o JCP pode não estar incluído em todos os casos" in cabecalho
    assert 'class="ab-ajuda"' in cabecalho


def test_cdi_e_ipca_sobem_ao_longo_do_periodo_com_as_datas_com_fuso_do_yahoo(monkeypatch, tmp_path):
    at, _ = _abrir(monkeypatch, tmp_path, {"AAA3": 100})

    linhas = _linhas_por_nome(_grafico_do_historico(at))

    for nome in ("CDI", "Inflação (IPCA)"):
        valores = app._valores_plotly(linhas[nome]["y"])
        assert valores[-1] > valores[0], nome  # a linha sobe: não é reta
    cdi = app._valores_plotly(linhas["CDI"]["y"])
    assert cdi[-1] / cdi[0] - 1 > 0.04  # 1 ano a 0,05% ao dia, bem acima de zero
