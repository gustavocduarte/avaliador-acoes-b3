> **Nota de registro (06/10/2026):** esta é a segunda revisão de código, de 06/10/2026, feita depois do tratamento da revisão de 05/10/2026. O texto abaixo está como foi recebido, sem alterações.

---

# Revisão de código — 06/10/2026

Segunda revisão de código, feita depois do tratamento da revisão de 05/10/2026.

## Resumo dos achados

| # | Achado | Arquivo | Prioridade | Evidência |
|---|---|---|---|---|
| 1 | Versões da mesma demonstração da CVM podem ser misturadas no cálculo do fluxo de caixa | `src/avaliador_b3/ingest/cvm.py` | Alta | Reproduzido com DFC sintética |
| 2 | Caches da CVM de anos fechados nunca expiram, mas a CVM reapresenta demonstrações | `src/avaliador_b3/ingest/cvm.py` | Alta | Leitura do código e documentação da CVM |
| 3 | Cache JSON com envelope válido, mas conteúdo interno inválido, é aceito | `ingest/fundamentus.py`, `ingest/cvm.py`, `ingest/balanco_cvm.py` | Média | Reproduzido |
| 4 | Divisão por zero em `calcular_acoes_em_circulacao()` | `src/avaliador_b3/ingest/balanco_cvm.py` | Média/baixa | Reproduzido |
| 5 | Beta e volatilidade não removem retornos infinitos | `src/avaliador_b3/empresa/comportamento.py` | Baixa | Leitura do código |
| 6 | A correlação gera `RuntimeWarning` com série sem variação | `src/avaliador_b3/empresa/correlacao.py` (ou equivalente) | Baixa | Aviso na suíte de testes |
| 7 | README parcialmente desatualizado | `README.md` | Portfólio | Leitura |

---

## 1. Bug: versões da CVM podem ser misturadas

**Arquivo:** `src/avaliador_b3/ingest/cvm.py`. **Prioridade: alta.** É o achado mais importante desta revisão.

O código lê todas as linhas do CNPJ:

```python
return [
    linha for linha in leitor
    if _normalizar_cnpj(linha["CNPJ_CIA"]) == cnpj_normalizado
]
```

Depois, para o caixa operacional (CFO) e o de investimento (CFI), usa a primeira linha encontrada:

```python
candidatas = [
    linha for linha in linhas_periodo
    if linha["CD_CONTA"] == codigo
]
return candidatas[0]
```

Se existirem duas versões da mesma demonstração, a primeira linha encontrada pode ser da versão antiga.

Há uma inconsistência no próprio código: existe a função `_versao_das_linhas(...)`, que encontra a maior `VERSAO`, mas ela é usada principalmente para escolher a versão correspondente da DRE (receita). O fluxo de caixa em si continua usando as linhas sem filtrar pela maior `VERSAO`.

### Reprodução

DFC sintética com duas versões:

```text
VERSAO 1:  6.01 = 100   6.02 = -10
VERSAO 2:  6.01 = 200   6.02 = -20
```

O código informa que a versão mais recente é a 2, mas `_cfo_cfi_do_periodo()` usa CFO = 100 e CFI = −10, ou seja, identifica a versão 2 e usa os valores da versão 1.

### Por que importa

A CVM informa que os conjuntos de dados da DFP são atualizados semanalmente com eventuais reapresentações, e ferramentas que trabalham com esses dados tratam `VERSAO` como um campo que precisa ser filtrado, mantendo a versão mais recente por empresa e data. Não é só uma possibilidade teórica.

### Impacto

Pode alterar: caixa operacional, caixa de investimento, capex, juros, risco sacado, fluxo de caixa livre, crescimento do fluxo, FCD, valor justo e o ranking do screener.

### Correção recomendada

Filtrar antes de qualquer extração:

```text
CNPJ → data de referência → maior VERSAO → só então CFO, CFI, capex, juros e risco sacado
```

A mesma proteção deveria existir para a DRE usada no lucro líquido.

---

## 2. Bug relacionado: caches da CVM de anos fechados ficam velhos para sempre

**Arquivo:** `src/avaliador_b3/ingest/cvm.py`. **Prioridade: alta.**

O código estabelece:

```python
if ano < hoje.year - 1:
    return False
```

Ou seja, anos considerados "fechados" nunca expiram. Isso afeta o zip da CVM. Além disso, o resultado do fluxo de caixa (`fcf_<CNPJ>_<ANO>.json`) tem cache versionado por schema, mas sem prazo de validade.

