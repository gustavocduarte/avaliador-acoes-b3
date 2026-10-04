# Investigação do fluxo-base do FCD: capital de giro e empresas cíclicas — 04/10/2026

Investigação só de leitura, aberta pela decisão registrada em `docs/investigacao-p10-2026-10-04.md` (seção 7, itens 2 e 4). Nenhum código, teste ou dado versionado foi alterado. Scripts, caches e downloads ficaram em `%TEMP%\investigacao_fluxo_base`; este relatório é o único arquivo novo.

**Convenções.** **CONFIRMADO** = lido no código, medido nos dados da CVM ou calculado com as funções do projeto. **HIPÓTESE** = plausível, não verificado (em geral, depende das notas explicativas). Os cálculos usam as 53 ações com FCD do `screener.csv` regenerado em 04/10/2026 (commit `c27f3ed`), com as entradas reais de cada chamada do FCD capturadas na rodada desse dia, e as DFC de 2019 a 2025 lidas dos zips da CVM com as funções existentes de `ingest/cvm.py`.

**Critério.** Cada alternativa é julgada pela coerência econômica da regra. A distância entre o FCD e o preço aparece só como informação.

**Como as alternativas foram calculadas.** As funções do projeto foram importadas sem alteração e chamadas com os mesmos parâmetros da rodada, variando só o fluxo-base. **CONFIRMADO:** o fluxo recomposto de 2025 coincide com o usado hoje (diferença 0) e a réplica do FCD atual coincide com o valor do CSV (diferença 0). Duas escolhas de implementação:
- N1 e N4 mudam a **definição** do fluxo, então valem para o ano de referência e para o ano-base do crescimento (o CAGR compara a mesma definição nas duas pontas).
- N2 e N3 mudam só o **nível** do fluxo de referência. Em N2 o crescimento fica o atual; em N3 o crescimento passa a ser o da receita (ver 3.4). O teto pela receita e a faixa de −20% a +30% seguem valendo em todas.

## 1. Resumo executivo

- As 53 ações usam a DFC pelo método **indireto** (consolidada em 50 e individual em 3) em todos os anos de 2019 a 2025, então 6.01.01, 6.01.02 e 6.01.03 existem em todas (só a AURE3 não tem 2019 e 2020).
- **Juros pagos** estão em 6.01.03 na maioria (22 empresas), mas em 6.01.02 em 9 empresas e em 6.01.01 em 2; o **imposto de renda pago** está em 6.01.02 (22 empresas) ou em 6.01.03 (27). A soma de volta atual dos juros não depende da subconta; as alternativas que tiram 6.01.02 precisam tratar isso.
- **N1 (sem capital de giro)** superestima quem cresce: nas 29 ações com receita crescendo 12% ao ano ou mais, o capital de giro de 2021 a 2025 consome 43% do fluxo acumulado (mediana) e tirá-lo eleva o FCD em 47% (mediana). Descartada.
- **N2 (giro médio)** e **N3 (margem média × receita)** dependem de janelas curtas (3 ou 5 anos; 7 anos) e movem o FCD nos dois sentidos, com extremos grandes (N3: de −43% a +14.581%).
- **N4 (risco sacado)** acha linhas de convênio com fornecedores no 6.03 em MGLU3, RENT3, FLRY3 e VIVA3. Na MGLU3 elas somam −R$ 12,3 bi (2024) e −R$ 13,5 bi (2025), 92% a 93% do aumento de fornecedores em 6.01.02; o FCD da MGLU3 vai de R$ 102,16 para −R$ 1,14.
- **Recomendação:** adotar N4 (reclassificação explícita, objetiva e estreita). As empresas cíclicas (VALE3, GGBR4) seguem como limitação documentada: N3 é a resposta conceitual, mas a janela de 2019 a 2025 não cobre um ciclo completo e o efeito é extremo (PETR4 de R$ 44,55 para R$ 141,93).

## 2. Estrutura dos dados

### 2.1 Método da DFC (CONFIRMADO)

| Ano | Indireto (MI) consolidada | Indireto (MI) individual | Direto (MD) |
|---|---|---|---|
| 2025 (referência) | 50 | 3 | 0 |
| 2020 (ano-base) | 49 | 3 | 0 |

