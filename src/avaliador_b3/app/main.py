"""Dashboard (Streamlit) do Avaliador de Ações da B3 — valor justo das ações do
Ibovespa por Graham, Bazin e fluxo de caixa descontado, com o valor combinado
e o simulador de carteira em três cenários (pessimista/base/otimista). Só chama
os adapters/modelos que já existem e organiza o resultado na tela; nenhuma lógica
de cálculo é reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import json
import re
import sys
import warnings
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

# O projeto não está instalado como pacote (sem pyproject [project]/pip
# install -e . ainda) — `streamlit run` não adiciona src/ ao sys.path
# sozinho como o pytest faz via pythonpath, então isso resolve na mão.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app.componentes import (
    _html_barra_potencial,
    _html_cabecalho_painel,
    _html_kpi,
    _tabela_formatada_pt_br,
    _titulo_painel,
    aplicar_template_grafico,
    exibir_grafico,
)
from avaliador_b3.app.css import (
    _CSS_DA_PAGINA,
)
from avaliador_b3.app.dados import (
    _buscar_ano_fcd_mais_recente,
    _buscar_cambio_correlacao,
    _buscar_cnpj,
    _buscar_dividendos,
    _buscar_fcf_fcd,
    _buscar_gpr_diaria,
    _buscar_historico,
    _buscar_historico_ibovespa,
    _buscar_historico_petroleo,
    _buscar_indicadores_fundamentus,
    _buscar_leitura_balanco,
    _buscar_macro,
    _buscar_segmento_setorial,
    _buscar_serie_bcb,
    _buscar_universo_ibovespa,
    _carregar_screener_ou_avisar,
    _data_da_ultima_rodada,
    _rodar_screener_permitido,
    _texto_screener_atualizado_pelo_workflow,
)
from avaliador_b3.app.formatacao import (
    _acoes_por_extenso,
    _fmt,
    _fmt_bilhoes,
    _fmt_bilhoes_md,
    _fmt_bilhoes_ou_traco,
    _fmt_data,
    _fmt_percentual,
    _fmt_potencial,
    _fmt_quantidade,
    _lista_em_texto,
    _nomes_dos_metodos,
    _nomes_dos_metodos_do_csv,
    _percentual_ou_traco,
    _pt_br,
    _rotulo_segmento_setorial,
    _texto_potencial_minimo,
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
    ANOS_JANELA_CORRELACAO,
    ANOS_JANELA_DIVIDENDOS,
    AVISO_MACRO_ARQUIVO_REFERENCIA,
    AVISO_MACRO_IPCA_FONTE,
    AVISO_MACRO_MESMA_FONTE,
    AVISO_MACRO_SELIC_FONTE,
    AVISO_PRECO_INDISPONIVEL,
    AVISO_SIMULADOR_SEM_PREVISAO,
    CHAVE_BARRA_ANALISAR,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_BARRA_RODAPE,
    CHAVE_BARRA_SCREENER,
    CHAVE_CARTEIRA_ACAO,
    CHAVE_CARTEIRA_POSICOES,
    CHAVE_CARTEIRA_QUANTIDADE,
    CHAVE_CARTEIRA_REMOVER_PREFIXO,
    CHAVE_DROPDOWN_TICKER,
    CHAVE_FILTRO_ESCONDER_SEM_COMBINADO,
    CHAVE_FILTRO_METODO_PREFIXO,
    CHAVE_FILTRO_POTENCIAL_MINIMO,
    CHAVE_FILTRO_SETOR,
    CHAVE_FILTROS_GUARDADOS,
    CHAVE_PERIODO_HISTORICO_CARTEIRA,
    CHAVE_RODAR_SCREENER_SOLICITADO,
    CHAVE_TEXTO_TICKER,
    CHAVE_TICKER_GUARDADO,
    COR_ALERTA,
    COR_FUNDO_PAGINA,
    COR_FUNDO_PAINEL,
    COR_NEGATIVO,
    COR_NEUTRO,
    COR_POSITIVO,
    COR_PRINCIPAL,
    COR_TEXTO,
    COR_TEXTO_SECUNDARIO,
    CORES_ACOES_CARTEIRA,
    DESCRICOES_DAS_PAGINAS,
    FAIXA_POTENCIAL_LARGURA,
    FAIXA_POTENCIAL_LIMITE,
    FOLGA_ROTULO_BARRA,
    FOLGA_TOPO_HISTOGRAMA,
    FRACAO_ROTULO_BARRA_HISTOGRAMA,
    FRASE_FONTE_MACRO,
    FRASE_RESUMO_SIMULADOR,
    ICONE_PAGINA_ANALISAR,
    ICONE_PAGINA_CARTEIRA,
    ICONE_PAGINA_SCREENER,
    JANELA_PADRAO_HISTORICO_CARTEIRA,
    JANELAS_COMPARACAO_PETROLEO,
    JANELAS_HISTORICO_CARTEIRA,
    LARGURA_CARACTERE_ROTULO_BARRA,
    LARGURA_COLUNA_OBSERVACAO_RANKING,
    LARGURA_MARGEM_COLUNA_SETOR,
    LARGURA_PX_POR_CARACTERE_COLUNA_SETOR,
    LEGENDA_REINVESTIMENTO_CAPEX,
    LIMITE_CARACTERES_OBSERVACAO_RANKING,
    LIMITE_CONCENTRACAO_SETOR_PERCENTUAL,
    LIMITE_DIVERGENCIA_METODOS_ALTA,
    LIMITE_LIQUIDEZ_CORRENTE_BAIXA,
    LIMITE_ROTULO_INVESTIDO_DIREITA,
    LIMITE_ROTULO_INVESTIDO_ESQUERDA,
    LIMITE_SINAL_INDICADOR,
    MARCA_FCD_DEDUCOES_NA_TABELA,
    MENSAGEM_TRADINGVIEW_TICKER_INVALIDO,
    MOTIVOS_FCD_NAO_APLICAVEL_POR_SETOR,
    NOME_LINHA_CARTEIRA,
    NOME_LINHA_CDI,
    NOME_LINHA_IPCA,
    NOMES_FATORES_CORRELACAO,
    NOMES_METODOS,
    NOTA_DIVIDEND_YIELD_SUBESTIMADO,
    NOTA_DIVIDENDOS_ANO_PARCIAL,
    OPACIDADE_BARRA_PARCIAL,
    OPCAO_TODOS_OS_SETORES,
    PADRAO_TICKER_B3,
    PARAMETRO_URL_ACAO,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    PERIODO_PRECO_ATUAL,
    PESO_MINIMO_TEXTO_NA_FATIA,
    POTENCIAL_MINIMO_FILTRO_DESLIGADO,
    POTENCIAL_MINIMO_FILTRO_MAXIMO,
    POTENCIAL_MINIMO_FILTRO_PASSO,
    PREFIXO_FONTE_ARQUIVO_REFERENCIA,
    PROPORCAO_CABECALHO_ANALISE,
    QUANTIDADE_PADRAO_CARTEIRA,
    RAZAO_DIVIDENDOS_ATIPICA_BAZIN,
    ROTULO_ADICIONAR_A_CARTEIRA,
    ROTULO_ANO_PARCIAL,
    ROTULO_CARTEIRA_ACAO,
    ROTULO_CARTEIRA_QUANTIDADE,
    ROTULO_COLUNAS_RANKING_SCREENER,
    ROTULO_COMBINADO_GRAFICO,
    ROTULO_FILTRO_ESCONDER_SEM_COMBINADO,
    ROTULO_FILTRO_METODOS,
    ROTULO_FILTRO_POTENCIAL_MINIMO,
    ROTULO_FILTRO_SETOR,
    ROTULO_JANELA_DIVIDENDOS_COMPLETA,
    ROTULO_JANELA_DIVIDENDOS_CURTA,
    ROTULO_KPI_ABAIXO_DO_VALOR_JUSTO,
    ROTULO_KPI_COM_COMBINADO,
    ROTULO_KPI_COM_FCD,
    ROTULO_KPI_CONCENTRACAO,
    ROTULO_KPI_MEDIANA_POTENCIAL,
    ROTULO_KPI_POTENCIAL_CARTEIRA,
    ROTULO_KPI_VALOR_INVESTIDO,
    ROTULO_KPI_VALOR_JUSTO_CARTEIRA,
    ROTULO_LIMPAR_CARTEIRA,
    ROTULO_LIMPAR_FILTROS,
    ROTULO_POTENCIAL,
    ROTULO_REMOVER_POSICAO,
    ROTULO_RODAR_SCREENER,
    ROTULO_SELETOR_PERIODO_HISTORICO,
    ROTULOS_CENARIOS_CARTEIRA,
    ROTULOS_COLUNAS_POSICOES,
    ROTULOS_COMPONENTES_VALOR_FIRMA,
    ROTULOS_METODOS_GRAFICO,
    SEPARADOR_OBSERVACAO_RANKING,
    SUFIXO_BARRA_ATIVA,
    TEXTO_ABERTURA_SIMULADOR,
    TEXTO_ACAO_DA_URL_INVALIDA,
    TEXTO_AJUDA_CORRELACAO,
    TEXTO_AJUDA_INDICADORES_AUSENTES,
    TEXTO_AJUDA_LPA_VPA_AJUSTADOS,
    TEXTO_AJUDA_POTENCIAL_DO_TOTAL,
    TEXTO_AJUDA_RANKING_SCREENER,
    TEXTO_AJUDA_TRADINGVIEW,
    TEXTO_AVISO_ESTIMATIVAS,
    TEXTO_AVISO_FORA_DO_SCREENER,
    TEXTO_BUSCANDO_HISTORICO,
    TEXTO_CARTAO_SEM_METODO,
    TEXTO_CARTEIRA_ACAO_PLACEHOLDER,
    TEXTO_CARTEIRA_VAZIA,
    TEXTO_CENARIO_LIMITADO_SINGULAR,
    TEXTO_CENARIOS_LIMITADOS_PLURAL,
    TEXTO_COMPLEMENTO_SEM_METODO,
    TEXTO_CORTE_DA_OBSERVACAO,
    TEXTO_CRESCIMENTO_IPCA,
    TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA,
    TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA,
    TEXTO_DEMAIS_ACOES_NA_CARTEIRA,
    TEXTO_DESMARQUE_OPCAO,
    TEXTO_DESMARQUE_QUALQUER,
    TEXTO_DESMARQUE_UM,
    TEXTO_DESMARQUE_VARIOS,
    TEXTO_DIVERGENCIA_NENHUM_METODO,
    TEXTO_DIVERGENCIA_UM_METODO,
    TEXTO_EXPANDER_SIMULADOR,
    TEXTO_FAIXA_ACIMA_DO_LIMITE,
    TEXTO_FCD_AJUSTES_DO_BALANCO,
    TEXTO_FCD_NAO_APLICAVEL_NA_TABELA,
    TEXTO_FCD_NAO_APLICAVEL_RESUMIDO,
    TEXTO_FIRMA_SEM_COMPONENTES,
    TEXTO_FORA_DA_LINHA_CARTEIRA,
    TEXTO_INVESTIDO_NO_CENTRO,
    TEXTO_KPI_ABAIXO_DO_VALOR_JUSTO,
    TEXTO_KPI_COM_COMBINADO,
    TEXTO_KPI_COM_FCD,
    TEXTO_KPI_POSICAO_SINGULAR,
    TEXTO_KPI_POSICOES,
    TEXTO_KPI_SEM_COMBINADO,
    TEXTO_KPI_SEM_METODO,
    TEXTO_KPI_SOBRE_COM_COMBINADO,
    TEXTO_LEGENDA_DATA_SCREENER_SETORIAL,
    TEXTO_LEGENDA_FILTRO_METODOS,
    TEXTO_LINHA_INVESTIDO_NO_GRAFICO,
    TEXTO_LINK_ACAO_REGEX,
    TEXTO_MAIS_DE_METADE_NUM_SETOR,
    TEXTO_MEDIANA_NO_GRAFICO,
    TEXTO_MOSTRANDO_ACOES,
    TEXTO_NENHUM_ALERTA,
    TEXTO_NENHUM_HISTORICO_DA_CARTEIRA,
    TEXTO_NENHUM_METODO_NA_TABELA,
    TEXTO_NENHUM_METODO_SE_APLICA,
    TEXTO_NENHUMA_ACAO_COM_CENARIO,
    TEXTO_NENHUMA_ACAO_NOS_FILTROS,
    TEXTO_OBSERVACOES_CORRELACAO,
    TEXTO_OUTRAS_ACOES,
    TEXTO_POSICAO_DA_CARTEIRA,
    TEXTO_POSICAO_FORA_DO_SCREENER,
    TEXTO_POSICAO_SEM_COMBINADO,
    TEXTO_RISCO_SACADO_RECLASSIFICADO,
    TEXTO_RODADA_DESCARTADA,
    TEXTO_RODAPE_APP_DORMINDO,
    TEXTO_RODAPE_LINK_REPOSITORIO,
    TEXTO_RODAPE_SCREENER_ATUALIZADO,
    TEXTO_RODAPE_SCREENER_SEM_DATA,
    TEXTO_RODAPE_SELIC,
    TEXTO_SCREENER_CONCLUIDO,
    TEXTO_SCREENER_CONCLUIDO_COM_FALHAS,
    TEXTO_SCREENER_SEM_SEGMENTO_SETORIAL,
    TEXTO_SELECIONE_PERIODO_HISTORICO,
    TEXTO_SEM_ACAO_METODO,
    TEXTO_SEM_ACAO_METODO_NO_SETOR,
    TEXTO_SEM_ACAO_TODOS_OS_METODOS,
    TEXTO_SEM_ACAO_TODOS_OS_METODOS_LISTADOS,
    TEXTO_SEM_ACOES_EM_CIRCULACAO,
    TEXTO_SEM_AJUSTES_DO_BALANCO,
    TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA,
    TEXTO_SEM_CENARIO_PLURAL,
    TEXTO_SEM_CENARIO_SINGULAR,
    TEXTO_SEM_CONTRIBUICAO,
    TEXTO_SEM_DADO_NA_TABELA,
    TEXTO_SEM_DESCONTO_NAO_CONTROLADORES,
    TEXTO_SEM_HISTORICO_DE_PRECOS,
    TEXTO_SEM_OUTRA_ACAO_NO_SEGMENTO,
    TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS,
    TEXTO_SEM_POTENCIAL_PARA_O_GRAFICO,
    TEXTO_SETOR_APOS_PROXIMA_ATUALIZACAO,
    TEXTO_TOTAL_DAS_POSICOES,
    TEXTO_ULTIMO_DADO_GPR,
    TEXTOS_CURTOS_AVISO_DESCONTO_EXTREMO,
    TITULO_ABA_NAVEGADOR,
    TITULO_APP,
    TITULO_ATENCAO,
    TITULO_CARTAO_SEM_METODO,
    TITULO_CENARIOS_CARTEIRA,
    TITULO_COMPOSICAO_ACAO,
    TITULO_COMPOSICAO_SETOR,
    TITULO_CONTRIBUICAO_CARTEIRA,
    TITULO_DISTRIBUICAO_POTENCIAL,
    TITULO_EIXO_POTENCIAL,
    TITULO_EXPANDER_CENARIOS_POR_ACAO,
    TITULO_EXPANDER_SIMULADOR,
    TITULO_HISTORICO_CARTEIRA,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    TITULO_PAINEL_DIVIDENDOS,
    TITULO_POSICOES,
    TITULO_RANKING_SCREENER,
    TOLERANCIA_INICIO_HISTORICO_DIAS,
    TOOLTIP_COMPOSICAO_ACAO,
    TOOLTIP_COMPOSICAO_SETOR,
    TOOLTIP_CONCENTRACAO,
    TOOLTIP_CONTRIBUICAO_CARTEIRA,
    TOOLTIP_DISTRIBUICAO_POTENCIAL,
    TOOLTIP_DIVERGENCIA_METODOS,
    TOOLTIP_HISTORICO_CARTEIRA,
    TOOLTIP_MEDIANA_POTENCIAL,
    TOOLTIP_POSICOES,
    TOOLTIP_POTENCIAL_CARTAO,
    TOOLTIP_POTENCIAL_CARTEIRA,
    TOOLTIP_POTENCIAL_CENARIO,
    TOOLTIP_POTENCIAL_COLUNA,
    TOOLTIP_VALOR_FIRMA,
    TOOLTIP_VALOR_JUSTO_CARTEIRA,
    URL_LINK_ACAO,
    URL_PAGINA_ANALISAR,
    URL_PAGINA_CARTEIRA,
    URL_PAGINA_SCREENER,
    URL_REPOSITORIO,
    YIELD_MINIMO_BAZIN,
)
from avaliador_b3.correlacao import calcular_correlacoes_fatores, classificar_magnitude_correlacao
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
from avaliador_b3.empresa.valor_mercado import calcular_valor_mercado_e_firma
from avaliador_b3.graficos import (
    agregar_dividendos_por_ano,
    calcular_dividend_yield_por_ano,
    normalizar_base_100,
    ticks_mensais_pt_br,
)
from avaliador_b3.historico_carteira import (
    HistoricoDaCarteira,
    montar_historico,
    serie_cdi,
    serie_ipca,
)
from avaliador_b3.ingest import (
    bcb_sgs,
)
from avaliador_b3.ingest.bcb_sgs import (
    ResultadoMacro,
)
from avaliador_b3.ingest.precos import (
    preco_valido,
)
from avaliador_b3.modelos.aviso_fcd import avaliar_fcd_extremo
from avaliador_b3.modelos.bazin import calcular_preco_teto_bazin
from avaliador_b3.modelos.combinado import (
    calcular_divergencia_metodos,
    calcular_valor_combinado,
    linhas_motivos_metodos,
)
from avaliador_b3.modelos.fcd import (
    calcular_proporcao_capex_caixa_operacional_percentual,
    calcular_valor_justo_fcd,
    montar_ajustes_balanco,
    montar_fluxos_fcd,
)
from avaliador_b3.modelos.graham import calcular_valor_justo_graham, reescalar_lpa_vpa
from avaliador_b3.numeros import decimal_pt_br, numero_finito
from avaliador_b3.screener import (
    DeteccaoAnoCvmFalhouWarning,
    FundamentusIndisponivelWarning,
    MacroIndisponivelWarning,
    RodadaScreenerRejeitada,
)

MENSAGEM_MACRO_INDISPONIVEL_CURTA = "Selic/IPCA indisponíveis agora — veja o aviso no topo."

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


# Ticker pré-selecionado e buscado automaticamente só na primeira abertura da
# sessão (ver `busca_inicial_automatica_feita` em session_state, mais abaixo)
# — mostra um resultado de exemplo de cara, sem exigir clique em "Buscar".
TICKER_PADRAO_PRIMEIRA_ABERTURA = "PETR4"


def _ler_acao_da_url() -> str | None:
    """Ticker do parâmetro `?acao=` do endereço, em maiúsculas e sem espaços (o parâmetro é
    retirado da URL); `None` se não houver o parâmetro."""
    if PARAMETRO_URL_ACAO not in st.query_params:
        return None
    acao = st.query_params[PARAMETRO_URL_ACAO]
    del st.query_params[PARAMETRO_URL_ACAO]
    return acao.strip().upper()


def _acao_da_url_e_valida(acao: str, opcoes_validas: set[str] | None) -> bool:
    """Com a lista do Ibovespa, só vale ticker dela; sem a lista, vale o formato de ticker da
    B3."""
    if opcoes_validas is not None:
        return acao in opcoes_validas
    return re.fullmatch(PADRAO_TICKER_B3, acao) is not None


def _acao_da_url_para_exibir(acao: str) -> str:
    """O pedido da URL para a mensagem de erro: só letras e números, no máximo 12, para o texto
    do endereço nunca virar formatação na tela."""
    limpo = re.sub(r"[^A-Z0-9]", "", acao)[:12]
    return f"“{limpo}”" if limpo else "pedida"


def pagina_analisar() -> None:
    # Buscado aqui em cima (não só depois de "Buscar") porque o dropdown
    # abaixo precisa da lista de opções pra se desenhar — reaproveitado
    # mais adiante na seção "Governança", não buscado de novo lá.
    universo_ibovespa, erro_universo = _buscar_universo_ibovespa()
    usando_dropdown = not (erro_universo or universo_ibovespa is None or universo_ibovespa.empty)

    busca_inicial_ja_feita = st.session_state.get("busca_inicial_automatica_feita", False)

    # Ação pedida pelo endereço (?acao=PETR4, o link do ticker no Screener); o parâmetro é
    # retirado da URL depois de lido, para não ficar desatualizado quando a ação mudar.
    acao_da_url = _ler_acao_da_url()
    opcoes_validas = (
        set(universo_ibovespa["ticker"])
        if usando_dropdown and universo_ibovespa is not None
        else None
    )
    ticker_da_url = None
    if acao_da_url is not None:
        if _acao_da_url_e_valida(acao_da_url, opcoes_validas):
            ticker_da_url = acao_da_url
            st.session_state["busca_inicial_automatica_feita"] = True
            busca_inicial_ja_feita = True
            st.session_state[CHAVE_TICKER_GUARDADO] = ticker_da_url
            st.session_state.pop(CHAVE_DROPDOWN_TICKER, None)
            st.session_state.pop(CHAVE_TEXTO_TICKER, None)
        else:
            st.warning(
                TEXTO_ACAO_DA_URL_INVALIDA.format(acao=_acao_da_url_para_exibir(acao_da_url))
            )

    # A ação escolhida fica guardada à parte: o Streamlit apaga o estado de um widget que não é
    # desenhado numa rodada (ao sair da página), e a seleção é restaurada ao voltar.
    ticker_guardado = st.session_state.get(CHAVE_TICKER_GUARDADO)
    with _bloco_barra_analisar:
        if usando_dropdown:
            assert universo_ibovespa is not None, "o dropdown só é usado com o universo carregado"
            nomes_por_ticker = dict(
                zip(universo_ibovespa["ticker"], universo_ibovespa["nome"], strict=True)
            )
            opcoes_ticker = list(nomes_por_ticker.keys())
            if CHAVE_DROPDOWN_TICKER not in st.session_state and ticker_guardado in opcoes_ticker:
                st.session_state[CHAVE_DROPDOWN_TICKER] = ticker_guardado
            # Pré-seleciona o ticker padrão só na primeira abertura da sessão; depois, o
            # dropdown segue 100% manual. A `key` fixa preserva a escolha entre reruns.
            indice_inicial = (
                opcoes_ticker.index(TICKER_PADRAO_PRIMEIRA_ABERTURA)
                if not busca_inicial_ja_feita and TICKER_PADRAO_PRIMEIRA_ABERTURA in opcoes_ticker
                else None
            )
            ticker_selecionado = st.selectbox(
                "Ação (Ibovespa)",
                options=opcoes_ticker,
                format_func=lambda t: f"{t} — {nomes_por_ticker[t]}",
                key=CHAVE_DROPDOWN_TICKER,
                index=indice_inicial,
                placeholder="Selecione uma ação...",
            )
            ticker = ticker_selecionado or ""
        else:
            # Degradação graciosa: a API da B3 pode estar fora do ar; texto livre, sem a lista.
            # Sem dropdown não há pré-seleção, então a busca automática não se aplica.
            st.warning(
                "Lista de ações do Ibovespa indisponível "
                f"({erro_universo or 'resultado vazio'}) — digite o ticker manualmente."
            )
            if CHAVE_TEXTO_TICKER not in st.session_state and ticker_guardado:
                st.session_state[CHAVE_TEXTO_TICKER] = ticker_guardado
            ticker = st.text_input("Ticker (ex: PETR4)", value="", key=CHAVE_TEXTO_TICKER)
            ticker = ticker.strip().upper()
        st.session_state[CHAVE_TICKER_GUARDADO] = ticker

        buscar_clicado = st.button("Buscar")

    # Dispara a busca automaticamente só na primeira abertura da sessão,
    # equivalente a já ter clicado em "Buscar" uma vez — marca a flag em
    # session_state antes de qualquer coisa pra garantir que isso não se
    # repete em nenhum rerun futuro (troca de página, outra busca, etc.).
    busca_automatica_primeira_abertura = (
        usando_dropdown and not busca_inicial_ja_feita and ticker == TICKER_PADRAO_PRIMEIRA_ABERTURA
    )
    if busca_automatica_primeira_abertura:
        st.session_state["busca_inicial_automatica_feita"] = True
    buscar = (
        buscar_clicado
        or busca_automatica_primeira_abertura
        or (ticker_da_url is not None and ticker == ticker_da_url)
    )

    if buscar and not ticker:
        st.warning("Selecione uma ação." if usando_dropdown else "Digite um ticker.")

    if buscar and ticker:
        st.session_state["ticker_com_resultado_exibido"] = ticker

    # "Sticky": uma vez buscado com sucesso, o resultado continua visível em
    # reruns disparados por outros widgets DENTRO da seção de resultado (ex:
    # as pills de "Comparando com Petróleo" mais abaixo) — sem isso, só trocar
    # a janela de comparação apagaria a página inteira, já que qualquer
    # widget com estado dispara um rerun do zero e `buscar` sozinho só é True
    # no exato rerun do clique em "Buscar". As buscas abaixo já têm cache
    # próprio (disco com TTL, ou st.cache_data), então reexecutá-las num
    # rerun "sticky" é barato — não bate na rede de novo.
    mostrar_resultado = bool(ticker) and (
        buscar or ticker == st.session_state.get("ticker_com_resultado_exibido")
    )

    if mostrar_resultado:
        with st.spinner(f"Buscando dados de {ticker}..."):
            historico, erro_historico = _buscar_historico(ticker, PERIODO_HISTORICO_COMPORTAMENTO)
            # Busca separada (não reaproveita `historico`) só pro card "Preço
            # atual": o endpoint de histórico diário do yfinance (o mesmo por
            # trás de PERIODO_HISTORICO_COMPORTAMENTO) atrasa um pregão
            # inteiro, mesmo já encerrado — period="1d" traz o fechamento
            # mais recente disponível de verdade. Ver o comentário em
            # config.py com a investigação completa (discrepância real
            # encontrada contra o TradingView).
            historico_preco_atual, erro_preco_atual = _buscar_historico(ticker, PERIODO_PRECO_ATUAL)
            historico_beta, erro_historico_beta = _buscar_historico(ticker, PERIODO_BETA)
            historico_ibovespa_beta, erro_historico_ibovespa_beta = _buscar_historico_ibovespa(
                PERIODO_BETA
            )
            indicadores, erro_indicadores = _buscar_indicadores_fundamentus(ticker)
            dividendos, erro_dividendos = _buscar_dividendos(ticker)
            cnpj, erro_cnpj = _buscar_cnpj(ticker)
            # Buscado aqui (cedo, perto do cnpj) pra alimentar o FCD logo
            # abaixo — não decide se o FCD se aplica com nenhum outro dado
            # já buscado (ver config.SEGMENTOS_FCD_NAO_APLICAVEL), só o
            # segmento setorial. "Comparação setorial" mais abaixo
            # reaproveita esse mesmo resultado, não busca de novo.
            segmento_setorial, erro_segmento_setorial = _buscar_segmento_setorial(ticker)
            macro, erro_macro = _buscar_macro()
            selic_meta = macro.selic_meta if macro else None
            ipca_12m = macro.ipca_12m if macro else None
            data_ipca = macro.data_ipca if macro else None
            macro_usou_valor_guardado = macro.usou_valor_guardado if macro else False
            macro_data_busca = macro.data_busca if macro else None
            ano_fcd_mais_recente, erro_ano_fcd = _buscar_ano_fcd_mais_recente()
            # Pro card "Correlação com fatores externos" mais abaixo — custo
            # parecido com o resto (mais duas séries de 2 anos e uma leitura
            # de arquivo do GPR), por isso já busca aqui junto, sem exigir
            # clique extra.
            historico_acao_correlacao, erro_acao_correlacao = _buscar_historico(
                ticker, periodo=f"{ANOS_JANELA_CORRELACAO}y"
            )
            historico_petroleo, erro_petroleo = _buscar_historico_petroleo()
            serie_cambio, erro_cambio = _buscar_cambio_correlacao()
            serie_gpr, erro_gpr = _buscar_gpr_diaria()

            # Erros de FCF não são exibidos à parte — já aparecem no motivo de
            # "não aplicável" do próprio card do FCD. `erro_ano_fcd` (detecção
            # do ano em si falhando, ex: CVM fora do ar) tem o mesmo destino:
            # sem `ano_fcd_mais_recente`, fcf_atual segue None e o card cai no
            # "não aplicável" do jeito de sempre, sem aviso à parte.
            fluxos_fcd = montar_fluxos_fcd(None)
            ano_fcd_utilizado = None
            fcd_usou_fallback = False
            caixa_fcd_utilizado = capex_fcd_utilizado = risco_sacado_fcd_utilizado = None
            if cnpj and ano_fcd_mais_recente is not None:
                (
                    fluxos_fcd,
                    ano_fcd_utilizado,
                    fcd_usou_fallback,
                    caixa_fcd_utilizado,
                    capex_fcd_utilizado,
                    risco_sacado_fcd_utilizado,
                    _,
                ) = _buscar_fcf_fcd(cnpj, ano_fcd_mais_recente)
            leitura_balanco = _buscar_leitura_balanco(cnpj, indicadores, ticker) if cnpj else None

        linha_listagem = (
            universo_ibovespa[universo_ibovespa["ticker"] == ticker]
            if universo_ibovespa is not None
            else None
        )
        segmento_listagem = nome_empresa = None
        if linha_listagem is not None and not linha_listagem.empty:
            segmento_listagem = linha_listagem.iloc[0]["segmento_listagem"]
            nome_empresa = linha_listagem.iloc[0]["nome"]
        # Ticker e nome à esquerda, pílulas de setor e governança à direita (abaixo, se estreito).
        coluna_titulo, coluna_pilulas = st.columns(PROPORCAO_CABECALHO_ANALISE, gap="small")
        coluna_titulo.subheader(f"{ticker} · {nome_empresa}" if nome_empresa else ticker)
        html_pilulas = _html_pilulas(segmento_setorial, segmento_listagem)
        if html_pilulas:  # st.html não aceita texto vazio
            coluna_pilulas.html(html_pilulas)
        # Números de destaque: preenchido mais abaixo, quando o valor combinado já existe.
        painel_destaque = st.container(border=True, key="painel_destaque")

        # st.error (preço) vs. st.warning (indicadores/dividendos/CNPJ/
        # macro abaixo) não é inconsistência: investigado e confirmado que
        # a distinção é funcional, não sobre "o resto da página trava"
        # (não trava — Graham/Bazin/FCD continuam computáveis sem preço,
        # só o delta de upside some; Saúde financeira só perde Valor de
        # Mercado/Firma, o resto continua). É sobre o dado em si: "Preço
        # atual" é o único número desta seção sem NENHUM fallback visual
        # quando falta — some por completo, só o erro fica no lugar. Já
        # indicadores/dividendos/CNPJ/macro alimentam seções que já têm
        # "N/D"/"indisponível" dedicado (ver `_fmt`, "Saúde financeira",
        # cartões de método) — a ausência delas já aparece refletida com
        # um fallback claro mais abaixo, não como um vazio nu.
        if erro_preco_atual:
            st.error(f"Preço: {erro_preco_atual}")
            preco_atual = None
        else:
            assert historico_preco_atual is not None, "sem erro de preço, o histórico existe"
            preco_atual = float(historico_preco_atual["Close"].iloc[-1])
            if not preco_valido(preco_atual):
                st.warning(AVISO_PRECO_INDISPONIVEL)
                preco_atual = None

        if erro_indicadores:
            st.warning(f"Fundamentus: {erro_indicadores}")
        if erro_dividendos:
            st.warning(f"Dividendos: {erro_dividendos}")
        if erro_cnpj:
            st.warning(f"CNPJ (CVM): {erro_cnpj}")
        if erro_macro:
            st.warning(erro_macro)
        elif (
            macro is not None
            and macro_usou_valor_guardado
            and macro.fonte_selic.startswith(PREFIXO_FONTE_ARQUIVO_REFERENCIA)
        ):
            st.warning(AVISO_MACRO_ARQUIVO_REFERENCIA.format(data=_fmt_data(macro_data_busca)))
        elif macro_usou_valor_guardado:
            st.warning(
                "Banco Central indisponível agora. Usando a Selic e o IPCA "
                f"obtidos em {_fmt_data(macro_data_busca)}."
            )
        elif macro and (aviso_fonte_macro := _aviso_fonte_macro(macro)):
            st.info(aviso_fonte_macro)
        if erro_ano_fcd:
            st.warning(erro_ano_fcd)
        # Número de ações do Fundamentus que não bate com a CVM (oferta, bonificação ou
        # cancelamento depois da data-base) ou número da CVM descartado por divergir demais.
        if leitura_balanco and leitura_balanco.get("aviso_unit"):
            st.warning(leitura_balanco["aviso_unit"])
        if leitura_balanco and leitura_balanco.get("aviso_divergencia_acoes"):
            st.warning(leitura_balanco["aviso_divergencia_acoes"])
        elif leitura_balanco and leitura_balanco.get("detalhe_acoes", {}).get(
            "descartada_por_divergencia"
        ):
            st.warning(leitura_balanco["motivo_acoes"])

        lpa = indicadores["lpa"] if indicadores else None
        vpa = indicadores["vpa"] if indicadores else None
        numero_acoes = indicadores["numero_acoes"] if indicadores else None
        divida_liquida_sobre_patrimonio = (
            indicadores["divida_liquida_sobre_patrimonio"] if indicadores else None
        )
        # Dívida líquida em valor ABSOLUTO (campo próprio do Fundamentus,
        # ausente pra bancos — ver CAMPOS_FUNDAMENTUS_OPCIONAIS), não a
        # mesma coisa que divida_liquida_sobre_patrimonio acima (a
        # proporção). Usada pro Valor de Firma mais abaixo e pra converter
        # o FCD de Enterprise Value pra Equity Value (ver modelos/fcd.py).
        divida_liquida = indicadores["divida_liquida"] if indicadores else None

        # Beta real (janela de 1 ano, calculada uma vez e reaproveitada no WACC
        # do FCD e no card de "Comportamento da ação" abaixo). None quando não
        # calculável — calcular_wacc cai pro BETA_PADRAO sozinho nesse caso,
        # não é tratado aqui.
        beta = None
        if not erro_historico_beta and not erro_historico_ibovespa_beta:
            beta = calcular_beta(historico_beta, historico_ibovespa_beta)

        # Graham é chamado direto (calcular_valor_justo_graham aceita
        # lpa/vpa como `float | None` e já trata ausência internamente).
        # Bazin e FCD, abaixo, precisam desse pré-check aqui em main.py
        # porque as duas funções EXIGEM tipo não-None nesses parâmetros
        # específicos — calcular_preco_teto_bazin quer um `pd.DataFrame`
        # de verdade (não `None`, mesmo vazio serve) pra `dividendos`, e
        # calcular_valor_justo_fcd declara `selic_meta`/`ipca_12m` como
        # `float`, não `float | None` — chamar qualquer uma direto com
        # `None` nesses parâmetros quebraria com AttributeError/TypeError
        # antes mesmo de chegar nos guards que elas já têm pra OUTROS
        # parâmetros (ex: fcf_atual/numero_acoes no FCD, que já são
        # `float | None` e tratados lá dentro). Não é duplicação evitável
        # — é a mesma forma de guard que os dois modelos já fazem
        # internamente pros parâmetros que aceitam None, só que aqui pros
        # que não aceitam.
        ajustes_balanco = montar_ajustes_balanco(leitura_balanco)
        lpa_graham, vpa_graham = reescalar_lpa_vpa(
            lpa, vpa, numero_acoes, ajustes_balanco["acoes_em_circulacao"]
        )
        resultado_graham = calcular_valor_justo_graham(lpa_graham, vpa_graham)
        ajuda_lpa_vpa = _ajuda_lpa_vpa_ajustados(lpa, vpa, lpa_graham, vpa_graham)
        resultado_bazin: dict = (
            calcular_preco_teto_bazin(dividendos)
            if dividendos is not None
            else {
                "aplicavel": False,
                "preco_teto": None,
                "motivo_nao_aplicavel": erro_dividendos or "Histórico de dividendos indisponível.",
            }
        )
        if selic_meta is not None and ipca_12m is not None:
            resultado_fcd = calcular_valor_justo_fcd(
                **fluxos_fcd,
                **ajustes_balanco,
                numero_acoes=numero_acoes,
                selic_meta=selic_meta,
                ipca_12m=ipca_12m,
                divida_liquida_sobre_patrimonio=divida_liquida_sobre_patrimonio,
                beta=beta,
                divida_liquida=divida_liquida,
                segmento_setorial=segmento_setorial,
                ticker=ticker,
            )
        else:
            resultado_fcd = {
                "aplicavel": False,
                "valor_justo": None,
                "motivo_nao_aplicavel": MENSAGEM_MACRO_INDISPONIVEL_CURTA,
            }

        resultado_combinado = calcular_valor_combinado(
            resultado_graham, resultado_bazin, resultado_fcd
        )
        divergencia_metodos = calcular_divergencia_metodos(
            resultado_combinado["valores_por_metodo"], preco_atual
        )
        cartoes_destaque = []
        if preco_atual is not None:
            cartoes_destaque.append(
                _html_kpi("Preço atual", _fmt_bilhoes(preco_atual), "ab-cor-texto")
            )
        if resultado_combinado["aplicavel"]:
            valor_combinado = resultado_combinado["valor_combinado"]
            cartoes_destaque.append(
                _html_kpi("Valor combinado", _fmt_bilhoes(valor_combinado), "ab-cor-principal")
            )
            if preco_atual is not None:
                acima_do_preco = valor_combinado >= preco_atual
                cor_potencial = "ab-cor-positivo" if acima_do_preco else "ab-cor-negativo"
                cartoes_destaque.append(
                    _html_kpi(
                        ROTULO_POTENCIAL,
                        ("+" if valor_combinado > preco_atual else "")
                        + (_delta_percentual_upside(valor_combinado, preco_atual) or ""),
                        cor_potencial,
                        "▲ valor acima do preço" if acima_do_preco else "▼ valor abaixo do preço",
                        cor_potencial,
                        ajuda=TOOLTIP_POTENCIAL_CARTAO,
                    )
                )
        else:
            motivos_metodos = "\n".join(
                linhas_motivos_metodos(resultado_graham, resultado_bazin, resultado_fcd)
            )
            rotulos_sem_valor = ["Valor combinado"]
            if preco_atual is not None:
                rotulos_sem_valor.append(ROTULO_POTENCIAL)
            for rotulo_cartao in rotulos_sem_valor:
                cartoes_destaque.append(
                    _html_kpi(
                        rotulo_cartao,
                        "—",
                        "ab-cor-secundario",
                        TEXTO_NENHUM_METODO_SE_APLICA,
                        ajuda=motivos_metodos,
                    )
                )
        cartoes_destaque.append(
            _html_kpi(
                "Divergência entre métodos",
                **_kpi_divergencia(divergencia_metodos, resultado_combinado["valores_por_metodo"]),
                ajuda=TOOLTIP_DIVERGENCIA_METODOS,
            )
        )
        with painel_destaque:
            st.html(f'<div class="ab-kpis">{"".join(cartoes_destaque)}</div>')

        proporcao_reinvestimento = None
        selos_valor_justo: list[tuple[str, str]] = []
        if resultado_fcd["aplicavel"]:
            origem_beta = "calculado, 1a" if beta is not None else "padrão, sem histórico"
            beta_wacc = _fmt(resultado_fcd["beta_utilizado"])
            selos_valor_justo.append(
                (f"Beta {beta_wacc}", f"Beta no WACC: {beta_wacc} ({origem_beta})")
            )
            if caixa_fcd_utilizado is not None and capex_fcd_utilizado is not None:
                proporcao_reinvestimento = calcular_proporcao_capex_caixa_operacional_percentual(
                    caixa_fcd_utilizado, capex_fcd_utilizado
                )
            # Sem capex identificado, sem selo (o FCD nem é calculado).
            if proporcao_reinvestimento is not None:
                selos_valor_justo.append(
                    (
                        f"Reinvestimento {proporcao_reinvestimento:.0f}%",
                        LEGENDA_REINVESTIMENTO_CAPEX.format(
                            ano=ano_fcd_utilizado, proporcao=proporcao_reinvestimento
                        ),
                    )
                )

        metodos_painel = (
            ("graham", resultado_graham),
            ("bazin", resultado_bazin),
            ("fcd", resultado_fcd),
        )
        coluna_valor_justo, coluna_saude = st.columns([3, 2])
        with (
            coluna_valor_justo,
            st.container(border=True, key="painel_valor_justo", height="stretch"),
        ):
            st.html(_html_cabecalho_painel("Valor justo por método", selos_valor_justo))
            if resultado_combinado["aplicavel"]:
                exibir_grafico(
                    _figura_valor_justo(
                        resultado_combinado["valores_por_metodo"],
                        resultado_combinado["valor_combinado"],
                        preco_atual,
                    )
                )
            else:
                st.info(
                    f"Valor combinado: {resultado_combinado['motivo_nao_aplicavel']} "
                    f"{TEXTO_COMPLEMENTO_SEM_METODO}"
                )
            # Método fora do gráfico: legenda com o motivo.
            for chave, resultado in metodos_painel:
                nome = ROTULOS_METODOS_GRAFICO[chave]
                if not resultado["aplicavel"]:
                    motivo = resultado["motivo_nao_aplicavel"].replace("$", "\\$")
                    st.caption(f"{nome} — Não aplicável: {motivo}")
                elif chave not in resultado_combinado["valores_por_metodo"]:
                    st.caption(f"{nome} — Valor indisponível.")

            razao_dividendos_bazin = resultado_bazin.get("razao_dividendos_12m_vs_mediana_5a")
            if (
                resultado_bazin["aplicavel"]
                and razao_dividendos_bazin is not None
                and razao_dividendos_bazin > RAZAO_DIVIDENDOS_ATIPICA_BAZIN
            ):
                st.caption(
                    "Dividendos dos últimos 12 meses em "
                    f"{razao_dividendos_bazin * 100:.0f}% da mediana dos 5 anos "
                    "anteriores. Pode ser crescimento real dos pagamentos ou um "
                    "pagamento extraordinário — a fonte não permite distinguir. "
                    "Se for extraordinário, o preço teto está inflado."
                )
            if resultado_fcd["aplicavel"]:
                aviso_fcd_extremo = avaliar_fcd_extremo(resultado_fcd, preco_atual)
                if aviso_fcd_extremo is not None:
                    st.warning(aviso_fcd_extremo["texto"].replace("$", "\\$"))
            notas_por_metodo = {
                chave: _notas_do_metodo(resultado)
                for chave, resultado in metodos_painel
                if resultado["aplicavel"]
            }
            for visiveis, _detalhes in notas_por_metodo.values():
                for nota in visiveis:
                    st.caption(nota)

            with st.expander("Métodos utilizados"):
                if resultado_combinado["aplicavel"]:
                    st.caption(
                        "Métodos utilizados: "
                        + _nomes_dos_metodos(resultado_combinado["metodos_utilizados"])
                    )
                    divergencia = divergencia_metodos
                    if divergencia["aplicavel"]:
                        if divergencia["divergencia_percentual"] is not None:
                            st.caption(
                                "Os métodos aplicáveis vão de "
                                f"{_fmt_bilhoes_md(divergencia['menor'])} a "
                                f"{_fmt_bilhoes_md(divergencia['maior'])}: uma diferença "
                                f"equivalente a {divergencia['divergencia_percentual']:.0f}% do "
                                "preço atual. Quanto maior essa diferença, menos os métodos "
                                "concordam entre si."
                            )
                        else:
                            st.caption(
                                "Os métodos aplicáveis vão de "
                                f"{_fmt_bilhoes_md(divergencia['menor'])} a "
                                f"{_fmt_bilhoes_md(divergencia['maior'])} "
                                f"({_fmt_bilhoes_md(divergencia['diferenca'])} de diferença)."
                            )
                for chave, (_visiveis, detalhes) in notas_por_metodo.items():
                    if detalhes:
                        st.markdown(f"**{ROTULOS_METODOS_GRAFICO[chave]}**")
                    for nota in detalhes:
                        st.caption(nota)
                if resultado_fcd["aplicavel"]:
                    # Só o FCD vem da DFP anual da CVM; "Saúde financeira" vem do Fundamentus
                    # (últimos 12 meses), sem relação com esse ano. Sem fallback, o ano já
                    # aparece em "Datas de referência dos dados usados".
                    if fcd_usou_fallback:
                        st.caption(
                            f"FCD calculado com a demonstração financeira anual de "
                            f"{ano_fcd_utilizado} (CVM) — a de {ano_fcd_mais_recente} "
                            "ainda não foi entregue por essa empresa."
                        )
                    if risco_sacado_fcd_utilizado:
                        st.caption(
                            TEXTO_RISCO_SACADO_RECLASSIFICADO.format(
                                ano=ano_fcd_utilizado,
                                valor=_fmt_bilhoes_md(abs(risco_sacado_fcd_utilizado)),
                            )
                        )

            st.caption(
                "Os valores acima são calculados a partir de fórmulas de valuation "
                "públicas e conhecidas (Graham, Bazin, FCD) aplicadas aos dados "
                "reais da empresa — isto não é uma recomendação de compra ou "
                "venda, apenas uma referência de estudo."
            )

        with st.expander("Como funciona esse cálculo?"):
            st.markdown(
                "**Graham** — fórmula de Benjamin Graham (mentor de Warren Buffett): "
                "valor justo = raiz quadrada de (22,5 × LPA × VPA). Só se aplica a "
                "empresas com lucro e patrimônio líquido positivos.\n\n"
                "**Bazin (preço teto)** — método do investidor Décio Bazin, focado em "
                "dividendos: calcula o preço máximo que garantiria um retorno de "
                f"{YIELD_MINIMO_BAZIN:.0%} ao ano só em dividendos, baseado no histórico "
                "de pagamento da empresa. Só se aplica a quem tem histórico consistente "
                "de dividendo. A fonte dos dividendos (Yahoo Finance) não distingue "
                "pagamentos ordinários de extraordinários: um provento pontual grande "
                "(como um dividendo especial) entra na mesma soma dos últimos 12 meses "
                "e pode inflar o preço teto.\n\n"
                "**FCD (Fluxo de Caixa Descontado)** — projeta os fluxos de caixa "
                "futuros da empresa e traz isso a valor presente, descontando pelo "
                "custo de capital (WACC).\n\n"
                "*Taxa de desconto*\n\n"
                "O custo do capital próprio parte da Selic menos o spread de default "
                "do Brasil (que a Selic já embute) mais o Beta da ação vezes o prêmio "
                "de risco do país; o custo da dívida é a Selic mais 2 pontos "
                "percentuais.\n\n"
                "*Fluxo de caixa*\n\n"
                "O fluxo de caixa usado é o caixa gerado pela operação menos o que a "
                "empresa gastou em imobilizado e intangível (máquinas, obras, "
                "sistemas) no ano, mais os juros pagos sobre a dívida, já descontado "
                "o imposto: os juros voltam ao fluxo porque o custo da dívida já "
                "entra no custo de capital e na dedução da dívida líquida.\n\n"
                "Quando a empresa paga os fornecedores por um convênio com banco "
                "(risco sacado ou similar) e registra o pagamento ao banco no caixa "
                "de financiamento, esse valor é tratado como operacional, porque "
                "substitui o pagamento ao fornecedor; sem isso o caixa operacional "
                "pareceria maior do que a geração de caixa, e a página avisa quando "
                "o ajuste é aplicado.\n\n"
                "Ficam de fora as aplicações financeiras, a compra e venda de "
                "participações e de ativos e o pagamento de arrendamentos (aluguéis "
                "de longo prazo).\n\n"
                "*Crescimento*\n\n"
                "O crescimento do fluxo nos cinco anos projetados é medido entre o "
                "ano mais recente e cinco anos antes, limitado ao crescimento da "
                "receita líquida no mesmo período (um fluxo não cresce mais que a "
                "receita por cinco anos, o que assume margem constante) e à faixa "
                "de -20% a +30% ao ano; sem receita utilizável, vale o crescimento "
                "do fluxo, e a página diz o motivo. Esse crescimento converge "
                "gradualmente, ano a ano, para o de longo prazo (a inflação, IPCA) "
                "em vez de saltar no sexto ano. Quando o fluxo de cinco anos atrás "
                "não pode ser usado, o crescimento passa a ser a inflação (IPCA) e "
                "a página avisa.\n\n"
                "Por isso, empresas em fase de investimento pesado (comuns em "
                "energia e saneamento) ou com dívida muito alta tendem a ter FCD "
                "bem abaixo dos outros métodos, mesmo quando são saudáveis. Separar "
                "o investimento que só mantém a empresa do que a faz crescer "
                "exigiria um dado que a fonte não informa de forma padronizada. A "
                'porcentagem reinvestida no ano aparece no selo "Reinvestimento", no '
                "topo do painel de valor justo.\n\n"
                "*Do valor da empresa ao valor por ação*\n\n"
                "Esse valor presente é o da empresa como um todo, dívida incluída — "
                "por isso a dívida líquida é deduzida antes de dividir pelo número "
                "de ações, chegando no valor que sobra para os acionistas; quando a "
                "dívida líquida não está disponível para uma empresa, o cálculo usa "
                "o valor da empresa inteira como aproximação, sem deduzir nada, e "
                "mostra um aviso na tela.\n\n"
                f"{TEXTO_FCD_AJUSTES_DO_BALANCO}\n\n"
                "*Quando o FCD não se aplica*\n\n"
                "Não se aplica a bancos — a dívida e os depósitos são a própria "
                "operação do banco, não financiamento externo — nem a seguradoras "
                "e à Itaúsa, cujo caixa vem de prêmios e de dividendos de "
                "participações; nesses casos a lógica de custo de capital do FCD "
                "não tem interpretação econômica válida (Graham e Bazin continuam "
                "funcionando normalmente). Também não é calculado quando a dívida "
                "líquida, o arrendamento e os sócios minoritários somam mais que o "
                "valor da empresa pelo fluxo de caixa (o valor por ação ficaria zero "
                "ou negativo; é comum em holdings e empresas muito endividadas), nem "
                "quando o caixa livre do último ano foi zero ou negativo: projetar "
                "um fluxo assim "
                "não estima valor. Se o gasto em imobilizado e intangível não puder "
                "ser identificado na demonstração da empresa, o FCD não é "
                "calculado, e o mesmo vale quando o fluxo do último ano é zero ou "
                "negativo.\n\n"
                "Fora esses casos, funciona mesmo para empresas sem lucro contábil "
                "no momento, já que olha geração de caixa, não resultado contábil "
                "passado.\n\n"
                "**Valor combinado** — média simples só dos métodos que se aplicam à "
                "empresa (se só um se aplica, o combinado é ele mesmo). É uma "
                "heurística: os pesos são iguais por simplicidade, não porque exista "
                "evidência de que os três acertam igualmente — definir pesos melhores "
                "exigiria testar os métodos contra o histórico de preços, o que este "
                "projeto ainda não faz. Os três também medem coisas diferentes: Graham "
                "e FCD estimam quanto a ação vale (um pelo lucro e patrimônio, outro "
                "pelo fluxo de caixa futuro), enquanto o Bazin é um preço teto de "
                f"compra — o máximo a pagar para receber {YIELD_MINIMO_BAZIN:.0%} ao "
                "ano em dividendos, não uma estimativa de valor. Por isso, leia o "
                "combinado junto com os valores individuais, não sozinho.\n\n"
                "**Limitações conhecidas de cada método**: Graham usa o valor "
                "patrimonial (VPA) na fórmula, então tende a ficar menos "
                "representativo para empresas com poucos ativos físicos mas alto "
                "valor de marca ou tecnologia — e não é calculável se VPA for "
                "negativo. Bazin depende de histórico consistente de dividendo, "
                "então fica indisponível para empresas de crescimento que "
                "reinvestem o lucro em vez de distribuir. FCD é o mais sensível a "
                "premissas (taxa de desconto e crescimento futuro) — pequenas "
                "mudanças nessas variáveis podem alterar bastante o resultado, "
                "especialmente quando a taxa de crescimento é estimada a partir de "
                "poucos anos de histórico."
            )

        with coluna_saude, st.container(border=True, key="painel_saude"):
            _titulo_painel("Saúde financeira", TEXTO_AJUDA_INDICADORES_AUSENTES)
            if indicadores is None:
                st.info("Indisponível — ver aviso do Fundamentus acima.")
            else:
                acoes_em_circulacao = ajustes_balanco["acoes_em_circulacao"]
                valores_mercado_firma = calcular_valor_mercado_e_firma(
                    preco_atual,
                    acoes_em_circulacao if acoes_em_circulacao is not None else numero_acoes,
                    divida_liquida,
                    ajustes_balanco["nao_controladores"],
                    ajustes_balanco["arrendamento_fora_da_divida"],
                )
                # Grade de 2 colunas: "R$ 618,7 bi" cabe sem cortar nas larguras de notebook.
                st.html(
                    '<div class="ab-grade">'
                    + _html_indicador(
                        "ROE",
                        _fmt(indicadores["roe_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["roe_percentual"], "sinal"),
                    )
                    + _html_indicador(
                        "Margem líquida",
                        _fmt(indicadores["margem_liquida_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["margem_liquida_percentual"], "sinal"),
                    )
                    + _html_indicador(
                        "LPA", _fmt(indicadores["lpa"], "R$ {:.2f}"), ajuda=ajuda_lpa_vpa["lpa"]
                    )
                    + _html_indicador(
                        "VPA", _fmt(indicadores["vpa"], "R$ {:.2f}"), ajuda=ajuda_lpa_vpa["vpa"]
                    )
                    + _html_indicador(
                        "Liquidez corrente",
                        _fmt(indicadores["liquidez_corrente"]),
                        _cor_indicador(indicadores["liquidez_corrente"], "liquidez"),
                    )
                    + _html_indicador(
                        "Dív. líq./patrim.", _fmt(indicadores["divida_liquida_sobre_patrimonio"])
                    )
                    + _html_indicador(
                        "Cresc. receita (5a)",
                        _fmt(indicadores["crescimento_receita_5a_percentual"], "{:.1f}%"),
                        _cor_indicador(indicadores["crescimento_receita_5a_percentual"], "queda"),
                    )
                    + _html_indicador(
                        "Valor de mercado", _fmt_bilhoes(valores_mercado_firma["valor_mercado"])
                    )
                    + _html_indicador(
                        "Dívida líquida", _fmt_bilhoes(valores_mercado_firma["divida_liquida"])
                    )
                    + _html_indicador(
                        "Valor de firma",
                        _fmt_bilhoes(valores_mercado_firma["valor_firma"]),
                        ajuda=TOOLTIP_VALOR_FIRMA,
                    )
                    + "</div>"
                )
                if valores_mercado_firma["componentes_ausentes"]:
                    st.caption(
                        TEXTO_FIRMA_SEM_COMPONENTES.format(
                            componentes=", ".join(
                                ROTULOS_COMPONENTES_VALOR_FIRMA[nome]
                                for nome in valores_mercado_firma["componentes_ausentes"]
                            )
                        )
                    )
                if leitura_balanco and ajustes_balanco["motivo_sem_acoes_em_circulacao"]:
                    st.caption(
                        TEXTO_SEM_ACOES_EM_CIRCULACAO.format(
                            motivo=ajustes_balanco["motivo_sem_acoes_em_circulacao"]
                        )
                    )

        with st.container(border=True, key="painel_grafico_preco"):
            _titulo_painel("Preço vs. Ibovespa (1 ano, base 100)")
            if erro_historico_beta or erro_historico_ibovespa_beta:
                st.info(
                    "Gráfico indisponível — histórico de preço ou do Ibovespa não pôde ser "
                    "buscado (ver avisos acima)."
                )
            else:
                # Reaproveita historico_beta/historico_ibovespa_beta (PERIODO_BETA,
                # 1 ano) já buscados pro cálculo de Beta acima — não busca dado
                # novo. Normalizado pra base 100 (ver graficos.py): plotar preço
                # bruto da ação ao lado dos ~130 mil pontos do Ibovespa deixaria a
                # ação uma linha reta ilegível.
                figura_preco, nomes_sem_dados_preco = _grafico_comparacao_normalizada(
                    historico_beta, ticker, historico_ibovespa_beta, "Ibovespa"
                )
                if figura_preco is None:
                    st.info(_mensagem_grafico_comparacao_sem_dados(nomes_sem_dados_preco))
                else:
                    exibir_grafico(figura_preco)

        with coluna_saude, st.container(border=True, key="painel_governanca"):
            _titulo_painel("Governança")
            linha_universo = (
                universo_ibovespa[universo_ibovespa["ticker"] == ticker]
                if universo_ibovespa is not None
                else None
            )
            indicadores_governanca = []
            if erro_universo:
                st.warning(f"Segmento de listagem: {erro_universo}")
            elif linha_universo is not None and not linha_universo.empty:
                indicadores_governanca.append(
                    _html_indicador(
                        "Segmento de listagem", str(linha_universo.iloc[0]["segmento_listagem"])
                    )
                )
            else:
                indicadores_governanca.append(
                    _html_indicador(
                        "Segmento de listagem",
                        "—",
                        ajuda=(
                            f"{ticker!r} não está na carteira teórica atual do Ibovespa — essa é "
                            "a única fonte de segmento de listagem que já temos."
                        ),
                    )
                )
            indicadores_governanca.append(
                _html_indicador("Free float", "—", ajuda="Dado não disponível nas fontes usadas.")
            )
            st.html('<div class="ab-grade">' + "".join(indicadores_governanca) + "</div>")

        coluna_comportamento, coluna_correlacao = st.columns(2)
        with (
            coluna_comportamento,
            st.container(border=True, key="painel_comportamento", height="stretch"),
        ):
            _titulo_painel("Comportamento da ação")
            indicadores_comportamento = []
            if erro_historico:
                st.info("Volume/volatilidade indisponíveis — ver aviso de preço acima.")
            else:
                indicadores_comportamento += [
                    _html_indicador(
                        "Volume médio (3m)", _fmt(calcular_volume_medio(historico), "{:,.0f}")
                    ),
                    _html_indicador(
                        "Volatilidade anualizada",
                        _fmt(calcular_volatilidade_anualizada(historico), "{:.1%}"),
                    ),
                ]

            # Beta usa uma janela própria mais longa (PERIODO_BETA) que volume/volatilidade, de
            # propósito (ver config.py); reaproveita o `beta` já calculado para o WACC do FCD.
            motivo_beta = ""
            if erro_historico_beta:
                motivo_beta = f"Preço indisponível: {erro_historico_beta}"
            elif erro_historico_ibovespa_beta:
                motivo_beta = f"Ibovespa indisponível: {erro_historico_ibovespa_beta}"
            elif beta is None:
                motivo_beta = "Histórico curto demais para calcular (poucas datas em comum)."
            indicadores_comportamento.append(
                _html_indicador(
                    "Beta (vs. Ibovespa, 1a)",
                    "—" if motivo_beta else _fmt(beta),
                    ajuda=motivo_beta,
                )
            )
            st.html('<div class="ab-grade">' + "".join(indicadores_comportamento) + "</div>")

        with (
            coluna_correlacao,
            st.container(border=True, key="painel_correlacao", height="stretch"),
        ):
            _titulo_painel(
                "Correlação com fatores externos",
                TEXTO_AJUDA_CORRELACAO.format(anos=ANOS_JANELA_CORRELACAO),
            )
            if erro_acao_correlacao:
                st.error(f"Preço de {ticker} (janela de correlação): {erro_acao_correlacao}")
            else:
                if erro_petroleo:
                    st.warning(f"Petróleo (Brent): {erro_petroleo}")
                if erro_cambio:
                    st.warning(f"Câmbio USD/BRL: {erro_cambio}")
                if erro_gpr:
                    st.warning(f"GPR: {erro_gpr}")

                resultados_correlacao = calcular_correlacoes_fatores(
                    historico_acao=historico_acao_correlacao,
                    historico_petroleo=historico_petroleo,
                    serie_cambio=serie_cambio,
                    serie_gpr=serie_gpr,
                )

                ultimo_gpr = None
                if serie_gpr is not None and not serie_gpr.empty:
                    ultimo_gpr = TEXTO_ULTIMO_DADO_GPR.format(
                        data=_fmt_data(serie_gpr["data"].max())
                    )
                st.html(_html_correlacoes(resultados_correlacao, ultimo_gpr))

        with st.container(border=True, key="painel_petroleo"):
            _titulo_painel("Comparando com Petróleo (Brent) · base 100")
            janela_petroleo_selecionada = st.pills(
                "Janela de comparação",
                options=list(JANELAS_COMPARACAO_PETROLEO.keys()),
                default="2 anos",
                key="janela_comparacao_petroleo",
            )
            if not janela_petroleo_selecionada:
                st.info("Selecione uma janela acima para ver o gráfico.")
            else:
                periodo_petroleo = JANELAS_COMPARACAO_PETROLEO[janela_petroleo_selecionada]
                with st.spinner(
                    f"Buscando histórico de {ticker} e do petróleo (Brent) em "
                    f"{janela_petroleo_selecionada}..."
                ):
                    historico_acao_petroleo, erro_acao_petroleo = _buscar_historico(
                        ticker, periodo=periodo_petroleo
                    )
                    historico_petroleo_janela, erro_petroleo_janela = _buscar_historico_petroleo(
                        periodo=periodo_petroleo
                    )

                if erro_acao_petroleo:
                    st.error(f"Preço de {ticker}: {erro_acao_petroleo}")
                elif erro_petroleo_janela:
                    st.error(f"Petróleo (Brent): {erro_petroleo_janela}")
                else:
                    figura_petroleo, nomes_sem_dados_petroleo = _grafico_comparacao_normalizada(
                        historico_acao_petroleo,
                        ticker,
                        historico_petroleo_janela,
                        "Petróleo (Brent)",
                    )
                    if figura_petroleo is None:
                        st.info(_mensagem_grafico_comparacao_sem_dados(nomes_sem_dados_petroleo))
                    else:
                        exibir_grafico(figura_petroleo)

        with st.container(border=True, key="painel_tradingview"):
            _titulo_painel("Gráfico avançado (TradingView)", TEXTO_AJUDA_TRADINGVIEW)
            html_tradingview = _widget_avancado_tradingview(ticker)
            if html_tradingview is None:
                st.info(MENSAGEM_TRADINGVIEW_TICKER_INVALIDO)
            else:
                st.iframe(html_tradingview.strip(), height=520)

        coluna_dividendos, coluna_comparacao_setorial = st.columns(2)
        with (
            coluna_dividendos,
            st.container(border=True, key="painel_dividendos", height="stretch"),
        ):
            if erro_dividendos:
                _titulo_painel(TITULO_PAINEL_DIVIDENDOS)
                st.info("Gráfico indisponível — ver aviso de dividendos acima.")
            else:
                ano_corrente = datetime.now().year
                # Reaproveita `dividendos` já buscado pro método de Bazin acima —
                # não busca dado novo.
                dividendos_por_ano = agregar_dividendos_por_ano(
                    dividendos, ano_corrente=ano_corrente
                )
                if dividendos_por_ano.empty:
                    _titulo_painel(TITULO_PAINEL_DIVIDENDOS)
                    st.info("Nenhum dividendo pago no histórico disponível.")
                else:
                    # period="max" porque o Dividend Yield por ano precisa do preço médio de
                    # TODOS os anos com dividendo pago. auto_adjust=False: preço NOMINAL da
                    # época, não ajustado por dividendos futuros (ver `_buscar_historico`).
                    historico_max, erro_historico_max = _buscar_historico(
                        ticker, "max", auto_adjust=False
                    )
                    dividend_yield_por_ano = calcular_dividend_yield_por_ano(
                        dividendos_por_ano,
                        historico_max
                        if not erro_historico_max
                        else pd.DataFrame(columns=["data", "Close"]),
                    )
                    notas = []
                    if dividendos_por_ano["parcial"].any():
                        notas.append(NOTA_DIVIDENDOS_ANO_PARCIAL.format(ano=ano_corrente))
                    if not dividend_yield_por_ano.empty:
                        notas.append(NOTA_DIVIDEND_YIELD_SUBESTIMADO)
                    _titulo_painel(TITULO_PAINEL_DIVIDENDOS, " ".join(notas) or None)

                    if not dividend_yield_por_ano.empty:
                        ano_inicial_janela = ano_corrente - ANOS_JANELA_DIVIDENDOS + 1
                        primeiro_ano = int(dividend_yield_por_ano["ano"].min())
                        rotulo_janela_curta = ROTULO_JANELA_DIVIDENDOS_CURTA.format(
                            anos=ANOS_JANELA_DIVIDENDOS
                        )
                        janela_dividendos = rotulo_janela_curta
                        # Com o histórico todo dentro da janela curta, não há o que escolher.
                        if primeiro_ano < ano_inicial_janela:
                            janela_dividendos = (
                                st.pills(
                                    "Janela do histórico",
                                    options=[
                                        rotulo_janela_curta,
                                        ROTULO_JANELA_DIVIDENDOS_COMPLETA.format(ano=primeiro_ano),
                                    ],
                                    default=rotulo_janela_curta,
                                    key="janela_dividendos",
                                )
                                or rotulo_janela_curta
                            )
                        exibir_grafico(
                            _figura_dividendos(
                                dividendos_por_ano,
                                dividend_yield_por_ano,
                                ano_inicial=(
                                    ano_inicial_janela
                                    if janela_dividendos == rotulo_janela_curta
                                    else None
                                ),
                            )
                        )

                    # Degradação transparente: yield ausente ou parcial não é erro, mas merece
                    # uma linha explicando o motivo.
                    if erro_historico_max:
                        st.caption(f"Dividend Yield indisponível: {erro_historico_max}")
                    elif dividend_yield_por_ano.empty:
                        st.caption(
                            "Dividend Yield indisponível — sem preço histórico "
                            "suficiente para os anos com dividendo pago."
                        )
                    elif len(dividend_yield_por_ano) < len(dividendos_por_ano):
                        st.caption(
                            "Dividend Yield mostrado só para os anos com preço "
                            "histórico disponível — ação listada há menos "
                            "tempo que o histórico de dividendos."
                        )

        with (
            coluna_comparacao_setorial,
            st.container(border=True, key="painel_comparacao_setorial", height="stretch"),
        ):
            _titulo_painel("Comparação setorial")
            # segmento_setorial/erro_segmento_setorial já buscados mais
            # acima (perto do cnpj, pro FCD) — reaproveitado aqui, sem
            # busca nova.
            if erro_segmento_setorial:
                st.warning(f"Classificação setorial: {erro_segmento_setorial}")
            else:
                tabela_screener_setor = _carregar_screener_ou_avisar(
                    screener_mod.CAMINHO_SAIDA_PADRAO,
                    'Rode o screener primeiro na página "Screener"',
                )
                if tabela_screener_setor is not None:
                    if "segmento_setorial" not in tabela_screener_setor.columns:
                        st.info(TEXTO_SCREENER_SEM_SEGMENTO_SETORIAL)
                    else:
                        # Os pares do mesmo setor vêm da coluna segmento_setorial do
                        # screener salvo, sem catálogo nem rede. Os números da tabela
                        # (preço, valor combinado, potencial) também vêm dele, não são
                        # recalculados.
                        tabela_pares = tabela_screener_setor[
                            tabela_screener_setor["segmento_setorial"] == segmento_setorial
                        ]
                        if tabela_pares.empty:
                            st.info(
                                f"Nenhuma outra ação do segmento setorial "
                                f"{_rotulo_segmento_setorial(segmento_setorial)!r} "
                                "encontrada no resultado salvo do screener."
                            )
                        else:
                            nome_segmento = _rotulo_segmento_setorial(segmento_setorial)
                            st.caption(f"Segmento setorial (B3): {nome_segmento}")
                            st.html(_html_tabela_setorial(tabela_pares, ticker))
                            if set(tabela_pares["ticker"]) <= {ticker}:
                                st.caption(TEXTO_SEM_OUTRA_ACAO_NO_SEGMENTO)
                            data_rodada = _data_da_ultima_rodada()
                            if data_rodada is not None:
                                st.caption(
                                    TEXTO_LEGENDA_DATA_SCREENER_SETORIAL.format(
                                        data=_fmt_data(data_rodada)
                                    )
                                )

        with st.expander("Datas de referência dos dados usados"):
            # Preço/Beta vêm da coluna "data" que obter_historico já traz
            # (ver ingest.precos) — só não era extraída até aqui. Balanço
            # vem de indicadores (Fundamentus, "Últ balanço processado",
            # ver ingest.fundamentus). FCD reaproveita ano_fcd_utilizado,
            # já calculado acima pro cartão do FCD. IPCA reaproveita
            # data_ipca de _buscar_macro. Selic normalmente não tem uma
            # data própria pra mostrar — é recalculada com a data de hoje
            # a cada busca — exceto
            # quando o Banco Central está fora do ar e o valor guardado
            # entra em uso: aí a data que importa é a da última busca com
            # sucesso, não a de hoje. Dividendos do Bazin continuam
            # sempre com a data de hoje.
            texto_selic_referencia = (
                f"último valor obtido em {_fmt_data(macro_data_busca)} "
                "(Banco Central indisponível agora)"
                if macro_usou_valor_guardado
                else "calculada com a data de hoje"
            )
            data_preco_referencia = None
            if not erro_preco_atual:
                assert historico_preco_atual is not None, "sem erro de preço, o histórico existe"
                data_preco_referencia = historico_preco_atual["data"].iloc[-1]
            data_beta_referencia = None
            if not erro_historico_beta:
                assert historico_beta is not None, "sem erro de Beta, o histórico existe"
                data_beta_referencia = historico_beta["data"].iloc[-1]
            data_balanco_referencia = (
                indicadores["data_balanco_fundamentus"] if indicadores else None
            )
            texto_fcd_referencia = (
                f"demonstração financeira anual de {ano_fcd_utilizado} (CVM)"
                if resultado_fcd["aplicavel"]
                else "não aplicável"
            )
            st.markdown(
                "Comparar o preço de hoje com o último balanço disponível é o "
                "padrão de mercado — cada dado abaixo tem uma data-base "
                "diferente por natureza (o balanço de uma empresa sempre sai "
                "com atraso), não por inconsistência:\n\n"
                f"- **Preço** — último fechamento: {_fmt_data(data_preco_referencia)}.\n"
                "- **Indicadores fundamentalistas** (Fundamentus) — balanço de "
                f"{_fmt_data(data_balanco_referencia)}: lucro, receita e margens "
                "somam os 12 meses até essa data; patrimônio, dívida e número "
                "de ações são a posição nessa data.\n"
                f"- **FCD** — {texto_fcd_referencia}.\n"
                f"- **Beta** — 1 ano de pregões até {_fmt_data(data_beta_referencia)}.\n"
                f"- **IPCA (12 meses)** — acumulado até {_fmt_data(data_ipca, '%m/%Y')}.\n"
                f"- **Selic** — {texto_selic_referencia}.\n"
                "- **Dividendos do método Bazin** (últimos 12 meses) — sempre "
                "calculados com a data de hoje."
            )


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
    with _bloco_barra_screener:
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
    with _bloco_barra_carteira:
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


# Nota de rodapé, fora de qualquer página (aparece nas três) — Streamlit
# Community Cloud "adormece" apps sem acesso recente. Diferente do que se
# poderia supor, não é uma tela em branco automática: a plataforma mostra
# sua própria página de "app dormindo", com um botão que o visitante
# precisa clicar pra acordar o container (confirmado contra a documentação
# oficial, 2026-09-21) — só depois disso começa a espera de carregamento.
# Sem esse aviso, o clique extra pareceria um link quebrado.


def _rodape_da_barra_lateral() -> None:
    """Data da última atualização do screener (a mesma do aviso do workflow) e o link do
    repositório."""
    macro = bcb_sgs.carregar_macro_referencia()
    data_rodada = _data_da_ultima_rodada()
    with st.sidebar.container(key=CHAVE_BARRA_RODAPE):
        if data_rodada is not None:
            st.caption(
                TEXTO_RODAPE_SCREENER_ATUALIZADO.format(data=_fmt_data(data_rodada)),
                help=None
                if _rodar_screener_permitido()
                else _texto_screener_atualizado_pelo_workflow(),
            )
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


_paginas = {
    CHAVE_BARRA_ANALISAR: st.Page(
        pagina_analisar,
        title=TITULO_PAGINA_ANALISAR,
        icon=ICONE_PAGINA_ANALISAR,
        url_path=URL_PAGINA_ANALISAR,
        default=True,
    ),
    CHAVE_BARRA_SCREENER: st.Page(
        pagina_screener,
        title=TITULO_PAGINA_SCREENER,
        icon=ICONE_PAGINA_SCREENER,
        url_path=URL_PAGINA_SCREENER,
    ),
    CHAVE_BARRA_CARTEIRA: st.Page(
        pagina_carteira,
        title=TITULO_PAGINA_CARTEIRA,
        icon=ICONE_PAGINA_CARTEIRA,
        url_path=URL_PAGINA_CARTEIRA,
    ),
}
_ROTULOS_DO_MENU = [
    (TITULO_PAGINA_ANALISAR, ICONE_PAGINA_ANALISAR),
    (TITULO_PAGINA_SCREENER, ICONE_PAGINA_SCREENER),
    (TITULO_PAGINA_CARTEIRA, ICONE_PAGINA_CARTEIRA),
]
# Menu próprio (um bloco por página), no lugar do menu padrão do Streamlit.
pagina_atual = st.navigation(list(_paginas.values()), position="hidden")
# Fora de uma execução do Streamlit (importação nos testes) a página não tem título.
_titulo_da_pagina_atual = getattr(pagina_atual, "title", TITULO_PAGINA_ANALISAR)
# O título da aba é o da página aberta, por isso a configuração vem depois do menu.
st.set_page_config(
    page_title=TITULO_ABA_NAVEGADOR.format(pagina=_titulo_da_pagina_atual),
    page_icon="📈",
    layout="wide",
)
# Único bloco de CSS da página (ver `_CSS_DA_PAGINA`).
st.html(_CSS_DA_PAGINA)
st.sidebar.html(f'<div class="ab-app-marca">{escape(TITULO_APP)}</div>')
_blocos_barra: dict[str, DeltaGenerator] = {}
for (_chave, _pagina), (_titulo, _icone) in zip(_paginas.items(), _ROTULOS_DO_MENU, strict=True):
    _ativa = _pagina is pagina_atual
    _blocos_barra[_chave] = st.sidebar.container(
        border=True, key=_chave + (SUFIXO_BARRA_ATIVA if _ativa else "")
    )
    with _blocos_barra[_chave]:
        st.page_link(_pagina, label=_titulo, icon=_icone)
# A caixa da ação e o Buscar entram no bloco da análise, só quando a página de análise roda; os
# filtros e o botão da rodada, no bloco do Screener, só quando a página do Screener roda.
_bloco_barra_analisar = _blocos_barra[CHAVE_BARRA_ANALISAR]
_bloco_barra_screener = _blocos_barra[CHAVE_BARRA_SCREENER]
_bloco_barra_carteira = _blocos_barra[CHAVE_BARRA_CARTEIRA]
# Cabeçalho: o título é o da página aberta; abaixo, o que ela faz e o aviso de estimativas.
st.html(f'<div class="ab-app-titulo">{escape(_titulo_da_pagina_atual)}</div>')
st.caption(f"{DESCRICOES_DAS_PAGINAS[_titulo_da_pagina_atual]}  \n{TEXTO_AVISO_ESTIMATIVAS}")
st.html('<div class="ab-app-divisoria"></div>')
pagina_atual.run()
_rodape_da_barra_lateral()

st.caption(TEXTO_RODAPE_APP_DORMINDO)
