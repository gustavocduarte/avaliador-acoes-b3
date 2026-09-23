# Correções de 2026-09-22

Quatro commits num único dia, todos motivados por bugs reais confirmados por
screenshot ao vivo no app (não achados de auditoria estática, diferente de
`docs/auditoria-2026-09-18.md`/`docs/vistoria-pre-publicacao-2026-09-20.md`).
Os três primeiros corrigem problemas visíveis na aba "Analisar uma ação"; o
quarto é uma limpeza do código escrito nos três primeiros, com uma correção
real de bug encontrada no processo.

---

## 1. Texto desatualizado, "Preço atual" sem vírgula, truncamento em "Saúde financeira" (`3b84384`)

Três achados distintos na mesma leva, todos na aba "Analisar uma ação":

- **Texto público desatualizado**: o `st.caption` logo abaixo do título
  ("Avaliador de Ações da B3") e a docstring do módulo em `app/main.py`
  ainda diziam "Protótipo mínimo — teste de integração visual... não a
  versão final do dashboard", uma descrição que não refletia mais o estado
  real do projeto. Reescritos reaproveitando a abertura do README ("Ferramenta
  de avaliação de valor justo para ações principais da B3... com projeções
  apresentadas sempre como cenários — nunca como um número único").
- **"Preço atual" sem vírgula brasileira**: usava `f"R$ {preco:.2f}"` sem
  nenhuma conversão de separador decimal (ex: "R$ 48.00" em vez de
  "R$ 48,00"). Corrigido reaproveitando `_fmt_bilhoes` diretamente — um
  preço por ação está sempre abaixo do piso de R$ 1 milhão da função, então
  sempre cai no branco que já formata por extenso com vírgula.
- **Truncamento em "Saúde financeira"**: a seção usava 4 colunas por linha
  (`st.columns(4)`), o que cortava tanto valores curtos (LPA, VPA) quanto os
  já abreviados por `_fmt_bilhoes` (Valor de mercado, Dívida líquida, Valor
  de firma) em larguras comuns de notebook. Testado manualmente em
  1024/1366/1920px medindo `scrollWidth`/`clientWidth` via JavaScript (não só
  inspeção visual): valores abreviados como "R$ 618,7 bi" precisam de ~188px
  de largura, que só uma grade de 2 colunas (não 3 ou 4) garante sem corte
  nessas larguras — 3 colunas ficava literalmente empatada no limite em
  1366px (187,7px disponíveis vs. 188px necessários). Reduzido de 4 para 2
  colunas por linha.

**Verificação**: confirmado ao vivo no navegador nas 3 larguras, sem corte em
nenhuma das 10 métricas da seção (LPA, VPA, ROE, Margem líquida, Liquidez
corrente, Dív. líq./patrim., Cresc. receita, Valor de mercado, Dívida
líquida, Valor de firma).

---

## 2. Formatação de moeda/percentual e meses em inglês nos gráficos (`b16bf22`)

### Bug 1 — ponto decimal americano em vez de vírgula brasileira

Confirmado por screenshot em cartões de Valor Justo (Graham/Bazin/FCD/
Combinado), Saúde financeira, correlação, gráfico de dividendos, Simulador
de carteira e Comparação Setorial (ex: "R$ 10.35", "1370.8%"). Levantamento
prévio (grep completo em `app/main.py`) encontrou o bug em três frentes
arquiteturalmente distintas, cada uma corrigida de um jeito diferente:

- **`st.metric`/`st.caption`**: a raiz estava em `_fmt`, que só aplicava o
  template Python sem converter separador — um fix ali sozinho já corrige 9
  métricas (ROE, Margem líquida, LPA, VPA, Liquidez corrente, Dív.
  líq./patrim., Cresc. receita, Volatilidade anualizada, Beta). Fora da
  `_fmt`, outros ~12 pontos formatavam sem conversão cada um no seu próprio
  call site: `_delta_percentual_upside`, `_cartao_metodo`, `_cartao_correlacao`,
  "Valor combinado", "Beta no WACC", o aviso por ticker sem cenário, e 6
  pontos na aba de carteira (a frase "R$X podem valer entre...", a legenda de
  capital fora da projeção, e as legendas de CAGR). Extraído `_pt_br` — a
  mesma técnica de swap em três passos que `_fmt_bilhoes` já usava — e criado
  `_fmt_percentual` pro caso genérico de percentual.
- **Gráficos Plotly** (7 pontos — 4 no gráfico de dividendos, 3 na
  projeção da carteira): o d3-format por trás de especificadores como
  `"%{y:.2f}"` tem a mesma limitação de locale que o Python.
  `texttemplate`/`hovertemplate` passaram a usar valores pré-formatados via
  `text`/`customdata` em vez de deixar o Plotly formatar.
- **As 4 tabelas** (`st.dataframe`, 16 colunas no total — Comparação
  Setorial, Screener, Simulador de carteira, Ganho nominal vs. real):
  `st.column_config.NumberColumn(format=...)` é sprintf-js/d3-format por
  baixo, sem vírgula decimal brasileira em nenhum locale; a opção
  `format="localized"` do Streamlit usa `Intl.NumberFormat` com o locale do
  **navegador de quem visita**, não do código — confirmado lendo o bundle
  JS do Streamlit (`Intl.NumberFormat(void 0, t)`, locale indefinido =
  locale do runtime, não fixo em pt-BR). Convertidas pra `TextColumn` com
  valor pré-formatado. Trade-off aceito e documentado: ordenar por essas
  colunas no cabeçalho da tabela vira alfabético, não numérico — confirmado
  antes de aplicar que a ordem padrão de cada uma das 4 tabelas (sem nenhum
  clique de reordenação) já fazia sentido por si só.

### Bug 2 — mês em inglês no eixo X dos gráficos de série temporal

O eixo X de "Preço vs. Ibovespa" e "Comparando com Petróleo" mostrava
abreviação de mês em inglês ("May", "Sep", "Oct"). Confirmado que o bundle de
Plotly.js que o Streamlit empacota só tem o locale en-US registrado
(`grep` no bundle não achou nenhuma referência a "pt-BR" ou registro de
locale) — `config={"locale": "pt-BR"}` no `st.plotly_chart` não teria efeito
nenhum. Corrigido gerando `tickvals`/`ticktext` explicitamente em
`graficos.ticks_mensais_pt_br`, com mês traduzido em Python. Confirmado que
o gráfico de dividendos (eixo categórico, só ano) e o de projeção da carteira
(eixo em anos, não datas) não tinham esse problema.

**Verificação**: 8 testes novos (4 em `test_app_main.py` — Saúde
financeira, correlação, gráfico de dividendos, tabela do Screener; 4 em
`test_graficos.py` — `ticks_mensais_pt_br`) + verificação ao vivo no
navegador nos cartões, gráficos e nas 4 tabelas (incluindo o "1.370,8%" da
Comparação Setorial, com separador de milhar correto). 334 testes passando
no total.

---

## 3. Espaçamento irregular de mês nos eixos de gráfico (`66da64a`)

A correção do item 2 introduziu um bug novo, também confirmado por
screenshot: o eixo X de "Preço vs. Ibovespa" mostrava pulo de mês
inconsistente (2/2/1/2/2/1/2 meses), e "Comparando com Petróleo" também
(4/3/4/3/3/4/3). Causa raiz: `ticks_mensais_pt_br` usava
`pd.date_range(inicio, fim, periods=max_ticks)`, que divide o intervalo por
**tempo corrido** (dias) — como os meses têm tamanho diferente (28 a 31
dias), espaçamento igual em dias não produz espaçamento igual em meses.

Reescrito pra calcular o passo em **meses**: acha o menor passo "redondo" (1,
2, 3, 6, 12, 24 ou 60 meses — só intervalos que uma pessoa lê como natural)
que mantém a contagem de ticks dentro de `max_ticks`, depois anda de passo em
passo a partir da data mais recente pra trás (`pd.DateOffset(months=passo)`),
mantendo a mesma âncora à direita do eixo de antes — só corrigindo a
regularidade do espaçamento das datas anteriores.

**Verificação**: 2 testes novos confirmam passo constante entre ticks
consecutivos nas janelas de 1 ano e 2 anos que expuseram o bug, mais os 4
testes existentes atualizados pro novo comportamento (a âncora garantida
agora é a data mais recente, não mais a primeira data da série). Screenshot
ao vivo confirma Set/25→Nov/25→Jan/26→Mar/26→Mai/26→Jul/26→Set/26 (passo 2,
janela de 1 ano) e Mar/25→Set/25→Mar/26→Set/26 (passo 6, janela de 2 anos).
336 testes passando no total.

---

## 4. Limpeza do código dos três itens acima (`7016921`)

Depois de aplicadas as três correções, uma auditoria específica (não uma
nova rodada de bugs — investigação do próprio código escrito no dia)
encontrou comentários redundantes, uma duplicação real entre as 4 tabelas, e
testes que reimplementavam na mão um helper que já existia. Dividido em
refatoração pura e uma correção real de bug, commitados juntos mas descritos
separadamente na mensagem de commit:

### Refatoração (sem mudança de comportamento)

- **3 comentários encurtados**: um bloco de 17 linhas em `test_graficos.py`
  que repetia quase palavra-por-palavra a docstring de `ticks_mensais_pt_br`
  (mantida só a frase específica do teste, sobre por que `tickvals[-1]` é
  verificado em vez de `tickvals[0]`); um comentário em
  `test_tabela_screener_mostra_moeda_e_percentual_com_virgula_brasileira` que
  repetia a explicação completa do trade-off de ordenação antes de apontar
  pro comentário central em `app/main.py` (mantida só a referência); um
  comentário em `test_projecao_carteira_usa_base_com_cenario_nao_a_base_total`
  que misturava narrativa geral (já coberta pela mensagem de commit) com
  contexto específico do teste (mantido só o específico).
- **Helper `_tabela_formatada_pt_br`** (`app/main.py`): as 4 tabelas
  convertidas de `NumberColumn` pra `TextColumn` no item 2 repetiam o mesmo
  padrão de `.assign()` + `column_config` — 83 linhas quase idênticas ao
  todo (16 colunas monetárias/percentuais, 48 delas só repetindo
  `st.column_config.TextColumn(rótulo, alignment="right")`). Consolidado
  numa função que recebe o DataFrame e dois dicts (`{coluna: rótulo}` de
  moeda e de percentual) e devolve o DataFrame formatado + o
  `column_config` pronto. O comentário central sobre o porquê (sprintf-js
  sem vírgula brasileira, `"localized"` depende do navegador de quem
  visita) e o trade-off de ordenação passou a viver uma única vez, na
  docstring do helper, em vez de duplicado nos 4 call sites.
- **Helper `_metrica_por_label`** (`tests/test_app_main.py`): o padrão
  "filtrar `at.metric` por `label`, confirmar que achou exatamente um,
  extrair o valor" apareceu 6 vezes de forma independente no arquivo — 3
  como list comprehension inline, 2 como closure local (`_valor`/
  `_valor_metrica`, escritas em momentos diferentes com nomes quase iguais)
  e uma delas já pré-existente antes de hoje. Consolidado num helper de
  módulo único, substituindo todas as 6 ocorrências.

### Correção real

Ao reescrever os 4 testes que reimplementavam na mão o bloco de mocks já
coberto por `_bloquear_buscas_de_rede_por_ticker` (escrito antes de hoje) —
Saúde financeira, correlação, gráfico de dividendos e tabela do Screener —
para chamar o helper existente em vez de duplicá-lo, ficou exposto que
`test_grafico_dividendos_mostra_rotulos_com_virgula_brasileira` nunca
mockava `obter_historico_ibovespa`. Esse teste dependia de acesso de rede
real (ou de uma falha silenciosa tratada) pra esse dado específico,
contrariando o objetivo dos testes do projeto — determinístico, sem rede de
verdade. Corrigido como consequência direta de usar o helper compartilhado,
que já cobre esse mock.

**Verificação**: suíte completa rodada depois de cada uma das três partes
(comentários, helper das tabelas, helper de teste + correção do gap), não só
no final — nenhuma delas revelou dependência de rede real que exigisse
inventar um valor pra fazer passar. 336 testes passando, líquido de -112
linhas (131 inserções, 243 remoções) nos 3 arquivos tocados.

---

## Resumo executivo

| Commit | Tipo | O que mudou |
|---|---|---|
| `3b84384` | Correção | Texto público desatualizado, "Preço atual" sem vírgula, truncamento em "Saúde financeira" (4→2 colunas) |
| `b16bf22` | Correção | Ponto em vez de vírgula em moeda/percentual (cards, gráficos Plotly, 4 tabelas) + mês em inglês nos eixos de série temporal |
| `66da64a` | Correção | Espaçamento irregular de mês nos mesmos eixos (regressão introduzida pelo commit anterior, corrigida no mesmo dia) |
| `7016921` | Refatoração + correção | Comentários redundantes encurtados, `_tabela_formatada_pt_br` e `_metrica_por_label` extraídos, gap de mock em teste corrigido |

Progressão da suíte de testes no dia: 326 → 334 (`b16bf22`, 8 testes novos)
→ 336 (`66da64a`, 2 testes novos) → 336 (`7016921`, refatoração sem
mudança de contagem líquida). Ruff limpo em todos os 4 commits.
