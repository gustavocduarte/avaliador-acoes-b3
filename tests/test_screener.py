import dataclasses
import json
import warnings

import pandas as pd
import pytest
import requests

from avaliador_b3 import screener
from avaliador_b3.config import MENSAGEM_PRECO_INDISPONIVEL_SCREENER
from avaliador_b3.ingest import bcb_sgs
from avaliador_b3.ingest.precos import TickerInvalido

# Ano fixo usado pelos mocks de FCD abaixo — substitui screener.
# ANO_REFERENCIA_FCD (removida em 2026-09-23, ver
# docs/correcao-ano-fcd-2026-09-23.md), já que o ano agora é detectado em
# tempo de execução (ingest.cvm.resolver_ano_mais_recente_disponivel), não
# uma constante.
ANO_FCD_MOCK = 2025

# A fixture `ambiente_feliz` troca `screener._buscar_macro`; os testes de BCB usam a real.
_BUSCAR_MACRO_REAL = screener._buscar_macro
MACRO_AO_VIVO = bcb_sgs.ResultadoMacro(
    selic_meta=0.10,
    ipca_12m=0.04,
    data_ipca=pd.Timestamp("2026-08-01"),
    usou_valor_guardado=False,
    data_busca=pd.Timestamp("2026-10-03 12:00"),
    fonte_selic="BCB (SOAP)",
    fonte_ipca="IBGE (SIDRA)",
)


def _historico(fechamentos: list[float]) -> pd.DataFrame:
    datas = pd.date_range("2026-01-01", periods=len(fechamentos), freq="D")
    return pd.DataFrame({"data": datas, "Close": fechamentos, "Volume": [1000] * len(fechamentos)})


def _indicadores(
    lpa=5.0,
    vpa=20.0,
    numero_acoes=1000.0,
    divida_liquida_sobre_patrimonio=0.3,
    divida_liquida=None,
    data_balanco_fundamentus="2026-06-30",
):
    return {
        "lpa": lpa,
        "vpa": vpa,
        "numero_acoes": numero_acoes,
        "divida_liquida_sobre_patrimonio": divida_liquida_sobre_patrimonio,
        # None por padrão (não deduzida do FCD) — preserva os valores/
        # potenciais que os testes existentes já esperavam antes da
        # correção de 2026-09-23; ver test_fcd.py pra cobertura da
        # dedução em si.
        "divida_liquida": divida_liquida,
        "data_balanco_fundamentus": data_balanco_fundamentus,
        "acoes_por_cotacao": 1,
    }


def _leitura_balanco(
    nao_controladores=0.0,
    patrimonio_liquido_total=None,
    arrendamento_fora_da_divida=0.0,
    acoes_em_circulacao=None,
    motivo_acoes=None,
):
    """Leitura única do balanço da CVM (`ingest.balanco_cvm.obter_leitura_balanco`)."""
    return {
        "disponivel": True,
        "motivo": None,
        "data_base": "2026-06-30",
        "nao_controladores": nao_controladores,
        "patrimonio_liquido_total": patrimonio_liquido_total,
        "arrendamento_fora_da_divida": arrendamento_fora_da_divida,
        "acoes_em_circulacao": acoes_em_circulacao,
        "motivo_acoes": motivo_acoes,
    }


def _dividendos_vazio() -> pd.DataFrame:
    # Bazin sempre "não aplicável" com histórico vazio — o caso mais
    # simples e determinístico de simular; a lógica de aplicabilidade do
    # Bazin em si já é testada em test_bazin.py, não é o foco aqui.
    return pd.DataFrame({"data": pd.to_datetime([]), "dividendo": pd.Series(dtype=float)})


def _capex(valor):
    status = "identificado" if valor is not None else "nao_identificado"
    return {"status": status, "valor": valor, "linhas": []}


def _resultado_fcf_cvm(
    ano_mais_recente,
    cfo=1_200_000.0,
    capex=200_000.0,
    cfo_base=1_000_000.0,
    capex_base=200_000.0,
    juros=0.0,
):
    """Resultado de `obter_fluxo_caixa_livre_com_fallback`: com os padrões, o
    fluxo do FCD é 1.000.000 no ano de referência e 800.000 no ano-base."""
    return {
        "fcf_atual": cfo - (capex or 0.0),
        "fcf_ha_n_anos": cfo_base - (capex_base or 0.0),
        "ano_referencia_utilizado": ano_mais_recente,
        "ano_mais_recente_disponivel": ano_mais_recente,
        "usou_fallback": False,
        "cfo_atual": cfo,
        "cfi_atual": -(capex or 0.0),
        "capex_atual": _capex(capex),
        "juros_pagos_atual": {"valor": juros, "linhas": []},
        "cfo_ha_n_anos": cfo_base,
        "capex_ha_n_anos": _capex(capex_base),
        "juros_pagos_ha_n_anos": {"valor": juros, "linhas": []},
    }


@pytest.fixture
def ambiente_feliz(monkeypatch):
    """Monkeypatcha os adapters usados por screener.py com dado fake
    simples e controlado — por padrão todo ticker tem sucesso, com Graham
    e FCD aplicáveis (Bazin não, por simplicidade determinística)."""
    ibovespa = _historico([100.0, 101.0, 99.0, 102.0, 103.0])
    precos_por_ticker = {"AAAA4": 40.0, "BBBB4": 40.0}

    def historico_falso(ticker, periodo, diretorio_cache=None):
        preco = precos_por_ticker.get(ticker, 40.0)
        return _historico([preco - 2, preco - 1, preco - 1.5, preco + 0.5, preco])

    monkeypatch.setattr(screener, "obter_historico", historico_falso)
    monkeypatch.setattr(screener, "obter_historico_ibovespa", lambda **kw: ibovespa)
    monkeypatch.setattr(
        screener,
        "obter_universo_ibovespa",
        lambda **kw: pd.DataFrame({"ticker": ["AAAA4", "BBBB4"]}),
    )
    monkeypatch.setattr(screener, "obter_catalogo_emissores", lambda **kw: pd.DataFrame())
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        # segmento_setorial genérico (não-financeiro) por padrão — os
        # testes de exclusão do FCD por segmento têm sua própria fixture
        # em test_fcd.py; aqui só precisa não bater com
        # SEGMENTOS_FCD_NAO_APLICAVEL, pra não mudar o comportamento que
        # esses testes já esperavam.
        lambda ticker, catalogo: {
            "cnpj": f"CNPJ-{ticker}",
            "segmento_setorial": "Setor Genérico",
        },
    )
    monkeypatch.setattr(screener, "obter_indicadores", lambda ticker, **kw: _indicadores())
    monkeypatch.setattr(screener, "obter_dividendos", lambda ticker, **kw: _dividendos_vazio())
    monkeypatch.setattr(
        screener,
        "resolver_ano_mais_recente_disponivel",
        lambda **kw: ANO_FCD_MOCK,
    )
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: _resultado_fcf_cvm(
            ano_mais_recente
        ),
    )
    monkeypatch.setattr(screener, "_buscar_macro", lambda diretorio_cache: MACRO_AO_VIVO)
    monkeypatch.setattr(screener, "obter_leitura_balanco", lambda *a, **kw: _leitura_balanco())

    return {"precos_por_ticker": precos_por_ticker}


