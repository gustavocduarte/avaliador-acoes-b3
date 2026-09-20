# Vistoria pré-publicação — Fase 1 (2026-09-20)

Vistoria somente-leitura (nenhum arquivo alterado nesta fase), com dois
focos específicos, diferentes da auditoria de 2026-09-18
(`docs/auditoria-2026-09-18.md`), que já cobriu `src/avaliador_b3/` módulo a
módulo:

- **Parte A**: delta introduzido pela sessão do tema de cores (dark
  navy/dourado) — tudo que não existia, ou não tinha o formato atual, na
  auditoria anterior.
- **Parte B**: prontidão de publicação do repositório como um todo — como
  ele aparece pra alguém de fora, não a qualidade do código Python em si.

---

## Parte A — Delta desde a última auditoria (sessão do tema de cores)

### A.1 `.streamlit/config.toml` (novo)

Arquivo de 9 linhas, só a seção `[theme]`: `base`, 4 cores, 3 chaves de
fonte (`font`/`headingFont`/`codeFont`, todas apontando pra IBM Plex Sans
ou Mono via URL do Google Fonts, sintaxe `"Nome:URL"` confirmada contra a
documentação oficial na sessão anterior). Nenhum achado — arquivo pequeno,
sem lógica, consistente com o que foi decidido e verificado visualmente.

### A.2 Constantes `COR_*` em `config.py`

8 constantes novas, ao final do arquivo (linhas 559-595): `COR_GRAFICO_FUNDO`,
`COR_GRAFICO_TEXTO`, `COR_GRAFICO_PROTAGONISTA`, `COR_GRAFICO_CONTEXTO`,
`COR_GRAFICO_GRADE`, `COR_GANHO`, `COR_PERDA`, `COR_NEUTRA`. Todas
importadas e usadas em `app/main.py` (confirmado via grep, nenhum import
morto — ver A.5).

### A.3 `CORES_CENARIO` — inconsistente com o resto da paleta (achado)

**Achado — CONSISTÊNCIA (prioridade média)**: `CORES_CENARIO` (nome real
confirmado, `app/main.py:1435-1439`) é um dict **local**, definido dentro do
corpo da função de `aba_carteira` (recriado a cada rerender da aba), não uma
constante em `config.py`:

```python
CORES_CENARIO = {
    "pessimista": COR_PERDA,
    "base": COR_NEUTRA,
    "otimista": COR_GANHO,
}
```

Isso é inconsistente com o padrão que a própria sessão do tema estabeleceu:
`COR_GRAFICO_*`, `COR_GANHO`, `COR_PERDA` e `COR_NEUTRA` — os blocos que
`CORES_CENARIO` referencia diretamente — vivem todos em `config.py`, cada
um com comentário de origem/motivo. `CORES_CENARIO` é só uma *combinação*
desses tokens já centralizados (não introduz cor nova), então o dict em si
poderia perfeitamente estar em `config.py` junto dos outros, seguindo o
mesmo padrão. Hoje ele é a única peça da paleta que não segue essa
convenção. Não corrigido nesta fase, só reportado, conforme pedido.

### A.4 Cores efetivamente aplicadas vs. decisão documentada

Sem resíduo de placeholder/rascunho. Busquei por hex codes do Plotly padrão
que apareceram em versões intermediárias da implementação
(`#636EFA`/`#00CC96`/`#EF553B`/`#00d4ff`, case-insensitive) em todo
`src/`/`tests/` — nenhuma ocorrência. O mapeamento efetivamente aplicado
bate exatamente com o decidido: pessimista→`COR_PERDA`, otimista→
`COR_GANHO`, base→`COR_NEUTRA`, linha de inflação→`COR_GRAFICO_CONTEXTO`
(`app/main.py:1502`).

### A.5 Imports mortos, variáveis mortas, comentários desatualizados

**Imports/variáveis**: nenhum morto. Os 8 `COR_*` importados em
`app/main.py` (linhas 32-39) são todos referenciados pelo menos uma vez
(confirmado por grep, contagem de uso ≥ 1 para cada). `ruff check` (rodado
do zero na Parte B, item B.7) confirma isso de forma independente — não
haveria import não utilizado sem o ruff acusar (`F401` está no conjunto de
regras selecionado, `select = ["E", "F", "I", "UP"]`).

**Achado — CONSISTÊNCIA / DOCUMENTAÇÃO (prioridade baixa)**: o comentário de
`COR_NEUTRA` (`config.py:590-594`) descreve um propósito que **não é o uso
real** da constante:

