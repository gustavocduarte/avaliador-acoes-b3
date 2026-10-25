"""Bloco de CSS da página: o único `st.html` com estilo do app."""

from string import Template

from avaliador_b3.config import (
    COR_ALERTA,
    COR_BORDA,
    COR_FUNDO_PAINEL,
    COR_NEGATIVO,
    COR_POSITIVO,
    COR_PRINCIPAL,
    COR_TEXTO,
    COR_TEXTO_SECUNDARIO,
    LARGURA_MINIMA_LISTA_SELECAO_PX,
)

_CSS_DA_PAGINA = Template("""<style>
/* Fundo dos painéis: gancho `.st-key-painel_*` gerado pelo `key` de cada st.container. */
[class*="st-key-painel_"] { background-color: $painel; }
/* Blocos da barra lateral: gancho `.st-key-barra_*`; o da página aberta tem o sufixo `_ativa`. */
[class*="st-key-barra_"] { background-color: $painel; }
[class*="st-key-barra_"][class*="_ativa"] { border-color: $principal; }
[class*="st-key-barra_"] a, [class*="st-key-barra_"] a p { font-size: 16px; font-weight: 600; }
[class*="st-key-barra_"][class*="_ativa"] a, [class*="st-key-barra_"][class*="_ativa"] a p {
  color: $principal; }
[class*="st-key-barra_"] label, [class*="st-key-barra_"] label p { font-size: 14px; }
.st-key-barra_rodape { background-color: transparent; }
/* Rótulo de um grupo de filtros, igual ao dos widgets nativos do bloco. */
.ab-rotulo-filtro { font-size: 14px; margin-bottom: .25rem; }
/* Cabeçalho do app: título menor, divisória fina e menos espaço no topo da página. */
[data-testid="stMainBlockContainer"] { padding-top: 4rem; }
.ab-app-titulo { font-size: 1.5rem; font-weight: 700; line-height: 1.2; }
/* Marca do app no topo da barra lateral: só texto, sem link. */
.ab-app-marca { font-size: 1.05rem; font-weight: 700; line-height: 1.2;
  padding: .25rem .25rem .1rem; }
/* O ticker da página de análise fica abaixo do título da página. */
[data-testid="stHeading"] h3 { font-size: 1.25rem; }
.ab-app-divisoria { border-top: 1px solid $borda; margin: .25rem 0 .5rem; }
/* Limites "mín." e "máx." do slider do potencial: o valor atual já diz se há filtro. */
[class*="st-key-barra_"] [data-testid="stSliderTickBar"] { display: none; }
/* Linhas do painel "Cenários" do Simulador. */
.ab-cenarios { display: flex; flex-direction: column; gap: .4rem; margin-bottom: .5rem; }
.ab-cenario { display: grid; grid-template-columns: 1fr auto auto; gap: .8rem; padding: .4rem .7rem;
  border-radius: 4px; border-left: 3px solid transparent; }
.ab-cenario-base { background: $borda; border-left-color: $principal; font-weight: 600; }
.ab-cenario-valor { font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; text-align: right; }
/* Cartões de alerta do Screener. */
.ab-atencao { display: flex; flex-direction: column; gap: .6rem; max-height: 20rem;
  overflow-y: auto; }
.ab-atencao-cartao { padding: .6rem .8rem; border: 1px solid $borda; border-left: 3px solid $alerta;
  border-radius: 4px; }
.ab-atencao-titulo { font-weight: 600; margin-bottom: .2rem; }
.ab-atencao-texto { font-size: .85rem; color: $secundario; }
.st-key-barra_rodape p, .st-key-barra_rodape a { font-size: 14px; }
/* Classes `.ab-*`: números de destaque, títulos e pílulas. Se o Streamlit deixar de aceitar
   este bloco, o conteúdo continua na tela, só sem o estilo. */
.ab-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1rem; }
.ab-kpi { min-width: 0; }
.ab-titulo { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase;
  color: $secundario; }
.ab-ajuda { cursor: help; margin-left: .4rem; padding: 0 .35rem; border: 1px solid $borda;
  border-radius: 50%; font-size: .65rem; letter-spacing: 0; }
.ab-valor { font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 2.25rem; font-weight: 600; line-height: 1.25; white-space: nowrap; }
.ab-linha { font-size: .8rem; color: $secundario; min-height: 1.2em; }
.ab-cor-texto { color: $texto; }
.ab-cor-principal { color: $principal; }
.ab-cor-positivo { color: $positivo; }
.ab-cor-negativo { color: $negativo; }
.ab-cor-alerta { color: $alerta; }
.ab-cor-secundario { color: $secundario; }
.ab-cabecalho { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: .5rem; margin-bottom: .25rem; }
.ab-selos { display: flex; flex-wrap: wrap; gap: .4rem; }
.ab-selo { padding: .05rem .6rem; border: 1px solid $borda; border-radius: 999px; font-size: .75rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace; color: $texto; cursor: help; }
.ab-grade { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem 1rem; }
.ab-ind { min-width: 0; }
.ab-ind-rotulo { display: block; font-size: .72rem; color: $secundario; }
.ab-ind-valor { font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; font-size: 1.2rem; font-weight: 600; white-space: nowrap; }
/* A tabela da comparação setorial ocupa a altura do painel (que acompanha o vizinho). Se o
   Streamlit renomear as classes .stElementContainer/.stHtml, só o esticamento se perde: a
   tabela continua visível, com a altura do conteúdo. */
.st-key-painel_comparacao_setorial .stElementContainer:has(.ab-tabela-caixa:not(.ab-tabela-curta)) {
  flex: 1 1 auto; min-height: 0; }
.st-key-painel_comparacao_setorial .stHtml:has(.ab-tabela-caixa:not(.ab-tabela-curta)),
.st-key-painel_comparacao_setorial .ab-tabela-caixa:not(.ab-tabela-curta),
.st-key-painel_comparacao_setorial .ab-tabela-caixa:not(.ab-tabela-curta) .ab-tabela {
  height: 100%; }
.ab-tabela-caixa { overflow-x: auto; }
.ab-tabela { width: 100%; border-collapse: collapse; font-size: .85rem; }
.ab-tabela th { padding: .35rem .5rem; text-align: left; font-size: .72rem; font-weight: 400;
  letter-spacing: .08em; text-transform: uppercase; color: $secundario;
  border-bottom: 1px solid $borda; }
.ab-tabela td { padding: .45rem .5rem; border-bottom: 1px solid $borda; }
.ab-tabela .ab-num { text-align: right; font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-variant-numeric: tabular-nums; white-space: nowrap; }
.ab-tabela tr.ab-linha-destaque td { font-weight: 600; background: $borda; }
.ab-tabela tr.ab-linha-total td { font-weight: 600; border-top: 1px solid $secundario; }
.ab-tabela tr.ab-linha-destaque td:first-child { color: $principal;
  box-shadow: inset 3px 0 $principal; }
.ab-div { display: flex; align-items: center; gap: .5rem; min-width: 11rem; }
.ab-div-trilho { position: relative; flex: 1; height: .6rem; }
.ab-div-trilho::before { content: ""; position: absolute; left: 50%; top: -.15rem;
  bottom: -.15rem; width: 1px; background: $secundario; }
.ab-div-barra { position: absolute; top: 0; bottom: 0; border-radius: 2px; }
.ab-div-pos { left: 50%; background: $positivo; }
.ab-div-neg { right: 50%; background: $negativo; }
.ab-div-valor { min-width: 4.2rem; text-align: right; white-space: nowrap;
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.ab-corr { display: grid; grid-template-columns: 8.5rem minmax(3rem, 1fr) 4.2rem 5.2rem;
  align-items: center; gap: .6rem; padding: .45rem 0; }
.ab-corr-nome { font-size: .85rem; }
.ab-corr-classe { font-size: .75rem; color: $secundario; }
.ab-corr-pos { left: 50%; background: $principal; }
.ab-corr-neg { right: 50%; background: $principal; }
.ab-pilulas { display: flex; flex-wrap: wrap; gap: .5rem; margin: .25rem 0 .75rem; }
@media (min-width: 640px) { .ab-pilulas { justify-content: flex-end; margin-top: .75rem; } }
.ab-pilula { padding: .1rem .75rem; border: 1px solid $borda; border-radius: 999px;
  font-size: .78rem; color: $secundario; }
/* A lista aberta das caixas de seleção cabe o maior rótulo, mesmo passando da barra lateral. */
[data-testid="stSelectboxVirtualDropdown"] { min-width: ${largura_lista}px; }
</style>""").substitute(
    painel=COR_FUNDO_PAINEL,
    secundario=COR_TEXTO_SECUNDARIO,
    borda=COR_BORDA,
    texto=COR_TEXTO,
    principal=COR_PRINCIPAL,
    positivo=COR_POSITIVO,
    negativo=COR_NEGATIVO,
    alerta=COR_ALERTA,
    largura_lista=LARGURA_MINIMA_LISTA_SELECAO_PX,
)
