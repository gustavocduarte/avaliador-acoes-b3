"""Página Screener."""

import re
import warnings
from datetime import datetime
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app import barra_lateral
from avaliador_b3.app.componentes import (
    _html_kpi,
    _titulo_painel,
    aplicar_template_grafico,
    exibir_grafico,
)
from avaliador_b3.app.dados import _carregar_screener_ou_avisar, _rodar_screener_permitido
from avaliador_b3.app.formatacao import (
    _acoes_por_extenso,
    _fmt_bilhoes,
    _fmt_potencial,
    _nomes_dos_metodos_do_csv,
    _percentual_ou_traco,
    _rotulo_segmento_setorial,
    _texto_potencial_minimo,
)
from avaliador_b3.config import (
    CHAVE_BARRA_SCREENER,
    CHAVE_FILTRO_ESCONDER_SEM_COMBINADO,
    CHAVE_FILTRO_METODO_PREFIXO,
    CHAVE_FILTRO_POTENCIAL_MINIMO,
    CHAVE_FILTRO_SETOR,
    CHAVE_FILTROS_GUARDADOS,
    CHAVE_RODAR_SCREENER_SOLICITADO,
    COR_ALERTA,
    COR_NEGATIVO,
    COR_POSITIVO,
    COR_TEXTO,
    COR_TEXTO_SECUNDARIO,
    FAIXA_POTENCIAL_LARGURA,
    FAIXA_POTENCIAL_LIMITE,
    FOLGA_TOPO_HISTOGRAMA,
    FRACAO_ROTULO_BARRA_HISTOGRAMA,
    LARGURA_COLUNA_OBSERVACAO_RANKING,
    LARGURA_MARGEM_COLUNA_SETOR,
    LARGURA_PX_POR_CARACTERE_COLUNA_SETOR,
    LIMITE_CARACTERES_OBSERVACAO_RANKING,
    LIMITE_SINAL_INDICADOR,
    MARCA_FCD_DEDUCOES_NA_TABELA,
    MOTIVOS_FCD_NAO_APLICAVEL_POR_SETOR,
    NOMES_METODOS,
    OPCAO_TODOS_OS_SETORES,
    POTENCIAL_MINIMO_FILTRO_DESLIGADO,
    POTENCIAL_MINIMO_FILTRO_MAXIMO,
    POTENCIAL_MINIMO_FILTRO_PASSO,
    ROTULO_COLUNAS_RANKING_SCREENER,
    ROTULO_FILTRO_ESCONDER_SEM_COMBINADO,
    ROTULO_FILTRO_METODOS,
    ROTULO_FILTRO_POTENCIAL_MINIMO,
    ROTULO_FILTRO_SETOR,
    ROTULO_KPI_ABAIXO_DO_VALOR_JUSTO,
    ROTULO_KPI_COM_COMBINADO,
    ROTULO_KPI_COM_FCD,
    ROTULO_KPI_MEDIANA_POTENCIAL,
    ROTULO_LIMPAR_FILTROS,
    ROTULO_RODAR_SCREENER,
    SEPARADOR_OBSERVACAO_RANKING,
    TEXTO_AJUDA_RANKING_SCREENER,
    TEXTO_CARTAO_SEM_METODO,
    TEXTO_CORTE_DA_OBSERVACAO,
    TEXTO_DESMARQUE_OPCAO,
    TEXTO_DESMARQUE_QUALQUER,
    TEXTO_DESMARQUE_UM,
    TEXTO_DESMARQUE_VARIOS,
    TEXTO_FAIXA_ACIMA_DO_LIMITE,
    TEXTO_FCD_NAO_APLICAVEL_NA_TABELA,
    TEXTO_FCD_NAO_APLICAVEL_RESUMIDO,
    TEXTO_KPI_ABAIXO_DO_VALOR_JUSTO,
    TEXTO_KPI_COM_COMBINADO,
    TEXTO_KPI_COM_FCD,
    TEXTO_KPI_SEM_METODO,
    TEXTO_LEGENDA_FILTRO_METODOS,
    TEXTO_LINK_ACAO_REGEX,
    TEXTO_MEDIANA_NO_GRAFICO,
    TEXTO_MOSTRANDO_ACOES,
    TEXTO_NENHUM_ALERTA,
    TEXTO_NENHUM_METODO_NA_TABELA,
    TEXTO_NENHUM_METODO_SE_APLICA,
    TEXTO_NENHUMA_ACAO_NOS_FILTROS,
    TEXTO_RODADA_DESCARTADA,
    TEXTO_SCREENER_CONCLUIDO,
    TEXTO_SCREENER_CONCLUIDO_COM_FALHAS,
    TEXTO_SEM_ACAO_METODO,
    TEXTO_SEM_ACAO_METODO_NO_SETOR,
    TEXTO_SEM_ACAO_TODOS_OS_METODOS,
    TEXTO_SEM_ACAO_TODOS_OS_METODOS_LISTADOS,
    TEXTO_SEM_DADO_NA_TABELA,
    TEXTO_SEM_POTENCIAL_PARA_O_GRAFICO,
    TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO,
    TEXTOS_CURTOS_AVISO_DESCONTO_EXTREMO,
    TITULO_ATENCAO,
    TITULO_CARTAO_SEM_METODO,
    TITULO_DISTRIBUICAO_POTENCIAL,
    TITULO_EIXO_POTENCIAL,
    TITULO_RANKING_SCREENER,
    TOOLTIP_DISTRIBUICAO_POTENCIAL,
    TOOLTIP_MEDIANA_POTENCIAL,
    TOOLTIP_POTENCIAL_COLUNA,
    URL_LINK_ACAO,
)
from avaliador_b3.screener import (
    DeteccaoAnoCvmFalhouWarning,
    FundamentusIndisponivelWarning,
    MacroIndisponivelWarning,
    RodadaScreenerRejeitada,
)

