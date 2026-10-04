# Investigação do crescimento do FCD e do prêmio de risco (P10 e pergunta 5) — 04/10/2026

Investigação só de leitura: nenhum código, teste ou dado versionado foi alterado. Scripts, caches e downloads ficaram em `%TEMP%\investigacao_p10` (fora do repositório); este relatório é o único arquivo novo.

**Convenções.** **CONFIRMADO** = lido no código, medido nos dados ou lido na fonte citada. **HIPÓTESE** = plausível, não verificado. Os números de ações vêm de uma rodada real do Screener feita em 04/10/2026 (preços do fechamento de 02/10/2026, Selic 13,75%, IPCA 12m 4,2235%), com saída em `%TEMP%` e a captura das entradas reais de cada chamada do FCD. Os fluxos de caixa de 2019 a 2025 e a receita (conta 3.01 da DRE) foram lidos dos zips da DFP da CVM com as funções existentes do projeto (`ingest/cvm.py`), com cache em `%TEMP%`.

**Critério.** Cada alternativa é julgada pela coerência econômica da regra. A distância entre o FCD e o preço aparece só como informação (coluna "FCD ÷ preço, mediana"), nunca como argumento.

**Método de cálculo das alternativas.** As funções do projeto foram importadas sem alteração. As alternativas de teto (C) e de crescimento (A, B, D) substituem só o crescimento ou o fluxo-base; para a convergência (E) usei uma réplica dos passos de `calcular_valor_justo_fcd`. **CONFIRMADO:** com o crescimento atual, a réplica reproduz o valor por ação da função original nas 53 ações, com diferença máxima de 0 (zero) em reais por ação.

## 1. Resumo executivo

- O crescimento explícito é o CAGR entre o fluxo de 2025 e o de 2020, limitado a −20% e +30% ao ano; a perpetuidade cresce pelo IPCA de 12 meses (nenhuma ação foi limitada por WACC − 1 p.p.).
- Distribuição nas 53 ações com FCD: **12 no teto (+30%), 1 no piso (ENGI11), 9 no IPCA (base ausente ou não positiva) e 31 no meio** (mediana 4,4%).
- O teto quase sempre vem de ano-base pequeno ou atípico, e em várias de crescimento real ou de aquisições; na MGLU3 o fluxo de 2024 e 2025 é inflado por R$ 13 a 15 bi em "Fornecedores" no caixa operacional, compensados quase um a um no caixa de financiamento. Nenhuma das alternativas de crescimento corrige isso, porque o problema está no fluxo-base.
- O valor terminal pesa 56% do FCD (mediana; 37% a 71%) e 59% nas 12 do teto.
- Alternativas: o teto por receita (D) e a convergência linear (E) têm justificativa econômica e não pedem dados novos além da receita; as médias nas pontas (A) pedem 4 anos a mais e criam distorções próprias; os tetos menores (C) não têm justificativa econômica. D + E reduz a mediana do FCD em 10,8% (53,6% nas 12 do teto) e deixa só 3 ações no teto.
- Prêmio de risco: o 7,47% é o prêmio total de risco de ações do Brasil na tabela do Damodaran (mercado maduro 4,23% + risco-país 3,24%); a página é de 05/01/2026. O próprio Damodaran orienta tirar o spread de default da taxa livre de risco em moeda local, e somar o prêmio país a uma Selic que já embute o risco soberano é dupla contagem **conceitualmente CONFIRMADO**; que a Selic equivalha a essa taxa é **HIPÓTESE**.
- Recomendação: D + E para o crescimento; para o prêmio, usar Selic menos o spread de default (2,13%) com o prêmio total (alternativa P2), efeito de −1,5 p.p. na mediana do WACC e +16% na mediana do FCD. Detalhes e limitações nas seções 5 e 6.

## 2. Diagnóstico do crescimento atual (CONFIRMADO)

### 2.1 Como é calculado

| Elemento | Regra | Onde |
|---|---|---|
| Anos usados | Ano de referência (2025) e o de 5 anos antes (2020); dois pontos, último ano, não média | `ingest/cvm.py:718` (`ano_base`), `:743`; `config.py:701` |
| Crescimento explícito | CAGR = (fluxo 2025 ÷ fluxo 2020)^(1/5) − 1 | `modelos/fcd.py:266-274` |
| Faixa | Limitado entre −20% e +30% ao ano | `config.py:836-837`; `fcd.py:274` |
| Queda para o IPCA | Base ausente ou não positiva, ou fluxo atual não positivo: a taxa explícita vira o IPCA de 12 meses, com o motivo na tela | `fcd.py:271-272`, `:430-436` |
| Horizonte | 5 anos, desconto ao fim de cada ano | `config.py:700`; `fcd.py:446-449` |
| Perpetuidade | g = mín(IPCA 12m, WACC − 1 p.p.); valor terminal sobre o fluxo do ano 5 | `fcd.py:277-281`, `:442`, `:450-451`; `config.py:889` |

