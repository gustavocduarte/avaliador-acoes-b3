"""Tabela "Ranking por potencial" do Screener: ordem, colunas, apresentação em pt-BR pelo Styler
(números de verdade por baixo) e cor do potencial."""

import json
import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from avaliador_b3 import config
from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import (
    COLUNAS_TABELA_SCREENER,
    _configuracao_colunas_ranking,
    _largura_coluna_setor,
    _tabela_ranking_screener,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina


def _tabela(**extras) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA3", "BBB4", "CCC3", "DDD3", "EEE3"],
            "segmento_setorial": [
                "Bancos",
                "Exploração. Refino e Distribuição",
                "Bancos",
                None,
                "Bancos",
            ],
            "preco_atual": [10.0, 1234.56, 5.0, 8.0, 3.0],
            "valor_combinado": [11.0, 1000.0, None, 8.0, 6.0],
            "desconto_percentual": [10.0, -19.0, None, 0.0, 100.0],
            "erro": ["", "", "Nenhum método se aplica a esta empresa.", "", ""],
            "divergencia_percentual_metodos": [12.4, None, None, 3.0, 40.0],
            "bazin_razao_dividendos_percentual": [None, 150.0, None, None, None],
            "proporcao_reinvestimento_percentual": [20.0, None, None, None, None],
            "metodos_utilizados": ["graham,fcd", "bazin", "", "graham", "graham,bazin,fcd"],
            "aviso_desconto_extremo": ["", "", "", "", ""],
        }
        | extras
    )


def _ticker(url: str) -> str:
    """Ticker de dentro do link da coluna (`/?acao=PETR4`)."""
    return url.removeprefix("/?acao=")


def _celulas(estilo) -> list[list[str]]:
    """Valores exibidos (já formatados pelo Styler), linha a linha."""
    html = estilo.to_html()
    linhas = re.findall(r"<tr>(.*?)</tr>", html.split("<tbody>")[1], re.DOTALL)
    return [re.findall(r'class="data row\d+ col\d+ *" *>(.*?)</td>', linha) for linha in linhas]


def test_colunas_na_ordem_pedida_com_aviso_e_observacao_numa_coluna_so():
    _, colunas = _tabela_ranking_screener(_tabela())

    assert colunas == [
        "ticker",
        "segmento_setorial",
        "preco_atual",
        "valor_combinado",
        "desconto_percentual",
        "erro",
        "divergencia_percentual_metodos",
        "bazin_razao_dividendos_percentual",
        "proporcao_reinvestimento_percentual",
        "metodos_utilizados",
    ]
    assert colunas == COLUNAS_TABELA_SCREENER
    assert not {"graham_valor_justo", "bazin_preco_teto", "fcd_valor_justo"} & set(colunas)
    assert "aviso_desconto_extremo" not in colunas


def test_coluna_de_setor_so_existe_se_o_arquivo_trouxer():
    _, colunas = _tabela_ranking_screener(_tabela().drop(columns="segmento_setorial"))

    assert "segmento_setorial" not in colunas
    assert colunas[:3] == ["ticker", "preco_atual", "valor_combinado"]


def test_ordena_por_potencial_decrescente_e_deixa_as_sem_combinado_no_fim():
    estilo, _ = _tabela_ranking_screener(_tabela())

    assert [_ticker(t) for t in estilo.data["ticker"]] == ["EEE3", "AAA3", "DDD3", "BBB4", "CCC3"]


def test_mostra_os_numeros_em_pt_br_com_sinal_e_traco_para_o_que_falta():
    estilo, _ = _tabela_ranking_screener(_tabela())

    celulas = {_ticker(linha[0]): linha for linha in _celulas(estilo)}
    # ticker, setor, preço, combinado, potencial, observação, divergência, dividendos, reinvest.
    assert celulas["AAA3"][1:5] == ["Bancos", "R$ 10,00", "R$ 11,00", "+10,0%"]
    assert celulas["BBB4"][1:5] == [
        "Exploração, Refino e Distribuição",
        "R$ 1.234,56",
        "R$ 1.000,00",
        "-19,0%",
    ]
    assert celulas["CCC3"][3:5] == ["—", "—"]
    assert celulas["DDD3"][1] == "—"
    assert celulas["DDD3"][4] == "0,0%"
    assert celulas["AAA3"][6:9] == ["12%", "—", "20%"]
    assert celulas["BBB4"][8] == "—" and celulas["BBB4"][7] == "150%"
    assert celulas["AAA3"][9] == "Graham, FCD"


