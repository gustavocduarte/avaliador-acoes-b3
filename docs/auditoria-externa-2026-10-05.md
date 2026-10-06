> **Nota de registro (05/10/2026):** esta auditoria externa foi feita em 05/10/2026 sobre um ZIP do projeto, sem acesso ao Streamlit nem à rede. Os testes de interface (`tests/test_app_main.py`) não rodaram nela: só os testes que não dependem do Streamlit passaram (746), com um stub mínimo do `yfinance`. O texto abaixo está como foi recebido, sem alterações.

---

\# Auditoria técnica completa — Avaliador de Ações da B3



\## 1. Escopo da auditoria



A análise foi feita sobre o projeto completo enviado no ZIP, incluindo:



\* 57 arquivos Python;

\* aproximadamente 248 funções/métodos no código de produção;

\* 839 funções de teste;

\* modelos Graham, Bazin e FCD;

\* pipeline do Screener;

\* ingestão de B3, CVM, Fundamentus, Yahoo Finance, BCB, IBGE e GPR;

\* simulador de carteira;

\* painel Streamlit;

\* gráficos;

\* cache;

\* workflows do GitHub Actions;

\* `pyproject.toml`;

\* `requirements.txt`;

\* `requirements-dev.txt`;

\* dados versionados;

\* documentação técnica e auditorias anteriores.



Também fiz verificações de:



\* sintaxe Python;

\* integridade do `screener.csv`;

\* execução da suíte de testes;

\* testes isolados sem rede;

\* propagação de `NaN`;

\* comportamento de cache;

\* coerência entre código e documentação;

\* possíveis problemas de segurança;

\* robustez dos workflows;

\* consistência dos cálculos financeiros;

\* APIs/depreciações atuais do Streamlit.



\---



\# 2. Resultado executivo



Minha classificação geral:



| Área                                    | Situação                                        |

| --------------------------------------- | ----------------------------------------------- |

| Sintaxe Python                          | 🟢 Boa                                          |

| Arquitetura                             | 🟢 Boa                                          |

| Separação de responsabilidades          | 🟢 Boa                                          |

| Testes                                  | 🟢 Muito boa                                    |

| Tratamento de fontes externas           | 🟢 Bom                                          |

| Integridade do Screener                 | 🟢 Boa                                          |

| Modelos matemáticos básicos             | 🟢 Bons                                         |

| FCD                                     | 🟡 Bom código, metodologia ainda discutível     |

| Cache                                   | 🟡 Precisa reforço                              |

| Tratamento de `NaN`/valores não finitos | 🔴 Existe bug                                   |

| Streamlit/API futura                    | 🟡 Há APIs depreciadas                          |

| Segurança do widget TradingView         | 🟡 Pequeno problema de sanitização              |

| Proveniência macroeconômica             | 🟡 Existe inconsistência                        |

| Atomicidade/transação do resultado      | 🟡 Pequena janela de inconsistência             |

| Dependências                            | 🟢 Pins válidos                                 |

| Documentação                            | 🟢 Muito boa, com alguns pontos desatualizáveis |

| Risco de quebra imediata                | 🟢 Baixo                                        |



\*\*Não encontrei um bug crítico que indique que o projeto inteiro esteja calculando tudo errado ou que permita comprometimento grave do servidor.\*\*



Mas encontrei \*\*2 bugs técnicos concretos\*\*, \*\*3 problemas de robustez/manutenção\*\*, \*\*1 problema de segurança de baixo impacto\*\* e \*\*várias questões metodológicas financeiras\*\*.



\---



\# 3. BUG ALTO — `NaN` pode produzir valor justo `NaN` com `aplicável=True`



\## Severidade: ALTA



Esse é o bug técnico mais importante encontrado.



O problema aparece principalmente em:



`src/avaliador\_b3/modelos/fcd.py`



e



`src/avaliador\_b3/modelos/graham.py`.



O código valida:



```python

if numero\_acoes is None or numero\_acoes <= 0:

```



e:



```python

if lpa is None or vpa is None:

```



O problema é que:



```python

float("nan") <= 0

```



é `False`.



Portanto, `NaN` passa pela validação.



Eu reproduzi isso diretamente.



\### Graham



Com:



```python

lpa = NaN

vpa = 10

```



o resultado é:



```python

{

&#x20;   "aplicavel": True,

&#x20;   "valor\_justo": nan

}

```



Isso é incorreto.



O método deveria considerar o dado inválido e retornar:



```text

aplicável = False

```



ou um motivo explícito de dado inválido.



\### FCD



Também reproduzi:



```python

divida\_liquida\_sobre\_patrimonio = NaN

divida\_liquida = NaN

```



O resultado foi:



```text

aplicável = True

valor\_justo = NaN

wacc = NaN

```



Isso é particularmente perigoso porque o `NaN` pode continuar passando pelo pipeline.



O código:



```python

if wacc <= 0:

```



também não captura `NaN`, porque:



```python

nan <= 0

```



é `False`.



\### Consequência



Em condições normais, o Fundamentus provavelmente não entregará `"nan"` como valor.



Mas um valor corrompido, uma alteração no HTML do site, uma transformação intermediária ou algum cache inconsistente pode introduzir `NaN`.



Nesse caso o pipeline pode produzir:



```text

método aplicável

↓

valor justo = NaN

↓

valor combinado = NaN

```



Em vez de rejeitar o dado.



