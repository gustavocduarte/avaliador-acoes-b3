"""Blocos de HTML e gráficos da página de análise."""

import json
import re
from html import escape

import pandas as pd
import plotly.graph_objects as go

from avaliador_b3.app.componentes import _html_barra_potencial, aplicar_template_grafico
from avaliador_b3.app.formatacao import (
    _fmt,
    _fmt_bilhoes,
    _fmt_bilhoes_ou_traco,
    _fmt_percentual,
    _pt_br,
    _rotulo_segmento_setorial,
)
from avaliador_b3.config import (
    AVISO_MACRO_IPCA_FONTE,
    AVISO_MACRO_MESMA_FONTE,
    AVISO_MACRO_SELIC_FONTE,
    COR_ALERTA,
    COR_FUNDO_PAGINA,
    COR_FUNDO_PAINEL,
    COR_NEGATIVO,
    COR_NEUTRO,
    COR_POSITIVO,
    COR_PRINCIPAL,
    COR_TEXTO,
    FOLGA_ROTULO_BARRA,
    FRASE_FONTE_MACRO,
    LARGURA_CARACTERE_ROTULO_BARRA,
    LIMITE_DIVERGENCIA_METODOS_ALTA,
    LIMITE_LIQUIDEZ_CORRENTE_BAIXA,
    LIMITE_SINAL_INDICADOR,
    NOMES_FATORES_CORRELACAO,
    NOMES_METODOS,
    OPACIDADE_BARRA_PARCIAL,
    PADRAO_TICKER_B3,
    ROTULO_ANO_PARCIAL,
    ROTULO_COMBINADO_GRAFICO,
    ROTULO_POTENCIAL,
    ROTULOS_METODOS_GRAFICO,
    TEXTO_AJUDA_LPA_VPA_AJUSTADOS,
    TEXTO_CRESCIMENTO_IPCA,
    TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA,
    TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA,
    TEXTO_DIVERGENCIA_NENHUM_METODO,
    TEXTO_DIVERGENCIA_UM_METODO,
    TEXTO_OBSERVACOES_CORRELACAO,
    TEXTO_SEM_ACOES_EM_CIRCULACAO,
    TEXTO_SEM_AJUSTES_DO_BALANCO,
    TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA,
    TEXTO_SEM_DESCONTO_NAO_CONTROLADORES,
    TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS,
    TOOLTIP_POTENCIAL_COLUNA,
)
from avaliador_b3.correlacao import classificar_magnitude_correlacao
from avaliador_b3.graficos import normalizar_base_100, ticks_mensais_pt_br
from avaliador_b3.ingest.bcb_sgs import ResultadoMacro
from avaliador_b3.numeros import decimal_pt_br


def _widget_avancado_tradingview(ticker: str) -> str | None:
    """HTML do widget "Advanced Chart" do TradingView (embutido via
    st.iframe), símbolo montado dinamicamente a partir do
    ticker buscado na tela — ver
    https://br.tradingview.com/widget/advanced-chart/. Só aceita ticker no formato
    da B3 (`PADRAO_TICKER_B3`); qualquer outro texto devolve `None`, sem HTML. A
    configuração vai como JSON serializado (`json.dumps`), nunca por interpolação.
    Se o JavaScript não carregar (rede/ambiente restrito), o widget só fica em
    branco, sem quebrar o resto da página."""
    if not re.fullmatch(PADRAO_TICKER_B3, ticker):
        return None
    configuracao = json.dumps(
        {
            "autosize": True,
            "symbol": f"BMFBOVESPA:{ticker}",
            "interval": "D",
            "timezone": "America/Sao_Paulo",
            "theme": "dark",
            "style": "1",
            "locale": "br",
            "allow_symbol_change": True,
            "support_host": "https://www.tradingview.com",
        }
    ).replace("<", "\\u003c")
    return f"""
    <style>html, body {{ height: 100%; margin: 0; overflow: hidden; }}</style>
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget"
        style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
        async>
      {configuracao}
      </script>
    </div>
    """


