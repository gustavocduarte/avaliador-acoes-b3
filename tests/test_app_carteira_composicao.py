"""Composição por ação (rosca), composição por setor, tabela "Posições" em HTML e o expander
"Cenários por ação" do Simulador."""

import json
import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import (
    _cores_das_acoes,
    _fatias_da_composicao,
    _figura_composicao_por_acao,
    _figura_composicao_por_setor,
    _html_tabela_posicoes,
    _pesos_por_setor,
)
from avaliador_b3.carteira import compor_posicoes
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina, adicionar_a_carteira


def _tabela() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA3", "BBB4", "CCC3", "DDD3"],
            "preco_atual": [10.0, 20.0, 5.0, None],
            "valor_combinado": [15.0, 10.0, None, 9.0],
            "segmento_setorial": ["Bancos", "Bancos", "Energia Elétrica", None],
        }
    )


def _composicao(posicoes: dict[str, int]) -> pd.DataFrame:
    return compor_posicoes(_tabela(), posicoes)


def test_compor_posicoes_calcula_investido_valor_justo_potencial_e_peso():
    comp = _composicao({"AAA3": 100, "BBB4": 50, "CCC3": 200}).set_index("ticker")

    assert comp.loc["AAA3", "investido"] == pytest.approx(1000.0)
    assert comp.loc["AAA3", "valor_justo"] == pytest.approx(1500.0)
    assert comp.loc["AAA3", "potencial_percentual"] == pytest.approx(50.0)
    assert comp.loc["BBB4", "potencial_percentual"] == pytest.approx(-50.0)
    assert comp.loc["BBB4", "setor"] == "Bancos"
    assert comp["peso_percentual"].tolist() == pytest.approx([1000 / 3000 * 100] * 3)
    assert comp["peso_percentual"].sum() == pytest.approx(100.0)


def test_compor_posicoes_sem_valor_combinado_ou_sem_preco_fica_vazia_mas_conta_o_investido():
    comp = _composicao({"CCC3": 200, "DDD3": 10}).set_index("ticker")

    assert comp.loc["CCC3", "sem_combinado"] and comp.loc["DDD3", "sem_combinado"]
    assert comp.loc["CCC3", "investido"] == pytest.approx(1000.0)
    assert pd.isna(comp.loc["CCC3", "valor_justo"])
    assert pd.isna(comp.loc["CCC3", "potencial_percentual"])
    assert comp.loc["DDD3", "investido"] == 0.0  # sem preço
    assert comp.loc["CCC3", "peso_percentual"] == pytest.approx(100.0)


def test_as_sete_maiores_acoes_recebem_as_cores_na_ordem_do_peso_e_as_demais_nenhuma():
    tabela = pd.DataFrame(
        {
            "ticker": [f"A{i}" for i in range(9)],
            "preco_atual": [10.0] * 9,
            "valor_combinado": [12.0] * 9,
        }
    )
    # A0 é a menor posição e A8 a maior.
    comp = compor_posicoes(tabela, {f"A{i}": i + 1 for i in range(9)})

    cores = _cores_das_acoes(comp)

    assert list(cores) == [f"A{i}" for i in range(8, 1, -1)]  # as 7 maiores, da maior à menor
    assert list(cores.values()) == list(config.CORES_ACOES_CARTEIRA)
    assert len(set(cores.values())) == 7  # nenhuma cor se repete
    assert "A0" not in cores and "A1" not in cores


def test_rosca_tem_o_percentual_na_fatia_o_total_no_centro_e_as_cores_das_acoes():
    comp = _composicao({"AAA3": 100, "BBB4": 50, "CCC3": 200})
    cores = _cores_das_acoes(comp)

    figura = _figura_composicao_por_acao(comp, cores)

    rosca = figura.data[0]
    assert rosca.hole == 0.6
    assert list(rosca.text) == ["33,3%", "33,3%", "33,3%"]
    assert list(rosca.marker.colors) == [cores[t] for t in rosca.labels]
    assert [a.text for a in figura.layout.annotations] == ["<b>R$ 3.000,00</b><br>investido"]
    assert figura.layout.separators == ",."