\### Onde corrigir



A validação deveria ser baseada em finitude, por exemplo:



```python

math.isfinite(valor)

```



ou uma função central:



```python

def numero\_finito\_positivo(valor):

&#x20;   return (

&#x20;       valor is not None

&#x20;       and math.isfinite(float(valor))

&#x20;       and valor > 0

&#x20;   )

```



Isso deveria ser aplicado aos principais inputs financeiros:



\* LPA;

\* VPA;

\* número de ações;

\* preço;

\* FCF;

\* dívida líquida;

\* patrimônio;

\* Beta;

\* WACC;

\* taxas;

\* receita;

\* valores dos métodos.



\*\*Recomendação: corrigir antes de considerar o projeto definitivamente fechado.\*\*



\---



\# 4. BUG MÉDIO/ALTO — cache corrompido pode derrubar o processamento



\## Severidade: MÉDIA/ALTA



Esse problema aparece em vários adapters.



O padrão atual é aproximadamente:



```python

bruto = json.loads(caminho.read\_text(...))

```



ou:



```python

pd.read\_csv(caminho)

```



sem tratar corrupção do arquivo como `cache miss`.



Por exemplo:



`ingest/fundamentus.py`



```python

bruto = json.loads(caminho.read\_text(encoding="utf-8"))

```



Eu reproduzi isso criando propositalmente:



```text

{broken

```



no cache.



O resultado foi:



```text

JSONDecodeError

```



em vez de:



```text

cache inválido → ignorar → buscar novamente

```



\## Isso acontece em vários lugares



\### Fundamentus



```text

ingest/fundamentus.py

```



\### CVM FCF



```text

ingest/cvm.py

```



\### Balanço CVM



```text

ingest/balanco\_cvm.py

```



\### Preços



```text

ingest/precos.py

```



\### Dividendos



```text

ingest/precos.py

```



\### GPR



```text

ingest/gpr.py

```



\### B3



```text

ingest/b3\_universo.py

ingest/crosswalk\_cnpj.py

```



Alguns caches, como o macro do BCB, já fazem um tratamento melhor de JSON inválido.



\## Como isso pode acontecer?



Por exemplo:



1\. aplicação começa a escrever cache;

2\. processo é interrompido;

3\. máquina/container reinicia;

4\. arquivo fica truncado;

5\. próximo acesso considera o arquivo existente;

6\. tenta ler;

7\. `JSONDecodeError`/`ParserError`;

8\. o sistema pode tratar como falha da fonte, quando na realidade o problema está apenas no cache local.



No Streamlit Cloud isso é especialmente interessante porque o filesystem é compartilhado pelo processo entre sessões.



\## Problema adicional



Os caches também são gravados diretamente:



```python

caminho.write\_text(...)

```



em vez de:



```text

arquivo.tmp

↓

fsync opcional

↓

rename/replace atômico

```



O ZIP da CVM já possui uma implementação muito melhor:



```text

.zip.tmp

↓

download completo

↓

.replace()

```



Esse padrão deveria ser generalizado para os caches críticos.



\## Recomendação



Criar uma função central:



```python

ler\_cache\_seguro(...)

```



que:



1\. captura `JSONDecodeError`;

2\. captura `OSError`;

3\. captura `pd.errors.ParserError`;

4\. valida schema;

5\. valida valores;

6\. retorna `None` em caso de corrupção;

7\. força nova consulta.



E uma função:



```python

gravar\_cache\_atomico(...)

```



para todos os JSON/CSV importantes.



\---



\# 5. BUG MÉDIO — origem da Selic/IPCA fica incorreta quando vem do cache



\## Severidade: MÉDIA



Encontrei uma inconsistência de proveniência em:



`src/avaliador\_b3/ingest/bcb\_sgs.py`



O arquivo `macro\_referencia.json` grava corretamente:



```json

{

&#x20;   "fonte\_selic": "...",

&#x20;   "fonte\_ipca": "..."

}

```



Porém `\_ler\_macro()` não recupera esses campos.



Ele recupera somente:



\* Selic;

\* IPCA;

\* data do IPCA;

\* data da busca.



Depois, quando o valor é recuperado do cache, o sistema faz:



```python

fonte\_selic = fonte

fonte\_ipca = fonte

```



com algo como:



```text

Valor guardado em 05/10/2026

```



Isso significa que a aplicação perde a informação de que, por exemplo:



```text

Selic → BCB API

IPCA → IBGE SIDRA

```



e passa a mostrar genericamente:



```text

valor guardado

```



para os dois.



\## Impacto



Não altera o número.



Mas altera a \*\*transparência da origem dos dados\*\*, justamente em uma aplicação financeira que se preocupa bastante com rastreabilidade.



\## Correção



Salvar e carregar:



```text

fonte\_selic

fonte\_ipca

```



também no cache.



\---



\# 6. BUG MÉDIO — pequena quebra de atomicidade entre `screener.csv` e `macro\_referencia.json`



\## Severidade: MÉDIA/BAIXA



Em:



`src/avaliador\_b3/screener.py`



o fluxo é:



```python

os.replace(caminho\_novo, caminho\_saida)

```



e depois:



```python

salvar\_macro\_referencia(...)

```



Ou seja:



```text

1\. novo screener passa

2\. screener.csv é substituído

3\. salva macro\_referencia.json

```



Se o passo 3 falhar, o método lança exceção.



Nesse ponto:



```text

screener.csv = NOVO

macro\_referencia.json = ANTIGO

```



Mas o workflow pode interpretar a execução como falha.



Isso cria uma situação em que o estado do projeto não é completamente consistente.



\## Melhor arquitetura



Gerar os dois arquivos temporários:



```text

screener.csv.tmp

macro\_referencia.json.tmp

```



validar os dois e então fazer:



```text

replace screener

replace macro

```



Ou, no mínimo, salvar o macro antes da substituição do CSV e só publicar o resultado quando ambos estiverem prontos.



\---



\# 7. PROBLEMA DE SEGURANÇA — ticker é interpolado diretamente em JavaScript



\## Severidade: BAIXA/MÉDIA



Existe uma questão interessante em:



`src/avaliador\_b3/app/main.py`



A função:



```python

\_widget\_avancado\_tradingview(ticker)

```



monta HTML/JavaScript com:



```python

"symbol": "BMFBOVESPA:{ticker}",

```



O `ticker` é inserido diretamente dentro de uma string JavaScript.



Quando o universo B3 está disponível, isso é mitigado porque o usuário escolhe uma ação de um `selectbox`.



Mas existe o caminho alternativo:



```python

st.text\_input("Ticker...")

```



quando o catálogo B3 está indisponível.



Nesse caso, o usuário pode fornecer conteúdo arbitrário.



\## Exemplo conceitual



Um valor contendo caracteres de escape de string ou HTML/JavaScript poderia alterar o conteúdo do bloco.



O impacto é limitado porque o código roda dentro do componente/iframe do TradingView, e não encontrei acesso a segredos ou dados sensíveis nessa área.



Portanto não classificaria isso como vulnerabilidade crítica.



Mas é uma falha de sanitização.



\## Correção



Não interpolar diretamente.



Usar serialização JSON:



```python

json.dumps(f"BMFBOVESPA:{ticker}")

```



ou validar agressivamente o ticker:



```python

^\[A-Z0-9]{4,7}$

```



antes de montar o widget.



Isso também combina melhor com o fato de que o aplicativo realmente trabalha com tickers B3.



\---



\# 8. PROBLEMA DE MANUTENÇÃO — APIs do Streamlit depreciadas



\## Severidade: MÉDIA para manutenção futura



O projeto está fixado em:



```text

streamlit==1.63.0

```



Essa versão existe e está publicada no PyPI.



Porém o código ainda utiliza:



```python

use\_container\_width=True

```



em diversos lugares.



A documentação atual do Streamlit marca `use\_container\_width` como depreciado e recomenda:



```python

width="stretch"

```



para substituir:



```python

use\_container\_width=True

```



Também encontrei:



```python

components.html(...)

```



e o próprio código usa:



```python

st.components.v1.html

```



A API `st.components.v1.html` foi depreciada desde o Streamlit 1.56.0 e a documentação recomenda `st.html`.



\## Importante



Isso \*\*não é um bug imediato na versão atual\*\*.



Mas é dívida técnica real.



Se o projeto atualizar o Streamlit futuramente, existe risco de quebra.



\## Recomendação



Trocar gradualmente:



```python

use\_container\_width=True

```



por:



```python

width="stretch"

```



e avaliar a migração de:



```python

components.html(...)

```



para a API atual adequada.



\---



\# 9. Dependências — problema antigo foi resolvido



Aqui houve uma evolução positiva importante.



A auditoria antiga apontava dependências sem versão.



Isso foi corrigido.



Atualmente o projeto fixa versões como:



```text

pandas==3.0.5

numpy==2.5.3

yfinance==1.7.0

streamlit==1.63.0

plotly==7.0.0

...

```



Eu verifiquei que essas versões existem no PyPI.



O `pandas 3.0.5` foi publicado em julho de 2026.



O `yfinance 1.7.0` existe e foi publicado em agosto de 2026.



O Streamlit 1.63.0 também existe.



Portanto:



\*\*P12 da auditoria antiga pode ser considerado resolvido.\*\*



\---



\# 10. Testes — resultado muito bom, mas não consegui executar 100% neste ambiente



Aqui é importante separar duas coisas.



O ambiente desta auditoria não possui:



```text

yfinance

streamlit

```



instalados.



A tentativa de instalar `requirements-dev.txt` também não foi possível porque este ambiente de execução está sem acesso à Internet.



Por isso, a suíte completa não pôde ser executada literalmente como no CI.



Entretanto, criei um stub mínimo de `yfinance` apenas para permitir a coleta dos testes não relacionados à interface.



Resultado:



```text

746 passed

3 warnings

```



sem acessar a rede.



Isso é um resultado muito bom.



Também confirmei que todos os arquivos Python compilam sem erro de sintaxe.



\---



\# 11. Existem 93 testes de interface que ficaram sem execução



O arquivo:



```text

tests/test\_app\_main.py

```



possui aproximadamente 93 funções `test\_\*`.



Eles dependem do Streamlit/AppTest.



Como o Streamlit não está instalado neste ambiente, eles não puderam ser executados.



Portanto não afirmo:



> "todos os testes passaram"



A afirmação correta desta auditoria é:



> \*\*746 testes não-UI passaram; os testes de interface não puderam ser executados neste ambiente por falta do Streamlit.\*\*



Isso é importante porque evita uma falsa sensação de 100% de validação.



\---



\# 12. Testes atuais já cobrem vários bugs antigos