def test_rodar_screener_processa_ticker_com_sucesso(ambiente_feliz, tmp_path):
    caminho_saida = tmp_path / "screener.csv"

    resultado = screener.rodar_screener(
        tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=caminho_saida
    )

    assert len(resultado) == 1
    linha = resultado.iloc[0]
    assert linha["ticker"] == "AAAA4"
    assert linha["sucesso"]
    assert linha["preco_atual"] == pytest.approx(40.0)
    assert linha["graham_valor_justo"] is not None
    assert linha["fcd_valor_justo"] is not None
    assert linha["ano_referencia_fcd"] == ANO_FCD_MOCK
    assert linha["data_balanco_fundamentus"] == "2026-06-30"
    assert linha["bazin_preco_teto"] is None  # dividendos vazios -> não aplicável
    assert linha["bazin_razao_dividendos_percentual"] is None
    assert "graham" in linha["metodos_utilizados"]
    assert "fcd" in linha["metodos_utilizados"]
    assert "bazin" not in linha["metodos_utilizados"]
    assert linha["desconto_percentual"] is not None
    # 2 métodos aplicáveis (Graham + FCD, Bazin não) -> divergência
    # calculável. Deriva o esperado dos próprios graham/fcd da linha (não
    # do FCD à mão, que depende de WACC/beta) -- cross-validação
    # relacional, não um número mágico hardcoded.
    diferenca_esperada = abs(linha["graham_valor_justo"] - linha["fcd_valor_justo"])
    divergencia_esperada = diferenca_esperada / linha["preco_atual"] * 100
    assert linha["divergencia_percentual_metodos"] == pytest.approx(divergencia_esperada)


def test_rodar_screener_divergencia_fica_nula_com_um_so_metodo_aplicavel(
    ambiente_feliz, tmp_path, monkeypatch
):
    # FCD não aplicável (banco) + Bazin não aplicável (dividendos vazios,
    # padrão de ambiente_feliz) -> só Graham sobra. Não existe
    # "divergência" entre um único valor.
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        lambda ticker, catalogo: {"cnpj": f"CNPJ-{ticker}", "segmento_setorial": "Bancos"},
    )

    resultado = screener.rodar_screener(
        tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
    )

    linha = resultado.iloc[0]
    assert linha["graham_valor_justo"] is not None
    assert linha["fcd_valor_justo"] is None
    assert linha["bazin_preco_teto"] is None
    assert linha["divergencia_percentual_metodos"] is None


def test_calcular_linha_ticker_bazin_razao_dividendos_percentual(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Investigação de 2026-09-25 (achado em revisão externa): o preço teto
    # do Bazin usa só os últimos 12 meses, sem distinguir provento
    # ordinário de extraordinário — a razão contra a mediana dos 5 anos
    # anteriores é o sinal disso. R$3,00 nos últimos 12 meses (ano_atual-1)
    # contra R$1,00 nos outros 4 anos -> mediana=R$1,00, razão=3,0 (300%).
    # A coluna grava em PORCENTAGEM (razão × 100), não a razão bruta — ver
    # config.RAZAO_DIVIDENDOS_ATIPICA_BAZIN.
    ano_atual = pd.Timestamp.now().year
    dividendos = pd.DataFrame(
        {
            "data": [pd.Timestamp(year=ano_atual - i, month=12, day=1) for i in range(1, 6)],
            "dividendo": [3.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    monkeypatch.setattr(screener, "obter_dividendos", lambda ticker, **kw: dividendos)

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["bazin_preco_teto"] == pytest.approx(3.0 / 0.06)
    assert linha["bazin_razao_dividendos_percentual"] == pytest.approx(300.0)


def test_calcular_linha_ticker_fundamentus_com_erro_de_rede_nao_derruba_a_linha(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Graham e FCD dependem de dado do Fundamentus (LPA/VPA e número de
    # ações, respectivamente) e ficam não aplicáveis; Bazin só depende de
    # dividendos, segue calculado normalmente — a linha inteira não vira
    # "Erro inesperado" por uma falha de rede numa fonte só.
    def obter_indicadores_falha(*args, **kwargs):
        resposta = type("RespostaFalsa", (), {"status_code": 503})()
        raise requests.HTTPError("503 Server Error", response=resposta)

    monkeypatch.setattr(screener, "obter_indicadores", obter_indicadores_falha)

    ano_atual = pd.Timestamp.now().year
    dividendos_validos = pd.DataFrame(
        {
            "data": [pd.Timestamp(year=ano_atual - i, month=12, day=1) for i in range(1, 6)],
            "dividendo": [1.0] * 5,
        }
    )
    monkeypatch.setattr(screener, "obter_dividendos", lambda ticker, **kw: dividendos_validos)

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["sucesso"] is True
    assert linha["erro"] is None
    assert linha["graham_valor_justo"] is None
    assert linha["fcd_valor_justo"] is None
    assert linha["bazin_preco_teto"] == pytest.approx(1.0 / 0.06)
    assert linha["metodos_utilizados"] == "bazin"


def _erro_503():
    resposta = type("RespostaFalsa", (), {"status_code": 503})()
    return requests.HTTPError("503 Server Error", response=resposta)


def test_rodar_screener_disjuntor_para_de_consultar_fundamentus_apos_3_falhas_seguidas(
    ambiente_feliz, tmp_path, monkeypatch
):
    consultados = []

    def indicadores_falha(ticker, **kwargs):
        consultados.append(ticker)
        raise _erro_503()

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_falha)
    tickers = ["AAAA4", "BBBB4", "CCCC4", "DDDD4", "EEEE4"]

    with pytest.warns(screener.FundamentusIndisponivelWarning, match="Fundamentus indisponível"):
        resultado = screener.rodar_screener(
            tickers=tickers, diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
        )

    assert consultados == ["AAAA4", "BBBB4", "CCCC4"]
    restantes = resultado[resultado["ticker"].isin(["DDDD4", "EEEE4"])]
    assert restantes["sucesso"].all()
    assert restantes["graham_valor_justo"].isna().all()
    assert restantes["fcd_valor_justo"].isna().all()


def test_calcular_linha_ticker_com_disjuntor_aberto_nao_consulta_e_explica_graham_e_fcd(
    ambiente_feliz, tmp_path, monkeypatch
):
    def obter_indicadores_proibido(*args, **kwargs):
        raise AssertionError("não deveria consultar o Fundamentus com o disjuntor aberto")

    monkeypatch.setattr(screener, "obter_indicadores", obter_indicadores_proibido)

    recebidos = {}

    def combinado_falso(resultado_graham, resultado_bazin, resultado_fcd):
        recebidos["graham"] = resultado_graham
        recebidos["fcd"] = resultado_fcd
        return {
            "aplicavel": False,
            "valor_combinado": None,
            "valores_por_metodo": {},
            "metodos_utilizados": [],
            "motivo_nao_aplicavel": "simulado",
        }

    monkeypatch.setattr(screener, "calcular_valor_combinado", combinado_falso)

    disjuntor = screener.DisjuntorFundamentus()
    for _ in range(disjuntor.limite):
        disjuntor.registrar_falha_de_rede()
    assert disjuntor.aberto

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
        disjuntor_fundamentus=disjuntor,
    )

    assert linha["sucesso"] is True
    for metodo in ("graham", "fcd"):
        assert recebidos[metodo]["aplicavel"] is False
        assert recebidos[metodo]["motivo_nao_aplicavel"] == "Fundamentus indisponível nesta rodada"


def test_rodar_screener_disjuntor_avisa_uma_vez_so(ambiente_feliz, tmp_path, monkeypatch):
    def indicadores_falha(ticker, **kwargs):
        raise _erro_503()

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_falha)

    with pytest.warns(screener.FundamentusIndisponivelWarning) as avisos:
        screener.rodar_screener(
            tickers=["AAAA4", "BBBB4", "CCCC4", "DDDD4", "EEEE4"],
            diretorio_cache=tmp_path,
            caminho_saida=tmp_path / "screener.csv",
        )

    globais = [a for a in avisos if a.category is screener.FundamentusIndisponivelWarning]
    assert len(globais) == 1


def test_rodar_screener_disjuntor_nao_abre_se_a_sequencia_de_falhas_de_rede_for_interrompida(
    ambiente_feliz, tmp_path, monkeypatch
):
    from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado

    consultados = []

    def indicadores_alternados(ticker, **kwargs):
        consultados.append(ticker)
        if ticker == "CCCC4":
            raise TickerNaoEncontrado("simulado")
        raise _erro_503()

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_alternados)
    tickers = ["AAAA4", "BBBB4", "CCCC4", "DDDD4", "EEEE4"]

    with warnings.catch_warnings():
        warnings.simplefilter("error", screener.FundamentusIndisponivelWarning)
        screener.rodar_screener(
            tickers=tickers, diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
        )

    assert consultados == tickers


def _linha_ticker(ticker, tmp_path):
    return screener._calcular_linha_ticker(
        ticker,
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )


def test_calcular_linha_ticker_fcf_de_referencia_negativo_deixa_o_fcd_de_fora(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: _resultado_fcf_cvm(
            ano_mais_recente, cfo=-100_000.0, capex=200_000.0
        ),
    )

    linha = _linha_ticker("AAAA4", tmp_path)

    assert linha["sucesso"] is True
    assert linha["fcd_valor_justo"] is None
    assert "fcd" not in linha["metodos_utilizados"].split(",")
    assert linha["graham_valor_justo"] is not None  # os outros métodos seguem


def test_calcular_linha_ticker_capex_nao_identificado_deixa_o_fcd_de_fora(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: _resultado_fcf_cvm(
            ano_mais_recente, capex=None
        ),
    )

    linha = _linha_ticker("AAAA4", tmp_path)

    assert linha["fcd_valor_justo"] is None
    assert "fcd" not in linha["metodos_utilizados"].split(",")
    assert linha["graham_valor_justo"] is not None


def test_calcular_linha_ticker_usa_o_fluxo_da_alt3_nos_dois_anos(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Mesmo FCD que o fluxo de 1.000.000 (ano de referência) e 800.000 (base)
    # sem juros; com juros pagos somados de volta (líquidos de imposto), o
    # fluxo sobe e o FCD também.
    sem_juros = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: _resultado_fcf_cvm(
            ano_mais_recente, juros=100_000.0
        ),
    )

    com_juros = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]

    assert com_juros > sem_juros


def test_calcular_linha_ticker_desconta_os_nao_controladores_do_fcd(
    ambiente_feliz, tmp_path, monkeypatch
):
    sem_ajuste = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]
    monkeypatch.setattr(
        screener,
        "obter_leitura_balanco",
        lambda *a, **kw: _leitura_balanco(nao_controladores=5_000.0),
    )

    com_ajuste = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]

    # numero_acoes = 1.000 no `_indicadores()` padrão.
    assert com_ajuste == pytest.approx(sem_ajuste - 5_000.0 / 1_000.0)


