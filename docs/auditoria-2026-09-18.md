# Auditoria analítica do projeto — Fase 1 (2026-09-18)

Auditoria somente-leitura de todo `src/avaliador_b3/` (nenhum arquivo alterado
nesta fase). Objetivo: mapear estado de documentação, corretude, consistência,
código morto, duplicação, magic numbers e type hints, módulo a módulo, antes de
decidir o que corrigir/documentar na Fase 2.

## 1. Mapeamento módulo → teste

Todo módulo substantivo do projeto tem um arquivo de teste correspondente —
nenhum órfão encontrado.

| Módulo | Teste | Observação |
|---|---|---|
| `app/main.py` | `test_app_main.py` | dashboard Streamlit |
| `carteira.py` | `test_carteira.py` | |
| `config.py` | *(nenhum)* | arquivo de constantes, sem lógica — esperado não ter teste dedicado |
| `correlacao.py` | `test_correlacao.py` | |
| `empresa/comportamento.py` | `test_comportamento.py` | |
| `empresa/valor_mercado.py` | `test_valor_mercado.py` | |
| `graficos.py` | `test_graficos.py` | |
| `ingest/b3_universo.py` | `test_b3_universo.py` | |
| `ingest/bcb_sgs.py` | `test_bcb_sgs.py` | |
| `ingest/crosswalk_cnpj.py` | `test_crosswalk_cnpj.py` | |
| `ingest/cvm.py` | `test_cvm.py` | |
| `ingest/fundamentus.py` | `test_fundamentus.py` | |
| `ingest/gpr.py` | `test_gpr.py` | |
| `ingest/precos.py` | `test_precos.py` | |
| `modelos/bazin.py` | `test_bazin.py` | |
| `modelos/combinado.py` | `test_combinado.py` | |
| `modelos/fcd.py` | `test_fcd.py` | |
| `modelos/graham.py` | `test_graham.py` | |
| `screener.py` | `test_screener.py` | |

**Achado estrutural extra (código morto de nível de pacote)**: `src/avaliador_b3/macro/`
e `src/avaliador_b3/setorial/` existem só como `__init__.py` vazios, nunca
importados em lugar nenhum do projeto (`grep` confirmado) — sobras do
scaffolding inicial, sem função nenhuma hoje.

---

## 2. Auditoria por módulo

### `src/avaliador_b3/config.py`

**Resumo**: Arquivo central de constantes do projeto — toda decisão de valor
numérico/URL/limiar do resto do código vive aqui, com a política declarada no
próprio docstring: "Toda constante aqui deve citar a fonte que a valida".

**Documentação atual**: É a referência do projeto — cada grupo de constantes
tem um comentário extenso citando fonte, data de validação e alternativas
descartadas (ex: `DESCONTO_EXTREMO_LIMITE_SUPERIOR`, nota de validação do FCD).
Nada desatualizado.

**Achados**:
- CORRETUDE: nenhum (arquivo de dados, sem lógica executável).
- CONSISTÊNCIA: é o padrão-ouro do projeto, não o desvio.
- **CÓDIGO MORTO**: `DATA_CACHE_DIR` (linha 8) é definida mas nunca importada
  em nenhum outro módulo — confirmado via grep em `src/`/`tests/`. O diretório
  `data/cache/` que ela aponta existe no disco só com um `.gitkeep`, vazio.
  Todo cache real do projeto usa `data/raw/<fonte>/`. Provável sobra do
  scaffolding inicial, junto com `macro/`/`setorial/` (achado da seção 1).
- DUPLICAÇÃO: nenhuma.
- MAGIC NUMBERS: nenhum, por construção.
- TYPE HINTS: nenhuma função pública.

---

### `src/avaliador_b3/ingest/b3_universo.py`

**Resumo**: Adapter para o universo de "ações principais" (carteira teórica do
Ibovespa) e segmento de listagem de cada uma, via API não-documentada da B3.

**Documentação atual**: Docstring de módulo completa. Funções privadas
triviais (`_montar_url`, `_baixar_pagina`) sem docstring própria, mas
autoexplicativas. `obter_universo_ibovespa` documenta a política de cache
(sem TTL, revisão quadrimestral) corretamente.

**Achados**:
- CORRETUDE: nenhum.
- CONSISTÊNCIA: paginação **sem** `delay_segundos`/`time.sleep` entre páginas
  — diferente de `fundamentus.py`/`precos.py`, que aplicam delay antes de
  requisições reais. **Correção (2026-09-18, durante o Lote 1)**: a primeira
  versão deste achado afirmava que `crosswalk_cnpj.py` "já aplica delay entre
  páginas" — isso estava ERRADO, confirmado só ao investigar o item 6 do
  Lote 1: nenhum dos dois módulos de paginação da B3 (`b3_universo.py` nem
  `crosswalk_cnpj.py`) tinha delay entre páginas antes do Lote 1, apesar de
  `crosswalk_cnpj.py` paginar até ~36 vezes contra a API. Corrigido no Lote 1
  — os dois módulos agora aplicam `DELAY_PAGINACAO_B3_SEGUNDOS` entre páginas
  via `ingest/_paginacao.py`.
- CÓDIGO MORTO: nenhum.
- **DUPLICAÇÃO**: `_montar_url`/`_baixar_pagina`/loop de paginação (linhas
  ~36-58, ~110-121) são quase idênticos ao mesmo trio em `crosswalk_cnpj.py`
  (linhas ~69-85, ~126-137) — mesmo padrão de URL base64-JSON, mesmo
  tratamento de JSON inválido, mesmo loop de páginas. Candidato a um helper
  compartilhado.
- MAGIC NUMBERS: `tamanho_pagina: int = 120` (linha ~95) hardcoded, sem
  comentário do porquê, não está em config.py.
- TYPE HINTS: completos nas funções públicas.

---

### `src/avaliador_b3/ingest/bcb_sgs.py`

