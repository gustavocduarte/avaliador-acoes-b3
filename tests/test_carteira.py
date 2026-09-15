import pandas as pd
import pytest

from avaliador_b3 import carteira


def _linha_screener(
    ticker="AAAA4",
    preco_atual=40.0,
    valor_combinado=None,
    graham=None,
    bazin=None,
    fcd=None,
):
    return {
        "ticker": ticker,
        "preco_atual": preco_atual,
        "valor_combinado": valor_combinado,
        "graham_valor_justo": graham,
        "bazin_preco_teto": bazin,
        "fcd_valor_justo": fcd,
    }


# --- derivar_cenarios_ticker: 0, 1, 2 e 3 métodos aplicáveis -----------------


def test_derivar_cenarios_sem_nenhum_metodo_aplicavel():
    linha = _linha_screener(valor_combinado=None, graham=None, bazin=None, fcd=None)

    cenarios = carteira.derivar_cenarios_ticker(linha)

    assert cenarios["aplicavel"] is False
    assert cenarios["otimista"] is None
    assert cenarios["base"] is None
    assert cenarios["pessimista"] is None
    assert "Nenhum método" in cenarios["motivo_nao_aplicavel"]


def test_derivar_cenarios_com_um_metodo_aplicavel():
    # Só Graham aplicável: os três cenários colapsam no mesmo valor.
    linha = _linha_screener(valor_combinado=50.0, graham=50.0, bazin=None, fcd=None)

    cenarios = carteira.derivar_cenarios_ticker(linha)

    assert cenarios["aplicavel"] is True
    assert cenarios["otimista"] == pytest.approx(50.0)
    assert cenarios["base"] == pytest.approx(50.0)
    assert cenarios["pessimista"] == pytest.approx(50.0)


def test_derivar_cenarios_com_dois_metodos_aplicaveis():
    # Graham=40, FCD=60 -> combinado (base) = 50; otimista=60, pessimista=40.
    linha = _linha_screener(valor_combinado=50.0, graham=40.0, bazin=None, fcd=60.0)

    cenarios = carteira.derivar_cenarios_ticker(linha)

    assert cenarios["aplicavel"] is True
    assert cenarios["otimista"] == pytest.approx(60.0)
    assert cenarios["base"] == pytest.approx(50.0)
    assert cenarios["pessimista"] == pytest.approx(40.0)


def test_derivar_cenarios_com_tres_metodos_aplicaveis():
    # Graham=30, Bazin=45, FCD=90 -> combinado (base) = 55; otimista=90, pessimista=30.
    linha = _linha_screener(valor_combinado=55.0, graham=30.0, bazin=45.0, fcd=90.0)

    cenarios = carteira.derivar_cenarios_ticker(linha)

    assert cenarios["aplicavel"] is True
    assert cenarios["otimista"] == pytest.approx(90.0)
    assert cenarios["base"] == pytest.approx(55.0)
    assert cenarios["pessimista"] == pytest.approx(30.0)


def test_derivar_cenarios_trata_nan_do_pandas_igual_a_none():
    # Uma linha vinda de pd.read_csv tem NaN (float), não None, nas
    # colunas de método não aplicável — precisa ser tratado do mesmo jeito.
    linha = pd.Series(
        {
            "ticker": "AAAA4",
            "preco_atual": 40.0,
            "valor_combinado": 60.0,
            "graham_valor_justo": float("nan"),
            "bazin_preco_teto": float("nan"),
            "fcd_valor_justo": 60.0,
        }
    )

    cenarios = carteira.derivar_cenarios_ticker(linha)

    assert cenarios["aplicavel"] is True
    assert cenarios["otimista"] == pytest.approx(60.0)
    assert cenarios["pessimista"] == pytest.approx(60.0)


# --- simular_investimento_ticker --------------------------------------------


def test_simular_investimento_projeta_reais_e_percentual_nos_tres_cenarios():
    # preço atual 40; cenários pessimista=30, base=50, otimista=70.
    linha = _linha_screener(preco_atual=40.0, valor_combinado=50.0, graham=30.0, fcd=70.0)

    resultado = carteira.simular_investimento_ticker(linha, valor_investido=1000.0)

    assert resultado["aplicavel"] is True
    assert resultado["projecao_pessimista"] == pytest.approx(750.0)  # 1000 * 30/40
    assert resultado["projecao_base"] == pytest.approx(1250.0)  # 1000 * 50/40
    assert resultado["projecao_otimista"] == pytest.approx(1750.0)  # 1000 * 70/40
    assert resultado["retorno_pessimista_percentual"] == pytest.approx(-25.0)
    assert resultado["retorno_base_percentual"] == pytest.approx(25.0)
    assert resultado["retorno_otimista_percentual"] == pytest.approx(75.0)


