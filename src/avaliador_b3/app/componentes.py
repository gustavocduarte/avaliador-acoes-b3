"""Peças de tela reaproveitadas pelas páginas: cartões, painéis, barra de potencial e gráficos."""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from avaliador_b3.app.formatacao import _fmt_bilhoes, _fmt_percentual, _fmt_potencial
from avaliador_b3.config import (
    CONFIG_PLOTLY,
    COR_BORDA,
    COR_FUNDO_PAINEL,
    COR_GRADE,
    COR_TEXTO,
    LIMITE_BARRA_POTENCIAL,
    LIMITE_SINAL_INDICADOR,
    SEPARADORES_NUMERICOS_GRAFICO,
    SEQUENCIA_CORES_SERIES,
)


def aplicar_template_grafico(figura: go.Figure) -> go.Figure:
    """Template único dos gráficos: fundo transparente (o painel da página
    aparece por trás), grade discreta, fonte e sequência de cores do tema."""
    figura.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COR_TEXTO},
        colorway=list(SEQUENCIA_CORES_SERIES),
        hoverlabel={"bgcolor": COR_FUNDO_PAINEL, "bordercolor": COR_BORDA},
        separators=SEPARADORES_NUMERICOS_GRAFICO,
    )
    figura.update_xaxes(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE, linecolor=COR_BORDA)
    figura.update_yaxes(gridcolor=COR_GRADE, zerolinecolor=COR_GRADE, linecolor=COR_BORDA)
    return figura


def exibir_grafico(figura: go.Figure) -> None:
    """Único ponto de `st.plotly_chart` do app: tema do Plotly (não o do Streamlit), largura
    total e sem a barra de ferramentas."""
    st.plotly_chart(figura, width="stretch", theme=None, config=CONFIG_PLOTLY)


def _html_kpi(
    rotulo: str,
    valor: str,
    classe_cor: str,
    linha: str = "",
    classe_linha: str = "ab-cor-secundario",
    ajuda: str | None = None,
) -> str:
    """Cartão de número de destaque (HTML com as classes `.ab-*` de `_CSS_DA_PAGINA`);
    `st.metric` não deixa colorir o número. `ajuda` vira o "?" com tooltip."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    return (
        '<div class="ab-kpi">'
        f'<div class="ab-titulo">{escape(rotulo)}{marca_ajuda}</div>'
        f'<div class="ab-valor {classe_cor}">{escape(valor)}</div>'
        f'<div class="ab-linha {classe_linha}">{escape(linha)}</div>'
        "</div>"
    )


def _html_cabecalho_painel(
    titulo: str, selos: list[tuple[str, str]], ajuda: str | None = None
) -> str:
    """Título do painel (pequeno, em caixa alta, com "?" opcional) e, à direita, selos
    `(texto, dica)`."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    html_selos = "".join(
        f'<span class="ab-selo" title="{escape(dica)}">{escape(texto)}</span>'
        for texto, dica in selos
    )
    return (
        f'<div class="ab-cabecalho"><span class="ab-titulo">{escape(titulo)}{marca_ajuda}</span>'
        f'<span class="ab-selos">{html_selos}</span></div>'
    )


def _titulo_painel(titulo: str, ajuda: str | None = None) -> None:
    """Título pequeno de painel, sem âncora (no lugar de `st.subheader`)."""
    st.html(_html_cabecalho_painel(titulo, [], ajuda))


def _html_barra_potencial(valor: float | None) -> str:
    """Barra divergente do potencial: verde à direita do centro, rosa à esquerda, cortada em
    `LIMITE_BARRA_POTENCIAL`; o valor exato fica ao lado."""
    if valor is None or pd.isna(valor):
        return (
            '<div class="ab-div"><span class="ab-div-trilho"></span>'
            '<span class="ab-div-valor">—</span></div>'
        )
    classe = "ab-div-pos" if valor > LIMITE_SINAL_INDICADOR else "ab-div-neg"
    largura = min(abs(valor), LIMITE_BARRA_POTENCIAL) / LIMITE_BARRA_POTENCIAL * 50
    return (
        '<div class="ab-div"><span class="ab-div-trilho">'
        f'<i class="ab-div-barra {classe}" style="width:{largura:.1f}%"></i></span>'
        f'<span class="ab-div-valor">{escape(_fmt_potencial(valor))}</span></div>'
    )


def _tabela_formatada_pt_br(
    df: pd.DataFrame,
    colunas_moeda: dict[str, str],
    colunas_percentual: dict[str, str] | None = None,
    ajudas: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Pré-formata colunas monetárias/percentuais de `df` como texto em
    convenção brasileira (`_fmt_bilhoes`/`_fmt_percentual`) e monta o
    `column_config` correspondente, pronto pra passar pro `st.dataframe`
    — devolve `(df_formatado, column_config)`. `colunas_moeda`/
    `colunas_percentual` são dicts `{nome_da_coluna: rótulo_exibido}`;
    `ajudas` (opcional) é `{nome_da_coluna: tooltip}`.

    Por que texto pré-formatado, não `st.column_config.NumberColumn
    (format=...)`: o `format` do NumberColumn é sprintf-js/d3-format por
    baixo, nenhum dos dois tem vírgula decimal brasileira em qualquer
    locale, e a opção `format="localized"` do Streamlit usa
    `Intl.NumberFormat` com o locale do NAVEGADOR de quem visita (não do
    nosso código) — mesmo anti-padrão já rejeitado pro locale de mês dos
    gráficos (ver `graficos.ticks_mensais_pt_br`), não dá pra garantir
    pt-BR pra todo visitante.

    Custo aceito: clicar no cabeçalho de uma coluna formatada por aqui
    pra reordenar ordena como TEXTO (alfabético, ex: "R$ 1.000,00" antes
    de "R$ 618,70"), não numericamente — as demais colunas da tabela
    (que não passam por aqui) continuam ordenando normal. Usado nas
    tabelas do projeto que mostram R$/%: Screener, Simulador de carteira,
    Ganho nominal vs. real."""
    colunas_percentual = colunas_percentual or {}
    ajudas = ajudas or {}
    df_formatado = df.assign(**{coluna: df[coluna].apply(_fmt_bilhoes) for coluna in colunas_moeda})
    if colunas_percentual:
        df_formatado = df_formatado.assign(
            **{coluna: df_formatado[coluna].apply(_fmt_percentual) for coluna in colunas_percentual}
        )
    column_config = {
        coluna: st.column_config.TextColumn(rotulo, alignment="right", help=ajudas.get(coluna))
        for coluna, rotulo in {**colunas_moeda, **colunas_percentual}.items()
    }
    return df_formatado, column_config
