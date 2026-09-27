# Auditoria técnica — Avaliador de Ações da B3 (2026-09-27)

Auditoria feita sobre o zip `avaliador-acoes-b3-master` (estado do `master`
em 27/09/2026). Foco: bugs reais, erros financeiros, problemas de dados e
"bugs silenciosos". Cada achado está marcado como **CONFIRMADO** (reproduzido
ou provado pelo código), **POSSÍVEL** (plausível, não reproduzido) ou **NÃO
FOI POSSÍVEL VERIFICAR**.

## 0. O que foi executado

| Ferramenta | Resultado |
|---|---|
| `pytest` (Python 3.12.3, deps do `requirements.txt` sem versão fixada) | **444 passaram**, 0 falhas, 3 avisos (1 esperado, 1 `RuntimeWarning` do numpy em teste de série constante) |
| `ruff check .` | Limpo |
| `ruff format --check .` | 20 arquivos seriam reformatados (formatação não é aplicada/checada no projeto) |
| `mypy src --ignore-missing-imports` | 34 erros; a maioria é `Optional` não estreitado no `app/main.py` ou falso positivo do pandas-stubs. Nenhum comprovado como erro de execução (ver P17) |
| Verificação numérica manual do FCD | Bate com o código até a última casa (ver seção FCD) |
| Reproduções escritas para esta auditoria | P01 (Bazin), P05 (correlação) — ambos reproduzidos |

**Não executado / não verificável:**
- O app Streamlit ao vivo e as fontes externas (Yahoo, CVM, Fundamentus, B3,
  BCB, GPR): o ambiente da auditoria só tem rede para repositórios de
  pacotes. Tudo que depende de dado real atual foi analisado pelo código, pelo
  `screener.csv` versionado e pelas fixtures, e está marcado como tal.
- Cobertura de testes (não rodada).

## 1. Arquitetura e fluxo (resumo)

```
B3 (carteira Ibovespa, catálogo emissores) ─┐
Fundamentus (HTML, TTM até últ. balanço) ───┤
yfinance (preço, dividendos, ^BVSP, BZ=F) ──┼─> ingest/* (cache em disco, TTL/versão)
CVM DFP anual (zip, DFC 6.01/6.02) ─────────┤        │
BCB SGS (Selic meta 432, IPCA 433, câmbio) ─┤        v
GPR diário (xls) ───────────────────────────┘   modelos/ (Graham, Bazin, FCD, combinado)
                                                 empresa/ (beta, vol, valor de mercado)
                                                 correlacao.py, carteira.py, graficos.py
                                                        │
                                   screener.py (76 ações → screener.csv versionado)
                                                        │
                                   app/main.py (3 abas: Analisar, Screener, Carteira)
```

Linhagem dos números principais:

| Resultado | Origem |
|---|---|
| Preço atual | yfinance `history(period="1d", auto_adjust=True)` → último `Close` |
| Graham | `sqrt(22,5 × LPA × VPA)`, LPA/VPA do Fundamentus (12 meses até o último balanço trimestral, ex. 30/06/2026) |
| Bazin | soma dos dividendos do yfinance com data em (hoje−1 ano, hoje] ÷ 6% |
| FCD | FCF = DFC 6.01 + 6.02 (CVM, DFP anual, consolidado → individual), ano detectado; crescimento = CAGR FCF (ano, ano−5) limitado a [−20%, +30%]; WACC = CAPM com Selic meta + beta 1a + prêmio 7,47%, Kd = Selic+2% × (1−34%), pesos por Dív.Líq/PL (Fundamentus); perpetuidade = min(IPCA 12m, WACC−1pp); EV − dívida líquida (Fundamentus) ÷ nº de ações (Fundamentus) |
| Valor combinado | média simples dos métodos aplicáveis |
| "Desconto" | (valor combinado − preço) ÷ preço × 100 |
| Cenários do Simulador | pessimista = min(métodos), base = combinado, otimista = max(métodos), projetados como preço daqui a 5 anos |

---

## 2. Problemas encontrados

### P01 — Bazin descarta o pagamento mais antigo da janela de 5 anos