O crescimento explícito vai até o ano 5; no ano 6 a taxa passa de forma abrupta para o IPCA (4,22% em 04/10/2026).

### 2.2 Distribuição nas 53 ações com FCD (04/10/2026)

| Grupo | Ações |
|---|---|
| Teto (+30%) | 12: ALOS3, AXIA3, AZZA3, COGN3, CSAN3, CURY3, LREN3, MGLU3, POMO4, RENT3, TEND3, VBBR3 |
| Piso (−20%) | 1: ENGI11 (CAGR calculado de −30,9%) |
| IPCA (sem CAGR utilizável) | 9: AURE3 (sem demonstração de 2020 na CVM); BRAV3, EMBJ3, HYPE3, MRVE3, MULT3, RAIL3, RDOR3 e SMFT3 (fluxo de 2020 negativo) |
| Meio | 31, de −19,1% a +29,0%; quartis −5,0%, 4,4% e 14,9%; 10 negativos e 17 acima do IPCA |

### 2.3 As 13 ações no teto ou no piso

Fluxos em R$ milhões (fluxo do FCD = caixa operacional − capex + juros líquidos, na demonstração do ano de referência). CAGRs de 2020 a 2025.

| Ação | Fluxo 2019 a 2025 | CAGR fluxo | CAGR receita | Motivo provável |
|---|---|---|---|---|
| ALOS3 | 142, 244, 104, 621, 1.112, 1.168, 1.212 | 37,8% | 29,1% | Crescimento real: o fluxo cresce quase no ritmo da receita |
| AXIA3 | 51, 2.918, 7.218, −23.882, 4.267, 8.963, 10.935 | 30,2% | 7,3% | Série muito volátil (−R$ 23,9 bi em 2022) com receita quase estável: o fluxo cresce muito mais que a receita |
| AZZA3 | 144, 180, 85, −82, 196, 52, 849 | 36,4% | 49,3% | 2025 atípico (849 contra 52 em 2024); a receita sobe 49%, o que **HIPÓTESE** liga a aquisições |
| COGN3 | 109, 92, 283, 164, 668, 885, 1.137 | 65,3% | 5,9% | Ano-base pequeno (92) e receita quase parada: o fluxo cresce por margem, não por volume |
| CSAN3 | 1.988, 1.090, 1.155, 5.441, 4.008, 5.247, 4.567 | 33,2% | 24,5% | Parte real e parte consolidação de aquisições (**HIPÓTESE**); 2025 abaixo de 2023 e 2024 |
| CURY3 | 161, 174, 356, 349, 463, 511, 805 | 35,9% | 36,4% | Crescimento real (fluxo e receita no mesmo ritmo) |
| LREN3 | 811, 104, 391, 689, 1.965, 1.939, 2.080 | 82,2% | 16,0% | Ano-base pequeno (2020, ano da pandemia: 104 contra 811 em 2019) |
| MGLU3 | −3.851, 2.060, −5.529, 2.369, 2.714, 15.106, 14.828 | 48,4% | 5,8% | Capital de giro e fornecedores em 2024 e 2025 (ver 2.4) |
| POMO4 | 444, 41, 84, −52, 907, 900, 1.118 | 93,3% | 20,3% | Ano-base muito pequeno (41) |
| RENT3 | −2.595, 375, −3.269, −7.895, −7.123, 3.713, 5.308 | 69,9% | 32,3% | Ano-base pequeno (375) e fluxo negativo de 2021 a 2024 (**HIPÓTESE:** renovação de frota no capex): a virada de 2024 vira crescimento de 70% |
| TEND3 | 24, 39, −307, −426, −51, 476, 171 | 34,1% | 12,8% | Ano-base pequeno (39); 2025 caiu pela metade em relação a 2024 |
| VBBR3 | 2.304, 1.212, 1.692, 536, 5.505, 3.014, 5.214 | 33,9% | 18,3% | Série volátil; crescimento maior que o da receita |
| ENGI11 (piso) | 75, 2.674, −1.738, 793, 2.180, 1.540, 421 | −30,9% | 11,8% | Ano-base alto e atípico (2.674 contra 75 em 2019), e 2025 baixo |

Os motivos da coluna são leituras dos números; as causas de negócio marcadas como HIPÓTESE (aquisições, renovação de frota) não foram verificadas nas notas explicativas.

### 2.4 MGLU3

