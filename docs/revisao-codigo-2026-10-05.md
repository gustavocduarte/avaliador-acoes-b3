> **Nota de registro (05/10/2026):** esta revisão é de 05/10/2026 e cobre o código novo desse dia, feita sobre um ZIP do repositório. O texto abaixo está como foi recebido, sem alterações.

---

# Revisão de código — 05/10/2026

Revisão focada no código novo de 05/10/2026 (validação de números finitos, cache seguro e gravação atômica, ticker do TradingView, proveniência da Selic/IPCA e ordem de gravação do screener) e nas diferenças de comportamento entre Windows (desenvolvimento) e Linux (CI e GitHub Actions, `ubuntu-24.04`).

## Resumo dos achados

| # | Achado | Arquivo | Classificação | Evidência |
|---|---|---|---|---|
| 1 | `gravar_texto_atomico()` não é seguro contra duas gravações simultâneas | `src/avaliador_b3/ingest/_cache.py` | Bug, severidade média/alta | Reproduzido (20 threads, 15 com `FileNotFoundError`) |
| 2 | `screener.csv` e `macro_referencia.json` não são publicados de forma conjunta | `src/avaliador_b3/screener.py` | Bug | Reproduzido (falha forçada no segundo `os.replace`) |
| 3 | `macro_referencia.json.novo` pode ficar abandonado | `src/avaliador_b3/screener.py` | Bug secundário, severidade baixa | Reproduzido (junto com o achado 2) |
| 4 | Concorrência no próprio `rodar_screener()` | `src/avaliador_b3/screener.py` | Bug, severidade média | Leitura do código |
| 5 | `ler_csv_cache()` aceita um CSV só com cabeçalho | `src/avaliador_b3/ingest/_cache.py` | Sugestão de robustez | Leitura do código e teste existente |
| 6 | `ler_json_cache()` aceita `NaN` e `Infinity` | `src/avaliador_b3/ingest/_cache.py` | Melhoria de robustez | Comportamento do `json.loads` |
| 7 | `os.replace()` se comporta diferente no Windows e no Linux | geral | Risco operacional de portabilidade | Comportamento do sistema operacional |

---

## 1. Bug: `gravar_texto_atomico()` não é seguro contra duas gravações simultâneas

**Arquivo:** `src/avaliador_b3/ingest/_cache.py`, linhas 31, 33 e 34.

```python
temporario = caminho.with_name(caminho.name + ".tmp")   # linha 31
temporario.write_text(texto, encoding="utf-8", newline="")  # linha 33
os.replace(temporario, caminho)                          # linha 34
```

É o problema mais importante encontrado na implementação nova.

A documentação do tratamento da auditoria externa diz que "a gravação atômica já garante que ninguém lê arquivo pela metade". Isso é verdade quando há um único escritor, mas não basta quando há dois escritores ao mesmo tempo.

### O problema

Todos os escritores usam exatamente o mesmo arquivo temporário (`x.json.tmp`). Não existe um temporário exclusivo por escritor:

```text
Sessão A                     Sessão B
--------                     --------
x.json.tmp ← escreve
                             x.json.tmp ← escreve
os.replace(tmp, x.json)
                             os.replace(tmp, x.json)   ← o temporário já não existe
```

### Reprodução

Execução com 20 threads simultâneas, todas chamando `gravar_texto_atomico(target, ...)` para o mesmo arquivo. Resultado:

- 15 threads terminaram com `FileNotFoundError`;
- o arquivo final existe;
- o arquivo temporário não existe.

Erro obtido:

```text
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/.../x.txt.tmp' -> '/tmp/.../x.txt'
```

Ou seja, uma chamada legítima de cache pode falhar apenas porque outra sessão está gravando o mesmo cache ao mesmo tempo. É uma reprodução real, não uma hipótese.

### Consequência

Não é corrupção silenciosa garantida, mas pode fazer uma consulta falhar:

```text
requisição A: cache ausente → busca externa → grava o cache
requisição B: cache ausente → busca externa → grava o mesmo cache → FileNotFoundError
```

No Streamlit, duas sessões podem consultar o mesmo ticker ao mesmo tempo.

**Severidade:** média/alta.

---

## 2. Bug: `screener.csv` e `macro_referencia.json` não são publicados de forma conjunta

**Arquivo:** `src/avaliador_b3/screener.py`, linhas 787–788, 801 e 802–803.

A mudança de ordem não resolveu o problema por completo. O código prepara o arquivo de referência antes de trocar o CSV:

```python
# O arquivo de referência é preparado antes de trocar o CSV...
```

e depois publica os dois:

```python
os.replace(caminho_novo, caminho_saida)

if grava_macro:
    os.replace(caminho_macro_novo, caminho_macro)
```

A sequência fica:

```text
1. prepara o macro
2. publica o screener.csv
3. publica o macro_referencia.json
```

Isso melhora bastante o caso de falha ao preparar ou gravar o macro, porque o CSV anterior continua intacto. Mas existe um segundo caso:

```text
macro preparado → screener.csv publicado → os.replace do macro_referencia.json falha
```

Nesse caso fica:

