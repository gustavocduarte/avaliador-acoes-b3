# Investigação da normalização do fluxo-base das empresas cíclicas — 04/10/2026

Investigação só de leitura, aberta pela decisão de adiar o N3 em `docs/investigacao-fluxo-base-2026-10-04.md`. Nenhum código, teste ou dado versionado foi alterado. Scripts, downloads e resultados ficaram em `%TEMP%\investigacao_ciclicas` (`extrai16.py`, `base.py`, `cobertura.py`, `run_metodos.py`, `dfc16.json`, `painel.pkl`, `resultados.pkl`); este relatório é o único arquivo novo.

**Convenções.** **CONFIRMADO** = lido no código, medido nos dados da CVM ou calculado com as funções do projeto. **HIPÓTESE** = plausível, não verificado (em geral, causa de negócio que dependeria das notas explicativas). Todos os valores de FCD são em R$ por ação, calculados com as funções existentes (`calcular_valor_justo_fcd`, importada sem alteração) e as entradas reais da rodada de 04/10/2026, variando só o fluxo-base e, onde indicado, o crescimento. A distância ao preço aparece só como informação.

**Critério.** Coerência econômica da regra; nunca aproximar o FCD do preço.

## 1. Resumo executivo

- **Dados:** os 16 zips da DFP (2010 a 2025) somam **175,1 MB** (os de 2010 a 2018, 84,8 MB). O layout é o mesmo em todos os anos (contas 6.01.01, 6.01.02, 6.01.03, 6.02 e 6.03 em 100% das 751 DFC indiretas, com a identidade 6.01 = soma das três). **33 das 53 ações têm os 16 anos completos**; 52 têm 5 anos úteis ou mais em qualquer janela (a BRAP4 não tem receita).
- **IFRS 16:** o pagamento de arrendamento no 6.03 sobe de 0,00% da receita (mediana, 2018) para 0,44% (2019). É relevante em 19 ações, entre elas a PETR4 (6,8% da receita, 20% do caixa operacional); VALE3 e GGBR4 não estão entre elas.
- **Critério de cíclica:** setor da B3 (mineração, siderurgia, petróleo e gás, papel e celulose, químicos) **e** receita nominal em queda em pelo menos 1/3 dos anos: **CSAN3, GGBR4, GOAU4, PETR3, PETR4, USIM5 e VALE3** (VALE3, GGBR4 e PETR4 entram). A variabilidade da margem **não** separa as cíclicas (VALE3 é a 41ª de 47).
- **Métodos:** a base normalizada muda muito o FCD: VALE3 de R$ 5,40 para R$ 45 a R$ 101, GGBR4 de R$ 0,14 para R$ 14 a R$ 24, PETR4 de R$ 44,55 para R$ 64 a R$ 128, conforme janela e método. M1 e M2 são o mesmo número quando os anos coincidem; M3 dá valores maiores.
- **Aplicar às 53:** a variação mediana vai de −30% a +36% e o intervalo de P10 a P90 chega a −91% a +343% no caso base; de 3 a 7 ações ficam sem base positiva. **Não deve valer para todas.**
- **Viabilidade:** ler 16 anos por empresa em lote leva ~31 s para as 53 ações (contra ~85 min se cada empresa-ano reabrir o zip, como hoje); cache de +108 MB (175 MB no total, bem abaixo do limite de 10 GB); a página deve ler uma série pré-calculada (63 KB), não os zips.
- **Recomendação:** M1 com crescimento G1, janela 2015 a 2025 e ajuste do IFRS 16, só nas cíclicas do critério acima. Limitações: a janela cobre cerca de 1,5 ciclo e o superciclo de 2020 a 2022 pesa nela; a quebra de 2019 e o perímetro (CSAN3) são tratados por hipóteses.

## 2. Dados de 2010 a 2025

### 2.1 Downloads e layout (CONFIRMADO)

Os zips de 2010 a 2018 (9 arquivos, 84,8 MB) foram baixados com a função do projeto (`_baixar_zip_ano`); os de 2019 a 2025 vieram do cache anterior. Total de 2010 a 2025: **175,1 MB**. Velocidade medida: 10,2 MB em 0,9 s (zip de 2018).

**Layout igual ao de hoje.** Nos zips de 2010, 2012, 2018, 2019 e 2025 os membros (`DFC_MD_con`, `DFC_MD_ind`, `DFC_MI_con`, `DFC_MI_ind`, `DRE_con`, `DRE_ind`) e as 15 colunas são idênticos. Nas 751 DFC indiretas lidas (382 até 2018 e 369 de 2019 em diante), as contas 6.01, 6.01.01, 6.01.02, 6.01.03, 6.02 e 6.03 existem em 100%, com as mesmas descrições nas contas de topo ("Caixa Líquido Atividades Operacionais", "Caixa Gerado nas Operações", "Variações nos Ativos e Passivos", "Outros", "Caixa Líquido Atividades de Investimento" e "de Financiamento"), e a identidade 6.01 = 6.01.01 + 6.01.02 + 6.01.03 vale em todas. O que muda é a descrição das subcontas, que cada empresa escreve de um jeito: a Petrobras de 2010 a 2012 descreve o investimento por segmento ("Investimentos em Exploração e Produção…"), e por isso a regra atual não identifica o capex desses três anos.

### 2.2 Cobertura por ano

Entre as 53 ações com FCD (consolidada, como no ano de referência). DFC existente, método indireto, receita (3.01) positiva, capex identificado pela regra atual e depreciação identificada:

| Ano | Com DFP | Indireto | Receita | Capex | Depreciação |
|---|---|---|---|---|---|
| 2010 | 40 | 38 | 40 | 36 | 37 |
| 2011 | 41 | 40 | 41 | 38 | 40 |
| 2012 | 42 | 41 | 42 | 38 | 39 |
| 2013 | 42 | 42 | 42 | 41 | 41 |
| 2014 | 42 | 42 | 42 | 40 | 41 |
| 2015 | 42 | 42 | 42 | 41 | 41 |
| 2016 | 44 | 44 | 44 | 43 | 43 |
| 2017 | 45 | 45 | 45 | 44 | 44 |
| 2018 | 48 | 48 | 48 | 47 | 47 |
| 2019 | 52 | 52 | 52 | 52 | 51 |
| 2020 | 52 | 52 | 52 | 52 | 51 |
| 2021 a 2025 | 53 | 53 | 53 | 53 | 52 |

A DFC do ano de referência foi lida com a mesma regra de hoje (a mesma demonstração do ano de referência, com a escolha de `cvm._tipo_da_demonstracao`). Nos anos de 2010 a 2025 aparecem 717 demonstrações indiretas consolidadas, 34 individuais e 4 diretas.

### 2.3 Lacunas por ação (CONFIRMADO)

**33 ações têm os 16 anos completos** (indireto, receita e capex). As outras 20 têm lacunas:

| Ação | Anos sem dado | Motivo |
|---|---|---|
| ABEV3 | 2010, 2011; 2012 | sem DFP nesse CNPJ; sem receita |
| ASAI3 | 2010 a 2018 | sem DFP nesse CNPJ |
| AURE3 | 2010 a 2020 | sem DFP nesse CNPJ |
| AZZA3 | 2010 | método direto |
| BEEF3 | 2010 | capex não identificado |
| BRAP4 | 2010 a 2025 | sem receita (holding) |
| BRAV3 | 2010 a 2018 | sem DFP nesse CNPJ |
| CEAB3 | 2010 a 2017 | sem DFP nesse CNPJ |
| CSAN3 | 2010 | sem DFP nesse CNPJ |
| CURY3 | 2010 a 2018 | sem DFP nesse CNPJ |
| ENGI11 | 2010 a 2012 | método direto |
| HAPV3 | 2010 a 2016 | sem DFP nesse CNPJ |
| PETR3 e PETR4 | 2010 a 2012 | capex não identificado |
| RDOR3 | 2010 a 2017 | sem DFP nesse CNPJ |
| SMFT3 | 2010 a 2015 | sem DFP nesse CNPJ |
| TAEE11 | 2010 a 2014 | capex não identificado |
| TIMS3 | 2010 a 2017 | sem DFP nesse CNPJ |
| VBBR3 | 2010 a 2015 | sem DFP nesse CNPJ |
| VIVA3 | 2010 a 2018 | sem DFP nesse CNPJ |

Distribuição dos anos completos: 33 ações com 16; 3 com 15; 4 com 13; 1 com 11; 2 com 10; 1 com 9; 3 com 8; 4 com 7; 1 com 5; 1 com 0 (BRAP4). **52 das 53** têm 5 anos úteis ou mais em cada uma das três janelas (2010 a 2025, 2015 a 2025, 2019 a 2025). **HIPÓTESE:** a maior parte das lacunas "sem DFP nesse CNPJ" vem de abertura de capital recente ou de reorganização societária que trocou o CNPJ da companhia aberta (não verificado nas notas).

### 2.4 Depreciação e amortização

A linha foi identificada pela descrição entre as folhas de 6.01.01.xx (depreciação, amortização, depleção ou exaustão). **Cobertura (CONFIRMADO):** 37 de 40 ações em 2010, 51 ou 52 de 52 ou 53 de 2019 em diante (tabela do item 2.2); a única ação sem a linha em nenhum ano é a **BRAP4** (holding). Na PETR4 a linha é "Depreciação, Depleção e Amortização". **Limitação:** a depreciação de 2025 inclui a amortização do direito de uso dos arrendamentos e, em concessões, a amortização do intangível, o que a deixa maior do que a reposição de ativos próprios.

### 2.5 Quebra do IFRS 16 em 2019

**O que muda (CONFIRMADO nos dados: os pagamentos de arrendamento só aparecem no 6.03 a partir de 2019):** a partir de 2019 o principal dos arrendamentos sai do caixa operacional e vai para o 6.03; antes, os aluguéis operacionais estavam dentro do 6.01. A série do caixa operacional fica **maior em 2019** do que a anterior, a menos do negócio.

**Tamanho do efeito.** Pagamentos de arrendamento identificados no 6.03 pela descrição, como proporção da receita, nas 48 ações com 2018 e 2019: mediana **0,00% em 2018, 0,44% em 2019 e 0,57% em 2020**. A variação da margem do caixa operacional entre 2018 e 2019 tem mediana −0,05 p.p. (P25 −5,7 e P75 +6,4 p.p.): para a maioria das ações, o efeito do IFRS 16 é pequeno diante da variação anual da própria margem. **Relevantes** para uma média de margens (arrendamento de 3% ou mais da receita, ou de 10% ou mais do caixa operacional, em 2019): **19 ações**.