def test_calcular_linha_ticker_usa_o_patrimonio_total_nos_pesos_do_wacc(
    ambiente_feliz, tmp_path, monkeypatch
):
    # `_indicadores()` padrão: razão dívida/patrimônio de 0,3 e dívida líquida None; com
    # dívida líquida e patrimônio total, a razão usada passa a ser a da leitura.
    monkeypatch.setattr(
        screener, "obter_indicadores", lambda ticker, **kw: _indicadores(divida_liquida=200.0)
    )
    sem_patrimonio_total = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]
    monkeypatch.setattr(
        screener,
        "obter_leitura_balanco",
        lambda *a, **kw: _leitura_balanco(patrimonio_liquido_total=10_000.0),
    )

    com_patrimonio_total = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]

    assert com_patrimonio_total != pytest.approx(sem_patrimonio_total)


def test_calcular_linha_ticker_soma_o_arrendamento_fora_da_divida_a_divida_liquida(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener, "obter_indicadores", lambda ticker, **kw: _indicadores(divida_liquida=200.0)
    )
    sem_arrendamento = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]
    monkeypatch.setattr(
        screener,
        "obter_leitura_balanco",
        lambda *a, **kw: _leitura_balanco(arrendamento_fora_da_divida=4_000.0),
    )

    com_arrendamento = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]

    # numero_acoes = 1.000 no `_indicadores()` padrão.
    assert com_arrendamento == pytest.approx(sem_arrendamento - 4_000.0 / 1_000.0)


def test_calcular_linha_ticker_usa_as_acoes_em_circulacao_no_fcd_e_no_graham(
    ambiente_feliz, tmp_path, monkeypatch
):
    sem_leitura = _linha_ticker("AAAA4", tmp_path)
    monkeypatch.setattr(
        screener,
        "obter_leitura_balanco",
        lambda *a, **kw: _leitura_balanco(acoes_em_circulacao=800.0),  # Fundamentus: 1.000
    )

    com_circulacao = _linha_ticker("AAAA4", tmp_path)

    # Mesmo valor do acionista dividido por 800 em vez de 1.000 ações; o Graham (LPA e
    # VPA do Fundamentus, reescalados) muda na mesma proporção.
    assert com_circulacao["fcd_valor_justo"] == pytest.approx(
        sem_leitura["fcd_valor_justo"] * 1000 / 800
    )
    assert com_circulacao["graham_valor_justo"] == pytest.approx(
        sem_leitura["graham_valor_justo"] * 1000 / 800
    )


def test_calcular_linha_ticker_com_acoes_descartadas_mantem_o_numero_do_fundamentus(
    ambiente_feliz, tmp_path, monkeypatch
):
    sem_leitura = _linha_ticker("AAAA4", tmp_path)
    monkeypatch.setattr(
        screener,
        "obter_leitura_balanco",
        lambda *a, **kw: _leitura_balanco(
            acoes_em_circulacao=None, motivo_acoes="Tesouraria de 53% do capital."
        ),
    )

    linha = _linha_ticker("AAAA4", tmp_path)

    assert linha["fcd_valor_justo"] == pytest.approx(sem_leitura["fcd_valor_justo"])
    assert linha["graham_valor_justo"] == pytest.approx(sem_leitura["graham_valor_justo"])