def test_o_potencial_leva_cor_so_quando_positivo_ou_negativo():
    estilo, _ = _tabela_ranking_screener(_tabela())

    cores = {}
    for seletores, cor in re.findall(r"([^{}]+)\{\s*color: (#\w+);", estilo.to_html()):
        for linha in re.findall(r"row(\d+)_col4", seletores):
            cores[_ticker(estilo.data["ticker"].iloc[int(linha)])] = cor
    # Ordem das linhas: EEE3, AAA3, DDD3, BBB4, CCC3; zero e vazio ficam sem cor.
    assert cores == {
        "EEE3": config.COR_POSITIVO,
        "AAA3": config.COR_POSITIVO,
        "BBB4": config.COR_NEGATIVO,
    }


def test_numeros_de_verdade_por_baixo_da_formatacao():
    estilo, _ = _tabela_ranking_screener(_tabela())

    assert pd.api.types.is_float_dtype(estilo.data["preco_atual"])
    assert pd.api.types.is_float_dtype(estilo.data["desconto_percentual"])


def test_configuracao_das_colunas_tem_rotulo_e_a_explicacao_do_potencial():
    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER)

    assert configuracao["segmento_setorial"]["label"] == "Setor"
    assert configuracao["erro"]["label"] == "Observação"
    assert configuracao["desconto_percentual"]["help"] == config.TOOLTIP_POTENCIAL_COLUNA
    assert configuracao["preco_atual"].get("help") is None


def _abrir_screener(monkeypatch, tmp_path) -> AppTest:
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
        "segmento_setorial": "Bancos",
    }
    linhas = [
        base
        | {"ticker": "BAIXO3", "preco_atual": 9.0, "valor_combinado": 5.0}
        | {"desconto_percentual": -44.4},
        base | {"ticker": "SEMM3", "preco_atual": 5.0, "erro": "Nenhum método se aplica."},
        base
        | {"ticker": "ALTO4", "preco_atual": 10.0, "valor_combinado": 20.0}
        | {"desconto_percentual": 100.0},
    ]
    caminho = tmp_path / "screener.csv"
    pd.DataFrame(linhas, columns=COLUNAS_RESULTADO).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, config.TITULO_PAGINA_SCREENER)
    assert not at.exception
    return at


def test_pagina_mostra_o_ranking_ordenado_com_as_sem_combinado_no_fim(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)
    next(c for c in at.sidebar.checkbox if c.label == "Esconder sem valor combinado").uncheck().run(
        timeout=60
    )

    tabelas = [df for df in at.dataframe if "desconto_percentual" in df.value.columns]
    assert len(tabelas) == 1
    assert [_ticker(t) for t in tabelas[0].value["ticker"]] == ["ALTO4", "BAIXO3", "SEMM3"]
    colunas = json.loads(tabelas[0].proto.columns)
    assert colunas["desconto_percentual"]["label"] == "Potencial"
    assert colunas["segmento_setorial"]["label"] == "Setor"


def test_pagina_comeca_nos_cartoes_e_deixa_o_expander_de_leitura_depois_da_tabela(
    monkeypatch, tmp_path
):
    at = _abrir_screener(monkeypatch, tmp_path)

    tipos = [elemento.type for elemento in at.main]
    antes_dos_cartoes = tipos[1 : tipos.index("flex_container")]
    assert set(antes_dos_cartoes) <= {"html", "caption"}  # só o cabeçalho do app
    assert tipos.index("expander") > tipos.index("dataframe")
    assert [c for c in at.caption if c.value.startswith("Ranking pelo potencial")] == []


def test_ticker_vira_link_para_a_analise_com_o_texto_so_do_ticker():
    estilo, _ = _tabela_ranking_screener(_tabela())
    assert list(estilo.data["ticker"])[:2] == ["/?acao=EEE3", "/?acao=AAA3"]

    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER)

    assert configuracao["ticker"]["label"] == "Ticker"
    assert configuracao["ticker"]["type_config"]["type"] == "link"
    assert configuracao["ticker"]["type_config"]["display_text"] == "acao=(.*)"


AVISO_FCD = config.AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD
RESUMO_AVISO_FCD = "Potencial extremo: confira as premissas do FCD"


TEXTO_FCD_CURTO_REAL = config.MOTIVO_FCD_DEDUCOES_SUPERAM_VALOR_CURTO.format(
    parcelas="dívida líquida, arrendamento e sócios minoritários",
    deducoes="R$ 44,3 bi",
    valor_empresa="R$ 12,6 bi",
)
TEXTO_SEM_METODO_REAL = (
    "Nenhum método se aplica a esta empresa. Graham não aplicável: Fórmula de Graham exige "
    "LPA>0 e VPA>0 (LPA = -2,25 e VPA = 1,26). Bazin não aplicável: Empresa não distribuiu "
    "dividendos em cada um dos últimos 5 anos. FCD não aplicável: O que precisa ser descontado."
)
FCD_MINIMO = "FCD não aplicável: dívidas superam o valor da empresa"