```python
# Cor neutra pra estados "não aplicável"/indisponível (ex: correlação
# sem observações suficientes) — distinta tanto do dourado de destaque
# quanto do vermelho de erro/perda, pra "indisponível" não parecer nem
# erro nem destaque. Mesmo tom de COR_GRAFICO_CONTEXTO (mesma função:
# neutro, não deve chamar atenção).
COR_NEUTRA = "#5B6B7C"
```

O único uso real de `COR_NEUTRA` no código é `CORES_CENARIO["base"]`
(`app/main.py:1437`, cor da curva "base" no gráfico de projeção) — **não**
nos cartões de método/correlação "não aplicável"/indisponível que o
comentário descreve. Isso foi decidido explicitamente na sessão anterior
(o `st.metric`/`st.caption` nativos já tratam esse estado via opacidade,
sem precisar de cor customizada — não dá pra injetar `COR_NEUTRA` ali sem
HTML bruto), mas o comentário em `config.py` nunca foi atualizado pra
refletir essa decisão. Hoje ele descreve um caso de uso que existe só na
intenção original, não no código.

### A.6 Padrão de comentário dos 8 novos tokens

Os 8 tokens seguem, em espírito, o mesmo padrão do resto do arquivo
(bloco de comentário explicando o motivo antes do valor, não só o valor
solto) — mas com uma diferença de natureza, não de forma: o docstring do
módulo diz "toda constante aqui deve citar a **fonte** que a valida", e
todo o resto do arquivo cita fontes externas verificáveis (API, paper
acadêmico, investigação real contra um endpoint). Os `COR_*` são decisões
de design, não fatos externos — não têm uma "fonte" no mesmo sentido, e os
comentários citam a **justificativa de design** (o que substitui, pra esse
tipo de constante, o papel que a fonte cumpre pras outras). Não é uma
violação real da política do arquivo, só uma categoria diferente de
constante que o docstring original não previa explicitamente — sinalizo
como observação, não como achado a corrigir.

---

## Parte B — Prontidão para publicação (organização)

### B.1 README.md — **desatualizado (prioridade ALTA)**

Lido por completo (23 linhas). Dois problemas:

1. **Seção "Status" (linha 14-17) está completamente errada**: diz "Em
   desenvolvimento inicial — estrutura de pastas definida, adapters de
   dados ainda não implementados." O projeto tem hoje 7 adapters
   implementados e testados (`ingest/`), 4 modelos de valuation, um
   dashboard Streamlit com 3 abas funcionais (análise individual,
   screener, simulador de carteira), painel de correlação, e agora um
   tema visual completo — 44 commits de histórico. Essa seção descreve o
   estado do projeto de quando ele tinha só a estrutura de pastas, não o
   estado atual.
2. **Nenhuma instrução de instalação/execução** — não há seção de
   "Como rodar", não menciona `requirements.txt`, `pip install`, Python
   3.12+, nem o comando `streamlit run src/avaliador_b3/app/main.py`. Não
   dá pra "confirmar que as instruções funcionam contra o
   pyproject.toml/requirements.txt atual" (pedido do item 5) porque **não
   existem instruções pra testar** — gap total, não um erro pontual.

Sem resíduo do Monitor de conflitos (GDELT) — busquei "gdelt"/"monitor de
conflito" (case-insensitive) em `README.md` e `docs/especificacao.md`,
nenhuma ocorrência. Consistente com o que já foi checado no Lote 5.

