"""Filtros da página Screener (bloco da barra lateral): lógica pura, widgets, valores guardados
ao trocar de página e botão da rodada no fim do bloco."""

import pandas as pd
from streamlit.testing.v1 import AppTest

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.main import _filtrar_tabela_screener
from avaliador_b3.config import (
    OPCAO_TODOS_OS_SETORES,
    ROTULO_FILTRO_ESCONDER_SEM_COMBINADO,
    ROTULO_FILTRO_METODOS,
    ROTULO_FILTRO_POTENCIAL_MINIMO,
    ROTULO_FILTRO_SETOR,
    ROTULO_LIMPAR_FILTROS,
    ROTULO_RODAR_SCREENER,
    TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_SCREENER,
)
from avaliador_b3.screener import COLUNAS_RESULTADO
from tests import test_app_main as app
from tests.helpers_app import abrir_pagina

SETORES = {
    "AAA3": "Bancos",
    "BBB4": "Energia Elétrica",
    "CCC3": "Energia Elétrica",
    "DDD3": "Bancos",
}


def _tabela() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA3", "BBB4", "CCC3", "DDD3"],
            "valor_combinado": [15.0, 12.0, None, 8.0],
            "desconto_percentual": [50.0, -20.0, None, -150.0],
            "metodos_utilizados": ["graham,bazin,fcd", "graham", "", "bazin,fcd"],
        }
    )


def _filtrar(**mudancas) -> list[str]:
    parametros = {
        "setor_por_ticker": SETORES,
        "setor": OPCAO_TODOS_OS_SETORES,
        "potencial_minimo": -100,
        "metodos_exigidos": [],
        "esconder_sem_combinado": False,
    } | mudancas
    return list(_filtrar_tabela_screener(_tabela(), **parametros)["ticker"])


def test_sem_filtros_todas_as_acoes_passam_inclusive_sem_potencial_e_abaixo_de_menos_100():
    assert _filtrar() == ["AAA3", "BBB4", "CCC3", "DDD3"]


def test_potencial_minimo_ligado_tira_as_abaixo_e_as_sem_potencial():
    assert _filtrar(potencial_minimo=-25) == ["AAA3", "BBB4"]
    assert _filtrar(potencial_minimo=0) == ["AAA3"]


def test_exigir_metodo_mostra_so_as_acoes_com_todos_os_marcados():
    assert _filtrar(metodos_exigidos=["fcd"]) == ["AAA3", "DDD3"]
    assert _filtrar(metodos_exigidos=["graham", "fcd"]) == ["AAA3"]
    assert _filtrar(metodos_exigidos=["graham", "bazin", "fcd"]) == ["AAA3"]


def test_esconder_sem_valor_combinado_tira_so_as_sem_combinado():
    assert _filtrar(esconder_sem_combinado=True) == ["AAA3", "BBB4", "DDD3"]


def test_setor_filtra_pelo_rotulo_e_sem_catalogo_nao_filtra():
    assert _filtrar(setor="Bancos") == ["AAA3", "DDD3"]
    assert _filtrar(setor="Bancos", setor_por_ticker=None) == ["AAA3", "BBB4", "CCC3", "DDD3"]


def test_filtros_combinados_valem_todos_ao_mesmo_tempo():
    assert _filtrar(setor="Bancos", metodos_exigidos=["fcd"], potencial_minimo=0) == ["AAA3"]