**Resumo**: Adapter para séries temporais do SGS do Banco Central (Selic,
IPCA, câmbio, M2).

**Documentação atual**: Docstring de módulo boa. `obter_serie` documenta a
política de cache, mas **não menciona `data_inicial`/`data_final` como parte
do contrato de cache** — ligado ao achado de corretude abaixo.

**Achados**:
- **CORRETUDE — ALTA PRIORIDADE**: `_caminho_cache` (linha ~63-64) gera a
  chave do cache **só a partir de `codigo`**, ignorando `data_inicial`/
  `data_final`. `app/main.py` (`_buscar_cambio_correlacao`) chama `obter_serie`
  com uma janela ROLANTE (recalculada a cada execução a partir de "hoje").
  A primeira chamada grava `data/raw/bcb/serie_1.csv` com a janela daquele
  dia; toda chamada seguinte (em qualquer dia futuro) **lê esse mesmo
  arquivo cacheado**, porque a única checagem é `caminho.exists()`. Resultado:
  a série de câmbio usada em "Correlação com fatores externos" fica **presa
  na janela do primeiro fetch, indefinidamente**, silenciosamente — só
  resolveria com `forcar_atualizacao=True`, que nada no código dispara
  automaticamente. Nenhum teste exercita esse cenário (`test_bcb_sgs.py` só
  varia `codigo`, nunca `data_inicial`/`data_final`). Contraste direto:
  `ingest/precos.py` já documenta explicitamente (linhas ~68-81) por que
  parâmetros que mudam o resultado (período, ajuste) precisam entrar na
  chave do cache — `bcb_sgs.py` não segue essa mesma disciplina apesar de
  ter parâmetro variável equivalente.
  **Correção sugerida**: incluir `data_inicial`/`data_final` na chave de
  `_caminho_cache` (hash ou string formatada).
- CONSISTÊNCIA: ver achado acima — é o oposto do padrão documentado em
  `precos.py`.
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: padrão de cache-com-TTL é conceitualmente igual a
  `gpr.py`/`b3_universo.py` — esperado, não duplicação problemática.
- MAGIC NUMBERS: nenhum.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/ingest/crosswalk_cnpj.py`

**Resumo**: Liga ticker (B3) a CNPJ/código CVM/segmento setorial, conectando
`b3_universo.py` a `cvm.py`.

**Documentação atual**: Docstring de módulo excelente — documenta a
investigação e a validação manual contra os 76 tickers reais do Ibovespa.
Funções públicas com docstring clara.

**Achados**:
- CORRETUDE (nota, prioridade **baixa**): `resolver_cnpj` devolve
  `codigo_cvm` cujo TIPO pode variar entre execução fresca (tipo bruto do
  JSON da B3) e execução com cache (`obter_catalogo_emissores` lê com
  `dtype=str`, linha ~124) — inconsistência de tipo latente. Nenhum
  consumidor atual compara `codigo_cvm` por tipo (grep não achou uso
  downstream que quebraria hoje).
- CONSISTÊNCIA: ver duplicação com `b3_universo.py` abaixo.
- **CÓDIGO MORTO**: `obter_crosswalk_ibovespa` (linhas ~196-234) é
  totalmente implementada e testada (4 testes), mas **não é chamada por
  nenhum código de produção** — nem `main.py`, nem `screener.py`. O app
  resolve CNPJ ticker-a-ticker via `resolver_cnpj` dentro de um loop
  (`screener.py`), nunca em lote. Código morto do ponto de vista do app,
  apesar de testado.
- **DUPLICAÇÃO**: `_montar_url`/`_baixar_pagina`/paginação (linhas ~69-85,
  ~126-137) duplicam `b3_universo.py` quase linha a linha — ver achado lá.
- MAGIC NUMBERS: `tamanho_pagina: int = 100` (linha ~112) hardcoded, mesmo
  padrão não documentado que `b3_universo.py` tem com 120.
- TYPE HINTS: completos (retorno genérico `dict`/`pd.DataFrame` em alguns
  casos, aceitável dado o padrão do projeto).

---

### `src/avaliador_b3/ingest/cvm.py`

**Resumo**: Adapter para demonstrações financeiras da CVM (Lucro Líquido e
Fluxo de Caixa Livre), processando o zip anual do DFP linha a linha sem
carregar tudo em memória.

**Documentação atual**: Docstring de módulo muito boa — documenta as duas
decisões não-óbvias de design (dois períodos por arquivo, código de conta
não-fixo entre tipos de empresa). Funções públicas bem documentadas.

**Achados**:
- **CORRETUDE — MÉDIA PRIORIDADE**: `_valor_conta` (linhas ~158-162)
  levanta `ContaLucroNaoEncontrada` quando `ESCALA_MOEDA` é desconhecida —
  mas essa função é **compartilhada com o caminho de Fluxo de Caixa**
  (`_fcf_do_periodo`, chama `_valor_conta` para as contas CFO/CFI, que não
  são "Lucro"). Se uma conta 6.01/6.02 tiver escala monetária não mapeada em
  `FATOR_ESCALA_MOEDA_CVM`, o erro levantado cita "Lucro Líquido" num
  contexto de Fluxo de Caixa — mensagem enganosa. `app/main.py` e
  `screener.py` só capturam `(CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada)`
  ao redor de `obter_fluxo_caixa_livre`, então esse erro "vazado" não seria
  pego por esse catch específico — mas ambos os call sites têm um
  `except Exception` genérico logo depois que evita crash. `test_cvm.py`
  já fixa esse comportamento como atual (não é lapso de teste).
  **Correção sugerida**: `_valor_conta` receber a classe de exceção a
  levantar como parâmetro, ou existir uma exceção genérica reaproveitável
  pelos dois caminhos.
- CONSISTÊNCIA: segue bem o padrão do projeto.
- CÓDIGO MORTO: nenhum.
- **DUPLICAÇÃO**: dois pares de funções quase-gêmeas — `_linhas_da_empresa`
  vs `_linhas_da_empresa_dfc` (mesma leitura de zip/CSV/filtro por CNPJ, só
  muda o nome do membro do zip e a exceção) e `_montar_resultado` vs
  `_montar_resultado_fcf` (mesmo split ÚLTIMO/PENÚLTIMO, mesma extração de
  metadados da primeira linha).
- MAGIC NUMBERS: `CODIGO_CFO_CVM = "6.01"`/`CODIGO_CFI_CVM = "6.02"`
  hardcoded no módulo (não em config.py, diferente de `CONTA_LUCRO_POR_ACAO_CVM`).
  `TAMANHO_PEDACO_DOWNLOAD = 256 * 1024` também local, sem comentário do
  porquê desse valor.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/ingest/fundamentus.py`