Também reavaliei os problemas registrados na auditoria de 27/09.



\## P01 — Bazin



A antiga falha da janela de cinco anos parece estar corrigida.



Agora o código usa anos civis:



```python

\_anos\_exigidos(...)

```



e existem testes como:



```text

test\_aplicavel\_independente\_do\_mes\_da\_data\_referencia

```



Portanto:



\*\*P01 → corrigido.\*\*



\---



\## P02 — perda superior a 100%



Também foi corrigido.



A carteira agora limita:



```text

\-100%

```



e existem testes específicos:



```text

test\_simular\_investimento\_fcd\_negativo\_limita\_pessimista\_a\_perda\_total

```



Portanto:



\*\*P02 → corrigido.\*\*



\---



\## P05 — correlação antes de alinhar datas



Também foi corrigido.



Agora o código:



```text

níveis

↓

merge por data

↓

ordenação

↓

pct\_change

↓

correlação

```



e existem testes específicos para:



\* datas em comum;

\* fusos;

\* calendários diferentes;

\* overlap insuficiente.



Portanto:



\*\*P05 → corrigido.\*\*



\---



\## P07 — falha do BCB silenciosa



Também houve correção.



Agora o projeto gera:



```text

MacroIndisponivelWarning

```



e a interface captura o aviso.



Portanto:



\*\*P07 → substancialmente corrigido.\*\*



\---



\# 13. FCD — não encontrei erro matemático grosseiro, mas existem limitações importantes



O código do FCD está significativamente melhor do que a versão antiga.



Ele trata:



\* Enterprise Value;

\* dívida líquida;

\* caixa líquido;

\* não controladores;

\* arrendamentos;

\* ações em circulação;

\* Beta;

\* WACC;

\* crescimento;

\* perpetuidade;

\* capex;

\* juros;

\* risco sacado;

\* fallback de dados.



Isso é uma arquitetura razoavelmente sofisticada.



Porém ainda existem questões metodológicas.



\---



\# 14. Crescimento do FCD continua sendo baseado em apenas dois pontos



Atualmente:



```text

FCF atual

vs.

FCF de 5 anos atrás

```



gera uma CAGR.



Isso significa que:



```text

2020 → 2025

```



é tratado como uma trajetória contínua, mesmo que:



```text

2020 = R$ 1 bi

2021 = R$ 1,1 bi

2022 = R$ 0,7 bi

2023 = R$ 1,5 bi

2024 = R$ 4 bi

2025 = R$ 5 bi

```



A fórmula olha essencialmente para:



```text

1 → 5

```



e ignora a trajetória intermediária.



O próprio projeto já identificou esse problema nas investigações de 04/10.



Portanto:



\*\*não considero isso um bug de programação.\*\*



É uma limitação metodológica conhecida.



Mas é uma das coisas que mais podem distorcer o FCD.



\---



\# 15. Empresas cíclicas continuam sendo um problema metodológico



A investigação:



```text

docs/investigacao-ciclicas-2026-10-04.md

```



mostra corretamente que uma única fotografia de FCF pode ser inadequada para empresas cíclicas.



Isso afeta principalmente empresas ligadas a:



\* commodities;

\* mineração;

\* siderurgia;

\* petróleo;

\* transporte;

\* varejo em ciclos extremos;

\* empresas altamente sensíveis ao ciclo econômico.



Para uma empresa no pico do ciclo:



```text

FCF atual muito alto

↓

CAGR aparentemente enorme

↓

FCD elevado

```



Isso não necessariamente representa valor econômico normalizado.



A investigação de normalização já existe, mas ainda não está implementada.



Portanto:



\*\*não é bug de código; é risco metodológico relevante.\*\*



\---



\# 16. WACC — código coerente com a decisão registrada, mas premissa ainda discutível



O projeto atualmente usa:



```text

Ke = (Selic − spread de default) + Beta × prêmio de risco Brasil

```



Isso foi deliberadamente decidido no relatório de 04/10.



Portanto não encontrei inconsistência entre documentação e implementação.



Mas ainda existe uma questão financeira relevante:



```text

Selic

```



é uma taxa de curto prazo, enquanto um DCF de longo prazo normalmente exige uma taxa livre de risco coerente com o horizonte do valuation.



O próprio projeto reconhece essa questão.



Portanto:



\*\*não recomendo alterar isso como "bug" sem uma nova investigação metodológica.\*\*



\---



\# 17. Valor combinado — matematicamente correto, mas conceitualmente discutível



O projeto faz:



```text

Graham

\+

Bazin

\+

FCD

\----------------

n

```



somente entre os métodos aplicáveis.



O código está correto.



O problema é conceitual:



Graham, Bazin e FCD não são necessariamente três estimadores independentes do mesmo objeto.



Por exemplo:



\* Graham → múltiplos implícitos baseados em lucro e patrimônio;

\* Bazin → yield sobre dividendos;

\* FCD → fluxo de caixa descontado.



Uma média simples atribui implicitamente:



```text

peso igual

```



a metodologias economicamente diferentes.



Isso não é bug.



É uma escolha de modelo.



A documentação deixa isso relativamente transparente, o que é positivo.



\---



\# 18. Simulador de carteira — atualmente bem documentado



A antiga crítica de que o simulador tratava o valor justo como "preço daqui a cinco anos" foi parcialmente eliminada pela documentação.



Hoje a interface explicitamente diz:



