"""Página Simulador de carteira."""

from datetime import datetime, timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app import barra_lateral
from avaliador_b3.app.componentes import (
    _html_barra_potencial,
    _html_kpi,
    _tabela_formatada_pt_br,
    _titulo_painel,
    aplicar_template_grafico,
    exibir_grafico,
)
from avaliador_b3.app.dados import (
    _buscar_historico,
    _buscar_serie_bcb,
    _carregar_screener_ou_avisar,
)
from avaliador_b3.app.formatacao import (
    _fmt_bilhoes,
    _fmt_percentual,
    _fmt_potencial,
    _fmt_quantidade,
    _lista_em_texto,
    _rotulo_segmento_setorial,
)
from avaliador_b3.carteira import (
    calcular_totais_carteira,
    compor_posicoes,
    montar_tabela_carteira,
    resumir_carteira,
)
from avaliador_b3.config import (
    ACOES_COM_COR_PROPRIA,
    ALTURA_MINIMA_CONTRIBUICAO,
    ALTURA_POR_BARRA_CONTRIBUICAO,
    AVISO_SIMULADOR_SEM_PREVISAO,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_CARTEIRA_ACAO,
    CHAVE_CARTEIRA_POSICOES,
    CHAVE_CARTEIRA_QUANTIDADE,
    CHAVE_CARTEIRA_REMOVER_PREFIXO,
    CHAVE_PERIODO_HISTORICO_CARTEIRA,
    COR_ALERTA,
    COR_FUNDO_PAGINA,
    COR_FUNDO_PAINEL,
    COR_NEGATIVO,
    COR_NEUTRO,
    COR_POSITIVO,
    COR_PRINCIPAL,
    COR_TEXTO,
    CORES_ACOES_CARTEIRA,
    FRASE_RESUMO_SIMULADOR,
    JANELA_PADRAO_HISTORICO_CARTEIRA,
    JANELAS_HISTORICO_CARTEIRA,
    LIMITE_CONCENTRACAO_SETOR_PERCENTUAL,
    LIMITE_ROTULO_INVESTIDO_DIREITA,
    LIMITE_ROTULO_INVESTIDO_ESQUERDA,
    LIMITE_SINAL_INDICADOR,
    NOME_LINHA_CARTEIRA,
    NOME_LINHA_CDI,
    NOME_LINHA_IPCA,
    PESO_MINIMO_TEXTO_NA_FATIA,
    QUANTIDADE_PADRAO_CARTEIRA,
    ROTULO_ADICIONAR_A_CARTEIRA,
    ROTULO_CARTEIRA_ACAO,
    ROTULO_CARTEIRA_QUANTIDADE,
    ROTULO_KPI_CONCENTRACAO,
    ROTULO_KPI_POTENCIAL_CARTEIRA,
    ROTULO_KPI_VALOR_INVESTIDO,
    ROTULO_KPI_VALOR_JUSTO_CARTEIRA,
    ROTULO_LIMPAR_CARTEIRA,
    ROTULO_REMOVER_POSICAO,
    ROTULO_SELETOR_PERIODO_HISTORICO,
    ROTULOS_CENARIOS_CARTEIRA,
    ROTULOS_COLUNAS_POSICOES,
    TEXTO_ABERTURA_SIMULADOR,
    TEXTO_AJUDA_POTENCIAL_DO_TOTAL,
    TEXTO_AVISO_FORA_DO_SCREENER,
    TEXTO_BUSCANDO_HISTORICO,
    TEXTO_CARTEIRA_ACAO_PLACEHOLDER,
    TEXTO_CARTEIRA_VAZIA,
    TEXTO_CENARIO_LIMITADO_SINGULAR,
    TEXTO_CENARIOS_LIMITADOS_PLURAL,
    TEXTO_DEMAIS_ACOES_NA_CARTEIRA,
    TEXTO_EXPANDER_SIMULADOR,
    TEXTO_FORA_DA_LINHA_CARTEIRA,
    TEXTO_INVESTIDO_NO_CENTRO,
    TEXTO_KPI_POSICAO_SINGULAR,
    TEXTO_KPI_POSICOES,
    TEXTO_KPI_SEM_COMBINADO,
    TEXTO_KPI_SOBRE_COM_COMBINADO,
    TEXTO_LINHA_INVESTIDO_NO_GRAFICO,
    TEXTO_MAIS_DE_METADE_NUM_SETOR,
    TEXTO_NENHUM_HISTORICO_DA_CARTEIRA,
    TEXTO_NENHUM_METODO_SE_APLICA,
    TEXTO_NENHUMA_ACAO_COM_CENARIO,
    TEXTO_OUTRAS_ACOES,
    TEXTO_POSICAO_DA_CARTEIRA,
    TEXTO_POSICAO_FORA_DO_SCREENER,
    TEXTO_POSICAO_SEM_COMBINADO,
    TEXTO_SELECIONE_PERIODO_HISTORICO,
    TEXTO_SEM_CENARIO_PLURAL,
    TEXTO_SEM_CENARIO_SINGULAR,
    TEXTO_SEM_CONTRIBUICAO,
    TEXTO_SEM_DADO_NA_TABELA,
    TEXTO_SEM_HISTORICO_DE_PRECOS,
    TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO,
    TEXTO_TOTAL_DAS_POSICOES,
    TITULO_CENARIOS_CARTEIRA,
    TITULO_COMPOSICAO_ACAO,
    TITULO_COMPOSICAO_SETOR,
    TITULO_CONTRIBUICAO_CARTEIRA,
    TITULO_EXPANDER_CENARIOS_POR_ACAO,
    TITULO_EXPANDER_SIMULADOR,
    TITULO_HISTORICO_CARTEIRA,
    TITULO_POSICOES,
    TOLERANCIA_INICIO_HISTORICO_DIAS,
    TOOLTIP_COMPOSICAO_ACAO,
    TOOLTIP_COMPOSICAO_SETOR,
    TOOLTIP_CONCENTRACAO,
    TOOLTIP_CONTRIBUICAO_CARTEIRA,
    TOOLTIP_HISTORICO_CARTEIRA,
    TOOLTIP_POSICOES,
    TOOLTIP_POTENCIAL_CARTEIRA,
    TOOLTIP_POTENCIAL_CENARIO,
    TOOLTIP_VALOR_JUSTO_CARTEIRA,
)
from avaliador_b3.graficos import ticks_mensais_pt_br
from avaliador_b3.historico_carteira import (
    HistoricoDaCarteira,
    montar_historico,
    serie_cdi,
    serie_ipca,
)
from avaliador_b3.numeros import numero_finito


