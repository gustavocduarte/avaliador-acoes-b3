# Vistoria técnica (terceira passada) — 2026-09-28

Sobre o zip `avaliador-acoes-b3-master` depois das correções da vistoria
anterior (`docs/vistoria-2026-09-28.md`: isolamento dos testes, bloqueio de
rede). Esta passada foi mais funda nas partes que as anteriores olharam
pouco: adapters de dados (Fundamentus, CVM, catálogo da B3, universo do
Ibovespa, GPR), prazos de cache, tratamento de erro por ação no screener e a
fidelidade dos testes de interface.

Classificação de status: **CONFIRMADO** (provado pelo código ou
reproduzido), **POSSÍVEL** (plausível, não reproduzido), **NÃO VERIFICADO**
(depende de fonte externa inacessível daqui).

## 0. O que foi executado

| Verificação | Resultado |
|---|---|
| `pytest` | **466 passaram**, 12 avisos, 21 s |
| `data/` antes e depois do `pytest` (hash de cada arquivo) | **Idêntico** — o isolamento dos testes funciona |
| `ruff check .` | Limpo |
| `mypy src --ignore-missing-imports` | 30 erros (mesmo perfil das vistorias anteriores) |
| Instrumentação temporária do bloqueio de rede, registrando cada tentativa por teste | 32 testes tentam acessar a rede (ver V01) |
| Leitura linha a linha de `ingest/fundamentus.py`, `ingest/cvm.py`, `ingest/crosswalk_cnpj.py`, `ingest/b3_universo.py`, `ingest/gpr.py`, tratamento de erro do `screener.py` e `tests/conftest.py` | Ver achados |
| Contagem de rótulos repetidos na página do Fundamentus (fixtures PETR4 e ITUB4) | Ver V07 |

Sem acesso às fontes externas e sem rodar o app ao vivo, como nas anteriores.

## 1. Situação dos achados anteriores

| ID | Achado | Situação |
|---|---|---|
| N01 | Testes gravavam Selic/IPCA falsos no cache real | **Corrigido**: isolamento por teste + verificação da execução inteira; `data/` idêntico antes e depois |
| N02 | Docstring contrária ao código | **Corrigido** |
| N03 | Mensagem de falha do BCB repetida | **Corrigido** |
| N05 | 43 avisos na saída dos testes | **Corrigido** (12 restantes, esperados) |
| — | Testes acessando a rede real | **Corrigido** (bloqueio); ver V01 sobre o efeito disso |
| P03 | Simulador trata valor justo como preço em 5 anos | Pendente |
| P04 | Composição do FCF (tesouraria, venda de ativos, juros, IFRS 16) | Pendente, sem documentação no repositório |
| P06 | Nº de ações de units | Pendente, não verificado |
| P09/P10 | WACC e crescimento (limitações) | Pendentes; `docs/limitacoes-conhecidas.md` ainda não existe |
| P11 | "Desconto" é potencial de valorização | Pendente |
| P12 | `requirements.txt` sem versões | Pendente |
| P13 | README diz "316 testes" (são 466) | Pendente |
| P14 | Clique em botão por posição | Parcial: sobram 2 (`test_app_main.py`, linhas 240 e 1690) |
| N04, N06, N07, N08, P16, P17 | Itens de baixa severidade | Pendentes, sem mudança |

## 2. Problemas novos

### V01 — 32 testes de interface validam a tela no estado de falha da CVM

**Classificação:** TESTE · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Onde:** `tests/test_app_main.py`, helper `_bloquear_buscas_de_rede_por_ticker`

**O que foi medido:** registrando cada tentativa bloqueada, os 32 testes que
tentam acessar a rede tentam **a mesma coisa**: baixar
`dfp_cia_aberta_2025.zip` da CVM (~12 MB), via
`resolver_ano_mais_recente_disponivel`. O helper compartilhado simula
preço, Fundamentus, catálogo, dividendos, BCB e GPR, mas **não** simula a
detecção do ano da CVM.

