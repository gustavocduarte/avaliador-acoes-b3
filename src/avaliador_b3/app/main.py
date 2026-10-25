"""Dashboard (Streamlit) do Avaliador de Ações da B3 — valor justo das ações do
Ibovespa por Graham, Bazin e fluxo de caixa descontado, com o valor combinado
e o simulador de carteira em três cenários (pessimista/base/otimista). Só chama
os adapters/modelos que já existem e organiza o resultado na tela; nenhuma lógica
de cálculo é reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path

# O projeto não está instalado como pacote (sem pyproject [project]/pip
# install -e . ainda) — `streamlit run` não adiciona src/ ao sys.path
# sozinho como o pytest faz via pythonpath, então isso resolve na mão.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from avaliador_b3 import screener as screener_mod
from avaliador_b3.app import barra_lateral
from avaliador_b3.app.componentes import (
    _html_cabecalho_painel,
    _html_kpi,
    _titulo_painel,
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
    _buscar_universo_ibovespa,
    _carregar_screener_ou_avisar,
    _data_da_ultima_rodada,
)
from avaliador_b3.app.formatacao import (
    _fmt,
    _fmt_bilhoes,
    _fmt_bilhoes_md,
    _fmt_data,
    _nomes_dos_metodos,
    _rotulo_segmento_setorial,
)
from avaliador_b3.app.paginas.analise_blocos import (
    _ajuda_lpa_vpa_ajustados,
    _aviso_fonte_macro,
    _cor_indicador,
    _delta_percentual_upside,
    _figura_dividendos,
    _figura_valor_justo,
    _grafico_comparacao_normalizada,
    _html_correlacoes,
    _html_indicador,
    _html_pilulas,
    _html_tabela_setorial,
    _kpi_divergencia,
    _mensagem_grafico_comparacao_sem_dados,
    _notas_do_metodo,
    _widget_avancado_tradingview,
)
from avaliador_b3.app.paginas.carteira import (
    pagina_carteira,
)
from avaliador_b3.app.paginas.screener import (
    pagina_screener,
)
from avaliador_b3.config import (
    ANOS_JANELA_CORRELACAO,
    ANOS_JANELA_DIVIDENDOS,
    AVISO_MACRO_ARQUIVO_REFERENCIA,
    AVISO_PRECO_INDISPONIVEL,
    CHAVE_BARRA_ANALISAR,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_BARRA_SCREENER,
    CHAVE_DROPDOWN_TICKER,
    CHAVE_TEXTO_TICKER,
    CHAVE_TICKER_GUARDADO,
    DESCRICOES_DAS_PAGINAS,
    ICONE_PAGINA_ANALISAR,
    ICONE_PAGINA_CARTEIRA,
    ICONE_PAGINA_SCREENER,
    JANELAS_COMPARACAO_PETROLEO,
    LEGENDA_REINVESTIMENTO_CAPEX,
    MENSAGEM_TRADINGVIEW_TICKER_INVALIDO,
    NOTA_DIVIDEND_YIELD_SUBESTIMADO,
    NOTA_DIVIDENDOS_ANO_PARCIAL,
    PADRAO_TICKER_B3,
    PARAMETRO_URL_ACAO,
    PERIODO_BETA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    PERIODO_PRECO_ATUAL,
    PREFIXO_FONTE_ARQUIVO_REFERENCIA,
    PROPORCAO_CABECALHO_ANALISE,
    RAZAO_DIVIDENDOS_ATIPICA_BAZIN,
    ROTULO_JANELA_DIVIDENDOS_COMPLETA,
    ROTULO_JANELA_DIVIDENDOS_CURTA,
    ROTULO_POTENCIAL,
    ROTULOS_COMPONENTES_VALOR_FIRMA,
    ROTULOS_METODOS_GRAFICO,
    TEXTO_ACAO_DA_URL_INVALIDA,
    TEXTO_AJUDA_CORRELACAO,
    TEXTO_AJUDA_INDICADORES_AUSENTES,
    TEXTO_AJUDA_TRADINGVIEW,
    TEXTO_AVISO_ESTIMATIVAS,
    TEXTO_COMPLEMENTO_SEM_METODO,
    TEXTO_FCD_AJUSTES_DO_BALANCO,
    TEXTO_FIRMA_SEM_COMPONENTES,
    TEXTO_LEGENDA_DATA_SCREENER_SETORIAL,
    TEXTO_NENHUM_METODO_SE_APLICA,
    TEXTO_RISCO_SACADO_RECLASSIFICADO,
    TEXTO_RODAPE_APP_DORMINDO,
    TEXTO_SCREENER_SEM_SEGMENTO_SETORIAL,
    TEXTO_SEM_ACOES_EM_CIRCULACAO,
    TEXTO_SEM_OUTRA_ACAO_NO_SEGMENTO,
    TEXTO_ULTIMO_DADO_GPR,
    TITULO_ABA_NAVEGADOR,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    TITULO_PAINEL_DIVIDENDOS,
    TOOLTIP_DIVERGENCIA_METODOS,
    TOOLTIP_POTENCIAL_CARTAO,
    TOOLTIP_VALOR_FIRMA,
    URL_PAGINA_ANALISAR,
    URL_PAGINA_CARTEIRA,
    URL_PAGINA_SCREENER,
    YIELD_MINIMO_BAZIN,
)
from avaliador_b3.correlacao import calcular_correlacoes_fatores
from avaliador_b3.empresa.comportamento import (
    calcular_beta,
    calcular_volatilidade_anualizada,
    calcular_volume_medio,
)
from avaliador_b3.empresa.valor_mercado import calcular_valor_mercado_e_firma
from avaliador_b3.graficos import (
    agregar_dividendos_por_ano,
    calcular_dividend_yield_por_ano,
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

MENSAGEM_MACRO_INDISPONIVEL_CURTA = "Selic/IPCA indisponíveis agora — veja o aviso no topo."


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
    with barra_lateral.bloco_da_barra(CHAVE_BARRA_ANALISAR):
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


# Nota de rodapé, fora de qualquer página (aparece nas três) — Streamlit
# Community Cloud "adormece" apps sem acesso recente. Diferente do que se
# poderia supor, não é uma tela em branco automática: a plataforma mostra
# sua própria página de "app dormindo", com um botão que o visitante
# precisa clicar pra acordar o container (confirmado contra a documentação
# oficial, 2026-09-21) — só depois disso começa a espera de carregamento.
# Sem esse aviso, o clique extra pareceria um link quebrado.


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
barra_lateral.montar_barra_lateral(_paginas, pagina_atual)
# A caixa da ação e o Buscar entram no bloco da análise, só quando a página de análise roda; os
# filtros e o botão da rodada, no bloco do Screener, só quando a página do Screener roda.
# Cabeçalho: o título é o da página aberta; abaixo, o que ela faz e o aviso de estimativas.
st.html(f'<div class="ab-app-titulo">{escape(_titulo_da_pagina_atual)}</div>')
st.caption(f"{DESCRICOES_DAS_PAGINAS[_titulo_da_pagina_atual]}  \n{TEXTO_AVISO_ESTIMATIVAS}")
st.html('<div class="ab-app-divisoria"></div>')
pagina_atual.run()
barra_lateral._rodape_da_barra_lateral()

st.caption(TEXTO_RODAPE_APP_DORMINDO)