Em 2020 a AURE3 não tem DFC na CVM (nem em 2019), então são 52 ações com demonstração. Nenhuma das 53 usa o método direto em ano algum de 2019 a 2025 (a escolha do projeto é MI primeiro). A separação entre 6.01.01, 6.01.02 e 6.01.03 só existe no MI, e vale para todas.

### 2.2 Significado das subcontas (CONFIRMADO)

Em **369 empresas-ano** (53 ações × 7 anos, menos 2 da AURE3), as descrições de 6.01.01, 6.01.02 e 6.01.03 são exatamente as esperadas: "Caixa Gerado nas Operações" (antes do capital de giro), "Variações nos Ativos e Passivos" (capital de giro) e "Outros". Nenhuma exceção. A identidade 6.01 = 6.01.01 + 6.01.02 + 6.01.03 vale nas 369. A soma das subcontas de 6.01.02 bate com a conta em 367; as 2 diferenças são EGIE3 2021 (−R$ 736 mi contra −R$ 735 mi, arredondamento) e TEND3 2023 (R$ 72 mi contra −R$ 4 mi, uma subconta de nível mais fundo).

### 2.3 Onde ficam os juros pagos e o imposto pago (CONFIRMADO)

| Item | Em 6.01.01 | Em 6.01.02 | Em 6.01.03 |
|---|---|---|---|
| Linhas de juros pagos identificadas (198 empresas-ano) | 4 (AZZA3 em 2019; KLBN11 em 2019 a 2021) | 36 | 158 |
| Empresas com juros identificados | 2 (AZZA3, KLBN11) | 9 (ABEV3, CURY3, EMBJ3, KLBN11, MRVE3, RENT3, VIVT3, WEGE3, YDUQ3) | 22 |
| Linhas explícitas de imposto de renda pago (empresas-ano) | 9 | 122 | 168 |
| Empresas com linha explícita de imposto pago | 2 | 22 | 27 |

Em 82 empresas-ano não há linha explícita de imposto de renda pago em 6.01 (o imposto vem embutido em outras linhas).

**Consequência.** A soma de volta atual dos juros (`ingest/cvm.py`, `_extrair_juros_pagos_6_01`) olha todas as subcontas de 6.01 e não depende de onde a linha está. Já uma alternativa que tira 6.01.02 inteira (N1) também tira os juros e o imposto pago que estiverem ali, e a soma de volta não pode contar esses juros duas vezes. As variantes de N1 abaixo tratam isso.

### 2.4 Disponibilidade de 2019 a 2025 (CONFIRMADO)

Todas as 53 têm a DFC em todos os anos de 2019 a 2025, exceto a **AURE3** (sem 2019 e 2020; tem 2021 a 2025). Ações que ficam **sem dados** ou **não aplicáveis** em cada alternativa:

| Alternativa | Sem dados | Não aplicável (fluxo-base não positivo) |
|---|---|---|
| N1 | nenhuma | BRAP4, CPLE3, RDOR3 |
| N2, 3 anos | nenhuma | MRVE3, RDOR3 |
| N2, 5 anos | nenhuma | RDOR3 |
| N3 | BRAP4 (receita não positiva) | BRAV3, MRVE3, RDOR3, RENT3, SMFT3 (margem média não positiva) |
| N4 | nenhuma | nenhuma |

## 3. Alternativas

### 3.1 Definições

| Alt. | Regra (escolhas desta investigação) |
|---|---|
| **N1** | Caixa operacional sem 6.01.02, menos capex, mais a soma de volta dos juros. Duas variantes: **literal** (tira 6.01.02 inteira; a soma de volta exclui os juros que estavam em 6.01.02) e **giro puro** (tira só a parte de capital de giro: 6.01.02 sem as linhas de juros pagos e de imposto de renda pago que estiverem nela). |
| **N2** | O 6.01.02 do ano de referência é trocado pela média de 3 anos (2023 a 2025) ou 5 anos (2021 a 2025); o resto do fluxo de 2025 fica igual e o crescimento fica o atual. |
| **N3** | Fluxo-base = margem média (fluxo ÷ receita, 2019 a 2025, mesma demonstração, no mínimo 5 anos) × receita de 2025. Margem média não positiva: o FCD não se aplica. |
| **N4** | Do caixa operacional (6.01) sai o valor das linhas de 6.03 descritas como risco sacado, convênio com fornecedores, cessão de crédito por fornecedores ou forfait. Termos em lista, com exclusão de "parcelamento". A tabela principal usa o **sinal da linha** (saída reduz o caixa operacional, entrada o aumenta), o N4 "simétrico"; a seção 4.3 mostra por que a regra recomendada vale só para **saídas**, com o saldo líquido anual das linhas do mesmo programa. |
| **N5** | Combinações: **N2 (3 anos) + N4** (a média do giro é feita sobre o 6.01.02 já ajustado pela reclassificação do N4), **N3 só nas cíclicas** e **N3 nas cíclicas + N4 nas demais**. |