**Classificação:** BUG · **Severidade:** ALTA · **Status:** CONFIRMADO

**Arquivo:** `src/avaliador_b3/modelos/bazin.py` · **Local:** `_anos_com_dividendo` + `_tem_historico_relevante`

**Problema:** os anos exigidos são os 5 anos civis anteriores
(`ano−1 … ano−5`), mas os pagamentos considerados são filtrados por
`data >= data_referencia − 5 anos`. O ano mais antigo exigido (`ano−5`) só é
reconhecido se o pagamento dele cair **depois** do dia/mês da data de
referência.

**Evidência:**
```python
limite = data_referencia - pd.DateOffset(years=ANOS_HISTORICO_MINIMO_BAZIN)
recentes = dividendos[dividendos["data"] >= limite]           # corta 2021 antes de 27/09
...
anos_esperados = {data_referencia.year - i for i in range(1, 6)}  # exige 2021 inteiro
```

**Como reproduzir:** empresa que paga todo ano em 15/05, de 2019 a 2026:
```
ref 2026-09-27 → aplicavel=False ("não distribuiu dividendos em cada um dos últimos 5 anos")
ref 2026-03-01 → aplicavel=True, preço teto 16,67
```
Mesma empresa, mesmo histórico: o resultado depende do mês em que o app roda.

**Resultado esperado:** o critério é "pagou em cada um dos 5 anos civis
anteriores"; o filtro deveria ser pelo ano civil (`data.year >= ano−5`), não
pela data exata.

**Impacto:** cálculo e ranking. No `screener.csv` atual, **36 de 76 ações**
estão sem Bazin, incluindo pagadoras conhecidas e regulares (BBSE3, CPFE3,
ISAE4, CPLE3, SBSP3, EQTL3, VALE3). **POSSÍVEL** que várias delas sejam
falsos negativos deste bug (quem paga só no 1º semestre é excluída quando o
app roda no 2º). Não foi possível confirmar ticker a ticker sem acesso ao
yfinance. Um Bazin faltando muda o valor combinado, o ranking e os cenários do
Simulador.

**Por que os testes não pegaram:** as fixtures de dividendos usam 1º de
dezembro de cada ano, data que sempre fica depois do limite.

**Correção sugerida:** filtrar por ano civil em `_anos_com_dividendo`, usando
o mesmo conjunto de anos de `_tem_historico_relevante` e de
`_razao_dividendos_12m_vs_mediana` (que já usa ano civil inteiro — hoje as
duas funções discordam sobre o que é "os últimos 5 anos").

**Teste necessário:** pagamento anual em maio, referência em setembro →
aplicável; referência em janeiro/junho/dezembro → mesmo resultado.

---

### P02 — Simulador pode projetar perda maior que 100%

**Classificação:** BUG / ERRO FINANCEIRO · **Severidade:** ALTA · **Status:** CONFIRMADO (pelo código)

**Arquivo:** `src/avaliador_b3/carteira.py` · **Local:** `derivar_cenarios_ticker`, `simular_investimento_ticker`

**Problema:** pessimista = `min(métodos aplicáveis)`. O FCD pode ser
negativo (hoje há **30 ações com FCD < 0** no `screener.csv`, ex. SBSP3
−26,74, PRIO3, EQTL3). A projeção é `valor_investido × (valor/preço)`,
então vira **negativa**: investir R$1.000 em SBSP3 mostra um cenário
pessimista de valor negativo, que também entra somado no "Total da carteira".
No caso da SBSP3 até o cenário **base** é negativo, porque o valor combinado
dela no CSV atual é −R$0,55.

**Resultado esperado:** o piso econômico de uma ação é zero (responsabilidade
limitada). Valor justo ≤ 0 deve virar "perda total" (R$0, −100%), ou o
cenário deve ser marcado como "modelo sem leitura", nunca um saldo negativo.

**Impacto:** usuário (número impossível), totais da carteira, CAGR
(`calcular_cagr_implicito` devolve `None` e o cenário some da legenda).