def _figura_dividendos(
    dividendos_por_ano: pd.DataFrame, dividend_yield_por_ano: pd.DataFrame, ano_inicial: int | None
) -> go.Figure:
    """Barras do dividend yield (%) de cada ano, em eixo único; o yield e o total pago (R$/ação)
    ficam no hover. Com `ano_inicial`, mostra só dele em diante e escreve o % sobre cada barra
    (anos sem dividendo ficam sem rótulo); sem ele, o histórico todo, com rótulo só no hover. O
    ano corrente, incompleto, tem barra clara com hachura e asterisco no rótulo do eixo."""
    anos = dividendos_por_ano.merge(dividend_yield_por_ano, on="ano")
    if ano_inicial is not None:
        anos = anos[anos["ano"] >= ano_inicial]
    rotulos_x = [
        ROTULO_ANO_PARCIAL.format(ano=int(ano)) if parcial else str(int(ano))
        for ano, parcial in zip(anos["ano"], anos["parcial"], strict=True)
    ]
    # Formatado em Python: o d3-format do Plotly não tem vírgula decimal sem um locale registrado.
    percentuais = [_fmt_percentual(y) for y in anos["yield_percentual"]]
    totais = list(anos["total"])
    hover = [[pct, _fmt_bilhoes(total)] for pct, total in zip(percentuais, totais, strict=True)]
    rotulos = [pct if total > 0 else "" for pct, total in zip(percentuais, totais, strict=True)]
    figura = go.Figure(
        go.Bar(
            x=rotulos_x,
            y=anos["yield_percentual"],
            text=rotulos,
            textposition="outside" if ano_inicial is not None else "none",
            textfont={"color": COR_TEXTO},
            cliponaxis=False,
            customdata=hover,
            hovertemplate="Dividend Yield: %{customdata[0]}<br>Total pago: %{customdata[1]}"
            "<extra></extra>",
            marker={
                "color": COR_PRINCIPAL,
                "opacity": [OPACIDADE_BARRA_PARCIAL if p else 1.0 for p in anos["parcial"]],
                "line": {"color": COR_PRINCIPAL, "width": 2},
                "pattern": {
                    "shape": ["/" if p else "" for p in anos["parcial"]],
                    "fgcolor": COR_PRINCIPAL,
                    "bgcolor": COR_FUNDO_PAINEL,
                },
            },
        )
    )
    figura.update_layout(
        xaxis={"type": "category"},
        yaxis={"ticksuffix": "%", "rangemode": "tozero"},
        showlegend=False,
        margin={"t": 20, "b": 10, "l": 10, "r": 10},
    )
    figura.update_xaxes(automargin=True)
    figura.update_yaxes(automargin=True)
    return aplicar_template_grafico(figura)