| Ano | Caixa operacional (6.01) | Fornecedores (6.01.02.08) | Financiamento (6.03) | Capex | Fluxo do FCD | Receita |
|---|---|---|---|---|---|---|
| 2019 | −3.330 | n/d | 3.965 | 522 | −3.851 | 19.886 |
| 2020 | 2.604 | 2.564 | −577 | 544 | 2.060 | 29.177 |
| 2021 | −4.364 | 1.184 | 6.567 | 1.164 | −5.529 | 35.278 |
| 2022 | 3.064 | 103 | −2.167 | 695 | 2.369 | 37.299 |
| 2023 | 3.355 | 1.225 | −3.033 | 641 | 2.714 | 36.768 |
| 2024 | 15.835 | **13.296** | **−15.311** | 730 | **15.106** | 38.038 |
| 2025 | 15.719 | **14.686** | **−14.970** | 892 | **14.828** | 38.703 |

**CONFIRMADO:** em 2025, o caixa operacional de R$ 15,7 bi inclui +R$ 14,7 bi na linha "Fornecedores" (a mesma linha tinha R$ 13,3 bi em 2024, contra R$ 1,2 bi em 2023), e o caixa de financiamento tem −R$ 15,0 bi (−R$ 15,3 bi em 2024). Somando 6.01 e 6.03, o resultado é de R$ 0,5 a 0,7 bi nos dois anos. A receita cresce 5,8% ao ano de 2020 a 2025, contra 48,4% do fluxo. **Não é geração recorrente de caixa**: é capital de giro ou reclassificação entre atividades operacionais e de financiamento. **HIPÓTESE** (não verificada nas notas explicativas): que seja financiamento de fornecedores (operações em que o banco paga o fornecedor e a empresa quita depois).

### 2.5 Peso do valor terminal

**CONFIRMADO (cálculo com as funções do projeto):** nas 53 ações, o valor terminal é 56% do valor presente do fluxo (EV) na mediana (mínimo 37%, quartis 50% e 64%, máximo 71%); nas 12 do teto, 59% na mediana (de 53% a 67%; MGLU3: 53%). A premissa de perpetuidade pesa mais da metade do valor em quase todas as ações.

## 3. Alternativas de crescimento

### 3.1 Definições

| Alt. | Regra (parâmetros e escolhas desta investigação) | Dados exigidos |
|---|---|---|
| A | Crescimento entre a média de 2019 a 2021 e a de 2023 a 2025. Os centros das janelas ficam a **4 anos** (2020 e 2024), então o CAGR usa o expoente 1/4. Base não positiva em qualquer média: cai para o IPCA. Faixa −20% a +30%. O fluxo-base projetado continua o de 2025. | Fluxos de 2019 e de 2021 a 2024, além de 2020 e 2025 |
| B | O fluxo projetado parte da média de 2023 a 2025; o crescimento continua o atual (2025 contra 2020). Média não positiva: FCD não se aplica. | Fluxos de 2023 e 2024 |
| C | Mesmo cálculo, com o teto em 20% (C1) ou 15% (C2). | Nenhum |
| D | Crescimento do fluxo limitado ao crescimento da receita líquida (3.01 da DRE, mesma demonstração, mesmos anos): taxa = mín(taxa do fluxo, taxa da receita), na faixa −20% a +30%. Receita não positiva em uma ponta: mantém a taxa do fluxo. | Receita (DRE 3.01) de 2020 e 2025 |
| E | O crescimento começa na taxa calculada no ano 1 e converge linearmente para a taxa da perpetuidade no ano 5: g(t) = g0 + (g∞ − g0) × (t − 1) ÷ 4. Sem salto no ano 6. | Nenhum |
| G | D + E (a combinação recomendada na seção 5) | Receita (DRE 3.01) de 2020 e 2025 |
| F1, F2, F3 | A + E; A + D + E; A + B + D + E | A união dos dados |

### 3.2 Distribuição do crescimento nas 53 ações

"Sem dados" = ações que não podem ser calculadas pela alternativa e ficam fora da contagem; "n/a" = fluxo-base médio não positivo.

| Alternativa | Calculadas | Teto | Piso | IPCA | Meio | Sem dados | n/a |
|---|---|---|---|---|---|---|---|
| 0 Atual | 53 | 12 | 1 | 9 | 31 | 0 | 0 |
| A Médias nas pontas | 52 | 15 | 4 | 8 | 25 | 1 (AURE3) | 0 |
| B Fluxo-base médio | 52 | 12 | 1 | 8 | 31 | 0 | 1 (MRVE3) |
| C1 Teto 20% | 53 | 16 | 1 | 9 | 27 | 0 | 0 |
| C2 Teto 15% | 53 | 19 | 1 | 9 | 24 | 0 | 0 |
| D Teto pela receita | 52 | 3 | 1 | 8 | 40 | 1 (AURE3) | 0 |
| E Convergência linear | 53 | 12 | 1 | 9 | 31 | 0 | 0 |
| G D + E | 52 | 3 | 1 | 8 | 40 | 1 (AURE3) | 0 |
| F1 A+E | 52 | 15 | 4 | 8 | 25 | 1 | 0 |
| F2 A+D+E | 52 | 3 | 4 | 8 | 37 | 1 | 0 |
| F3 A+B+D+E | 51 | 3 | 4 | 7 | 37 | 1 | 1 |