**Teste necessário:** linha com FCD negativo como menor método → projeção
pessimista ≥ 0 (ou marcada explicitamente).

---

### P03 — Simulador trata o valor justo de hoje como preço daqui a 5 anos

**Classificação:** ERRO FINANCEIRO · **Severidade:** ALTA · **Status:** CONFIRMADO (metodologia)

**Arquivo:** `src/avaliador_b3/app/main.py` (aba Simulador, `n_anos = HORIZONTE_PROJECAO_FCD_ANOS`), `carteira.py`

**Problema:** Graham, Bazin e FCD produzem um valor **presente** (quanto a
ação valeria hoje). O Simulador usa esse valor como o preço que a ação terá
**em 5 anos**, calcula o CAGR sobre 5 anos e ainda deflaciona o resultado
pelo IPCA de 5 anos ("ganho real"). Três problemas:
1. O "5" vem do horizonte de projeção explícita do FCD, que não tem relação
   com quando o mercado convergiria ao valor justo.
2. Deflacionar um valor que já está em reais de hoje conta a inflação duas
   vezes.
3. Dividendos recebidos no período não entram (para pagadoras de Bazin, é a
   maior parte do retorno).

**Impacto:** CAGR e "ganho real" exibidos não têm interpretação financeira
consistente.

**Correção sugerida:** apresentar como "potencial de valorização se o preço
convergir ao valor justo" (sem prazo), ou modelar explicitamente o prazo como
premissa do usuário e crescer o valor justo pelo custo de capital no
período. No mínimo, documentar a premissa na tela.

---

### P04 — O "fluxo de caixa livre" (6.01 + 6.02) mistura itens que não são geração de caixa operacional

**Classificação:** ERRO FINANCEIRO / LIMITAÇÃO NÃO DOCUMENTADA · **Severidade:** ALTA · **Status:** CONFIRMADO (definição) / impacto por empresa POSSÍVEL

**Arquivo:** `src/avaliador_b3/ingest/cvm.py` (`_cfo_cfi_do_periodo`), `config.py` (seção FCD)

**Problema:** `FCF = Caixa Líquido Operacional (6.01) + Caixa Líquido de
Investimento (6.02)`. Pelas normas contábeis brasileiras (CPC 03/IAS 7):
- **6.02 inclui movimentações de tesouraria** (aplicações e resgates
  financeiros) e vendas de participações/ativos. Um resgate de aplicação ou
  uma venda pontual entra como "fluxo livre" e é perpetuado na
  projeção. Caso real já observado: CSAN3 (venda de ~R$8,9 bi quase anulou
  ~R$8,5 bi de investimento em 2025) — FCD R$32,06 contra preço R$3,82.
- **Juros pagos** podem ser classificados em 6.01 ou 6.03 à escolha da
  empresa. O FCF vira "antes dos juros" (tipo FCFF) numa empresa e "depois
  dos juros" em outra, e as duas são descontadas pelo mesmo WACC.
- **Arrendamentos (IFRS 16)**: o pagamento do principal fica em 6.03, então
  varejistas e empresas com muitos aluguéis (RADL3, LREN3, ASAI3) têm FCF
  inflado. Se a "dívida líquida" do Fundamentus não incluir o passivo de
  arrendamento (NÃO VERIFICADO), o custo do aluguel desaparece do valuation.

**Resultado:** o fluxo não é nem FCFF nem FCFE, e não é comparável entre
empresas.

**Correção sugerida:** no curto prazo, documentar em
`docs/limitacoes-conhecidas.md` e no expander do FCD. No médio prazo, usar
só a conta de aquisição de imobilizado/intangível (dentro de 6.02, localizada
por descrição, como já é feito com Lucro Líquido) em vez do 6.02 inteiro, e
tratar juros pagos de forma uniforme.

---

### P05 — Correlação calcula retornos antes de alinhar as datas

**Classificação:** BUG (estatístico) / INCONSISTÊNCIA · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Arquivo:** `src/avaliador_b3/correlacao.py` · **Local:** `_retornos_diarios` + `calcular_correlacao`