def _preco_valido_da_linha(linha: pd.Series) -> float | None:
    preco = linha.get("preco_atual")
    return float(preco) if numero_finito(preco) else None


def _html_kpis_carteira(resumo: dict) -> str:
    """Cartões do topo do Simulador: valor investido, valor justo da carteira (ciano), potencial
    (verde ou rosa, com a diferença em R$) e concentração no maior setor (amarela acima de 50%)."""
    sem_combinado = resumo["quantidade_sem_combinado"]
    linha_investido = (
        TEXTO_KPI_SEM_COMBINADO.format(
            quantidade=sem_combinado, valor=_fmt_bilhoes(resumo["investido_sem_combinado"])
        )
        if sem_combinado
        else (
            TEXTO_KPI_POSICAO_SINGULAR
            if resumo["quantidade_posicoes"] == 1
            else TEXTO_KPI_POSICOES.format(quantidade=resumo["quantidade_posicoes"])
        )
    )
    cartoes = [
        _html_kpi(
            ROTULO_KPI_VALOR_INVESTIDO,
            _fmt_bilhoes(resumo["investido_total"]),
            "ab-cor-texto",
            linha_investido,
        )
    ]

    potencial = resumo["potencial_percentual"]
    if potencial is None:
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_VALOR_JUSTO_CARTEIRA,
                "—",
                "ab-cor-secundario",
                TEXTO_NENHUM_METODO_SE_APLICA,
                ajuda=TOOLTIP_VALOR_JUSTO_CARTEIRA,
            )
        )
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_POTENCIAL_CARTEIRA,
                "—",
                "ab-cor-secundario",
                TEXTO_NENHUM_METODO_SE_APLICA,
                ajuda=TOOLTIP_POTENCIAL_CARTEIRA,
            )
        )
    else:
        cor = (
            "ab-cor-positivo"
            if potencial > LIMITE_SINAL_INDICADOR
            else "ab-cor-negativo"
            if potencial < LIMITE_SINAL_INDICADOR
            else "ab-cor-texto"
        )
        diferenca = resumo["diferenca_reais"]
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_VALOR_JUSTO_CARTEIRA,
                _fmt_bilhoes(resumo["valor_justo"]),
                "ab-cor-principal",
                TEXTO_KPI_SOBRE_COM_COMBINADO.format(
                    valor=_fmt_bilhoes(resumo["investido_com_combinado"])
                )
                if sem_combinado
                else "",
                ajuda=TOOLTIP_VALOR_JUSTO_CARTEIRA,
            )
        )
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_POTENCIAL_CARTEIRA,
                _fmt_potencial(potencial),
                cor,
                ("+" if diferenca > LIMITE_SINAL_INDICADOR else "") + _fmt_bilhoes(diferenca),
                cor,
                ajuda=TOOLTIP_POTENCIAL_CARTEIRA,
            )
        )

    setor = resumo["setor_de_maior_peso"]
    if setor is None:
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_CONCENTRACAO,
                "—",
                "ab-cor-secundario",
                TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO,
                ajuda=TOOLTIP_CONCENTRACAO,
            )
        )
    else:
        peso = resumo["peso_do_maior_setor_percentual"]
        cartoes.append(
            _html_kpi(
                ROTULO_KPI_CONCENTRACAO,
                _fmt_percentual(peso, 1),
                "ab-cor-alerta" if peso > LIMITE_CONCENTRACAO_SETOR_PERCENTUAL else "ab-cor-texto",
                _rotulo_segmento_setorial(setor) or setor,
                ajuda=TOOLTIP_CONCENTRACAO,
            )
        )
    return f'<div class="ab-kpis">{"".join(cartoes)}</div>'