### Cenário

```text
baixa a DFP de 2024 → calcula o fluxo → grava fcf_..._2024.json
passam 6 meses → a CVM reapresenta 2024 → o projeto continua usando o resultado antigo
```

A premissa de que "anos fechados não mudam" não é segura, porque a CVM atualiza os arquivos da DFP semanalmente com eventuais reapresentações.

### Impacto no FCD

O FCD usa o ano de referência e o ano cinco anos antes (por exemplo, 2025 e 2020). Se a DFP de 2020 for reapresentada, o cache pode continuar com o fluxo antigo de 2020, e o crescimento (CAGR) continua calculado sobre o valor antigo, o que altera o valor justo.

### Atenuante

O workflow do GitHub Actions tem proteção parcial: os zips são guardados em cache por semana, e o ano corrente é renovado. Mas isso não resolve os anos antigos: 2025 se atualiza, 2024 e 2020 podem ficar congelados.

### Recomendação

Não é preciso baixar todos os anos todo dia. Opções:

- prazo de validade curto para os anos recentes e semanal ou mensal para os antigos; ou
- atualizar os zips da CVM semanalmente e invalidar o resultado do fluxo de caixa junto com o zip.

O custo de rede é baixo perto do risco de manter congelada uma demonstração reapresentada.

---

## 3. Cache JSON estruturalmente válido, mas internamente inválido

**Arquivos:** `ingest/fundamentus.py` (campo `indicadores`), `ingest/cvm.py` (campo `resultado` do fluxo de caixa), `ingest/balanco_cvm.py` (campo `resultado`). **Prioridade: média.**

`ler_json_cache()` faz `json.loads(...)` e verifica `isinstance(dados, dict)`. Mas alguns caches usam um envelope:

```json
{
  "versao_schema": 5,
  "resultado": {}
}
```

e depois o código faz `return bruto.get("resultado")` sem verificar se `resultado` é realmente um `dict`.

### Reprodução

Com o cache:

```json
{
  "versao_schema": 5,
  "resultado": []
}
```

o cache foi aceito e o resultado foi `[]`, em vez de `None` (cache inválido).

### Consequência

Um cache corrompido dessa forma pode produzir um resultado aparentemente válido (`[]`), quando o código espera um `dict`, e causar `TypeError` ou comportamento inesperado. É menos perigoso que a corrupção parcial, porque a gravação atômica já foi corrigida.

### Correção

```python
resultado = bruto.get("resultado")
if not isinstance(resultado, dict):
    return None
```

---

## 4. Divisão por zero em `calcular_acoes_em_circulacao()`

**Arquivo:** `src/avaliador_b3/ingest/balanco_cvm.py`. **Prioridade: média/baixa.**

Existe a proteção:

```python
razao = referencia / integralizado if integralizado else 0.0
```

mas depois:

```python
divergencia = min(
    abs(referencia / em_circulacao - 1),
    abs(referencia / com_tesouraria - 1),
)
```

Se `integralizado = 0` e `tesouraria = 0`, com uma referência de ações válida (`referencia > 0`), então `em_circulacao = 0` e `com_tesouraria = 0`, e ocorre `ZeroDivisionError`.

### Reprodução

Com a composição `{"integralizado": 0, "tesouraria": 0, "ordinarias": 0, "preferenciais": 0}` e referência positiva, a função levanta `ZeroDivisionError: float division by zero`.

Não é um cenário normal para uma companhia válida, mas o objetivo dessa camada é justamente impedir que dados anômalos da CVM derrubem o processamento. O correto seria tratar como "ações em circulação indisponíveis", com motivo explícito.

---

## 5. Beta e volatilidade não removem retornos infinitos

**Arquivo:** `src/avaliador_b3/empresa/comportamento.py`. **Prioridade: baixa.**

```python
retornos = historico["Close"].pct_change().dropna()
```

Com um fechamento anterior igual a 0 e o seguinte igual a 10, o retorno vira `inf`, e `dropna()` não remove `inf`. Isso pode contaminar `retornos.std()` e `cov()`.

O FCD já verifica a finitude do Beta, então o problema não costuma virar um valor justo silenciosamente errado, mas o bloco "Comportamento da ação" pode exibir valores inválidos.

### Correção

```python
retornos = (
    historico["Close"]
    .pct_change()
    .replace([float("inf"), float("-inf")], float("nan"))
    .dropna()
)
```