**Resumo**: Adapter via scraping (sem API oficial) para indicadores
fundamentalistas (ROE, margem, LPA/VPA, dívida, etc.) do Fundamentus.

**Documentação atual**: Muito bem documentada — antecipa os dois caminhos de
falha no próprio docstring de módulo.

**Achados**:
- **CORRETUDE — ALTA PRIORIDADE, JÁ OCORREU EM PRODUÇÃO**: o cache em disco
  (`_caminho_cache`) **não tem TTL nem versionamento de schema**. Quando
  `CAMPOS_FUNDAMENTUS`/`CAMPOS_FUNDAMENTUS_OPCIONAIS` ganham um campo novo —
  aconteceu duas vezes nesta mesma sessão (Valor de Mercado/Firma) — qualquer
  JSON já cacheado em `data/raw/fundamentus/*.json` fica permanentemente
  desatualizado, sem o campo novo. `obter_indicadores` devolve esse dict
  incompleto direto do cache, e o primeiro consumidor que acessar a chave
  nova recebe `KeyError`. **Isso literalmente aconteceu** (`KeyError:
  'divida_liquida'`, ao vivo no Streamlit, corrigido só apagando o cache
  manualmente). Diferente de `b3_universo.py`/`crosswalk_cnpj.py`, que
  documentam "sem TTL" como decisão deliberada (dado muda pouco por
  natureza), `fundamentus.py` não documenta essa política — e o dado aqui é
  mais volátil (muda por trimestre de resultado).
  **Correção sugerida**: TTL (ex: 24h, já que fundamentalistas atualizam no
  máximo diariamente) e/ou invalidar cache quando o schema mudar (gravar
  versão de schema no JSON, comparar ao ler).
- CONSISTÊNCIA: nenhum outro achado.
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma relevante.
- MAGIC NUMBERS: nenhum — headers/codificação vêm de config.py.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/ingest/gpr.py`

**Resumo**: Adapter para o índice GPR (Geopolitical Risk Index) via download
direto de planilha Excel, sem API.

**Documentação atual**: Docstring de módulo boa, inclui uma pegadinha real já
documentada (colunas de metadados desalinhadas na planilha).

**Achados**:
- CORRETUDE: nenhum bug.
- CONSISTÊNCIA (achado leve): a docstring de `obter_gpr` chama a série
  "diaria" de "atualizada diariamente", mas o cache não tem TTL — a
  justificativa pra isso ("arquivo raramente muda") só existe no call site
  (`app/main.py`), não em `gpr.py` onde a decisão de cache é tomada. Sem
  evidência de que isso já causou problema (diferente do achado equivalente
  em `fundamentus.py`) — é lacuna de documentação, não bug confirmado.
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma relevante.
- MAGIC NUMBERS: nenhum.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/ingest/precos.py`

**Resumo**: Adapter para preço histórico e dividendos de ações via yfinance —
o mais "combatido" do projeto (documenta 3 bugs reais já corrigidos:
Dividend Yield com preço ajustado, cache sem período/ajuste na chave,
exceções não-documentadas do yfinance).

**Documentação atual**: O módulo mais bem documentado do projeto depois de
`config.py` — cada decisão não-óbvia cita o bug real que a motivou.

**Achados**:
- CORRETUDE: nenhum achado direto. **Nota de verificação cruzada** (relevante
  pros achados de `graficos.py`/`app/main.py` abaixo): `obter_historico`
  já levanta `TickerInvalido` explicitamente se o histórico vier vazio
  (linha ~150-151), ANTES de gravar no cache — ou seja, um histórico de
  preço vazio nunca deveria chegar a `graficos.py`/`app/main.py` pelo
  caminho normal (fetch novo). O único jeito de um DataFrame vazio escapar
  seria uma leitura de cache que devolvesse um CSV com só cabeçalho, sem
  linhas (corrupção/escrita interrompida) — não reproduzível no código
  atual, mas não impossível por definição. Já `obter_dividendos` trata
  vazio como **resultado válido, por design** (ação sem histórico de
  dividendo) — os consumidores de dividendo (`modelos/bazin.py`,
  `graficos.calcular_dividend_yield_por_ano`) já tratam isso corretamente e
  com teste.