(Em C, "teto" é o teto da própria alternativa; em E, a convergência não muda a taxa do ano 1, só o caminho.)

### 3.3 Variação do FCD contra o atual (por ação, (alt − atual) ÷ |atual|)

| Alternativa | Mediana nas calculadas | Ações com variação > 1% | Mediana (as que mudaram) | Mediana nas 12 do teto | Mediana nas outras | Sinal do FCD mudou | FCD negativo (n) | FCD ÷ preço, mediana (informativo) |
|---|---|---|---|---|---|---|---|---|
| 0 Atual | — | — | — | — | — | — | 12 | 0,57 |
| A | +14,6% | 42 | +11,9% | −9,0% | +16,2% | CPFE3, DIRR3, EGIE3, GGBR4, HAPV3 | 10 | 0,63 |
| B | −7,8% | 51 | −8,5% | −20,5% | −3,4% | BRAV3, DIRR3, EGIE3, GGBR4, RENT3 | 14 | 0,53 |
| C1 | 0,0% | 16 | −31,7% | −33,6% | 0,0% | CSAN3 | 13 | 0,52 |
| C2 | 0,0% | 17 | −45,8% | −47,0% | 0,0% | CSAN3 | 13 | 0,51 |
| D | 0,0% | 18 | −38,9% | −39,0% | 0,0% | EGIE3 | 12 | 0,47 |
| E | −3,9% | 41 | −21,2% | −38,8% | 0,0% | CSAN3, VALE3 | 12 | 0,47 |
| **G (D + E)** | **−10,8%** | 41 | −27,1% | −53,6% | 0,0% | CSAN3, EGIE3, VALE3 | 12 | 0,43 |
| F1 | +14,6% | 45 | +5,7% | −45,6% | +6,6% | CPFE3, CSAN3, EGIE3, GGBR4, HAPV3, VALE3 | 9 | 0,43 |
| F2 | −8,4% | 46 | −20,3% | −60,1% | 0,0% | CPFE3, CSAN3, EGIE3, GGBR4, HAPV3, VALE3 | 9 | 0,37 |
| F3 | −21,4% | 50 | −25,2% | −69,5% | +2,2% | BRAV3, CPFE3, CSAN3, DIRR3, EGIE3, GGBR4, HAPV3, RENT3, VALE3 | 11 | 0,31 |

"Mediana nas calculadas" é a mediana da variação nas ações que a alternativa consegue calcular (52 ou 53); em C e D ela é zero porque a maioria das ações não muda, e por isso a tabela traz também a mediana entre as que mudaram, entre as 12 do teto e entre as outras.

### 3.4 FCD das 12 ações no teto atual (R$ por ação)

| Ação | Atual | A | B | C1 | C2 | D | E | G (D+E) | F1 | F2 | F3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ALOS3 | 38,45 | 38,45 | 37,16 | 29,33 | 25,67 | 37,51 | 28,16 | 27,80 | 28,16 | 28,16 | 27,28 |
| AXIA3 | 44,38 | 33,66 | 28,51 | 27,21 | 20,34 | 11,60 | 24,73 | 10,32 | 20,56 | 9,58 | 2,88 |
| AZZA3 | 50,56 | 46,45 | 13,79 | 32,21 | 24,87 | 50,56 | 29,62 | 29,62 | 28,06 | 28,06 | 4,10 |
| COGN3 | 5,83 | 5,83 | 4,04 | 3,43 | 2,48 | 1,07 | 3,10 | 0,97 | 3,10 | 0,76 | 0,05 |
| CSAN3 | 5,09 | 5,09 | 5,30 | −1,95 | −4,75 | 0,97 | −3,13 | −4,67 | −3,13 | −4,75 | −4,62 |
| CURY3 | 33,11 | 29,75 | 24,30 | 23,84 | 20,11 | 33,11 | 22,70 | 22,70 | 21,38 | 21,38 | 15,66 |
| LREN3 | 24,98 | 24,98 | 23,90 | 17,70 | 14,78 | 15,33 | 16,86 | 12,72 | 16,86 | 11,72 | 11,18 |
| MGLU3 | 222,99 | 89,81 | 161,35 | 159,23 | 133,57 | 95,39 | 151,84 | 93,04 | 89,81 | 89,81 | 63,60 |
| POMO4 | 15,73 | 15,73 | 13,52 | 10,69 | 8,69 | 10,84 | 9,88 | 7,97 | 9,88 | 8,07 | 6,84 |
| RENT3 | 63,27 | 5,42 | −21,00 | 35,30 | 24,16 | 63,27 | 30,69 | 30,69 | 5,42 | 5,42 | −27,89 |
| TEND3 | 16,08 | 5,13 | 19,13 | 10,83 | 8,72 | 7,90 | 10,15 | 6,62 | 5,13 | 5,13 | 6,40 |
| VBBR3 | 78,13 | 70,43 | 66,94 | 51,16 | 40,44 | 47,39 | 46,60 | 34,56 | 43,78 | 30,88 | 25,45 |