def _grafico_comparacao_normalizada(
    serie_a: pd.DataFrame, nome_a: str, serie_b: pd.DataFrame, nome_b: str
) -> tuple[go.Figure | None, list[str]]:
    """Gráfico de linha com duas séries de preço normalizadas pra base 100
    (`graficos.normalizar_base_100`) — necessário pra sobrepor séries de
    escala bruta muito diferente (ação em R$ dezenas vs. Ibovespa em
    ~130 mil pontos, ou vs. petróleo Brent em US$ dezenas) no mesmo eixo
    sem uma delas virar uma linha reta ilegível. Compartilhado entre
    "Preço vs. Ibovespa" e "Comparando com Petróleo (Brent)", que só
    diferem nas séries/nomes passados.

    Devolve `(figura, nomes_sem_dados)`. `nomes_sem_dados` lista
    `nome_a`/`nome_b` cuja série não teve "base 100" calculável (ver
    `graficos.normalizar_base_100`); `figura` vem `None` sempre que essa
    lista não for vazia — mesmo com a outra série ainda válida, uma
    figura com uma das linhas invisível não é útil sem dizer por quê, e
    quem chama decide a mensagem a partir de `nomes_sem_dados`."""
    normalizado_a = normalizar_base_100(serie_a["Close"])
    normalizado_b = normalizar_base_100(serie_b["Close"])
    nomes_sem_dados = [
        nome
        for nome, normalizado in ((nome_a, normalizado_a), (nome_b, normalizado_b))
        if normalizado.isna().all()
    ]
    if nomes_sem_dados:
        return None, nomes_sem_dados

    figura = go.Figure()
    figura.add_trace(
        go.Scatter(
            x=serie_a["data"],
            y=normalizado_a,
            name=nome_a,
            line={"color": COR_PRINCIPAL},
        )
    )
    figura.add_trace(
        go.Scatter(
            x=serie_b["data"],
            y=normalizado_b,
            name=nome_b,
            line={"color": COR_NEUTRO},
        )
    )
    figura.update_layout(
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "top", "y": -0.12, "xanchor": "left", "x": 0},
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
    )
    aplicar_template_grafico(figura)
    tickvals, ticktext = ticks_mensais_pt_br(serie_a["data"])
    figura.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
    # Margem esquerda pequena: o eixo Y cresce sozinho para caber os números.
    figura.update_yaxes(automargin=True)
    return figura, []


def _mensagem_grafico_comparacao_sem_dados(nomes_sem_dados: list[str]) -> str:
    """Mensagem mostrada no lugar do gráfico quando `_grafico_comparacao_
    normalizada` devolve `figura=None` — nomeia a série sem dados quando
    só uma falhou, pra não esconder que a outra está ok."""
    if len(nomes_sem_dados) == 1:
        return f"Sem dados suficientes de {nomes_sem_dados[0]} para montar este gráfico."
    return "Sem dados suficientes para montar este gráfico."


def _delta_percentual_upside(valor: float, preco_atual: float | None) -> str | None:
    """Diferença percentual entre `valor` (valor justo de um método) e o
    preço atual — (valor - preco_atual) / preco_atual × 100, pro
    parâmetro `delta` do st.metric. Cor padrão do Streamlit, SEM inverter
    (`delta_color="normal"`, o default): aqui valor justo maior que o
    preço é upside, sinal bom = verde — diferente de outros deltas do
    projeto onde "maior é pior" e por isso usam `delta_color="inverse"`.

    `None` (sem delta nenhum, não um "0%" inventado) quando `preco_atual`
    não está disponível — st.metric já trata `delta=None` como "não
    mostrar o indicador"."""
    if preco_atual is None:
        return None
    return _fmt_percentual((valor - preco_atual) / preco_atual * 100)


def _kpi_divergencia(divergencia: dict, valores_por_metodo: dict[str, float]) -> dict:
    """Conteúdo do cartão de divergência entre métodos: o número é o
    `divergencia_percentual` de `calcular_divergencia_metodos`, em amarelo a partir de
    `LIMITE_DIVERGENCIA_METODOS_ALTA`; a linha pequena traz o menor e o maior valor justo
    com o nome do método. Sem divergência calculável, "—" e o motivo."""
    if not divergencia["aplicavel"]:
        texto = (
            TEXTO_DIVERGENCIA_UM_METODO
            if len(valores_por_metodo) == 1
            else TEXTO_DIVERGENCIA_NENHUM_METODO
        )
        return {"valor": "—", "classe_cor": "ab-cor-secundario", "linha": texto}
    ordenados = sorted(valores_por_metodo.items(), key=lambda item: item[1])
    menor, maior = ordenados[0], ordenados[-1]
    linha = " · ".join(
        f"{NOMES_METODOS.get(nome, nome)} {_fmt_bilhoes(valor)}" for nome, valor in (menor, maior)
    )
    percentual = divergencia["divergencia_percentual"]
    if percentual is None:
        return {"valor": "—", "classe_cor": "ab-cor-texto", "linha": linha}
    alta = percentual / 100 >= LIMITE_DIVERGENCIA_METODOS_ALTA
    return {
        "valor": f"{percentual:.0f}%",
        "classe_cor": "ab-cor-alerta" if alta else "ab-cor-texto",
        "linha": linha,
    }