def _cores_das_acoes(composicao: pd.DataFrame) -> dict[str, str]:
    """Cor de cada uma das maiores ações da carteira (por valor investido), da primeira à última de
    `CORES_ACOES_CARTEIRA`; as demais ficam sem cor própria. A mesma cor em todos os gráficos."""
    maiores = composicao.sort_values("investido", ascending=False, kind="stable")["ticker"]
    return dict(zip(maiores, CORES_ACOES_CARTEIRA, strict=False))


def _fatias_da_composicao(composicao: pd.DataFrame) -> list[tuple[str, float, float]]:
    """`(nome, investido, peso %)` de cada fatia da rosca, da maior para a menor; com mais de
    `ACOES_COM_COR_PROPRIA` ações, as menores se juntam numa fatia "Outras"."""
    ordenada = composicao.sort_values("investido", ascending=False, kind="stable")
    fatias = [
        (linha.ticker, linha.investido, linha.peso_percentual) for linha in ordenada.itertuples()
    ]
    if len(fatias) > ACOES_COM_COR_PROPRIA:
        principais, resto = fatias[:ACOES_COM_COR_PROPRIA], fatias[ACOES_COM_COR_PROPRIA:]
        fatias = [
            *principais,
            (TEXTO_OUTRAS_ACOES, sum(f[1] for f in resto), sum(f[2] for f in resto)),
        ]
    return fatias


def _figura_composicao_por_acao(composicao: pd.DataFrame, cores: dict[str, str]) -> go.Figure:
    """Rosca do peso de cada ação no valor investido, com o % na fatia, o total investido no
    centro e a cor de cada ação (as menores, quando são muitas, viram "Outras")."""
    fatias = _fatias_da_composicao(composicao)
    figura = go.Figure(
        go.Pie(
            labels=[f[0] for f in fatias],
            values=[f[1] for f in fatias],
            hole=0.6,
            sort=False,
            direction="clockwise",
            marker={"colors": [cores.get(f[0], COR_NEUTRO) for f in fatias]},
            # Fatia pequena não mostra o % por dentro; ele fica na legenda e no hover.
            text=[
                _fmt_percentual(f[2], 1) if f[2] >= PESO_MINIMO_TEXTO_NA_FATIA else ""
                for f in fatias
            ],
            textinfo="text",
            customdata=[f"{_fmt_bilhoes(f[1])} ({_fmt_percentual(f[2], 1)})" for f in fatias],
            hovertemplate="%{label}: %{customdata}<extra></extra>",
            textfont={"color": COR_FUNDO_PAGINA},
        )
    )
    figura.add_annotation(
        text=(
            f"<b>{_fmt_bilhoes(composicao['investido'].sum())}</b><br>{TEXTO_INVESTIDO_NO_CENTRO}"
        ),
        showarrow=False,
        font={"color": COR_TEXTO, "size": 14},
    )
    figura.update_layout(height=300, margin={"t": 10, "b": 10, "l": 10, "r": 10})
    return aplicar_template_grafico(figura)


def _pesos_por_setor(composicao: pd.DataFrame) -> pd.Series:
    """Peso (%) de cada setor no investido das posições que têm setor, do maior para o menor."""
    com_setor = composicao[composicao["setor"].notna() & (composicao["investido"] > 0)]
    por_setor = com_setor.groupby("setor")["investido"].sum().sort_values(ascending=False)
    return por_setor / por_setor.sum() * 100 if len(por_setor) else por_setor


def _peso_do_maior_setor(composicao: pd.DataFrame) -> float:
    pesos = _pesos_por_setor(composicao)
    return float(pesos.iloc[0]) if len(pesos) else 0.0