**Consequência:** esses 32 testes (legendas, formatação com vírgula,
expanders, gráficos, Saúde financeira, tabelas) rodam sempre com a detecção
do ano falhando, ou seja, com o aviso "Falha ao detectar o ano mais recente
do DFP da CVM" na tela. Eles passam, e as asserções deles não dependem do
FCD (o catálogo vazio já deixa o FCD não aplicável), então **não são testes
vazios**. Mas a tela que eles validam não é a tela normal do app: um erro
que só aparecesse no caminho normal (ano detectado com sucesso) passaria
despercebido.

**Histórico relevante:** antes do bloqueio de rede, cada execução desses
testes baixava o zip de 12 MB de verdade, o que explica a suíte ter caído de
~90 s para ~21 s. Antes do isolamento de cache, o zip ia para o `data/raw`
real.

**Correção:** simular `resolver_ano_mais_recente_disponivel` no helper
compartilhado (devolvendo um ano fixo), deixando o caminho de falha só nos
testes que existem para testá-lo. Depois disso, rodar a instrumentação de
novo: a lista de testes que tentam a rede deveria ficar vazia.

---

### V02 — Universo do Ibovespa em cache sem prazo, mas a carteira muda 3 vezes por ano

**Classificação:** DADOS / TEMPORALIDADE · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Onde:** `ingest/b3_universo.py::obter_universo_ibovespa`

**Evidência:** a própria docstring diz que a carteira "é revisada só a cada
quadrimestre, então o cache não tem TTL — vale até ser explicitamente
atualizado com `forcar_atualizacao=True`". Nada no app nem no screener chama
com `forcar_atualizacao=True`.

**Problema:** a carteira teórica do Ibovespa é rebalanceada em janeiro, maio
e setembro. Numa máquina com cache (a sua), depois do próximo rebalanceamento
o app continua mostrando e ranqueando **a carteira antiga**: ações que
saíram do índice continuam no screener, as que entraram não aparecem, e os
pesos ficam errados. Nenhum aviso. No Streamlit Cloud o problema se corrige
sozinho quando o disco é apagado num reinício, então afeta principalmente a
execução local e o `screener.csv` que é gerado localmente e publicado.

**Correção:** prazo de validade de alguns dias (ex.: 7), com uso do arquivo
existente se a atualização falhar, mesmo padrão já usado no zip da CVM.

---

### V03 — Série diária do GPR em cache sem prazo

**Classificação:** TEMPORALIDADE / BUG SILENCIOSO · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Onde:** `ingest/gpr.py::obter_gpr`

**Evidência:** a docstring diz que "o cache em disco não tem TTL pra nenhuma
das duas [séries] — mesmo a diária muda pouco de um dia pro outro". Mudar
pouco de um dia pro outro não justifica nunca atualizar.

**Problema:** a correlação usa uma janela de 2 anos que termina hoje. Com o
GPR congelado na data do primeiro download, a parte da janela depois dessa
data fica sem GPR: a correlação passa a ser calculada sobre um período cada
vez mais antigo, sem aviso, e o número de observações vai caindo até a
correlação virar "não aplicável". O card mostra "Correlação fraca (N
observações)" como se fosse o período atual.

**Correção:** prazo de validade (ex.: 7 dias) com uso do arquivo existente se
a atualização falhar. Opcional: mostrar no card a data do último dado do GPR.

---

### V04 — Catálogo de emissores da B3 em cache sem prazo

**Classificação:** DADOS · **Severidade:** BAIXA · **Status:** CONFIRMADO

**Onde:** `ingest/crosswalk_cnpj.py::obter_catalogo_emissores`

O catálogo traz o **segmento setorial**, que decide se o FCD é excluído
(bancos) e monta a Comparação setorial. Sem prazo, mudanças de segmento,
novas empresas e mudanças de CNPJ nunca chegam ao app local. Mudanças são
raras, por isso a severidade baixa. Correção: prazo longo (ex.: 30 dias).

---

### V05 — No screener, uma falha de rede no Fundamentus ou na CVM derruba a linha inteira

**Classificação:** ROBUSTEZ · **Severidade:** MÉDIA · **Status:** CONFIRMADO

