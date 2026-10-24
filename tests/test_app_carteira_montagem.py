"""Montagem da carteira do Simulador na barra lateral: campos, posições, "×", "Limpar carteira" e
a carteira guardada ao trocar de página."""

import re

import pandas as pd
import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import _adicionar_posicao_da_carteira, _investimentos_da_carteira
from avaliador_b3.config import (
    CHAVE_CARTEIRA_POSICOES,
    CHAVE_CARTEIRA_REMOVER_PREFIXO,
    QUANTIDADE_PADRAO_CARTEIRA,
    ROTULO_ADICIONAR_A_CARTEIRA,
    ROTULO_CARTEIRA_ACAO,
    ROTULO_CARTEIRA_QUANTIDADE,
    ROTULO_LIMPAR_CARTEIRA,
    TEXTO_CARTEIRA_VAZIA,
    TEXTO_SEM_CENARIO_SINGULAR,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
)
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina, adicionar_a_carteira


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
    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)
    assert not at.exception
    return at


def _linhas_das_posicoes(at) -> list[list[str]]:
    """Linhas da tabela "Posições" (HTML), com a de Total no fim, como listas de textos."""
    html = next(h.proto.body for h in at.get("html") if "ab-tabela-posicoes" in h.proto.body)
    corpo = html.split("<tbody>")[1]
    return [
        [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.DOTALL)]
        for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo, re.DOTALL)
    ]


def _posicoes_na_barra(at) -> list[str]:
    return [m.value for m in at.sidebar.markdown if "×" in m.value]


def _botao(at, rotulo: str):
    return next(b for b in at.sidebar.button if b.label == rotulo)