def test_com_mais_de_sete_acoes_as_menores_viram_outras_e_a_sem_combinado_entra():
    tabela = pd.DataFrame(
        {
            "ticker": [f"A{i}" for i in range(10)],
            "preco_atual": [10.0] * 10,
            "valor_combinado": [12.0] * 9 + [None],  # a última é sem valor combinado
        }
    )
    posicoes = {f"A{i}": 100 - i for i in range(10)}  # A9 é a menor, e sem valor combinado
    comp = compor_posicoes(tabela, posicoes)

    fatias = _fatias_da_composicao(comp)

    assert len(fatias) == 8  # 7 ações + "Outras"
    assert [f[0] for f in fatias[:7]] == [f"A{i}" for i in range(7)]
    nome, investido, peso = fatias[-1]
    assert nome == "Outras"
    assert investido == pytest.approx(10 * (93 + 92 + 91))  # A7, A8 e A9
    assert peso == pytest.approx(sum(comp["peso_percentual"].iloc[7:]))
    assert sum(f[2] for f in fatias) == pytest.approx(100.0)
    figura = _figura_composicao_por_acao(comp, _cores_das_acoes(comp))
    assert figura.data[0].marker.colors[-1] == config.COR_NEUTRO
    assert list(figura.data[0].marker.colors[:7]) == list(config.CORES_ACOES_CARTEIRA)


def test_com_oito_acoes_a_oitava_vira_a_fatia_outras_sozinha():
    tabela = pd.DataFrame(
        {
            "ticker": [f"A{i}" for i in range(8)],
            "preco_atual": [10.0] * 8,
            "valor_combinado": [1.0] * 8,
        }
    )
    comp = compor_posicoes(tabela, {f"A{i}": 100 - i for i in range(8)})

    fatias = _fatias_da_composicao(comp)

    assert len(fatias) == 8 and fatias[-1][0] == "Outras"
    assert fatias[-1][1] == pytest.approx(10 * 93)


def test_ate_sete_acoes_nao_ha_fatia_outras():
    comp = _composicao({"AAA3": 1, "BBB4": 1, "CCC3": 1})

    assert "Outras" not in [f[0] for f in _fatias_da_composicao(comp)]


def test_composicao_por_setor_pesa_so_as_posicoes_com_setor_e_destaca_acima_de_cinquenta():
    comp = _composicao({"AAA3": 100, "BBB4": 50, "CCC3": 100, "DDD3": 10})

    pesos = _pesos_por_setor(comp)
    # Bancos 2.000, Energia 500; DDD3 (sem setor e sem preço) fica de fora.
    assert pesos.index.tolist() == ["Bancos", "Energia Elétrica"]
    assert pesos.tolist() == pytest.approx([80.0, 20.0])
    figura = _figura_composicao_por_setor(comp)
    barras = figura.data[0]
    assert list(barras.y) == ["Bancos", "Energia Elétrica"]
    assert list(barras.text) == ["80,0%", "20,0%"]
    assert list(barras.marker.color) == [config.COR_ALERTA, config.COR_PRINCIPAL]


def test_maior_setor_ate_cinquenta_por_cento_nao_fica_amarelo_e_sem_setor_nao_ha_grafico():
    comp = _composicao({"AAA3": 100, "CCC3": 200})  # Bancos 1.000, Energia 1.000: 50%

    barras = _figura_composicao_por_setor(comp).data[0]
    assert list(barras.marker.color) == [config.COR_PRINCIPAL, config.COR_PRINCIPAL]
    assert _figura_composicao_por_setor(_composicao({"DDD3": 5})) is None


def _linhas_html(html: str) -> list[list[str]]:
    corpo = html.split("<tbody>")[1]
    return [
        [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.DOTALL)]
        for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo, re.DOTALL)
    ]


def test_tabela_de_posicoes_tem_as_colunas_e_os_valores_por_posicao():
    html = _html_tabela_posicoes(_composicao({"AAA3": 100, "BBB4": 50}))

    cabecalho = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", html)
    assert cabecalho == list(config.ROTULOS_COLUNAS_POSICOES)
    linhas = _linhas_html(html)
    # Ação, Qtd., Preço, Investido, Combinado, Valor justo, Potencial, Peso
    assert linhas[0] == [
        "AAA3",
        "100",
        "R$ 10,00",
        "R$ 1.000,00",
        "R$ 15,00",
        "R$ 1.500,00",
        "+50,0%",
        "50,0%",
    ]
    assert linhas[1][6] == "-50,0%"
    assert "ab-div-barra ab-div-pos" in html and "ab-div-barra ab-div-neg" in html


