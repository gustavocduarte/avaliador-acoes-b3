"""Testes do dashboard Streamlit (app/main.py) via `streamlit.testing.v1.AppTest`
— roda o script de verdade (mesmo runner que `streamlit run` usa por baixo),
sem precisar de navegador. Cobre a degradação graciosa do dropdown de ticker
na aba "Analisar uma ação" (ver a investigação e o teste manual no navegador
— URL de `obter_universo_ibovespa` apontada pra um domínio inválido de
propósito, revertida depois — que motivou o teste original) e, desde
2026-09-16, a pré-seleção + busca automática de PETR4 só na primeira
abertura da sessão (ver `TICKER_PADRAO_PRIMEIRA_ABERTURA` em app/main.py).

Como a busca automática da primeira abertura dispara o mesmo fluxo de
"Buscar" de verdade (preço, indicadores, dividendos, CNPJ, macro e, desde
que a Correlação com fatores externos passou a viver dentro desta aba,
também petróleo/câmbio/GPR), os testes que passam pelo carregamento
inicial da aba com o universo disponível também mockam essas fontes pra
continuarem rápidos e determinísticos, sem rede de verdade — ver
`_bloquear_buscas_de_rede_por_ticker`.
"""

import json
import re
import warnings
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from avaliador_b3.config import (
    ANOS_JANELA_CORRELACAO,
    TICKER_PETROLEO_BRENT,
    YIELD_MINIMO_BAZIN,
)
from avaliador_b3.ingest.cvm import CnpjNaoEncontrado
from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado
from avaliador_b3.ingest.precos import TickerInvalido
from avaliador_b3.screener import DeteccaoAnoCvmFalhouWarning

# Ano fixo usado pelos mocks de FCD abaixo — substitui ANO_REFERENCIA_FCD
# (removida em 2026-09-23, ver docs/correcao-ano-fcd-2026-09-23.md), já
# que o ano agora é detectado em tempo de execução
# (`ingest.cvm.resolver_ano_mais_recente_disponivel`), não uma constante.
ANO_FCD_MOCK = 2025

# Caminho absoluto: AppTest.from_file resolve caminho relativo contra o
# arquivo que CHAMA from_file (este arquivo de teste), não contra o cwd do
# pytest — relativo a "tests/" ficaria errado.
CAMINHO_APP = str(Path(__file__).resolve().parents[1] / "src/avaliador_b3/app/main.py")

# Mensagem de erro usada nos mocks abaixo — de propósito sem a palavra
# "indispon" (de "indisponível"), pra não colidir com a asserção que checa
# especificamente o aviso de dropdown indisponível em outro teste.
MENSAGEM_ERRO_MOCK = "falha simulada (mock de teste, sem rede)"