def _preparar_screener(monkeypatch, tmp_path, com_setor=True) -> None:
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: app._universo_falso(),
    )
    app._bloquear_buscas_de_rede_por_ticker(monkeypatch)
    base = {c: None for c in COLUNAS_RESULTADO} | {
        "sucesso": True,
        "erro": "",
        "aviso_desconto_extremo": "",
    }
    linhas = [
        base
        | {
            "ticker": ticker,
            "preco_atual": 10.0,
            "valor_combinado": valor,
            "desconto_percentual": potencial,
            "metodos_utilizados": metodos,
            "segmento_setorial": SETORES[ticker],
        }
        for ticker, valor, potencial, metodos in [
            ("AAA3", 15.0, 50.0, "graham,bazin,fcd"),
            ("BBB4", 12.0, -20.0, "graham"),
            ("CCC3", None, None, ""),
            ("DDD3", 8.0, -150.0, "bazin,fcd"),
        ]
    ]
    caminho = tmp_path / "screener.csv"
    colunas = (
        [*COLUNAS_RESULTADO]
        if com_setor
        else [c for c in COLUNAS_RESULTADO if c != "segmento_setorial"]
    )
    pd.DataFrame(linhas).reindex(columns=colunas).to_csv(caminho, index=False)
    monkeypatch.setattr(screener_mod, "CAMINHO_SAIDA_PADRAO", caminho)

    def _catalogo_nao_deve_ser_buscado(*args, **kwargs):
        raise AssertionError("a página do Screener não busca o catálogo de emissores")

    monkeypatch.setattr(
        "avaliador_b3.ingest.crosswalk_cnpj.obter_catalogo_emissores",
        _catalogo_nao_deve_ser_buscado,
    )


def _abrir_screener(monkeypatch, tmp_path) -> AppTest:
    _preparar_screener(monkeypatch, tmp_path)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, TITULO_PAGINA_SCREENER)
    assert not at.exception
    return at


def _por_rotulo(elementos, rotulo: str):
    return next(e for e in elementos if e.label == rotulo)


def _linhas_mostradas(at) -> str:
    return next(c.value for c in at.caption if c.value.startswith("Mostrando"))