def test_simular_investimento_sem_metodo_aplicavel_nao_projeta_nada():
    # Caso real do screener: HAPV3/MRVE3-like, sem nenhum método aplicável.
    linha = _linha_screener(ticker="HAPV3", preco_atual=5.0, valor_combinado=None)

    resultado = carteira.simular_investimento_ticker(linha, valor_investido=500.0)

    assert resultado["ticker"] == "HAPV3"
    assert resultado["aplicavel"] is False
    assert "Nenhum método" in resultado["motivo_nao_aplicavel"]
    assert resultado["projecao_otimista"] is None
    assert resultado["projecao_base"] is None
    assert resultado["projecao_pessimista"] is None
    assert resultado["retorno_otimista_percentual"] is None
    assert resultado["retorno_base_percentual"] is None
    assert resultado["retorno_pessimista_percentual"] is None


def test_simular_investimento_sem_preco_atual_nao_projeta_nada():
    linha = _linha_screener(preco_atual=None, valor_combinado=50.0, graham=50.0)

    resultado = carteira.simular_investimento_ticker(linha, valor_investido=500.0)

    assert resultado["aplicavel"] is False
    assert resultado["preco_atual"] is None
    assert resultado["projecao_base"] is None


# --- montar_tabela_carteira / calcular_totais_carteira ----------------------


def _tabela_screener_exemplo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # AAAA4: dois métodos aplicáveis.
            _linha_screener(
                ticker="AAAA4", preco_atual=40.0, valor_combinado=50.0, graham=40.0, fcd=60.0
            ),
            # BBBB4: três métodos aplicáveis.
            _linha_screener(
                ticker="BBBB4",
                preco_atual=20.0,
                valor_combinado=25.0,
                graham=20.0,
                bazin=25.0,
                fcd=30.0,
            ),
            # CCCC4: nenhum método aplicável (ex: HAPV3/MRVE3 no screener real).
            _linha_screener(ticker="CCCC4", preco_atual=10.0, valor_combinado=None),
        ]
    )


def test_montar_tabela_carteira_agrega_mais_de_uma_acao_na_ordem_selecionada():
    tabela_screener = _tabela_screener_exemplo()
    investimentos = {"BBBB4": 1000.0, "AAAA4": 2000.0}  # ordem proposital diferente do CSV

    tabela_carteira = carteira.montar_tabela_carteira(tabela_screener, investimentos)

    assert list(tabela_carteira["ticker"]) == ["BBBB4", "AAAA4"]
    assert list(tabela_carteira["valor_investido"]) == [1000.0, 2000.0]
    assert tabela_carteira["aplicavel"].all()


def test_montar_tabela_carteira_inclui_acao_sem_cenario_com_aviso_explicito():
    tabela_screener = _tabela_screener_exemplo()
    investimentos = {"AAAA4": 1000.0, "CCCC4": 500.0}

    tabela_carteira = carteira.montar_tabela_carteira(tabela_screener, investimentos)

    linha_sem_cenario = tabela_carteira[tabela_carteira["ticker"] == "CCCC4"].iloc[0]
    assert linha_sem_cenario["aplicavel"] == False  # noqa: E712 (numpy.bool_, "is False" não vale)
    assert "Nenhum método" in linha_sem_cenario["motivo_nao_aplicavel"]
    # Numa tabela mista, pandas converte o None (ação sem cenário) pra NaN
    # ao juntar com as colunas float das ações aplicáveis — semântica
    # equivalente de "ausente", só a representação muda.
    assert pd.isna(linha_sem_cenario["projecao_base"])
    # não foi silenciosamente ignorada: a linha existe na tabela.
    assert len(tabela_carteira) == 2


def test_calcular_totais_soma_investido_de_todos_mas_projeta_so_os_aplicaveis():
    tabela_screener = _tabela_screener_exemplo()
    # AAAA4 (aplicável): 1000 * 50/40 = 1250 base.
    # CCCC4 (sem cenário): 500 investidos, sem projeção.
    investimentos = {"AAAA4": 1000.0, "CCCC4": 500.0}
    tabela_carteira = carteira.montar_tabela_carteira(tabela_screener, investimentos)

    totais = carteira.calcular_totais_carteira(tabela_carteira)

    assert totais["soma_investida"] == pytest.approx(1500.0)  # inclui os 500 da CCCC4
    assert totais["total_base"] == pytest.approx(1250.0)  # só a projeção da AAAA4
    assert totais["total_otimista"] == pytest.approx(1500.0)  # 1000 * 60/40
    assert totais["total_pessimista"] == pytest.approx(1000.0)  # 1000 * 40/40
    assert totais["quantidade_sem_cenario"] == 1


def test_calcular_totais_soma_projecoes_de_multiplas_acoes_aplicaveis():
    tabela_screener = _tabela_screener_exemplo()
    investimentos = {"AAAA4": 1000.0, "BBBB4": 1000.0}
    tabela_carteira = carteira.montar_tabela_carteira(tabela_screener, investimentos)

    totais = carteira.calcular_totais_carteira(tabela_carteira)

    # AAAA4 base = 1000 * 50/40 = 1250; BBBB4 base = 1000 * 25/20 = 1250.
    assert totais["soma_investida"] == pytest.approx(2000.0)
    assert totais["total_base"] == pytest.approx(2500.0)
    assert totais["quantidade_sem_cenario"] == 0