**Problema:** cada série vira retorno percentual **no seu próprio
calendário** e só depois as séries são juntadas pela data. Se um calendário
tem dias que o outro não tem, o "retorno de segunda-feira" de cada série cobre
períodos diferentes. O GPR tem leitura em fins de semana (o próprio código
cita uma leitura em 09/02/2025, um domingo): a variação de segunda do GPR é
domingo→segunda, a da ação é sexta→segunda. O Brent segue o calendário
americano.

**Evidência (reprodução):** duas séries com movimento idêntico, uma
observada todo dia e outra só em dias úteis:
```
implementação atual:           0,868
alinhando os níveis primeiro:  1,000
```

**Inconsistência:** `empresa.comportamento.calcular_beta` faz o certo (junta
os preços primeiro e depois calcula os retornos). A docstring da correlação
diz que aplica "o mesmo cuidado" do beta, o que não é verdade.

**Impacto:** a correlação com GPR (e em menor grau com o Brent) sai
sistematicamente atenuada, empurrando o resultado pra "fraca".

**Correção sugerida:** juntar os níveis por data e só então calcular
`pct_change` nas duas colunas, como no beta.

**Teste necessário:** o caso da reprodução acima (resultado 1,0).

---

### P06 — Units (ex. KLBN11, TAEE11, ENGI11): número de ações pode estar em outra unidade que o preço

**Classificação:** ERRO DE DADOS · **Severidade:** ALTA se confirmado · **Status:** NÃO FOI POSSÍVEL VERIFICAR

**Arquivo:** `modelos/fcd.py`, `empresa/valor_mercado.py`, `ingest/fundamentus.py`

**Problema:** o preço do yfinance para uma unit é o preço **da unit** (que
reúne várias ações; a KLBN11 são 5). O FCD divide o valor dos acionistas pelo
"Nro. Ações" do Fundamentus. Se o Fundamentus informar o número de **ações**
(e não de units) para esses tickers, o FCD por unit sai dividido pelo fator
errado, e o "Valor de mercado" do app (preço × nº de ações) sai multiplicado
pelo mesmo fator.

**Indício:** para PETR4 a conta fecha (Cotação 49,00 × 12,8887 bi = Valor
de mercado 631,5 bi no próprio Fundamentus). Para units não há fixture.

**Correção/verificação sugerida:** usar como número de ações "equivalente ao
ticker" `Valor de mercado ÷ Cotação`, ambos lidos da mesma página do
Fundamentus. Isso é consistente por construção com o preço do ticker, para
units ou não. Teste: fixture de uma unit + checagem de que
`preço × nº de ações ≈ valor de mercado do Fundamentus`.

---

### P07 — Falha do Banco Central no Screener é silenciosa

**Classificação:** ROBUSTEZ / BUG SILENCIOSO · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Arquivo:** `src/avaliador_b3/screener.py` · **Local:** `rodar_screener`

**Evidência:**
```python
try:
    selic_meta, ipca_12m = _buscar_macro(diretorio_cache)
except Exception:
    selic_meta = ipca_12m = None
```

**Problema:** se o BCB falhar, o FCD de todas as 76 ações vira "não
aplicável" com o motivo "Selic/IPCA indisponíveis", que não chega à coluna
"erro" do CSV (o combinado usa a própria mensagem). O ranking é gravado e
publicado sem FCD, sem aviso. É exatamente o problema já corrigido para a
detecção do ano da CVM (`DeteccaoAnoCvmFalhouWarning`), mas não para o macro.

**Correção sugerida:** mesmo tratamento do ano da CVM (aviso global
capturado e exibido na tela).

---

### P08 — Selic/IPCA buscados por duas implementações diferentes

**Classificação:** INCONSISTÊNCIA / MANUTENÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO

**Arquivo:** `app/main.py::_buscar_macro` e `screener.py::_buscar_macro`