**Onde:** `screener.py::_calcular_linha_ticker` e o laço de `rodar_screener`

**Evidência:** cada fonte tem seu próprio `try`, mas eles só capturam erros
de "dado ausente":
```python
except (TickerNaoEncontrado, EstruturaPaginaMudou):   # Fundamentus
except (CnpjNaoEncontrado, ContaFluxoCaixaNaoEncontrada):  # CVM
```
Um erro de rede (HTTP 429/5xx, timeout, conexão) no Fundamentus ou no
download da CVM não é capturado ali, sobe até o laço e vira
`"Erro inesperado: ..."` para a ação inteira.

**Consequência:** uma falha passageira de uma única requisição no
Fundamentus apaga Graham, Bazin **e** FCD daquela ação no ranking, mesmo com
preço e dividendos disponíveis. O Fundamentus é consultado 76 vezes em
sequência e não tem nova tentativa (o BCB tem, depois da última rodada).

**Correção:** capturar `requests.RequestException` em cada fonte (a fonte
fica indisponível só para o método que depende dela) e aplicar ao
Fundamentus a mesma nova tentativa com pausa já usada no BCB. Teste:
Fundamentus com erro 503 → Graham não aplicável com motivo, Bazin e FCD
calculados normalmente.

---

### V06 — Leitura da CVM não filtra por versão do documento

**Classificação:** DADOS · **Severidade:** BAIXA · **Status:** POSSÍVEL / NÃO VERIFICADO

**Onde:** `ingest/cvm.py::_linhas_do_membro` e `_linha_por_codigo`

Os arquivos da CVM têm a coluna `VERSAO`. O código pega todas as linhas do
CNPJ e usa a **primeira** ocorrência de cada conta
(`candidatas[0]`). Se o arquivo trouxer mais de uma versão do mesmo
documento (reapresentação), o valor usado pode ser o da versão antiga e as
linhas de versões diferentes se misturam. A fixture tem só a versão 1, e
não foi possível confirmar se os arquivos reais trazem mais de uma versão.
Correção barata e defensiva: manter só as linhas da maior `VERSAO` de cada
CNPJ antes de qualquer cálculo.

---

### V07 — Rótulos repetidos na página do Fundamentus

**Classificação:** MANUTENÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO (risco latente)

**Onde:** `ingest/fundamentus.py::_extrair_rotulos_valores`

Nas fixtures reais, "Lucro Líquido", "Receita Líquida" e "EBIT" (PETR4) e
"Lucro Líquido", "Result Int Financ" e "Rec Serviços" (ITUB4) aparecem
**duas vezes**: uma para os últimos 12 meses e outra para os últimos 3
meses. O parser guarda a última ocorrência. Nenhum desses rótulos é usado
hoje, então não há erro atual. Mas quem adicionar "Lucro Líquido" no futuro
vai receber o valor **trimestral** achando que é anual, sem nenhum aviso.
Correção: detectar rótulo repetido e levantar erro (ou guardar só a primeira
ocorrência, que é a de 12 meses), com teste.

---

### V08 — O isolamento por `__defaults__` não cobre parâmetros só-nomeados

**Classificação:** TESTE / MANUTENÇÃO · **Severidade:** BAIXA · **Status:** CONFIRMADO (risco latente)

**Onde:** `tests/conftest.py::_isolar_cache_de_disco`

A fixture monta a nova tupla de padrões com todos os parâmetros que têm
valor padrão, mas `__defaults__` só guarda os posicionais; os só-nomeados
(depois de um `*`) ficam em `__kwdefaults__`. Hoje nenhuma função afetada tem
parâmetro só-nomeado (verificado), então não há erro. Se um dia tiver, os
padrões ficam desalinhados em silêncio. A verificação da execução inteira
(hash de `data/`) ainda pegaria qualquer escrita indevida, então o risco é
só de comportamento estranho em testes. Correção: tratar `__kwdefaults__` à
parte, ou pular funções com parâmetros só-nomeados.

---

### V09 — Dois rótulos ambíguos na tela