> valor ao convergir



e:



> sem prazo definido



e:



> não é previsão.



Isso é importante.



O simulador está calculando:



```text

valor investido × valor justo / preço atual

```



e não:



```text

retorno anualizado em 5 anos

```



Portanto não considero mais P03 um bug atual.



\---



\# 19. Um ponto que ainda merece atenção no simulador



A carteira usa:



```text

pessimista = menor método

base = média

otimista = maior método

```



Isso funciona matematicamente.



Mas o menor valor pode ser o Bazin.



E o próprio projeto reconhece que:



> Bazin não é exatamente uma estimativa de valor intrínseco; é um preço-teto baseado em yield.



Logo:



```text

pessimista = Bazin

```



não significa necessariamente:



```text

cenário econômico pessimista

```



É apenas:



```text

menor estimativa entre os métodos

```



A interface já deixa isso relativamente claro.



Eu manteria assim por enquanto, mas não apresentaria esses três números como uma distribuição probabilística de cenários.



\---



\# 20. Cache — recomendação de arquitetura



Hoje o projeto possui uma boa arquitetura de cache:



```text

Yahoo

Fundamentus

CVM

BCB

B3

GPR

```



com TTLs diferentes.



Isso é positivo.



O problema é que existem duas características que deveriam ser adicionadas:



\### 20.1 Escrita atômica



Principalmente para:



```text

JSON

CSV

```



\### 20.2 Validação de conteúdo



Não basta:



```text

arquivo existe

```



Deveria existir:



```text

arquivo existe

\+

schema correto

\+

valores válidos

\+

campos esperados

\+

dados finitos

```



Isso também resolveria boa parte do problema de `NaN`.



\---



\# 21. Problema adicional de concorrência



Como o app é Streamlit, diferentes sessões podem executar código simultaneamente.



Imagine:



```text

Usuário A → PETR4

Usuário B → PETR4

```



ao mesmo tempo.



Ambos podem descobrir:



```text

cache não existe

```



e ambos podem escrever:



```text

PETR4.json

```



Não necessariamente ocorrerá corrupção, mas o desenho atual não possui uma estratégia explícita de lock.



Uma arquitetura mais robusta seria:



```text

cache miss

↓

lock por chave

↓

verifica novamente se outro processo já gravou

↓

busca

↓

escreve .tmp

↓

replace

↓

unlock

```



Para o volume atual isso provavelmente não é urgente, mas é uma melhoria de produção.



\---



\# 22. Problema de portabilidade do pacote



O projeto usa:



```python

ROOT\_DIR = Path(\_\_file\_\_).resolve().parents\[2]

```



e espera encontrar:



```text

data/

```



relativamente ao código-fonte.



Isso funciona muito bem quando o projeto é executado como:



```text

repositório/

├── src/

├── data/

```



Mas o pacote não é totalmente relocável como um pacote Python tradicional.



Se alguém instalar um wheel fora dessa estrutura, os dados:



```text

data/processed/

data/raw/

```



não necessariamente estarão disponíveis.



Não é um problema para o uso atual no GitHub + Streamlit Community Cloud.



É uma limitação de empacotamento.



\---



\# 23. `mypy` tem uma pequena inconsistência de alvo



O projeto declara:



```toml

requires-python = ">=3.12"

```



e Ruff:



```toml

target-version = "py312"

```



mas mypy:



```toml

python\_version = "3.14"

```



Isso significa:



```text

runtime mínimo = Python 3.12

lint = Python 3.12

type checker = Python 3.14

```



É uma inconsistência.



O CI roda 3.14, então o pipeline oficial fica coerente.



Mas alguém usando:



```text

Python 3.12

```



pode ter comportamento diferente na checagem de tipos.



Eu usaria:



```toml

python\_version = "3.12"

```



como alvo mínimo, ou deixaria isso explicitamente documentado.



\---



\# 24. Warnings encontrados nos testes



Existem quatro `SyntaxWarning` em:



```text

tests/test\_app\_main.py

```



relacionados a:



```python

"\\$"

```



em strings.



Exemplo conceitual:



```python

"R\\$ 109"

```



Em Python isso não precisa da barra.



Deveria ser:



```python

"R$ 109"

```



ou, dependendo do contexto de regex:



```python

r"R\\$ 109"

```



Isso não quebra os testes atualmente.



É apenas ruído técnico que deveria ser eliminado.



\---



\# 25. Yahoo Finance — risco operacional externo



O projeto depende fortemente do `yfinance`.



A versão atualmente fixada existe, mas o próprio projeto `yfinance` informa que não é afiliado ao Yahoo e que o acesso aos dados utiliza APIs públicas do Yahoo; a página do pacote também alerta que a API do Yahoo é destinada a uso pessoal.



Isso não é um bug do código.



Mas para uma aplicação pública, é um risco operacional:



```text

Yahoo muda endpoint

↓

yfinance muda

↓

ticker para de funcionar

```



O adapter já possui boa camada de isolamento e tratamento de erro, então a arquitetura está preparada para isso.



Mas eu não trataria Yahoo como fonte de dados contratualmente garantida para uma eventual versão comercial.



\---



\# 26. Segurança — resultado geral



Procurei especificamente por:



\* API keys;

\* senhas;

\* tokens;

\* `.env`;

\* secrets;

\* `eval`;

\* `exec`;

\* `pickle`;

\* shell execution;