| Ação | Arrendamento 2018 (% receita) | Arrendamento 2019 (% receita) | Arrendamento 2019 (% do CFO) | Margem do CFO 2018 → 2019 |
|---|---|---|---|---|
| SMFT3 | 0,0 | 11,2 | 44,2 | 11,3% → 25,3% |
| PRIO3 | 0,0 | 9,6 | 35,6 | 31,8% → 27,0% |
| RAIL3 | 8,1 | 9,4 | 18,8 | 41,1% → 49,7% |
| TIMS3 | 1,2 | 9,1 | 21,9 | 70,5% → 41,6% |
| VIVT3 | 0,0 | 8,4 | 20,9 | 27,5% → 40,0% |
| **PETR4** (e PETR3) | 0,0 | 6,8 | 20,3 | 27,4% → 33,7% |
| CEAB3 | 0,0 | 6,7 | 41,6 | 6,9% → 16,1% |
| FLRY3 | 0,0 | 5,6 | 22,2 | 26,3% → 25,2% |
| RADL3 | 0,0 | 4,4 | 103,9 | 4,6% → 4,3% |
| LREN3 | 0,5 | 3,7 | 22,4 | 9,6% → 16,3% |
| AZZA3 | 0,0 | 2,8 | 22,8 | 7,7% → 12,2% |
| TOTS3 | 1,1 | 2,7 | 17,8 | 18,4% → 15,1% |
| AXIA3 | 0,0 | 2,0 | 633,9 | 9,7% → −0,3% |
| COGN3 | 0,0 | 2,0 | 32,9 | 18,6% → 6,0% |
| HAPV3 | 0,0 | 1,9 | 16,5 | 11,3% → 11,7% |
| MGLU3 | 0,0 | 1,8 | 11,0 | 7,9% → −16,7% |
| GOAU4 | 0,0 | 0,4 | 10,1 | 4,4% → 4,0% |
| UGPA3 | 0,0 | 0,4 | 11,0 | 3,2% → 3,3% |

(HIPÓTESE sobre a TIMS3: a margem de 2018 vem de uma entidade diferente da de 2019, ver 2.6.) Os 29 não relevantes incluem **VALE3, GGBR4**, KLBN11, WEGE3 e SUZB3. **Limitações (HIPÓTESE):** a identificação é pela descrição no 6.03 e pode perder linhas que misturam arrendamento com empréstimos; o juros de arrendamento fica fora desta medida.

### 2.6 Mudanças de perímetro

Saltos da receita líquida incompatíveis com o histórico (alta de 60% ou mais, ou queda de 40% ou mais, de um ano para o outro) em **46 casos** (CONFIRMADO nos dados; as causas de negócio são HIPÓTESE, sem consulta às notas):

| Ação | Anos (razão da receita contra o ano anterior) |
|---|---|
| ALOS3 | 2019 (2,0), 2023 (2,4) |
| AURE3 | 2022 (2,1), 2025 (1,6) |
| AXIA3 | 2016 (1,9) |
| AZZA3 | 2021 (1,8), 2024 (1,7) |
| BEEF3 | 2025 (1,6) |
| BRAV3 | 2020 (6,3), 2021 (3,6), 2022 (2,4), 2023 (3,3) |
| COGN3 | 2012 (1,9), 2014 (1,9) |
| **CSAN3** | **2013 (0,29), 2021 (1,8)** |
| DIRR3 | 2017 (0,55) |
| EMBJ3 | 2019 (0,56), 2020 (1,9) |
| ENGI11 | 2014 (2,9) |
| **GGBR4 e GOAU4** | 2021 (1,8) |
| HAPV3 | 2022 (2,4) |
| MBRF3 | 2019 (1,6) |
| **PETR3 e PETR4** | 2021 (1,7) |
| PRIO3 | 2014 (110,8), 2015 (0,52), 2019 (1,9), 2021 (2,3), 2023 (1,9) |
| RADL3 | 2012 (2,0) |
| RDOR3 | 2023 (2,0) |
| RENT3 | 2022 (1,6), 2023 (1,6) |
| SMFT3 | 2019 (1,7), 2022 (1,7) |
| SUZB3 | 2019 (1,9) |
| TAEE11 | 2020 (2,0) |
| TEND3 | 2011 (0,35), 2012 (2,5), 2023 (0,27), 2024 (5,0) |
| **TIMS3** | **2019 (5,2)** |
| **USIM5** | 2021 (2,1) |
| VIVT3 | 2011 (1,9) |

Nas cíclicas, os saltos de GGBR4, GOAU4, PETR3, PETR4 e USIM5 em 2021 coincidem com o ciclo de preços (**HIPÓTESE**, não com aquisição). Os que quebram a comparabilidade da série são os da **CSAN3** (2013 e 2021, **HIPÓTESE**: reorganização societária), da **TIMS3** (2019, **HIPÓTESE**: a série até 2018 é de outra entidade) e os da PRIO3 e da BRAV3 (receita mínima no início). **Filtro de qualidade usado nos cálculos:** anos em que a margem do caixa operacional ou do fluxo passa de ±100% da receita não entram na média (12 empresas-ano: B3SA3 2016 e 2017, BRAV3 2020, PRIO3 2010 a 2013, TAEE11 2014 a 2017 e TEND3 2011); sem esse filtro a média da PRIO3 seria de −1.786%.

## 3. Critério objetivo de "cíclica"

Testados em 47 ações com 8 anos válidos ou mais (a BRAP4, a ASAI3, a AURE3, a BRAV3, a CURY3 e a VIVA3 não têm anos suficientes na janela de 2010 a 2025):