- CONSISTÊNCIA: é a referência positiva do projeto — deveria ser o modelo
  pros outros módulos de `ingest/` (ver achado de `bcb_sgs.py`).
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma relevante.
- MAGIC NUMBERS: nenhum.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/modelos/graham.py`

**Resumo**: Fórmula de Benjamin Graham (VI = √(22,5 × LPA × VPA)) — só
aplicável com LPA e VPA ambos positivos.

**Documentação atual**: Completa e precisa, bate exatamente com o código.

**Achados**: nenhum em nenhuma categoria. Guard clauses cobrem `None` e
valores não-positivos antes de `math.sqrt`; testado exaustivamente
(inclusive o caso de produto de dois negativos "escapando" da regra
`lpa<=0 or vpa<=0`). Type hints completos, sem magic number (`FATOR_GRAHAM`
vem de config.py), sem duplicação.

---

### `src/avaliador_b3/modelos/bazin.py`

**Resumo**: Preço-teto pelo Método Bazin (dividendos 12 meses / yield mínimo
de 6%), exigindo histórico de dividendo ininterrupto nos últimos N anos civis.

**Documentação atual**: Completa — cita a fonte externa do critério de
aplicabilidade. Todas as 4 funções documentadas.

**Achados**:
- CORRETUDE (prioridade **baixa**, defensivo): `calcular_preco_teto_bazin`
  acessa `dividendos["data"].dtype` antes de checar se o DataFrame está
  vazio. Só quebraria (`KeyError`) se um chamador futuro passasse um
  DataFrame sem a coluna `data` — o único produtor real
  (`ingest.precos.obter_dividendos`) já garante esse schema mesmo quando
  vazio.
- CONSISTÊNCIA: normalização de timezone (`tz_localize`) é peculiaridade só
  desse módulo, mas bem documentada com a causa raiz (yfinance devolve
  tz-aware).
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma com os outros modelos.
- MAGIC NUMBERS: nenhum (`ANOS_HISTORICO_MINIMO_BAZIN`/`YIELD_MINIMO_BAZIN`
  vêm de config.py).
- TYPE HINTS: completos.

---

### `src/avaliador_b3/modelos/fcd.py`

**Resumo**: Fluxo de Caixa Descontado — projeta FCF por 5 anos mais
perpetuidade (Gordon Growth), descontados pelo WACC (CAPM), dividido pelo
número de ações. Desenhado para ser "quase sempre aplicável".

**Documentação atual**: O módulo mais bem documentado dos 6 de
`modelos/`+`empresa/` — cada função privada explica o "porquê", não só o
"o quê". Nenhuma desatualização.

**Achados**: nenhum em nenhuma categoria. Os 3 pontos de falha documentados
(`fcf_atual is None`, `numero_acoes` ausente/não-positivo, `wacc<=0`) são
checados antes de qualquer divisão; a garantia matemática de que
`WACC - taxa_perpetuidade` nunca se aproxima de zero é código, não só
comentário (`MARGEM_SEGURANCA_PERPETUIDADE_FCD`). Type hints completos
inclusive nas privadas, sem magic number solto, sem duplicação.

---

### `src/avaliador_b3/modelos/combinado.py`

**Resumo**: Combina Graham/Bazin/FCD numa média simples, usando só os
métodos marcados `aplicavel` — nunca uma média fixa dos três.

**Documentação atual**: Completa, incluindo a intenção de transparência
(`metodos_utilizados` existe pra nunca ser caixa-preta).

**Achados**: nenhum em nenhuma categoria. `CHAVE_VALOR_POR_METODO` resolve
corretamente a assimetria de nome de chave entre Bazin (`preco_teto`) e
Graham/FCD (`valor_justo`), testado explicitamente. Valores negativos somam
normalmente, sem filtro de sinal acidental.

---

### `src/avaliador_b3/empresa/comportamento.py`

**Resumo**: Bloco "comportamento da ação" — volatilidade anualizada, Beta vs.
Ibovespa e volume médio negociado, sobre DataFrames de histórico já
buscados.

**Documentação atual**: Docstring de módulo clara. `calcular_volatilidade_anualizada`
e `calcular_beta` documentam explicitamente quando devolvem `None`.
`calcular_volume_medio` tem uma docstring de uma linha só, sem mencionar
nenhum caso de borda — diferente das duas vizinhas.

**Achados**:
- **CORRETUDE — ALTA PRIORIDADE, CONFIRMADO, VISÍVEL NA UI**:
  `calcular_volume_medio` (linhas ~21-23) não trata `historico` vazio.
  `historico["Volume"].mean()` sobre uma Series vazia devolve `NaN` (não
  levanta erro), e `float(NaN)` é um float válido — a função devolve `nan`
  silenciosamente, diferente de `calcular_volatilidade_anualizada` e
  `calcular_beta` no MESMO módulo, que devolvem `None` explicitamente pro
  caso equivalente. **Impacto confirmado**: `app/main.py` (linha ~742-744)
  chama `st.metric("Volume médio (3m)", f"{volume_medio:,.0f}"...)` sempre
  que a busca não teve erro — mas isso só cobre falha de *busca*, não
  "busca funcionou mas devolveu poucas/nenhuma linha" (ticker com histórico
  mais curto que a janela, gap de dados). `f"{nan:,.0f}"` formata
  literalmente como `"nan"` — **a UI mostraria "Volume médio (3m): nan"**
  pro usuário, em vez de "N/D" como o resto do projeto trata dado ausente.
  Sem teste cobrindo esse caso (as duas funções vizinhas têm teste
  equivalente; essa não tem).
  **Correção sugerida**: `if historico.empty: return None`, igual às
  vizinhas, e mudar o tipo de retorno pra `float | None`.
- CONSISTÊNCIA: `DIAS_UTEIS_POR_ANO = 252` (linha ~18) é uma constante de
  projeto definida **localmente** neste módulo, não em config.py —
  diferente de toda outra constante numérica do projeto, que vive em
  config.py com comentário de fonte (violação direta da política declarada
  no topo do próprio config.py).
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma.
- MAGIC NUMBERS: `DIAS_UTEIS_POR_ANO = 252` — mesmo achado de CONSISTÊNCIA
  acima.
- TYPE HINTS: completos hoje; `calcular_volume_medio` ficaria com hint
  impreciso (`-> float`) depois de corrigir o bug (deveria virar
  `-> float | None`).

---

### `src/avaliador_b3/empresa/valor_mercado.py`

**Resumo**: Valor de Mercado (preço × número de ações) e Valor de Firma
(+ dívida líquida absoluta) — aritmética pura, sem estimativa/premissa.

**Documentação atual**: Completa, incluindo a nuance de dívida líquida
negativa (posição de caixa líquido, valor real, não tratado como ausência).

**Achados**: nenhum em nenhuma categoria — os 3 guards de `None` e o caso de
dívida negativa já são testados explicitamente. Sem magic number (não há
nenhuma constante — só multiplicação/soma).

---

### `src/avaliador_b3/carteira.py`

**Resumo**: Simulador de carteira — deriva 3 cenários (otimista/base/
pessimista) por ação a partir dos valores do screener, projeta retorno em
R$/% para um valor investido, calcula CAGR implícito e ganho nominal vs.
real (deflacionado pelo IPCA).

**Documentação atual**: Excelente — docstring de módulo explica a origem dos
3 cenários e a regra "sem método aplicável = sem cenário, nunca zero
disfarçado". Todas as 6 funções públicas documentadas com o porquê.

**Achados**:
- CORRETUDE (prioridade **baixa**): `calcular_ganho_nominal_vs_real`
  (linha ~162) faz `valor_destino / (1 + ipca_anual) ** anos` sem guardar
  `ipca_anual == -1` exato (causaria `ZeroDivisionError`) — cenário sem
  correspondência real (IPCA de -100%), já que a série vem do BCB.
- CORRETUDE (nota de design, não bug): `montar_tabela_carteira` confia que
  todo ticker em `investimentos` existe em `tabela_screener` — já
  documentado explicitamente na docstring como premissa garantida pela UI
  (multiselect restrito), não um descuido.
- CONSISTÊNCIA: módulo-modelo — usa `for cenario in CENARIOS:` pra evitar
  repetir 3 blocos, padrão que `correlacao.py` NÃO segue pro problema
  equivalente (ver achado lá).
- CÓDIGO MORTO: nenhum — todas as funções são usadas por `app/main.py`.
- DUPLICAÇÃO: nenhuma relevante.
- MAGIC NUMBERS: nenhum (`*100` é conversão decimal→percentual padrão).
- TYPE HINTS: completos.

---

### `src/avaliador_b3/correlacao.py`

**Resumo**: Correlação de Pearson entre retorno diário de uma ação e 3
fatores externos (petróleo Brent, câmbio, GPR) numa janela de 2 anos —
lógica pura.

**Documentação atual**: Excelente, talvez o segundo módulo mais bem
documentado do projeto depois de `config.py`. `_retornos_diarios` documenta
um bug real já encontrado e corrigido (GPR com leitura 0.0 gerando `inf`
que contamina a série inteira) — exemplo exato do padrão de profundidade
que se quer replicar no resto do projeto.

**Achados**:
- CORRETUDE: nenhum — overlap insuficiente, desvio padrão zero e divisão
  por zero num nível isolado já são tratados e testados.
- **CONSISTÊNCIA/DUPLICAÇÃO**: `calcular_correlacoes_fatores` (linhas
  ~141-175) repete o mesmo bloco if/else 3 vezes (petróleo/câmbio/GPR) —
  mesma estrutura, só variando nome de coluna e mensagem de erro.
  `carteira.py` (`CENARIOS`) já usa loop-sobre-lista pro problema
  equivalente; esse módulo poderia adotar o mesmo padrão e remover ~30
  linhas repetidas.
- CÓDIGO MORTO: nenhum.
- MAGIC NUMBERS: nenhum (limiares vêm de config.py).
- TYPE HINTS: completos.

---

### `src/avaliador_b3/graficos.py`

**Resumo**: Funções puras de preparação de dado pros gráficos do dashboard
(normalização base-100, curvas de projeção, agregação de dividendos,
dividend yield) — não desenha nada, só transforma dado pro plotly em
`app/main.py`. *(Editado nesta mesma sessão: `montar_mapa_conflitos` foi
removido junto com o Monitor de conflitos — auditoria já reflete o estado
atual.)*

**Documentação atual**: Boa, docstring de módulo já atualizada
corretamente após a remoção. As 6 funções públicas documentam o porquê.

**Achados**:
- **CORRETUDE — MÉDIA PRIORIDADE** (recalibrado após investigação cruzada
  com `ingest/precos.py`): `normalizar_base_100` (linha ~20) —
  `serie.dropna().iloc[0]` levanta `IndexError` se `serie` vier vazia ou só
  com `NaN`. `app/main.py` chama essa função em ~4 lugares (preço vs.
  Ibovespa, preço vs. petróleo) checando só `erro_*` (setado quando
  `_buscar_historico` levanta exceção), nunca `.empty` no resultado.
  **Porém**: confirmei em `ingest/precos.py` que `obter_historico` já
  levanta `TickerInvalido` explicitamente se o histórico vier vazio, ANTES
  de gravar no cache — então, no caminho normal (fetch novo), essa condição
  não é alcançável hoje. O único jeito de escapar seria uma leitura de
  cache corrompida (CSV com só cabeçalho, sem linhas). Rebaixado de Alta
  pra Média por isso, mas mantido como achado porque é a mesma FORMA de bug
  (contrato implícito não verificado no ponto de consumo) que já se
  concretizou duas vezes nesta sessão em outros módulos (`KeyError` do
  Fundamentus, e o mesmo padrão aqui). **Sugestão**: `if serie.dropna().empty:
  return serie` (ou erro mais claro) em vez de deixar o `IndexError` cru
  estourar — defesa barata dado o histórico do projeto com esse tipo de bug.
- CORRETUDE (prioridade **baixa**): `projetar_curva_linear` —
  `incremento * t / anos` com `anos=0` levanta `ZeroDivisionError` (mesmo
  com numerador zero). Não alcançável hoje (único caller usa
  `HORIZONTE_PROJECAO_FCD_ANOS`, fixo em 5) — mas note a inconsistência:
  `carteira.calcular_cagr_implicito` já guarda `anos<=0` explicitamente pro
  mesmo tipo de input, `graficos.py` não guarda nada equivalente.
- CONSISTÊNCIA: nenhuma divergência de padrão além do achado acima.
- CÓDIGO MORTO: nenhum — confirmado que a remoção do mapa de conflitos foi
  completa (zero resquício de `montar_mapa_conflitos`/imports do plotly).
- DUPLICAÇÃO: a duplicação entre `projetar_curva_composta`/
  `projetar_curva_inflacao` é intencional e já documentada no próprio
  docstring ("matematicamente idêntica... nome e uso semanticamente
  diferentes") — não é um achado, é uma decisão de design explícita.
- MAGIC NUMBERS: nenhum.
- TYPE HINTS: completos.

---

### `src/avaliador_b3/screener.py`

**Resumo**: Roda o pipeline completo de valuation (Graham/Bazin/FCD/
combinado) pras ~76 ações do Ibovespa, uma de cada vez, gravando
incrementalmente em `data/processed/screener.csv` — sem reimplementar
lógica de cálculo, só orquestração com isolamento de erro por ação.

**Documentação atual**: Excelente — docstring de módulo explica o
processamento incremental (restrição de RAM), isolamento de erro, e quais
fontes são compartilhadas vs. buscadas por ação.

**Achados**:
- CORRETUDE: nenhum bug — o mesmo tipo de risco de `IndexError` sobre
  `historico["Close"].iloc[-1]` que existe em `graficos.py`/`app/main.py`
  **já é coberto aqui** por um `except Exception` genérico em
  `rodar_screener`, testado explicitamente
  (`test_rodar_screener_trata_excecao_inesperada_sem_derrubar_as_demais`).
  Vira uma linha de erro na tabela, não uma queda do processo — bom
  exemplo de rede de segurança que `app/main.py` NÃO tem pro mesmo tipo de
  falha (ver achado de `app/main.py` abaixo).
- CONSISTÊNCIA: segue os mesmos padrões de exceção customizada dos módulos
  `ingest/`.
- CÓDIGO MORTO: nenhum.
- DUPLICAÇÃO: nenhuma — reaproveita adapters/modelos existentes.
- MAGIC NUMBERS: nenhum.
- TYPE HINTS: completos, inclusive nas privadas.

---

### `src/avaliador_b3/app/main.py`

**Resumo**: Único arquivo de UI/orquestração do projeto — script Streamlit
que só chama os adapters e módulos de cálculo e organiza o resultado em 3
abas (Analisar uma ação, Screener, Simulador de carteira); não reimplementa
lógica de cálculo. *(Editado nesta mesma sessão: aba "Monitor de conflitos"
removida por completo — auditoria já reflete o estado atual.)*

**Documentação atual**: Docstring de módulo presente e precisa. Das ~20
funções privadas (`_algo`), a documentação é **inconsistente**: `_buscar_historico_ibovespa`,
`_buscar_indicadores_fundamentus`, `_buscar_dividendos`, `_buscar_cnpj`,
`_buscar_fcf`, `_cartao_metodo`, `_cartao_correlacao` não têm docstring
nenhuma, enquanto `_buscar_historico`, `_buscar_historico_petroleo`,
`_buscar_macro`, `_buscar_segmento_setorial`, `_carregar_screener_salvo`,
`_aviso_screener_vazio`, `_ativar_aba`, `_delta_percentual_upside`,
`_fmt`/`_fmt_bilhoes`, `_widget_avancado_tradingview` têm docstrings ricas.
As que existem batem com o comportamento real — nada desatualizado.

**Achados**:
- **CORRETUDE — MÉDIA PRIORIDADE** (recalibrado, ver nota cruzada com
  `graficos.py`/`ingest/precos.py` acima): nenhum ponto do arquivo verifica
  `.empty` nos DataFrames de histórico antes de indexá-los — só o par
  `erro_*` é checado. Padrão se repete em ~7 locais: `preco_atual` (linha
  ~540), `historico`/volume-volatilidade (~742-743), `historico_beta`/
  `historico_ibovespa_beta` (~778-789), `historico_acao_petroleo`/
  `historico_petroleo_janela` (~834-844), `historico_max` (~885-892),
  `historico_acao_correlacao`/`historico_petroleo` (~1061-1062). Como já
  investigado, `obter_historico` garante não-vazio no caminho normal — risco
  real está limitado a cache corrompido, mas é o mesmo formato de bug já
  visto nesta sessão duas vezes.
- CORRETUDE (prioridade **média**): chamada de método de valuation
  inconsistente entre si — Graham é chamado direto (linha ~572), sem
  pré-checagem; Bazin e FCD (linhas ~573-597) são pré-checados com um dict
  "não aplicável" **montado à mão dentro do próprio main.py**, em vez de
  deixar as funções de `modelos/` tratar `None` internamente do jeito que
  presumivelmente Graham já trata. Não quebra nada hoje, mas é um contrato
  duplicado e frágil — se o dict "real" ganhar uma chave nova no futuro, os
  2 fallbacks manuais em main.py não a teriam.
- CORRETUDE (prioridade **média**): texto do expander "Como funciona esse
  cálculo?" (linha ~641-643) cita "retorno de 6% ao ano" (Bazin) como texto
  hardcoded na UI — se `YIELD_MINIMO_BAZIN` mudar, esse texto vira
  documentação errada, silenciosamente, sem teste/lint que acuse.
- CORRETUDE (prioridade **baixa**): severidade de erro inconsistente entre
  fontes — falha de preço usa `st.error` (linhas ~536-550), falha de
  indicadores/dividendos/CNPJ/macro usa `st.warning` (~822-825), sem
  comentário explicando a diferença de severidade visual (pode ser
  intencional, mas não documentado).
- CONSISTÊNCIA: nomenclatura pt-BR consistente em todo o arquivo. Uso de
  `@st.cache_data(ttl=3600)` é consistente e bem justificado (só buscas que
  NÃO dependem do ticker são decoradas). A única inconsistência real de UI
  é a severidade de erro acima.
- CÓDIGO MORTO: nenhum — todas as ~20 funções privadas e todos os ~50
  imports são usados (conferido nome a nome).
- **DUPLICAÇÃO**:
  - O bloco que monta "Preço vs. Ibovespa" (~775-796) e o bloco que monta
    "Comparando com Petróleo" (~831-852) são quase idênticos: `go.Figure()`
    + dois `go.Scatter` com `normalizar_base_100` + `update_layout` com os
    mesmos 4 parâmetros. Extraível num helper único — remove ~20 linhas.
    Achado de duplicação com melhor retorno do arquivo.
  - Padrão "`tabela = _carregar_screener_salvo(...)`; `if tabela is None:
    _aviso_screener_vazio(...)`" repete 3 vezes (uma por seção que depende
    do screener) — já parcialmente fatorado via `_aviso_screener_vazio`,
    mas o par carregar+checar-None poderia virar um único helper.
  - `st.dataframe(..., column_order=..., column_config={...}, ...)` repete
    4 vezes com colunas diferentes — boilerplate inerente ao Streamlit,
    baixo valor em fatorar.
- **MAGIC NUMBERS**: `.tail(12)` (meses de IPCA acumulado, linha ~252);
  `timedelta(days=90)`/`timedelta(days=730)` (janelas Selic/IPCA, linhas
  ~242/249); `JANELAS_COMPARACAO_PETROLEO = {"2 anos": "2y", ...}` definida
  no meio do script (linha ~800) em vez de config.py — inconsistente com o
  padrão do projeto de centralizar constantes de "janela" lá; `"~228
  requisições reais"` no aviso do Screener (linha ~1083), texto informativo
  que fica desatualizado se a lista do Ibovespa mudar de tamanho (baixa
  prioridade, é só texto); defaults de UI/cores hex (baixa prioridade,
  presentation-only).