\* subprocessos;

\* comandos arbitrários;

\* credenciais hardcoded.



Não encontrei uma credencial evidente ou mecanismo perigoso desse tipo.



O `.gitignore` também trata corretamente:



```text

.env

.streamlit/secrets.toml

data/raw/

```



Isso está bom.



O único ponto de segurança que encontrei foi a interpolação do ticker no JavaScript do TradingView, discutida anteriormente.



\---



\# 27. Integridade do `screener.csv`



Também validei o arquivo atualmente versionado.



Resultado:



```text

76 ações

0 tickers duplicados

0 preços não finitos

0 valores combinados não finitos

0 Graham não finitos

0 Bazin não finitos

0 FCD não finitos

0 Beta não finitos

0 linhas com sucesso=False

```



Existem duas ações sem método aplicável:



```text

CSNA3

NATU3

```



Isso está sendo representado como ausência de método, não como um falso valor zero.



Esse comportamento é correto.



\---



\# 28. A arquitetura de proteção da rodada está boa



O mecanismo:



```text

rodada

↓

arquivo .novo

↓

processamento completo

↓

checagem

↓

ACEITA → replace

REJEITA → .rejeitado.csv

```



é uma boa decisão arquitetural.



Também é positivo que uma exceção no meio da rodada provoque:



```python

caminho\_novo.unlink(...)

```



sem destruir diretamente o resultado anterior.



Essa é uma das partes mais maduras do projeto.



\---



\# 29. O tratamento do ZIP da CVM está particularmente bom



Aqui encontrei uma implementação sólida.



O fluxo:



```text

download

↓

.zip.tmp

↓

download completo

↓

replace

```



evita corromper o ZIP existente caso:



\* a conexão caia;

\* o download seja interrompido;

\* o processo morra;

\* o servidor devolva erro.



Essa abordagem deveria ser usada como padrão para os outros caches.



\---



\# 30. O pipeline CVM está bem estruturado



Também não encontrei um bug óbvio na arquitetura:



```text

DFP

↓

empresa

↓

DFC

↓

método MI/MD

↓

consolidado/individual

↓

CFO/CFI

↓

capex

↓

juros

↓

risco sacado

↓

receita

↓

FCD

```



A lógica de fallback por empresa também está bem pensada:



```text

ano mais recente

↓

empresa não entregou

↓

ano anterior somente para aquela empresa

```



sem degradar todas as empresas.



Isso é melhor que simplesmente usar um ano global antigo.



\---



\# 31. Problema metodológico ainda aberto: risco sacado



A implementação atual já incorpora o ajuste investigado em 04/10.



O projeto decidiu:



```text

saídas explicitamente identificadas como

risco sacado / convênio / forfait / cessão

↓

ajuste operacional

```



Isso é uma decisão metodológica defensável.



Mas a identificação depende da descrição textual da CVM.



Se uma empresa utilizar uma descrição diferente:



```text

"operação financeira com fornecedores"

```



por exemplo, o algoritmo pode não reconhecer.



Isso é uma limitação inerente ao método de classificação por texto.



Não classificaria como bug até aparecer um caso real perdido.



\---



\# 32. Problema metodológico: FCD pode ficar extremamente sensível ao valor terminal



O projeto já possui aviso de valor extremo.



Isso é correto.



Em um DCF de cinco anos:



```text

PV do período explícito

\+

PV da perpetuidade

```



o segundo componente pode dominar completamente o valuation.



Isso significa que pequenas mudanças em:



```text

WACC

g

FCF

```



podem alterar muito o valor justo.



O código trata:



```text

WACC - g

```



com margem de segurança.



Isso evita explosão matemática.



Mas não elimina a sensibilidade econômica.



Não é bug.



É uma propriedade do modelo.



\---



\# 33. Problema de terminologia



A coluna interna continua chamada:



```text

desconto\_percentual

```



enquanto matematicamente é:



```text

(valor justo - preço atual) / preço atual

```



ou seja:



```text

potencial de valorização

```



A interface já parece ter migrado para "Potencial", o que é bom.



Mas internamente ainda existe o nome antigo.



Não quebra nada, mas aumenta a chance de alguém no futuro interpretar:



```text

desconto = desconto sobre valor justo

```



quando não é isso.



Eu renomearia internamente para:



```text

potencial\_percentual

```



em uma mudança futura de schema.



\---



\# 34. Pontos que eu NÃO considero bugs



É importante separar isso para não começar a alterar coisas que estão funcionando.



Não considero bugs:



\### Graham



```text

sqrt(22,5 × LPA × VPA)

```



com LPA/VPA positivos.



Está coerente com a implementação escolhida.



\### Bazin



Histórico de cinco anos civis.



Está implementado e testado.



\### Correlação



Alinhamento antes de `pct\_change`.



Está correto.



\### FCD negativo



Não transformar artificialmente em zero.



Está correto.



\### Simulador



Limitar perda máxima a:



```text

\-100%

```



está correto para uma ação de responsabilidade limitada.



\### Fallback CVM por empresa



Está bem implementado.



\### Fallback BCB



Está bem estruturado.



\### Cache do ZIP CVM



Está muito bom.



\### Separação dos adapters



Está boa.



\### Proteção contra rodada ruim



Está boa.



\---



\# 35. Ranking final dos problemas



\## 🔴 Prioridade 1 — corrigir



\### BUG 1