# Colunas do ranking mostradas como texto ("12%" ou "—").
COLUNAS_PERCENTUAL_EM_TEXTO_RANKING = [
    "divergencia_percentual_metodos",
    "bazin_razao_dividendos_percentual",
    "proporcao_reinvestimento_percentual",
]


COLUNAS_TABELA_SCREENER = [
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


def _filtrar_tabela_screener(
    tabela: pd.DataFrame,
    setor_por_ticker: dict[str, str] | None,
    setor: str,
    potencial_minimo: float,
    metodos_exigidos: list[str],
    esconder_sem_combinado: bool,
) -> pd.DataFrame:
    """Linhas do screener que passam pelos filtros: setor (rótulo exibido), potencial mínimo
    (desligado no valor mínimo do slider; ação sem potencial não passa quando ligado), métodos
    que precisam estar todos entre os aplicáveis e, se pedido, só ações com valor combinado."""
    mascara = pd.Series(True, index=tabela.index)
    if esconder_sem_combinado:
        mascara &= tabela["valor_combinado"].notna()
    if potencial_minimo > POTENCIAL_MINIMO_FILTRO_DESLIGADO:
        mascara &= tabela["desconto_percentual"] >= potencial_minimo
    if metodos_exigidos:
        aplicaveis = tabela["metodos_utilizados"].fillna("").map(lambda v: set(v.split(",")))
        mascara &= aplicaveis.map(lambda usados: set(metodos_exigidos) <= usados)
    if setor != OPCAO_TODOS_OS_SETORES and setor_por_ticker is not None:
        mascara &= tabela["ticker"].map(setor_por_ticker) == setor
    return tabela[mascara]


def _texto_sem_acao_nos_filtros(
    tabela: pd.DataFrame,
    setor_por_ticker: dict[str, str] | None,
    setor: str,
    potencial_minimo: float,
    metodos_exigidos: list[str],
    esconder_sem_combinado: bool,
) -> str:
    """Mensagem para quando nenhuma ação passa pelos filtros. Se a causa é um método marcado (o
    filtro exige todos os marcados), diz qual e quantas ações aparecem ao desmarcá-lo; se é
    outro filtro, o texto genérico."""

    def contar(metodos: list[str]) -> int:
        return len(
            _filtrar_tabela_screener(
                tabela,
                setor_por_ticker,
                setor,
                potencial_minimo,
                metodos,
                esconder_sem_combinado,
            )
        )

    liberam = {
        metodo: quantidade
        for metodo in metodos_exigidos
        if (quantidade := contar([m for m in metodos_exigidos if m != metodo]))
    }
    if len(liberam) == 1:
        ((metodo, quantidade),) = liberam.items()
        nome = NOMES_METODOS[metodo]
        if setor == OPCAO_TODOS_OS_SETORES:
            inicio = TEXTO_SEM_ACAO_METODO.format(metodo=nome)
        else:
            inicio = TEXTO_SEM_ACAO_METODO_NO_SETOR.format(setor=setor, metodo=nome)
            motivo = MOTIVOS_FCD_NAO_APLICAVEL_POR_SETOR.get(setor) if metodo == "fcd" else None
            inicio += f": {motivo}." if motivo else "."
        fim = TEXTO_DESMARQUE_UM.format(metodo=nome, acoes=_acoes_por_extenso(quantidade, setor))
        return f"{inicio} {fim}"
    if liberam:
        opcoes = " ou ".join(
            TEXTO_DESMARQUE_OPCAO.format(
                metodo=NOMES_METODOS[metodo], acoes=_acoes_por_extenso(quantidade, setor)
            )
            for metodo, quantidade in liberam.items()
        )
        return f"{TEXTO_SEM_ACAO_TODOS_OS_METODOS} {TEXTO_DESMARQUE_VARIOS.format(opcoes=opcoes)}"
    sem_metodos = contar([]) if metodos_exigidos else 0
    if sem_metodos:
        nomes = " e ".join(NOMES_METODOS[m] for m in metodos_exigidos)
        return (
            f"{TEXTO_SEM_ACAO_TODOS_OS_METODOS_LISTADOS.format(metodos=nomes)} "
            f"{TEXTO_DESMARQUE_QUALQUER.format(acoes=_acoes_por_extenso(sem_metodos, setor))}"
        )
    return TEXTO_NENHUMA_ACAO_NOS_FILTROS


def _padroes_filtros_screener() -> dict[str, object]:
    """Chave do session_state de cada filtro e o valor padrão."""
    return {
        CHAVE_FILTRO_SETOR: OPCAO_TODOS_OS_SETORES,
        CHAVE_FILTRO_POTENCIAL_MINIMO: POTENCIAL_MINIMO_FILTRO_DESLIGADO,
        **{CHAVE_FILTRO_METODO_PREFIXO + metodo: False for metodo in NOMES_METODOS},
        CHAVE_FILTRO_ESCONDER_SEM_COMBINADO: True,
    }


def _limpar_filtros_screener() -> None:
    padroes = _padroes_filtros_screener()
    st.session_state.update(padroes)
    st.session_state[CHAVE_FILTROS_GUARDADOS] = dict(padroes)


def _solicitar_rodada_screener() -> None:
    st.session_state[CHAVE_RODAR_SCREENER_SOLICITADO] = True


def _html_kpis_screener(tabela: pd.DataFrame) -> str:
    """Cartões do topo do Screener, sobre o universo inteiro: ações com valor combinado, mediana
    do potencial (verde se positiva, rosa se negativa), ações abaixo do valor justo (potencial
    acima de zero) e ações com FCD aplicável."""
    total = len(tabela)
    com_combinado = int(tabela["valor_combinado"].notna().sum())
    potencial = tabela["desconto_percentual"]
    mediana = potencial.median()
    cor_mediana = (
        "ab-cor-secundario"
        if pd.isna(mediana)
        else "ab-cor-positivo"
        if mediana > LIMITE_SINAL_INDICADOR
        else "ab-cor-negativo"
    )
    cartoes = [
        _html_kpi(
            ROTULO_KPI_COM_COMBINADO,
            TEXTO_KPI_COM_COMBINADO.format(com=com_combinado, total=total),
            "ab-cor-texto",
            TEXTO_KPI_SEM_METODO.format(sem=total - com_combinado),
        ),
        _html_kpi(
            ROTULO_KPI_MEDIANA_POTENCIAL,
            "—" if pd.isna(mediana) else _fmt_potencial(mediana),
            cor_mediana,
            ajuda=TOOLTIP_MEDIANA_POTENCIAL,
        ),
        _html_kpi(
            ROTULO_KPI_ABAIXO_DO_VALOR_JUSTO,
            str(int((potencial > LIMITE_SINAL_INDICADOR).sum())),
            "ab-cor-positivo",
            TEXTO_KPI_ABAIXO_DO_VALOR_JUSTO,
        ),
        _html_kpi(
            ROTULO_KPI_COM_FCD,
            str(int(tabela["fcd_valor_justo"].notna().sum())),
            "ab-cor-principal",
            TEXTO_KPI_COM_FCD,
        ),
    ]
    return f'<div class="ab-kpis">{"".join(cartoes)}</div>'


def _faixa_do_potencial(valor: float) -> int:
    """Índice da faixa do potencial: 0 a 9 (de 20 em 20 pontos, de -100% a +100%) e 10 para o
    que passa de +100%; o que fica abaixo de -100% entra na primeira."""
    faixas = 2 * FAIXA_POTENCIAL_LIMITE // FAIXA_POTENCIAL_LARGURA
    if valor > FAIXA_POTENCIAL_LIMITE:
        return faixas
    indice = int((valor + FAIXA_POTENCIAL_LIMITE) // FAIXA_POTENCIAL_LARGURA)
    return min(max(indice, 0), faixas - 1)


def _rotulos_das_faixas() -> list[str]:
    limites = range(-FAIXA_POTENCIAL_LIMITE, FAIXA_POTENCIAL_LIMITE, FAIXA_POTENCIAL_LARGURA)
    return [f"{i} a {i + FAIXA_POTENCIAL_LARGURA}%" for i in limites] + [
        TEXTO_FAIXA_ACIMA_DO_LIMITE
    ]


def _figura_distribuicao_potencial(potencial: pd.Series) -> go.Figure:
    """Histograma do potencial em faixas de 20 pontos (e uma faixa para o que passa de +100%),
    com barras rosa abaixo de zero e verdes acima, uma linha fina no zero e a mediana tracejada."""
    valores = potencial.dropna()
    rotulos = _rotulos_das_faixas()
    contagens = [0] * len(rotulos)
    for valor in valores:
        contagens[_faixa_do_potencial(valor)] += 1
    faixas_negativas = FAIXA_POTENCIAL_LIMITE // FAIXA_POTENCIAL_LARGURA
    cores = [COR_NEGATIVO if i < faixas_negativas else COR_POSITIVO for i in range(len(rotulos))]
    figura = go.Figure(
        go.Bar(
            x=list(range(len(rotulos))),
            y=contagens,
            marker={"color": cores},
            text=[str(c) if c else "" for c in contagens],
            textposition="outside",
            textfont={"color": COR_TEXTO},
            cliponaxis=False,
            customdata=rotulos,
            hovertemplate="%{customdata}: %{y} ações<extra></extra>",
        )
    )
    figura.add_vline(x=faixas_negativas - 0.5, line_width=1, line_color=COR_TEXTO_SECUNDARIO)
    # A linha da mediana desce do topo só até acima do número da barra que ela cruza, e o rótulo
    # fica acima da área do gráfico: nada passa por cima de número de barra.
    mediana = float(valores.median())
    posicao_mediana = _posicao_no_histograma(mediana)
    topo = max(contagens, default=0) * FOLGA_TOPO_HISTOGRAMA + 1
    barra = min(max(round(posicao_mediana), 0), len(contagens) - 1)
    corte = contagens[barra] + topo * FRACAO_ROTULO_BARRA_HISTOGRAMA
    figura.add_shape(
        type="line",
        x0=posicao_mediana,
        x1=posicao_mediana,
        y0=corte,
        y1=topo,
        yref="y",
        line={"color": COR_ALERTA, "dash": "dash", "width": 2},
    )
    figura.add_annotation(
        x=posicao_mediana,
        y=1,
        yref="paper",
        yanchor="bottom",
        text=TEXTO_MEDIANA_NO_GRAFICO.format(mediana=_fmt_potencial(mediana)),
        showarrow=False,
        font={"color": COR_ALERTA},
    )
    # Rótulos nas bordas das faixas (-100 ... +80) e ">100" sob a última barra; o "%" vai no título.
    bordas = range(-FAIXA_POTENCIAL_LIMITE, FAIXA_POTENCIAL_LIMITE, FAIXA_POTENCIAL_LARGURA)
    figura.update_xaxes(
        tickvals=[i - 0.5 for i in range(len(bordas))] + [len(rotulos) - 1],
        ticktext=[f"{borda:+d}" if borda > 0 else str(borda) for borda in bordas]
        + [TEXTO_FAIXA_ACIMA_DO_LIMITE.rstrip("%")],
        tickfont={"size": 10},
        tickangle=0,
        automargin=True,
        title={"text": TITULO_EIXO_POTENCIAL, "font": {"size": 10}, "standoff": 8},
    )
    # Folga no topo: o número da barra mais alta não encosta no rótulo da mediana.
    figura.update_yaxes(showticklabels=False, range=[0, topo])
    figura.update_layout(height=300, margin={"t": 36, "b": 10, "l": 24, "r": 10}, showlegend=False)
    return aplicar_template_grafico(figura)


def _posicao_no_histograma(valor: float) -> float:
    """Posição horizontal do valor no histograma: as faixas ocupam [i - 0,5; i + 0,5]; o que passa
    de +100% fica no centro da última faixa."""
    faixas = 2 * FAIXA_POTENCIAL_LIMITE // FAIXA_POTENCIAL_LARGURA
    if valor > FAIXA_POTENCIAL_LIMITE:
        return float(faixas)
    limitado = max(valor, -FAIXA_POTENCIAL_LIMITE)
    return (limitado + FAIXA_POTENCIAL_LIMITE) / FAIXA_POTENCIAL_LARGURA - 0.5


def _resumo_do_aviso(aviso: str) -> str:
    """Linha curta do aviso de potencial extremo (config); um texto desconhecido usa o começo dele,
    até o primeiro " — " ou ponto."""
    if aviso in TEXTOS_CURTOS_AVISO_DESCONTO_EXTREMO:
        return TEXTOS_CURTOS_AVISO_DESCONTO_EXTREMO[aviso]
    return re.split(r" — |\. ", aviso, maxsplit=1)[0].rstrip(".")


def _html_atencao_screener(tabela: pd.DataFrame) -> str:
    """Cartões de alerta do universo inteiro: um por ação com aviso de potencial extremo (ticker,
    potencial, linha curta e o texto completo no "?"), e um com as ações sem método aplicável.
    Sem nenhum, uma frase."""
    cartoes = []
    for linha in tabela[tabela["aviso_desconto_extremo"] != ""].itertuples():
        cor = (
            "ab-cor-positivo"
            if linha.desconto_percentual > LIMITE_SINAL_INDICADOR
            else "ab-cor-negativo"
        )
        cartoes.append(
            '<div class="ab-atencao-cartao">'
            f'<div class="ab-atencao-titulo">{escape(str(linha.ticker))} '
            f'<span class="{cor}">{escape(_fmt_potencial(linha.desconto_percentual))}</span>'
            f'<span class="ab-ajuda" title="{escape(linha.aviso_desconto_extremo)}">?</span></div>'
            f'<div class="ab-atencao-texto">'
            f"{escape(_resumo_do_aviso(linha.aviso_desconto_extremo))}</div></div>"
        )
    sem_metodo = tabela[tabela["valor_combinado"].isna()]
    if len(sem_metodo):
        texto = TEXTO_CARTAO_SEM_METODO.format(
            quantidade=len(sem_metodo), tickers=", ".join(sem_metodo["ticker"])
        )
        cartoes.append(
            '<div class="ab-atencao-cartao">'
            f'<div class="ab-atencao-titulo">{escape(TITULO_CARTAO_SEM_METODO)}</div>'
            f'<div class="ab-atencao-texto">{escape(texto)}</div></div>'
        )
    if not cartoes:
        return f'<div class="ab-atencao-texto">{escape(TEXTO_NENHUM_ALERTA)}</div>'
    return f'<div class="ab-atencao">{"".join(cartoes)}</div>'


def _desenhar_filtros_screener(tabela: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Desenha os filtros no bloco atual da barra lateral e devolve as linhas que passam por
    eles, com o texto para quando nenhuma passa. Os valores escolhidos são copiados para
    `CHAVE_FILTROS_GUARDADOS` e restaurados ao voltar à página."""
    padroes = _padroes_filtros_screener()
    for chave, valor in {**padroes, **st.session_state.get(CHAVE_FILTROS_GUARDADOS, {})}.items():
        st.session_state.setdefault(chave, valor)

    # O setor vem do próprio screener.csv (sem buscar o catálogo); um arquivo anterior à coluna
    # fica sem o filtro de setor até a próxima atualização.
    setor_por_ticker: dict[str, str] | None = None
    if "segmento_setorial" in tabela.columns and tabela["segmento_setorial"].notna().any():
        setor_por_ticker = {
            ticker: _rotulo_segmento_setorial(segmento) or ""
            for ticker, segmento in zip(tabela["ticker"], tabela["segmento_setorial"].fillna(""))
        }
    else:
        st.caption(TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO)
    if setor_por_ticker:
        opcoes = [
            OPCAO_TODOS_OS_SETORES,
            *sorted(set(setor_por_ticker.values()) - {""}, key=str.casefold),
        ]
        if st.session_state.get(CHAVE_FILTRO_SETOR) not in opcoes:
            st.session_state[CHAVE_FILTRO_SETOR] = OPCAO_TODOS_OS_SETORES
        st.selectbox(ROTULO_FILTRO_SETOR, opcoes, key=CHAVE_FILTRO_SETOR)

    st.select_slider(
        ROTULO_FILTRO_POTENCIAL_MINIMO,
        options=list(
            range(
                POTENCIAL_MINIMO_FILTRO_DESLIGADO,
                POTENCIAL_MINIMO_FILTRO_MAXIMO + 1,
                POTENCIAL_MINIMO_FILTRO_PASSO,
            )
        ),
        format_func=_texto_potencial_minimo,
        key=CHAVE_FILTRO_POTENCIAL_MINIMO,
    )
    st.html(f'<div class="ab-rotulo-filtro">{escape(ROTULO_FILTRO_METODOS)}</div>')
    st.caption(TEXTO_LEGENDA_FILTRO_METODOS)
    for metodo, nome in NOMES_METODOS.items():
        st.checkbox(nome, key=CHAVE_FILTRO_METODO_PREFIXO + metodo)
    st.checkbox(ROTULO_FILTRO_ESCONDER_SEM_COMBINADO, key=CHAVE_FILTRO_ESCONDER_SEM_COMBINADO)
    st.button(ROTULO_LIMPAR_FILTROS, on_click=_limpar_filtros_screener)

    valores = {chave: st.session_state.get(chave, padrao) for chave, padrao in padroes.items()}
    st.session_state[CHAVE_FILTROS_GUARDADOS] = valores
    argumentos = (
        tabela,
        setor_por_ticker,
        valores[CHAVE_FILTRO_SETOR],
        valores[CHAVE_FILTRO_POTENCIAL_MINIMO],
        [m for m in NOMES_METODOS if valores[CHAVE_FILTRO_METODO_PREFIXO + m]],
        valores[CHAVE_FILTRO_ESCONDER_SEM_COMBINADO],
    )
    filtrada = _filtrar_tabela_screener(*argumentos)
    texto_vazio = _texto_sem_acao_nos_filtros(*argumentos) if filtrada.empty else ""
    return filtrada, texto_vazio


def _cor_do_potencial(valor: float) -> str:
    """Estilo CSS da célula do potencial: verde acima de zero, rosa abaixo."""
    if pd.isna(valor) or valor == LIMITE_SINAL_INDICADOR:
        return ""
    return f"color: {COR_POSITIVO if valor > LIMITE_SINAL_INDICADOR else COR_NEGATIVO}"


def _observacao_minima(observacao: str) -> str:
    """Observação da rodada na forma mínima da tabela: o FCD sem aplicação por deduções, sem
    valores nem parcelas, e "Nenhum método se aplica" sem a lista de motivos; o resto, como veio
    (a rodada já grava os outros motivos de FCD na forma mínima)."""
    if MARCA_FCD_DEDUCOES_NA_TABELA in observacao:
        return TEXTO_FCD_NAO_APLICAVEL_NA_TABELA
    if observacao.startswith(TEXTO_NENHUM_METODO_SE_APLICA):
        return TEXTO_NENHUM_METODO_NA_TABELA
    return observacao


def _observacao_do_ranking(aviso: str, observacao: str) -> str:
    """Texto da coluna Observação: a linha curta do aviso de potencial extremo (a mesma dos cartões
    "Atenção") e a observação da rodada na forma mínima. Havendo as duas, juntas por " · " só com
    o começo de cada uma ("Potencial extremo · FCD não aplicável"). Texto acima do limite de
    caracteres é cortado com reticências."""
    partes = [_resumo_do_aviso(aviso) if aviso else "", _observacao_minima(observacao)]
    if all(partes):
        partes = [
            TEXTO_FCD_NAO_APLICAVEL_RESUMIDO if parte.startswith("FCD n") else parte.split(":")[0]
            for parte in partes
        ]
    texto = SEPARADOR_OBSERVACAO_RANKING.join(parte for parte in partes if parte)
    if len(texto) > LIMITE_CARACTERES_OBSERVACAO_RANKING:
        texto = (
            texto[: LIMITE_CARACTERES_OBSERVACAO_RANKING - 1].rstrip() + TEXTO_CORTE_DA_OBSERVACAO
        )
    return texto


def _tabela_ranking_screener(tabela: pd.DataFrame) -> tuple[pd.io.formats.style.Styler, list[str]]:
    """Tabela do ranking: ordenada por potencial (as sem valor combinado no fim). Preço, valor
    combinado e potencial são números de verdade (a ordenação do cabeçalho continua numérica),
    apresentados em pt-BR pelo Styler, e o potencial leva sinal e cor. Divergência, dividendos e
    reinvestimento são texto ("12%" ou "—"), sem ordenação numérica, para o vazio não aparecer
    como "None". Aviso e observação formam uma coluna só. Devolve o Styler e as colunas a mostrar,
    na ordem; a do setor só existe se o arquivo do screener a trouxer."""
    colunas = [c for c in COLUNAS_TABELA_SCREENER if c in tabela.columns]
    ordenada = tabela.sort_values("desconto_percentual", ascending=False, na_position="last")
    dados = ordenada[colunas].assign(
        ticker=ordenada["ticker"].map(lambda t: URL_LINK_ACAO.format(acao=t)),
        erro=[
            _observacao_do_ranking(aviso, observacao)
            for aviso, observacao in zip(
                ordenada["aviso_desconto_extremo"], ordenada["erro"], strict=True
            )
        ],
        metodos_utilizados=ordenada["metodos_utilizados"].map(_nomes_dos_metodos_do_csv),
    )
    for coluna in COLUNAS_PERCENTUAL_EM_TEXTO_RANKING:
        dados[coluna] = dados[coluna].map(_percentual_ou_traco)
    if "segmento_setorial" in dados.columns:
        dados = dados.assign(
            segmento_setorial=dados["segmento_setorial"].map(
                lambda segmento: _rotulo_segmento_setorial(segmento) if pd.notna(segmento) else None
            )
        )
    # No Streamlit 1.63 a célula nula de coluna numérica aparece como "None" (cinza), mesmo com
    # `na_rep` do Styler ou `NumberColumn`; aqui só pode aparecer em preço, valor combinado e
    # potencial (ações sem método). As outras colunas vazias saem como texto "—".
    sem_dado = TEXTO_SEM_DADO_NA_TABELA
    estilo = (
        dados.style.format(na_rep=sem_dado)
        .format(_fmt_bilhoes, subset=["preco_atual", "valor_combinado"], na_rep=sem_dado)
        .format(_fmt_potencial, subset=["desconto_percentual"], na_rep=sem_dado)
        .map(_cor_do_potencial, subset=["desconto_percentual"])
    )
    return estilo, colunas


def _largura_coluna_setor(tabela: pd.DataFrame) -> int | None:
    """Largura (px) da coluna Setor: a do maior rótulo de setor da tabela inteira (não só das
    linhas filtradas, para a coluna não mudar de largura ao filtrar); `None` sem a coluna."""
    if "segmento_setorial" not in tabela.columns or tabela["segmento_setorial"].isna().all():
        return None
    maior = max(
        len(_rotulo_segmento_setorial(s) or "") for s in tabela["segmento_setorial"].dropna()
    )
    return maior * LARGURA_PX_POR_CARACTERE_COLUNA_SETOR + LARGURA_MARGEM_COLUNA_SETOR


def _configuracao_colunas_ranking(colunas: list[str], largura_setor: int | None = None) -> dict:
    """`column_config` do ranking: rótulo de cada coluna, o link do ticker, a explicação do
    potencial, a largura da Observação e do Setor e o alinhamento à direita dos percentuais em
    texto."""
    configuracao: dict = {}
    for coluna in colunas:
        rotulo = ROTULO_COLUNAS_RANKING_SCREENER[coluna]
        if coluna == "ticker":
            # O link abre a análise da ação em outra aba; o texto mostrado é só o ticker.
            configuracao[coluna] = st.column_config.LinkColumn(
                rotulo, display_text=TEXTO_LINK_ACAO_REGEX
            )
        elif coluna == "erro":
            configuracao[coluna] = st.column_config.Column(
                rotulo, width=LARGURA_COLUNA_OBSERVACAO_RANKING
            )
        elif coluna == "segmento_setorial" and largura_setor is not None:
            configuracao[coluna] = st.column_config.Column(rotulo, width=largura_setor)
        elif coluna in COLUNAS_PERCENTUAL_EM_TEXTO_RANKING:
            configuracao[coluna] = st.column_config.TextColumn(rotulo, alignment="right")
        else:
            ajuda = TOOLTIP_POTENCIAL_COLUNA if coluna == "desconto_percentual" else None
            configuracao[coluna] = st.column_config.Column(rotulo, help=ajuda)
    return configuracao


def pagina_screener() -> None:
    rodar_screener_permitido = _rodar_screener_permitido()

    if rodar_screener_permitido and st.session_state.pop(CHAVE_RODAR_SCREENER_SOLICITADO, False):
        st.warning(
            "Isso faz ~228 requisições reais (preço, dividendos e Beta de cada "
            "uma das ~76 ações, com delay entre chamadas) — leva de 5 a 15 "
            "minutos. Não feche esta página enquanto roda."
        )
        # Captura os avisos emitidos durante a rodada pra poder mostrar na
        # tela os de DeteccaoAnoCvmFalhouWarning especificamente (sem isso,
        # quem clica no botão só veria a coluna do FCD inteira vazia, sem
        # nenhuma explicação — o aviso de rodar_screener ia só pro log do
        # servidor, invisível na UI). `record=True` intercepta TODOS os
        # avisos da rodada (inclusive o de cache do zip da CVM desatualizado,
        # categoria diferente) — por isso, ao sair do bloco, cada um é
        # reemitido pro canal normal antes de filtrar só os de detecção do
        # ano, preservando o comportamento de log de todos os outros.
        resultado_rodada = rodada_rejeitada = None
        with warnings.catch_warnings(record=True) as avisos_capturados:
            warnings.simplefilter("always")
            with st.spinner("Rodando o screener — isso leva alguns minutos..."):
                try:
                    resultado_rodada = screener_mod.rodar_screener()
                except RodadaScreenerRejeitada as erro:
                    rodada_rejeitada = erro
        for aviso in avisos_capturados:
            warnings.warn_explicit(aviso.message, aviso.category, aviso.filename, aviso.lineno)
        # Mesmo tratamento pros avisos "globais" (afetam a rodada inteira,
        # não uma linha) que rodar_screener pode emitir: detecção do ano da
        # CVM, busca de Selic/IPCA do BCB e Fundamentus indisponível.
        avisos_globais = [
            str(aviso.message)
            for aviso in avisos_capturados
            if issubclass(
                aviso.category,
                (
                    DeteccaoAnoCvmFalhouWarning,
                    MacroIndisponivelWarning,
                    FundamentusIndisponivelWarning,
                ),
            )
        ]
        if avisos_globais:
            # st.rerun() logo abaixo descarta qualquer coisa renderizada
            # nesta mesma execução — guarda em session_state pra mostrar
            # DEPOIS do rerun, não aqui.
            st.session_state["avisos_screener_globais"] = avisos_globais
        if rodada_rejeitada is not None:
            # Sem rerun: a mensagem fica na tela, e a tabela abaixo continua com o
            # resultado anterior, que a rodada descartada não substituiu.
            st.error(
                TEXTO_RODADA_DESCARTADA.format(
                    motivo=rodada_rejeitada.motivo, caminho=rodada_rejeitada.caminho_rejeitado
                )
            )
        else:
            falhas_de_fonte = getattr(resultado_rodada, "attrs", {}).get("falhas_de_fonte", {})
            if falhas_de_fonte:
                acoes_com_falha = ", ".join(
                    f"{ticker} ({', '.join(fontes)})"
                    for ticker, fontes in sorted(falhas_de_fonte.items())
                )
                mensagem = TEXTO_SCREENER_CONCLUIDO_COM_FALHAS.format(acoes=acoes_com_falha)
            else:
                mensagem = TEXTO_SCREENER_CONCLUIDO
            st.session_state["mensagem_rodada_screener"] = mensagem
            st.rerun()

    mensagem_rodada = st.session_state.pop("mensagem_rodada_screener", None)
    if mensagem_rodada:
        st.success(mensagem_rodada)

    for aviso in st.session_state.pop("avisos_screener_globais", []):
        st.warning(aviso)

    tabela_screener = _carregar_screener_ou_avisar(
        screener_mod.CAMINHO_SAIDA_PADRAO,
        f'Clique em "{ROTULO_RODAR_SCREENER}" na barra lateral pra gerar '
        f"{screener_mod.CAMINHO_SAIDA_PADRAO.name}",
    )

    # Filtros e botão da rodada ficam no bloco da barra lateral, depois do link da página.
    with barra_lateral.bloco_da_barra(CHAVE_BARRA_SCREENER):
        tabela_exibida = None
        texto_sem_acao = TEXTO_NENHUMA_ACAO_NOS_FILTROS
        if tabela_screener is not None:
            tabela_exibida, texto_sem_acao = _desenhar_filtros_screener(tabela_screener)
        if rodar_screener_permitido:
            st.button(ROTULO_RODAR_SCREENER, on_click=_solicitar_rodada_screener)

    if tabela_screener is not None and tabela_exibida is not None:
        if rodar_screener_permitido:
            atualizado_em = datetime.fromtimestamp(
                screener_mod.CAMINHO_SAIDA_PADRAO.stat().st_mtime
            )
            st.caption(
                f"Última atualização: {atualizado_em.strftime('%d/%m/%Y %H:%M')} — "
                "dado salvo em disco, não ao vivo. Use o botão acima para atualizar."
            )

        with st.container(border=True, key="painel_destaque_screener"):
            st.html(_html_kpis_screener(tabela_screener))

        coluna_distribuicao, coluna_atencao = st.columns([2, 1])
        with (
            coluna_distribuicao,
            st.container(border=True, key="painel_distribuicao_screener", height="stretch"),
        ):
            _titulo_painel(TITULO_DISTRIBUICAO_POTENCIAL, TOOLTIP_DISTRIBUICAO_POTENCIAL)
            if tabela_exibida["desconto_percentual"].notna().any():
                exibir_grafico(
                    _figura_distribuicao_potencial(tabela_exibida["desconto_percentual"])
                )
            else:
                st.info(TEXTO_SEM_POTENCIAL_PARA_O_GRAFICO)
        with (
            coluna_atencao,
            st.container(border=True, key="painel_atencao_screener", height="stretch"),
        ):
            _titulo_painel(TITULO_ATENCAO)
            st.html(_html_atencao_screener(tabela_screener))

        with st.container(border=True, key="painel_tabela_screener"):
            _titulo_painel(TITULO_RANKING_SCREENER, TEXTO_AJUDA_RANKING_SCREENER)
            st.caption(
                TEXTO_MOSTRANDO_ACOES.format(
                    mostradas=len(tabela_exibida), total=len(tabela_screener)
                )
            )
            if tabela_exibida.empty:
                st.info(texto_sem_acao)
            tabela_ranking, colunas_ranking = _tabela_ranking_screener(tabela_exibida)
            st.dataframe(
                tabela_ranking,
                column_order=colunas_ranking,
                column_config=_configuracao_colunas_ranking(
                    colunas_ranking, _largura_coluna_setor(tabela_screener)
                ),
                hide_index=True,
                width="stretch",
            )

    with st.expander("Como ler esta tabela"):
        st.markdown(
            "- **Potencial** — quanto o valor justo combinado está acima (+) "
            "ou abaixo (-) do preço atual (valor justo ÷ preço - 1). O valor "
            "combinado é a média simples de Graham, Bazin e FCD aplicáveis, "
            "com pesos iguais por simplicidade — veja 'Como funciona esse "
            "cálculo?' na página Analisar uma ação. A tabela vem ordenada do "
            "maior para o menor potencial.\n"
            "- **Divergência** — mostra o quanto os métodos discordam entre "
            "si. Divergência vazia significa que só um método se aplica "
            "àquela ação.\n"
            "- **Dividendos vs. histórico** — mostra os dividendos dos "
            "últimos 12 meses em relação à mediana dos 5 anos anteriores; "
            "valores bem acima de 100% deixam o preço teto do Bazin menos "
            "confiável. Dividendos vs. histórico vazio significa que o Bazin "
            "não se aplica àquela ação (ou, raramente, que os anos "
            "anteriores não têm pagamento para comparar).\n"
            "- **Reinvestimento** — mostra quanto do caixa gerado pela "
            "operação foi para o investimento em imobilizado e intangível "
            "(o mesmo usado no cálculo do FCD) no ano, sobre o mesmo caixa "
            "operacional que o FCD usa (com os juros somados de volta e o ajuste de "
            "risco sacado); valores altos puxam o FCD para baixo. Vazio quando "
            "o FCD não se aplica, o investimento não foi identificado ou o "
            "caixa operacional foi negativo.\n"
            "- **Aviso** — aparece quando o potencial está fora da faixa "
            "considerada confiável (valor justo muito acima ou muito abaixo "
            "do preço); a causa provável varia de uma ação para outra, "
            "conforme o texto de cada aviso. Vazio significa potencial dentro "
            "da faixa normal."
        )