Em A, MGLU3, RENT3 e TEND3 caem para o IPCA porque a média de 2019 a 2021 é não positiva (a regra da base não positiva). No caso da MGLU3, o fluxo-base continua o de 2025 (R$ 14,8 bi), então o valor segue alto (R$ 89,81) mesmo com crescimento de 4,2%.

### 3.5 Ações de controle (R$ por ação; crescimento explícito entre parênteses)

| Ação | Atual | A | B | C1 e C2 | D | E | G (D+E) | F1 | F2 | F3 |
|---|---|---|---|---|---|---|---|---|---|---|
| WEGE3 | 6,43 (2,8%) | 16,14 (30,0%) | 8,09 (2,8%) | 6,43 | 6,43 (2,8%) | 6,56 | 6,56 (2,8%) | 10,92 (30,0%) | 9,06 (19,6%) | 11,45 (19,6%) |
| PETR4 | 26,36 (−5,0%) | 40,96 (1,1%) | 44,13 (−5,0%) | 26,36 | 26,36 | 35,79 | 35,79 (−5,0%) | 44,79 (1,1%) | 44,79 | 69,01 |
| KLBN11 | 35,14 (13,7%) | 58,99 (22,4%) | 37,04 (13,7%) | 35,14 | 30,25 (11,6%) | 25,27 | 23,01 (11,6%) | 35,27 (22,4%) | 22,18 (10,8%) | 23,68 (10,8%) |
| TIMS3 | 30,23 (13,2%) | 36,08 (17,6%) | 27,66 (13,2%) | 30,23 | 25,30 (9,0%) | 25,52 | 23,05 (9,0%) | 28,25 (17,6%) | 23,34 (9,6%) | 21,27 (9,6%) |

**CONFIRMADO:** a alternativa A leva a WEGE3 do crescimento de 2,8% ao teto de 30%, porque o fluxo de 2021 (R$ 92 mi) puxa para baixo a média inicial (R$ 1.615 mi), contra R$ 4.944 mi na média final. Três anos em cada ponta não eliminam a volatilidade de séries como a da WEGE3 (1.383, 3.371, 92, 1.809, 5.447, 5.508, 3.877). Na PETR4, a convergência (E) eleva o valor em 36% porque o crescimento de −5,0% converge para +4,2%: a regra é simétrica.

### 3.6 Dados exigidos e disponibilidade

| Alternativa | Dados | Disponibilidade nas 53 |
|---|---|---|
| A | DFP de 2019 e de 2021 a 2024, além de 2020 e 2025 | Zips da DFP existem para todos os anos. No cache local do projeto havia só 2019, 2020, 2024 e 2025: seriam 3 downloads de cerca de 13 MB (2021 a 2023). **AURE3** não tem demonstração de 2019 e 2020 e ficaria sem A, D e as combinações |
| B | Fluxos de 2023 e 2024 | Todas as 53; a **MRVE3** ficaria "não aplicável" (média 2023 a 2025 não positiva) |
| C, E | Nenhum | Todas |
| D | DRE 3.01 de 2020 e 2025, mesma demonstração do fluxo | Todas, exceto **AURE3** (sem 2020) |

## 4. Prêmio de risco (pergunta 5)

### 4.1 O que é o 7,47% (CONFIRMADO na fonte)

Fonte: página "Country Default Spreads and Risk Premiums" do Damodaran, `https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html`, **lida em 04/10/2026**; o cabeçalho da página diz "Last updated: January 5, 2026". Linha do Brasil: **Moody's Ba1; spread de default ajustado 2,13%; prêmio de risco-país (CRP) 3,24%; prêmio total de risco de ações (ERP) 7,47%**; alíquota de imposto 34%; ERP com base em CDS soberano 7,59%.