**Problema:** o app usa `JANELA_BUSCA_SELIC_DIAS`, `JANELA_BUSCA_IPCA_DIAS` e
`MESES_IPCA_ACUMULADO`; o screener usa `90`, `730` e `12` escritos à mão.
Mudar as constantes muda só o app. Além disso, nenhum dos dois confere se
existem de fato 12 meses de IPCA: com série incompleta, `tail(12)` multiplica
menos meses e o IPCA sai **subestimado em silêncio** (entra no WACC e na
perpetuidade).

**Correção sugerida:** uma função única (ex. em `ingest/bcb_sgs.py`) usada
pelos dois, levantando erro se houver menos de 12 leituras.

---

### P09 — Premissas do WACC que distorcem sistematicamente

**Classificação:** LIMITAÇÃO METODOLÓGICA · **Severidade:** MÉDIA · **Status:** CONFIRMADO (documentação parcial em `config.py`)

- **Pesos por valor contábil:** a proporção dívida/capital próprio vem de
  Dívida Líquida ÷ Patrimônio (contábil). O padrão é usar valor de mercado
  do capital próprio. Empresas negociadas bem acima do patrimônio (P/VP alto)
  recebem peso de dívida exagerado e um WACC mais baixo.
- **Taxa livre de risco = Selic meta** (juro de curto prazo) para descontar
  fluxos até a perpetuidade. Com a Selic em 13,75%, o WACC de todo o universo
  sobe junto com o ciclo de juros, não com o risco da empresa.
- **Benefício fiscal da dívida sempre 34%**, mesmo para empresas com
  prejuízo, que não aproveitam o benefício.

**Ação:** documentar na lista de limitações; nenhuma mudança obrigatória.

---

### P10 — Crescimento calculado com dois pontos domina o resultado

**Classificação:** LIMITAÇÃO METODOLÓGICA · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Arquivo:** `modelos/fcd.py::_taxa_crescimento_explicita`

**Problema:** o crescimento de 5 anos é o CAGR entre só dois anos (ex. 2020 e
2025), limitado a +30%. Uma base baixa em 2020 (ano atípico) leva direto ao
teto de 30% por 5 anos. Caso atual: MGLU3 com FCD de R$226,60 contra preço de
R$6,76 (divergência entre métodos de 3264%). Na verificação numérica abaixo,
o valor terminal responde por ~55% do valor da empresa mesmo num caso
moderado. Quando o FCF é negativo, a taxa cai para o IPCA e o fluxo
**negativo** é perpetuado, gerando valores muito negativos (ex. PRIO3,
CSNA3).

**Ação:** já parcialmente registrada em `docs/correcao-ano-fcd-2026-09-23.md`;
consolidar nas limitações e considerar mediana de vários anos ou teto menor.

---

### P11 — "Desconto" é, na verdade, potencial de valorização

**Classificação:** INCONSISTÊNCIA (terminologia) · **Severidade:** BAIXA · **Status:** CONFIRMADO

**Problema:** `desconto_percentual = (valor − preço) / preço`. Isso é
potencial de valorização (upside). Um "desconto de 1.614%" não existe em
finanças (desconto é limitado a 100%); o valor negativo significa "acima do
valor justo". Leitores de finanças vão estranhar.

**Correção sugerida:** renomear na interface para "Potencial" ou
"Valorização até o valor justo" (a coluna do CSV pode manter o nome).

---

### P12 — Dependências sem versão fixada

**Classificação:** MANUTENÇÃO · **Severidade:** MÉDIA · **Status:** CONFIRMADO

`requirements.txt` não fixa nenhuma versão. O yfinance muda de
comportamento com frequência, e o Streamlit Cloud instala sempre a última
versão; o próprio projeto já foi afetado (substituição automática do pyarrow
por bug de segfault). Os avisos de descontinuação conhecidos
(`use_container_width`, `st.components.v1.html`) viram erro quando essas APIs
forem removidas.

**Correção sugerida:** gerar um `requirements.txt` com versões testadas
(`pip freeze` do ambiente que passa os 444 testes) e atualizar de propósito.

---

### P13 — README desatualizado

**Classificação:** DOCUMENTAÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO

- Diz "316 testes automatizados"; são 444.
- Cita só 2 relatórios de auditoria; `docs/` tem 8.
- Não menciona nenhuma limitação metodológica (bancos sem FCD, valor
  combinado como heurística, janela do Bazin), que são justamente o
  diferencial documentado do projeto.