```text
screener.csv           = NOVO
macro_referencia.json  = ANTIGO
```

### Reprodução

Estado inicial com `screener.csv` e `macro_referencia.json` antigos, e uma falha simulada especificamente em `os.replace(caminho_macro_novo, caminho_macro)`. Resultado: `rodar_screener()` levantou `PermissionError`, e depois disso o `screener.csv` estava novo e o `macro_referencia.json` continuava o antigo.

O problema foi confirmado por execução, não só por leitura.

### Relevância no Windows

No Linux, `os.replace()` normalmente consegue substituir um arquivo mesmo que outro processo o esteja lendo. No Windows, se outro processo mantiver o arquivo aberto sem permitir exclusão compartilhada, `os.replace()` pode levantar `PermissionError`. Por isso o cenário reproduzido é mais plausível no Windows do que no Linux.

No ambiente de produção (GitHub Actions, Ubuntu 24.04) o risco é menor; no desenvolvimento em Windows, merece atenção.

---

## 3. Bug secundário: `macro_referencia.json.novo` pode ficar abandonado

Quando `os.replace(caminho_novo, caminho_saida)` funciona e o `os.replace(caminho_macro_novo, caminho_macro)` seguinte falha, não há `try/except` em volta desse segundo estágio. Na reprodução do achado 2, o diretório ficou com:

```text
macro_referencia.json.novo
screener.csv
macro_referencia.json
```

**Severidade:** baixa. Não corrompe o resultado diretamente e provavelmente é sobrescrito na execução seguinte; é principalmente sujeira operacional, mas é sintoma do problema do achado 2.

---

## 4. Bug: concorrência no próprio `rodar_screener()`

**Arquivo:** `src/avaliador_b3/screener.py`, linhas 735, 736, 652, 687 e 688.

A decisão de não usar travas também deixa este caso descoberto. Os nomes dos arquivos da rodada são fixos:

```python
caminho_novo = caminho_saida.with_name(caminho_saida.name + ".novo")          # linha 735
caminho_rejeitado = caminho_saida.with_name(caminho_saida.stem + ".rejeitado.csv")  # linha 736
```

Duas execuções simultâneas usam o mesmo `screener.csv.novo` e o mesmo `screener.rejeitado.csv`.

### Diferença em relação à concorrência do cache

No cache, duas sessões podem disputar um arquivo como `PETR4.csv.tmp`. Aqui, são duas rodadas completas disputando o `screener.csv.novo`. A função `_executar_rodada()` abre o arquivo em modo de escrita e grava de forma incremental:

```python
with open(caminho_saida, "w", ...)   # linha 652
...
escritor.writerow(linha)            # linha 687
arquivo.flush()                     # linha 688
```

### Consequências possíveis

```text
A começa e escreve PETR4
B começa, abre o screener.csv.novo com "w" e apaga o conteúdo de A
A continua e escreve VALE3
B continua e escreve ITUB4
```

O arquivo temporário pode acabar com uma mistura das duas rodadas. Pior: se A falhar, ela executa `caminho_novo.unlink()` e pode apagar o temporário que B está usando. No Linux, um processo pode continuar escrevendo num arquivo já removido; no Windows, o comportamento é mais problemático porque o arquivo pode estar aberto.

### O GitHub Actions está protegido

O workflow `.github/workflows/atualiza-screener.yml` tem:

```yaml
concurrency:
  group: atualiza-screener
  cancel-in-progress: false
```

Isso impede duas rodadas simultâneas no workflow oficial e reduz bastante o risco ali.

### O Streamlit não está protegido

Duas sessões do Streamlit podem clicar em "Rodar screener agora" ao mesmo tempo. Não há trava nem identificador único da rodada que impeça isso.

**Severidade:** média. Não deve acontecer no uso normal, mas é uma condição de corrida real.

---

## 5. Sugestão: `ler_csv_cache()` aceita um CSV só com cabeçalho

**Arquivo:** `src/avaliador_b3/ingest/_cache.py`, linhas 69–75.

A função verifica se o arquivo termina com quebra de linha:

```python
if not conteudo.endswith(b"\n"):
    ...
```

e se as colunas esperadas existem:

```python
faltando = set(colunas_esperadas) - set(df.columns)
```

Portanto um arquivo com apenas `data,Close` é considerado válido, e há um teste em `tests/test_cache_seguro.py` que determina esse comportamento.

Não é necessariamente um bug, porque alguns caches podem representar legitimamente "nenhum registro". Mas, nos caches que deveriam ter dados, isso pode mascarar um cache vazio.

**Sugestão:** permitir arquivo vazio (por exemplo, com um parâmetro `allow_empty=True`) só nos caches em que vazio é semanticamente válido.

---

## 6. Melhoria: `ler_json_cache()` aceita `NaN` e `Infinity`

O helper `ler_json_cache()` verifica se o JSON é válido e se é um objeto. Mas o parser de JSON do Python aceita como extensão:

```json
{ "valor": NaN }
```

```json
{ "valor": Infinity }
```

e `json.loads(...)` devolve `float("nan")` ou `float("inf")` sem que `ler_json_cache()` considere o arquivo corrompido.