`NaN` passa pelas validações financeiras.



Arquivos principais:



```text

modelos/graham.py

modelos/fcd.py

```



Impacto:



```text

valor justo NaN

↓

método considerado aplicável

↓

possível NaN no combinado

```



\---



\## 🟠 Prioridade 2 — corrigir



\### BUG 2



Cache corrompido não é tratado como cache miss.



Principalmente:



```text

fundamentus.py

precos.py

cvm.py

balanco\_cvm.py

gpr.py

b3\_universo.py

crosswalk\_cnpj.py

```



Recomendação:



```text

cache inválido

↓

ignorar

↓

buscar novamente

↓

reescrever atomicamente

```



\---



\## 🟠 Prioridade 3



\### Proveniência Selic/IPCA



Preservar:



```text

fonte\_selic

fonte\_ipca

```



também nos caches.



\---



\## 🟡 Prioridade 4



\### Atomicidade do resultado



Publicar:



```text

screener.csv

\+

macro\_referencia.json

```



como uma operação logicamente única.



\---



\## 🟡 Prioridade 5



\### Sanitizar ticker do TradingView



Evitar interpolação direta no JavaScript.



\---



\## 🟡 Prioridade 6



\### Migrar APIs depreciadas do Streamlit



Principalmente:



```text

use\_container\_width

st.components.v1.html

```



As APIs atuais do Streamlit já indicam essas depreciações.



\---



\## 🟢 Prioridade 7



\### Corrigir warnings dos testes



Remover:



```text

invalid escape sequence '\\$'

```



\---



\## 🟢 Prioridade 8



\### Alinhar Python alvo do mypy



Hoje:



```text

runtime mínimo = 3.12

Ruff = 3.12

mypy = 3.14

```



Melhor padronizar.



\---



\# 36. Prioridade metodológica



Depois dos bugs de programação, eu colocaria estas questões na fila:



\### 1. Normalização do FCF de empresas cíclicas



Provavelmente a investigação mais importante.



\### 2. Crescimento do FCD



Sair de:



```text

CAGR de dois pontos

```



para alguma metodologia que utilize mais informação histórica.



\### 3. Taxa livre de risco



Investigar:



```text

Selic

vs.

título longo em reais

```



antes de considerar o WACC definitivo.



\### 4. Valor combinado



Reavaliar se:



```text

Graham = 33,3%

Bazin = 33,3%

FCD = 33,3%

```



é realmente a melhor agregação.



\---



\# 37. Veredito final



Minha avaliação do código atual:



\*\*Arquitetura: 8,5/10\*\*



\*\*Qualidade de engenharia: 8/10\*\*



\*\*Testes: 9/10\*\*



\*\*Tratamento de dados externos: 8,5/10\*\*



\*\*Robustez de cache: 6,5/10\*\*



\*\*Robustez numérica: 6,5/10\*\*



\*\*Interface Streamlit: 8/10\*\*



\*\*Metodologia financeira: 7/10\*\*



\*\*Documentação: 9/10\*\*



\*\*Estado geral: 8/10\*\*



O ponto mais importante é que \*\*eu não recomendaria reescrever o projeto\*\*.



A estrutura está boa.



O caminho correto agora é fazer uma rodada de correções cirúrgicas:



```text

1\. Corrigir NaN/inf

&#x20;       ↓

2\. Corrigir caches corrompidos

&#x20;       ↓

3\. Tornar caches atômicos

&#x20;       ↓

4\. Corrigir proveniência macro

&#x20;       ↓

5\. Sanitizar TradingView

&#x20;       ↓

6\. Atualizar APIs depreciadas

&#x20;       ↓

7\. Executar 100% da suíte no ambiente real do projeto

&#x20;       ↓

8\. Só depois voltar às decisões metodológicas do FCD

```



A suíte não precisa ser expandida indiscriminadamente. Ela precisa principalmente ganhar \*\*testes de propriedades/edge cases\*\* para os dois bugs novos encontrados:



```text

NaN

inf

cache JSON corrompido

cache CSV corrompido

escrita concorrente

falha ao salvar macro depois de publicar screener

ticker malformado no TradingView

```



Esses são os pontos que eu atacaria antes de adicionar novas funcionalidades ao projeto.





---

# Tratamento (05/10/2026)

Cada item abaixo foi confirmado no código antes de qualquer correção. As correções saíram em commits separados, um por assunto, e a suíte passou de 844 para 1216 testes (todos passando, ruff e mypy limpos).

## Confirmado e corrigido