def _html_pilulas(segmento_setorial: str | None, segmento_listagem: str | None) -> str:
    """Pílulas com o segmento setorial e o de listagem; só as que existem. Vazio sem nenhuma."""
    segmento_setorial = _rotulo_segmento_setorial(segmento_setorial)
    pilulas = [
        f'<span class="ab-pilula" title="{escape(titulo)}">{escape(texto)}</span>'
        for titulo, texto in (
            ("Segmento setorial (B3)", segmento_setorial),
            ("Segmento de listagem", segmento_listagem),
        )
        if texto
    ]
    return f'<div class="ab-pilulas">{"".join(pilulas)}</div>' if pilulas else ""


def _notas_do_metodo(resultado: dict) -> tuple[list[str], list[str]]:
    """Legendas de um método aplicável (Graham/Bazin/FCD), em duas listas: as que ficam à
    vista (hoje só o aviso de dívida líquida indisponível, que muda a leitura do valor) e as
    de detalhe, que vão para o expander. `resultado` é o dict padrão dos três modelos.

    `resultado.get("divida_liquida_deduzida")` só existe no dict do FCD (ver modelos/fcd.py):
    `False` significa que o valor não teve a dívida líquida deduzida (dado ausente pra essa
    empresa; banco nunca chega aqui, já é "não aplicável" antes, ver
    config.SEGMENTOS_FCD_NAO_APLICAVEL)."""
    visiveis: list[str] = []
    detalhes: list[str] = []
    if resultado.get("divida_liquida_deduzida") is False:
        visiveis.append(
            "Dívida líquida indisponível para essa empresa — sem ela para "
            "deduzir, este valor não desconta a dívida da empresa, então "
            "tende a ficar mais alto do que se a dedução fosse possível."
        )
    # Sem balanço da CVM, os três ajustes que dependem dele ficam de fora pelo mesmo
    # motivo: uma legenda só, em vez de três iguais.
    motivo_sem_nao_controladores = resultado.get("motivo_sem_nao_controladores")
    motivo_sem_arrendamento = resultado.get("motivo_sem_arrendamento")
    motivo_sem_patrimonio_total = resultado.get("motivo_sem_patrimonio_total")
    motivos_do_balanco = {
        motivo_sem_nao_controladores,
        motivo_sem_arrendamento,
        motivo_sem_patrimonio_total,
    }
    balanco_inteiro_indisponivel = len(motivos_do_balanco) == 1 and None not in motivos_do_balanco
    if balanco_inteiro_indisponivel:
        detalhes.append(TEXTO_SEM_AJUSTES_DO_BALANCO.format(motivo=motivo_sem_nao_controladores))
    elif motivo_sem_nao_controladores:
        detalhes.append(
            TEXTO_SEM_DESCONTO_NAO_CONTROLADORES.format(motivo=motivo_sem_nao_controladores)
        )
    motivo_sem_acoes = resultado.get("motivo_sem_acoes_em_circulacao")
    if motivo_sem_acoes:
        detalhes.append(TEXTO_SEM_ACOES_EM_CIRCULACAO.format(motivo=motivo_sem_acoes))
    if motivo_sem_arrendamento and not balanco_inteiro_indisponivel:
        detalhes.append(TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA.format(motivo=motivo_sem_arrendamento))
    if motivo_sem_patrimonio_total and not balanco_inteiro_indisponivel:
        detalhes.append(
            TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS.format(motivo=motivo_sem_patrimonio_total)
        )
    motivo_crescimento_ipca = resultado.get("motivo_crescimento_ipca")
    if motivo_crescimento_ipca:
        detalhes.append(TEXTO_CRESCIMENTO_IPCA.format(motivo=motivo_crescimento_ipca))
    if resultado.get("crescimento_limitado_pela_receita"):
        detalhes.append(
            TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA.format(
                taxa=_fmt_percentual(resultado["taxa_crescimento_receita"] * 100, 1)
            )
        )
    elif resultado.get("motivo_sem_limite_da_receita"):
        detalhes.append(
            TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA.format(
                motivo=resultado["motivo_sem_limite_da_receita"]
            )
        )
    return visiveis, detalhes