- O **prêmio de mercado maduro é 4,23%** (linha de países Aaa, como Austrália e Dinamarca na mesma tabela). **CONFIRMADO:** 4,23% + 3,24% = 7,47%. Então o 7,47% é o **prêmio total do Brasil** (mercado maduro + risco-país), e **não** é só o prêmio-país.
- O CRP de 3,24% é o spread de default (2,13%) multiplicado pela volatilidade relativa das ações contra a dos títulos (cerca de 1,52 = 3,24 ÷ 2,13). A página descreve esse passo ("multiplying the default spread by the relative equity market volatility"). O comentário em `config.py:845-851` ("spread de default ajustado 2,13% + country risk premium 3,24% sobre o prêmio de mercado maduro") dá a entender uma soma de três parcelas; a soma correta é 4,23% + 3,24% (o 2,13% está dentro do 3,24%). O mesmo comentário diz que a tabela é "atualizada mensalmente", mas a página mostra a última atualização em 05/01/2026.
- **Moeda do prêmio.** **CONFIRMADO:** o prêmio de mercado maduro nasce do retorno esperado implícito do S&P 500 menos a taxa livre de risco **em dólares** (a página define "Riskfree rate in US dollars = US treasury bond rate minus Default spread for the US"). **HIPÓTESE:** que o ERP do Brasil, por ser mercado maduro mais um spread, esteja expresso em termos de dólar e precise ou não de ajuste de inflação para uso em reais; a página não afirma isso, e o artigo sobre risco-país do Damodaran (não obtido: o endereço do PDF devolveu 404) é onde isso seria tratado.

### 4.2 Dupla contagem do risco-país (orientação do Damodaran)

Fonte: "What is the riskfree rate? A Search for the Basic Building Block" (Damodaran, dezembro de 2008), `https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/riskfreerate.pdf`, lido em 04/10/2026. **CONFIRMADO no texto:** quando a taxa de um título do governo em moeda local já inclui um spread de default, o Damodaran recomenda tirar esse spread para chegar à taxa livre de risco naquela moeda (exemplo da Índia: 10,70% − 2,60% = 8,10%), e observa que embutir o risco de default na taxa livre de risco pode contar o risco duas vezes quando o analista também usa um prêmio de risco de ações mais alto para o país (que, na abordagem dele, soma o spread de default ao prêmio de mercado maduro). Ele também diz que a taxa livre de risco deve ser medida na mesma moeda dos fluxos (fluxos nominais em reais pedem taxa nominal em reais). A página de 2026 mantém a mesma lógica para os EUA (taxa do Tesouro menos o spread de default).

Aplicação ao projeto:

- **CONFIRMADO no código:** o custo do capital próprio é a Selic meta mais Beta × 7,47% (`fcd.py:227-229`; `config.py:852`), ou seja, a Selic como taxa livre de risco mais o prêmio total, que inclui o risco-país.
- **Conclusão conceitual (CONFIRMADA na fonte):** se a Selic embute o spread de default do Brasil, somar o prêmio total (que contém o risco-país de 3,24%) conta o risco-país duas vezes.
- **HIPÓTESES:** (1) que a Selic meta embuta o spread de default da mesma forma que o juro de um título longo do governo (o texto do Damodaran fala de títulos do governo, e a Selic é a taxa de juros overnight; o prêmio de prazo não foi estudado); (2) que o spread de 2,13% da tabela (rating Ba1) seja a medida certa do componente de default na Selic de hoje.

### 4.3 Alternativas e efeito nas 53 ações

Betas das 53: mínimo 0,18, mediana 1,03, máximo 1,97. Só o custo do capital próprio muda; custo da dívida, pesos e fluxos ficam iguais. **Mediana da variação do FCD** = mediana de (alt − atual) ÷ |atual|.

| Alternativa | Ke | WACC mín, mediana, máx | Variação da mediana do WACC | Mediana da variação do FCD | FCD negativo | FCD ÷ preço, mediana (informativo) |
|---|---|---|---|---|---|---|
| P0 Atual | Selic + β × 7,47% | 11,6%, 17,9%, 26,3% | — | — | 12 | 0,57 |
| P1 Só prêmio de mercado maduro | Selic + β × 4,23% | 11,3%, 15,7%, 20,8% | −2,23 p.p. | +27,1% | 12 | 0,73 |
| P2 Selic menos o spread de default, prêmio total | (Selic − 2,13%) + β × 7,47% | 11,3%, 16,5%, 24,2% | −1,50 p.p. | +16,3% | 12 | 0,69 |

O Ke cai 2,13 p.p. para todas as ações em P2, e em P1 cai entre 0,59 e 6,38 p.p. conforme o Beta (mediana 3,32 p.p.).

Exemplos (R$ por ação; WACC):

| Ação | Beta | P0 | P1 | P2 |
|---|---|---|---|---|
| PETR4 | 0,40 | 26,36 (14,2%) | 30,36 (13,4%) | 33,37 (12,9%) |
| WEGE3 | 0,75 | 6,43 (19,4%) | 7,57 (16,9%) | 7,40 (17,2%) |
| KLBN11 | 0,59 | 35,14 (13,5%) | 40,95 (12,7%) | 41,63 (12,6%) |
| TIMS3 | 0,77 | 30,23 (19,5%) | 37,61 (17,0%) | 36,33 (17,4%) |
| MGLU3 | 1,97 | 222,99 (24,4%) | 314,30 (19,5%) | 247,82 (22,8%) |
| CSAN3 | 1,76 | 5,09 (17,0%) | 11,11 (14,7%) | 7,06 (16,2%) |
| GOAU4 | 0,96 | −27,52 (19,5%) | −26,45 (16,8%) | −26,83 (17,7%) |

