import pandas as pd
import pytest

from avaliador_b3 import screener
from avaliador_b3.ingest.precos import TickerInvalido

# Ano fixo usado pelos mocks de FCD abaixo — substitui screener.
# ANO_REFERENCIA_FCD (removida em 2026-09-23, ver
# docs/correcao-ano-fcd-2026-09-23.md), já que o ano agora é detectado em
# tempo de execução (ingest.cvm.resolver_ano_mais_recente_disponivel), não
# uma constante.
ANO_FCD_MOCK = 2025


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
        # descontos que os testes existentes já esperavam antes da
        # correção de 2026-09-23; ver test_fcd.py pra cobertura da
        # dedução em si.
        "divida_liquida": divida_liquida,
        "data_balanco_fundamentus": data_balanco_fundamentus,
    }


def _dividendos_vazio() -> pd.DataFrame:
    # Bazin sempre "não aplicável" com histórico vazio — o caso mais
    # simples e determinístico de simular; a lógica de aplicabilidade do
    # Bazin em si já é testada em test_bazin.py, não é o foco aqui.
    return pd.DataFrame({"data": pd.to_datetime([]), "dividendo": pd.Series(dtype=float)})


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
        lambda cnpj, ano_mais_recente, anos_historico_crescimento, **kw: {
            "fcf_atual": 1_000_000.0,
            "fcf_ha_n_anos": 800_000.0,
            "ano_referencia_utilizado": ano_mais_recente,
            "ano_mais_recente_disponivel": ano_mais_recente,
            "usou_fallback": False,
        },
    )
    monkeypatch.setattr(screener, "_buscar_macro", lambda diretorio_cache: (0.10, 0.04))

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
    # AAAA4 mais barata (mesmos fundamentos, preço menor) -> desconto maior
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
    # contrário da ordem por desconto — não na ordem final por desconto.
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
    ("desconto", "esperado_aviso"),
    [
        (None, False),
        (0.0, False),
        (150.0, False),
        (-90.0, False),
        (200.0, False),  # limiar exato -> não sinaliza (checagem é estrita)
        (-100.0, False),  # limiar exato -> não sinaliza (checagem é estrita)
        (200.01, True),
        (-100.01, True),
        (1730.6, True),  # o caso real da CSNA3 na validação
        (-405.6, True),  # o caso real da AURE3 na validação
    ],
)
def test_aviso_desconto_extremo(desconto, esperado_aviso):
    aviso = screener._aviso_desconto_extremo(desconto)
    if esperado_aviso:
        assert aviso == screener.AVISO_DESCONTO_EXTREMO
    else:
        assert aviso == ""


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
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 10.0  # desconto = 900%

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
    assert linha["aviso_desconto_extremo"] == screener.AVISO_DESCONTO_EXTREMO


def test_calcular_linha_ticker_sinaliza_desconto_extremo_negativo(
    ambiente_feliz, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        screener,
        "calcular_valor_combinado",
        lambda *a, **k: {
            "aplicavel": True,
            "valor_combinado": -20.0,  # valor combinado negativo -> desconto < -100%
            "metodos_utilizados": ["fcd"],
            "valores_por_metodo": {"fcd": -20.0},
            "motivo_nao_aplicavel": None,
        },
    )
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 10.0  # desconto = (-20-10)/10*100 = -300%

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
    assert linha["aviso_desconto_extremo"] == screener.AVISO_DESCONTO_EXTREMO


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
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 40.0  # desconto = (55-40)/40*100 = 37,5%

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
    ambiente_feliz["precos_por_ticker"]["AAAA4"] = 40.0  # desconto = 1150% -> extremo
    ambiente_feliz["precos_por_ticker"]["BBBB4"] = 40.0  # desconto = 12,5% -> normal

    resultado = screener.rodar_screener(
        tickers=["AAAA4", "BBBB4"],
        diretorio_cache=tmp_path,
        caminho_saida=tmp_path / "screener.csv",
    )

    linha_extrema = resultado[resultado["ticker"] == "AAAA4"].iloc[0]
    linha_normal = resultado[resultado["ticker"] == "BBBB4"].iloc[0]

    assert linha_extrema["aviso_desconto_extremo"] == screener.AVISO_DESCONTO_EXTREMO
    assert linha_normal["aviso_desconto_extremo"] == ""