### 3.2 Distribuição do efeito nas 53 (variação do FCD contra o atual, (alt − atual) ÷ |atual|)

| Alternativa | Calculadas | Não aplicável | Sem dados | Mediana | Mínimo | Máximo | FCD negativo | Sinal do FCD mudou |
|---|---|---|---|---|---|---|---|---|
| Atual | 53 | 0 | 0 | — | — | — | 12 | — |
| N1 literal | 50 | 3 | 0 | +39,1% | −2.096% | +1.654% | 6 | AURE3, CPFE3, CSAN3, GGBR4, HAPV3, MRVE3, RAIL3, TAEE11 |
| N1 giro puro | 50 | 3 | 0 | +39,1% | −2.096% | +1.654% | 6 | (as mesmas) |
| N2, 3 anos | 51 | 2 | 0 | +10,8% | −79,2% | +1.824% | 7 | AURE3, CPFE3, HAPV3 |
| N2, 5 anos | 52 | 1 | 0 | +5,1% | −3.392% | +493% | 10 | AURE3, CPFE3, CSAN3, GGBR4, USIM5 |
| N3 | 47 | 5 | 1 | +3,5% | −197% | +14.582% | 8 | AXIA3, COGN3, CPFE3, GOAU4, HAPV3 |
| N4 simétrico (entradas e saídas) | 53 | 0 | 0 | 0,0% | −101,1% | +69,7% | 13 | MGLU3 |
| N4 só saídas, linha a linha | 53 | 0 | 0 | 0,0% | −101,1% | 0,0% | 13 | MGLU3 |
| **N4 só saídas, saldo líquido anual** | **53** | 0 | 0 | **0,0%** | −101,1% | 0,0% | 13 | **MGLU3** |
| N2 (3 anos) + N4 | 51 | 2 | 0 | +13,5% | −103,7% | +2.833% | 8 | AURE3, CPFE3, HAPV3, PRIO3 |
| N5: N3 só nas cíclicas | 51 | 1 (BRAV3) | 1 (BRAP4) | 0,0% (+179,1% nas 13 que mudam) | −43,1% | +14.582% | 11 | — |
| N5: N3 nas cíclicas + N4 nas demais | 51 | 1 (BRAV3) | 1 (BRAP4) | 0,0% (+142,0% nas 16 que mudam) | −101,1% | +14.582% | 12 | MGLU3 |

N1 literal e N1 giro puro têm as mesmas estatísticas de resumo porque a diferença entre elas só aparece em algumas ações (por exemplo, CURY3: R$ 57,08 contra R$ 45,84). As extremidades grandes de N1, N2 e N3 vêm de ações com fluxo-base próximo de zero, em que qualquer ajuste muda muito o valor.

### 3.3 FCD das ações de teste, das que estão no teto e dos controles (R$ por ação)

| Ação | Atual | N1 literal | N1 giro puro | N2 3 anos | N2 5 anos | N3 | N4 | N2 3 anos + N4 | N5 N3 só cíclicas | N5 N3 cíclicas + N4 |
|---|---|---|---|---|---|---|---|---|---|---|
| MGLU3 | 102,16 | 4,54 | 4,54 | 75,12 | 40,65 | 17,66 | **−1,14** | 5,58 | 102,16 | −1,14 |
| VALE3 | 5,40 | 7,12 | 7,12 | 5,86 | 4,93 | 62,01 | 5,40 | 6,06 | 62,01 | 62,01 |
| GGBR4 | 0,14 | −2,77 | −2,77 | 2,67 | −4,57 | 20,37 | 0,14 | 4,07 | 20,37 | 20,37 |
| AZZA3 | 34,84 | 47,77 | 47,77 | 32,31 | 30,57 | 17,73 | 34,84 | 32,31 | 34,84 | 34,84 |
| CURY3 | 25,74 | 57,08 | 45,84 | 34,88 | 40,87 | 27,37 | 25,74 | 34,88 | 25,74 | 25,74 |
| RENT3 | 35,72 | 76,40 | 76,40 | 17,83 | 7,96 | n/a | 35,24 | 16,69 | 35,72 | 35,24 |
| WEGE3 | 7,57 | 20,74 | 15,95 | 10,21 | 9,17 | 11,85 | 7,57 | 11,69 | 7,57 | 7,57 |
| PETR4 | 44,55 | 79,67 | 80,43 | 47,67 | 44,69 | 141,93 | 44,55 | 49,12 | 141,93 | 141,93 |
| KLBN11 | 28,03 | 38,13 | 26,91 | 34,80 | 32,73 | 21,46 | 28,03 | 34,80 | 21,46 | 21,46 |
| TIMS3 | 27,63 | 33,51 | 32,36 | 29,53 | 29,56 | 21,48 | 27,63 | 29,53 | 27,63 | 27,63 |