def _figura_composicao_por_setor(composicao: pd.DataFrame) -> go.Figure | None:
    """Barras horizontais do peso de cada setor; a do maior setor fica em amarelo quando ele passa
    de 50%. `None` sem nenhum setor no screener."""
    pesos = _pesos_por_setor(composicao)
    if pesos.empty:
        return None
    destacar = pesos.iloc[0] > LIMITE_CONCENTRACAO_SETOR_PERCENTUAL
    rotulos = [_rotulo_segmento_setorial(setor) or setor for setor in pesos.index]
    figura = go.Figure(
        go.Bar(
            x=list(pesos),
            y=rotulos,
            orientation="h",
            marker={
                "color": [
                    COR_ALERTA if destacar and i == 0 else COR_PRINCIPAL for i in range(len(pesos))
                ]
            },
            text=[_fmt_percentual(p, 1) for p in pesos],
            textposition="outside",
            textfont={"color": COR_TEXTO},
            cliponaxis=False,
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    figura.update_xaxes(range=[0, 120], showticklabels=False)
    figura.update_yaxes(autorange="reversed", automargin=True)
    figura.update_layout(
        height=max(120, 60 + 40 * len(pesos)),
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        showlegend=False,
    )
    return aplicar_template_grafico(figura)


def _html_tabela_posicoes(composicao: pd.DataFrame) -> str:
    """Tabela "Posições" em HTML: ação, quantidade, preço, investido, valor combinado, valor justo,
    potencial (barra divergente) e peso, mais a linha de Total; as posições sem valor combinado
    ficam com "—" e o motivo no "?"."""
    cabecalho = "".join(
        (f'<th class="ab-num">{escape(rotulo)}</th>' if i else f"<th>{escape(rotulo)}</th>")
        for i, rotulo in enumerate(ROTULOS_COLUNAS_POSICOES)
    )
    sem_dado = TEXTO_SEM_DADO_NA_TABELA

    def celula(texto: str) -> str:
        return f'<td class="ab-num">{escape(texto)}</td>'

    linhas = []
    for linha in composicao.itertuples():
        ajuda = ""
        if linha.sem_combinado:
            motivo = escape(TEXTO_POSICAO_SEM_COMBINADO)
            ajuda = f'<span class="ab-ajuda" title="{motivo}">?</span>'
        preco = _fmt_bilhoes(linha.preco_atual) if linha.preco_atual else sem_dado
        combinado = sem_dado if linha.sem_combinado else _fmt_bilhoes(linha.valor_combinado)
        valor_justo = sem_dado if linha.sem_combinado else _fmt_bilhoes(linha.valor_justo)
        linhas.append(
            f"<tr><td>{escape(str(linha.ticker))}{ajuda}</td>"
            + celula(_fmt_quantidade(linha.quantidade))
            + celula(preco)
            + celula(_fmt_bilhoes(linha.investido))
            + celula(combinado)
            + celula(valor_justo)
            + f"<td>{_html_barra_potencial(linha.potencial_percentual)}</td>"
            + celula(_fmt_percentual(linha.peso_percentual, 1))
            + "</tr>"
        )
    com_valor = composicao[~composicao["sem_combinado"]]
    investido_com_valor = com_valor["investido"].sum()
    valor_justo_total = com_valor["valor_justo"].sum()
    potencial = (valor_justo_total / investido_com_valor - 1) * 100 if investido_com_valor else None
    ajuda_total = ""
    if composicao["sem_combinado"].any():
        # O potencial do Total é só sobre as posições com valor combinado, não sobre o investido
        # total mostrado na mesma linha.
        texto_ajuda = TEXTO_AJUDA_POTENCIAL_DO_TOTAL.format(valor=_fmt_bilhoes(investido_com_valor))
        ajuda_total = f'<span class="ab-ajuda" title="{escape(texto_ajuda)}">?</span>'
    linhas.append(
        f'<tr class="ab-linha-total"><td>{escape(TEXTO_TOTAL_DAS_POSICOES)}</td>'
        + celula("")
        + celula("")
        + celula(_fmt_bilhoes(composicao["investido"].sum()))
        + celula("")
        + celula(_fmt_bilhoes(valor_justo_total) if investido_com_valor else sem_dado)
        + f"<td>{_html_barra_potencial(potencial)}{ajuda_total}</td>"
        + celula(_fmt_percentual(composicao["peso_percentual"].sum(), 1))
        + "</tr>"
    )
    return (
        '<div class="ab-tabela-caixa"><table class="ab-tabela ab-tabela-posicoes"><thead><tr>'
        f"{cabecalho}</tr></thead><tbody>{''.join(linhas)}</tbody></table></div>"
    )


def _frase_resumo_cenarios(totais: dict) -> str:
    """ "R$ X investidos hoje equivaleriam a entre R$ P (pessimista) e R$ O (otimista)…", sobre as
    posições com cenário."""
    return FRASE_RESUMO_SIMULADOR.format(
        investido=_fmt_bilhoes(totais["soma_investida_com_cenario"]),
        pessimista=_fmt_bilhoes(totais["total_pessimista"]),
        otimista=_fmt_bilhoes(totais["total_otimista"]),
    )


def _ajuda_cenarios_carteira(totais: dict) -> str:
    """ "?" do painel Cenários: a abertura do Simulador, o aviso de que não é previsão e, havendo
    cenário, a frase-resumo com os valores da carteira."""
    partes = [TEXTO_ABERTURA_SIMULADOR, AVISO_SIMULADOR_SEM_PREVISAO]
    if totais["soma_investida_com_cenario"]:
        partes.append(_frase_resumo_cenarios(totais))
    return " ".join(partes)


def _html_cenarios_carteira(totais: dict) -> str:
    """Três linhas (pessimista, base e otimista) com o valor da carteira em cada cenário e o
    potencial sobre o investido nas posições com cenário; o base fica em destaque."""
    investido = totais["soma_investida_com_cenario"]
    linhas = []
    for cenario in ("pessimista", "base", "otimista"):
        valor = totais[f"total_{cenario}"]
        potencial = (valor / investido - 1) * 100 if investido else None
        cor = (
            "ab-cor-texto"
            if potencial is None or potencial == LIMITE_SINAL_INDICADOR
            else "ab-cor-positivo"
            if potencial > LIMITE_SINAL_INDICADOR
            else "ab-cor-negativo"
        )
        destaque = " ab-cenario-base" if cenario == "base" else ""
        linhas.append(
            f'<div class="ab-cenario{destaque}">'
            f"<span>{escape(ROTULOS_CENARIOS_CARTEIRA[cenario])}</span>"
            f'<span class="ab-cenario-valor">{escape(_fmt_bilhoes(valor))}</span>'
            f'<span class="ab-cenario-valor {cor}">{escape(_fmt_potencial(potencial))}</span>'
            "</div>"
        )
    return f'<div class="ab-cenarios">{"".join(linhas)}</div>'


def _figura_faixa_cenarios(totais: dict) -> go.Figure:
    """Faixa horizontal do pessimista ao otimista (em R$), com o ponto do base e a linha tracejada
    do valor investido nas posições com cenário."""
    pessimista, base, otimista = (totais[f"total_{c}"] for c in ("pessimista", "base", "otimista"))
    investido = totais["soma_investida_com_cenario"]
    figura = go.Figure()
    figura.add_trace(
        go.Scatter(
            x=[pessimista, otimista],
            y=[0, 0],
            mode="lines",
            line={"color": COR_PRINCIPAL, "width": 16},
            opacity=0.35,
            hoverinfo="skip",
        )
    )
    figura.add_trace(
        go.Scatter(
            x=[base],
            y=[0],
            mode="markers",
            marker={
                "color": COR_PRINCIPAL,
                "size": 16,
                "line": {"color": COR_FUNDO_PAINEL, "width": 2},
            },
            customdata=[_fmt_bilhoes(base)],
            hovertemplate="Base: %{customdata}<extra></extra>",
        )
    )
    menor, maior = min(pessimista, investido), max(otimista, investido)
    folga = (maior - menor) * 0.12 or 1.0
    inicio, fim = menor - folga, maior + folga
    # Na ponta do eixo o rótulo do investido se alinha pelo lado de dentro da linha.
    posicao = (investido - inicio) / (fim - inicio)
    ancora = (
        "right"
        if posicao > LIMITE_ROTULO_INVESTIDO_DIREITA
        else "left"
        if posicao < LIMITE_ROTULO_INVESTIDO_ESQUERDA
        else "center"
    )
    figura.add_vline(
        x=investido,
        line_dash="dash",
        line_color=COR_ALERTA,
        annotation_text=TEXTO_LINHA_INVESTIDO_NO_GRAFICO.format(valor=_fmt_bilhoes(investido)),
        annotation_position="top",
        annotation_xanchor=ancora,
        annotation_font_color=COR_ALERTA,
    )
    figura.update_xaxes(
        range=[inicio, fim],
        tickprefix="R$ ",
        tickformat=",.0f",
        automargin=True,
    )
    figura.update_yaxes(visible=False, range=[-1, 1])
    figura.update_layout(height=170, margin={"t": 36, "b": 10, "l": 10, "r": 10}, showlegend=False)
    return aplicar_template_grafico(figura)


def _figura_contribuicao_carteira(tabela_aplicavel: pd.DataFrame) -> go.Figure:
    """Barras horizontais divergentes da contribuição de cada ação (projeção base menos o
    investido, em R$), verde acima de zero e rosa abaixo, da maior para a menor."""
    ordenada = tabela_aplicavel.assign(
        contribuicao=tabela_aplicavel["projecao_base"] - tabela_aplicavel["valor_investido"]
    ).sort_values("contribuicao", ascending=False)
    valores = list(ordenada["contribuicao"])
    textos = [("+" if v > LIMITE_SINAL_INDICADOR else "") + _fmt_bilhoes(v) for v in valores]
    figura = go.Figure(
        go.Bar(
            x=valores,
            y=list(ordenada["ticker"]),
            orientation="h",
            marker={
                "color": [
                    COR_POSITIVO if v >= LIMITE_SINAL_INDICADOR else COR_NEGATIVO for v in valores
                ]
            },
            text=textos,
            textposition="outside",
            textfont={"color": COR_TEXTO},
            cliponaxis=False,
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    maior_modulo = max((abs(v) for v in valores), default=0.0) or 1.0
    figura.update_xaxes(range=[-maior_modulo * 1.5, maior_modulo * 1.5], showticklabels=False)
    figura.update_yaxes(autorange="reversed", automargin=True)
    figura.update_layout(
        height=max(ALTURA_MINIMA_CONTRIBUICAO, ALTURA_POR_BARRA_CONTRIBUICAO * len(valores) + 40),
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        showlegend=False,
    )
    return aplicar_template_grafico(figura)


def _investimentos_da_carteira(
    tabela_screener: pd.DataFrame, posicoes: dict[str, int]
) -> dict[str, float]:
    """Valor investido em R$ de cada posição: quantidade × preço do screener (zero quando o
    screener não traz preço; a ação segue na carteira, sem cenário)."""
    por_ticker = tabela_screener.set_index("ticker", drop=False)
    investimentos = {}
    for ticker, quantidade in posicoes.items():
        preco = _preco_valido_da_linha(por_ticker.loc[ticker])
        investimentos[ticker] = quantidade * preco if preco is not None else 0.0
    return investimentos


def _adicionar_posicao_da_carteira() -> None:
    """Soma a quantidade escolhida à da ação, se ela já estiver na carteira."""
    ticker = st.session_state.get(CHAVE_CARTEIRA_ACAO)
    quantidade = st.session_state.get(CHAVE_CARTEIRA_QUANTIDADE)
    if not ticker or not quantidade or quantidade < 1:
        return
    posicoes = dict(st.session_state.get(CHAVE_CARTEIRA_POSICOES, {}))
    posicoes[ticker] = posicoes.get(ticker, 0) + int(quantidade)
    st.session_state[CHAVE_CARTEIRA_POSICOES] = posicoes


def _remover_posicao_da_carteira(ticker: str) -> None:
    posicoes = dict(st.session_state.get(CHAVE_CARTEIRA_POSICOES, {}))
    posicoes.pop(ticker, None)
    st.session_state[CHAVE_CARTEIRA_POSICOES] = posicoes


def _limpar_carteira() -> None:
    st.session_state[CHAVE_CARTEIRA_POSICOES] = {}


def _desenhar_montagem_da_carteira(
    tabela_screener: pd.DataFrame,
) -> tuple[dict[str, int], list[str]]:
    """Campos de montagem da carteira no bloco atual da barra lateral (ação, quantidade e
    "Adicionar à carteira") e a lista das posições, cada uma com seu "×", mais "Limpar carteira".
    Devolve as posições que entram nas contas (ticker -> quantidade) e os tickers que saíram do
    screener: esses seguem na lista, marcados, sem entrar nas contas. A carteira vive em
    `CHAVE_CARTEIRA_POSICOES`, que sobrevive à troca de página."""
    tickers = sorted(tabela_screener["ticker"])
    todas = st.session_state.get(CHAVE_CARTEIRA_POSICOES, {})
    posicoes = {t: q for t, q in todas.items() if t in tickers}
    fora_do_screener = [t for t in todas if t not in tickers]

    acao = st.selectbox(
        ROTULO_CARTEIRA_ACAO,
        tickers,
        index=None,
        placeholder=TEXTO_CARTEIRA_ACAO_PLACEHOLDER,
        key=CHAVE_CARTEIRA_ACAO,
    )
    st.number_input(
        ROTULO_CARTEIRA_QUANTIDADE,
        min_value=1,
        value=QUANTIDADE_PADRAO_CARTEIRA,
        step=1,
        key=CHAVE_CARTEIRA_QUANTIDADE,
    )
    st.button(
        ROTULO_ADICIONAR_A_CARTEIRA,
        on_click=_adicionar_posicao_da_carteira,
        disabled=acao is None,
    )

    por_ticker = tabela_screener.set_index("ticker", drop=False)
    for ticker, quantidade in todas.items():
        coluna_texto, coluna_remover = st.columns([4, 1], vertical_alignment="center")
        texto = TEXTO_POSICAO_DA_CARTEIRA.format(ticker=ticker, quantidade=quantidade)
        if ticker in fora_do_screener:
            texto += f" · {TEXTO_POSICAO_FORA_DO_SCREENER}"
        elif not numero_finito(por_ticker.loc[ticker].get("valor_combinado")):
            texto += f" · {TEXTO_POSICAO_SEM_COMBINADO}"
        coluna_texto.markdown(texto)
        coluna_remover.button(
            ROTULO_REMOVER_POSICAO,
            key=CHAVE_CARTEIRA_REMOVER_PREFIXO + ticker,
            on_click=_remover_posicao_da_carteira,
            args=(ticker,),
        )
    if todas:
        st.button(ROTULO_LIMPAR_CARTEIRA, on_click=_limpar_carteira)
    return posicoes, fora_do_screener


def _figura_historico_carteira(
    historico: HistoricoDaCarteira,
    cores: dict[str, str],
    ipca: pd.Series | None,
    cdi: pd.Series | None,
) -> go.Figure:
    """Linhas em R$ do histórico: uma por ação com cor própria (as maiores), a "Carteira" mais
    grossa em COR_PRINCIPAL, a inflação pontilhada em COR_NEUTRO e o CDI tracejado em COR_TEXTO."""
    figura = go.Figure()
    for ticker, serie in historico.por_acao.items():
        if ticker in cores:
            figura.add_trace(
                go.Scatter(
                    x=serie.index,
                    y=serie,
                    name=ticker,
                    mode="lines",
                    line={"color": cores[ticker], "width": 1.5},
                    hovertemplate="R$ %{y:,.2f}",
                )
            )
    if historico.carteira is not None:
        figura.add_trace(
            go.Scatter(
                x=historico.carteira.index,
                y=historico.carteira,
                name=NOME_LINHA_CARTEIRA,
                mode="lines",
                line={"color": COR_PRINCIPAL, "width": 4},
                hovertemplate="R$ %{y:,.2f}",
            )
        )
    for serie, nome, cor, traco in (
        (ipca, NOME_LINHA_IPCA, COR_NEUTRO, "dot"),
        (cdi, NOME_LINHA_CDI, COR_TEXTO, "dash"),
    ):
        if serie is not None:
            figura.add_trace(
                go.Scatter(
                    x=serie.index,
                    y=serie,
                    name=nome,
                    mode="lines",
                    line={"color": cor, "width": 2, "dash": traco},
                    hovertemplate="R$ %{y:,.2f}",
                )
            )
    figura.update_layout(
        height=420,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "top", "y": -0.12, "xanchor": "left", "x": 0},
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
    )
    aplicar_template_grafico(figura)
    todas = [t.x for t in figura.data if len(t.x)]
    if todas:
        tickvals, ticktext = ticks_mensais_pt_br(
            pd.Series(pd.concat([pd.Series(x) for x in todas]))
        )
        figura.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
    figura.update_yaxes(tickprefix="R$ ", tickformat=",.0f", automargin=True)
    return figura


def _desenhar_historico_da_carteira(composicao: pd.DataFrame, cores: dict[str, str]) -> None:
    """Painel "Histórico da carteira": seletor de período, busca dos preços (e do IPCA e do CDI),
    avisos das ações sem histórico completo e o gráfico."""
    _titulo_painel(TITULO_HISTORICO_CARTEIRA, TOOLTIP_HISTORICO_CARTEIRA)
    janela = st.pills(
        ROTULO_SELETOR_PERIODO_HISTORICO,
        options=list(JANELAS_HISTORICO_CARTEIRA),
        default=JANELA_PADRAO_HISTORICO_CARTEIRA,
        key=CHAVE_PERIODO_HISTORICO_CARTEIRA,
    )
    if not janela:
        st.info(TEXTO_SELECIONE_PERIODO_HISTORICO)
        return
    periodo, anos = JANELAS_HISTORICO_CARTEIRA[janela]
    com_preco = composicao[composicao["investido"] > 0]
    valor_inicial = float(com_preco["investido"].sum())
    pesos = dict(zip(com_preco["ticker"], com_preco["investido"] / valor_inicial, strict=True))
    with st.spinner(TEXTO_BUSCANDO_HISTORICO):
        historicos: dict[str, pd.DataFrame] = {}
        sem_preco = []
        for ticker in com_preco["ticker"]:
            historico, erro = _buscar_historico(ticker, periodo)
            if erro or historico is None:
                sem_preco.append(ticker)
            else:
                historicos[ticker] = historico
        inicio_dos_indices = datetime.now() - timedelta(days=365 * anos + 45)
        ipca_mensal, erro_ipca = _buscar_serie_bcb(
            "ipca_mensal", NOME_LINHA_IPCA, inicio_dos_indices
        )
        cdi_diario, erro_cdi = _buscar_serie_bcb("cdi_diaria", NOME_LINHA_CDI, inicio_dos_indices)
    historico = montar_historico(
        historicos, pesos, valor_inicial, anos, TOLERANCIA_INICIO_HISTORICO_DIAS
    )
    historico.sem_historico = [*sem_preco, *historico.sem_historico]
    if not historico.por_acao:
        st.info(TEXTO_NENHUM_HISTORICO_DA_CARTEIRA)
        return
    referencia = (
        historico.carteira
        if historico.carteira is not None
        else next(iter(historico.por_acao.values()))
    )
    datas = referencia.index
    ipca = serie_ipca(ipca_mensal, datas, valor_inicial) if ipca_mensal is not None else None
    cdi = serie_cdi(cdi_diario, datas, valor_inicial) if cdi_diario is not None else None
    exibir_grafico(_figura_historico_carteira(historico, cores, ipca, cdi))
    demais = sorted((t for t in historico.na_carteira if t not in cores), key=lambda t: -pesos[t])
    if demais:
        st.caption(TEXTO_DEMAIS_ACOES_NA_CARTEIRA.format(tickers=", ".join(demais)))
    if historico.fora_da_carteira:
        st.warning(
            TEXTO_FORA_DA_LINHA_CARTEIRA.format(tickers=", ".join(historico.fora_da_carteira))
        )
    if historico.sem_historico:
        st.warning(TEXTO_SEM_HISTORICO_DE_PRECOS.format(tickers=", ".join(historico.sem_historico)))
    for erro in (erro_ipca, erro_cdi):
        if erro:
            st.warning(erro)


def pagina_carteira() -> None:
    tabela_screener_carteira = _carregar_screener_ou_avisar(
        screener_mod.CAMINHO_SAIDA_PADRAO,
        'Rode o screener primeiro na página "Screener"',
    )

    # Os campos de montagem ficam no bloco da barra lateral, depois do link da página.
    with barra_lateral.bloco_da_barra(CHAVE_BARRA_CARTEIRA):
        posicoes: dict[str, int] = {}
        fora_do_screener: list[str] = []
        if tabela_screener_carteira is not None:
            posicoes, fora_do_screener = _desenhar_montagem_da_carteira(tabela_screener_carteira)

    if tabela_screener_carteira is not None:
        if fora_do_screener:
            st.warning(TEXTO_AVISO_FORA_DO_SCREENER.format(tickers=", ".join(fora_do_screener)))
        investimentos = _investimentos_da_carteira(tabela_screener_carteira, posicoes)

        if not investimentos:
            st.caption(TEXTO_ABERTURA_SIMULADOR)
            st.info(TEXTO_CARTEIRA_VAZIA)
        else:
            with st.container(border=True, key="painel_destaque_carteira"):
                st.html(_html_kpis_carteira(resumir_carteira(tabela_screener_carteira, posicoes)))

            tabela_carteira = montar_tabela_carteira(tabela_screener_carteira, investimentos)
            tabela_carteira_aplicavel = tabela_carteira[tabela_carteira["aplicavel"]]
            totais_carteira = calcular_totais_carteira(tabela_carteira)

            coluna_cenarios, coluna_contribuicao = st.columns([1, 2])
            with (
                coluna_cenarios,
                st.container(border=True, key="painel_cenarios_carteira", height="stretch"),
            ):
                _titulo_painel(TITULO_CENARIOS_CARTEIRA, _ajuda_cenarios_carteira(totais_carteira))
                if tabela_carteira_aplicavel.empty:
                    st.info(TEXTO_NENHUMA_ACAO_COM_CENARIO)
                else:
                    st.html(_html_cenarios_carteira(totais_carteira))
                    exibir_grafico(_figura_faixa_cenarios(totais_carteira))
                sem_cenario = list(tabela_carteira[~tabela_carteira["aplicavel"]]["ticker"])
                if sem_cenario:
                    st.caption(
                        (
                            TEXTO_SEM_CENARIO_SINGULAR
                            if len(sem_cenario) == 1
                            else TEXTO_SEM_CENARIO_PLURAL
                        ).format(tickers=_lista_em_texto(sem_cenario))
                    )
            with (
                coluna_contribuicao,
                st.container(border=True, key="painel_contribuicao_carteira", height="stretch"),
            ):
                _titulo_painel(TITULO_CONTRIBUICAO_CARTEIRA, TOOLTIP_CONTRIBUICAO_CARTEIRA)
                if tabela_carteira_aplicavel.empty:
                    st.info(TEXTO_NENHUMA_ACAO_COM_CENARIO)
                else:
                    exibir_grafico(_figura_contribuicao_carteira(tabela_carteira_aplicavel))
                sem_contribuicao = list(tabela_carteira[~tabela_carteira["aplicavel"]]["ticker"])
                if sem_contribuicao:
                    st.caption(TEXTO_SEM_CONTRIBUICAO.format(tickers=", ".join(sem_contribuicao)))

            # Cenário com valor de método ≤ 0 (ex: FCD negativo) é limitado a
            # perda total (R$0, -100%) em vez de projeção negativa — ver
            # carteira.simular_investimento_ticker. Avisa qual(is) cenário(s)
            # de cada ação foram limitados, pra não esconder que o número
            # exibido não é a conta "crua".
            for _, linha_com_cenario in tabela_carteira_aplicavel.iterrows():
                cenarios_limitados = linha_com_cenario["cenarios_limitados_perda_total"]
                if cenarios_limitados:
                    texto = (
                        TEXTO_CENARIO_LIMITADO_SINGULAR
                        if len(cenarios_limitados) == 1
                        else TEXTO_CENARIOS_LIMITADOS_PLURAL
                    )
                    st.caption(
                        texto.format(
                            ticker=linha_com_cenario["ticker"],
                            cenarios=_lista_em_texto([c.capitalize() for c in cenarios_limitados]),
                        )
                    )

            composicao = compor_posicoes(tabela_screener_carteira, posicoes)
            cores_das_acoes = _cores_das_acoes(composicao)
            coluna_por_acao, coluna_por_setor = st.columns(2)
            with (
                coluna_por_acao,
                st.container(border=True, key="painel_composicao_acao", height="stretch"),
            ):
                _titulo_painel(TITULO_COMPOSICAO_ACAO, TOOLTIP_COMPOSICAO_ACAO)
                if composicao["investido"].sum() > 0:
                    exibir_grafico(_figura_composicao_por_acao(composicao, cores_das_acoes))
            with (
                coluna_por_setor,
                st.container(border=True, key="painel_composicao_setor", height="stretch"),
            ):
                _titulo_painel(TITULO_COMPOSICAO_SETOR, TOOLTIP_COMPOSICAO_SETOR)
                figura_setor = _figura_composicao_por_setor(composicao)
                if figura_setor is None:
                    st.info(TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO)
                else:
                    exibir_grafico(figura_setor)
                    if _peso_do_maior_setor(composicao) > LIMITE_CONCENTRACAO_SETOR_PERCENTUAL:
                        st.caption(TEXTO_MAIS_DE_METADE_NUM_SETOR)

            with st.container(border=True, key="painel_posicoes_carteira"):
                _titulo_painel(TITULO_POSICOES, TOOLTIP_POSICOES)
                st.html(_html_tabela_posicoes(composicao))
                if not tabela_carteira_aplicavel.empty:
                    with st.expander(TITULO_EXPANDER_CENARIOS_POR_ACAO):
                        cenarios_fmt, colunas_cenarios = _tabela_formatada_pt_br(
                            tabela_carteira_aplicavel,
                            colunas_moeda={},
                            colunas_percentual={
                                "retorno_pessimista_percentual": ROTULOS_CENARIOS_CARTEIRA[
                                    "pessimista"
                                ],
                                "retorno_base_percentual": ROTULOS_CENARIOS_CARTEIRA["base"],
                                "retorno_otimista_percentual": ROTULOS_CENARIOS_CARTEIRA[
                                    "otimista"
                                ],
                            },
                            ajudas={
                                coluna: TOOLTIP_POTENCIAL_CENARIO
                                for coluna in (
                                    "retorno_pessimista_percentual",
                                    "retorno_base_percentual",
                                    "retorno_otimista_percentual",
                                )
                            },
                        )
                        st.dataframe(
                            cenarios_fmt,
                            column_order=[
                                "ticker",
                                "retorno_pessimista_percentual",
                                "retorno_base_percentual",
                                "retorno_otimista_percentual",
                            ],
                            column_config={"ticker": "Ação", **colunas_cenarios},
                            hide_index=True,
                            width="stretch",
                        )

            with st.container(border=True, key="painel_historico_carteira"):
                _desenhar_historico_da_carteira(composicao, cores_das_acoes)

            with st.expander(TITULO_EXPANDER_SIMULADOR):
                st.markdown(TEXTO_EXPANDER_SIMULADOR)