@pytest.mark.parametrize(
    ("aviso", "observacao", "esperado"),
    [
        (AVISO_FCD, "", RESUMO_AVISO_FCD),
        ("", "", ""),
        # O motivo curto do FCD (com parcelas e valores) vira a versão mínima na tabela.
        ("", TEXTO_FCD_CURTO_REAL, FCD_MINIMO),
        # Sem método: só "Nenhum método se aplica", sem a lista de motivos.
        ("", TEXTO_SEM_METODO_REAL, "Nenhum método se aplica"),
        # As duas partes juntas: só o começo de cada uma.
        (AVISO_FCD, TEXTO_FCD_CURTO_REAL, "Potencial extremo · FCD não aplicável"),
        (
            config.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
            FCD_MINIMO,
            "Potencial extremo · FCD não aplicável",
        ),
        (
            config.AVISO_DESCONTO_EXTREMO_GENERICO,
            TEXTO_SEM_METODO_REAL,
            "Potencial fora do comum · Nenhum método se aplica",
        ),
        # Mensagem livre (erro de busca) sem aviso: como veio, se couber.
        ("", "Preço indisponível agora.", "Preço indisponível agora."),
    ],
)
def test_observacao_na_forma_minima_e_junta_so_o_comeco_de_cada_parte(aviso, observacao, esperado):
    tabela = _tabela().iloc[[0]].assign(aviso_desconto_extremo=[aviso], erro=[observacao])

    estilo, _ = _tabela_ranking_screener(tabela)

    assert list(estilo.data["erro"]) == [esperado]


def test_mensagem_livre_acima_do_limite_e_cortada_com_reticencias():
    longa = (
        "Falha ao buscar o preço de AAA3 no Yahoo Finance: tempo esgotado depois de várias "
        "tentativas"
    )
    tabela = _tabela().iloc[[0]].assign(aviso_desconto_extremo=[""], erro=[longa])

    estilo, _ = _tabela_ranking_screener(tabela)

    texto = list(estilo.data["erro"])[0]
    assert len(texto) == config.LIMITE_CARACTERES_OBSERVACAO_RANKING
    assert texto.endswith("…") and longa.startswith(texto[:-1])


def test_todos_os_textos_fixos_possiveis_da_observacao_cabem_no_limite_de_caracteres():
    from avaliador_b3.app.main import _observacao_do_ranking

    avisos = [
        "",
        config.AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD,
        config.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
        config.AVISO_DESCONTO_EXTREMO_GENERICO,
    ]
    observacoes = ["", TEXTO_FCD_CURTO_REAL, TEXTO_SEM_METODO_REAL]
    limite = config.LIMITE_CARACTERES_OBSERVACAO_RANKING

    for aviso in avisos:
        for observacao in observacoes:
            texto = _observacao_do_ranking(aviso, observacao)
            assert len(texto) <= limite, texto
            assert "…" not in texto, texto  # nenhum texto fixo precisa ser cortado
    # O maior texto fixo ainda cabe com folga no limite que cabe nos 360 px da coluna.
    assert len(config.TEXTO_FCD_NAO_APLICAVEL_NA_TABELA) <= limite


def test_observacao_tem_largura_para_o_texto_curto_do_aviso_sem_corte():
    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER)

    assert configuracao["erro"]["label"] == "Observação"
    # ~7,5 px por caractere nos 14 px da tabela.
    assert configuracao["erro"]["width"] >= len(RESUMO_AVISO_FCD) * 7.5
    assert configuracao["erro"]["width"] == config.LARGURA_COLUNA_OBSERVACAO_RANKING


def test_divergencia_dividendos_e_reinvestimento_mostram_traco_no_lugar_do_vazio():
    estilo, _ = _tabela_ranking_screener(_tabela())

    celulas = {_ticker(linha[0]): linha for linha in _celulas(estilo)}
    # divergência, dividendos, reinvestimento
    assert celulas["AAA3"][6:9] == ["12%", "—", "20%"]
    assert celulas["CCC3"][6:9] == ["—", "—", "—"]
    assert "None" not in estilo.to_html()
    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER)
    for coluna in (
        "divergencia_percentual_metodos",
        "bazin_razao_dividendos_percentual",
        "proporcao_reinvestimento_percentual",
    ):
        assert estilo.data[coluna].map(lambda v: isinstance(v, str)).all()
        assert configuracao[coluna]["type_config"]["type"] == "text"
        assert configuracao[coluna]["alignment"] == "right"


def test_preco_valor_combinado_e_potencial_continuam_numericos_para_ordenar():
    estilo, _ = _tabela_ranking_screener(_tabela())

    for coluna in ("preco_atual", "valor_combinado", "desconto_percentual"):
        assert pd.api.types.is_float_dtype(estilo.data[coluna])


def test_ponto_de_interrogacao_do_titulo_ensina_a_abrir_a_analise():
    assert "Clique duas vezes no ticker para abrir a análise da ação numa nova aba." in (
        config.TEXTO_AJUDA_RANKING_SCREENER
    )


