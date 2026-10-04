"""Testes do dashboard Streamlit (app/main.py) via `streamlit.testing.v1.AppTest`
— roda o script de verdade (mesmo runner que `streamlit run` usa por baixo),
sem precisar de navegador. Cobre a degradação graciosa do dropdown de ticker
na aba "Analisar uma ação" e a pré-seleção + busca automática de PETR4 só na
primeira abertura da sessão (ver `TICKER_PADRAO_PRIMEIRA_ABERTURA` em
app/main.py).

Como a busca automática da primeira abertura dispara o mesmo fluxo de
"Buscar" de verdade (preço, indicadores, dividendos, CNPJ, macro e, como a
Correlação com fatores externos vive dentro desta aba,
também petróleo/câmbio/GPR), os testes que passam pelo carregamento
inicial da aba com o universo disponível também mockam essas fontes pra
continuarem rápidos e determinísticos, sem rede de verdade — ver
`_bloquear_buscas_de_rede_por_ticker`.
"""

import json
import re
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from avaliador_b3.config import (
    ANOS_JANELA_CORRELACAO,
    LEGENDA_REINVESTIMENTO_CAPEX,
    MOTIVO_RECEITA_SEM_DRE,
    TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA,
    TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA,
    TEXTO_FIRMA_SEM_COMPONENTES,
    TEXTO_RISCO_SACADO_RECLASSIFICADO,
    TICKER_PETROLEO_BRENT,
    YIELD_MINIMO_BAZIN,
)
from avaliador_b3.ingest.bcb_sgs import ResultadoMacro
from avaliador_b3.ingest.cvm import CnpjNaoEncontrado
from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado
from avaliador_b3.ingest.precos import TickerInvalido
from avaliador_b3.screener import DeteccaoAnoCvmFalhouWarning, MacroIndisponivelWarning

# Ano fixo usado pelos mocks de FCD abaixo: o ano é detectado em tempo de
# execução (`ingest.cvm.resolver_ano_mais_recente_disponivel`), não é uma
# constante.
ANO_FCD_MOCK = 2025


def _resultado_fcf_mock(
    cfo_atual, capex, juros_pagos=0.0, cfi_atual=None, receita=None, risco_sacado=0.0
):
    """Resultado do FCF de UM ano (`ingest.cvm.obter_fluxo_caixa_livre`). `capex`
    `None` simula o capex não identificado. O fluxo do FCD é
    cfo - capex + juros_pagos x (1 - alíquota)."""
    cfi = -(capex or 0.0) if cfi_atual is None else cfi_atual
    return {
        "fcf_atual": cfo_atual + cfi,
        "cfo_atual": cfo_atual,
        "cfi_atual": cfi,
        "capex_atual": {
            "status": "identificado" if capex is not None else "nao_identificado",
            "valor": capex,
            "linhas": [],
        },
        "juros_pagos_atual": {"valor": juros_pagos, "linhas": []},
        "risco_sacado_atual": {"valor": risco_sacado, "saldo": risco_sacado, "linhas": []},
        "receita_atual": {
            "valor": receita,
            "versao": 1 if receita is not None else None,
            "motivo": None if receita is not None else MOTIVO_RECEITA_SEM_DRE,
        },
    }


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