def _rotulo_barra_valor_justo(valor: float, preco_atual: float | None) -> str:
    """Rótulo da barra: o valor e, havendo preço, a diferença para ele ("93,22  +60,7%")."""
    texto = _pt_br(f"{valor:,.2f}")
    if preco_atual is None:
        return texto
    diferenca = (valor - preco_atual) / preco_atual * 100
    sinal = "+" if diferenca > 0 else ""
    return f"{texto}\u00a0\u00a0{sinal}{_fmt_percentual(diferenca)}"


def _figura_valor_justo(
    valores_por_metodo: dict[str, float], valor_combinado: float, preco_atual: float | None
) -> go.Figure:
    """Barras horizontais do valor de cada método aplicável e do combinado, com o preço atual
    numa linha tracejada. Verde acima do preço, rosa abaixo; o combinado em ciano; sem preço,
    barras neutras e sem linha."""
    rotulos = [ROTULOS_METODOS_GRAFICO.get(nome, nome) for nome in valores_por_metodo]
    valores = [*valores_por_metodo.values(), valor_combinado]
    rotulos.append(ROTULO_COMBINADO_GRAFICO)

    def cor_da_barra(valor: float) -> str:
        if preco_atual is None:
            return COR_NEUTRO
        return COR_POSITIVO if valor >= preco_atual else COR_NEGATIVO

    cores = [cor_da_barra(valor) for valor in valores[:-1]] + [COR_PRINCIPAL]
    figura = go.Figure(
        go.Bar(
            x=valores,
            y=rotulos,
            orientation="h",
            marker={"color": cores},
            text=[_rotulo_barra_valor_justo(valor, preco_atual) for valor in valores],
            textposition="none",
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    extremos = [0.0, *valores] + ([preco_atual] if preco_atual is not None else [])
    menor, maior = min(extremos), max(extremos)
    amplitude = (maior - menor) or 1.0
    figura.update_xaxes(
        range=[menor - 0.1 * amplitude if menor < 0 else 0, maior + 0.4 * amplitude],
        showticklabels=False,
    )
    limite_x = maior + 0.4 * amplitude
    fora_da_barra = []
    for rotulo, valor, texto in zip(rotulos, valores, figura.data[0].text, strict=True):
        # O valor vai numa anotação com fundo, que cobre a linha do preço quando ela passa por trás.
        figura.add_annotation(
            x=valor,
            y=rotulo,
            text=texto,
            showarrow=False,
            xanchor="left",
            xshift=6,
            bgcolor=COR_FUNDO_PAINEL,
            borderpad=2,
            font={"color": COR_TEXTO},
        )
        largura_necessaria = len(rotulo) * LARGURA_CARACTERE_ROTULO_BARRA + FOLGA_ROTULO_BARRA
        if valor > 0 and valor / limite_x >= largura_necessaria:
            figura.add_annotation(
                x=0,
                y=rotulo,
                text=f"<b>{rotulo}</b>",
                showarrow=False,
                xanchor="left",
                xshift=6,
                font={"color": COR_FUNDO_PAGINA},
            )
        else:
            fora_da_barra.append(rotulo)
    # Nome dentro da barra; o que não cabe fica no eixo, à esquerda (a margem acompanha).
    figura.update_yaxes(
        autorange="reversed",
        tickmode="array",
        tickvals=fora_da_barra,
        ticktext=fora_da_barra,
        showticklabels=bool(fora_da_barra),
        automargin=True,
    )
    if preco_atual is not None:
        figura.add_vline(
            x=preco_atual,
            line_dash="dash",
            line_color=COR_ALERTA,
            annotation_text=f"Preço {_fmt_bilhoes(preco_atual)}",
            annotation_position="top",
            annotation_font_color=COR_ALERTA,
        )
    figura.update_layout(
        height=70 + 46 * len(valores), margin={"t": 36, "b": 10, "l": 10, "r": 10}, showlegend=False
    )
    return aplicar_template_grafico(figura)


def _cor_indicador(valor: float | None, regra: str) -> str:
    """Classe de cor de um indicador da Saúde financeira: `"sinal"` (verde acima de zero, rosa
    abaixo), `"queda"` (rosa abaixo de zero) ou `"liquidez"` (amarelo abaixo do limite). Sem
    cor para zero, dado ausente ou fora dessas regras."""
    if valor is None or pd.isna(valor):
        return "ab-cor-texto"
    if regra == "liquidez":
        return "ab-cor-alerta" if valor < LIMITE_LIQUIDEZ_CORRENTE_BAIXA else "ab-cor-texto"
    if valor < LIMITE_SINAL_INDICADOR:
        return "ab-cor-negativo"
    if valor > LIMITE_SINAL_INDICADOR and regra == "sinal":
        return "ab-cor-positivo"
    return "ab-cor-texto"


def _html_indicador(
    rotulo: str, valor: str, classe_cor: str = "ab-cor-texto", ajuda: str = ""
) -> str:
    """Um indicador da grade: rótulo pequeno e valor monoespaçado; `ajuda` vira o "?" do rótulo."""
    marca_ajuda = f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span>' if ajuda else ""
    return (
        f'<div class="ab-ind"><span class="ab-ind-rotulo">{escape(rotulo)}{marca_ajuda}</span>'
        f'<span class="ab-ind-valor {classe_cor}">{escape(valor)}</span></div>'
    )


def _html_linha_correlacao(nome: str, resultado: dict, ultimo_gpr: str | None) -> str:
    """Linha de um fator: nome com "?" (observações, data do GPR ou motivo), mini barra de -1 a
    +1 (do centro para a direita se positiva, para a esquerda se negativa), valor e leitura de
    magnitude (`correlacao.classificar_magnitude_correlacao`); sem dado, "—"."""
    if not resultado["aplicavel"]:
        ajuda = f"Indisponível: {resultado['motivo_nao_aplicavel']}"
        trilho = '<span class="ab-div-trilho"></span>'
        valor, classe = "—", ""
    else:
        coeficiente = resultado["correlacao"]
        ajuda = TEXTO_OBSERVACOES_CORRELACAO.format(observacoes=resultado["observacoes"])
        lado = "ab-corr-pos" if coeficiente >= 0 else "ab-corr-neg"
        largura = min(abs(coeficiente), 1.0) * 50
        trilho = (
            '<span class="ab-div-trilho">'
            f'<i class="ab-div-barra {lado}" style="width:{largura:.1f}%"></i></span>'
        )
        valor = _fmt(coeficiente)
        classe = classificar_magnitude_correlacao(coeficiente)
    if ultimo_gpr:
        ajuda += f" · {ultimo_gpr}"
    return (
        '<div class="ab-corr">'
        f'<span class="ab-corr-nome">{escape(nome)}'
        f'<span class="ab-ajuda" title="{escape(ajuda)}">?</span></span>'
        f'{trilho}<span class="ab-div-valor">{escape(valor)}</span>'
        f'<span class="ab-corr-classe">{escape(classe)}</span></div>'
    )


def _ajuda_lpa_vpa_ajustados(
    lpa: float | None,
    vpa: float | None,
    lpa_graham: float | None,
    vpa_graham: float | None,
) -> dict[str, str]:
    """Nota do "?" de LPA e de VPA: o Graham usa os dois reescalados para as ações em circulação;
    a nota só aparece no indicador cujo valor ajustado, em 2 casas, difere do mostrado."""
    if lpa_graham is None or vpa_graham is None:
        return {"lpa": "", "vpa": ""}
    nota = TEXTO_AJUDA_LPA_VPA_AJUSTADOS.format(
        lpa=decimal_pt_br(lpa_graham), vpa=decimal_pt_br(vpa_graham)
    )

    def diferente(mostrado: float | None, ajustado: float) -> bool:
        return mostrado is not None and round(mostrado, 2) != round(ajustado, 2)

    return {
        "lpa": nota if diferente(lpa, lpa_graham) else "",
        "vpa": nota if diferente(vpa, vpa_graham) else "",
    }


def _html_correlacoes(resultados: dict, ultimo_gpr: str | None) -> str:
    """As linhas dos três fatores; `ultimo_gpr` (data já formatada) entra na dica do GPR."""
    return "".join(
        _html_linha_correlacao(nome, resultados[chave], ultimo_gpr if chave == "gpr" else None)
        for chave, nome in NOMES_FATORES_CORRELACAO.items()
    )


def _html_tabela_setorial(tabela: pd.DataFrame, ticker_destacado: str) -> str:
    """Tabela da comparação setorial (ticker, preço, valor combinado e potencial com barra
    divergente); a linha de `ticker_destacado` fica em destaque."""
    linhas = []
    for linha in tabela.itertuples():
        classe = ' class="ab-linha-destaque"' if linha.ticker == ticker_destacado else ""
        linhas.append(
            f"<tr{classe}><td>{escape(str(linha.ticker))}</td>"
            f'<td class="ab-num">{escape(_fmt_bilhoes_ou_traco(linha.preco_atual))}</td>'
            f'<td class="ab-num">{escape(_fmt_bilhoes_ou_traco(linha.valor_combinado))}</td>'
            f"<td>{_html_barra_potencial(linha.desconto_percentual)}</td></tr>"
        )
    ajuda = f'<span class="ab-ajuda" title="{escape(TOOLTIP_POTENCIAL_COLUNA)}">?</span>'
    # Com uma linha só, a tabela não estica até a altura do painel.
    curta = " ab-tabela-curta" if len(tabela) == 1 else ""
    return (
        f'<div class="ab-tabela-caixa{curta}"><table class="ab-tabela"><thead><tr>'
        '<th>Ticker</th><th class="ab-num">Preço atual</th>'
        '<th class="ab-num">Valor combinado</th>'
        f"<th>{escape(ROTULO_POTENCIAL)}{ajuda}</th></tr></thead>"
        f"<tbody>{''.join(linhas)}</tbody></table></div>"
    )


def _aviso_fonte_macro(macro: ResultadoMacro) -> str:
    """Texto sobre a origem da Selic e do IPCA quando algum veio de fonte que não é a API
    REST do Banco Central; vazio quando ambos vieram dela (ou de valor guardado)."""
    if macro.usou_valor_guardado:
        return ""
    frase_selic = FRASE_FONTE_MACRO.get(macro.fonte_selic)
    frase_ipca = FRASE_FONTE_MACRO.get(macro.fonte_ipca)
    if frase_selic and frase_selic == frase_ipca:
        return AVISO_MACRO_MESMA_FONTE.format(frase=frase_selic)
    partes = []
    if frase_selic:
        partes.append(AVISO_MACRO_SELIC_FONTE.format(frase=frase_selic))
    if frase_ipca:
        partes.append(AVISO_MACRO_IPCA_FONTE.format(frase=frase_ipca))
    return " ".join(partes)