def test_calcular_linha_ticker_passa_data_base_e_acoes_do_fundamentus_para_a_leitura(
    ambiente_feliz, tmp_path, monkeypatch
):
    chamadas = []

    def leitura(cnpj, data_base, acoes, acoes_por_cotacao, **kw):
        chamadas.append((cnpj, data_base, acoes, acoes_por_cotacao))
        return _leitura_balanco()

    monkeypatch.setattr(screener, "obter_leitura_balanco", leitura)

    _linha_ticker("AAAA4", tmp_path)

    assert chamadas == [("CNPJ-AAAA4", "2026-06-30", 1000.0, 1)]


def test_calcular_linha_ticker_falha_de_rede_no_balanco_mantem_o_fcd_e_conta_falha_da_cvm(
    ambiente_feliz, tmp_path, monkeypatch
):
    sem_ajuste = _linha_ticker("AAAA4", tmp_path)["fcd_valor_justo"]

    def leitura_com_falha(*args, **kwargs):
        raise requests.ConnectionError("CVM fora do ar")

    monkeypatch.setattr(screener, "obter_leitura_balanco", leitura_com_falha)
    falhas = screener.FalhasDeFonte()

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
        falhas_de_fonte=falhas,
    )

    assert linha["fcd_valor_justo"] == pytest.approx(sem_ajuste)
    assert falhas.por_ticker() == {"AAAA4": ["CVM"]}


def test_calcular_linha_ticker_sem_cnpj_nao_le_o_balanco(ambiente_feliz, tmp_path, monkeypatch):
    def leitura(*args, **kwargs):
        raise AssertionError("não devia ler o balanço sem CNPJ")

    monkeypatch.setattr(screener, "obter_leitura_balanco", leitura)
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        lambda ticker, catalogo: (_ for _ in ()).throw(screener.EmissorNaoEncontrado(ticker)),
    )

    linha = _linha_ticker("AAAA4", tmp_path)

    assert linha["fcd_valor_justo"] is None


def test_calcular_linha_ticker_itausa_fica_sem_fcd_e_com_os_demais_metodos(
    ambiente_feliz, tmp_path
):
    linha = _linha_ticker("ITSA4", tmp_path)

    assert linha["fcd_valor_justo"] is None
    assert "fcd" not in linha["metodos_utilizados"].split(",")
    assert linha["graham_valor_justo"] is not None


def test_calcular_linha_ticker_proporcao_reinvestimento_percentual(ambiente_feliz, tmp_path):
    # ambiente_feliz mocka cfo_atual=1.200.000, cfi_atual=-200.000 ->
    # 200.000/1.200.000 = 16,67% reinvestido.
    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["fcd_valor_justo"] is not None
    assert linha["proporcao_reinvestimento_percentual"] == pytest.approx(200_000 / 1_200_000 * 100)


def test_calcular_linha_ticker_proporcao_reinvestimento_nula_quando_fcd_nao_aplicavel(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Banco -> FCD não aplicável (config.SEGMENTOS_FCD_NAO_APLICAVEL) — a
    # proporção reinvestida não deve aparecer pra uma linha cujo FCD nem
    # foi usado, mesmo que o dado de CFO/CFI tenha sido buscado.
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        lambda ticker, catalogo: {"cnpj": f"CNPJ-{ticker}", "segmento_setorial": "Bancos"},
    )

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["fcd_valor_justo"] is None
    assert linha["proporcao_reinvestimento_percentual"] is None


def test_rodar_screener_data_balanco_fundamentus_fica_nula_quando_fundamentus_falha(
    ambiente_feliz, tmp_path, monkeypatch
):
    from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado

    def indicadores_falha(ticker, **kwargs):
        raise TickerNaoEncontrado("simulado")

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_falha)

    resultado = screener.rodar_screener(
        tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
    )

    assert resultado.iloc[0]["data_balanco_fundamentus"] is None


def test_rodar_screener_ano_referencia_fcd_fica_nulo_quando_fcd_nao_aplicavel(
    ambiente_feliz, tmp_path, monkeypatch
):
    # FCD "não aplicável" por segmento (ver config.SEGMENTOS_FCD_NAO_
    # APLICAVEL) não deve deixar um ano "órfão" na coluna nova — mesmo
    # padrão de fcd_valor_justo, que já fica None nesse caso.
    monkeypatch.setattr(
        screener,
        "resolver_cnpj",
        lambda ticker, catalogo: {"cnpj": f"CNPJ-{ticker}", "segmento_setorial": "Bancos"},
    )

    resultado = screener.rodar_screener(
        tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
    )

    linha = resultado.iloc[0]
    assert linha["fcd_valor_justo"] is None
    assert linha["ano_referencia_fcd"] is None