@pytest.fixture(autouse=True)
def _limpar_cache_streamlit():
    """`st.cache_data` guarda o resultado numa memória global do processo,
    não por execução do AppTest — sem limpar entre testes, o segundo teste
    leria o resultado (bom ou com falha) já cacheado pelo primeiro, em vez
    de chamar `obter_universo_ibovespa` (mockado de novo) de verdade."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _universo_falso() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["PETR4", "VALE3"],
            "nome": ["PETROBRAS", "VALE S.A."],
            "segmento_listagem": ["Nível 2", "Novo Mercado"],
            "tipo_bruto": ["PN N2", "ON NM"],
        }
    )


def _catalogo_emissores_vazio() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["codigo_emissor", "codigo_cvm", "cnpj", "nome_empresa", "segmento_setorial"]
    )


def _bloquear_buscas_de_rede_por_ticker(monkeypatch) -> None:
    """Mocka todas as fontes externas chamadas dentro do fluxo de "Buscar"
    (preço/histórico, indicadores do Fundamentus, dividendos, catálogo de
    emissores da B3, Selic/IPCA/câmbio do BCB e o índice GPR) pra levantar
    rapidamente o mesmo tipo de erro "não encontrado"/"falha" que cada uma
    já trataria de verdade — mantém os testes que agora disparam a busca
    automática da primeira abertura (que hoje também inclui a correlação
    com fatores externos, movida pra dentro desta aba) tão rápidos e
    determinísticos quanto eram antes."""

    def _falha_precos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico_ibovespa", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_precos)

    def _falha_fundamentus(*args, **kwargs):
        raise TickerNaoEncontrado(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.fundamentus.obter_indicadores", _falha_fundamentus)

    # Catálogo vazio (não uma exceção genérica) porque `_buscar_cnpj` só
    # trata `EmissorNaoEncontrado` — um catálogo vazio faz `resolver_cnpj`
    # levantar esse erro naturalmente, sem precisar de rede nenhuma.
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )

    def _falha_macro(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _falha_macro)
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_macro)


def _metrica_por_label(at, rotulo: str):
    """Acha o único `st.metric` com esse `label` na árvore de elementos de
    `at` — levanta `AssertionError` se não achar exatamente um (rótulo
    ausente ou duplicado), em vez de devolver uma lista pro chamador
    filtrar/indexar na mão."""
    metricas = [metrica for metrica in at.metric if metrica.label == rotulo]
    assert len(metricas) == 1, f"métrica {rotulo!r} não encontrada (ou duplicada)"
    return metricas[0]


def test_dropdown_lista_acoes_do_ibovespa_quando_universo_disponivel(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    # A busca automática da primeira abertura (PETR4) dispara nesse mesmo
    # `at.run()` — sem isso, os `_buscar_*` do fluxo de "Buscar" tentariam
    # rede de verdade.
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].label == "Ação (Ibovespa)"
    assert any("PETR4" in opcao and "PETROBRAS" in opcao for opcao in at.selectbox[0].options)
    assert not any("indispon" in aviso.value.lower() for aviso in at.warning)


def test_cai_pro_campo_de_texto_livre_quando_universo_falha(monkeypatch):
    # Reproduz o cenário confirmado manualmente no navegador (API da B3 fora
    # do ar): a aba não pode travar, tem que degradar pro texto livre com um
    # aviso claro nomeando o motivo.
    def falha(**kwargs):
        raise RuntimeError("falha simulada de rede")

    monkeypatch.setattr("avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", falha)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert len(at.selectbox) == 0

    rotulos_texto = [ti.label for ti in at.text_input]
    assert "Ticker (ex: PETR4)" in rotulos_texto

    avisos = [aviso.value for aviso in at.warning]
    assert any(
        "indisponível" in aviso and "falha simulada de rede" in aviso for aviso in avisos
    )


# --- Busca automática de PETR4 na primeira abertura da sessão --------------


def test_primeira_abertura_pre_seleciona_e_busca_petr4_automaticamente(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    # Dropdown já nasce com PETR4 selecionado (não o placeholder) ...
    assert at.selectbox[0].value == "PETR4"
    # ... e a busca já rodou sozinha nesse mesmo carregamento, sem precisar
    # clicar em "Buscar" — confirmado pelo subheader com o ticker, que só
    # aparece depois de `if buscar and ticker:` em app/main.py.
    assert any(subheader.value == "PETR4" for subheader in at.subheader)
    assert at.session_state["busca_inicial_automatica_feita"] is True


def test_depois_da_busca_automatica_fluxo_volta_a_ser_100_por_cento_manual(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    assert any(subheader.value == "PETR4" for subheader in at.subheader)

    # Trocar a ação selecionada, sozinho, não deve disparar nova busca
    # automática — a flag em session_state já foi consumida na abertura.
    # Sem clicar em "Buscar", o bloco de resultado não roda de novo nesse
    # rerun (mesmo comportamento de qualquer troca de ação sem busca) —
    # não aparece nem o resultado antigo (PETR4) nem um novo (VALE3).
    at.selectbox[0].select("VALE3").run(timeout=60)

    assert not at.exception
    assert at.selectbox[0].value == "VALE3"
    assert not any(subheader.value == "PETR4" for subheader in at.subheader)
    assert not any(subheader.value == "VALE3" for subheader in at.subheader)

    # Só depois do clique manual em "Buscar" é que a busca de VALE3 roda —
    # fluxo 100% manual de novo, igual a antes da mudança.
    at.button[0].click().run(timeout=60)

    assert not at.exception
    assert any(subheader.value == "VALE3" for subheader in at.subheader)


# --- Histórico "vazio mas sem exceção" vira erro tratado (_buscar_historico) -


def test_historico_vazio_sem_excecao_vira_erro_tratado_nao_crash(monkeypatch):
    # Regressão: obter_historico devolvendo um DataFrame vazio SEM
    # levantar exceção (teoricamente só possível com um cache em disco
    # corrompido/truncado — o caminho de busca nova já levanta
    # TickerInvalido nesse caso, ver ingest/precos.py) chegava até
    # `preco_atual = float(historico_preco_atual["Close"].iloc[-1])` sem
    # nenhum guard — IndexError cru, não tratado. _buscar_historico/
    # _buscar_historico_ibovespa agora tratam DataFrame vazio como erro,
    # mesmo par (None, motivo) de uma exceção real.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )

    def _historico_vazio(*args, **kwargs):
        return pd.DataFrame(columns=["data", "Close", "Volume"])

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", _historico_vazio)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico_ibovespa", _historico_vazio)

    def _falha_fundamentus(*args, **kwargs):
        raise TickerNaoEncontrado(MENSAGEM_ERRO_MOCK)

    def _falha_dividendos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    def _falha_macro(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.fundamentus.obter_indicadores", _falha_fundamentus)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_dividendos)
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _falha_macro)
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_macro)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    # "Preço atual" não é mostrado (mesmo caminho de erro_preco_atual real)...
    assert not any(metrica.label == "Preço atual" for metrica in at.metric)
    # ... e o motivo aparece como erro tratado, não um traceback cru.
    assert any("veio vazio" in erro.value for erro in at.error)


# --- "Preço atual" usa período separado do histórico de comportamento -------


def _historico_por_periodo(fechamentos_por_periodo: dict[str, float]):
    """Fake de `obter_historico` que devolve um Close DIFERENTE conforme o
    `periodo` pedido — usado pra provar que "Preço atual" e o histórico de
    volume/volatilidade vêm de buscas (períodos) separadas, não da mesma."""

    def _fake(ticker, periodo="3mo", auto_adjust=True, **kwargs):
        if periodo not in fechamentos_por_periodo:
            raise TickerInvalido(MENSAGEM_ERRO_MOCK)
        return pd.DataFrame(
            {
                "data": pd.to_datetime(["2026-09-15"], utc=True),
                "Close": [fechamentos_por_periodo[periodo]],
                "Volume": [30_000_000],
            }
        )

    return _fake


def test_preco_atual_usa_periodo_separado_do_historico_de_3_meses(monkeypatch):
    # Regressão: o histórico diário mais longo (period="3mo", usado pra
    # volume/volatilidade) atrasa um pregão inteiro no yfinance, mesmo já
    # encerrado — descoberto comparando "Preço atual" contra o preço ao
    # vivo do widget do TradingView (PETR4: R$ 48,92 no card vs. R$ 50,43
    # no TradingView, um pregão inteiro de defasagem). "Preço atual"
    # precisa vir de PERIODO_PRECO_ATUAL ("1d"), não do mesmo histórico
    # usado pra volume/volatilidade — os dois têm valores DIFERENTES aqui
    # de propósito, pra provar que vêm de buscas separadas.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo({"1d": 50.43, "3mo": 48.92, "1y": 48.92}),
    )

    def _falha_fundamentus(*args, **kwargs):
        raise TickerNaoEncontrado(MENSAGEM_ERRO_MOCK)

    def _falha_dividendos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    def _falha_macro(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.fundamentus.obter_indicadores", _falha_fundamentus)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_dividendos)
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _falha_macro)
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_macro)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Preço atual").value == "R$ 50,43"


# --- Correlação com fatores externos, movida pra dentro de "Analisar uma ---
# --- ação" (não é mais uma aba separada) -------------------------------------


def test_correlacao_nao_e_mais_uma_aba_separada_e_aparece_sem_clique_extra(monkeypatch):
    # A antiga aba "Correlação com fatores externos" foi removida — a
    # seção agora mora dentro de "Analisar uma ação" e aparece junto do
    # resto, reaproveitando o ticker já buscado ali. Confirmado logo no
    # primeiro carregamento da sessão (busca automática de PETR4), sem
    # precisar de nenhum clique extra.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert "Correlação com fatores externos" not in [tab.label for tab in at.tabs]
    assert any(
        subheader.value == "Correlação com fatores externos" for subheader in at.subheader
    )


# --- Delta (%) de upside nos cards de valor justo -----------------------------


def _indicadores_falsos_aplicavel_pra_graham() -> dict:
    return {
        "lpa": 5.0,
        "vpa": 20.0,
        "numero_acoes": 1_000_000.0,
        "divida_liquida_sobre_patrimonio": 0.5,
        "roe_percentual": 15.0,
        "margem_liquida_percentual": 10.0,
        "liquidez_corrente": 1.2,
        "crescimento_receita_5a_percentual": 8.0,
        "patrimonio_liquido": 20_000_000.0,
        "divida_liquida": 10_000_000.0,
        "data_balanco_fundamentus": "2026-06-30",
    }


def test_card_de_valor_justo_mostra_delta_so_quando_aplicavel(monkeypatch):
    # Graham aplicável (LPA/VPA válidos) mostra o delta % de upside contra
    # o preço atual; Bazin não aplicável (sem dividendo) não mostra delta
    # nenhum — mesmo espírito do caso real ABEV3 (um método não aplicável)
    # conferido manualmente no navegador.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": 50.0, "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )

    def _falha_precos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    def _falha_rt(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico_ibovespa", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_precos)
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: _indicadores_falsos_aplicavel_pra_graham(),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _falha_rt)
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_rt)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    # Graham = raiz(22,5 × 5 × 20) ≈ 47,43; preço 50 -> delta ≈ -5,1%.
    metrica_graham = _metrica_por_label(at, "Graham")
    assert metrica_graham.value == "R$ 47,43"
    assert metrica_graham.delta == "-5,1%"

    assert not _metrica_por_label(at, "Bazin (preço teto)").delta


def _preparar_fcd_aplicavel(
    monkeypatch,
    divida_liquida: float | None,
    segmento_setorial: str = "Petróleo, Gás e Biocombustíveis",
) -> None:
    """Configura mocks pro FCD ficar 'aplicável' de verdade — diferente
    dos outros testes deste arquivo (que mockam `obter_catalogo_
    emissores` vazio via `_bloquear_buscas_de_rede_por_ticker`, o que faz
    `resolver_cnpj` sempre falhar e o FCD ficar sempre 'não aplicável'
    antes de chegar no cálculo), aqui `resolver_cnpj` e `obter_fluxo_
    caixa_livre` são mockados com sucesso, de propósito. `segmento_
    setorial` default é não-financeiro (o "aplicável" no nome da função
    só vale pra esse caso) — passar "Bancos" testa a exclusão."""
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": 50.0, "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: {
            "lpa": 5.0,
            "vpa": 20.0,
            "numero_acoes": 100.0,
            "roe_percentual": 15.0,
            "margem_liquida_percentual": 10.0,
            "liquidez_corrente": 1.2,
            "crescimento_receita_5a_percentual": 8.0,
            "divida_liquida_sobre_patrimonio": 0.5,
            "divida_liquida": divida_liquida,
            "data_balanco_fundamentus": "2026-06-30",
        },
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.resolver_cnpj",
        lambda ticker, catalogo: {
            "ticker": ticker,
            "codigo_emissor": "PETR",
            "cnpj": "33000167000101",
            "codigo_cvm": "009512",
            "nome_empresa": "PETROBRAS",
            "segmento_setorial": segmento_setorial,
        },
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.resolver_ano_mais_recente_disponivel",
        lambda **kwargs: ANO_FCD_MOCK,
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre",
        lambda cnpj, ano, *a, **kw: {
            "fcf_atual": 1_000_000.0 if ano == ANO_FCD_MOCK else 800_000.0
        },
    )
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _obter_serie_bcb_falso)


def test_fcd_nao_mostra_aviso_quando_divida_liquida_esta_disponivel(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != "—"

    avisos_divida = [c.value for c in at.caption if "Dívida líquida indisponível" in c.value]
    assert avisos_divida == []


def test_fcd_mostra_aviso_quando_divida_liquida_esta_ausente(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != "—"

    avisos_divida = [c.value for c in at.caption if "Dívida líquida indisponível" in c.value]
    assert len(avisos_divida) == 1
    assert "tende a ficar mais alto" in avisos_divida[0]


def test_fcd_mostra_rotulo_do_ano_normal_quando_empresa_esta_no_ano_mais_recente(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    rotulos_ano = [c.value for c in at.caption if "demonstração financeira anual de" in c.value]
    assert len(rotulos_ano) == 1
    assert (
        rotulos_ano[0]
        == f"FCD calculado com a demonstração financeira anual de {ANO_FCD_MOCK} (CVM)."
    )


def test_fcd_mostra_rotulo_de_fallback_quando_empresa_nao_esta_no_ano_mais_recente(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    def obter_fluxo_caixa_livre_com_fallback(cnpj, ano, *args, **kwargs):
        if ano == ANO_FCD_MOCK:
            raise CnpjNaoEncontrado("não encontrado no ano mais recente")
        return {"fcf_atual": 800_000.0}

    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre", obter_fluxo_caixa_livre_com_fallback
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    rotulos_ano = [c.value for c in at.caption if "demonstração financeira anual de" in c.value]
    assert len(rotulos_ano) == 1
    assert rotulos_ano[0] == (
        f"FCD calculado com a demonstração financeira anual de {ANO_FCD_MOCK - 1} (CVM) — "
        f"a de {ANO_FCD_MOCK} ainda não foi entregue por essa empresa."
    )


# --- Bloco "Datas de referência dos dados usados" (investigação de
# 2026-09-24: preço/beta/IPCA vêm de datas diferentes entre si e do
# balanço usado pelos indicadores do Fundamentus — não é bug, é o padrão
# de mercado, mas ficava invisível na tela até este bloco). Os mocks de
# `_preparar_fcd_aplicavel` (via `_historico_por_periodo`) fixam a mesma
# data (2026-09-15) pra preço E beta — não testa datas DIFERENTES entre
# os dois (isso é conteúdo do próprio yfinance, não da lógica deste
# bloco), só que cada valor é extraído e mostrado corretamente.


def test_bloco_datas_referencia_mostra_as_datas_certas(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [m.value for m in at.markdown if "Comparar o preço de hoje" in m.value]
    assert len(blocos) == 1
    bloco = blocos[0]
    assert "último fechamento: 15/09/2026." in bloco
    assert "balanço de 30/06/2026:" in bloco
    assert f"demonstração financeira anual de {ANO_FCD_MOCK} (CVM)." in bloco
    assert "1 ano de pregões até 15/09/2026." in bloco
    assert "acumulado até 12/2025." in bloco
    assert "sempre calculados com a data de hoje." in bloco


def test_bloco_datas_referencia_mostra_nd_quando_fundamentus_falha(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    def indicadores_falha(*args, **kwargs):
        raise TickerNaoEncontrado(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.fundamentus.obter_indicadores", indicadores_falha)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    bloco = next(m.value for m in at.markdown if "Comparar o preço de hoje" in m.value)
    assert "balanço de N/D:" in bloco
    # O resto do bloco não depende do Fundamentus — continua com data real,
    # a falha não deveria "vazar" pras outras linhas.
    assert "último fechamento: 15/09/2026." in bloco


def test_bloco_datas_referencia_fcd_nao_aplicavel_mostra_nao_aplicavel(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    bloco = next(m.value for m in at.markdown if "Comparar o preço de hoje" in m.value)
    assert "**FCD** — não aplicável." in bloco


def test_fcd_banco_fica_nao_aplicavel_e_combinado_usa_so_graham_bazin(monkeypatch):
    # Correção de 2026-09-23: segmento "Bancos" -> FCD "não aplicável",
    # mesmo padrão de Graham/Bazin quando não se aplicam (não é erro nem
    # exceção, é um resultado explícito). Bazin mockado com histórico
    # válido de dividendo (diferente da fixture padrão de
    # _preparar_fcd_aplicavel, que deixa obter_dividendos falhando) pra
    # confirmar que o combinado vira a média de Graham+Bazin só, sem FCD.
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")

    # Um pagamento em 1/dez de cada um dos últimos 5 anos civis — sem
    # lacuna, e o mais recente dentro dos últimos 12 meses (mesmo padrão
    # de tests/test_bazin.py), pra Bazin ficar "aplicável" de verdade.
    ano_atual = pd.Timestamp.now().year
    dividendos_validos = pd.DataFrame(
        {
            "data": [pd.Timestamp(year=ano_atual - i, month=12, day=1) for i in range(1, 6)],
            "dividendo": [1.0] * 5,
        }
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos",
        lambda *args, **kwargs: dividendos_validos,
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    metrica_fcd = _metrica_por_label(at, "FCD")
    assert metrica_fcd.value == "—"

    avisos_fcd = [c.value for c in at.caption if "Instituição financeira" in c.value]
    assert len(avisos_fcd) == 1
    assert "Graham e Bazin continuam válidos" in avisos_fcd[0]

    # Graham: raiz(22,5 × 5 × 20) ≈ 47,4342; Bazin: 1,0/0,06 ≈ 16,6667.
    # Combinado sem FCD = média dos dois ≈ 32,05 — bem diferente do que
    # sairia se o FCD (não aplicável aqui) entrasse na conta.
    valor_combinado_esperado = ((22.5 * 5 * 20) ** 0.5 + 1.0 / 0.06) / 2
    texto_combinado = _metrica_por_label(at, "Valor combinado").value
    valor_combinado_exibido = float(
        texto_combinado.replace("R$ ", "").replace(".", "").replace(",", ".")
    )
    assert valor_combinado_exibido == pytest.approx(valor_combinado_esperado, abs=0.01)


# --- Divergência entre os métodos (caption no cartão "Valor combinado") ---


def _preparar_banco_com_graham_e_bazin_aplicaveis(monkeypatch):
    """Mesmo setup de `test_fcd_banco_fica_nao_aplicavel_e_combinado_usa_
    so_graham_bazin` acima — FCD não aplicável (banco), Bazin aplicável
    com histórico de dividendo controlado — reaproveitado aqui porque dá
    valores EXATOS e conhecidos pros 2 métodos que sobram (Graham ≈
    47,4342, Bazin ≈ 16,6667), então a divergência esperada também é
    exata, não precisa de tolerância larga pra um cálculo indireto via
    FCD (que depende de beta/WACC, mais difícil de prever à mão)."""
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")
    ano_atual = pd.Timestamp.now().year
    dividendos_validos = pd.DataFrame(
        {
            "data": [pd.Timestamp(year=ano_atual - i, month=12, day=1) for i in range(1, 6)],
            "dividendo": [1.0] * 5,
        }
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos",
        lambda *args, **kwargs: dividendos_validos,
    )


def test_caption_divergencia_aparece_com_dois_metodos_aplicaveis(monkeypatch):
    _preparar_banco_com_graham_e_bazin_aplicaveis(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    # Graham ≈ 47,4342; Bazin ≈ 16,6667; preço fixado em 50,0 pelo mock de
    # _preparar_fcd_aplicavel — diferença ≈ 30,7675, ≈ 61,53% do preço.
    graham = (22.5 * 5 * 20) ** 0.5
    bazin = 1.0 / 0.06
    pct_esperado = round((graham - bazin) / 50.0 * 100)

    divergencias = [
        c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value
    ]
    assert len(divergencias) == 1
    assert f"{pct_esperado}% do preço atual" in divergencias[0]
    assert "Quanto maior essa diferença, menos os métodos concordam entre si." in divergencias[0]


def test_caption_divergencia_some_com_um_so_metodo_aplicavel(monkeypatch):
    # Banco (FCD não aplicável) + dividendos indisponíveis (mock padrão de
    # _bloquear_buscas_de_rede_por_ticker, sem override) -> só Graham
    # sobra. Sem 2+ métodos, a caption de divergência não faz sentido e
    # não deve aparecer.
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value == "—"
    divergencias = [
        c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value
    ]
    assert divergencias == []


def test_caption_divergencia_sem_preco_atual_mostra_variante_sem_percentual(monkeypatch):
    _preparar_banco_com_graham_e_bazin_aplicaveis(monkeypatch)
    # Sobrescreve só o período "1d" (Preço atual) pra falhar -- os demais
    # (usados por Beta/correlação/etc.) continuam OK, então Graham/Bazin
    # seguem aplicáveis normalmente, só preco_atual vira None.
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo({"3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    divergencias = [
        c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value
    ]
    assert len(divergencias) == 1
    assert "de diferença)." in divergencias[0]
    assert "% do preço atual" not in divergencias[0]


def test_expander_valor_combinado_usa_yield_da_constante(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [m.value for m in at.markdown if "**Valor combinado**" in m.value]
    assert len(blocos) == 1
    bloco = blocos[0]
    assert f"receber {YIELD_MINIMO_BAZIN:.0%} ao ano em dividendos" in bloco
    assert "não porque exista evidência de que os três acertam igualmente" in bloco
    assert "leia o combinado junto com os valores individuais, não sozinho." in bloco


def test_expander_bazin_menciona_que_fonte_nao_distingue_extraordinario(monkeypatch):
    # Investigação de 2026-09-25 (achado em revisão externa): o preço teto
    # do Bazin soma os dividendos dos últimos 12 meses sem distinguir
    # pagamento ordinário de extraordinário — o parágrafo do Bazin no
    # expander precisa deixar essa limitação da fonte explícita.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [m.value for m in at.markdown if "**Valor combinado**" in m.value]
    assert len(blocos) == 1
    bloco = blocos[0]
    assert (
        "A fonte dos dividendos (Yahoo Finance) não distingue pagamentos "
        "ordinários de extraordinários" in bloco
    )
    assert (
        "um provento pontual grande (como um dividendo especial) entra na "
        "mesma soma dos últimos 12 meses e pode inflar o preço teto" in bloco
    )


# --- Sinal de dividendos atípicos no cartão do Bazin (razão 12m vs. mediana) -


def _dividendos_com_razao(ano_atual: int, dividendo_12m: float, dividendo_anos_anteriores: float):
    """5 pagamentos anuais (1/dez), o mais recente com `dividendo_12m`
    (dentro dos últimos 12 meses a partir de 'hoje') e os 4 anteriores com
    `dividendo_anos_anteriores` cada — mesmo padrão de tests/test_bazin.py.
    Como só 1 dos 5 valores difere, a mediana dos totais anuais continua
    sendo `dividendo_anos_anteriores`, então a razão esperada é sempre
    `dividendo_12m / dividendo_anos_anteriores`, sem precisar recalcular a
    mediana à mão em cada teste."""
    return pd.DataFrame(
        {
            "data": [pd.Timestamp(year=ano_atual - i, month=12, day=1) for i in range(1, 6)],
            "dividendo": [dividendo_12m] + [dividendo_anos_anteriores] * 4,
        }
    )


def test_caption_dividendos_atipicos_aparece_acima_do_corte(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")
    ano_atual = pd.Timestamp.now().year
    # Razão = 3,0/1,0 = 3,0 (300%) -- acima do corte de 2,0
    # (RAZAO_DIVIDENDOS_ATIPICA_BAZIN).
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos",
        lambda *args, **kwargs: _dividendos_com_razao(ano_atual, 3.0, 1.0),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        c.value for c in at.caption if "Dividendos dos últimos 12 meses em" in c.value
    ]
    assert len(avisos) == 1
    assert "Dividendos dos últimos 12 meses em 300% da mediana dos 5 anos anteriores." in avisos[0]
    assert "Pode ser crescimento real dos pagamentos ou um pagamento extraordinário" in avisos[0]
    assert "a fonte não permite distinguir" in avisos[0]
    assert "Se for extraordinário, o preço teto está inflado." in avisos[0]


def test_caption_dividendos_atipicos_nao_aparece_abaixo_do_corte(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None, segmento_setorial="Bancos")
    ano_atual = pd.Timestamp.now().year
    # Razão = 1,2/1,0 = 1,2 (120%) -- abaixo do corte de 2,0.
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos",
        lambda *args, **kwargs: _dividendos_com_razao(ano_atual, 1.2, 1.0),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        c.value for c in at.caption if "Dividendos dos últimos 12 meses em" in c.value
    ]
    assert avisos == []


def test_saude_financeira_mostra_numeros_com_virgula_brasileira(monkeypatch):
    # ROE/Margem líquida/LPA/VPA/Liquidez corrente usavam `_fmt()` sem
    # conversão de ponto pra vírgula (ex: "15.0%"/"R$ 5.00" em vez de
    # "15,0%"/"R$ 5,00") — bug real confirmado por screenshot, mesma
    # família do "Preço atual" corrigido em 2026-09-21 (aqui é `_fmt` em
    # si que estava sem a conversão, não um call site isolado).
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": 50.0, "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: _indicadores_falsos_aplicavel_pra_graham(),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    # Valores de _indicadores_falsos_aplicavel_pra_graham: roe_percentual=15.0,
    # margem_liquida_percentual=10.0, lpa=5.0, vpa=20.0, liquidez_corrente=1.2.
    assert _metrica_por_label(at, "ROE").value == "15,0%"
    assert _metrica_por_label(at, "Margem líquida").value == "10,0%"
    assert _metrica_por_label(at, "LPA").value == "R$ 5,00"
    assert _metrica_por_label(at, "VPA").value == "R$ 20,00"
    assert _metrica_por_label(at, "Liquidez corrente").value == "1,20"


def test_correlacao_mostra_coeficiente_com_virgula_brasileira(monkeypatch):
    # _cartao_correlacao usava f"{...:.2f}" sem conversão de ponto pra
    # vírgula (ex: "1.00" em vez de "1,00") — mesma família de bug.
    # Petróleo em queda constante e ação em alta constante -> correlação
    # perfeita negativa (-1,00), fácil de prever exatamente.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    n = 40  # > MINIMO_OBSERVACOES_CORRELACAO (30)
    datas = pd.date_range("2024-01-01", periods=n, freq="D")
    historico_acao = pd.DataFrame(
        {
            "data": datas,
            "Close": [float(i + 1) for i in range(n)],
            "Volume": [30_000_000] * n,
        }
    )
    historico_petroleo = pd.DataFrame(
        {"data": datas, "Close": [float(n - i) for i in range(n)], "Volume": [0] * n}
    )

    def _historico_por_ticker(ticker, periodo=None, **kwargs):
        # Mesma função de ingest atende ação e petróleo (Brent) — só o
        # `ticker` muda (ver `_buscar_historico`/`_buscar_historico_petroleo`
        # em app/main.py). Sobrescreve o mock de falha genérica que
        # _bloquear_buscas_de_rede_por_ticker aplicou acima.
        if ticker == TICKER_PETROLEO_BRENT:
            return historico_petroleo.copy()
        return historico_acao.copy()

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", _historico_por_ticker)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    # Correlação calculada sobre retorno % dia a dia, não sobre o nível
    # bruto — não vale a pena prever o coeficiente exato aqui (não é -1,00
    # só porque os níveis são lineares opostos); o que importa pro bug
    # corrigido é o formato: vírgula decimal, não ponto.
    valor_petroleo = _metrica_por_label(at, "Petróleo (Brent)").value
    assert re.fullmatch(r"-?\d,\d\d", valor_petroleo), (
        f"correlação não está no formato brasileiro esperado: {valor_petroleo!r}"
    )


def test_grafico_dividendos_mostra_rotulos_com_virgula_brasileira(monkeypatch):
    # figura_dividendos usava texttemplate="R$ %{text:.2f}" e "%{text:.1f}%"
    # — o d3-format que o Plotly usa por trás desses especificadores tem o
    # mesmo problema de locale do _fmt/_fmt_bilhoes (sem vírgula decimal
    # brasileira sem registrar um locale que o bundle do Streamlit não
    # traz). Corrigido pré-formatando `text` com _fmt_bilhoes/
    # _fmt_percentual e usando "%{text}" (passthrough) no texttemplate.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": 50.0, "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )
    dividendos_fake = pd.DataFrame(
        {"data": pd.to_datetime(["2023-06-01", "2024-06-01"]), "dividendo": [2.5, 3.25]}
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_dividendos", lambda *args, **kwargs: dividendos_fake
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: _indicadores_falsos_aplicavel_pra_graham(),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    graficos_plotly = at.get("plotly_chart")
    figuras_dividendos = [
        json.loads(g.proto.spec)
        for g in graficos_plotly
        if json.loads(g.proto.spec)["data"]
        and json.loads(g.proto.spec)["data"][0].get("name") == "Dividendos"
    ]
    assert len(figuras_dividendos) == 1
    trace_dividendos = figuras_dividendos[0]["data"][0]
    assert trace_dividendos["texttemplate"] == "%{text}"
    for texto in trace_dividendos["text"]:
        assert "," in texto and "R$" in texto
        assert not re.search(r"\d\.\d\d\b", texto), f"rótulo com ponto decimal: {texto!r}"


# --- Formatação abreviada de Valor de mercado/Dívida líquida/Valor de firma --
#
# Regressão: sem abreviação, o valor por extenso (ex: "R$ 625,10 bi") ficava
# truncado com reticências pelo st.metric dentro da coluna estreita de 4 da
# seção "Saúde financeira" (ex: "R$ 625,1...") — bug real encontrado em
# produção, não hipotético. `_fmt_bilhoes` cobre isso com "X,X bi"/"X,X mi".


def _indicadores_falsos_com(numero_acoes: float, divida_liquida: float) -> dict:
    return {
        "lpa": 5.0,
        "vpa": 20.0,
        "numero_acoes": numero_acoes,
        "divida_liquida_sobre_patrimonio": 0.5,
        "roe_percentual": 15.0,
        "margem_liquida_percentual": 10.0,
        "liquidez_corrente": 1.2,
        "crescimento_receita_5a_percentual": 8.0,
        "patrimonio_liquido": 20_000_000.0,
        "divida_liquida": divida_liquida,
        "data_balanco_fundamentus": "2026-06-30",
    }


# Cada caso: (preço, número de ações, dívida líquida) -> (Valor de mercado,
# Dívida líquida, Valor de firma) esperados, já formatados.
CASOS_FORMATACAO_VALOR_GRANDE = {
    # Casa dos milhões: R$ 50 mi de mercado, R$ 10 mi de dívida -> R$ 60 mi de firma.
    "milhoes": (50.0, 1_000_000.0, 10_000_000.0, "R$ 50,0 mi", "R$ 10,0 mi", "R$ 60,0 mi"),
    # Casa dos bilhões: R$ 5 bi de mercado, R$ 2 bi de dívida -> R$ 7 bi de firma.
    "bilhoes": (100.0, 50_000_000.0, 2_000_000_000.0, "R$ 5,0 bi", "R$ 2,0 bi", "R$ 7,0 bi"),
    # Caixa líquido (dívida líquida negativa) — sinal precisa continuar
    # visível depois de abreviado. Firma = 50 mi + (-300 mi) = -250 mi.
    "caixa_liquido": (
        50.0,
        1_000_000.0,
        -300_000_000.0,
        "R$ 50,0 mi",
        "R$ -300,0 mi",
        "R$ -250,0 mi",
    ),
    # Limite exato de R$ 1 bilhão: >= 1 bi já mostra "bi", não "1000,0 mi".
    # Firma = 50 mi + 1 bi = 1,05 bi, também cai no ramo "bi".
    "limite_1bi": (
        50.0,
        1_000_000.0,
        1_000_000_000.0,
        "R$ 50,0 mi",
        "R$ 1,0 bi",
        "R$ 1,1 bi",
    ),
    # Abaixo do piso de R$ 1 milhão: mostra o valor completo por extenso,
    # não abrevia ("R$ 0,5 mi" seria menos claro que "R$ 500.000,00" pra
    # valores nessa faixa).
    "abaixo_do_piso": (
        1.0,
        500_000.0,
        100_000.0,
        "R$ 500.000,00",
        "R$ 100.000,00",
        "R$ 600.000,00",
    ),
    # No próprio piso (exatamente R$ 1 milhão): já abrevia, não fica em
    # "R$ 1.000.000,00" — fronteira é ">=", não ">".
    "no_piso": (
        1.0,
        1_000_000.0,
        1_000_000.0,
        "R$ 1,0 mi",
        "R$ 1,0 mi",
        "R$ 2,0 mi",
    ),
}


@pytest.mark.parametrize("id_caso", list(CASOS_FORMATACAO_VALOR_GRANDE))
def test_valor_mercado_divida_firma_formatados_sem_truncar(monkeypatch, id_caso):
    preco, numero_acoes, divida_liquida, esperado_mercado, esperado_divida, esperado_firma = (
        CASOS_FORMATACAO_VALOR_GRANDE[id_caso]
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": preco, "3mo": preco, "1y": preco, f"{ANOS_JANELA_CORRELACAO}y": preco}
        ),
    )

    def _falha_precos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    def _falha_rt(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico_ibovespa", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_precos)
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: _indicadores_falsos_com(numero_acoes, divida_liquida),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _falha_rt)
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_rt)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    assert _metrica_por_label(at, "Valor de mercado").value == esperado_mercado
    assert _metrica_por_label(at, "Dívida líquida").value == esperado_divida
    assert _metrica_por_label(at, "Valor de firma").value == esperado_firma


# --- Base consistente na "Projeção de crescimento" da carteira --------------
#
# Regressão (bug real, corrigido em 2026-09-21): as curvas "Com juros
# compostos"/"Sem juros compostos" e a tabela "Ganho nominal vs. real"
# recebiam soma_investida (total, inclui tickers sem cenário) como ponto de
# partida/valor investido, enquanto o ponto final vinha de valor_por_cenario
# (só tickers com cenário aplicável) — mesma causa raiz já corrigida no CAGR.
# A linha de "Inflação (IPCA)" não tinha esse bug (não é pareada com
# valor_por_cenario), mas foi ajustada pra mesma base por consistência
# VISUAL do gráfico — com soma_investida total, ela partia de um ponto
# diferente das outras 6 curvas no mesmo gráfico, sem nenhuma indicação de
# que era proposital (confirmado com screenshot antes de mudar). st.
# plotly_chart não é inspecionável via AppTest, então o teste abaixo
# espiona projetar_curva_composta/projetar_curva_linear/
# calcular_ganho_nominal_vs_real/projetar_curva_inflacao (delegando pro
# real, só capturando os argumentos) pra confirmar que app/main.py agora
# passa soma_investida_com_cenario nas quatro, não soma_investida total.
#
# `_carregar_screener_salvo` é uma função PRIVADA de app/main.py (não
# importada de outro módulo) — AppTest executa o script inteiro num módulo
# novo a cada `.run()` (`_new_module`, não reaproveita `sys.modules`), então
# monkeypatchar essa função pelo caminho `avaliador_b3.app.main.X` não tem
# efeito nenhum na execução real (confirmado empiricamente). Em vez disso,
# escreve um CSV de verdade em `tmp_path` e aponta
# `avaliador_b3.screener.CAMINHO_SAIDA_PADRAO` (constante importada de um
# módulo de verdade, isso sim visível pro `from ... import` que roda de novo
# a cada execução) pra esse arquivo.


def _escrever_screener_falso_dobra_e_sem_cenario(caminho) -> None:
    from avaliador_b3.screener import COLUNAS_RESULTADO

    linhas = [
        # DOBR4: valor_combinado = 2x o preço atual -> cenário "base" dobra o
        # investido. Graham = 80 também (mesmo valor, só pra garantir
        # "aplicavel").
        {c: None for c in COLUNAS_RESULTADO}
        | {
            "ticker": "DOBR4",
            "sucesso": True,
            "erro": "",
            "preco_atual": 40.0,
            "valor_combinado": 80.0,
            "desconto_percentual": 100.0,
            "metodos_utilizados": "graham",
            "graham_valor_justo": 80.0,
            "aviso_desconto_extremo": "",
        },
        # SEMC3: nenhum método aplicável.
        {c: None for c in COLUNAS_RESULTADO}
        | {
            "ticker": "SEMC3",
            "sucesso": True,
            "erro": "",
            "preco_atual": 10.0,
            "metodos_utilizados": "",
            "aviso_desconto_extremo": "",
        },
    ]
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)


def _obter_serie_bcb_falso(codigo, data_inicial=None, data_final=None, **kwargs):
    from avaliador_b3.config import SERIES_BCB_SGS

    if codigo == SERIES_BCB_SGS["selic_meta"]:
        return pd.DataFrame({"data": pd.to_datetime(["2026-01-01"]), "valor": [10.5]})
    if codigo == SERIES_BCB_SGS["ipca_mensal"]:
        datas = pd.date_range("2025-01-01", periods=12, freq="MS")
        return pd.DataFrame({"data": datas, "valor": [0.3] * 12})
    raise RuntimeError(f"série {codigo} não mockada neste teste")


def test_tabela_screener_mostra_moeda_e_percentual_com_virgula_brasileira(
    monkeypatch, tmp_path
):
    # Ver comentário central perto de `_tabela_formatada_pt_br` em
    # app/main.py pro porquê (NumberColumn sem vírgula brasileira em
    # locale nenhum) e o trade-off aceito (ordenar pelo cabeçalho dessas
    # colunas vira alfabético, não numérico).
    import avaliador_b3.screener as screener_mod

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    caminho_screener_falso = tmp_path / "screener.csv"
    _escrever_screener_falso_dobra_e_sem_cenario(caminho_screener_falso)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception

    tabelas_com_preco = [df.value for df in at.dataframe if "preco_atual" in df.value.columns]
    assert len(tabelas_com_preco) == 1
    tabela = tabelas_com_preco[0]

    # texto, não numérico — a coluna virou texto pré-formatado.
    assert pd.api.types.is_string_dtype(tabela["preco_atual"])
    linha_dobr4 = tabela.loc[tabela["ticker"] == "DOBR4"].iloc[0]
    assert linha_dobr4["preco_atual"] == "R$ 40,00"
    assert linha_dobr4["valor_combinado"] == "R$ 80,00"
    assert linha_dobr4["desconto_percentual"] == "100,0%"


def test_faixa_amarela_desconto_extremo_referencia_o_nome_visivel_da_coluna(
    monkeypatch, tmp_path
):
    # Bug real: a faixa amarela mandava ver a coluna "aviso_desconto_
    # extremo" (nome interno do CSV), mas a tabela mostra essa coluna
    # como "Aviso" (ver column_config em app/main.py) -- quem lesse a
    # faixa não achava nenhuma coluna com esse nome na tela.
    import avaliador_b3.screener as screener_mod
    from avaliador_b3.screener import COLUNAS_RESULTADO

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    linha = {c: None for c in COLUNAS_RESULTADO} | {
        "ticker": "EXTR3",
        "sucesso": True,
        "erro": "",
        "preco_atual": 10.0,
        "valor_combinado": 30.0,
        "desconto_percentual": 200.01,
        "metodos_utilizados": "graham",
        "graham_valor_justo": 30.0,
        "aviso_desconto_extremo": screener_mod.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
    }
    caminho_screener_falso = tmp_path / "screener.csv"
    pd.DataFrame([linha], columns=COLUNAS_RESULTADO).to_csv(caminho_screener_falso, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        w.value for w in at.warning if "ação(ões) com desconto fora do comum" in w.value
    ]
    assert len(avisos) == 1
    assert avisos[0] == (
        '1 ação(ões) com desconto fora do comum (valor justo muito acima ou '
        'muito abaixo do preço) — veja a coluna "Aviso" na tabela: a causa '
        "provável varia de uma ação para outra."
    )
    assert "aviso_desconto_extremo" not in avisos[0]


def test_botao_screener_mostra_aviso_na_tela_quando_deteccao_do_ano_falha(monkeypatch):
    # Correção de 2026-09-23: warnings.warn dentro de rodar_screener vai só
    # pro log do servidor, invisível pra quem clicou no botão — sem essa
    # captura+reexibição em session_state, a coluna do FCD ficaria vazia
    # sem nenhuma explicação na tela. rodar_screener é substituído por um
    # fake que reproduz só o efeito relevante (emitir o aviso da categoria
    # DeteccaoAnoCvmFalhouWarning) — o comportamento real de emitir esse
    # aviso quando resolver_ano_mais_recente_disponivel falha já é coberto
    # em tests/test_screener.py; este teste cobre só a plumbing nova de
    # captura/reexibição em app/main.py.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    def rodar_screener_falso(*args, **kwargs):
        warnings.warn(
            "Detecção do ano mais recente da CVM falhou — o FCD de todas as "
            "ações desta rodada ficará indisponível: CVM fora do ar (simulado)",
            category=DeteccaoAnoCvmFalhouWarning,
            stacklevel=2,
        )

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodar_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    at.button[1].click().run(timeout=60)

    assert not at.exception
    avisos = [
        aviso.value
        for aviso in at.warning
        if "Detecção do ano mais recente da CVM falhou" in aviso.value
    ]
    assert len(avisos) == 1
    assert "CVM fora do ar (simulado)" in avisos[0]


def test_caption_screener_explica_dividendos_vs_historico_vazio(monkeypatch):
    # A coluna "Dividendos vs. histórico" fica vazia tanto quando o Bazin
    # não se aplica quanto (raramente) quando a mediana dos 5 anos sai
    # zero — a caption do topo da aba precisa deixar isso claro, sem
    # deixar a coluna vazia parecendo um dado faltando por erro.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    captions = [
        c.value
        for c in at.caption
        if "Dividendos vs. histórico vazio significa que o Bazin não se aplica" in c.value
    ]
    assert len(captions) == 1
    assert (
        "ou, raramente, que os anos anteriores não têm pagamento para comparar"
        in captions[0]
    )


def test_projecao_carteira_usa_base_com_cenario_nao_a_base_total(monkeypatch, tmp_path):
    import avaliador_b3.carteira as carteira_mod
    import avaliador_b3.graficos as graficos_mod
    import avaliador_b3.screener as screener_mod

    # Bloqueia as buscas de rede da busca automática de PETR4 na aba
    # "Analisar uma ação" (dispara sempre, independente da aba visitada) —
    # mesmo padrão de _bloquear_buscas_de_rede_por_ticker, mas SEM mockar
    # bcb_sgs.obter_serie, que este teste precisa que funcione de verdade
    # (IPCA/Selic da carteira).
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )

    def _falha_precos(*args, **kwargs):
        raise TickerInvalido(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_historico_ibovespa", _falha_precos)
    monkeypatch.setattr("avaliador_b3.ingest.precos.obter_dividendos", _falha_precos)

    def _falha_fundamentus(*args, **kwargs):
        raise TickerNaoEncontrado(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.fundamentus.obter_indicadores", _falha_fundamentus)
    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        lambda *args, **kwargs: _catalogo_emissores_vazio(),
    )

    def _falha_gpr(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", _falha_gpr)
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _obter_serie_bcb_falso)

    caminho_screener_falso = tmp_path / "screener.csv"
    _escrever_screener_falso_dobra_e_sem_cenario(caminho_screener_falso)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho_screener_falso)

    # Espiona as três funções que recebiam a base errada — delega pro real,
    # só captura os argumentos recebidos.
    chamadas_composta: list[float] = []
    original_composta = graficos_mod.projetar_curva_composta

    def _espiao_composta(valor_investido, cagr, anos):
        chamadas_composta.append(valor_investido)
        return original_composta(valor_investido, cagr, anos)

    chamadas_linear: list[float] = []
    original_linear = graficos_mod.projetar_curva_linear

    def _espiao_linear(valor_investido, valor_destino, anos):
        chamadas_linear.append(valor_investido)
        return original_linear(valor_investido, valor_destino, anos)

    chamadas_ganho: list[float] = []
    original_ganho = carteira_mod.calcular_ganho_nominal_vs_real

    def _espiao_ganho(valor_investido, valor_destino, ipca_anual, anos):
        chamadas_ganho.append(valor_investido)
        return original_ganho(valor_investido, valor_destino, ipca_anual, anos)

    chamadas_inflacao: list[float] = []
    original_inflacao = graficos_mod.projetar_curva_inflacao

    def _espiao_inflacao(valor_investido, ipca_anual, anos):
        chamadas_inflacao.append(valor_investido)
        return original_inflacao(valor_investido, ipca_anual, anos)

    monkeypatch.setattr(graficos_mod, "projetar_curva_composta", _espiao_composta)
    monkeypatch.setattr(graficos_mod, "projetar_curva_linear", _espiao_linear)
    monkeypatch.setattr(carteira_mod, "calcular_ganho_nominal_vs_real", _espiao_ganho)
    monkeypatch.setattr(graficos_mod, "projetar_curva_inflacao", _espiao_inflacao)

    def _aba_carteira(at):
        return [tab for tab in at.tabs if tab.label == "Simulador de carteira"][0]

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception

    _aba_carteira(at).multiselect[0].set_value(["DOBR4", "SEMC3"])
    at.run(timeout=60)
    assert not at.exception

    at.number_input(key="investimento_DOBR4").set_value(1000.0)
    at.number_input(key="investimento_SEMC3").set_value(300.0)
    at.run(timeout=60)
    assert not at.exception

    # "Sem juros compostos (linear)" e "Inflação (IPCA)" não vêm
    # selecionados por padrão — liga os dois, pra exercitar
    # projetar_curva_linear/projetar_curva_inflacao (composta já é
    # default). Referência a `_aba_carteira(at)` de novo (não a mesma
    # variável de antes): cada `.run()` reconstrói a árvore de elementos,
    # uma referência antiga fica vazia (`len(...) == 0`) depois de um rerun.
    _aba_carteira(at).pills[0].set_value(
        ["Com juros compostos", "Sem juros compostos (linear)", "Inflação (IPCA)"]
    )
    at.run(timeout=60)
    assert not at.exception

    # soma_investida total = 1300 (1000 + 300); soma_investida_com_cenario =
    # 1000 (só DOBR4, que tem cenário). As quatro funções espionadas
    # precisam ter recebido 1000, nunca 1300 — inclusive
    # projetar_curva_inflacao, ajustada por consistência visual do gráfico
    # em 2026-09-21 (todas as curvas passam a compartilhar o mesmo ponto de
    # partida no ano 0, ver comentário em app/main.py).
    assert chamadas_composta, "projetar_curva_composta não foi chamada"
    assert all(valor == pytest.approx(1000.0) for valor in chamadas_composta)

    assert chamadas_linear, "projetar_curva_linear não foi chamada"
    assert all(valor == pytest.approx(1000.0) for valor in chamadas_linear)

    assert chamadas_ganho, "calcular_ganho_nominal_vs_real não foi chamada"
    assert all(valor == pytest.approx(1000.0) for valor in chamadas_ganho)

    assert chamadas_inflacao, "projetar_curva_inflacao não foi chamada"
    assert all(valor == pytest.approx(1000.0) for valor in chamadas_inflacao)

    # soma_investida_com_cenario é exatamente 1000,00 aqui (só DOBR4 tem
    # cenário) — dá pra conferir esse valor exato; o regex cobre os
    # demais números da frase (pessimista/otimista), que dependem do
    # resultado do screener falso e não vale a pena recalcular à mão aqui.
    frases_projecao = [
        m.value for m in at.markdown if "com projeção disponível hoje" in m.value
    ]
    assert len(frases_projecao) == 1
    assert "R\\$ 1.000,00 com projeção disponível hoje" in frases_projecao[0]
    assert not re.search(r"R\\\$\s*[\d.]*\d\.\d\d\b", frases_projecao[0]), (
        f"frase de projeção com ponto decimal em vez de vírgula: {frases_projecao[0]!r}"
    )

    legendas_cagr = [c.value for c in at.caption if "equivale a" in c.value]
    assert legendas_cagr, "nenhuma legenda de CAGR encontrada"
    for legenda in legendas_cagr:
        assert not re.search(r"\d\.\d%", legenda), (
            f"legenda de CAGR com ponto decimal em vez de vírgula: {legenda!r}"
        )
