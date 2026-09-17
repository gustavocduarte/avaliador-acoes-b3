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

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from avaliador_b3.config import ANOS_JANELA_CORRELACAO
from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado
from avaliador_b3.ingest.precos import TickerInvalido

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
    precos_atuais = [metrica for metrica in at.metric if metrica.label == "Preço atual"]
    assert len(precos_atuais) == 1
    assert precos_atuais[0].value == "R$ 50.43"


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

    metricas_graham = [metrica for metrica in at.metric if metrica.label == "Graham"]
    assert len(metricas_graham) == 1
    # Graham = raiz(22,5 × 5 × 20) ≈ 47,43; preço 50 -> delta ≈ -5,1%.
    assert metricas_graham[0].delta == "-5.1%"

    metricas_bazin = [metrica for metrica in at.metric if metrica.label == "Bazin (preço teto)"]
    assert len(metricas_bazin) == 1
    assert not metricas_bazin[0].delta