---

### P14 — Testes que passam com o código quebrado

**Classificação:** TESTE · **Severidade:** MÉDIA · **Status:** CONFIRMADO

- **Bazin:** as datas fabricadas são sempre 1º de dezembro, o que esconde P01.
- **Correlação:** as séries de teste compartilham o mesmo calendário, o que
  esconde P05.
- **Simulador:** não há teste com método de valor negativo, o que esconde P02.
- **Units:** não há fixture de unit no Fundamentus (P06).
- **Clique por posição:** `at.button[1]` em `test_app_main.py` quebra ou
  clica no botão errado se a ordem dos botões mudar.

---

### P15 — Premissas de data combinadas no FCD

**Classificação:** PROBLEMA DE TEMPORALIDADE / LIMITAÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO e já documentado na interface

FCF anual de 2025 + dívida líquida e número de ações de 30/06/2026 + Selic
de hoje + preço de hoje. O bloco "Datas de referência dos dados usados"
deixa isso explícito. **Não há look-ahead bias:** o projeto não faz
backtest, só usa o dado mais recente disponível.

---

### P16 — Captura de avisos com estado global no Streamlit

**Classificação:** ROBUSTEZ · **Severidade:** BAIXA · **Status:** POSSÍVEL

`warnings.catch_warnings` altera estado global do interpretador. Com duas
sessões rodando o screener ao mesmo tempo no app publicado, um aviso pode
aparecer na sessão errada ou se perder. Baixa probabilidade, consequência
pequena.

---

### P17 — Checagem de tipos não aplicada

**Classificação:** MANUTENÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO

34 erros do mypy, quase todos `DataFrame | None` usado sem estreitar no
`app/main.py` (o fluxo real checa o erro antes, então não quebram hoje) e
falsos positivos do pandas-stubs. Não há erro de execução comprovado, mas o
tipo das funções `_buscar_*` (tuplas longas com `None`) torna fácil trocar a
ordem dos valores sem nenhum aviso.

---

## 3. Verificações específicas pedidas

### FCD — exemplo numérico manual

Entradas: FCF atual 100, FCF de 5 anos atrás 80, 10 ações, Selic 13,75%,
IPCA 4,5%, Dív.Líq/PL 0,5, beta 1,0, dívida líquida 200.

- Ke = 13,75% + 1,0 × 7,47% = 21,22%; Kd pós-IR = 15,75% × 0,66 = 10,395%
- WACC = 21,22% × 2/3 + 10,395% × 1/3 = **17,61%**
- g explícito = (100/80)^(1/5) − 1 = **4,56%**; g perpetuidade = min(4,5%, 16,61%) = **4,5%**
- VP explícito + VP terminal − 200, ÷ 10 = **R$ 59,895**
- Código: **R$ 59,895** (idêntico). Valor terminal = 55% do valor da empresa.

Checklist:

| Item | Situação |
|---|---|
| Fluxo | Nem FCFF nem FCFE (P04) |
| Taxa | WACC (coerente com subtrair a dívida depois) |
| EV vs. Equity | Correto: EV − dívida líquida (corrigido em 23/09) |
| Dívida líquida negativa (caixa) | Soma ao valor, correto |
| WACC > g | Garantido pela margem de 1pp |
| Valor terminal descontado | Sim, por (1+WACC)^5, correto |
| Nominal vs. real | Tudo nominal (Selic, IPCA como g), coerente |
| Capex / capital de giro / D&A | Não separados; implícitos no 6.01/6.02 (P04) |
| Impostos | Implícitos no caixa operacional; benefício fiscal da dívida a 34% fixo (P09) |
| Financeiras | Bancos excluídos; seguradoras e holdings não (limitação documentada) |
| Look-ahead | Não há |

### Graham

`sqrt(22,5 × LPA × VPA)`, igual à documentação. LPA ≤ 0 ou VPA ≤ 0 → não
aplicável, correto. LPA é dos últimos 12 meses (inclui lucro extraordinário
sem ajuste — limitação). Coerente por ticker porque LPA e VPA vêm da página
do próprio ticker. Units: ver P06.