Informativo, sem uso como argumento: preço da MGLU3, R$ 7,61; da VALE3, R$ 72,10; da GGBR4, R$ 26,10.

### 3.4 N1: por que superestima quem cresce

**Raciocínio.** O capital de giro (estoques, recebíveis, fornecedores) cresce com a receita: uma empresa que cresce precisa financiar mais estoque e mais prazo de recebimento, e esse investimento aparece como saída em 6.01.02. Tirar 6.01.02 do fluxo ignora esse investimento, que faz parte do custo do crescimento projetado, e portanto eleva o valor justo de quem mais cresce.

**CONFIRMADO nos dados (N1 giro puro, 49 ações com receita e N1 calculáveis):**

| Receita (2020 a 2025) | Ações | Giro acumulado 2021 a 2025 ÷ fluxo acumulado (mediana) | Variação do FCD em N1 (mediana) |
|---|---|---|---|
| Cresce menos de 5% ao ano | 3 | +4% | +31,8% |
| De 5% a 12% ao ano | 17 | −13% | +4,5% |
| 12% ao ano ou mais | 29 | −43% | +47,2% |

Nas que mais crescem, o capital de giro consome em média quase metade do fluxo, e a regra N1 devolve esse valor aos acionistas. Por isso N1 não é coerente com um fluxo que projeta crescimento.

### 3.5 N3: crescimento e coerência com o teto pela receita

Se o fluxo-base é margem média × receita, o fluxo normalizado cresce como a receita (margem constante), então o **CAGR do fluxo normalizado é o da receita** (limitado à faixa de −20% a +30%). Isso é coerente com o teto pela receita já implementado, que assume a mesma premissa de margem constante: em N3 o teto vira uma identidade (o crescimento é o da receita por construção) e passa a valer também o nível de margem. Em N3 não há CAGR do fluxo para medir: o crescimento não depende mais dos anos 2020 e 2025 do fluxo.

**Limitações.**
- A média de 2019 a 2025 (7 anos) pode não cobrir um ciclo completo (HIPÓTESE). A VALE3 tem margem do fluxo de 24,0%, 26,4%, 38,2%, 14,4%, 18,7%, 6,9% e 8,9% em 2019 a 2025, com média de 19,6%: a média inclui o pico de 2021, e o fluxo-base sobe de R$ 19,1 bi para R$ 42,0 bi; na GGBR4, a média de 8,0% leva a base de R$ 2,1 bi para R$ 5,6 bi.
- A margem inclui o capex de cada ano: anos de investimento alto (VALE3 e GGBR4 em 2024 e 2025) entram na média como parte do ciclo, sem separar investimento de expansão e de manutenção.
- O efeito em ações que não são cíclicas do ponto de vista do negócio é grande: PETR4 de R$ 44,55 para R$ 141,93 (a média de 2019 a 2025 inclui o pico de 2022).

**Critério objetivo de cíclica.** Duas tentativas:
- **Variabilidade da margem do fluxo** (desvio-padrão ÷ média de 2019 a 2025): não separa as cíclicas. VALE3 e GGBR4 têm 0,51, abaixo da mediana de 0,55, e ficam nas posições 23 e 22 de 52; no topo ficam RDOR3 (42,7), AXIA3 (11,0), EMBJ3 (7,7), TEND3 (4,2) e MGLU3 (2,4), que não são o caso procurado.
- **Setor da B3** (classificação setorial que o projeto já usa): minerais metálicos, siderurgia, papel e celulose, exploração, refino e distribuição, carnes e derivados. Pega 15 ações (BEEF3, BRAP4, BRAV3, CSAN3, GGBR4, GOAU4, KLBN11, MBRF3, PETR3, PETR4, PRIO3, SUZB3, UGPA3, USIM5, VALE3), inclusive a VALE3 e a GGBR4. É objetivo e externo, mas grosseiro: inclui a UGPA3 (distribuição) e a CSAN3 (holding diversificada), e deixa de fora, por exemplo, energia elétrica.

