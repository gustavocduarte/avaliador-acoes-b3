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

    def _valor_metrica(rotulo: str) -> str:
        metricas = [metrica for metrica in at.metric if metrica.label == rotulo]
        assert len(metricas) == 1, f"esperava 1 métrica '{rotulo}', achei {len(metricas)}"
        return metricas[0].value

    assert _valor_metrica("Valor de mercado") == esperado_mercado
    assert _valor_metrica("Dívida líquida") == esperado_divida
    assert _valor_metrica("Valor de firma") == esperado_firma


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