| Item da auditoria | Resultado | Commit |
|---|---|---|
| 3. `NaN` e infinito viram valor justo | Confirmado com reprodução. Graham, Bazin e FCD ficam "não aplicáveis" com o campo inválido no motivo; o combinado, a divergência, a carteira e o valor de mercado não propagam `NaN`; o `_parse_numero` do Fundamentus devolve `None` para "NaN" e "Infinity"; a rodada do screener é rejeitada se uma linha com sucesso trouxer valor não finito nas colunas de valor. Os testes de propriedade acharam um defeito a mais, que a auditoria não citava: Beta ou Selic finitos e gigantes levantavam `OverflowError` no FCD. Decisão no Bazin: dividendo inválido nos anos usados deixa o método de fora, em vez de ser descartado, porque somar só os válidos subestimaria o pagamento. | `9ac32bc` |
| 4 e 20.1. Cache corrompido e gravação não atômica | Confirmado. JSON truncado levantava `JSONDecodeError` em 4 adapters, e CSV truncado era lido sem erro, com a última linha cortada. Agora o arquivo inválido vira cache ausente e é refeito, e todas as gravações de cache usam arquivo temporário e troca atômica. | `beb52bd` |
| 20.2. Validação de conteúdo do cache | Corrigido em parte: o leitor valida a estrutura (JSON em formato de objeto, CSV com a linha final completa e com as colunas esperadas de cada cache). A finitude dos valores não é checada na leitura do cache; ela é garantida nos modelos e na checagem da rodada (item 3). | `beb52bd` |
| 7. Ticker interpolado no JavaScript do TradingView | Confirmado (baixo impacto: o `.upper()` do campo já neutralizava JavaScript, mas não HTML nem campos do JSON). O widget só é montado para ticker no formato da B3 e a configuração é serializada com `json.dumps`. | `59e2156` |
| 5. Proveniência da Selic e do IPCA | Confirmado. O valor guardado e o arquivo de referência perdiam a fonte de cada valor. Agora cada um preserva a origem da busca original; arquivos antigos, sem as fontes, continuam válidos. | `f11012d` |
| 6. Ordem entre `screener.csv` e `macro_referencia.json` | Confirmado com reprodução. O arquivo de referência passa a ser preparado antes da troca do CSV, e uma falha de gravação deixa o resultado anterior intacto. | `f11012d` |
| 23. Alvo do mypy | Confirmado. `python_version = "3.12"`, igual ao `requires-python` e ao ruff. | `1d5ddb0` |
| 24. `SyntaxWarning` nos testes | Confirmado (4 casos). A correção sugerida pela auditoria (`"R$ 109"`) quebraria os testes, porque o app emite `R\$` (escape do Markdown do Streamlit); o certo é `"R\$"`. | `1d5ddb0` |
| Ruff e a pasta `docs/` | Acréscimo desta rodada: `ruff format .` reformatava os blocos de código dos Markdown; `docs/` entrou no `extend-exclude`. | `1d5ddb0` |
| 8. APIs depreciadas do Streamlit | Confirmado no 1.63.0 (os avisos vão para o log, não para o `warnings` do pytest). `use_container_width` virou `width="stretch"`. A auditoria recomenda `st.html` para `components.html`, mas no 1.63.0 a substituição é `st.iframe`: o `st.html` ignora JavaScript por padrão e o widget precisa dele. O `st.iframe` não tem o parâmetro de rolagem, então o `overflow: hidden` foi para o HTML do widget, para manter a aparência. | `854ee29` |
| 21. Concorrência entre sessões (gravação do cache) | Reaberto pela revisão de código de 05/10: o temporário de nome fixo era disputado por todos os escritores. Cada gravação passa a usar um temporário de nome único e é tratada como tentativa; teste com várias threads. | `0859584` |
| 10 e 11. Suíte sem execução completa | Resolvido: a suíte inteira, incluindo os testes de interface, roda no ambiente do projeto (1216 passando). | — |

Os testes pedidos no veredito final foram escritos: `NaN` e infinito, JSON e CSV corrompidos, falha ao gravar a referência depois de preparar o screener e ticker malformado. O de escrita concorrente veio depois, com a correção do temporário compartilhado (`0859584`).

## Sem ação, e por quê

| Item | Por quê |
|---|---|
| 21. Concorrência entre sessões (travas por chave) | A gravação atômica impede leitura de arquivo pela metade, mas não protegia contra dois escritores no mesmo cache: todos usavam o mesmo temporário, e a revisão de código de 05/10 reproduziu erros e até arquivo final misturado (corrigido, ver acima). Com o temporário de nome único, travas por chave continuam sem ação: duas sessões que gravam a mesma chave gravam o mesmo conteúdo, e o pior caso é uma gravação perdida, que a consulta seguinte refaz. No Windows, `os.replace` pode falhar com o arquivo aberto por outro processo; a gravação agora é uma tentativa e não derruba a consulta. |
| 22. Pacote relocável | O uso é o repositório (GitHub e Streamlit Community Cloud, com `pip install -e .`); um wheel fora dessa estrutura não é um cenário suportado hoje. |
| 33. Renomear `desconto_percentual` | É coluna do `screener.csv`, lido pelo app, pelo workflow e pelos testes; renomear é uma migração de schema, não uma correção. A tela já mostra "Potencial". Fica para quando houver outra mudança de schema. |
| 14, 15 e 36. Crescimento por dois pontos, empresas cíclicas | Limitações metodológicas já conhecidas e investigadas em 04/10, ainda não implementadas; seguem na fila metodológica, depois desta rodada. |
| 16 e 36. Selic como taxa livre de risco | Decisão registrada no relatório de 04/10, coerente com o código; a revisão pede uma investigação própria. |
| 17, 18, 19 e 36. Valor combinado e cenários do simulador | Escolhas de modelo, documentadas na tela. |
| 31 e 32. Risco sacado e sensibilidade ao valor terminal | O ajuste de risco sacado é decisão metodológica (a identificação por texto só vira problema com um caso real perdido), e o aviso de valor extremo já existe. |
| 25. Dependência do Yahoo Finance | Risco operacional externo, já isolado no adapter de preços. |
| 9, 12, 26 a 30 e 34. Pontos positivos e itens que a auditoria não considera bug | Nada a corrigir. |