- **TYPE HINTS**: faltando retorno em `_buscar_dividendos` (linha ~198),
  `_cartao_metodo` (linha ~306), `_cartao_correlacao` (linha ~319). Resto
  do arquivo com hints completos.

**Cobertura de teste**: `test_app_main.py` tem 6 testes focados
(degradação do dropdown, busca automática, período separado de "Preço
atual", fusão da correlação, delta de upside) — bem direcionados a bugs
reais já encontrados no navegador. **Sem teste** cobrindo: aba Screener, aba
Simulador de carteira, seção "Comparando com Petróleo" (incluindo o
comportamento "sticky" entre pills), seção "Saúde financeira"/Valor de
Mercado-Firma, ou o caminho de erro individual de cada busca. Não é um bug,
mas é uma lacuna de cobertura real dado o tamanho do arquivo.

---

## 3. Resumo executivo

### 3.1 Lista priorizada de achados de CORRETUDE (projeto inteiro)

| # | Prioridade | Módulo | Local | Achado |
|---|---|---|---|---|
| 1 | **ALTA** | `empresa/comportamento.py` | `calcular_volume_medio`, ~21-23 | Devolve `NaN` (não `None`) pra histórico vazio — UI mostra literalmente "Volume médio (3m): nan". Confirmado o caminho completo até `app/main.py:~744`. Sem teste cobrindo. |
| 2 | **ALTA** | `ingest/bcb_sgs.py` | `_caminho_cache`, ~63-64 | Chave de cache ignora `data_inicial`/`data_final` — série de câmbio da "Correlação com fatores externos" fica presa na janela do primeiro fetch, pra sempre, silenciosamente. |
| 3 | **ALTA** | `ingest/fundamentus.py` | `_caminho_cache`, ~109-110 | Cache sem TTL nem versionamento de schema — **já causou** `KeyError: 'divida_liquida'` real, ao vivo, nesta sessão, quando o schema de campos ganhou entrada nova. |
| 4 | Média | `graficos.py` + `app/main.py` | `normalizar_base_100` (~20) + ~7 pontos de indexação em main.py | `IndexError`/similar não tratado se DataFrame de histórico vier vazio — mas investigação confirmou que `ingest/precos.py` já impede isso no caminho normal (fetch novo sempre levanta exceção se vazio). Risco real limitado a cache corrompido; mantido pela mesma FORMA de bug já vista 2x nesta sessão. |
| 5 | Média | `ingest/cvm.py` | `_valor_conta`, ~158-162 | Levanta a exceção errada (`ContaLucroNaoEncontrada`) quando chamada pelo caminho de Fluxo de Caixa — mensagem enganosa, não crasha (catch genérico downstream evita). |
| 6 | Média | `app/main.py` | ~572 vs. ~573-597 | Graham chamado direto; Bazin/FCD pré-checados com dict "não aplicável" montado à mão em main.py — contrato duplicado, frágil a mudança futura no shape desses retornos. |
| 7 | Média | `app/main.py` | ~641-643 | Texto da UI cita "6% ao ano" (Bazin) hardcoded — pode dessincronizar de `YIELD_MINIMO_BAZIN`. |
| 8 | Baixa | `modelos/bazin.py` | ~63 | Acessaria `dividendos["data"].dtype` antes de checar vazio se um chamador futuro violasse o contrato de schema (produtor real já garante). |
| 9 | Baixa | `graficos.py` | `projetar_curva_linear`, ~51 | `ZeroDivisionError` se `anos=0` — não alcançável hoje (caller usa constante fixa=5); inconsistente com `carteira.py`, que já guarda o mesmo tipo de input. |
| 10 | Baixa | `carteira.py` | `calcular_ganho_nominal_vs_real`, ~162 | `ZeroDivisionError` se `ipca_anual == -1` exato — cenário sem correspondência real. |
| 11 | Baixa | `ingest/crosswalk_cnpj.py` | `resolver_cnpj` vs. cache, ~161-168/124 | `codigo_cvm` pode ter tipo inconsistente (int vs. str) entre execução fresca e com cache. Sem consumidor afetado hoje. |
| 12 | Baixa | `app/main.py` | ~536-550 vs. ~822-825 | Severidade de erro inconsistente (`st.error` vs. `st.warning`) entre fontes, sem justificativa documentada. |

Os itens 1-3 são os únicos com impacto **já confirmado ou facilmente
reproduzível** — recomendo revisar esses primeiro. Os itens 4 e 9-10 foram
investigados a fundo e rebaixados de prioridade depois de confirmar que o
caminho normal do código já os previne (mas ficam documentados porque são a
mesma classe de risco que já se materializou 2x nesta sessão).

### 3.2 Contagem de achados por categoria e módulo

| Módulo | Corretude | Consistência | Código morto | Duplicação | Magic numbers | Type hints |
|---|---|---|---|---|---|---|
| `config.py` | 0 | 0 | 1 | 0 | 0 | 0 |
| `ingest/b3_universo.py` | 0 | 1 | 0 | 1 | 1 | 0 |
| `ingest/bcb_sgs.py` | 1 | 1 | 0 | 0 | 0 | 0 |
| `ingest/crosswalk_cnpj.py` | 1 | 0 | 1 | 1 | 1 | 0 |
| `ingest/cvm.py` | 1 | 0 | 0 | 1 | 2 | 0 |
| `ingest/fundamentus.py` | 1 | 0 | 0 | 0 | 0 | 0 |
| `ingest/gpr.py` | 0 | 1 | 0 | 0 | 0 | 0 |
| `ingest/precos.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `modelos/graham.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `modelos/bazin.py` | 1 | 0 | 0 | 0 | 0 | 0 |
| `modelos/fcd.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `modelos/combinado.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `empresa/comportamento.py` | 1 | 1 | 0 | 0 | 1 | 0* |
| `empresa/valor_mercado.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `carteira.py` | 1 | 0 | 0 | 0 | 0 | 0 |
| `correlacao.py` | 0 | 1 | 0 | 1 | 0 | 0 |
| `graficos.py` | 2 | 0 | 0 | 0 | 0 | 0 |
| `screener.py` | 0 | 0 | 0 | 0 | 0 | 0 |
| `app/main.py` | 4 | 1 | 0 | 3 | 5 | 3 |
| **Total** | **13** | **5** | **2** | **6** | **9** | **3** |

\* passaria a 1 depois de corrigir o achado de corretude (retorno precisaria
virar `float | None`).

Achados estruturais fora da tabela: 2 pacotes vazios nunca importados
(`macro/`, `setorial/`) — contados como código morto de nível de projeto,
não de módulo.

**Onde a limpeza vai concentrar esforço**: `app/main.py` sozinho concentra
quase um terço de todos os achados (16 de ~48) — esperado, é o maior
arquivo e o que mais acumulou funcionalidade ao longo da sessão. Os módulos
de `ingest/` vêm em seguida, puxados principalmente pelos 2 bugs de cache já
confirmados. `modelos/`+`empresa/`+`graficos.py`+`screener.py`+`correlacao.py`+
`carteira.py` (o núcleo de cálculo) já está com documentação madura — a
Fase 2 ali deve ser majoritariamente pequenos ajustes, não uma reescrita de
docstrings.

### 3.3 Proposta de lotes pra Fase 2

Agrupados por área do projeto, não por ordem alfabética — cada lote vira um
commit separado:

**Lote 1 — Ingest/dados** (`ingest/b3_universo.py`, `bcb_sgs.py`,
`crosswalk_cnpj.py`, `cvm.py`, `fundamentus.py`, `gpr.py`, `precos.py`):
maior cluster de achados de corretude confirmados (#2, #3, #5, #11) e as
duas duplicações de paginação (`b3_universo.py`/`crosswalk_cnpj.py`) e de
leitura de zip/CSV (`cvm.py`). `precos.py` serve de referência de estilo
pro resto do lote.

**Lote 2 — Cálculo/valuation** (`modelos/bazin.py`, `combinado.py`, `fcd.py`,
`graham.py`, `empresa/comportamento.py`, `empresa/valor_mercado.py`):
contém o achado #1 (o bug mais visível pro usuário final) e o achado #8.
Cluster já maduro — deve ser o lote mais rápido de fechar.

**Lote 3 — Módulos de topo / orquestração de análise** (`carteira.py`,
`correlacao.py`, `graficos.py`, `screener.py`): contém os achados #4
(parte graficos.py), #9, #10, e a triplicação em `correlacao.py`
(oportunidade de aplicar o mesmo padrão `for cenario in CENARIOS` que
`carteira.py` já usa).

**Lote 4 — Dashboard/UI** (`app/main.py`): sozinho, por tamanho e por
concentrar quase 1/3 dos achados — achados #4 (parte main.py), #6, #7, #12,
mais a duplicação dos blocos de gráfico e os 3 type hints faltando. Deixar
por último dá tempo de os padrões dos Lotes 1-3 já estarem consolidados
antes de tocar no maior arquivo.

**Lote 5 — Limpeza estrutural** (`config.py` + remoção de `macro/`/
`setorial/`): pequeno e de baixo risco — remover `DATA_CACHE_DIR` (e o
diretório `data/cache/` vazio) e os dois pacotes mortos. Proponho como
último lote justamente por ser pequeno e não depender de nenhum outro —
pode ser adiantado ou combinado com qualquer outro lote se preferir.

Decisão pendente pro Lote 1: o que fazer com `obter_crosswalk_ibovespa`
(código morto testado, mas nunca chamado em produção) — remover, ou manter
como API pública documentada pro futuro? Vou perguntar nesse lote
especificamente, não decidir sozinho.
