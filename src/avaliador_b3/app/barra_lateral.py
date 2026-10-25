"""Barra lateral: menu das páginas, blocos de cada página e rodapé."""

from html import escape

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from avaliador_b3 import rodada
from avaliador_b3.app.dados import (
    _data_da_ultima_rodada,
    _rodar_screener_permitido,
    _texto_screener_atualizado_pelo_workflow,
)
from avaliador_b3.app.formatacao import _fmt_data, _fmt_percentual
from avaliador_b3.config import (
    CHAVE_BARRA_RODAPE,
    ICONE_PAGINA_ANALISAR,
    ICONE_PAGINA_CARTEIRA,
    ICONE_PAGINA_SCREENER,
    SUFIXO_BARRA_ATIVA,
    TEXTO_AJUDA_DATA_APROXIMADA,
    TEXTO_RODAPE_LINK_REPOSITORIO,
    TEXTO_RODAPE_SCREENER_ATUALIZADO,
    TEXTO_RODAPE_SCREENER_ATUALIZADO_APROXIMADO,
    TEXTO_RODAPE_SCREENER_SEM_DATA,
    TEXTO_RODAPE_SELIC,
    TITULO_APP,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    URL_REPOSITORIO,
)
from avaliador_b3.ingest import bcb_sgs


def _rodape_da_barra_lateral() -> None:
    """Data da última atualização do screener (a mesma do aviso do workflow) e o link do
    repositório."""
    macro = bcb_sgs.carregar_macro_referencia()
    data_rodada = _data_da_ultima_rodada()
    with st.sidebar.container(key=CHAVE_BARRA_RODAPE):
        if data_rodada is not None:
            aproximada = rodada.carregar_data_rodada() is None
            ajuda = []
            if aproximada:
                ajuda.append(TEXTO_AJUDA_DATA_APROXIMADA)
            if not _rodar_screener_permitido():
                ajuda.append(_texto_screener_atualizado_pelo_workflow())
            modelo = (
                TEXTO_RODAPE_SCREENER_ATUALIZADO_APROXIMADO
                if aproximada
                else TEXTO_RODAPE_SCREENER_ATUALIZADO
            )
            st.caption(modelo.format(data=_fmt_data(data_rodada)), help=" ".join(ajuda) or None)
            if macro is not None and macro.get("selic_meta") is not None:
                st.caption(
                    TEXTO_RODAPE_SELIC.format(selic=_fmt_percentual(macro["selic_meta"] * 100, 2))
                )
        elif not _rodar_screener_permitido():
            st.caption(
                TEXTO_RODAPE_SCREENER_SEM_DATA,
                help=_texto_screener_atualizado_pelo_workflow(),
            )
        st.markdown(f"[{TEXTO_RODAPE_LINK_REPOSITORIO}]({URL_REPOSITORIO})")


_ROTULOS_DO_MENU = [
    (TITULO_PAGINA_ANALISAR, ICONE_PAGINA_ANALISAR),
    (TITULO_PAGINA_SCREENER, ICONE_PAGINA_SCREENER),
    (TITULO_PAGINA_CARTEIRA, ICONE_PAGINA_CARTEIRA),
]
_CHAVE_BLOCOS_NO_ESTADO = "_blocos_da_barra_lateral"


def montar_barra_lateral(paginas: dict[str, st.Page], pagina_atual: st.Page) -> None:
    """Marca do app e um bloco por página, com o link dela. Os blocos ficam na sessão para a
    página aberta preencher o seu (`bloco_da_barra`)."""
    st.sidebar.html(f'<div class="ab-app-marca">{escape(TITULO_APP)}</div>')
    blocos: dict[str, DeltaGenerator] = {}
    for (chave, pagina), (titulo, icone) in zip(paginas.items(), _ROTULOS_DO_MENU, strict=True):
        ativa = pagina is pagina_atual
        blocos[chave] = st.sidebar.container(
            border=True, key=chave + (SUFIXO_BARRA_ATIVA if ativa else "")
        )
        with blocos[chave]:
            st.page_link(pagina, label=titulo, icon=icone)
    st.session_state[_CHAVE_BLOCOS_NO_ESTADO] = blocos


def bloco_da_barra(chave: str) -> DeltaGenerator:
    """Bloco da barra lateral da página `chave`, criado por `montar_barra_lateral` na execução
    atual. Cada página preenche o seu só quando roda (a análise, a caixa da ação e o Buscar; o
    Screener, os filtros e o botão da rodada)."""
    return st.session_state[_CHAVE_BLOCOS_NO_ESTADO][chave]