A mesma lógica já existe no módulo de correlação.

---

## 6. A correlação gera avisos matemáticos

**Prioridade: baixa.**

A suíte mostra:

```text
RuntimeWarning: invalid value encountered in divide
```

quando testa uma série sem variação. O resultado final é corretamente convertido em `aplicavel = False`, então não é um bug funcional. Mas o cálculo chega a executar `retornos["retorno_a"].corr(...)` antes de perceber que a variância é zero. Seria mais limpo detectar antes:

```python
if retornos["retorno_a"].std() == 0:
    ...
```

---

## 7. README parcialmente desatualizado

**Prioridade:** relevante para o portfólio.

- O README ainda diz que o botão "Rodar screener agora" só aparece na execução local, mas o código usa `AVALIADOR_B3_PERMITIR_RODAR_SCREENER` e permite habilitar o botão por variável de ambiente ou secret.
- O README cita "mais de 800 testes" e "96% de cobertura", enquanto o registro do tratamento já fala em 1.302 testes, e a suíte atual é bem maior.

Não quebra o sistema, mas vale corrigir num projeto de portfólio.

---

# Tratamento (19/10/2026)

Cada achado foi confirmado no código antes de qualquer correção. A suíte passou de 1317 testes (antes da D2) para 1372, todos passando, com ruff e mypy limpos.

## Os 7 achados

| # | Achado | Confirmado | Correção | Commit |
|---|---|---|---|---|
| 1 | Versões da CVM misturadas no fluxo de caixa | Reproduzido com DFC sintética. Nos dados reais (Parte A), efeito nulo: zero empresas com versão dupla. | Mantém só a maior `VERSAO` por empresa e data, antes de qualquer extração. | `b7b1267` |
| 2 | Caches da CVM de anos fechados nunca expiram | Confirmado no código. Nos dados reais (Parte A), o zip de 2024 foi regenerado pela CVM sem mudança nos dados usados. | Zips de anos fechados valem 30 dias (o ano em preenchimento segue com 7). Os caches de fluxo de caixa, lucro e balanço guardam o tamanho e a data do zip de origem e são refeitos quando ele muda ou vence. Schemas do FCF (6) e do balanço (2); o lucro ganha envelope versionado. | `8a7aaa9` |
| 3 | Envelope de cache com conteúdo que não é objeto | Reproduzido (`[]` aceito como resultado). | Conteúdo que não é `dict` vale como cache ausente e é refeito, com log, no Fundamentus, no fluxo de caixa, no lucro e no balanço. | `a3aaf2d` |
| 4 | Divisão por zero em `calcular_acoes_em_circulacao` | Reproduzido, inclusive com integralizado zero e tesouraria positiva. | Sem ações em circulação, o número fica indisponível com motivo explícito, e o app usa o do Fundamentus. | `a3aaf2d` |
| 5 | Beta e volatilidade com retornos infinitos | Confirmado: um fechamento zero no meio da série deixava o Beta e a volatilidade em `NaN`. | Retornos infinitos viram `NaN` antes do `dropna`. | `a3aaf2d` |
| 6 | `RuntimeWarning` na correlação | Confirmado: 2 avisos em `test_serie_sem_variacao_fica_nao_aplicavel`. | A série sem variação é detectada antes do `.corr()`. Os avisos da suíte passaram de 13 para 11, e nenhum vem mais da correlação. | `a3aaf2d` |
| 7 | README desatualizado | Confirmado (800 testes, 96%, botão "só na execução local"). | Números, gravação atômica, regras da checagem da rodada e opt-in do botão atualizados. | Este commit |

O commit `cc7fedf` (Etapa 0) registrou a revisão neste documento. As correções saíram em um commit por assunto, na ordem da tabela.

## Acréscimos além da revisão

- **Zip ausente sem validade permanente.** Sem o zip no disco, o cache derivado vale o mesmo prazo (30 dias para ano fechado, 7 para o ano corrente), contado pela data do zip guardada no próprio cache. Sem essa data, o cache não vale (`8a7aaa9`).
- **Fechamento não positivo descartado na origem.** `ingest/precos.py` descarta fechamento zero ou negativo junto com o vazio, o que protege todos os consumidores do histórico, inclusive os gráficos. A troca de ±inf por `NaN` em `comportamento.py` e `correlacao.py` continua como defesa (`a3aaf2d`). A regra vale também para o petróleo: um preço negativo de futuro, como o do WTI em abril de 2020, seria descartado.