`docs/especificacao.md` (151 linhas, lido por completo) é explicitamente um
documento de planejamento pré-implementação ("escrito antes de qualquer
código de implementação") — seu propósito é histórico, não é esperado que
reflita o estado atual linha a linha. Único ponto secundário: a linha
"Segmento de listagem... **Em aberto**" (linha 139) já foi resolvida
(`b3_universo.py`/`SEGMENTOS_LISTAGEM_B3`) mas o documento não foi
atualizado — baixa prioridade, natureza diferente do problema do README
(este é o documento de planejamento, não o cartão de visita do repo).

### B.2 LICENSE — ausente

Confirmado: nenhum arquivo `LICENSE`/`LICENSE.md`/`LICENSE.txt` na raiz.
Não criei nenhum — só reportando pra decisão sua, conforme pedido.

### B.3 `.gitignore` / `git status`

`git status` na raiz do working tree: limpo, nada pendente. `git ls-files`
(57 arquivos rastreados) — revisei a lista inteira, nada sensível: sem
`.json`/`.csv` de cache, sem `secrets.toml`, sem `.env`. Os únicos
binários/dados rastreados são fixtures de teste legítimas e pequenas
(`tests/fixtures/*.zip`, `*.html`). `data/raw/` no disco tem 446 arquivos
de cache reais (7 subpastas por fonte) — nenhum rastreado, `.gitignore`
funcionando como esperado.

**Achado — prioridade baixa**: `.pytest_cache/` e `.ruff_cache/` existem no
disco mas **não estão listados no `.gitignore` do projeto**. Eles não
aparecem em `git status`/`git ls-files` hoje só porque `pytest`/`ruff`
geram, cada um, seu **próprio** `.gitignore` interno
(`.pytest_cache/.gitignore` e `.ruff_cache/.gitignore`, ambos com `*`) —
confirmado via `git check-ignore -v`. Ou seja, o projeto está protegido por
acidente/convenção da ferramenta, não pela configuração do próprio
`.gitignore`. Se alguém rodar essas ferramentas com `--cache-dir` custom,
ou uma versão futura parar de gerar esse `.gitignore` automático, esses
diretórios de cache passam a aparecer como untracked. Recomendo adicionar
`.pytest_cache/` e `.ruff_cache/` explicitamente.

### B.4 `pyproject.toml` / `requirements.txt` vs. imports reais

`pyproject.toml` não tem seção `[project]` — só `[tool.pytest.ini_options]`
e `[tool.ruff]`. O projeto não é instalável via `pip install -e .`
(consistente com o comentário já existente em `app/main.py:12-15` sobre o
hack de `sys.path`). Toda dependência declarada vive em `requirements.txt`.

Imports reais de terceiros em `src/` (via grep de `^import`/`^from`):
`numpy`, `pandas`, `plotly`, `requests`, `streamlit`, `yfinance`, `bs4`
(nome de import de `beautifulsoup4` — correto, não é um pacote extra).
Todos declarados em `requirements.txt`. Nenhuma dependência usada-mas-não-
declarada encontrada (`tests/` também conferido, mesma conclusão).

**Achado — prioridade baixa**: duas dependências declaradas em
`requirements.txt` sem uso confirmado no código:
- `lxml` (linha 9): o único parser HTML do projeto é
  `BeautifulSoup(html, "html.parser")` (`ingest/fundamentus.py:79`) — usa o
  parser embutido do Python, não o `lxml`. Nenhuma outra referência a
  `lxml` em `src/`.
- `openpyxl` (linha 11): o único `pd.read_excel` do projeto
  (`ingest/gpr.py:90`) lê os arquivos `.xls` do GPR (`URLS_GPR` em
  `config.py`, extensão `.xls`, não `.xlsx`) — pandas usa `xlrd` pra esse
  formato legado, não `openpyxl` (que só serve `.xlsx`/`.xlsm`). `xlrd`
  (linha 10) está corretamente declarado e é de fato necessário; `openpyxl`
  não tem consumidor identificado hoje.

Não removi nenhuma das duas — pode ser intencional (margem de segurança
caso uma fonte mude de formato) ou sobra; decisão sua.

### B.5 Estrutura de pastas

Árvore (2 níveis, excluindo `.git`/`.venv`) confere com o esperado:
`data/{processed,raw}`, `docs/` (2 arquivos), `src/avaliador_b3/` (pacote),
`tests/` (rachadas por módulo + `fixtures/`), `pyproject.toml`,
`requirements.txt`, `README.md`, `.streamlit/config.toml`. Busquei por
artefatos soltos de desenvolvimento (`*.bak`, `*.ipynb`, `*.log`, `*.tmp`,
`scratch*`, `test_manual*`, `*_old.*`, `*copy*`) em todo o projeto
(excluindo `.git`/`.venv`/`.claude`) — nenhum encontrado. Nada a reportar.

### B.6 `git log` — histórico completo

44 commits (`af7e786` até `b6b3ca9`). Busquei trailers de atribuição
(`co-authored-by`, `claude-session`, `generated with`, case-insensitive) em
**todo** o histórico — zero ocorrências, confirmando o padrão desta sessão
inteira sem exceção, incluindo os commits mais antigos (antes desta
sessão). Mensagens fazem sentido como histórico de portfólio: descrevem o
"o quê" de forma específica (não genéricas tipo "fix bug"), em português,
progressão lógica (adapters → modelos → dashboard → refinamentos →
limpeza). O histórico inclui a trajetória completa do Monitor de conflitos
(adicionado, refinado 2x, removido) — isso é transparente e normal pra um
histórico real de desenvolvimento, não algo a esconder/squashar.

### B.7 `pytest` + `ruff`, do zero (sem cache)

Removi `.pytest_cache/`, `.ruff_cache/` e todo `__pycache__/` do projeto
antes de rodar (exceto dentro de `.venv/`), pra garantir execução
realmente fria:

```
pytest -q -p no:cacheprovider  →  316 passed, 2 warnings in 17.88s
ruff check --no-cache src/ tests/  →  All checks passed!
```

Os 2 warnings (`RuntimeWarning: invalid value encountered in divide`, em
`test_correlacao.py::test_serie_sem_variacao_fica_nao_aplicavel`) são
esperados — o teste exercita deliberadamente uma série sem variação
(std=0), o `numpy` avisa sobre a divisão e o código trata o resultado
(`NaN`) corretamente como "não aplicável" a seguir. Não é uma regressão.

---

## 3. Resumo executivo

### 3.1 Lista priorizada de achados

| # | Prioridade | Área | Local | Achado |
|---|---|---|---|---|
| 1 | **ALTA** | Publicação | `README.md:14-17` | Seção "Status" descreve o projeto como "adapters ainda não implementados" — completamente desatualizada frente ao estado real (7 adapters, dashboard de 3 abas, tema completo, 44 commits). |
| 2 | **ALTA** | Publicação | `README.md` (ausente) | Nenhuma instrução de instalação/execução (`pip install`, Python 3.12+, comando `streamlit run`) — gap total, não um erro pontual. |
| 3 | Média | Delta do tema | `app/main.py:1435-1439` | `CORES_CENARIO` é dict local em `app/main.py`, não constante em `config.py` — inconsistente com `COR_GRAFICO_*`/`COR_GANHO`/`COR_PERDA`/`COR_NEUTRA`, que centralizam toda cor da paleta. |
| 4 | Baixa | Delta do tema | `config.py:590-594` | Comentário de `COR_NEUTRA` descreve uso em cartões "não aplicável"/indisponível — mas o único uso real é `CORES_CENARIO["base"]` no gráfico de projeção. Comentário não reflete a decisão tomada na sessão anterior. |
| 5 | Baixa | Publicação | `.gitignore` | `.pytest_cache/`/`.ruff_cache/` não estão listados explicitamente — hoje ficam de fora do repo só pelo `.gitignore` interno que as próprias ferramentas geram, não por configuração do projeto. |
| 6 | Baixa | Publicação | `requirements.txt:9,11` | `lxml` e `openpyxl` declarados sem uso confirmado no código (`BeautifulSoup` usa `html.parser`; o único `read_excel` lê `.xls`, que usa `xlrd`, não `openpyxl`). |
| 7 | Informativo | Publicação | — | `LICENSE` ausente — decisão seu, não criei nada. |
| 8 | Informativo | Publicação | `docs/especificacao.md:139` | "Segmento de listagem: Em aberto" já foi resolvido na implementação mas o documento de planejamento não foi atualizado — natureza diferente do achado #1 (este é o doc de planejamento histórico, não o cartão de visita). |

Nenhum achado de **CORRETUDE** (bug que muda comportamento/resultado) nesta
vistoria — os dois focos (delta do tema, organização do repo) são, por
natureza, mais sobre consistência/documentação/prontidão de publicação do
que sobre lógica de cálculo, que já foi o foco da auditoria anterior.

### 3.2 Testes e lint

`pytest` (316 testes) e `ruff` passam limpos, do zero, sem cache — nenhuma
regressão introduzida pela sessão do tema ou por qualquer mudança desde a
auditoria de 2026-09-18.

### 3.3 Observação de fechamento

Os achados #1 e #2 (README) são os únicos que eu classificaria como
bloqueantes pra uma publicação séria — é a primeira coisa que qualquer
visitante lê, e hoje ela ativamente subestima o projeto. Os achados #3-#6
são pequenos e de baixo risco, dá pra agrupar num lote único de limpeza se
decidir corrigir. #7 e #8 são só informativos, aguardando sua decisão.

Não apliquei nenhuma correção — aguardando sua revisão pra decidir o que
vira lote.