Isso não reabre o bug principal da auditoria externa, porque os modelos agora têm as proteções de finitude. Mas mostra que "cache JSON estruturalmente válido" não é o mesmo que "cache JSON semanticamente saudável".

**Classificação:** melhoria de robustez; não precisa de correção imediata.

---

## 7. Risco de portabilidade: `os.replace()` no Windows e no Linux

- **Linux:** `os.replace()` normalmente substitui o arquivo de destino mesmo que ele esteja sendo lido por outro processo.
- **Windows:** um arquivo aberto por outro processo pode impedir a substituição, dependendo dos modos de compartilhamento, e `os.replace()` pode levantar `PermissionError`.

Por isso `os.replace()` é adequado para o ambiente de produção em Linux, mas não garante o mesmo comportamento no Windows. Isso não significa que o projeto esteja errado, apenas que, nesse ponto, o desenvolvimento em Windows é diferente da produção em Linux.

**Classificação:** risco operacional de portabilidade.


---

# Tratamento (06/10/2026)

Cada achado foi confirmado por reprodução (sem rede e sem gravar em `data/`) antes de qualquer correção. Os testes passaram de 1216 para 1302, todos passando, com ruff e mypy limpos. Os commits seguem a ordem das etapas.

## Confirmado e corrigido

| Achado | Resultado | Commit |
|---|---|---|
| 1. Gravação do cache com duas escritas simultâneas | Confirmado, e pior que o relato: com 20 threads, houve erro em todas as rodadas de teste e, em 29 de 30, o arquivo final ficou ilegível, porque os escritores abriam o mesmo temporário e o `os.replace` publicava o conteúdo misturado. Cada gravação passa a usar um temporário de nome único no diretório do destino e é tratada como tentativa: se falhar (inclusive `PermissionError` no Windows), registra no log, limpa o temporário e não derruba a consulta. O arquivo de referência da rodada usa o modo estrito e continua levantando o erro. Testes com 12 escritores e um leitor, que exigem arquivo final sempre válido e completo (JSON e CSV). | `0859584` |
| 2. `screener.csv` e `macro_referencia.json` sem publicação conjunta | Confirmado (falha forçada no segundo `os.replace`). O macro passa a ser publicado primeiro e o CSV por último; uma falha no meio deixa o CSV anterior intacto e a referência só mais nova. Testes para a falha em cada um dos dois `os.replace`. | `a40097e` |
| 3. `macro_referencia.json.novo` abandonado | Confirmado. Os temporários da rodada são apagados em qualquer falha. | `a40097e` |
| 4. Rodadas simultâneas disputando os arquivos temporários | Confirmado (a segunda rodada falhou em `os.replace`). Temporários com nome único por rodada; o `screener.rejeitado.csv` mantém o nome fixo (o workflow o publica) e é trocado de forma atômica. O app publicado deixa de poder disparar rodadas (item abaixo). | `a40097e`, `5e4133c` |
| App publicado com o botão "Rodar screener agora" | Achado desta rodada: qualquer visitante podia disparar uma rodada. O botão só aparece com o opt-in explícito (`AVALIADOR_B3_PERMITIR_RODAR_SCREENER`, variável de ambiente ou secret), negado por padrão, sem detecção por `localhost`. Sem o opt-in, a aba mostra que o workflow atualiza o screener nos dias úteis, com a data da última atualização. | `5e4133c` |
| 5. CSV só com cabeçalho aceito | Confirmado. Só o cache de dividendos aceita vazio (parâmetro `permite_vazio`); nos demais, o arquivo vira cache ausente. Agravante encontrado na reprodução: um universo vazio fazia a rodada ser aceita com zero linhas e trocar o `screener.csv` por um arquivo só com o cabeçalho; a rodada passa a ser rejeitada se não tiver linhas ou se o universo do Ibovespa vier com menos de 60 ações (`MINIMO_ACOES_UNIVERSO_SCREENER`), com o motivo no resumo. | `3d52763`, `a40097e` |
| 6. `NaN` e `Infinity` no JSON | Confirmado (hoje nenhum cache grava esses valores: 409 arquivos varridos). A leitura os recusa, a gravação nunca os escreve, e `VL_CONTA` e a composição do capital da CVM com `NaN` ou infinito deixam a conta (ou o balanço) indisponível antes de entrar nos cálculos. | `3d52763` |

## Sem ação adicional

| Achado | Por quê |
|---|---|
| 7. `os.replace` no Windows e no Linux | Diferença de plataforma sem correção possível no código. A produção é Linux; no Windows, a gravação de cache passa a ser tentativa (não derruba a consulta) e a publicação da rodada levanta o erro, sem deixar temporários. |
| Travas contra duas rodadas locais simultâneas | Com temporários próprios, cada rodada publica o seu resultado e a última a terminar vence, sem arquivo misturado. Uma trava entre processos pediria uma biblioteca de lock de arquivo, e o workflow já tem `concurrency` próprio. |
| Falha entre as duas trocas da publicação | Se o `os.replace` do CSV falhar depois do macro, o CSV anterior fica e a referência fica mais nova; não há transação entre dois arquivos. A referência é só fallback, com validade de 90 dias. |