**Classificação:** INTERFACE · **Severidade:** BAIXA · **Status:** CONFIRMADO

- **"Preço — último fechamento"** (bloco de datas): durante o pregão, o
  preço do yfinance com `period="1d"` é o preço do momento (com atraso), não
  um fechamento.
- **"Volume médio (3m)"**: é a média de **ações negociadas** por dia
  (ex.: 38.408.602), não volume financeiro em reais, que é como o termo
  costuma ser lido. Sugestão: "Volume médio (3m, ações/dia)".

---

### V10 — Leitura da CVM varre arquivos inteiros por empresa

**Classificação:** PERFORMANCE · **Severidade:** BAIXA · **Status:** CONFIRMADO

Cada consulta de fluxo de caixa percorre o CSV inteiro da DFC (até 4
arquivos: MI/MD × consolidado/individual) procurando um CNPJ, e o screener
faz isso para 76 empresas × 2 anos. O resultado por empresa fica em cache,
então só a primeira rodada paga o custo. Aceitável; uma melhoria futura
seria ler cada arquivo uma vez e indexar por CNPJ.

## 3. Matriz

| ID | Problema | Categoria | Severidade | Correção |
|---|---|---|---|---|
| P06 | Nº de ações de units | Dados (não verificado) | ALTA se confirmado | Valor de mercado ÷ cotação |
| P03 | Premissa do Simulador | Financeiro | ALTA | Decidir e documentar |
| P04 | Composição do FCF | Financeiro | ALTA | Documentar; capex explícito |
| V02 | Universo do Ibovespa sem prazo | Dados/temporalidade | MÉDIA | Prazo + uso do antigo se falhar |
| V03 | GPR diário sem prazo | Temporalidade | MÉDIA | Prazo + data do último dado |
| V05 | Falha de rede derruba a linha inteira no screener | Robustez | MÉDIA | Capturar erro de rede por fonte; nova tentativa no Fundamentus |
| V01 | Testes de interface na tela de falha da CVM | Teste | MÉDIA | Simular a detecção do ano no helper |
| P09/P10 | Premissas do WACC e crescimento | Limitação | MÉDIA | `docs/limitacoes-conhecidas.md` |
| P12 | Dependências sem versão | Manutenção | MÉDIA | Fixar versões |
| V04 | Catálogo da B3 sem prazo | Dados | BAIXA | Prazo longo |
| V06 | CVM sem filtro de versão | Dados (possível) | BAIXA | Maior `VERSAO` por CNPJ |
| V07 | Rótulos repetidos no Fundamentus | Manutenção | BAIXA | Erro em rótulo repetido |
| V08 | `__kwdefaults__` no isolamento | Teste | BAIXA | Tratar à parte |
| V09 | "Último fechamento" e "Volume médio" | Interface | BAIXA | Ajustar rótulos |
| V10 | Varredura da CVM | Performance | BAIXA | Aceitar |
| P11, P13, P14, P16, P17, N04, N06–N08 | Pendências anteriores | Várias | BAIXA | Limpeza geral |

## 4. Conclusão

**Correções da rodada anterior:** confirmadas. Os testes não tocam mais em
`data/` (verificado por hash) e não acessam a rede.

**Achado mais relevante desta passada:** três caches sem prazo de validade
(universo do Ibovespa, GPR diário, catálogo da B3) que congelam dados que
mudam com o tempo. É o mesmo tipo de problema que já foi corrigido no
Fundamentus, no Banco Central e na CVM, e os dois primeiros afetam o que o
usuário vê sem nenhum aviso. O do universo vai se manifestar com certeza no
rebalanceamento de janeiro de 2027.

**Segundo mais relevante:** V05. Uma única falha passageira do Fundamentus
apaga os três métodos de uma ação no ranking.

**O que não precisa mudar:** a estratégia de isolamento dos testes (as duas
camadas se complementam), a leitura em streaming dos arquivos da CVM, a
normalização do CNPJ, e a separação entre "dado ausente" (resultado não
aplicável) e "erro" (mostrado ao usuário) nos modelos.