def test_filtros_ficam_no_bloco_da_barra_lateral_so_na_pagina_do_screener(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    barra = at.sidebar
    assert _por_rotulo(barra.selectbox, ROTULO_FILTRO_SETOR).value == OPCAO_TODOS_OS_SETORES
    assert _por_rotulo(barra.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).value == -100
    assert (
        _por_rotulo(barra.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).format_func(-100)
        == "Sem filtro"
    )
    assert [c.label for c in barra.checkbox] == [
        "Graham",
        "Bazin",
        "FCD",
        ROTULO_FILTRO_ESCONDER_SEM_COMBINADO,
    ]
    assert [c.value for c in barra.checkbox] == [False, False, False, True]
    assert any(ROTULO_FILTRO_METODOS in h.proto.body for h in barra.get("html"))
    assert ROTULO_LIMPAR_FILTROS in [b.label for b in barra.button]

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    assert not at.sidebar.select_slider
    assert ROTULO_LIMPAR_FILTROS not in [b.label for b in at.sidebar.button]


def test_por_padrao_esconde_as_sem_valor_combinado_e_mostra_quantas_sobraram(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    assert _linhas_mostradas(at) == "Mostrando 3 de 4 ações"
    opcoes = _por_rotulo(at.sidebar.selectbox, ROTULO_FILTRO_SETOR).options
    assert opcoes == [OPCAO_TODOS_OS_SETORES, "Bancos", "Energia Elétrica"]


def test_exigir_metodo_e_setor_reduzem_a_tabela(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    _por_rotulo(at.sidebar.checkbox, "FCD").check().run(timeout=60)
    assert _linhas_mostradas(at) == "Mostrando 2 de 4 ações"

    _por_rotulo(at.sidebar.selectbox, ROTULO_FILTRO_SETOR).select("Energia Elétrica").run(
        timeout=60
    )
    assert _linhas_mostradas(at) == "Mostrando 0 de 4 ações"
    assert any("Nenhuma ação passa pelos filtros." in i.value for i in at.info)


def test_filtros_continuam_ao_trocar_de_pagina_e_voltar(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)
    _por_rotulo(at.sidebar.checkbox, "Graham").check().run(timeout=60)
    _por_rotulo(at.sidebar.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).set_value(-25).run(
        timeout=60
    )

    abrir_pagina(at, TITULO_PAGINA_ANALISAR)
    abrir_pagina(at, TITULO_PAGINA_SCREENER)

    assert _por_rotulo(at.sidebar.checkbox, "Graham").value is True
    assert _por_rotulo(at.sidebar.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).value == -25
    assert _linhas_mostradas(at) == "Mostrando 2 de 4 ações"


def test_limpar_filtros_volta_tudo_ao_padrao(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)
    _por_rotulo(at.sidebar.checkbox, "FCD").check().run(timeout=60)
    _por_rotulo(at.sidebar.checkbox, ROTULO_FILTRO_ESCONDER_SEM_COMBINADO).uncheck().run(timeout=60)
    _por_rotulo(at.sidebar.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).set_value(0).run(
        timeout=60
    )

    _por_rotulo(at.sidebar.button, ROTULO_LIMPAR_FILTROS).click().run(timeout=60)

    assert [c.value for c in at.sidebar.checkbox] == [False, False, False, True]
    assert _por_rotulo(at.sidebar.select_slider, ROTULO_FILTRO_POTENCIAL_MINIMO).value == -100
    assert _por_rotulo(at.sidebar.selectbox, ROTULO_FILTRO_SETOR).value == OPCAO_TODOS_OS_SETORES
    assert _linhas_mostradas(at) == "Mostrando 3 de 4 ações"


def test_screener_antigo_sem_a_coluna_de_setor_esconde_o_filtro_e_avisa(monkeypatch, tmp_path):
    _preparar_screener(monkeypatch, tmp_path, com_setor=False)
    at = AppTest.from_file(app.CAMINHO_APP)
    abrir_pagina(at, TITULO_PAGINA_SCREENER)

    assert not at.exception
    assert not at.sidebar.selectbox
    assert TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO in [c.value for c in at.sidebar.caption]
    assert _linhas_mostradas(at) == "Mostrando 3 de 4 ações"


def test_setor_vem_do_csv_sem_buscar_o_catalogo(monkeypatch, tmp_path):
    at = _abrir_screener(monkeypatch, tmp_path)

    assert _por_rotulo(at.sidebar.selectbox, ROTULO_FILTRO_SETOR).options == [
        OPCAO_TODOS_OS_SETORES,
        "Bancos",
        "Energia Elétrica",
    ]
    assert TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO not in [c.value for c in at.sidebar.caption]


def test_botao_da_rodada_so_aparece_com_opt_in_e_fica_no_fim_do_bloco(monkeypatch, tmp_path):
    _preparar_screener(monkeypatch, tmp_path)
    at = AppTest.from_file(app.CAMINHO_APP)
    at.secrets["AVALIADOR_B3_PERMITIR_RODAR_SCREENER"] = True
    abrir_pagina(at, TITULO_PAGINA_SCREENER)

    rotulos = [b.label for b in at.sidebar.button]
    assert rotulos[-1] == ROTULO_RODAR_SCREENER
    assert rotulos.count(ROTULO_RODAR_SCREENER) == 1
    assert rotulos.index(ROTULO_LIMPAR_FILTROS) < rotulos.index(ROTULO_RODAR_SCREENER)


def test_mediana_negativa_fica_rosa_e_sem_potencial_nenhum_fica_cinza_com_traco():
    from avaliador_b3.app.main import _html_kpis_screener

    tabela = pd.DataFrame(
        {
            "valor_combinado": [10.0, 5.0, None],
            "desconto_percentual": [-10.0, -30.0, None],
            "fcd_valor_justo": [None, None, None],
        }
    )
    html = _html_kpis_screener(tabela)
    assert 'ab-valor ab-cor-negativo">-20,0%' in html
    assert 'ab-valor ab-cor-positivo">0<' in html
    assert "2 de 3" in html and "1 sem nenhum método aplicável" in html

    vazia = _html_kpis_screener(tabela.assign(valor_combinado=None, desconto_percentual=None))
    assert 'ab-valor ab-cor-secundario">—<' in vazia