## 5. Recomendação (pelo critério de coerência econômica)

### 5.1 Crescimento: D + E

- **E (convergência linear).** Hoje o crescimento cai de até 30% para 4,2% de um ano para o outro (ano 5 para o 6), sem nada na economia da empresa que explique o salto; o valor terminal, que pesa 56% do total, fica refém dele. Fazer o crescimento convergir gradualmente para o da perpetuidade é a forma padrão de tratar a fase de crescimento acima da economia. A regra é simétrica (sobe o valor de quem tem crescimento abaixo do IPCA, como a PETR4) e não pede dados novos.
- **D (teto pela receita).** Um fluxo que cresce mais que a receita por 5 anos exige margem ou intensidade de capital melhorando sem limite; limitar ao crescimento da receita assume margem constante, que é uma premissa neutra e a mesma para todas as ações. Troca um teto absoluto sem justificativa econômica (30%) por um limite ligado à própria empresa, com dado que já está nos zips da CVM.
- **Não recomendo A.** Médias de 3 anos em cada ponta não removem a volatilidade (WEGE3 vai de 2,8% ao teto de 30%), criam quedas para o IPCA por média não positiva (MGLU3, RENT3, TEND3) e pedem 4 anos de dados a mais.
- **Não recomendo C (tetos de 15% e 20%).** Qualquer valor de teto é arbitrário; não há argumento econômico para 15%, 20% ou 30%.
- **B (fluxo-base médio) fica como pergunta aberta:** normalizar o fluxo-base é coerente para séries voláteis, mas muda a definição do fluxo de referência e, no caso da MGLU3, não ajuda (a média inclui 2024 e 2025).

**Limitações de D + E.**
- A receita pode estar inflada por aquisições (AZZA3 cresce 49%): nesse caso o teto fica frouxo.
- D não age quando o fluxo cresce menos que a receita.
- E reduz o valor de toda ação com crescimento calculado acima do IPCA, por construção, e aumenta o de quem tem crescimento abaixo.
- AURE3 não tem dados de 2020 e ficaria como hoje.
- D + E não resolvem o fluxo-base inflado: na MGLU3, com D + E o crescimento cai para 5,8% (o da receita) e o FCD vai de R$ 222,99 para R$ 93,04, ainda alto por causa da base de R$ 14,8 bi. O problema da MGLU3 é de definição do fluxo, não de crescimento.
- D + E muda o sinal do FCD de 3 ações (CSAN3, EGIE3 e VALE3); a combinação com A (F2) muda 6 e reduz as 12 do teto em 60% na mediana, o que pesa contra A.
- D + E corta o FCD das 12 do teto em 53,6% na mediana e deixa só 3 no teto (de 12); a mediana em todas as calculadas cai 10,8%. Esse efeito é consequência das regras (crescimento limitado à receita e sem salto no ano 6), não um alvo.

### 5.2 Prêmio de risco: P2

A alternativa P2 é a que respeita a orientação do próprio Damodaran: taxa livre de risco em reais sem o spread de default (Selic − 2,13%) mais o prêmio total de risco do Brasil (4,23% + 3,24%), com Beta multiplicando o prêmio. P1 descartaria o risco-país do prêmio de ações em vez de tirá-lo da taxa livre de risco; como o spread na Selic entra com peso 1 e o prêmio-país entra multiplicado pelo Beta, P1 só seria equivalente para Beta 1 e distorce o custo do capital próprio das ações de Beta baixo ou alto.

**Limitações de P2.**
- Pressupõe que o spread de default de 2,13% (rating Ba1, tabela de 05/01/2026) é o que está dentro da Selic: **HIPÓTESE**.
- A Selic é uma taxa overnight; o texto do Damodaran fala de títulos longos do governo. Falta decidir se a taxa livre de risco deveria ser a de um título de 10 anos em reais menos o spread (**HIPÓTESE**, não calculado aqui).
- O prêmio e o spread da tabela mudam e precisam de atualização manual (a página mostra 05/01/2026 como última atualização).
- O custo da dívida também parte da Selic (Selic + 2 p.p.); não avaliei se deveria acompanhar a mudança.
- A moeda do prêmio (dólar ou real) é **HIPÓTESE** (4.1).

## 6. Perguntas em aberto