def test_campos_de_montagem_ficam_na_barra_lateral_so_na_pagina_do_simulador(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    acao = at.sidebar.selectbox[0]
    assert acao.label == ROTULO_CARTEIRA_ACAO and acao.value is None
    assert acao.options == ["DOBR4", "NEGA4", "SEMC3"]
    quantidade = at.sidebar.number_input[0]
    assert quantidade.label == ROTULO_CARTEIRA_QUANTIDADE
    assert quantidade.value == QUANTIDADE_PADRAO_CARTEIRA
    assert (quantidade.min, quantidade.step) == (1, 1)
    assert _botao(at, ROTULO_ADICIONAR_A_CARTEIRA).disabled  # sem ação escolhida
    assert ROTULO_LIMPAR_CARTEIRA not in [b.label for b in at.sidebar.button]
    assert [i.value for i in at.info if i.value == TEXTO_CARTEIRA_VAZIA]
    assert not at.multiselect  # o multiselect antigo saiu da página

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    assert ROTULO_ADICIONAR_A_CARTEIRA not in [b.label for b in at.sidebar.button]


def test_adicionar_poe_a_posicao_na_lista_e_na_carteira(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    adicionar_a_carteira(at, "DOBR4", 25)

    assert _posicoes_na_barra(at) == ["**DOBR4** × 25"]
    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {"DOBR4": 25}
    # Investido = quantidade × preço do screener: 25 × R$ 40,00.
    linhas = _linhas_das_posicoes(at)
    assert linhas[0][0] == "DOBR4" and linhas[0][1] == "25" and linhas[0][3] == "R$ 1.000,00"


def test_adicionar_uma_acao_que_ja_esta_na_carteira_soma_a_quantidade(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    adicionar_a_carteira(at, "DOBR4", 25)
    adicionar_a_carteira(at, "DOBR4", 10)

    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {"DOBR4": 35}
    assert _posicoes_na_barra(at) == ["**DOBR4** × 35"]


def test_o_x_remove_so_aquela_posicao_e_limpar_carteira_remove_todas(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    adicionar_a_carteira(at, "DOBR4", 25)
    adicionar_a_carteira(at, "NEGA4", 50)

    at.sidebar.button(key=CHAVE_CARTEIRA_REMOVER_PREFIXO + "DOBR4").click().run(timeout=60)
    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {"NEGA4": 50}

    _botao(at, ROTULO_LIMPAR_CARTEIRA).click().run(timeout=60)
    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {}
    assert _posicoes_na_barra(at) == []
    assert ROTULO_LIMPAR_CARTEIRA not in [b.label for b in at.sidebar.button]
    assert [i.value for i in at.info if i.value == TEXTO_CARTEIRA_VAZIA]


def test_campo_de_quantidade_e_inteiro_a_partir_de_um(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    quantidade = at.sidebar.number_input[0]
    assert isinstance(quantidade.value, int)
    assert (quantidade.min, quantidade.step) == (1, 1)


@pytest.mark.parametrize("quantidade", [0, -3, None])
def test_quantidade_invalida_nao_muda_a_carteira(monkeypatch, quantidade):
    estado = {"carteira_acao": "DOBR4", "carteira_quantidade": quantidade}
    monkeypatch.setattr(streamlit, "session_state", estado)

    _adicionar_posicao_da_carteira()

    assert CHAVE_CARTEIRA_POSICOES not in estado


def test_quantidade_valida_soma_a_posicao_existente(monkeypatch):
    estado = {
        "carteira_acao": "DOBR4",
        "carteira_quantidade": 10,
        CHAVE_CARTEIRA_POSICOES: {"DOBR4": 25},
    }
    monkeypatch.setattr(streamlit, "session_state", estado)

    _adicionar_posicao_da_carteira()

    assert estado[CHAVE_CARTEIRA_POSICOES] == {"DOBR4": 35}


def test_carteira_continua_ao_trocar_de_pagina_e_voltar(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    adicionar_a_carteira(at, "DOBR4", 25)
    adicionar_a_carteira(at, "NEGA4", 50)

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    abrir_pagina(at, TITULO_PAGINA_CARTEIRA)

    assert not at.exception
    assert _posicoes_na_barra(at) == ["**DOBR4** × 25", "**NEGA4** × 50"]
    assert [linha[0] for linha in _linhas_das_posicoes(at)[:-1]] == ["DOBR4", "NEGA4"]


def test_acao_sem_valor_combinado_fica_marcada_na_lista(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    adicionar_a_carteira(at, "SEMC3", 30)

    assert _posicoes_na_barra(at) == ["**SEMC3** × 30 · sem valor combinado"]
    assert not at.warning
    legenda = TEXTO_SEM_CENARIO_SINGULAR.format(tickers="SEMC3")
    assert [c.value for c in at.caption].count(legenda) == 1


def test_acao_que_saiu_do_screener_fica_na_lista_marcada_e_fora_das_contas(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)
    adicionar_a_carteira(at, "DOBR4", 25)

    at.session_state[CHAVE_CARTEIRA_POSICOES] = {"DOBR4": 25, "SUMIU3": 7}
    at.run(timeout=60)

    assert not at.exception
    # A posição continua guardada e na lista, marcada; o aviso diz que ela não entra nas contas.
    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {"DOBR4": 25, "SUMIU3": 7}
    assert _posicoes_na_barra(at) == ["**DOBR4** × 25", "**SUMIU3** × 7 · fora do screener atual"]
    avisos = [w.value for w in at.warning if "Fora do screener atual" in w.value]
    assert avisos == ["Fora do screener atual, sem entrar nas contas: SUMIU3."]
    assert [linha[0] for linha in _linhas_das_posicoes(at)[:-1]] == ["DOBR4"]
    assert app._kpi_por_rotulo(at, "Valor investido")["valor"] == "R$ 1.000,00"
    # Dá para tirá-la com o "×" mesmo fora do screener.
    at.sidebar.button(key=CHAVE_CARTEIRA_REMOVER_PREFIXO + "SUMIU3").click().run(timeout=60)
    assert at.session_state[CHAVE_CARTEIRA_POSICOES] == {"DOBR4": 25}
    assert not [w for w in at.warning if "Fora do screener atual" in w.value]


def test_so_com_acao_fora_do_screener_a_pagina_avisa_e_pede_posicoes(monkeypatch, tmp_path):
    at = _abrir_simulador(monkeypatch, tmp_path)

    at.session_state[CHAVE_CARTEIRA_POSICOES] = {"SUMIU3": 7}
    at.run(timeout=60)

    assert not at.exception
    assert [w.value for w in at.warning if "Fora do screener atual" in w.value]
    assert [i.value for i in at.info if i.value == TEXTO_CARTEIRA_VAZIA]
    assert ROTULO_LIMPAR_CARTEIRA in [b.label for b in at.sidebar.button]


def test_investido_e_quantidade_vezes_preco_e_zero_sem_preco():
    tabela = pd.DataFrame(
        {"ticker": ["AAA3", "BBB4", "CCC3"], "preco_atual": [40.0, None, float("nan")]}
    )

    investimentos = _investimentos_da_carteira(tabela, {"AAA3": 25, "BBB4": 10, "CCC3": 1})

    assert investimentos == {"AAA3": 1000.0, "BBB4": 0.0, "CCC3": 0.0}