def test_linha_de_total_soma_investido_e_valor_justo_so_das_posicoes_com_valor_combinado():
    html = _html_tabela_posicoes(_composicao({"AAA3": 100, "CCC3": 200}))

    linhas = _linhas_html(html)
    assert linhas[1][:1] == ["CCC3?"]  # o "?" traz o motivo
    assert linhas[1][4:7] == ["—", "—", "—"]  # sem valor combinado
    assert 'title="sem valor combinado"' in html
    total = linhas[-1]
    assert 'class="ab-linha-total"' in html
    # Investido 2.000 (as duas); valor justo 1.500 (só AAA3); potencial 50% sobre os 1.000.
    assert total[0] == "Total"
    assert total[3] == "R$ 2.000,00" and total[5] == "R$ 1.500,00"
    assert total[6] == "+50,0%?" and total[7] == "100,0%"  # o "?" explica a base do potencial


def _abrir_simulador(monkeypatch, tmp_path, com_setor=True) -> AppTest:
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
        | {"ticker": "DOBR4", "preco_atual": 40.0, "valor_combinado": 80.0}
        | {"graham_valor_justo": 80.0, "segmento_setorial": "Bancos" if com_setor else None},
        base
        | {"ticker": "NEGA4", "preco_atual": 10.0, "valor_combinado": 7.5}
        | {"graham_valor_justo": 20.0, "fcd_valor_justo": -5.0}
        | {"segmento_setorial": "Energia Elétrica" if com_setor else None},
        base | {"ticker": "SEMC3", "preco_atual": 10.0, "metodos_utilizados": ""},
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, config.TITULO_PAGINA_CARTEIRA)
    assert not at.exception
    return at


def _montar(at) -> None:
    adicionar_a_carteira(at, "DOBR4", 25)
    adicionar_a_carteira(at, "SEMC3", 30)
    adicionar_a_carteira(at, "NEGA4", 50)


def _tabela_posicoes_html(at) -> str:
    return next(h.proto.body for h in at.get("html") if "ab-tabela-posicoes" in h.proto.body)


def test_pagina_mostra_as_composicoes_a_tabela_de_posicoes_e_tira_a_tabela_larga(
    monkeypatch, tmp_path
):
    at = _abrir_simulador(monkeypatch, tmp_path)
    _montar(at)

    assert not at.exception
    graficos = [json.loads(g.proto.spec) for g in at.get("plotly_chart")]
    rosca = next(g for g in graficos if g["data"][0]["type"] == "pie")
    assert set(rosca["data"][0]["labels"]) == {"DOBR4", "SEMC3", "NEGA4"}  # a sem combinado entra
    assert any(
        g["data"][0].get("orientation") == "h" and "Bancos" in g["data"][0]["y"] for g in graficos
    )
    linhas = _linhas_html(_tabela_posicoes_html(at))
    assert [linha[0] for linha in linhas] == ["DOBR4", "SEMC3?", "NEGA4", "Total"]
    # A tabela larga de nove colunas saiu: não há mais `st.dataframe` com os valores por cenário.
    mostradas = [list(df.proto.column_order) for df in at.dataframe]
    assert mostradas == [
        [
            "ticker",
            "retorno_pessimista_percentual",
            "retorno_base_percentual",
            "retorno_otimista_percentual",
        ]
    ]