### Bazin

Dividendos com data do yfinance (data ex), soma dos últimos 12 meses ÷ 6%.
Janela de aplicabilidade com bug (P01). A sinalização de dividendos atípicos
está correta e não afirma o que a fonte não informa. O histórico de dividend
yield usa preço **nominal** (`auto_adjust=False`), o que está correto.

### Valor combinado

Média simples só dos aplicáveis; quando só um método se aplica, o combinado é
esse método e isso aparece em "Métodos utilizados" e na coluna Divergência
vazia. Valores negativos do FCD entram na média e podem puxar o combinado
para baixo de zero (ex. EQTL3, MBRF3), com aviso na coluna "Aviso".

### Screener

76 tickers, nenhum duplicado. PETR3/PETR4 (mesma empresa) aparecem como duas
linhas, o que é esperado. Não há critério de "aprovado": é um ranking, então
não existe o risco de aprovar ação com dado ausente; ações sem nenhum método
ficam sem valor combinado.

### Cache

Chaves verificadas: preço (ticker + período + ajuste, TTL 5 min),
dividendos (ticker, 24h), Fundamentus (ticker, 24h + versão), CVM (ano; ano
em preenchimento expira em 7 dias; FCF por CNPJ e ano com versão), catálogo
da B3 (sem prazo, com normalização na leitura). Não foi encontrado caso de
parâmetros diferentes retornando o mesmo cache.

---

## 4. Auditoria de bugs silenciosos

| Tipo | Encontrado? |
|---|---|
| Resultado válido mas economicamente errado | Sim: P02 (perda >100%), P03 (valor presente tratado como futuro), P04 (tesouraria/venda de ativo como fluxo livre) |
| Método não aplicável tratado como aplicável ou vice-versa | Sim: P01 (Bazin negado a pagadoras regulares) |
| Estatística atenuada sem erro | Sim: P05 |
| Erro capturado sem aviso | Sim: P07 |
| Dado incompleto virando número menor | Sim: P08 (IPCA com menos de 12 meses) |
| Unidade errada (units) | Possível: P06 |
| Milhares tratados como reais | Não: escala da CVM tratada (`ESCALA_MOEDA`) |
| Percentual vs. decimal | Não encontrado: Selic e IPCA divididos por 100 nos dois lugares |
| Preço ajustado misturado com nominal | Não: retornos usam ajustado, dividend yield usa nominal |
| Dívida líquida ignorada | Não (corrigido); quando ausente há aviso |
| Empresa duplicada | Não por ticker; classes da mesma empresa aparecem separadas (esperado) |

---

## 5. Matriz de problemas

| ID | Problema | Categoria | Severidade | Impacto | Correção |
|---|---|---|---|---|---|
| P01 | Janela do Bazin corta o ano mais antigo | Bug | ALTA | Bazin, combinado, ranking | Filtrar por ano civil |
| P02 | Cenário pessimista negativo (perda >100%) | Bug/financeiro | ALTA | Simulador | Piso em zero |
| P03 | Valor presente tratado como preço em 5 anos | Financeiro | ALTA | Simulador | Rever premissa ou documentar |
| P04 | FCF inclui tesouraria, venda de ativos; juros e IFRS 16 inconsistentes | Financeiro | ALTA | FCD de parte do universo | Documentar; usar capex explícito |
| P06 | Nº de ações de units | Dados (não verificado) | ALTA se confirmado | FCD e valor de mercado de units | Valor de mercado ÷ cotação |
| P05 | Correlação sem alinhar antes dos retornos | Bug estatístico | MÉDIA | Painel de correlação | Alinhar níveis primeiro |
| P07 | Falha do BCB silenciosa no screener | Robustez | MÉDIA | Ranking sem FCD | Aviso global |
| P09 | Premissas do WACC | Limitação | MÉDIA | FCD | Documentar |
| P10 | CAGR de 2 pontos | Limitação | MÉDIA | FCD | Documentar / suavizar |
| P12 | Dependências sem versão | Manutenção | MÉDIA | Deploy | Fixar versões |
| P14 | Testes cegos para P01, P02, P05, P06 | Teste | MÉDIA | Regressões | Testes específicos |
| P08 | Macro duplicado; IPCA incompleto | Inconsistência | BAIXA | WACC | Função única |
| P11 | "Desconto" = upside | Terminologia | BAIXA | Leitura | Renomear na tela |
| P13 | README desatualizado | Documentação | BAIXA | Avaliação externa | Atualizar |
| P15 | Datas diferentes no FCD | Temporalidade | BAIXA | — | Já documentado |
| P16 | Avisos com estado global | Robustez | BAIXA | Screener concorrente | Aceitar/documentar |
| P17 | mypy não aplicado | Manutenção | BAIXA | — | Tipar retornos |