Entre as 15, N3 muda 13 ações (mediana +179,1%, de −43,1% a +14.582%).

## 4. N4: risco sacado e convênio com fornecedores

### 4.1 Linhas encontradas (CONFIRMADO)

Busca nas linhas de 6.03 das 53 ações de 2019 a 2025, por termos em lista ("risco sacado", "convênio", "cessão de crédito por fornecedores", "forfait") com exclusão de "parcelamento". Valores em R$ milhões.

| Ação | Descrição da linha em 6.03 | Valores por ano |
|---|---|---|
| **MGLU3** | Aumento (redução) de Fornecedores - Convênio; Pagamento de fornecedores - convênio | 2022: −658; 2023: −1.444; **2024: −12.337**; **2025: −13.469** |
| RENT3 | Cessão de crédito por fornecedores - amortizações | 2022: −1.650; 2023: −142; 2024: −87; 2025: −38 |
| FLRY3 | Operação risco sacado; Novas operações risco sacado; Liquidação (principal) risco sacado | 2019 a 2024 entre −2 e +10; 2025: −121 e +116 |
| VIVA3 | Captação de financiamentos fornecedores convênio | 2024: +48; 2025: +147 |
| ASAI3 | Fornecedores - convênio | 2019 a 2021: 0 |
| ENGI11 (excluída) | Pagamento de parcelamento de fornecedores | 2019: −80 |

A ENGI11 saiu pela exclusão de "parcelamento": é parcelamento de dívida com fornecedores, não financiamento da cadeia de suprimento. Só a MGLU3 tem valor relevante; o efeito em RENT3 (2022) e FLRY3 e VIVA3 é pequeno.

### 4.2 Efeito

Descontando dos dois anos o valor das linhas, o FCD muda **só** nas ações em que elas aparecem. A variação depende de como as linhas entram:

| Versão do N4 | MGLU3 | RENT3 | FLRY3 | VIVA3 |
|---|---|---|---|---|
| Simétrico (entradas e saídas, linha a linha) | −101,1% | −1,4% | −0,4% | +69,7% |
| Só saídas, linha a linha | −101,1% | −1,4% | **−8,9%** | 0,0% |
| **Só saídas, saldo líquido anual** | −101,1% | −1,4% | −0,4% | 0,0% |

O FCD da **MGLU3** passa de R$ 102,16 para **−R$ 1,14**, e o da RENT3 de R$ 35,72 para R$ 35,24. O sinal do FCD só muda na MGLU3. A diferença da FLRY3 entre as versões vem de a regra "só saídas, linha a linha" contar a liquidação de risco sacado de 2025 (−R$ 121 mi) sem a linha de novas operações do mesmo programa (+R$ 116 mi): o saldo líquido do ano é de −R$ 5 mi, e é ele que representa a reclassificação.

**Coerência.** Se o banco paga o fornecedor e a empresa quita depois, a empresa deixou de pagar o fornecedor em caixa na operação e passou a pagar o banco no financiamento: o caixa operacional fica inflado e o de financiamento, deflacionado, sem mudança no caixa total. Reclassificar o valor de volta para o caixa operacional alinha o fluxo à natureza do pagamento. **HIPÓTESE:** que o "convênio" de cada empresa seja de fato financiamento de fornecedores (risco sacado); isso depende das notas explicativas.

**Limitações.** A busca depende da descrição escrita pela empresa; uma operação de risco sacado descrita de outro jeito, ou não destacada em 6.03, passa batida. A regra usa o sinal da linha, então captação positiva (VIVA3) aumenta o caixa operacional; isso segue a mesma lógica, mas não foi conferido caso a caso.

### 4.3 VIVA3: a entrada é a mesma operação de convênio?

Linhas de 6.03 (R$ milhões, DFC MI consolidada), com a descrição completa:

| Linha | 2024 | 2025 |
|---|---|---|
| 6.03.01 Recompra de ações | −7,0 | 0,0 |
| 6.03.03 Dividendos pagos | −87,7 | −319,2 |
| 6.03.04 Captação de empréstimos e financiamentos | 190,0 | 300,0 |
| 6.03.05 Amortização de empréstimos e financiamentos | −122,4 | −100,0 |
| 6.03.06 Liquidação contratos SWAP | −5,3 | 0,0 |
| 6.03.07 Amortização de arrendamentos direito de uso | −64,7 | −101,2 |
| **6.03.08 Captação de financiamentos fornecedores convênio** | **48,2** | **146,6** |
| 6.03.09 Juros sobre o capital próprio pagos | 0,0 | −194,4 |
| 6.03.10 Amortização de fornecedores convênio | (não existe) | 0,0 |
| 6.03.13 Encargos emissão debêntures | (não existe) | −1,8 |
| **6.03 total** | **−48,9** | **−269,9** |

Em 6.01.02 (R$ milhões): fornecedores (6.01.02.07) **+201,2 em 2024** e **−181,7 em 2025**; estoques −550,6 e −145,8; contas a receber −124,1 e −39,8; 6.01.02 total −557,1 e −216,7. O caixa operacional (6.01) é de R$ 150,7 mi em 2024 e R$ 468,9 mi em 2025. Em 2022 e 2023 não existe linha de convênio.

**Leitura.**
- **2025:** o sinal bate com o padrão de um programa de convênio apresentado em valores brutos: fornecedores com sinal negativo no operacional (−181,7) e captação de convênio positiva no financiamento (+146,6, cerca de 81% do valor). Seria o banco pagando o fornecedor, registrado como entrada de financiamento.
- **2024:** o padrão não aparece. Fornecedores tem sinal positivo no operacional (+201,2), e a entrada de convênio é de apenas R$ 48,2 mi; as duas linhas não se compensam.
- **Amortização:** a linha "Amortização de fornecedores convênio" existe só em 2025 e com valor 0,0, então não há saída para o convênio captado.

**Conclusão.** Não dá para afirmar que a entrada da VIVA3 seja a mesma operação de convênio em 2024, e em 2025 a coincidência de sinais é plausível, mas é um único ano. **HIPÓTESE** para 2025. Por isso a regra vale só para **saídas** (linhas negativas), no saldo líquido anual das linhas identificadas (que trata o caso da FLRY3), e a VIVA3 fica fora do efeito (suas linhas são entradas) e registrada como pergunta em aberto.

## 5. MGLU3 em detalhe

### 5.1 Fluxos de 2019 a 2025 (R$ milhões, DFC MI consolidada)

| Ano | 6.01 | 6.01.01 (gerado nas operações) | 6.01.02 (variações) | dos quais Fornecedores (6.01.02.08) | 6.01.03 (outros) | 6.03 | Convênio (6.03) |
|---|---|---|---|---|---|---|---|
| 2019 | −3.330 | 2.662 | −5.961 | n/d | −31 | 3.965 | — |
| 2020 | 2.604 | 1.580 | 1.115 | 2.564 | −91 | −577 | — |
| 2021 | −4.364 | 1.199 | −5.496 | 1.184 | −68 | 6.567 | — |
| 2022 | 3.064 | 1.727 | 1.327 | 103 | 11 | −2.167 | −658 |
| 2023 | 3.355 | 765 | 2.562 | 1.225 | 28 | −3.033 | −1.444 |
| 2024 | 15.835 | 3.136 | 12.701 | **13.296** | −2 | −15.311 | **−12.337** |
| 2025 | 15.719 | 2.597 | 13.057 | **14.686** | 65 | −14.970 | **−13.469** |

**CONFIRMADO:** o caixa gerado nas operações (6.01.01) é de R$ 2,6 a 3,1 bi em 2024 e 2025. Todo o salto do caixa operacional vem de 6.01.02, e dentro dela da linha de fornecedores.

### 5.2 Linhas de 6.03 em 2024 e 2025 (R$ milhões)