def test_rodar_screener_avisa_globalmente_quando_deteccao_do_ano_falha(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Falha na detecção é GLOBAL (afeta o FCD de todas as ações da rodada,
    # não uma linha específica) — por isso o sinal é um aviso da rodada
    # inteira, não uma coluna por ticker. Sem isso, a causa ficava
    # completamente silenciosa: cada linha só mostrava fcd_valor_justo
    # vazio, indistinguível de "essa empresa não tem FCD na CVM".
    def resolver_falso(**kw):
        raise RuntimeError("CVM fora do ar (simulado)")

    monkeypatch.setattr(screener, "resolver_ano_mais_recente_disponivel", resolver_falso)

    with pytest.warns(screener.DeteccaoAnoCvmFalhouWarning, match="Detecção do ano mais recente"):
        resultado = screener.rodar_screener(
            tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
        )

    linha = resultado.iloc[0]
    assert linha["fcd_valor_justo"] is None
    assert linha["ano_referencia_fcd"] is None
    # Nada derrubou a rodada -- o resto da linha continua calculado.
    assert linha["sucesso"]
    assert linha["graham_valor_justo"] is not None


def test_rodar_screener_avisa_globalmente_quando_bcb_falha(ambiente_feliz, tmp_path, monkeypatch):
    # P07 (docs/auditoria-tecnica-2026-09-27.md): antes desta correção,
    # a falha do BCB era engolida em silêncio (except Exception: selic_
    # meta = ipca_12m = None, sem warnings.warn nenhum) — mesmo problema
    # que a detecção do ano da CVM já tinha, corrigido acima com o
    # mesmo padrão de aviso global.
    def buscar_macro_falso(diretorio_cache):
        raise RuntimeError("BCB fora do ar (simulado)")

    monkeypatch.setattr(screener, "_buscar_macro", buscar_macro_falso)

    with pytest.warns(screener.MacroIndisponivelWarning, match="Selic/IPCA indisponíveis"):
        resultado = screener.rodar_screener(
            tickers=["AAAA4"], diretorio_cache=tmp_path, caminho_saida=tmp_path / "screener.csv"
        )

    linha = resultado.iloc[0]
    assert linha["fcd_valor_justo"] is None
    # Nada derrubou a rodada -- o resto da linha continua calculado.
    assert linha["sucesso"]
    assert linha["graham_valor_justo"] is not None


def test_buscar_macro_avisa_quando_usa_valor_guardado(tmp_path, monkeypatch):
    # BCB fora do ar mas com valor guardado recente o bastante (ver
    # ingest.bcb_sgs.obter_selic_e_ipca) — o screener não pode usar o
    # valor sem avisar, mesmo mecanismo de aviso global já usado pra
    # falha total.
    resultado_guardado = bcb_sgs.ResultadoMacro(
        selic_meta=0.1375,
        ipca_12m=0.045,
        data_ipca=pd.Timestamp("2026-08-01"),
        usou_valor_guardado=True,
        data_busca=pd.Timestamp("2026-09-20"),
    )
    monkeypatch.setattr(
        screener, "obter_selic_e_ipca", lambda diretorio_cache: resultado_guardado
    )

    with pytest.warns(screener.MacroIndisponivelWarning, match="Banco Central indisponível agora"):
        macro = screener._buscar_macro(tmp_path)

    assert macro.selic_meta == pytest.approx(0.1375)
    assert macro.ipca_12m == pytest.approx(0.045)


def test_calcular_linha_ticker_erro_deteccao_ano_fcd_nao_derruba_o_calculo(
    ambiente_feliz, tmp_path
):
    # calcular_valor_combinado sempre usa sua PRÓPRIA mensagem genérica
    # quando nada é aplicável ("Nenhum dos três métodos...") — o motivo
    # específico do FCD nunca vaza pra "erro" da linha, mesmo aqui. Por
    # isso o sinal de verdade pra essa falha é o aviso global em
    # rodar_screener (ver teste acima), não esta coluna; este teste só
    # garante que passar erro_deteccao_ano_fcd não quebra o cálculo em
    # si (fica "não aplicável" graciosamente, como qualquer outra causa).
    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=None,
        erro_deteccao_ano_fcd="CVM fora do ar (simulado)",
        diretorio_cache=tmp_path,
    )

    assert linha["sucesso"] is True
    assert linha["fcd_valor_justo"] is None
    assert linha["ano_referencia_fcd"] is None
    # Graham continua aplicável normalmente — a falha de detecção do ano
    # não derruba os outros métodos.
    assert linha["graham_valor_justo"] is not None


def test_rodar_screener_grava_incrementalmente_no_csv(ambiente_feliz, tmp_path):
    caminho_saida = tmp_path / "screener.csv"

    screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"], diretorio_cache=tmp_path, caminho_saida=caminho_saida
    )

    linhas_no_arquivo = caminho_saida.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas_no_arquivo) == 3  # cabeçalho + 2 ações


def test_rodar_screener_isola_erro_de_preco_de_uma_acao_e_continua_as_demais(
    ambiente_feliz, tmp_path, monkeypatch
):
    def historico_com_falha(ticker, periodo, diretorio_cache=None):
        if ticker == "BBBB4":
            raise TickerInvalido("ticker de teste inválido")
        return _historico([38.0, 39.0, 39.5, 40.5, 40.0])

    monkeypatch.setattr(screener, "obter_historico", historico_com_falha)

    resultado = screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    assert len(resultado) == 2
    linha_ok = resultado[resultado["ticker"] == "AAAA4"].iloc[0]
    linha_falha = resultado[resultado["ticker"] == "BBBB4"].iloc[0]

    assert linha_ok["sucesso"]
    assert not linha_falha["sucesso"]
    assert "Preço" in linha_falha["erro"]
    assert "ticker de teste inválido" in linha_falha["erro"]


@pytest.mark.parametrize("preco_invalido", [float("nan"), 0.0, -5.0])
def test_rodar_screener_preco_atual_invalido_vira_linha_de_erro_sem_potencial(
    ambiente_feliz, tmp_path, monkeypatch, preco_invalido
):
    def historico_com_preco_invalido(ticker, periodo, diretorio_cache=None):
        if ticker == "BBBB4":
            return _historico([38.0, 39.0, 39.5, 40.5, preco_invalido])
        return _historico([38.0, 39.0, 39.5, 40.5, 40.0])

    monkeypatch.setattr(screener, "obter_historico", historico_com_preco_invalido)

    resultado = screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    linha_ok = resultado[resultado["ticker"] == "AAAA4"].iloc[0]
    linha_ruim = resultado[resultado["ticker"] == "BBBB4"].iloc[0]
    assert linha_ok["sucesso"]
    assert not linha_ruim["sucesso"]
    assert linha_ruim["erro"] == MENSAGEM_PRECO_INDISPONIVEL_SCREENER
    assert pd.isna(linha_ruim["desconto_percentual"])
    assert pd.isna(linha_ruim["valor_combinado"])


# --- Checagem da rodada antes de substituir o screener.csv ---------------------

CONTEUDO_ANTIGO = "ticker\nANTIGO\n"


def _rodar_com_oficial_antigo(tmp_path, tickers=("AAAA4", "BBBB4")):
    oficial = tmp_path / "screener.csv"
    oficial.write_text(CONTEUDO_ANTIGO, encoding="utf-8")
    resultado = screener.rodar_screener(
        tickers=list(tickers), diretorio_cache=tmp_path, caminho_saida=oficial
    )
    return oficial, resultado


def _sem_preco_no_bbbb4(monkeypatch):
    def historico(ticker, periodo, diretorio_cache=None):
        ultimo = float("nan") if ticker == "BBBB4" else 40.0
        return _historico([38.0, 39.0, 39.5, 40.5, ultimo])

    monkeypatch.setattr(screener, "obter_historico", historico)


def _fundamentus_fora_do_ar(monkeypatch, tickers_afetados=None):
    def indicadores(ticker, **kwargs):
        if tickers_afetados is not None and ticker not in tickers_afetados:
            return _indicadores()
        resposta = type("RespostaFalsa", (), {"status_code": 503})()
        raise requests.HTTPError("503 Server Error", response=resposta)

    monkeypatch.setattr(screener, "obter_indicadores", indicadores)


def test_rodada_boa_substitui_o_oficial_sem_deixar_arquivo_novo(ambiente_feliz, tmp_path):
    oficial, resultado = _rodar_com_oficial_antigo(tmp_path)

    assert list(pd.read_csv(oficial)["ticker"]) == ["AAAA4", "BBBB4"]
    assert not (tmp_path / "screener.csv.novo").exists()
    assert not (tmp_path / "screener.rejeitado.csv").exists()
    assert resultado.attrs["falhas_de_fonte"] == {}