## 6. Matriz por área

| Área | Situação | Problemas | Ação |
|---|---|---|---|
| Python | Bom, lint limpo | P17 | Opcional |
| Pandas | Correto nos pontos verificados | P05 | Corrigir P05 |
| ETL | Robusto (cache versionado, TTL, fallback) | P07, P08 | Corrigir P07 |
| Dados | Escalas e fusos tratados | P04, P06 | Documentar P04, verificar P06 |
| APIs | Erros tratados e mostrados | P07 | Corrigir |
| Séries temporais | Beta correto, correlação não | P05 | Corrigir |
| Graham | Correto | P06 (units) | Verificar |
| Bazin | Bug na janela | P01 | Corrigir |
| FCD | Matemática correta, entrada problemática | P04, P09, P10 | Documentar/evoluir |
| WACC | Simplificado | P09 | Documentar |
| Screener | Correto como ranking | P07, P11 | Corrigir P07 |
| Carteira | Metodologia inconsistente | P02, P03 | Corrigir |
| Correlação | Desalinhada | P05 | Corrigir |
| Streamlit | Estado e cache bem tratados | P16 | Aceitar |
| Testes | 444, mas com pontos cegos | P14 | Adicionar casos |
| Performance | Sem problema relevante (cache em disco, zip da CVM em streaming) | — | — |
| Segurança | Sem credenciais, sem eval/exec; ticker no widget vem de lista fechada | — | — |
| Documentação | Relatórios bons, README velho | P13 | Atualizar |

## 7. Conclusão

**A. Bugs confirmados:** P01 (Bazin), P02 (perda >100% no Simulador), P05
(correlação), P07 (falha do BCB silenciosa).

**B. Problemas metodológicos confirmados:** P03 (Simulador), P04 (definição
do FCF), P09 (WACC), P10 (crescimento), P11 (terminologia).

**C. Riscos potenciais:** P06 (units), P16 (concorrência), impacto real de
P01 por ticker (depende do calendário de pagamento de cada empresa).

**D. Melhorias:** P08, P12, P13, P17, remover `at.button[1]`.

**E. Testes faltantes (mais importantes):**
1. Bazin com pagamento no 1º semestre e referência no 2º.
2. Simulador com método negativo.
3. Correlação com calendários diferentes.
4. Unit: `preço × nº de ações ≈ valor de mercado do Fundamentus`.
5. Screener com o BCB fora do ar mostrando aviso.
6. IPCA com menos de 12 meses disponíveis.

**F. Correções prioritárias:** P01, P02, P05, P07; verificar P06; decidir e
documentar P03 e P04.

**G. O que NÃO precisa mudar:**
- Fórmula do FCD (verificada numericamente), a conversão para valor dos
  acionistas e a trava WACC > g.
- Exclusão de bancos do FCD por segmento (critério correto, não por falta de
  dado).
- Retornos com preço ajustado e dividend yield com preço nominal.
- Beta alinhando os preços antes dos retornos.
- Cache com versão de formato e prazo apenas para o ano da CVM ainda em
  preenchimento.
- Normalização do CNPJ com zeros à esquerda em três camadas.
- Média simples no combinado, desde que apresentada como heurística (já é).