| Linha | 2024 | 2025 |
|---|---|---|
| 6.03.01 Captação de empréstimos e financiamentos | 300 | 1.997 |
| 6.03.02 Pagamento de empréstimos e financiamentos | −2.568 | −1.685 |
| 6.03.03 Pagamento de juros sobre empréstimos e financiamentos | −1.133 | −784 |
| 6.03.04 Pagamento de dividendos | 0 | −225 |
| **6.03.05 Fornecedores - convênio** | **−12.337** | **−13.469** |
| 6.03.09 Pagamento de arrendamento mercantil | −502 | −461 |
| 6.03.10 Pagamento de juros sobre arrendamento mercantil | −321 | −343 |
| 6.03.11 Aumento de capital social | 1.250 | 0 |
| **6.03 total** | **−15.311** | **−14.970** |

### 5.3 Correspondência com o aumento de fornecedores

| Ano | Fornecedores em 6.01.02.08 | Convênio em 6.03.05 | Convênio ÷ aumento de fornecedores |
|---|---|---|---|
| 2022 | 103 | −658 | n/a (a linha de fornecedores é pequena) |
| 2023 | 1.225 | −1.444 | 118% |
| 2024 | 13.296 | −12.337 | 93% |
| 2025 | 14.686 | −13.469 | 92% |

**CONFIRMADO nos números:** nos três anos o aumento de fornecedores em 6.01.02 e o valor da linha de convênio em 6.03 têm quase o mesmo tamanho e sinais opostos; somando 6.01 e 6.03, o resultado é de R$ 0,5 a 0,7 bi em 2024 e 2025. A linha 6.03.05 tem "convênio" na própria descrição.

**HIPÓTESE (depende das notas explicativas):** que o convênio seja financiamento de fornecedores (o banco paga o fornecedor e a MGLU3 paga o banco depois) e que, a partir de 2024, a empresa passou a apresentar esse pagamento no financiamento enquanto o aumento de fornecedores fica no operacional. Não foi verificado se houve mudança de apresentação em 2024 ou se o volume do convênio cresceu de fato.

### 5.4 Efeito do N4 na MGLU3

Com o N4, o fluxo de 2025 cai de R$ 14.828 mi para R$ 1.359 mi (R$ 14.828 mi menos os R$ 13.469 mi do convênio), e o de 2024, de R$ 15.106 mi para R$ 2.769 mi. O fluxo-base de 2025 fica abaixo do de 2020 (R$ 2.060 mi) e o FCD vai para −R$ 1,14.

## 6. Recomendação (pelo critério de coerência econômica)

**N4 (risco sacado) — adotar, só para saídas.** É uma correção de classificação com base em linhas explícitas das demonstrações, não um ajuste de nível. Não depende de janela nem de critério de ciclo, mexe só nas ações com saída líquida identificada (MGLU3, RENT3 e, de forma mínima, FLRY3) e deixa o resto do cálculo igual. As entradas (VIVA3) ficam fora, porque não dá para afirmar que sejam a mesma operação (seção 4.3). Limitações: depende da descrição da empresa; a natureza do convênio da MGLU3 é HIPÓTESE até a leitura das notas.

**N1 — descartar.** Ignora o capital de giro que acompanha o crescimento: eleva o FCD em 47% (mediana) nas 29 ações que crescem 12% ao ano ou mais, e tem extremos de −2.096% a +1.654%.

**N2 — não adotar.** Troca o capital de giro do ano por uma média absoluta, que não acompanha o tamanho atual da receita; as janelas (3 ou 5 anos) são arbitrárias, e o efeito vai nos dois sentidos (de −79% a +1.824%, ou −3.392% a +493%). Na MGLU3 a média de 3 anos ainda inclui 2024 e 2025, e o FCD só cai de R$ 102,16 para R$ 75,12.

**N3 — adiar.** É a resposta conceitual para empresas cíclicas (normalizar a margem e deixar o crescimento ser o da receita, coerente com o teto já implementado), mas a janela de 2019 a 2025 não cobre um ciclo completo, o critério de cíclica por setor é grosseiro e o efeito é extremo (PETR4 +219%, SUZB3 +15%, e a VALE3 de R$ 5,40 para R$ 62,01). Antes de adotar, precisa de uma janela mais longa e de uma decisão sobre o tratamento do capex de expansão.

**N5 (N2 + N4, N3 nas cíclicas).** N2 + N4 acrescenta a arbitrariedade da janela de N2 a algo que N4 resolve sozinho. N3 só nas cíclicas herda as limitações de N3.

**VALE3 e GGBR4** seguem como limitação documentada (a seção de empresas cíclicas de `docs/limitacoes-conhecidas.md`) até a investigação de uma janela mais longa.