1. Adotar D + E para o crescimento? Mantém a faixa de −20% a +30% como limite de segurança junto com D?
2. O fluxo-base médio (B) vale como etapa à parte, sabendo que não corrige a MGLU3?
3. Investigar a normalização do fluxo-base para variações de capital de giro (por exemplo, excluir "Fornecedores" ou usar o fluxo antes de variações de giro), tratando a MGLU3 (2024 e 2025) como caso de teste? Não foi testada nesta investigação.
4. Verificar nas notas explicativas da MGLU3 a natureza da linha "Fornecedores" e do −R$ 15 bi no financiamento (HIPÓTESE da seção 2.4).
5. Adotar P2? Antes, investigar a taxa livre de risco: Selic meta contra a taxa de um título de 10 anos em reais (qual série e onde obter), e a moeda do prêmio.
6. Como atualizar o prêmio e o spread (hoje constantes fixas)? Manual com data registrada, ou por rotina?
7. O custo da dívida (Selic + 2 p.p.) deve acompanhar a mudança da taxa livre de risco?
8. Depois das mudanças, regenerar o `screener.csv` e atualizar `docs/limitacoes-conhecidas.md` (crescimento, perpetuidade e prêmio).

## 7. Decisões (04/10/2026)

Nenhuma das decisões abaixo está implementada; elas definem o que será feito nas próximas etapas.

1. **Crescimento: D + E.** A convergência linear substitui o salto para a perpetuidade, e o teto passa a ser o crescimento da receita no mesmo período, mantendo a faixa de −20% a +30% como limite externo. Sem receita disponível (por exemplo, a AURE3), vale a regra atual, com o motivo na tela.
2. **A e C: descartadas. B: não adotada.** A normalização do capital de giro (separando 6.01.01 de 6.01.02 na DFC pelo método indireto) fica como nova investigação, com a MGLU3 como caso de teste.
3. **Prêmio de risco: P2.** Custo do capital próprio = (Selic − spread de default do Brasil) + Beta × prêmio total. O custo da dívida continua Selic + 2 p.p., por representar o custo real de captação em reais. O comentário de `config.py:845-851` será corrigido: duas parcelas (mercado maduro e risco-país), atualização anual em janeiro e conferência manual a cada atualização.
4. **As demais perguntas em aberto ficam registradas como estão.**

Situação das perguntas da seção 6 depois das decisões:

| Pergunta | Situação |
|---|---|
| 1 — D + E e a faixa de −20% a +30% | Decidida (item 1) |
| 2 — Fluxo-base médio (B) | Decidida: não adotada (item 2) |
| 3 — Normalização do fluxo-base para o capital de giro | Nova investigação (item 2) |
| 4 — Natureza da linha "Fornecedores" da MGLU3 | Em aberto (faz parte da investigação do item 2) |
| 5 — Adotar P2; taxa livre de risco (Selic contra título de 10 anos) e moeda do prêmio | P2 decidida (item 3); a investigação da taxa livre de risco e da moeda do prêmio segue em aberto |
| 6 — Como atualizar o prêmio e o spread | Decidida: atualização anual em janeiro, com conferência manual (item 3) |
| 7 — Custo da dívida acompanhar a mudança | Decidida: não, continua Selic + 2 p.p. (item 3) |
| 8 — Regenerar o `screener.csv` e atualizar `docs/limitacoes-conhecidas.md` | Em aberto, para depois da implementação |

## 8. Confirmado e hipóteses

**CONFIRMADO no código:** regras de crescimento, faixa, queda para o IPCA e perpetuidade (2.1); Ke = Selic + Beta × 7,47% (`fcd.py:227-229`, `config.py:852`); réplica do FCD igual à função original nas 53 (diferença 0).

**CONFIRMADO nos dados:** distribuição (2.2), fluxos, receitas e linhas do caixa operacional (2.3, 2.4); peso do valor terminal (2.5); resultados das alternativas (3.2 a 3.5) e do prêmio (4.3), calculados com as funções existentes; datas e valores da tabela do Damodaran (4.1).

**CONFIRMADO nas fontes:** o 7,47% é o prêmio total do Brasil (4,23% + 3,24%) na página lida em 04/10/2026 (última atualização 05/01/2026); o Damodaran (artigo de 2008) recomenda retirar o spread de default da taxa em moeda local e aponta o risco de dupla contagem com o prêmio-país.

**HIPÓTESE:** causas de negócio nas séries do teto (aquisições, renovação de frota, 2.3); natureza do fluxo de fornecedores da MGLU3 (2.4); que a Selic embuta o spread de default como um título longo (4.2); a moeda do prêmio e a necessidade de ajuste de inflação (4.1); a escolha da Selic overnight contra um título longo como taxa livre de risco.

**Reprodução.** Scripts e dados em `%TEMP%\investigacao_p10` (`captura_kwargs.py`, `coleta_historico.py`, `analise.py`, `parte1.py`, `parte3.py`, `historico.json`, `kwargs_fcd.json`, `alternativas.json`, páginas e PDF do Damodaran). Nada foi gravado em `data/`.