@pytest.fixture(autouse=True)
def _simular_ano_cvm_fixo(monkeypatch):
    """A busca automática da primeira abertura chama
    `resolver_ano_mais_recente_disponivel` em todo `at.run()`; sem este
    mock, cada teste tentaria baixar o zip da CVM. Um teste que exercita
    a falha dessa detecção sobrescreve com seu próprio `monkeypatch`."""
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.resolver_ano_mais_recente_disponivel",
        lambda **kwargs: ANO_FCD_MOCK,
    )


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
    já trataria de verdade — mantém rápidos e determinísticos os testes que
    disparam a busca automática da primeira abertura (que inclui a correlação
    com fatores externos). A detecção do ano mais recente da
    CVM é mockada à parte, pra todo o arquivo — ver
    `_simular_ano_cvm_fixo`."""
    # BCB simulado fora do ar de propósito aqui — filtra o aviso que isso
    # dispara, senão a mesma linha se repete em toda busca que passa por
    # este helper. pytest isola o filtro de warnings por teste, não vaza
    # pros outros.
    warnings.filterwarnings("ignore", message="Falha ao buscar Selic/IPCA do BCB")

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
    # Sem isso, obter_selic_e_ipca cairia pro ultimo_macro.json real do
    # projeto (diretorio_cache default) se ele existir em disco nesta
    # máquina — tornando o teste dependente de estado externo (idade do
    # arquivo) em vez de determinístico.
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs._carregar_ultimo_macro", lambda *a: None)
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
    # Universo disponível -> dropdown não deveria cair pro aviso de
    # fallback (esse aviso específico é o foco deste teste; Selic/IPCA
    # segue indisponível nesta simulação e mostra o aviso próprio dele,
    # sem relação com o dropdown).
    assert not any("Lista de ações do Ibovespa indisponível" in aviso.value for aviso in at.warning)


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
    assert any("indisponível" in aviso and "falha simulada de rede" in aviso for aviso in avisos)


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
    botao_buscar = next(b for b in at.button if b.label == "Buscar")
    botao_buscar.click().run(timeout=60)

    assert not at.exception
    assert any(subheader.value == "VALE3" for subheader in at.subheader)


# --- Histórico "vazio mas sem exceção" vira erro tratado (_buscar_historico) -


def test_historico_vazio_sem_excecao_vira_erro_tratado_nao_crash(monkeypatch):
    # Regressão: obter_historico devolvendo um DataFrame vazio SEM levantar
    # exceção (teoricamente só possível com um cache em disco corrompido/
    # truncado — o caminho de busca nova já levanta TickerInvalido nesse caso,
    # ver ingest/precos.py) não pode chegar em
    # `preco_atual = float(historico_preco_atual["Close"].iloc[-1])` (IndexError
    # cru): _buscar_historico/_buscar_historico_ibovespa tratam DataFrame vazio
    # como erro, mesmo par (None, motivo) de uma exceção real.
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


def test_pagina_da_acao_com_preco_atual_vazio_mostra_aviso_e_nao_calcula_potencial(
    monkeypatch,
):
    from avaliador_b3.config import AVISO_PRECO_INDISPONIVEL

    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": float("nan"), "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert AVISO_PRECO_INDISPONIVEL in [w.value for w in at.warning]
    assert not [m for m in at.metric if m.label == "Preço atual"]
    assert not _metrica_por_label(at, "Valor combinado").delta


def test_preco_atual_usa_periodo_separado_do_historico_de_3_meses(monkeypatch):
    # Regressão: o histórico diário mais longo (period="3mo", usado pra
    # volume/volatilidade) atrasa um pregão inteiro no yfinance, mesmo já
    # encerrado (PETR4: R$ 48,92 no card contra R$ 50,43 no TradingView).
    # "Preço atual"
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
    # A correlação com fatores externos não é uma aba separada: mora dentro de
    # "Analisar uma ação" e aparece junto do
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
    assert any(subheader.value == "Correlação com fatores externos" for subheader in at.subheader)


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


def _leitura_balanco_mock(
    nao_controladores=0.0,
    disponivel=True,
    motivo=None,
    patrimonio_liquido_total=None,
    arrendamento_fora_da_divida=0.0,
    acoes_em_circulacao=None,
    motivo_acoes=None,
):
    """Leitura única do balanço da CVM (`ingest.balanco_cvm.obter_leitura_balanco`)."""
    if not disponivel:
        return {"disponivel": False, "motivo": motivo}
    return {
        "disponivel": True,
        "motivo": None,
        "nao_controladores": nao_controladores,
        "patrimonio_liquido_total": patrimonio_liquido_total,
        "arrendamento_fora_da_divida": arrendamento_fora_da_divida,
        "acoes_em_circulacao": acoes_em_circulacao,
        "motivo_acoes": motivo_acoes,
    }


def _preparar_fcd_aplicavel(
    monkeypatch,
    divida_liquida: float | None,
    segmento_setorial: str = "Petróleo, Gás e Biocombustíveis",
    leitura_balanco: dict | None = None,
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
            "acoes_por_cotacao": 1,
        },
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.balanco_cvm.obter_leitura_balanco",
        lambda *args, **kwargs: leitura_balanco or _leitura_balanco_mock(),
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
        lambda cnpj, ano, *a, **kw: (
            _resultado_fcf_mock(1_200_000.0, 200_000.0)
            if ano == ANO_FCD_MOCK
            else _resultado_fcf_mock(1_000_000.0, 200_000.0)
        ),
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


def test_rest_do_bcb_fora_do_ar_e_soap_respondendo_nao_mostra_aviso_de_falha_na_pagina(
    monkeypatch,
):
    import requests

    from avaliador_b3.config import FONTE_BCB_SOAP

    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    pasta = Path(__file__).parent / "fixtures"
    xml_selic = (pasta / "bcb_soap_selic_meta_com_datas_futuras.xml").read_text("utf-8")
    xml_ipca = (pasta / "bcb_soap_ipca_mensal.xml").read_text("utf-8")
    pedidos_soap = []

    def rest_fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("api.bcb.gov.br fora do ar (simulado)")

    def soap(url, timeout, pausas, data, headers):
        pedidos_soap.append(data.decode("utf-8"))
        corpo = xml_selic if ">432<" in data.decode("utf-8") else xml_ipca
        return type("RespostaSoap", (), {"text": corpo})()

    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", rest_fora_do_ar)
    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.post_com_retry", soap)
    st.cache_data.clear()

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert pedidos_soap, f"o SOAP ({FONTE_BCB_SOAP}) devia ter sido consultado"
    # O FCD usa a Selic e o IPCA vindos do SOAP, e nenhuma falha intermediária vira aviso.
    assert _metrica_por_label(at, "FCD").value != "—"
    textos = [w.value for w in at.warning] + [e.value for e in at.error]
    termos_do_bcb = ("api.bcb.gov.br", "BCB", "Banco Central", "Selic", "IPCA")
    assert not [t for t in textos if any(termo in t for termo in termos_do_bcb)]
    # A origem efetiva aparece como informação (não como aviso).
    assert [i.value for i in at.info if "Selic e IPCA obtidos" in i.value] == [
        "Selic e IPCA obtidos pelo serviço SOAP do Banco Central."
    ]


def _macro_de_teste(**campos):
    base = dict(
        selic_meta=0.1375,
        ipca_12m=0.042,
        data_ipca=pd.Timestamp("2026-08-01"),
        usou_valor_guardado=False,
        data_busca=pd.Timestamp("2026-10-03"),
    )
    return ResultadoMacro(**{**base, **campos})


def test_aviso_de_fonte_do_macro_por_combinacao_de_fontes():
    from avaliador_b3.app.main import _aviso_fonte_macro

    assert _aviso_fonte_macro(_macro_de_teste()) == ""  # API REST: nada a avisar
    assert (
        _aviso_fonte_macro(_macro_de_teste(fonte_selic="BCB (SOAP)", fonte_ipca="BCB (SOAP)"))
        == "Selic e IPCA obtidos pelo serviço SOAP do Banco Central."
    )
    assert (
        _aviso_fonte_macro(_macro_de_teste(fonte_selic="BCB (SOAP)", fonte_ipca="IBGE (SIDRA)"))
        == "Selic obtida pelo serviço SOAP do Banco Central. IPCA obtido pelo IBGE (SIDRA)."
    )
    assert (
        _aviso_fonte_macro(_macro_de_teste(fonte_ipca="IBGE (SIDRA)"))
        == "IPCA obtido pelo IBGE (SIDRA)."
    )
    guardado = _macro_de_teste(usou_valor_guardado=True, fonte_selic="valor guardado de 01/10/2026")
    assert _aviso_fonte_macro(guardado) == ""


def test_arquivo_de_referencia_mostra_aviso_com_a_data_na_pagina(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    fonte = "arquivo de referência de 20/09/2026"
    referencia = _macro_de_teste(
        usou_valor_guardado=True,
        data_busca=pd.Timestamp("2026-09-20"),
        fonte_selic=fonte,
        fonte_ipca=fonte,
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.bcb_sgs.obter_selic_e_ipca", lambda *a, **kw: referencia
    )
    st.cache_data.clear()

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert any(
        w.value
        == "Banco Central indisponível agora. Usando a Selic e o IPCA do arquivo de referência "
        "do projeto, obtidos em 20/09/2026."
        for w in at.warning
    )


def test_fcd_com_leitura_do_balanco_nao_mostra_aviso_de_nao_controladores(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not [c.value for c in at.caption if "não controladores" in c.value]


def test_fcd_desconta_os_nao_controladores_do_balanco_da_cvm(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    sem_ajuste = _metrica_por_label(at, "FCD").value

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(nao_controladores=10_000.0),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != sem_ajuste


def test_valor_de_mercado_e_de_firma_usam_as_acoes_em_circulacao_da_cvm(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    # Preço 50 x 100 ações do Fundamentus; firma = mercado + dívida líquida 50.000.
    assert _metrica_por_label(at, "Valor de mercado").value == "R$ 5.000,00"
    assert _metrica_por_label(at, "Valor de firma").value == "R$ 55.000,00"

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(acoes_em_circulacao=80.0),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Valor de mercado").value == "R$ 4.000,00"
    assert _metrica_por_label(at, "Valor de firma").value == "R$ 54.000,00"
    assert not [c.value for c in at.caption if "ações em circulação da CVM" in c.value]


def test_valor_de_firma_usa_a_ponte_do_fcd_com_nao_controladores_e_arrendamento(monkeypatch):
    # Preço 50 x 100 ações = 5.000; firma = 5.000 + dívida líquida 50.000 + não
    # controladores 10.000 + arrendamento 2.000.
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(
            nao_controladores=10_000.0, arrendamento_fora_da_divida=2_000.0
        ),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Valor de firma").value == "R$ 67.000,00"
    assert not [c.value for c in at.caption if "Valor de firma calculado sem" in c.value]


def test_valor_de_firma_sem_o_balanco_da_cvm_deixa_de_fora_e_diz_quais_componentes(monkeypatch):
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(disponivel=False, motivo="balanço indisponível."),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Valor de firma").value == "R$ 55.000,00"
    assert TEXTO_FIRMA_SEM_COMPONENTES.format(
        componentes="não controladores, arrendamento fora da dívida"
    ) in [c.value for c in at.caption]


def test_valor_de_mercado_sem_acoes_em_circulacao_usa_o_fundamentus_e_mostra_o_motivo(
    monkeypatch,
):
    from avaliador_b3.config import TEXTO_SEM_ACOES_EM_CIRCULACAO

    motivo = "Tesouraria de 53% do capital na composição da CVM, acima do limite de 20%."
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(acoes_em_circulacao=None, motivo_acoes=motivo),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Valor de mercado").value == "R$ 5.000,00"
    legendas = [c.value for c in at.caption]
    # Uma no cartão do FCD e outra em "Saúde financeira", com o mesmo motivo.
    assert legendas.count(TEXTO_SEM_ACOES_EM_CIRCULACAO.format(motivo=motivo)) == 2


def test_pagina_avisa_quando_o_numero_de_acoes_do_fundamentus_diverge_da_cvm(monkeypatch):
    aviso = "O número de ações do Fundamentus (1.416,38 mi) difere em +24,0% do da CVM."
    leitura = {**_leitura_balanco_mock(acoes_em_circulacao=80.0), "aviso_divergencia_acoes": aviso}
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0, leitura_balanco=leitura)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert aviso in [w.value for w in at.warning]


def test_pagina_mostra_o_motivo_quando_o_numero_da_cvm_e_descartado_por_divergir_demais(
    monkeypatch,
):
    motivo = (
        "O número de ações da CVM (172,08 mi) difere +72% do do Fundamentus (296,73 mi): "
        "provável erro de escala ou de fator de unit; mantido o do Fundamentus."
    )
    leitura = {
        **_leitura_balanco_mock(acoes_em_circulacao=None, motivo_acoes=motivo),
        "detalhe_acoes": {"descartada_por_divergencia": True},
    }
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0, leitura_balanco=leitura)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert motivo in [w.value for w in at.warning]


def test_pagina_nao_mostra_aviso_de_acoes_quando_o_numero_bate(monkeypatch):
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(acoes_em_circulacao=98.0),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not [w.value for w in at.warning if "número de ações" in w.value.lower()]


def test_expander_do_fcd_explica_os_ajustes_do_balanco_e_as_acoes_em_circulacao(monkeypatch):
    from avaliador_b3.config import TEXTO_FCD_AJUSTES_DO_BALANCO

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
    assert TEXTO_FCD_AJUSTES_DO_BALANCO in blocos[0]
    for trecho in (
        "participação dos sócios não controladores",
        "passivo de arrendamento",
        "patrimônio total",
        "ações em circulação",
        "data-base do balanço do Fundamentus",
    ):
        assert trecho in blocos[0]


def test_fcd_e_graham_usam_as_acoes_em_circulacao_da_cvm(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    assert _metrica_por_label(at, "Graham").value == "R$ 47,43"
    fcd_sem_leitura = _metrica_por_label(at, "FCD").value

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(acoes_em_circulacao=80.0),  # Fundamentus: 100
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    # Graham = 47,43 x 100 / 80.
    assert _metrica_por_label(at, "Graham").value == "R$ 59,29"
    assert _metrica_por_label(at, "FCD").value != fcd_sem_leitura
    assert not [c.value for c in at.caption if "ações em circulação da CVM" in c.value]


def test_fcd_sem_acoes_em_circulacao_mostra_o_motivo_no_cartao(monkeypatch):
    from avaliador_b3.config import TEXTO_SEM_ACOES_EM_CIRCULACAO

    motivo = "Tesouraria de 53% do capital na composição da CVM, acima do limite de 20%."
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(acoes_em_circulacao=None, motivo_acoes=motivo),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "Graham").value == "R$ 47,43"
    assert TEXTO_SEM_ACOES_EM_CIRCULACAO.format(motivo=motivo) in [c.value for c in at.caption]


def test_fcd_soma_o_arrendamento_fora_da_divida_e_nao_mostra_aviso_de_arrendamento(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    sem_arrendamento = _metrica_por_label(at, "FCD").value

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(arrendamento_fora_da_divida=20_000.0),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != sem_arrendamento
    assert not [c.value for c in at.caption if "passivo de arrendamento" in c.value]


def test_fcd_sem_leitura_do_balanco_mostra_uma_legenda_so_com_o_motivo(monkeypatch):
    from avaliador_b3.config import TEXTO_SEM_AJUSTES_DO_BALANCO

    motivo = "A empresa não tem balanço consolidado de 30/06/2026 no ITR da CVM."
    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(disponivel=False, motivo=motivo),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption]
    assert legendas.count(TEXTO_SEM_AJUSTES_DO_BALANCO.format(motivo=motivo)) == 1
    assert not [c for c in legendas if "Sem o desconto" in c or "Pesos do custo de capital" in c]


def test_fcd_com_patrimonio_total_muda_o_valor_e_nao_mostra_aviso_dos_pesos(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    sem_patrimonio_total = _metrica_por_label(at, "FCD").value

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(patrimonio_liquido_total=10_000.0),
    )
    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != sem_patrimonio_total
    assert not [c.value for c in at.caption if "Pesos do custo de capital" in c.value]


def test_fcd_sem_patrimonio_total_mostra_o_motivo_dos_pesos_na_explicacao_do_cartao(monkeypatch):
    from avaliador_b3.config import TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(patrimonio_liquido_total=None),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    esperado = TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS.format(
        motivo="patrimônio líquido total não encontrado no balanço."
    )
    assert esperado in [c.value for c in at.caption]


def test_fcd_sem_leitura_do_balanco_mostra_o_motivo_na_explicacao_do_cartao(monkeypatch):
    from avaliador_b3.config import TEXTO_SEM_AJUSTES_DO_BALANCO

    _preparar_fcd_aplicavel(
        monkeypatch,
        divida_liquida=50_000.0,
        leitura_balanco=_leitura_balanco_mock(
            disponivel=False,
            motivo="A empresa não tem balanço consolidado de 30/06/2026 no ITR da CVM.",
        ),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != "—"
    esperado = TEXTO_SEM_AJUSTES_DO_BALANCO.format(
        motivo="A empresa não tem balanço consolidado de 30/06/2026 no ITR da CVM."
    )
    assert esperado in [c.value for c in at.caption]


def test_fcd_mostra_aviso_quando_divida_liquida_esta_ausente(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=None)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert _metrica_por_label(at, "FCD").value != "—"

    avisos_divida = [c.value for c in at.caption if "Dívida líquida indisponível" in c.value]
    assert len(avisos_divida) == 1
    assert "tende a ficar mais alto" in avisos_divida[0]


def test_fcd_nao_mostra_rotulo_do_ano_no_caso_normal_sem_fallback(monkeypatch):
    # No caso SEM fallback o cartão não traz a legenda "FCD calculado com a
    # demonstração financeira anual de X (CVM)" —
    # essa informação já aparece no bloco "Datas de referência dos dados
    # usados", texto repetido. Só a variante de fallback (que diz algo
    # específico dessa ação) continua no cartão — ver o teste seguinte.
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    rotulos_ano = [c.value for c in at.caption if "demonstração financeira anual de" in c.value]
    assert rotulos_ano == []


def test_fcd_mostra_rotulo_de_fallback_quando_empresa_nao_esta_no_ano_mais_recente(monkeypatch):
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    def obter_fluxo_caixa_livre_com_fallback(cnpj, ano, *args, **kwargs):
        if ano == ANO_FCD_MOCK:
            raise CnpjNaoEncontrado("não encontrado no ano mais recente")
        return _resultado_fcf_mock(900_000.0, 100_000.0)

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


# --- Proporção reinvestida no cartão do FCD (contexto: FCD sistematicamente
# baixo em empresas de investimento pesado, ver
# docs/correcao-cnpj-2026-09-25.md, seção 7) ------------------------------


def _preparar_fcd_com_cfo_cfi(
    monkeypatch,
    cfo_atual: float,
    cfi_atual: float,
    juros_pagos: float = 0.0,
    capex: float | None = -1.0,
    risco_sacado: float = 0.0,
) -> None:
    """`capex` -1.0 (padrão) usa -CFI (se negativo); `None` simula capex não identificado."""
    capex_do_ano = max(-cfi_atual, 0.0) if capex == -1.0 else capex
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre",
        lambda cnpj, ano, *a, **kw: (
            _resultado_fcf_mock(
                cfo_atual, capex_do_ano, juros_pagos, cfi_atual, risco_sacado=risco_sacado
            )
            if ano == ANO_FCD_MOCK
            else _resultado_fcf_mock(1_000_000.0, 200_000.0)
        ),
    )


def _preparar_fcd_com_receita(monkeypatch, receita_atual, receita_base):
    # Fluxo de 1.400.000 no ano de referência e 500.000 no ano-base: CAGR de ~22,9% ao ano.
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre",
        lambda cnpj, ano, *a, **kw: (
            _resultado_fcf_mock(1_600_000.0, 200_000.0, receita=receita_atual)
            if ano == ANO_FCD_MOCK
            else _resultado_fcf_mock(600_000.0, 100_000.0, receita=receita_base)
        ),
    )


def test_cartao_do_fcd_avisa_quando_a_receita_limita_o_crescimento(monkeypatch):
    # Receita de 1.000.000 para 1.610.510 em 5 anos: 10,0% ao ano, abaixo do CAGR do fluxo.
    _preparar_fcd_com_receita(monkeypatch, receita_atual=1_610_510.0, receita_base=1_000_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption]
    assert TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA.format(taxa="10,0%") in legendas
    assert not [c for c in legendas if "sem o limite da receita" in c]


def test_cartao_do_fcd_nao_avisa_quando_a_receita_cresce_mais_que_o_fluxo(monkeypatch):
    _preparar_fcd_com_receita(monkeypatch, receita_atual=9_000_000.0, receita_base=1_000_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption]
    assert not [c for c in legendas if "limitado ao da receita" in c]
    assert not [c for c in legendas if "sem o limite da receita" in c]


def test_cartao_do_fcd_traz_o_motivo_quando_a_receita_esta_indisponivel(monkeypatch):
    _preparar_fcd_com_receita(monkeypatch, receita_atual=None, receita_base=1_000_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption]
    assert TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA.format(motivo=MOTIVO_RECEITA_SEM_DRE) in legendas


def test_caption_reinvestimento_caso_normal(monkeypatch):
    # CFO=1.000.000, capex=300.000 -> reinvestiu 30% do caixa operacional.
    # Texto curto: a explicação de por que isso reduz o FCD fica só no
    # expander "Como funciona esse cálculo?", não repetida aqui no cartão.
    _preparar_fcd_com_cfo_cfi(monkeypatch, cfo_atual=1_000_000.0, cfi_atual=-300_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    captions = [c.value for c in at.caption if "reinvestiu" in c.value]
    assert len(captions) == 1
    assert captions[0] == LEGENDA_REINVESTIMENTO_CAPEX.format(ano=ANO_FCD_MOCK, proporcao=30.0)


def test_pagina_da_acao_sem_nenhum_metodo_mostra_aviso_neutro_e_o_motivo_de_cada_metodo(
    monkeypatch,
):
    from avaliador_b3.config import MOTIVO_FCD_FLUXO_NAO_POSITIVO, TEXTO_COMPLEMENTO_SEM_METODO

    # FCD não aplicável (fluxo negativo), Graham sem LPA/VPA e Bazin sem dividendos.
    _preparar_fcd_com_cfo_cfi(monkeypatch, cfo_atual=-500_000.0, cfi_atual=-100_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.fundamentus.obter_indicadores",
        lambda *args, **kwargs: {
            "lpa": None,
            "vpa": None,
            "numero_acoes": 100.0,
            "roe_percentual": 15.0,
            "margem_liquida_percentual": 10.0,
            "liquidez_corrente": 1.2,
            "crescimento_receita_5a_percentual": 8.0,
            "divida_liquida_sobre_patrimonio": 0.5,
            "divida_liquida": 50_000.0,
            "data_balanco_fundamentus": "2026-06-30",
        },
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    # Sem caixa vermelha de erro: é um aviso neutro, e cada cartão traz o seu motivo.
    assert not [e.value for e in at.error if "Valor combinado" in e.value]
    avisos = [i.value for i in at.info if i.value.startswith("Valor combinado:")]
    assert len(avisos) == 1
    assert avisos[0].endswith(TEXTO_COMPLEMENTO_SEM_METODO)
    assert not [m for m in at.metric if m.label == "Valor combinado"]
    captions = [c.value for c in at.caption]
    assert f"Não aplicável: {MOTIVO_FCD_FLUXO_NAO_POSITIVO}" in captions


def test_fcd_sem_capex_identificado_no_ano_de_referencia_e_nao_aplicavel_com_motivo(
    monkeypatch,
):
    from avaliador_b3.config import MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO

    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre",
        lambda cnpj, ano, *a, **kw: (
            _resultado_fcf_mock(1_200_000.0, None)
            if ano == ANO_FCD_MOCK
            else _resultado_fcf_mock(1_000_000.0, 200_000.0)
        ),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert f"Não aplicável: {MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO}" in [c.value for c in at.caption]


def test_fcd_com_capex_do_ano_base_nao_identificado_mostra_que_o_crescimento_usou_o_ipca(
    monkeypatch,
):
    from avaliador_b3.config import MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX, TEXTO_CRESCIMENTO_IPCA

    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.cvm.obter_fluxo_caixa_livre",
        lambda cnpj, ano, *a, **kw: (
            _resultado_fcf_mock(1_200_000.0, 200_000.0)
            if ano == ANO_FCD_MOCK
            else _resultado_fcf_mock(1_000_000.0, None)
        ),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    esperado = TEXTO_CRESCIMENTO_IPCA.format(motivo=MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX)
    assert esperado in [c.value for c in at.caption]


def test_caption_reinvestimento_divide_pelo_caixa_operacional_do_fcd(monkeypatch):
    # CFO negativo, mas os juros somados de volta (1.000.000 x 0,66) deixam o caixa operacional
    # do FCD em 160.000: a legenda divide o capex (90.000) por ele, não pelo CFO.
    _preparar_fcd_com_cfo_cfi(
        monkeypatch, cfo_atual=-500_000.0, cfi_atual=-90_000.0, juros_pagos=1_000_000.0
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption if "reinvestiu" in c.value]
    assert legendas == [
        LEGENDA_REINVESTIMENTO_CAPEX.format(ano=ANO_FCD_MOCK, proporcao=90_000 / 160_000 * 100)
    ]


def test_caption_reinvestimento_usa_o_caixa_ajustado_pelo_risco_sacado(monkeypatch):
    # Caixa do FCD: 1.000.000 - 400.000 (convênio) + 100.000 x 0,66 = 666.000; capex 300.000.
    _preparar_fcd_com_cfo_cfi(
        monkeypatch,
        cfo_atual=1_000_000.0,
        cfi_atual=-300_000.0,
        juros_pagos=100_000.0,
        risco_sacado=-400_000.0,
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption if "reinvestiu" in c.value]
    assert legendas == [
        LEGENDA_REINVESTIMENTO_CAPEX.format(ano=ANO_FCD_MOCK, proporcao=300_000 / 666_000 * 100)
    ]


def test_caption_reinvestimento_usa_o_capex_e_nao_o_caixa_de_investimento(monkeypatch):
    # O caixa de investimento (CFI) é positivo (venda de ativos e aplicações), mas o
    # capex do fluxo do FCD é 200.000: a legenda mostra capex ÷ caixa operacional = 20%.
    _preparar_fcd_com_cfo_cfi(
        monkeypatch, cfo_atual=1_000_000.0, cfi_atual=500_000.0, capex=200_000.0
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption if "reinvestiu" in c.value]
    assert legendas == [LEGENDA_REINVESTIMENTO_CAPEX.format(ano=ANO_FCD_MOCK, proporcao=20.0)]


def test_caption_reinvestimento_ausente_quando_o_capex_nao_foi_identificado(monkeypatch):
    _preparar_fcd_com_cfo_cfi(monkeypatch, cfo_atual=1_000_000.0, cfi_atual=-300_000.0, capex=None)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not [c.value for c in at.caption if "reinvestiu" in c.value]
    assert not [
        c.value for c in at.caption if "o caixa gerado pela operação foi negativo" in c.value
    ]


def test_expander_fcd_menciona_investimento_pesado(monkeypatch):
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
        "O fluxo de caixa usado é o caixa gerado pela operação menos o que a "
        "empresa gastou em imobilizado e intangível (máquinas, obras, sistemas) "
        "no ano, mais os juros pagos sobre a dívida, já descontado o imposto" in bloco
    )
    assert (
        "empresas em fase de investimento pesado (comuns em energia e "
        "saneamento) ou com dívida muito alta tendem a ter FCD bem abaixo dos "
        "outros métodos" in bloco
    )
    assert (
        "No cartão do FCD, a porcentagem reinvestida no ano aparece logo abaixo do valor." in bloco
    )


def test_caption_screener_topo_e_curta(monkeypatch):
    # A legenda do topo é um parágrafo curto — o detalhe de cada coluna fica no
    # expander "Como ler esta tabela" (ver testes abaixo), pra não crescer sem
    # limite a cada coluna nova.
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
        if "Ranking pelo potencial de valorização até o valor combinado" in c.value
    ]
    assert len(captions) == 1
    assert captions[0] == (
        "Ranking pelo potencial de valorização até o valor combinado (média "
        "simples dos métodos aplicáveis a cada ação). Veja abaixo como ler "
        "cada coluna."
    )


def test_expander_como_ler_tabela_existe(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    rotulos_expander = [e.label for e in at.expander]
    assert "Como ler esta tabela" in rotulos_expander


def test_expander_como_ler_tabela_explica_desconto_e_aviso(monkeypatch):
    # Potencial e Aviso têm item próprio no expander da legenda (junto de
    # Divergência/Dividendos vs. histórico/Reinvestimento).
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [m.value for m in at.markdown if "**Potencial**" in m.value and "**Aviso**" in m.value]
    assert len(blocos) == 1
    bloco = blocos[0]
    assert (
        "**Potencial** — quanto o valor justo combinado está acima (+) ou "
        "abaixo (−) do preço atual (valor justo ÷ preço − 1). O valor "
        "combinado é a média simples de Graham, Bazin e FCD aplicáveis, com "
        "pesos iguais por simplicidade — veja 'Como funciona esse cálculo?' "
        "na aba Analisar uma ação. A tabela vem ordenada do maior para o "
        "menor potencial." in bloco
    )
    assert (
        "**Aviso** — aparece quando o potencial está fora da faixa "
        "considerada confiável (valor justo muito acima ou muito abaixo do "
        "preço); a causa provável varia de uma ação para outra, conforme o "
        "texto de cada aviso. Vazio significa potencial dentro da faixa "
        "normal." in bloco
    )


def test_expander_como_ler_tabela_explica_coluna_reinvestimento(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [
        m.value
        for m in at.markdown
        if "**Reinvestimento** — mostra quanto do caixa gerado pela operação" in m.value
    ]
    assert len(blocos) == 1
    assert (
        "Vazio quando o FCD não se aplica, o investimento não foi identificado "
        "ou o caixa operacional foi negativo." in blocos[0]
    )


# --- Bloco "Datas de referência dos dados usados" (preço/beta/IPCA vêm de
# datas diferentes entre si e do balanço usado pelos indicadores do
# Fundamentus — é o padrão de mercado, mas ficaria invisível na tela sem este
# bloco). Os mocks de
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


def test_aviso_e_datas_referencia_mostram_valor_macro_guardado_quando_bcb_falha(monkeypatch):
    # BCB fora do ar mas com valor guardado recente o bastante (ver
    # ingest.bcb_sgs.obter_selic_e_ipca) — a tela precisa avisar que o
    # valor é o último obtido, não fingir que é "de hoje" como o resto
    # da Selic normalmente é.
    _preparar_fcd_aplicavel(monkeypatch, divida_liquida=50_000.0)

    def obter_serie_falha(*args, **kwargs):
        raise RuntimeError(MENSAGEM_ERRO_MOCK)

    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", obter_serie_falha)
    data_busca_guardada = datetime(2026, 9, 20, 10, 0)
    monkeypatch.setattr(
        "avaliador_b3.ingest.bcb_sgs._carregar_ultimo_macro",
        lambda diretorio_cache: {
            "selic_meta": 0.1375,
            "ipca_12m": 0.045,
            "data_ipca": pd.Timestamp("2026-08-01"),
            "data_busca": pd.Timestamp(data_busca_guardada),
        },
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        aviso.value for aviso in at.warning if "Banco Central indisponível agora" in aviso.value
    ]
    assert len(avisos) == 1
    assert "20/09/2026" in avisos[0]

    bloco = next(m.value for m in at.markdown if "Comparar o preço de hoje" in m.value)
    assert "último valor obtido em 20/09/2026 (Banco Central indisponível agora)." in bloco


def test_buscar_macro_nao_cacheia_erro_e_funciona_na_segunda_chamada(monkeypatch):
    # st.cache_data não pode guardar uma falha temporária do BCB por 1h
    # inteira — primeira chamada falha, segunda (mesmo processo, sem
    # limpar o cache) já usa o valor novo.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at1 = AppTest.from_file(CAMINHO_APP)
    at1.run(timeout=60)
    assert not at1.exception
    bloco1 = next(m.value for m in at1.markdown if "Comparar o preço de hoje" in m.value)
    assert "acumulado até N/D." in bloco1

    monkeypatch.setattr("avaliador_b3.ingest.bcb_sgs.obter_serie", _obter_serie_bcb_falso)

    at2 = AppTest.from_file(CAMINHO_APP)
    at2.run(timeout=60)
    assert not at2.exception
    bloco2 = next(m.value for m in at2.markdown if "Comparar o preço de hoje" in m.value)
    assert "acumulado até 12/2025." in bloco2


def test_fcd_banco_fica_nao_aplicavel_e_combinado_usa_so_graham_bazin(monkeypatch):
    # Segmento "Bancos" -> FCD "não aplicável",
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

    divergencias = [c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value]
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
    divergencias = [c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value]
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
    divergencias = [c.value for c in at.caption if "Os métodos aplicáveis vão de" in c.value]
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
    # O preço teto
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
    avisos = [c.value for c in at.caption if "Dividendos dos últimos 12 meses em" in c.value]
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
    avisos = [c.value for c in at.caption if "Dividendos dos últimos 12 meses em" in c.value]
    assert avisos == []


def test_saude_financeira_mostra_numeros_com_virgula_brasileira(monkeypatch):
    # ROE/Margem líquida/LPA/VPA/Liquidez corrente passam por `_fmt()` com
    # conversão de ponto pra vírgula (ex: "15,0%"/"R$ 5,00", não
    # "15.0%"/"R$ 5.00").
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
    # _cartao_correlacao converte o ponto decimal em vírgula (ex: "1,00", não "1.00").
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
    # só porque os níveis são lineares opostos); o que importa é o formato:
    # vírgula decimal, não ponto.
    valor_petroleo = _metrica_por_label(at, "Petróleo (Brent)").value
    assert re.fullmatch(r"-?\d,\d\d", valor_petroleo), (
        f"correlação não está no formato brasileiro esperado: {valor_petroleo!r}"
    )


def test_correlacao_mostra_data_do_ultimo_dado_do_gpr(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    serie_gpr = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-09-01", "2026-09-20", "2026-09-25"]),
            "GPRD": [90.0, 100.0, 110.0],
        }
    )
    monkeypatch.setattr("avaliador_b3.ingest.gpr.obter_gpr", lambda *args, **kwargs: serie_gpr)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_por_periodo(
            {"1d": 50.0, "3mo": 50.0, "1y": 50.0, f"{ANOS_JANELA_CORRELACAO}y": 50.0}
        ),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption]
    assert "Último dado do GPR: 25/09/2026." in legendas


def test_correlacao_sem_serie_gpr_nao_mostra_data_do_ultimo_dado(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not any(c.value.startswith("Último dado do GPR") for c in at.caption)


def test_grafico_dividendos_mostra_rotulos_com_virgula_brasileira(monkeypatch):
    # figura_dividendos usava texttemplate="R$ %{text:.2f}" e "%{text:.1f}%"
    # — o d3-format que o Plotly usa por trás desses especificadores tem o
    # mesmo problema de locale do _fmt/_fmt_bilhoes (sem vírgula decimal
    # brasileira sem registrar um locale que o bundle do Streamlit não
    # traz). `text` é pré-formatado com _fmt_bilhoes/
    # _fmt_percentual e usa "%{text}" (passthrough) no texttemplate.
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


# --- Gráfico "Preço vs. Ibovespa" sem dados válidos ------------------------


def _historico_beta_falso(close_acao: list[float]):
    """Fake de `obter_historico` com Close configurável pro histórico de
    1 ano (PERIODO_BETA, usado no gráfico "Preço vs. Ibovespa") — os
    demais períodos devolvem um valor válido fixo, sem relação com o
    caso testado."""

    def historico_falso(ticker, periodo="3mo", auto_adjust=True, **kwargs):
        if periodo == "1y":
            return pd.DataFrame(
                {
                    "data": pd.to_datetime(
                        [f"2025-09-{15 + i:02d}" for i in range(len(close_acao))], utc=True
                    ),
                    "Close": close_acao,
                    "Volume": [1000] * len(close_acao),
                }
            )
        return pd.DataFrame(
            {
                "data": pd.to_datetime(["2026-09-15"], utc=True),
                "Close": [50.0],
                "Volume": [30_000_000],
            }
        )

    return historico_falso


def _historico_ibovespa_falso(close_ibovespa: list[float]):
    def historico_falso(periodo="3mo", **kwargs):
        return pd.DataFrame(
            {
                "data": pd.to_datetime(
                    [f"2025-09-{15 + i:02d}" for i in range(len(close_ibovespa))], utc=True
                ),
                "Close": close_ibovespa,
                "Volume": [0] * len(close_ibovespa),
            }
        )

    return historico_falso


def test_grafico_preco_vs_ibovespa_nomeia_a_serie_sem_dados_quando_so_uma_falha(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_beta_falso([float("nan"), float("nan")]),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico_ibovespa",
        _historico_ibovespa_falso([130_000.0, 131_000.0]),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        i.value
        for i in at.info
        if "Sem dados suficientes de" in i.value and "para montar este gráfico." in i.value
    ]
    assert len(avisos) == 1
    assert avisos[0] == "Sem dados suficientes de PETR4 para montar este gráfico."


def test_grafico_preco_vs_ibovespa_mensagem_generica_quando_as_duas_series_falham(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico",
        _historico_beta_falso([float("nan"), float("nan")]),
    )
    monkeypatch.setattr(
        "avaliador_b3.ingest.precos.obter_historico_ibovespa",
        _historico_ibovespa_falso([float("nan"), float("nan")]),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    avisos = [
        i.value for i in at.info if i.value == "Sem dados suficientes para montar este gráfico."
    ]
    assert len(avisos) == 1


# --- Formatação abreviada de Valor de mercado/Dívida líquida/Valor de firma --
#
# Sem abreviação, o valor por extenso (ex: "R$ 625,10 bi") seria truncado com
# reticências pelo st.metric dentro da coluna estreita de 4 da seção "Saúde
# financeira" (ex: "R$ 625,1..."). `_fmt_bilhoes` cobre isso com "X,X bi"/"X,X
# mi".


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


# --- Simulador de carteira (potencial sem prazo) -----------------------------
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


def test_screener_mostra_acao_sem_nenhum_metodo_no_fim_sem_potencial_e_sem_erro(
    monkeypatch, tmp_path
):
    import avaliador_b3.screener as screener_mod
    from avaliador_b3.screener import COLUNAS_RESULTADO

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    base = {c: None for c in COLUNAS_RESULTADO} | {
        "sucesso": True,
        "aviso_desconto_extremo": "",
    }
    linhas = [
        # Sem nenhum método aplicável, como o screener grava (ex.: ação só com FCD
        # e fluxo de caixa negativo). Vem primeiro no arquivo de propósito.
        base
        | {
            "ticker": "SEMM3",
            "erro": "Nenhum dos três métodos (Graham, Bazin, FCD) é aplicável a essa ação.",
            "preco_atual": 5.4,
            "metodos_utilizados": "",
        },
        base
        | {
            "ticker": "NORM4",
            "erro": "",
            "preco_atual": 40.0,
            "valor_combinado": 60.0,
            "desconto_percentual": 50.0,
            "metodos_utilizados": "graham",
            "graham_valor_justo": 60.0,
        },
    ]
    caminho_screener_falso = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho_screener_falso, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not [e.value for e in at.error if "Nenhum dos três métodos" in e.value]
    tabelas = [df for df in at.dataframe if "desconto_percentual" in df.value.columns]
    assert len(tabelas) == 1
    tabela = tabelas[0].value
    # No fim da tabela, com potencial indisponível e o motivo na coluna de observação.
    assert list(tabela["ticker"]) == ["NORM4", "SEMM3"]
    linha_sem_metodo = tabela.loc[tabela["ticker"] == "SEMM3"].iloc[0]
    assert linha_sem_metodo["desconto_percentual"] == "N/D"
    assert linha_sem_metodo["erro"].startswith("Nenhum dos três métodos")
    rotulos = json.loads(tabelas[0].proto.columns)
    assert rotulos["erro"]["label"] == "Observação"


def _obter_serie_bcb_falso(codigo, data_inicial=None, data_final=None, **kwargs):
    from avaliador_b3.config import SERIES_BCB_SGS

    if codigo == SERIES_BCB_SGS["selic_meta"]:
        return pd.DataFrame({"data": pd.to_datetime(["2026-01-01"]), "valor": [10.5]})
    if codigo == SERIES_BCB_SGS["ipca_mensal"]:
        datas = pd.date_range("2025-01-01", periods=12, freq="MS")
        return pd.DataFrame({"data": datas, "valor": [0.3] * 12})
    raise RuntimeError(f"série {codigo} não mockada neste teste")


def test_tabela_screener_mostra_moeda_e_percentual_com_virgula_brasileira(monkeypatch, tmp_path):
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


def test_faixa_amarela_desconto_extremo_referencia_o_nome_visivel_da_coluna(monkeypatch, tmp_path):
    # A faixa amarela deve citar o nome visível da coluna ("Aviso", ver
    # column_config em app/main.py), não o nome interno do CSV
    # ("aviso_desconto_extremo") -- quem lesse a faixa não acharia nenhuma coluna
    # com esse nome na tela.
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
    avisos = [w.value for w in at.warning if "ação(ões) com potencial fora do comum" in w.value]
    assert len(avisos) == 1
    assert avisos[0] == (
        "1 ação(ões) com potencial fora do comum (valor justo muito acima ou "
        'muito abaixo do preço) — veja a coluna "Aviso" na tabela: a causa '
        "provável varia de uma ação para outra."
    )
    assert "aviso_desconto_extremo" not in avisos[0]


def test_botao_screener_mostra_aviso_na_tela_quando_deteccao_do_ano_falha(monkeypatch):
    # warnings.warn dentro de rodar_screener vai só
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

    botao_screener = next(b for b in at.button if b.label == "Rodar screener agora")
    botao_screener.click().run(timeout=60)

    assert not at.exception
    avisos = [
        aviso.value
        for aviso in at.warning
        if "Detecção do ano mais recente da CVM falhou" in aviso.value
    ]
    assert len(avisos) == 1
    assert "CVM fora do ar (simulado)" in avisos[0]


def test_botao_screener_mostra_aviso_na_tela_quando_bcb_falha(monkeypatch):
    # P07 (docs/auditoria-tecnica-2026-09-27.md): _buscar_macro (Selic/
    # IPCA do BCB) falhando dentro de rodar_screener não pode ser silencioso —
    # sem aviso, o FCD de todas as ações da rodada sumiria sem explicação em
    # lugar nenhum visível. Mesmo padrão do teste acima
    # pra detecção do ano da CVM: rodar_screener é substituído por um
    # fake que só emite o aviso (o comportamento real de emiti-lo
    # quando _buscar_macro falha já é coberto em tests/test_screener.py).
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    def rodar_screener_falso(*args, **kwargs):
        warnings.warn(
            "Selic/IPCA indisponíveis — o FCD de todas as ações desta rodada "
            "ficará indisponível: BCB fora do ar (simulado)",
            category=MacroIndisponivelWarning,
            stacklevel=2,
        )

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodar_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    botao_screener = next(b for b in at.button if b.label == "Rodar screener agora")
    with pytest.warns(MacroIndisponivelWarning, match="Selic/IPCA indisponíveis"):
        botao_screener.click().run(timeout=60)

    assert not at.exception
    avisos = [aviso.value for aviso in at.warning if "Selic/IPCA indisponíveis" in aviso.value]
    assert len(avisos) == 1
    assert "BCB fora do ar (simulado)" in avisos[0]


def test_botao_screener_rodada_rejeitada_mostra_o_motivo_e_o_arquivo_rejeitado(monkeypatch):
    from pathlib import Path

    from avaliador_b3.screener import RodadaScreenerRejeitada

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    def rodar_screener_falso(*args, **kwargs):
        raise RodadaScreenerRejeitada(
            "40 ações com falha de fonte (limite: 5); "
            "por fonte: Fundamentus: 40, CVM: 0, Yahoo: 1.",
            Path("data/processed/screener.rejeitado.csv"),
        )

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodar_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    next(b for b in at.button if b.label == "Rodar screener agora").click().run(timeout=60)

    assert not at.exception
    erros = [e.value for e in at.error if e.value.startswith("Rodada descartada")]
    assert len(erros) == 1
    assert "Fundamentus: 40, CVM: 0, Yahoo: 1" in erros[0]
    assert "screener.rejeitado.csv" in erros[0]
    assert not [s for s in at.success if "Screener concluído" in s.value]


def test_botao_screener_rodada_aceita_lista_as_acoes_com_falha_de_fonte(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    def rodar_screener_falso(*args, **kwargs):
        resultado = pd.DataFrame()
        resultado.attrs["falhas_de_fonte"] = {"WEGE3": ["Yahoo"], "VALE3": ["Fundamentus"]}
        return resultado

    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", rodar_screener_falso)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    next(b for b in at.button if b.label == "Rodar screener agora").click().run(timeout=60)

    assert not at.exception
    mensagens = [s.value for s in at.success if s.value.startswith("Screener concluído")]
    assert len(mensagens) == 1
    assert "VALE3 (Fundamentus), WEGE3 (Yahoo)" in mensagens[0]


def test_botao_screener_rodada_sem_falhas_mostra_so_a_mensagem_de_conclusao(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    monkeypatch.setattr("avaliador_b3.screener.rodar_screener", lambda *a, **k: pd.DataFrame())

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    next(b for b in at.button if b.label == "Rodar screener agora").click().run(timeout=60)

    assert not at.exception
    assert "Screener concluído — resultado salvo em disco." in [s.value for s in at.success]


def test_expander_como_ler_tabela_explica_dividendos_vs_historico_vazio(monkeypatch):
    # A coluna "Dividendos vs. histórico" fica vazia tanto quando o Bazin
    # não se aplica quanto (raramente) quando a mediana dos 5 anos sai
    # zero — o item do expander "Como ler esta tabela" precisa deixar
    # isso claro, sem deixar a coluna vazia parecendo um dado faltando
    # por erro. O texto fica em `st.markdown` dentro do expander.
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    blocos = [
        m.value
        for m in at.markdown
        if "Dividendos vs. histórico vazio significa que o Bazin não se aplica" in m.value
    ]
    assert len(blocos) == 1
    assert "ou, raramente, que os anos anteriores não têm pagamento para comparar" in blocos[0]


def _escrever_screener_falso_para_simulador(caminho) -> None:
    from avaliador_b3.screener import COLUNAS_RESULTADO

    base = {c: None for c in COLUNAS_RESULTADO} | {
        "sucesso": True,
        "erro": "",
        "aviso_desconto_extremo": "",
    }
    linhas = [
        # DOBR4: um só método (Graham = 80) -> os três cenários valem 2x o preço.
        base
        | {
            "ticker": "DOBR4",
            "preco_atual": 40.0,
            "valor_combinado": 80.0,
            "metodos_utilizados": "graham",
            "graham_valor_justo": 80.0,
        },
        # SEMC3: nenhum método aplicável.
        base | {"ticker": "SEMC3", "preco_atual": 10.0, "metodos_utilizados": ""},
        # NEGA4: FCD negativo -> o cenário pessimista é limitado a perda total.
        base
        | {
            "ticker": "NEGA4",
            "preco_atual": 10.0,
            "valor_combinado": 7.5,
            "metodos_utilizados": "graham,fcd",
            "graham_valor_justo": 20.0,
            "fcd_valor_justo": -5.0,
        },
    ]
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)


def test_simulador_mostra_potencial_sem_prazo_e_limita_a_perda_a_100_por_cento(
    monkeypatch, tmp_path
):
    import avaliador_b3.screener as screener_mod
    from avaliador_b3.config import ROTULOS_POTENCIAL_CENARIO

    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )
    _bloquear_buscas_de_rede_por_ticker(monkeypatch)
    caminho_screener_falso = tmp_path / "screener.csv"
    _escrever_screener_falso_para_simulador(caminho_screener_falso)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho_screener_falso)

    def _aba_carteira(at):
        return [tab for tab in at.tabs if tab.label == "Simulador de carteira"][0]

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)
    assert not at.exception

    _aba_carteira(at).multiselect[0].set_value(["DOBR4", "SEMC3", "NEGA4"])
    at.run(timeout=60)
    at.number_input(key="investimento_DOBR4").set_value(1000.0)
    at.number_input(key="investimento_SEMC3").set_value(300.0)
    at.number_input(key="investimento_NEGA4").set_value(500.0)
    at.run(timeout=60)
    assert not at.exception
    aba = _aba_carteira(at)

    # Perda acima de 100% continua limitada: NEGA4 pessimista = FCD -5 -> perda
    # total (R$ 0, -100%); otimista = Graham 20 contra preço 10 -> +100%.
    tabelas = [df for df in aba.dataframe if "projecao_pessimista" in df.value.columns]
    assert len(tabelas) == 1
    linha_nega4 = tabelas[0].value.loc[tabelas[0].value["ticker"] == "NEGA4"].iloc[0]
    assert linha_nega4["projecao_pessimista"] == "R$ 0,00"
    assert linha_nega4["retorno_pessimista_percentual"] == "-100,0%"
    assert linha_nega4["retorno_otimista_percentual"] == "100,0%"
    rotulos_colunas = json.loads(tabelas[0].proto.columns)
    assert (
        rotulos_colunas["retorno_pessimista_percentual"]["label"]
        == ROTULOS_POTENCIAL_CENARIO["pessimista"]
    )
    assert rotulos_colunas["retorno_base_percentual"]["help"] == (
        "Quanto o valor justo do cenário está acima (+) ou abaixo (−) do preço atual "
        "(valor justo ÷ preço − 1). Não é retorno esperado nem tem prazo."
    )
    assert any(
        "NEGA4: cenário(s) Pessimista limitado(s) a perda total" in c.value for c in aba.caption
    )

    # Frase-resumo: só DOBR4 e NEGA4 têm cenário (R$ 1.500,00 investidos);
    # pessimista = 2.000 (DOBR4) + 0 (NEGA4, piso); otimista = 2.000 + 1.000.
    frases = [m.value for m in aba.markdown if "sem prazo definido" in m.value]
    assert len(frases) == 1
    assert frases[0] == (
        "R\\$ 1.500,00 investidos hoje equivaleriam a entre R\\$ 2.000,00 (pessimista) e "
        "R\\$ 3.000,00 (otimista) se os preços convergissem aos valores justos, sem prazo "
        "definido."
    )
    assert any("ficaram de fora desse cálculo" in c.value for c in aba.caption)
    assert (
        "Quanto a carteira valeria se o preço de cada ação chegasse ao valor justo do "
        "cenário, em reais de hoje, sem prazo e sem contar dividendos. Não é previsão."
    ) in [c.value for c in aba.caption]

    # Sem prazo, taxa anual nem ganho real.
    textos = [c.value for c in aba.caption] + [m.value for m in aba.markdown]
    for proibido in ("ao ano", "Ganho real", "CAGR", "IPCA", " anos"):
        assert not any(proibido in texto for texto in textos), proibido
    assert len(aba.pills) == 0
    assert not any("ganho_real" in df.value.columns for df in aba.dataframe)


def test_cartao_do_fcd_mostra_o_valor_reclassificado_do_risco_sacado_e_o_motivo(monkeypatch):
    _preparar_fcd_com_cfo_cfi(
        monkeypatch,
        cfo_atual=15_000_000_000.0,
        cfi_atual=-300_000_000.0,
        risco_sacado=-13_500_000_000.0,
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    legendas = [c.value for c in at.caption if "convênio com fornecedores" in c.value]
    assert legendas == [
        TEXTO_RISCO_SACADO_RECLASSIFICADO.format(ano=ANO_FCD_MOCK, valor="R\\$ 13,5 bi")
    ]
    assert legendas[0] == (
        f"Em {ANO_FCD_MOCK}, R\\$ 13,5 bi pagos a bancos em operações de convênio com "
        "fornecedores (risco sacado ou similar), registrados no caixa de financiamento, foram "
        "tratados como operacionais: esses pagamentos substituem pagamentos a fornecedores, e "
        "sem o ajuste o caixa operacional pode parecer maior do que a geração de caixa da empresa."
    )


def test_cartao_do_fcd_nao_menciona_risco_sacado_quando_nao_ha_ajuste(monkeypatch):
    _preparar_fcd_com_cfo_cfi(monkeypatch, cfo_atual=1_000_000.0, cfi_atual=-300_000.0)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert not [c.value for c in at.caption if "convênio com fornecedores" in c.value]