def test_rodada_com_mais_acoes_sem_preco_que_o_limite_e_rejeitada(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(screener, "LIMITE_ACOES_SEM_PRECO_SCREENER", 0)
    _sem_preco_no_bbbb4(monkeypatch)

    with pytest.raises(screener.RodadaScreenerRejeitada, match="1 ações sem preço") as excecao:
        _rodar_com_oficial_antigo(tmp_path)

    assert (tmp_path / "screener.csv").read_text(encoding="utf-8") == CONTEUDO_ANTIGO
    assert excecao.value.caminho_rejeitado == tmp_path / "screener.rejeitado.csv"
    assert list(pd.read_csv(excecao.value.caminho_rejeitado)["ticker"]) == ["AAAA4", "BBBB4"]
    assert not (tmp_path / "screener.csv.novo").exists()


def test_rodada_aceita_grava_a_selic_e_o_ipca_no_arquivo_de_referencia(ambiente_feliz, tmp_path):
    _rodar_com_oficial_antigo(tmp_path)

    gravado = json.loads((tmp_path / "macro_referencia.json").read_text(encoding="utf-8"))
    assert gravado["selic_meta"] == pytest.approx(0.10)
    assert gravado["ipca_12m"] == pytest.approx(0.04)
    assert gravado["data_ipca"] == "2026-08-01"
    assert gravado["data_busca"].startswith("2026-10-03")
    assert (gravado["fonte_selic"], gravado["fonte_ipca"]) == ("BCB (SOAP)", "IBGE (SIDRA)")


def test_rodada_rejeitada_nao_grava_o_arquivo_de_referencia(ambiente_feliz, tmp_path, monkeypatch):
    monkeypatch.setattr(screener, "LIMITE_ACOES_SEM_PRECO_SCREENER", 0)
    _sem_preco_no_bbbb4(monkeypatch)

    with pytest.raises(screener.RodadaScreenerRejeitada):
        _rodar_com_oficial_antigo(tmp_path)

    assert not (tmp_path / "macro_referencia.json").exists()


def test_rodada_que_usou_valor_guardado_nao_regrava_o_arquivo_de_referencia(
    ambiente_feliz, tmp_path, monkeypatch
):
    guardado = dataclasses.replace(MACRO_AO_VIVO, usou_valor_guardado=True)
    monkeypatch.setattr(screener, "_buscar_macro", lambda diretorio_cache: guardado)

    _rodar_com_oficial_antigo(tmp_path)

    assert not (tmp_path / "macro_referencia.json").exists()


def test_rodada_com_acoes_sem_preco_no_limite_e_aceita(ambiente_feliz, tmp_path, monkeypatch):
    monkeypatch.setattr(screener, "LIMITE_ACOES_SEM_PRECO_SCREENER", 1)
    monkeypatch.setattr(screener, "LIMITE_ACOES_COM_FALHA_SCREENER", 1)
    _sem_preco_no_bbbb4(monkeypatch)

    oficial, _ = _rodar_com_oficial_antigo(tmp_path)

    assert list(pd.read_csv(oficial)["ticker"]) == ["AAAA4", "BBBB4"]


def test_rejeicao_sobrescreve_o_arquivo_rejeitado_anterior(ambiente_feliz, tmp_path, monkeypatch):
    monkeypatch.setattr(screener, "LIMITE_ACOES_SEM_PRECO_SCREENER", 0)
    _sem_preco_no_bbbb4(monkeypatch)
    (tmp_path / "screener.rejeitado.csv").write_text("velho\n", encoding="utf-8")

    with pytest.raises(screener.RodadaScreenerRejeitada):
        _rodar_com_oficial_antigo(tmp_path)

    assert "AAAA4" in (tmp_path / "screener.rejeitado.csv").read_text(encoding="utf-8")


def test_excecao_no_meio_da_rodada_apaga_o_arquivo_novo_e_preserva_o_oficial(
    ambiente_feliz, tmp_path, monkeypatch
):
    def indicadores(ticker, **kwargs):
        if ticker == "BBBB4":
            raise KeyboardInterrupt
        return _indicadores()

    monkeypatch.setattr(screener, "obter_indicadores", indicadores)

    with pytest.raises(KeyboardInterrupt):
        _rodar_com_oficial_antigo(tmp_path)

    assert (tmp_path / "screener.csv").read_text(encoding="utf-8") == CONTEUDO_ANTIGO
    assert not (tmp_path / "screener.csv.novo").exists()
    assert not (tmp_path / "screener.rejeitado.csv").exists()


def test_rodada_com_falhas_de_fundamentus_acima_do_limite_e_rejeitada(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(screener, "LIMITE_ACOES_COM_FALHA_SCREENER", 1)
    _fundamentus_fora_do_ar(monkeypatch)

    with pytest.raises(screener.RodadaScreenerRejeitada) as excecao:
        _rodar_com_oficial_antigo(tmp_path)

    assert "2 ações com falha de fonte (limite: 1)" in excecao.value.motivo
    assert "Fundamentus: 2, CVM: 0, Yahoo: 0" in excecao.value.motivo
    assert (tmp_path / "screener.csv").read_text(encoding="utf-8") == CONTEUDO_ANTIGO


def test_acoes_sem_nenhum_metodo_aplicavel_nao_contam_como_falha_de_fonte(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Graham sem lucro, Bazin sem dividendos e FCD com fluxo negativo: a linha
    # fica com "nenhum método aplicável", mas nenhuma fonte falhou.
    monkeypatch.setattr(screener, "LIMITE_ACOES_COM_FALHA_SCREENER", 0)
    monkeypatch.setattr(screener, "obter_indicadores", lambda ticker, **kw: _indicadores(lpa=-1.0))
    monkeypatch.setattr(
        screener,
        "obter_fluxo_caixa_livre_com_fallback",
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: _resultado_fcf_cvm(
            ano_mais_recente, cfo=-100_000.0, capex=200_000.0
        ),
    )

    oficial, resultado = _rodar_com_oficial_antigo(tmp_path)

    assert resultado["erro"].str.startswith("Nenhum dos três métodos").all()
    assert resultado["sucesso"].all()
    assert resultado.attrs["falhas_de_fonte"] == {}
    assert list(pd.read_csv(oficial)["ticker"]) == ["AAAA4", "BBBB4"]


def test_bcb_fora_do_ar_com_valor_guardado_nao_conta_como_falha_de_fonte(
    ambiente_feliz, tmp_path, monkeypatch
):
    # Mesmo caso da rodada de 03/10/2026: o BCB falhou, mas há Selic/IPCA guardados.
    monkeypatch.setattr(screener, "_buscar_macro", _BUSCAR_MACRO_REAL)
    monkeypatch.setattr(screener, "LIMITE_ACOES_COM_FALHA_SCREENER", 0)
    monkeypatch.setattr(
        screener,
        "obter_selic_e_ipca",
        lambda diretorio_cache: bcb_sgs.ResultadoMacro(
            selic_meta=0.1375,
            ipca_12m=0.0422,
            data_ipca=pd.Timestamp("2026-08-01"),
            usou_valor_guardado=True,
            data_busca=pd.Timestamp("2026-09-29"),
        ),
    )

    with pytest.warns(screener.MacroIndisponivelWarning, match="usando a Selic e o IPCA"):
        oficial, resultado = _rodar_com_oficial_antigo(tmp_path)

    assert resultado.attrs["falhas_de_fonte"] == {}
    assert resultado["fcd_valor_justo"].notna().all()
    assert list(pd.read_csv(oficial)["ticker"]) == ["AAAA4", "BBBB4"]


def test_bcb_fora_do_ar_sem_valor_guardado_conta_como_falha_e_rejeita_a_rodada(
    ambiente_feliz, tmp_path, monkeypatch
):
    def sem_valor_guardado(diretorio_cache):
        raise RuntimeError("BCB fora do ar e sem valor guardado")

    monkeypatch.setattr(screener, "_buscar_macro", _BUSCAR_MACRO_REAL)
    monkeypatch.setattr(screener, "obter_selic_e_ipca", sem_valor_guardado)
    monkeypatch.setattr(screener, "LIMITE_ACOES_COM_FALHA_SCREENER", 1)

    with (
        pytest.warns(screener.MacroIndisponivelWarning, match="Selic/IPCA indisponíveis"),
        pytest.raises(screener.RodadaScreenerRejeitada) as excecao,
    ):
        _rodar_com_oficial_antigo(tmp_path)

    assert "Banco Central: 2" in excecao.value.motivo
    assert (tmp_path / "screener.csv").read_text(encoding="utf-8") == CONTEUDO_ANTIGO


def test_ticker_que_o_fundamentus_nao_encontra_nao_conta_como_falha_de_fonte(
    ambiente_feliz, tmp_path, monkeypatch
):
    def indicadores(ticker, **kwargs):
        raise screener.TickerNaoEncontrado("não encontrado")

    monkeypatch.setattr(screener, "obter_indicadores", indicadores)

    _, resultado = _rodar_com_oficial_antigo(tmp_path)

    assert resultado.attrs["falhas_de_fonte"] == {}


def test_duas_rodadas_seguidas_nao_compartilham_falhas_de_fonte(
    ambiente_feliz, tmp_path, monkeypatch
):
    _fundamentus_fora_do_ar(monkeypatch, tickers_afetados={"AAAA4"})
    _, primeira = _rodar_com_oficial_antigo(tmp_path)
    monkeypatch.setattr(screener, "obter_indicadores", lambda ticker, **kw: _indicadores())

    _, segunda = _rodar_com_oficial_antigo(tmp_path)

    assert primeira.attrs["falhas_de_fonte"] == {"AAAA4": ["Fundamentus"]}
    assert segunda.attrs["falhas_de_fonte"] == {}


def test_falhas_de_fonte_registram_a_fonte_de_cada_acao(ambiente_feliz, tmp_path, monkeypatch):
    def dividendos(ticker, **kwargs):
        if ticker == "BBBB4":
            raise TickerInvalido("sem dividendos")
        return _dividendos_vazio()

    def cvm_fora_do_ar(cnpj, ano_mais_recente, anos_historico_crescimento, **kw):
        if cnpj == "CNPJ-AAAA4":
            raise requests.ConnectionError("CVM fora do ar")
        return _resultado_fcf_cvm(ano_mais_recente)

    monkeypatch.setattr(screener, "obter_dividendos", dividendos)
    monkeypatch.setattr(screener, "obter_fluxo_caixa_livre_com_fallback", cvm_fora_do_ar)

    _, resultado = _rodar_com_oficial_antigo(tmp_path)

    assert resultado.attrs["falhas_de_fonte"] == {"AAAA4": ["CVM"], "BBBB4": ["Yahoo"]}


def test_coletor_de_falhas_conta_cada_acao_uma_vez_e_separa_por_fonte():
    falhas = screener.FalhasDeFonte()

    falhas.registrar("AAAA4", "Fundamentus")
    falhas.registrar("AAAA4", "Fundamentus")
    falhas.registrar("AAAA4", "CVM")
    falhas.registrar("BBBB4", "Fundamentus")

    assert falhas.total() == 2
    assert falhas.contagem_por_fonte() == {
        "Fundamentus": 2,
        "CVM": 1,
        "Yahoo": 0,
        "Banco Central": 0,
    }
    assert falhas.por_ticker() == {"AAAA4": ["Fundamentus", "CVM"], "BBBB4": ["Fundamentus"]}


def test_rodar_screener_trata_excecao_inesperada_sem_derrubar_as_demais(
    ambiente_feliz, tmp_path, monkeypatch
):
    def indicadores_com_bug(ticker, **kwargs):
        if ticker == "BBBB4":
            raise RuntimeError("bug inesperado, não um dos erros tratados")
        return _indicadores()

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_com_bug)

    resultado = screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    assert len(resultado) == 2
    linha_ok = resultado[resultado["ticker"] == "AAAA4"].iloc[0]
    linha_falha = resultado[resultado["ticker"] == "BBBB4"].iloc[0]

    assert linha_ok["sucesso"]
    assert not linha_falha["sucesso"]
    assert "Erro inesperado" in linha_falha["erro"]
    assert "bug inesperado" in linha_falha["erro"]


def test_rodar_screener_ordena_por_desconto_percentual_decrescente(ambiente_feliz, tmp_path):
    # AAAA4 mais barata (mesmos fundamentos, preço menor) -> potencial maior
    # -> deve vir primeiro na tabela ordenada.
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 30.0
    ambiente_feliz["precos_por_ticker"]["BBBB4"] = 45.0

    resultado = screener.rodar_screener(
        tickers=["BBBB4", "AAAA4"],  # ordem de entrada proposital ao contrário
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    assert list(resultado["ticker"]) == ["AAAA4", "BBBB4"]
    assert resultado.iloc[0]["desconto_percentual"] > resultado.iloc[1]["desconto_percentual"]


def test_rodar_screener_arquivo_em_disco_fica_ordenado_por_desconto(ambiente_feliz, tmp_path):
    # Regressão: a escrita incremental (uma linha por ação, durante o
    # processamento) grava na ordem de `tickers` — proposital aqui, ao
    # contrário da ordem por potencial — não na ordem final por potencial.
    # Só o retorno em memória era ordenado; o arquivo em disco nunca era
    # reescrito depois do sort, então ficava preso na ordem de
    # processamento. Este teste lê o ARQUIVO, não `resultado`.
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 30.0
    ambiente_feliz["precos_por_ticker"]["BBBB4"] = 45.0
    caminho_saida = tmp_path / "screener.csv"

    screener.rodar_screener(
        tickers=["BBBB4", "AAAA4"],  # ordem de entrada proposital ao contrário
        diretorio_cache=tmp_path,
        caminho_saida=caminho_saida,
    )

    tabela_em_disco = pd.read_csv(caminho_saida)
    assert list(tabela_em_disco["ticker"]) == ["AAAA4", "BBBB4"]
    assert (
        tabela_em_disco.iloc[0]["desconto_percentual"]
        > tabela_em_disco.iloc[1]["desconto_percentual"]
    )


def test_rodar_screener_erros_ficam_no_fim_da_ordenacao(ambiente_feliz, tmp_path, monkeypatch):
    def historico_com_falha(ticker, periodo, diretorio_cache=None):
        if ticker == "BBBB4":
            raise TickerInvalido("sem dado")
        return _historico([38.0, 39.0, 39.5, 40.5, 40.0])

    monkeypatch.setattr(screener, "obter_historico", historico_com_falha)

    resultado = screener.rodar_screener(
        tickers=["BBBB4", "AAAA4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    assert list(resultado["ticker"]) == ["AAAA4", "BBBB4"]
    assert resultado.iloc[-1]["sucesso"] == False  # noqa: E712 (numpy.bool_, "is False" não vale)


def test_calcular_linha_ticker_degrada_graciosamente_quando_fundamentus_falha(
    ambiente_feliz, tmp_path, monkeypatch
):
    from avaliador_b3.ingest.fundamentus import TickerNaoEncontrado

    def indicadores_falha(ticker, **kwargs):
        raise TickerNaoEncontrado("não encontrado no Fundamentus")

    monkeypatch.setattr(screener, "obter_indicadores", indicadores_falha)

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    # Sem Fundamentus, Graham fica não aplicável (sem LPA/VPA) — mas o
    # resto do pipeline (FCD, que só precisa de número de ações do
    # Fundamentus pro denominador) ainda é tentado; aqui numero_acoes
    # também falta, então só resta o resultado combinado sem métodos.
    assert linha["sucesso"] is True
    assert linha["graham_valor_justo"] is None
    assert linha["metodos_utilizados"] == ""


@pytest.mark.parametrize(
    "desconto",
    [
        None,
        0.0,
        150.0,
        -90.0,
        200.0,  # limiar exato -> não sinaliza (checagem é estrita)
        -100.0,  # limiar exato -> não sinaliza (checagem é estrita)
    ],
)
def test_aviso_desconto_extremo_dentro_do_limiar_fica_vazio(desconto):
    # metodos_utilizados não importa aqui — dentro do limiar, nenhuma
    # combinação de sinal/FCD deveria disparar aviso nenhum.
    assert screener._aviso_desconto_extremo(desconto, ["graham", "fcd"]) == ""


def test_aviso_desconto_extremo_positivo_com_fcd():
    # Caso real da validação: CSNA3 (FCD entre os métodos).
    aviso = screener._aviso_desconto_extremo(1730.6, ["graham", "fcd"])
    assert aviso == screener.AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD


def test_aviso_desconto_extremo_positivo_sem_fcd():
    # Achado real que motivou a correção: COGN3 dispara o limiar positivo
    # só com Graham, sem FCD entre os métodos — o texto não pode culpar
    # a CAGR do FCD nesse caso.
    aviso = screener._aviso_desconto_extremo(225.68, ["graham"])
    assert aviso == screener.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD


def test_aviso_desconto_extremo_negativo_com_fcd():
    # Caso real da validação: AURE3 (só FCD, que é o único método capaz
    # de produzir valor combinado negativo).
    aviso = screener._aviso_desconto_extremo(-405.6, ["fcd"])
    assert aviso == screener.AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD


def test_aviso_desconto_extremo_negativo_sem_fcd_usa_texto_generico():
    # Combinação hoje INALCANÇÁVEL na prática (Graham é raiz quadrada,
    # Bazin só fica aplicável com dividendo positivo — nenhum dos dois
    # produz valor combinado negativo sem o FCD) — mas a função não pode
    # quebrar nem inventar uma causa específica se isso um dia acontecer
    # (ex: um dos dois modelos mudar). Cai no texto de reserva genérico,
    # ver AVISO_DESCONTO_EXTREMO_GENERICO em config.py.
    aviso = screener._aviso_desconto_extremo(-150.0, ["graham"])
    assert aviso == screener.AVISO_DESCONTO_EXTREMO_GENERICO


def test_calcular_linha_ticker_sinaliza_desconto_extremo_positivo(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener,
        "calcular_valor_combinado",
        lambda *a, **k: {
            "aplicavel": True,
            "valor_combinado": 100.0,
            "metodos_utilizados": ["graham"],
            "valores_por_metodo": {"graham": 100.0},
            "motivo_nao_aplicavel": None,
        },
    )
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 10.0  # potencial = 900%

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["desconto_percentual"] == pytest.approx(900.0)
    assert linha["aviso_desconto_extremo"] == screener.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD


def test_calcular_linha_ticker_sinaliza_desconto_extremo_negativo(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener,
        "calcular_valor_combinado",
        lambda *a, **k: {
            "aplicavel": True,
            "valor_combinado": -20.0,  # valor combinado negativo -> potencial < -100%
            "metodos_utilizados": ["fcd"],
            "valores_por_metodo": {"fcd": -20.0},
            "motivo_nao_aplicavel": None,
        },
    )
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 10.0  # potencial = (-20-10)/10*100 = -300%

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["desconto_percentual"] == pytest.approx(-300.0)
    assert linha["aviso_desconto_extremo"] == screener.AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD


def test_calcular_linha_ticker_nao_sinaliza_desconto_normal(ambiente_feliz, tmp_path, monkeypatch):
    monkeypatch.setattr(
        screener,
        "calcular_valor_combinado",
        lambda *a, **k: {
            "aplicavel": True,
            "valor_combinado": 55.0,
            "metodos_utilizados": ["graham", "fcd"],
            "valores_por_metodo": {"graham": 50.0, "fcd": 60.0},
            "motivo_nao_aplicavel": None,
        },
    )
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 40.0  # potencial = (55-40)/40*100 = 37,5%

    linha = screener._calcular_linha_ticker(
        "AAAA4",
        catalogo_emissores=pd.DataFrame(),
        historico_ibovespa_beta=_historico([100.0, 101.0, 99.0, 102.0, 103.0]),
        selic_meta=0.10,
        ipca_12m=0.04,
        ano_mais_recente_fcd=ANO_FCD_MOCK,
        erro_deteccao_ano_fcd=None,
        diretorio_cache=tmp_path,
    )

    assert linha["desconto_percentual"] == pytest.approx(37.5)
    assert linha["aviso_desconto_extremo"] == ""


def test_rodar_screener_sinaliza_so_a_acao_com_desconto_extremo(
    ambiente_feliz, tmp_path, monkeypatch
):
    valores_combinados = {"AAAA4": 500.0, "BBBB4": 45.0}

    def combinado_falso(resultado_graham, resultado_bazin, resultado_fcd):
        # descobre qual ticker está sendo processado através do preço já
        # embutido no resultado do FCD não é viável aqui, então usamos uma
        # fila simples: a ordem de chamada segue a ordem de `tickers`.
        ticker = combinado_falso.fila.pop(0)
        return {
            "aplicavel": True,
            "valor_combinado": valores_combinados[ticker],
            "metodos_utilizados": ["graham"],
            "valores_por_metodo": {"graham": valores_combinados[ticker]},
            "motivo_nao_aplicavel": None,
        }

    combinado_falso.fila = ["AAAA4", "BBBB4"]
    monkeypatch.setattr(screener, "calcular_valor_combinado", combinado_falso)
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 40.0  # potencial = 1150% -> extremo
    ambiente_feliz["precos_por_ticker"]["BBBB4"] = 40.0  # potencial = 12,5% -> normal

    resultado = screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    linha_extrema = resultado[resultado["ticker"] == "AAAA4"].iloc[0]
    linha_normal = resultado[resultado["ticker"] == "BBBB4"].iloc[0]

    assert (
        linha_extrema["aviso_desconto_extremo"]
        == screener.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD
    )
    assert linha_normal["aviso_desconto_extremo"] == ""