def test_cenarios_por_acao_ficam_num_expander_compacto_em_percentual(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    _montar(at)

    assert "Cenários por ação" in [e.label for e in at.expander]
    tabelas = [df for df in at.dataframe if "retorno_base_percentual" in df.value.columns]
    assert len(tabelas) == 1
    valor = tabelas[0].value.set_index("ticker")
    assert valor.loc["NEGA4", "retorno_pessimista_percentual"] == "-100,0%"
    assert valor.loc["NEGA4", "retorno_otimista_percentual"] == "100,0%"
    assert valor.loc["DOBR4", "retorno_base_percentual"] == "100,0%"
    assert "SEMC3" not in valor.index
    rotulos = json.loads(tabelas[0].proto.columns)
    assert [
        rotulos[c]["label"]
        for c in (
            "retorno_pessimista_percentual",
            "retorno_base_percentual",
            "retorno_otimista_percentual",
        )
    ] == ["Pessimista", "Base", "Otimista"]


def test_sem_setor_no_screener_a_composicao_por_setor_avisa(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path, com_setor=False)

    adicionar_a_carteira(at, "DOBR4", 25)

    assert [i.value for i in at.info if i.value == config.TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO]
    graficos = [json.loads(g.proto.spec) for g in at.get("plotly_chart")]
    assert not any(
        g["data"][0].get("orientation") == "h" and g["data"][0]["y"] == ["Bancos"] for g in graficos
    )


def test_linha_mais_de_cinquenta_por_cento_num_so_setor_aparece_quando_passa(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    adicionar_a_carteira(at, "DOBR4", 25)  # 100% em Bancos
    assert "Mais de 50% num só setor" in [c.value for c in at.caption]

    adicionar_a_carteira(at, "NEGA4", 100)  # Bancos 1.000, Energia 1.000: 50%, sem a linha
    assert "Mais de 50% num só setor" not in [c.value for c in at.caption]


def test_potencial_do_total_ganha_um_ponto_de_interrogacao_so_com_posicao_sem_combinado():
    com_sem_combinado = _html_tabela_posicoes(_composicao({"AAA3": 100, "CCC3": 200}))
    so_com_combinado = _html_tabela_posicoes(_composicao({"AAA3": 100, "BBB4": 50}))

    total_com = com_sem_combinado.split('class="ab-linha-total"')[1]
    total_sem = so_com_combinado.split('class="ab-linha-total"')[1]
    # Investido total R$ 2.000,00, mas o potencial é sobre R$ 1.000,00 (AAA3, com valor combinado).
    assert 'title="Sobre R$ 1.000,00 investidos em ações com valor combinado"' in total_com
    assert 'class="ab-ajuda"' not in total_sem
    # As linhas das posições não ganham esse "?" (o das sem valor combinado é outro).
    assert com_sem_combinado.count("Sobre R$ 1.000,00 investidos") == 1


def test_altura_do_grafico_de_contribuicao_acompanha_o_numero_de_acoes_com_minimo():
    from avaliador_b3.app.main import _figura_contribuicao_carteira

    def altura(n: int) -> int:
        tabela = pd.DataFrame(
            {
                "ticker": [f"A{i}" for i in range(n)],
                "valor_investido": [100.0] * n,
                "projecao_base": [100.0 + 10 * i for i in range(n)],
            }
        )
        return _figura_contribuicao_carteira(tabela).layout.height

    assert altura(1) == config.ALTURA_MINIMA_CONTRIBUICAO
    assert altura(2) == config.ALTURA_MINIMA_CONTRIBUICAO
    assert altura(6) == 6 * config.ALTURA_POR_BARRA_CONTRIBUICAO + 40
    assert altura(10) > altura(6) > altura(3)


def test_fatia_abaixo_de_5_por_cento_nao_mostra_o_percentual_dentro_mas_o_hover_sim():
    comp = _composicao({"AAA3": 1000, "BBB4": 1})
    pesos = comp.sort_values("investido", ascending=False)["peso_percentual"].tolist()
    assert pesos[1] < 5 <= pesos[0]

    rosca = _figura_composicao_por_acao(comp, _cores_das_acoes(comp)).data[0]

    assert list(rosca.labels) == ["AAA3", "BBB4"]
    assert list(rosca.text) == [f"{pesos[0]:.1f}%".replace(".", ","), ""]
    assert [c.split("(")[1] for c in rosca.customdata] == [
        f"{p:.1f}%)".replace(".", ",") for p in pesos
    ]


def test_rosca_com_uma_acao_so_usa_virgula_decimal_no_rotulo_e_no_hover():
    comp = _composicao({"AAA3": 100})

    rosca = _figura_composicao_por_acao(comp, _cores_das_acoes(comp)).data[0]

    assert list(rosca.text) == ["100,0%"]
    assert list(rosca.customdata) == ["R$ 1.000,00 (100,0%)"]
    assert rosca.hovertemplate == "%{label}: %{customdata}<extra></extra>"