| Critério | Seleção | Lista | VALE3, GGBR4 e PETR4 |
|---|---|---|---|
| (a) Setor da B3: minerais metálicos, siderurgia, exploração, refino e distribuição de petróleo e gás, papel e celulose, químicos | 13 ações | BRAP4, BRAV3, CSAN3, GGBR4, GOAU4, KLBN11, PETR3, PETR4, PRIO3, SUZB3, UGPA3, USIM5, VALE3 | entram os três |
| (b) Variabilidade da margem operacional de caixa (desvio-padrão ÷ média) no quartil superior (≥ 0,62) | 12 | COGN3, DIRR3, EMBJ3, ENGI11, MBRF3, MGLU3, MRVE3, PRIO3, RENT3, TEND3, USIM5, YDUQ3 | **nenhuma entra** (posições 41, 27 e 31 de 47; valores 0,23, 0,36 e 0,33) |
| (b') O mesmo com o desvio-padrão em p.p. (≥ 12,3) | 12 | ALOS3, B3SA3, COGN3, DIRR3, EGIE3, EMBJ3, MULT3, PRIO3, RAIL3, RENT3, TAEE11, TEND3 | nenhuma (posições 26, 39 e 18) |
| (b'') O mesmo com o desvio absoluto mediano ÷ mediana (≥ 0,35) | 12 | AXIA3, COGN3, DIRR3, ENGI11, GOAU4, MGLU3, MRVE3, POMO4, PRIO3, RENT3, TEND3, USIM5 | nenhuma (GOAU4 e USIM5 aparecem) |
| (c1) Receita nominal em queda em pelo menos 1/3 dos anos (2010 a 2025) | 10 | B3SA3, CSAN3, GGBR4, GOAU4, PETR3, PETR4, POMO4, USIM5, VALE3, VBBR3 | entram os três |
| **(c2) Setor da B3 (a) e queda da receita em 1/3 dos anos (c1)** | **7** | **CSAN3, GGBR4, GOAU4, PETR3, PETR4, USIM5, VALE3** | entram os três |

- **Por que a variabilidade da margem falha (CONFIRMADO):** com 16 anos, a margem das cíclicas oscila em termos absolutos tanto quanto a de empresas que não são cíclicas (mediana do desvio-padrão de 8,0 p.p.; VALE3 7,6; PETR4 10,7; GGBR4 4,4), e as listas do critério (b) são dominadas por empresas de crescimento, construtoras e varejo, com margens de média próxima de zero ou séries curtas.
- **Por que o critério (c2):** o setor sozinho (a) inclui empresas sem sinal de ciclo nos dados (KLBN11 com 1 queda em 15 anos, SUZB3 com 2, UGPA3 com 3) e as que não têm série comparável (BRAP4 sem receita, PRIO3 e BRAV3 com receita mínima no início); a queda da receita sozinha (c1) inclui empresas que não são cíclicas no sentido das commodities (B3SA3, POMO4, VBBR3). A **interseção** pede uma razão econômica (setor de preço dado pelo mercado) mais um sinal observado (queda da receita nominal em ciclos, o que numa economia com inflação média de 5 a 6% ao ano só acontece com queda real relevante). A seleção é estável entre os limites de 25% a 33% das quedas (os três destaques entram) e perde o GGBR4 só com 40% (6 ações).
- **Atenções à lista:** GGBR4 e GOAU4 são o mesmo negócio (a GOAU4 consolida a Gerdau, e as séries são idênticas); PETR3 e PETR4 também são a mesma companhia; na prática, são **5 companhias**. A **CSAN3** tem saltos de receita de 2013 e 2021 (HIPÓTESE: reorganização), e a série dela é a menos comparável da lista.
- **O mais defensável é o (c2).** Separa as ações pela causa econômica e pela evidência, e não pela distância ao preço; os limites (1/3 dos anos, os setores) ficam em `config.py` se for implementado.

## 4. Métodos de normalização

### 4.1 Definições (funções existentes sem alteração; só o fluxo-base e o crescimento mudam)

- **Fluxo do FCD** (como hoje): caixa operacional (6.01) + saída líquida de risco sacado + juros pagos × (1 − 34%) − capex. **Caixa operacional ajustado A** = o mesmo, antes do capex.
- **M1:** margem média do fluxo do FCD (fluxo ÷ receita) na janela × receita do ano de referência.
- **M2:** margem média do caixa operacional ajustado × receita, menos o capex médio (capex ÷ receita) × receita. **CONFIRMADO:** M1 e M2 são **o mesmo número quando os anos coincidem** (a média de (A − capex) ÷ receita é igual à média de A ÷ receita menos a média de capex ÷ receita); diferem só quando faltam anos de capex, que M2 aceita na margem do caixa e M1 não (PETR3 e PETR4 de 2010 a 2012).
- **M3:** margem média do caixa operacional ajustado × receita, menos a depreciação de 2025 (capex de manutenção).
- **Janelas:** 2010 a 2025, 2015 a 2025 e 2019 a 2025 (só pós-IFRS 16), com no mínimo 5 anos válidos; média simples das razões anuais, com o filtro de ±100% do item 2.6.
- **Crescimento G1:** CAGR da receita na janela (do primeiro ano válido a 2025), dentro da faixa de −20% a +30%; o teto pela receita de hoje fica desligado para não aplicar a janela de 5 anos por cima. **G2:** o crescimento da perpetuidade (IPCA de 12 meses) desde o ano 1, ou seja, crescimento real zero.
- **Tratamento da quebra de 2019 (por método):**
  - nas três janelas, a média usa o caixa operacional pós-IFRS 16 como base (o mesmo critério do fluxo de hoje, em que o aluguel fica fora do fluxo e o passivo é descontado no fim);
  - em 2010 e 2015, os anos até 2018 recebem de volta um pagamento de arrendamento estimado em (arrendamento de 2019 ÷ receita de 2019) × receita do ano (**HIPÓTESE:** a proporção é estável); a coluna "naive" abaixo não faz esse ajuste;
  - M1 e M2 usam esse ajuste na margem do caixa; M3 usa o mesmo e subtrai a depreciação de 2025, que já inclui a amortização do direito de uso (HIPÓTESE: um critério conservador, porque trata a renovação de arrendamentos como reposição);
  - na janela 2019 a 2025 não há quebra (e a média tem 7 anos e um só ciclo).
- **Coerência entre método e crescimento (argumento econômico):** em M1 e M2 o capex médio **inclui o investimento de expansão**, e a margem constante faz o fluxo crescer como a receita, igual à lógica do teto pela receita que o app já usa: o par coerente é **M1/M2 com G1**. Em M3 a base só repõe o que existe (depreciação como manutenção), sem investimento de expansão: o par coerente é **M3 com G2**, porque crescer acima da inflação exigiria o capex que M3 tirou.

### 4.2 FCD das cíclicas (critério c2), R$ por ação (com o ajuste do IFRS 16 nas janelas de 2010 e 2015)

Atual: CSAN3 −3,62; GGBR4 0,14; GOAU4 −24,84; PETR3 43,61; PETR4 44,55; USIM5 4,24; VALE3 5,40.

| Janela | Método | Cresc. | CSAN3 | GGBR4 | GOAU4 | PETR3 | PETR4 | USIM5 | VALE3 |
|---|---|---|---|---|---|---|---|---|---|
| 2010 a 2025 | M1 | G1 | −9,7 | 14,8 | −5,2 | 77,1 | 78,6 | 3,4 | 48,2 |
| 2010 a 2025 | M1 | G2 | −10,0 | 14,3 | −5,9 | 73,6 | 75,0 | 3,3 | 45,1 |
| 2010 a 2025 | M2 | G1 | −9,7 | 14,8 | −5,2 | 69,6 | 70,9 | 3,4 | 48,2 |
| 2010 a 2025 | M2 | G2 | −10,0 | 14,3 | −5,9 | 66,4 | 67,7 | 3,3 | 45,1 |
| 2010 a 2025 | M3 | G1 | −6,8 | 16,0 | −3,5 | 66,3 | 67,6 | 8,7 | 100,5 |
| 2010 a 2025 | M3 | G2 | −7,2 | 15,4 | −4,3 | 63,2 | 64,4 | 8,6 | 94,9 |
| 2015 a 2025 | M1 e M2 | G1 | −2,9 | 17,4 | −1,5 | 94,5 | 96,2 | 8,5 | 67,9 |
| 2015 a 2025 | M1 e M2 | G2 | −6,6 | 17,2 | −1,9 | 93,9 | 95,5 | 7,3 | 58,7 |
| 2015 a 2025 | M3 | G1 | −1,3 | 17,8 | −1,0 | 81,4 | 82,8 | 8,7 | 101,2 |
| 2015 a 2025 | M3 | G2 | −5,4 | 17,5 | −1,5 | 80,8 | 82,3 | 7,5 | 88,4 |
| 2019 a 2025 | M1 e M2 | G1 | −5,7 | 20,4 | 2,7 | 125,7 | 127,8 | 11,5 | 72,6 |
| 2019 a 2025 | M1 e M2 | G2 | −9,4 | 17,6 | −1,4 | 111,8 | 113,7 | 10,0 | 68,8 |
| 2019 a 2025 | M3 | G1 | −0,6 | 24,0 | 7,8 | 103,3 | 105,1 | 12,8 | 95,2 |
| 2019 a 2025 | M3 | G2 | −5,7 | 20,7 | 3,2 | 91,5 | 93,1 | 11,2 | 90,4 |

(Informação, não argumento: preços de 02/10/2026 de VALE3 R$ 72,10, GGBR4 R$ 26,10 e PETR4 R$ 51,17.)

**Sensibilidade à janela e ao método (CONFIRMADO):** a variação entre janelas é grande: VALE3 vai de 48 (2010 a 2025) a 68 (2015 a 2025) e 73 (2019 a 2025) em M1 com G1; PETR4, de 79 a 96 e 128. M3 é maior que M1 em VALE3 (a depreciação de 2025, R$ 17,3 bi, é bem menor que o capex médio) e menor em PETR4 (R$ 84,4 bi de depreciação contra capex médio menor). G2 reduz o valor de G1 em 3% a 14% nas cíclicas (VALE3 em 2015 a 2025: 67,9 para 58,7), e a diferença é pequena em GGBR4 e PETR4.

### 4.3 Destaques e controles não cíclicos (R$ por ação)

Atual: VALE3 5,40 · GGBR4 0,14 · PETR4 44,55 · WEGE3 7,57 · KLBN11 28,03 · TIMS3 27,63 · RADL3 2,06.

| Janela, método, crescimento, IFRS 16 | VALE3 | GGBR4 | PETR4 | WEGE3 | KLBN11 | TIMS3 | RADL3 |
|---|---|---|---|---|---|---|---|
| 2010 a 2025, M1, G1, ajustado | 48,2 | 14,8 | 78,6 | 9,8 | 2,5 | 38,7 | 5,8 |
| 2010 a 2025, M1, G1, sem ajuste | 46,7 | 14,2 | 63,5 | 9,8 | 1,1 | 37,0 | −1,2 |
| 2010 a 2025, M1, G2, ajustado | 45,1 | 14,3 | 75,0 | 7,8 | −2,2 | 21,2 | 2,6 |
| 2010 a 2025, M3, G2, ajustado | 94,9 | 15,4 | 64,4 | 9,6 | −4,6 | 17,9 | 0,9 |
| 2015 a 2025, M1, G1, ajustado | 67,9 | 17,4 | 96,2 | 11,0 | 6,6 | 38,7 | 5,1 |
| 2015 a 2025, M1, G1, sem ajuste | 66,8 | 17,0 | 84,6 | 11,0 | 5,6 | 37,0 | 1,0 |
| 2015 a 2025, M1, G2, ajustado | 58,7 | 17,2 | 95,5 | 8,8 | 0,3 | 21,2 | 2,8 |
| 2015 a 2025, M3, G2, ajustado | 88,4 | 17,5 | 82,3 | 10,2 | 0,2 | 17,9 | 1,0 |
| 2019 a 2025, M1, G1 | 72,6 | 20,4 | 127,8 | 12,3 | 22,3 | 20,6 | 3,2 |
| 2019 a 2025, M1, G2 | 68,8 | 17,6 | 113,7 | 8,9 | 14,3 | 18,9 | 1,5 |
| 2019 a 2025, M3, G2 | 90,4 | 20,7 | 93,1 | 10,5 | 4,5 | 14,4 | −1,3 |

**Bases e taxas (CONFIRMADO, janela 2015 a 2025, ajustada):**

| Ação | Fluxo-base de hoje (R$ bi) | Margem do fluxo em 2025 | Margem média 2010 a 2025 / 2015 a 2025 / 2019 a 2025 | Base M1 2015 a 2025 (R$ bi) | Base M3 2015 a 2025 (R$ bi) | CAGR da receita (2010 / 2015 / 2019) |
|---|---|---|---|---|---|---|
| VALE3 | 19,06 | 8,9% | 14,2% / 17,3% / 19,6% | 37,03 | 51,54 | 6,5% / 9,6% / 6,2% |
| GGBR4 | 2,10 | 3,0% | 6,9% / 7,9% / 8,0% | 5,51 | 5,58 | 5,5% / 4,8% / 9,9% |
| PETR4 | 91,62 | 18,4% | 21,5% / 26,0% / 29,9% | 129,18 | 114,90 | 5,8% / 4,5% / 8,7% |
| WEGE3 | 3,88 | 9,5% | 9,5% / 10,8% / 11,0% | 4,40 | 5,13 | 16,0% / 15,4% / 20,5% |
| KLBN11 | 4,63 | 22,4% | 11,8% / 13,0% / 19,7% | 2,70 | 2,68 | 12,2% / 13,8% / 12,4% |
| TIMS3 | 8,90 | 33,4% | 29,7% / 29,7% / 27,1% | 7,91 | 6,90 | 34,4%\* / 34,4%\* / 7,4% |
| RADL3 | 1,34 | 3,0% | 3,7% / 3,8% / 3,1% | 1,69 | 1,26 | 22,9% / 17,4% / 16,6% |

\* O CAGR da TIMS3 de 2010 e de 2015 parte de 2018, o primeiro ano com DFP nesse CNPJ, e usa a receita antes do salto de 5,2 vezes de 2019 (item 2.6): o crescimento é artefato da troca de entidade (HIPÓTESE) e fica preso no teto de 30%.

**Leitura (CONFIRMADO nos números):** nos controles não cíclicos, o resultado de uma média longa depende da janela até no sinal: KLBN11 vai de −4,6 a 22,3 e RADL3 de −3,9 a 5,8; a TIMS3 tem o artefato de entidade; a WEGE3 sobe de 7,57 para 8,8 a 14,5. A normalização move as não cíclicas por razões que não são de ciclo (crescimento, perímetro, tendência de margem).

### 4.4 Efeito se o método valesse para as 53 (variação do FCD contra o atual, com o ajuste do IFRS 16)

| Janela, método, crescimento | Calculadas | Sem base positiva | Mediana | P10 a P90 | Extremos | FCD negativo (hoje 13) | Mudou o sinal (de negativo para positivo / o inverso) |
|---|---|---|---|---|---|---|---|
| 2010 a 2025, M1 e M2, G1 | 46 | 6 | −11% | −91% a +343% | −506% (MGLU3) a +10.582% (GGBR4) | 8 | 4 / 2 |
| 2010 a 2025, M1 e M2, G2 | 46 | 6 | −30% | −109% a +81% | −536% a +10.204% | 14 | 2 / 6 |
| 2010 a 2025, M3, G1 | 49 | 3 | +9% | −102% a +420% | −154% (COGN3) a +11.418% | 10 | 8 / 6 |
| 2010 a 2025, M3, G2 | 49 | 3 | −27% | −115% a +265% | −188% a +11.017% | 12 | 7 / 7 |
| 2015 a 2025, M1 e M2, G1 | 47 | 5 | +11% | −79% a +309% | −455% (MGLU3) a +12.476% | 10 | 3 / 3 |
| 2015 a 2025, M1 e M2, G2 | 47 | 5 | −23% | −90% a +115% | −498% a +12.266% | 11 | 2 / 3 |
| 2015 a 2025, M3, G1 | 49 | 3 | +22% | −64% a +437% | −175% (COGN3) a +12.700% | 7 | 7 / 2 |
| 2015 a 2025, M3, G2 | 49 | 3 | −23% | −91% a +230% | −171% a +12.487% | 8 | 7 / 3 |
| 2019 a 2025, M1 e M2, G1 | 45 | 7 | +19% | −56% a +316% | −198% (AXIA3) a +14.628% | 7 | 4 / 2 |
| 2019 a 2025, M1 e M2, G2 | 45 | 7 | −30% | −80% a +147% | −199% a +12.557% | 9 | 2 / 2 |
| 2019 a 2025, M3, G1 | 46 | 6 | +36% | −71% a +513% | −253% (COGN3) a +17.181% | 3 | 9 / 2 |
| 2019 a 2025, M3, G2 | 46 | 6 | −12% | −82% a +272% | −249% a +14.822% | 5 | 8 / 3 |

Em todas as combinações, 1 ação fica sem receita (BRAP4) e de 3 a 7 ficam sem base normalizada positiva (a margem média do fluxo é zero ou negativa). **Conclusão (CONFIRMADO):** aplicada às 53, a normalização muda o valor de uma ação típica em dezenas de pontos percentuais para cima ou para baixo (P10 a P90 de −91% a +343% no caso base), troca o sinal do FCD em 4 a 14 ações e dispara valores de milhares de por cento onde o fluxo de hoje é quase zero (GGBR4). Essa dispersão não é efeito de ciclo, e **a normalização deve valer só para as cíclicas.**

## 5. Viabilidade de ler 10 a 16 anos por empresa

- **Tempo na rodada do screener (CONFIRMADO):** a extração completa de 2010 a 2025 das 53 ações levou **~31 s** lendo cada membro do zip uma única vez (86 leituras, com a regra atual do projeto para capex, juros, risco sacado e receita). Do jeito que a leitura é feita hoje, cada empresa-ano reabre o CSV inteiro do zip: **5,7 a 7,2 s por chamada** medidos em 3 chamadas (extrapolação: 848 chamadas, cerca de 85 minutos para 53 ações e 16 anos). O custo cai de ~85 min para ~31 s com uma leitura em lote (um zip lido uma vez para todas as empresas), o que muda a estrutura de `ingest/cvm.py`, mas não a regra. **HIPÓTESE:** para as 76 ações do Ibovespa o tempo fica na mesma ordem (a leitura é dominada pelo número de zips).
- **Cache no GitHub Actions (CONFIRMADO):** os zips de 2010 a 2025 somam 175,1 MB (hoje o cache tem ~67 MB, de 4 DFP e o ITR), então o acréscimo é de **~108 MB**, muito abaixo do limite de 10 GB. Como os zips de anos fechados não mudam, o ideal é uma chave de cache fixa para eles (~162 MB para 2010 a 2024) e a chave semanal só para o zip do ano corrente e o ITR. Primeira execução sem cache: os 9 zips novos (84,8 MB) baixam em poucos segundos na velocidade medida (11,6 MB/s).
- **Efeito na página de uma ação (hoje calcula ao vivo):** ler 16 anos ao vivo seria inviável: 16 chamadas de ~6 s cada (~96 s) e, no Streamlit Community Cloud, sem disco persistente, o download de 175 MB a cada partida. A proposta é a **rodada do screener (o workflow) gravar uma série histórica pré-calculada** (por ação e ano: receita, caixa operacional ajustado, capex, juros, depreciação), que a página lê em milissegundos. A tabela de 751 linhas ocupa **63 KB** em CSV (**HIPÓTESE:** o formato e o local `data/processed/`, que o workflow já commita). A página calcula a normalização sobre essa série sem rede.

## 6. Recomendação (pelo critério de coerência econômica)

**Normalizar só as cíclicas do critério (c2): CSAN3, GGBR4, GOAU4, PETR3, PETR4, USIM5 e VALE3.**

1. **Método M1** (margem média do fluxo do FCD × receita do ano de referência), com **crescimento G1**, **janela 2015 a 2025** e **ajuste do IFRS 16** nos anos até 2018. Razões: (i) capex médio inclui o investimento de expansão, e a margem constante faz o fluxo crescer como a receita, que é a premissa que o app já usa no teto pela receita; (ii) a janela de 11 anos cobre o piso de 2015 e 2016, o superciclo de 2020 a 2022 e o recuo de 2023 a 2025, mais perto de um ciclo completo que os 7 anos pós-IFRS 16; (iii) tem menos lacunas e menos quebras de perímetro que 2010 a 2025 (PETR4 e TAEE11 sem capex de 2010 a 2012 e 2010 a 2014; PRIO3 e BRAV3 com receita mínima).
2. **Limitações de cada opção:**
   - *Janela 2015 a 2025:* cerca de 1,5 ciclo; o superciclo de 2020 a 2022 pesa (a margem do fluxo da PETR4 foi de 43% em 2020 e a da VALE3 de 38% em 2021). Com a **mediana** no lugar da média, a base cai em PETR4 (de 129,2 para 111,5 R$ bi, FCD de 96,2 para 79,7) e sobe em VALE3 (de 37,0 para 39,9 R$ bi, FCD de 67,9 para 74,5). **HIPÓTESE:** a média de 2015 a 2025 fica acima do "meio do ciclo" da PETR4.
   - *2010 a 2025:* dois ciclos, mas lacunas, o IFRS 16 e perímetro (VALE3 48 contra 68 em 2015 a 2025).
   - *2019 a 2025:* sem IFRS 16, mas um ciclo só (PETR4 128).
   - *M3 com G2* (depreciação de 2025 como capex de manutenção, crescimento só da inflação): é o par coerente com um investimento só de reposição, mas depende de um número contábil que inclui a amortização do direito de uso e, em VALE3, dá o dobro de M1 (101 contra 68); fica como alternativa.
   - *G1:* o CAGR da receita em reais de 2015 a 2025 inclui câmbio e inflação (VALE3 9,6% ao ano; **HIPÓTESE:** parte vem da desvalorização do real); G2 é independente da janela e reduz o FCD em 3% a 14%.
   - *IFRS 16:* o ajuste adiciona (arrendamento de 2019 ÷ receita de 2019) × receita nos anos até 2018, **HIPÓTESE** de proporção estável; PETR4 +24% contra a média sem ajuste (79 contra 64 em 2010 a 2025, M1 com G1), VALE3 +3%, GGBR4 +4%.
   - *Perímetro:* a CSAN3 (saltos de 2013 e 2021) é a menos comparável da lista; convém decidir se ela fica de fora da normalização.
3. **Não generalizar às 53** (item 4.4).
4. **Implementação (se aprovada):** a rodada do screener passaria a ler 2010 a 2025 em lote, gravar a série pré-calculada (63 KB) e o FCD das cíclicas usaria a base normalizada com um aviso no cartão (valor da base de hoje contra a normalizada e o motivo), com os limites e textos em `config.py`.

## 7. Perguntas em aberto

1. Janela: 2015 a 2025 (recomendada), 2010 a 2025 ou 2019 a 2025? E média ou mediana da margem?
2. Crescimento: G1 (coerente com M1) ou G2 (independente da janela e do câmbio)?
3. A CSAN3 fica de fora (série com saltos de perímetro) e as duplas GGBR4/GOAU4 e PETR3/PETR4 seguem o mesmo tratamento?
4. O critério (c2) (setor e queda da receita em 1/3 dos anos) é aceitável, ou prefere o setor da B3 sozinho?
5. A série histórica pré-calculada (63 KB) pode ser gravada pela rodada do workflow em `data/processed/`?
6. Verificar nas notas explicativas as causas dos saltos de perímetro (CSAN3, TIMS3, SUZB3) e a identificação dos arrendamentos de 6.03 antes de implementar?
7. O aviso na tela deve mostrar o fluxo-base de hoje ao lado do normalizado?

## 8. Decisões (04/10/2026)

Nenhuma das decisões abaixo está implementada; a implementação fica para a migração para o Supabase (item 3).

1. **Critério de cíclica: (c2).** Setor de commodities da B3 (minerais metálicos, siderurgia, exploração, refino e distribuição de petróleo e gás, papel e celulose, químicos) e receita nominal em queda em pelo menos 1/3 dos anos. A **CSAN3 fica fora da lista**, porque as reorganizações de 2013 e 2021 tornam a série não comparável. **Lista resultante:** GGBR4, GOAU4, PETR3, PETR4, USIM5 e VALE3 (na prática, 4 companhias).
2. **Método:** M1 (margem média do fluxo do FCD × receita do ano de referência) com **G1** (CAGR da receita na janela, dentro da faixa de −20% a +30%), **janela de 2015 a 2025**, **ajuste do IFRS 16** nos anos até 2018, aplicado **só às cíclicas** da lista. **M3 com G2** (depreciação de 2025 como capex de manutenção e crescimento só da inflação) fica registrado como alternativa.
3. **Implementação adiada para a migração para o Supabase.** A série histórica de 2010 a 2025 por empresa passa a ser uma tabela do banco, gravada pela rodada do screener, e a normalização é implementada em cima dela, sem ler os zips na página. **Estimativa de viabilidade (seção 5):** leitura em lote das 53 ações em 16 anos em ~31 s (contra ~85 min se cada empresa-ano reabrir o zip), 175,1 MB de zips (+108 MB sobre o cache de hoje, contra o limite de 10 GB do GitHub Actions) e série de 63 KB (751 linhas). **HIPÓTESE:** o tempo e o tamanho valem na mesma ordem para as 76 ações e para o formato da tabela do banco.
4. **Até lá:** o item das empresas cíclicas de `docs/limitacoes-conhecidas.md` traz a faixa de valores normalizados de VALE3, GGBR4 e PETR4 (M1 com G1, janelas de 2010, 2015 e 2019 a 2025) e diz que a sensibilidade à janela é a principal limitação.

## 9. Confirmado e hipóteses

**CONFIRMADO no código:** a regra atual de capex, juros, risco sacado e receita (`ingest/cvm.py`) aplicada a 2010 a 2025; a função do FCD e os parâmetros usados (`modelos/fcd.py`, importada sem alteração; o fluxo recomposto de 2025 coincide com o usado hoje, diferença de 2,4e-7 R$).

**CONFIRMADO nos dados:** layout e identidade da DFC de 2010 a 2025; cobertura e lacunas por ação e ano; tamanho do efeito do IFRS 16 (pagamentos identificados no 6.03); saltos de receita; critérios de cíclica e suas listas; todas as tabelas de FCD, M1 igual a M2 quando os anos coincidem; efeito nas 53; tempos (31 s em lote, 5,7 a 7,2 s por chamada), tamanhos (175,1 MB e 63 KB) e velocidade de download.

**HIPÓTESE (não confirmada):** causa dos saltos de receita e das trocas de CNPJ (aquisições, reorganizações, abertura de capital); a série da TIMS3 até 2018 ser de outra entidade; a proporção do arrendamento ser estável antes de 2019 (ajuste); a identificação do arrendamento pela descrição do 6.03 captar os pagamentos; o superciclo de 2020 a 2022 elevar a média da PETR4 acima do meio do ciclo; o CAGR em reais refletir parte do câmbio; o tempo das 76 ações ser da mesma ordem; o formato e o local da série pré-calculada.

**Reprodução.** Scripts e dados em `%TEMP%\investigacao_ciclicas` (`baixa.py`, `extrai16.py`, `base.py`, `cobertura.py`, `run_metodos.py`). Nada foi gravado no repositório além deste relatório; os zips de 2010 a 2018 (84,8 MB) ficaram no cache temporário.