def test_formas_minimas_gravadas_pela_rodada_passam_como_estao_e_juntam_so_o_comeco():
    from avaliador_b3.app.main import _observacao_do_ranking

    formas = [v for k, v in vars(config).items() if k.startswith("FORMA_MINIMA_FCD_")]
    avisos = [
        config.AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD,
        config.AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD,
        config.AVISO_DESCONTO_EXTREMO_GENERICO,
    ]
    limite = config.LIMITE_CARACTERES_OBSERVACAO_RANKING

    for forma in formas:
        assert _observacao_do_ranking("", forma) == forma
        for aviso in avisos:
            junto = _observacao_do_ranking(aviso, forma)
            assert junto.endswith(" · FCD não aplicável"), junto
            assert len(junto) <= limite and "…" not in junto


def _tabela_com_setores(*setores) -> pd.DataFrame:
    return pd.DataFrame(
        {"ticker": [f"T{i}" for i in range(len(setores))], "segmento_setorial": setores}
    )


def test_largura_da_coluna_setor_vem_do_maior_rotulo_da_tabela_inteira():
    dado_bruto = "Serv.Méd.Hospit..Análises e Diagnósticos"
    maior = "Serviços Médico-Hospitalares, Análises e Diagnósticos"
    tabela = _tabela_com_setores("Bancos", dado_bruto, None, "Exploração. Refino e Distribuição")

    esperado = (
        len(maior) * config.LARGURA_PX_POR_CARACTERE_COLUNA_SETOR
        + config.LARGURA_MARGEM_COLUNA_SETOR
    )
    assert _largura_coluna_setor(tabela) == esperado


def test_largura_da_coluna_setor_cobre_o_rotulo_exibido_de_todo_segmento_corrigido():
    for dado, exibido in config.CORRECOES_EXIBICAO_SEGMENTO_SETORIAL.items():
        assert _largura_coluna_setor(_tabela_com_setores(dado)) == (
            len(exibido) * config.LARGURA_PX_POR_CARACTERE_COLUNA_SETOR
            + config.LARGURA_MARGEM_COLUNA_SETOR
        )


def test_largura_da_coluna_setor_usa_o_rotulo_exibido_e_nao_o_do_dado():
    # O dado traz "Exploração. Refino e Distribuição"; o exibido é "Exploração, Refino e ...".
    tabela = _tabela_com_setores("Exploração. Refino e Distribuição")

    assert _largura_coluna_setor(tabela) == (
        len("Exploração, Refino e Distribuição") * config.LARGURA_PX_POR_CARACTERE_COLUNA_SETOR
        + config.LARGURA_MARGEM_COLUNA_SETOR
    )


def test_largura_da_coluna_setor_cabe_o_maior_rotulo_com_folga_sobre_o_texto_medido():
    # Na fonte da tabela o texto leva cerca de 6 px por caractere; a coluna usa mais que isso.
    assert config.LARGURA_PX_POR_CARACTERE_COLUNA_SETOR >= 6.5
    assert (
        _largura_coluna_setor(_tabela_com_setores("Exploração. Refino e Distribuição")) > 33 * 6.5
    )


def test_sem_a_coluna_de_setor_ou_sem_nenhum_setor_nao_define_largura():
    assert _largura_coluna_setor(pd.DataFrame({"ticker": ["A"]})) is None
    assert _largura_coluna_setor(_tabela_com_setores(None, None)) is None


def test_configuracao_aplica_a_largura_so_na_coluna_setor():
    configuracao = _configuracao_colunas_ranking(COLUNAS_TABELA_SCREENER, largura_setor=333)

    assert configuracao["segmento_setorial"]["width"] == 333
    assert configuracao["segmento_setorial"]["label"] == "Setor"
    assert configuracao["erro"]["width"] == config.LARGURA_COLUNA_OBSERVACAO_RANKING
    assert (
        "width" not in configuracao["preco_atual"] or configuracao["preco_atual"]["width"] is None
    )


def test_lista_aberta_das_caixas_de_selecao_cabe_o_maior_rotulo_de_setor():
    from avaliador_b3.app.css import _CSS_DA_PAGINA

    maior = max(len(r) for r in config.CORRECOES_EXIBICAO_SEGMENTO_SETORIAL.values())
    assert config.LARGURA_MINIMA_LISTA_SELECAO_PX >= (
        maior * config.LARGURA_PX_POR_CARACTERE_COLUNA_SETOR + config.LARGURA_MARGEM_COLUNA_SETOR
    )
    assert (
        f'[data-testid="stSelectboxVirtualDropdown"] {{ min-width: '
        f"{config.LARGURA_MINIMA_LISTA_SELECAO_PX}px; }}"
    ) in _CSS_DA_PAGINA