## 7. Perguntas em aberto

1. **VIVA3:** a captação de convênio (+R$ 48,2 mi em 2024 e +R$ 146,6 mi em 2025) é a mesma operação de financiamento de fornecedores? Em 2025 o padrão de sinais é compatível, em 2024 não; a resposta depende das notas explicativas. Enquanto isso, as entradas ficam fora da regra.
2. A natureza do convênio da MGLU3 e a mudança de apresentação em 2024 seguem como HIPÓTESE apoiada pelos números (decisão da seção 8).
3. Como mostrar na tela o ajuste (decidido na seção 8: valor reclassificado e motivo no cartão do FCD), e se o Screener também ganha uma indicação.
4. Investigar uma janela mais longa para normalizar a margem das cíclicas. **CONFIRMADO:** os zips da DFP existem nos dados abertos desde 2010 (HEAD 200 para 2010 a 2019; 2008 e 2009 dão 404), o que daria até 16 anos de DFC; **HIPÓTESE:** que o layout das DFC de 2010 a 2018 seja o mesmo usado pelo projeto (não verificado). Qual janela e que tratamento de capex de expansão?
5. Definir o critério de cíclica: o setor da B3 (15 ações) é aceitável, ou há outro critério objetivo?
6. A soma de volta de juros funciona para 9 empresas com juros em 6.01.02 e 2 em 6.01.01; nenhuma mudança é necessária hoje, e o N1 foi descartado, então isso só importaria numa regra futura que tire 6.01.02.

## 8. Decisões (04/10/2026)

Nenhuma das decisões abaixo está implementada; elas definem o que será feito nas próximas etapas.

1. **N4 adotado.** As linhas de 6.03 identificadas pela descrição como convênio, risco sacado, forfait ou cessão de crédito por fornecedores são tratadas como operacionais e somadas ao caixa operacional, no ano de referência e no ano-base, na mesma demonstração. **Sinal:** só saídas (linhas negativas), conforme a conclusão da seção 4.3; as entradas ficam de fora, e o caso da VIVA3 fica como pergunta em aberto. Quando um mesmo programa tem entrada e saída no mesmo ano (FLRY3, 2025), vale o saldo líquido anual, aplicado só quando for saída. O saldo continua em fornecedores, fora da dívida líquida, o que mantém a regra coerente.
2. **Tela.** Quando o ajuste for aplicado, o cartão do FCD diz o valor reclassificado e o motivo.
3. **N1 e N2 descartadas. N3 adiada.** A normalização das cíclicas depende de uma janela mais longa de dados (verificar desde quando a CVM publica a DFP nos dados abertos; ver a pergunta 4: desde 2010 para os zips) e de um critério objetivo de cíclica. VALE3 e GGBR4 seguem como limitação documentada.
4. **A natureza do convênio da MGLU3 fica como HIPÓTESE apoiada pelos números** (saída no 6.03 quase igual ao aumento de fornecedores no 6.01.02: 93% em 2024 e 92% em 2025); não é preciso verificar nas notas explicativas antes de implementar.

## 9. Confirmado e hipóteses

**CONFIRMADO no código:** o fluxo atual e a soma de volta dos juros (`ingest/cvm.py` e `modelos/fcd.py`); a réplica do FCD atual (diferença 0).

**CONFIRMADO nos dados:** cobertura MI/MD, significado das subcontas, localização de juros e imposto pago (seção 2); todas as tabelas de alternativas (seção 3), calculadas com as funções do projeto; as linhas de risco sacado e o detalhe da MGLU3 (seções 4 e 5).

**HIPÓTESE:** natureza do convênio da MGLU3 como financiamento de fornecedores e a mudança de apresentação em 2024; que a janela de 2019 a 2025 não cubra um ciclo completo; a causa de negócio dos efeitos extremos de N3 em cada empresa; que as linhas de RENT3 e VIVA3 tenham a mesma natureza; que a entrada de convênio da VIVA3 em 2025 seja a mesma operação de financiamento de fornecedores (plausível pelo sinal, não afirmável); que o layout das DFC de 2010 a 2018 seja igual ao usado pelo projeto.

**Reprodução.** Scripts e dados em `%TEMP%\investigacao_fluxo_base` (`extrai_dfc.py`, `alternativas.py`, `dfc.json`, `resultados.json`). Nada foi gravado em `data/`.
