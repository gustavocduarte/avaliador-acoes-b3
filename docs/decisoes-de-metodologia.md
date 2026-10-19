# Decisões de metodologia

Este documento registra as decisões que mudaram o que o modelo calcula e como: o problema, as alternativas consideradas, a decisão, o porquê e os commits. As correções de bugs e as revisões de código estão em [`historico-de-revisoes.md`](historico-de-revisoes.md); o que ficou como limitação para quem usa o app está em [`limitacoes-conhecidas.md`](limitacoes-conhecidas.md). O que foi decidido e ainda não foi implementado está na última seção.

## Como ler

- **Critério das investigações.** Cada alternativa é julgada pela coerência econômica da regra, e nunca pela distância entre o FCD e o preço: essa distância aparece só como informação. As investigações de 02/10 a 04/10 foram só de leitura (nenhum código, teste ou dado versionado foi alterado) e separam o que foi **CONFIRMADO** (lido no código, medido nos dados ou calculado com as funções do projeto) do que é **HIPÓTESE** (plausível, não verificado).
- **Dados de referência.** Salvo indicação, os números são os de 02/10 a 04/10/2026 (Selic meta 13,75%, IPCA 12 meses 4,2235%, 53 ações com FCD, 76 no universo).
- **Siglas.** P03, P04, P09, P10 e P11 são os identificadores da auditoria técnica de 27/09 (ver o histórico). "Pergunta N" é o número da pergunta em aberto da investigação P03/P04. FCD é o fluxo de caixa descontado, e WACC é o custo médio ponderado de capital.

### Relatórios que este documento substitui

Os relatórios originais foram removidos da pasta `docs/` e continuam no histórico do Git. Todos existem no commit `90327ec`, o último antes da remoção:

```bash
git show 90327ec:docs/<arquivo>.md
# ou, para gravar num arquivo fora do repositório (PowerShell):
git show 90327ec:docs/<arquivo>.md > $env:TEMP\<arquivo>.md
```

| Arquivo removido | Seção deste documento | Recuperar |
|---|---|---|
| `correcao-fcd-2026-09-23.md` | 1.1 | `git show 90327ec:docs/correcao-fcd-2026-09-23.md` |
| `correcao-ano-fcd-2026-09-23.md` | 1.2 e 1.3 | `git show 90327ec:docs/correcao-ano-fcd-2026-09-23.md` |
| `correcao-cnpj-2026-09-25.md` | 1.4 (a correção em si está no histórico) | `git show 90327ec:docs/correcao-cnpj-2026-09-25.md` |
| `investigacao-p03-p04-2026-10-02.md` | 2 a 5 | `git show 90327ec:docs/investigacao-p03-p04-2026-10-02.md` |
| `investigacao-p10-2026-10-04.md` | 6 | `git show 90327ec:docs/investigacao-p10-2026-10-04.md` |
| `investigacao-fluxo-base-2026-10-04.md` | 7 | `git show 90327ec:docs/investigacao-fluxo-base-2026-10-04.md` |
| `investigacao-ciclicas-2026-10-04.md` | 8 e 9 | `git show 90327ec:docs/investigacao-ciclicas-2026-10-04.md` |

As tabelas por empresa (fluxos ano a ano de oito empresas, comparações das 76 ações, listas completas de cíclicas) ficam nos originais.

## Sumário

1. Correções de metodologia: valor do acionista e bancos, ano de referência, validade do zip da CVM, FCD baixo e reinvestimento
2. Simulador de carteira (P03)
3. Fluxo de caixa do FCD (P04)
4. Do valor da empresa ao valor do acionista: dívida e arrendamento, não controladores, pesos do WACC, número de ações, units, valor de firma
5. O vocabulário "Potencial" (P11)
6. Crescimento e prêmio de risco (P09 e P10)
7. Fluxo-base: capital de giro e risco sacado
8. Empresas cíclicas
9. Em aberto

---

## 1. Correções de metodologia

### 1.1 Valor da empresa para valor do acionista e bancos

- **Problema.** O FCD descontava o fluxo pelo WACC (chegando ao valor da empresa, *enterprise value*) e dividia o resultado direto pelo número de ações, sem subtrair a dívida líquida. Isso tratava o valor da empresa como valor do acionista e inflava o valor por ação de toda empresa endividada.
- **Decisão.** Subtrair a dívida líquida antes de dividir por ação (`2f66089`). Dívida líquida negativa (caixa líquido) soma, sem caso especial. Na regeneração do `screener.csv` (`e26dd69`), o FCD da PETR4 foi de R$ 118,82 para R$ 94,86 e o valor combinado de R$ 91,04 para R$ 83,05.
- **Bancos: alternativas.** (a) manter o FCD aplicável quando a dívida líquida falta, com um aviso de que a dedução não foi feita; (b) tornar o FCD não aplicável para os bancos.
- **Decisão sobre os bancos.** Foi escolhida a (a) de manhã e revista pouco mais de uma hora depois, no mesmo dia, para a (b): o FCD é **não aplicável para o segmento Bancos** (`f285819`, regeneração em `f197ac5`, adendo em `371f9b3`). O escopo ficou restrito a esse segmento.
- **Por quê.** Nos bancos o problema não é falta de dado, e sim a metodologia: dívida e depósitos são a própria operação (captação para emprestar), e o caixa operacional oscila com a expansão ou contração da carteira de crédito, não com geração de valor. Não existe "dívida líquida certa" para deduzir. A legenda da alternativa (a) ainda errava a direção: dizia que o valor tendia a ficar mais alto, mas nos dados o FCD saía abaixo de Graham e Bazin em 4 dos 5 bancos calculáveis (o SANB11 chegava a −R$ 23,33).
- **Efeito no valor combinado dos seis bancos:** ITUB4 de R$ 33,75 para R$ 46,99, SANB11 de R$ 21,53 para R$ 43,96, BPAC11 de R$ 23,68 para R$ 35,04, BBDC3 de R$ 25,94 para R$ 26,52, BBDC4 de R$ 26,47 para R$ 27,69 (o BBAS3 já não tinha FCD).
- **Seguradoras e outras financeiras** ficaram fora dessa correção por terem dívida líquida reportada; foram tratadas na seção 3.4.

### 1.2 Ano de referência do FCD

- **Problema.** O ano de referência era uma constante fixa (2024), escrita quando a CVM ainda não tinha publicado 2025.
- **Alternativas.** Manter o ano fixo e atualizá-lo à mão; ou detectar o ano mais recente publicado.
- **Decisão.** Detecção automática em **dois níveis** (`7a29e7f`; regeneração do `screener.csv` em `1560fac`). *Nível arquivo:* o candidato é o ano corrente menos 1; se a CVM ainda não publicou o zip (404, na janela de janeiro a março), cai para o ano anterior, uma vez por execução. *Nível empresa:* se a empresa específica ainda não entregou a DFP do ano mais recente (`CnpjNaoEncontrado`), cai um ano só para ela, e o ano-base do crescimento anda junto, mantendo o intervalo de cinco anos.
- **Por quê.** Uma constante envelhece em silêncio. O fallback por empresa evita perder o FCD de todas só porque uma ainda não publicou. A exceção `ContaFluxoCaixaNaoEncontrada` **não** dispara o fallback, porque indica mudança de layout da CVM, e cair para o ano anterior esconderia um erro real de leitura atrás de um número de outro ano.
- **Achados no meio da implementação.** O cache do zip era permanente (ver 1.3), e o motivo da falha do FCD nunca chegava à coluna "erro" do Screener, porque o valor combinado usa a sua própria mensagem. A correção foi um aviso global por rodada (`DeteccaoAnoCvmFalhouWarning`), mostrado na tela quando a rodada é disparada pelo botão.
- **Limitação registrada.** Mudar o ano desloca também o ano-base do crescimento (de 2019 para 2020). Isso pesa mais do que a variação do fluxo sugere: o fluxo da PETR4 caiu 13,3% e o FCD, 49% (R$ 94,96 para R$ 48,22); o da VALE3 caiu 47% e o FCD passou de R$ 12,06 para −R$ 8,53. E 2020 é um ano atípico para a maioria dos setores.

### 1.3 Validade do zip anual da CVM

- **Problema.** O cache do zip era permanente, e a CVM atualiza o zip do ano corrente conforme as empresas entregam a DFP (inclusive fora do prazo). Um zip baixado cedo ficaria incompleto para sempre num ambiente com disco persistente.
- **Primeira decisão (23/09).** Prazo de 7 dias para os anos em preenchimento (`ano >= ano corrente − 1`) e cache permanente para os anos fechados (`7a29e7f`). Se a atualização falha e há um zip em cache, usa o existente, com aviso.
- **Segunda decisão (19/10).** A premissa "anos fechados não mudam" era falsa: a CVM reapresenta demonstrações e regenera arquivos (em 04/10/2026 regenerou os zips de 2022 a 2025 e o ITR de 2026). Os zips de anos fechados passam a valer **30 dias**, e os resultados derivados (fluxo de caixa, lucro e balanço) guardam o tamanho e a data do zip de origem e são refeitos quando ele muda ou vence. Sem o zip no disco, vale o mesmo prazo sobre a data guardada no cache (`8a7aaa9`).
- **Por quê.** Um download mensal de cerca de 13 MB por ano usado é um custo baixo perto do risco de manter congelada uma demonstração reapresentada.

### 1.4 FCD baixo e reinvestimento

- **Problema.** Depois da correção do CNPJ (ver o histórico), 11 das 20 ações recuperadas ficaram com FCD negativo, 7 delas de energia elétrica.
- **Hipótese inicial.** O fluxo (6.01 + 6.02) penaliza empresas em investimento pesado financiado com dívida, e o setor elétrico seria o caso clássico.
- **Resultado da investigação (70 ações com FCD).** O fator principal é a **intensidade de reinvestimento** da empresa (correlação de Spearman de −0,79 entre a proporção reinvestida do caixa operacional e o quanto o FCD diverge do Graham), e não o setor: há exceções nos dois sentidos dentro do mesmo setor (FLRY3 reinveste pouco e não sofre o efeito). A dívida líquida alta é um segundo fator e, na AXIA3, o dominante.
- **Decisão.** Mostrar a proporção reinvestida como contexto, na legenda do cartão do FCD e na coluna "Reinvestimento" do Screener (`5affa0c`, regeneração em `ef4512a`), sem excluir setores nem mudar o cálculo do fluxo. Registro em `111dfd7`. A separação entre investimento de manutenção e de expansão (por depreciação e amortização) ficou como evolução possível: a conta não tem código fixo entre empresas. Depois que o fluxo passou a usar o capex, o reinvestimento foi recalculado sobre o mesmo caixa operacional do FCD (`b7bc05f`, `457b6c4`, `5127245`).

---

## 2. Simulador de carteira (P03)

- **Problema (CONFIRMADO).** O Simulador tratava o valor justo de hoje como preço daqui a 5 anos (o prazo era o horizonte de projeção do FCD, sem relação com o tempo que o mercado levaria para convergir) e deflacionava esse valor pelo IPCA. O valor justo já está em reais de hoje. No exemplo da LREN3 no cenário base, o Simulador mostrava "ganho real" de R$ 4.132 sobre R$ 10.000, enquanto o mesmo valor justo crescendo à inflação dava R$ 7.379 em reais de hoje.
- **Alternativas.** **A:** manter prazo e taxa, com prazo e crescimento escolhidos pelo usuário. **B:** potencial sem prazo, sem taxa anual e sem "ganho real". **C:** retorno total estimado (dividendos mais crescimento mais convergência amortizada em N anos).
- **Decisão.** **Opção B** (`9bea4c6`; textos alinhados em `c878f10`). O piso de −100% (valor justo ≤ 0 conta como perda total) continua (`15ca3c9`).
- **Por quê.** O Simulador mistura métodos com fragilidades diferentes: o FCD sai extremo em 16 de 70 ações e o Bazin é um preço teto, não uma estimativa de valor. Acrescentar prazo, crescimento e dividendos (A e C) multiplica as premissas sobre insumos frágeis e dá precisão falsa. A B remove os três problemas confirmados (prazo arbitrário, inflação sobre valor de hoje e dividendos ausentes) sem inventar um substituto. A C depende de dividend yield constante (proventos extraordinários) e de uma regra à parte para valor justo ≤ 0. A **A** fica como evolução opcional.

---

## 3. Fluxo de caixa do FCD (P04)

### 3.1 Definição do fluxo

- **Problema (CONFIRMADO).** O fluxo era 6.01 + 6.02 do último ano, que não é um fluxo livre da firma. Em 30 das 64 empresas não financeiras os juros pagos ficam dentro de 6.01 (o fluxo vira "depois de juros", e descontá-lo pelo WACC e subtrair a dívida penaliza o custo da dívida duas vezes). A conta 6.02 mistura capex com aplicações financeiras e venda de participações (na CSAN3, o 6.02 de 2025 é −R$ 76 mi porque o capex de R$ 8,46 bi foi anulado por R$ 8,95 bi de venda de investimentos). O arrendamento (IFRS 16) está em 6.03 em 51 das 64 empresas, fora do fluxo.
- **Alternativas.** **alt1:** 6.01 − capex. **alt2:** 6.01 − capex − arrendamento pago + juros pagos em 6.01 × (1 − 34%). **alt3:** 6.01 − capex + juros pagos em 6.01 × (1 − 34%), sem subtrair o arrendamento.
- **Decisão.** **alt3**, com **capex explícito**: quando o capex não é identificado, o FCD fica **não aplicável**, com o motivo na tela, sem voltar para 6.01 + 6.02. A soma de volta considera só as linhas dedicadas a juros de empréstimos, financiamentos e debêntures em 6.01; linhas de juros de arrendamento e linhas mistas ficam de fora. Extração por descrição das subcontas em `78f671e`, FCD em `e23397b`, regeneração do `screener.csv` em `23f0e16`.
- **Por quê.** A alt1 sozinha corrige o 6.02 mas deixa os juros de 30 empresas dentro do fluxo. A alt2 só é coerente onde o arrendamento está fora da dívida do Fundamentus (5 das 9 empresas verificadas): onde está dentro (CSAN3, PETR4), subtrair o pagamento conta o custo duas vezes (a PETR4 iria de R$ 26,55 para −R$ 10,13). O capex é identificado por descrição em 63 das 64 empresas em 2025 e 63 de 63 em 2020 (a exceção é a IGTI11), mas as regras foram ajustadas sobre os mesmos dados: o número vale **dentro da amostra**.
- **Limitação.** Onde o arrendamento está dentro da dívida (PETR4, CSAN3), os juros dele continuam descontados do fluxo e o passivo também sai na dívida líquida: uma pequena dupla contagem. O MRVE3 tem uma linha mista (cerca de R$ 70,9 mi) que não entra na soma.

### 3.2 Demonstração consolidada zerada (TIMS3)

- **Problema (bug de dado).** A DFC consolidada do TIMS3 está zerada na CVM em 2024 e 2025, e o app a aceitava (só pulava demonstração sem linhas): fluxo 0 e FCD de R$ 0,79. Com a individual seria R$ 57,67.
- **Decisão.** Se a consolidada do ano tem 6.01 e 6.02 iguais a zero (ou ausentes), ela é tratada como inexistente e o app usa a individual daquele ano. Corrigido em `4e23afb`, com a subida de `VERSAO_SCHEMA_CVM_FCF` para 2.

### 3.3 Mesma demonstração nos dois anos do crescimento

- **Problema.** Em 5 empresas o ano de referência e o ano-base usavam demonstrações diferentes (consolidada contra individual), o que muda o crescimento (ASAI3, TIMS3, BRAP4, SBSP3, SANB11).
- **Decisão.** Quando a do ano de referência existe, com valores, também no ano-base, o ano-base usa a mesma; senão vale a escolha padrão (`77530c4`). Com a alt3, o crescimento da ASAI3 passa de 19,5% para 15,1% e o FCD de R$ 44,53 para R$ 36,55; nas demais o efeito é irrelevante.

### 3.4 Quando o FCD não se aplica, e o aviso de valor extremo

- **Financeiras não bancárias (pergunta 6).** O FCD fica não aplicável para as seguradoras (BBSE3, PSSA3, CXSE3) e para a ITSA4. A B3SA3 continua com FCD, com a limitação documentada (`81a7f4a`).
- **Fluxo de referência não positivo (pergunta 7).** O FCD fica não aplicável quando o fluxo-base é ≤ 0, porque perpetuar fluxo negativo não estima valor (`81a7f4a`, e desde `e23397b` aplicado ao fluxo da alt3). As regras de aplicabilidade usam só as entradas do modelo. **Descartado:** excluir ou limitar o FCD pela razão FCD ÷ preço, que seria aproximar o modelo do preço.
- **Aviso de valor extremo.** Em vez de limitar o valor, o cartão do FCD mostra um aviso mais forte, só informativo, com a causa provável nas entradas do modelo (deduções acima ou perto do valor da empresa, crescimento no teto ou no piso, perpetuidade com 70% ou mais do valor, WACC baixo, fluxo do ano a partir de 50% do valor de mercado). Dispara com FCD ≤ 0, FCD ≥ 3 vezes o preço ou FCD positivo até 10% do preço (17 das 53 ações em 04/10/2026): `940a1a3`.
- **Teste frágil (pergunta 11).** `tests/test_conftest.py` não podia depender de o cache real existir ou não: corrigido em `e29e83b`.

---

## 4. Do valor da empresa ao valor do acionista

Os itens 4.1 a 4.4 foram decididos juntos, porque dependem do mesmo dado novo: o balanço consolidado da CVM (ITR ou DFP) na data-base da dívida do Fundamentus. Foram implementados sobre uma única leitura (`f394005`), com o `screener.csv` regenerado em `64b7014`.

### 4.1 Dívida líquida e arrendamento (pergunta 4 e etapa seguinte da alt3)

- **Problema.** Decidir entre alt2 e alt3 dependia de como o Fundamentus monta a "Dív. Líquida".
- **Resultado (CONFIRMADO em 9 empresas; que valha para as 76 é HIPÓTESE).** Dív. Bruta = contas 2.01.04 + 2.02.01 (inclui debêntures e, quando a empresa a registra ali, a subconta "Financiamento por Arrendamento"); Disponibilidades = 1.01.01 + 1.01.02; a diferença para o balanço da CVM é 0,0%. O arrendamento está **dentro** da dívida em 2 das 9 (CSAN3, PETR4), **fora** em 5 (RADL3, KLBN11, WEGE3, MGLU3, TIMS3) e inexistente em 2. As aplicações financeiras registradas em outras contas (R$ 5,5 bi na CSAN3) não são abatidas.
- **Decisão.** O passivo de arrendamento fora da dívida do Fundamentus é **somado à dedução do valor do acionista** (`83246eb`). **Arrendamento nos pesos do WACC: não incluído** enquanto os pesos forem contábeis (mais dívida contábil baixa o WACC e empurra o valor para cima); fica para quando os pesos forem a valor de mercado (seção 9).
- **Limitação.** O FCD da alt3 ignora o custo do arrendamento onde ele está fora da dívida (RADL3, por exemplo, iria de R$ 4,90 para R$ 1,97 com o passivo somado); a soma na dedução corrige isso.

### 4.2 Participação dos não controladores (pergunta 12)

- **Problema (CONFIRMADO).** O FCD é consolidado, mas a participação dos não controladores não era subtraída em lugar nenhum. Em 11 das 53 ações ela passa de 10% do patrimônio total (CSAN3 84,4%, GOAU4 64,2%, KLBN11 40,6%, BEEF3 27,6%).
- **Alternativas.** **A:** subtrair o valor contábil dos não controladores (conta 2.03.09) junto com a dívida líquida. **B:** multiplicar o FCD pela fração do lucro atribuída aos controladores.
- **Decisão.** **A** (`7b206e6`). Um valor negativo depois do ajuste é mostrado como está, com o aviso "Valor justo zero ou negativo", sem limitar a zero; o caso da GOAU4 (de R$ 0,50 para −R$ 25,63) vai para as limitações.
- **Por quê.** O fluxo e o valor da empresa são consolidados, então a parte dos minoritários tem de sair como a dívida; é dado de balanço padronizado, disponível na mesma data-base da dívida e sem depender do sinal do lucro. A B depende do lucro de um único ano e perde o sentido com prejuízo (CSAN3, MRVE3 e USIM5 dão frações de 95%, 100% e 106%); na KLBN11 a CVM publica as linhas zeradas e a B zera o valor.
- **Limitação.** O valor contábil costuma ser menor que o de mercado dos minoritários (CSAN3: Rumo e Compass).

### 4.3 Patrimônio nos pesos do WACC (pergunta 15)

- **Problema (CONFIRMADO).** O "Patrim. Líq" do Fundamentus é o patrimônio dos **controladores**, e o índice Dív Líq / Patrim do WACC usava a dívida consolidada sobre esse patrimônio: com minoritários relevantes, o peso da dívida (barata, pós-imposto) ficava inflado. Na CSAN3, esse fator pesava mais que a subtração dos minoritários (−R$ 18,15 contra −R$ 6,79 por ação, com o índice indo de 9,57 para 1,49 e o WACC de 11,96% para 17,04%).
- **Decisão.** Usar o patrimônio líquido total (controladores + não controladores), coerente com o fluxo e a dívida consolidados, com a razão do Fundamentus como fallback e o motivo no cartão (`b3cacb6`). Os pesos a valor de mercado seguem como limitação do P09.

### 4.4 Número de ações (pergunta 16)

- **Problema (CONFIRMADO).** O número de ações do Fundamentus divergia da composição do capital da CVM em mais de 1% em 25 das 76 ações (EGIE3 +24%, VALE3 +4,3%, AXIA3 −3,9%), com escala em milhares em 22 empresas e a tesouraria incluída na maioria (68 de 76 ficam a menos de 1% do capital integralizado).
- **Alternativas.** Manter o número do Fundamentus; usar o integralizado da CVM; usar o **em circulação** (integralizado menos tesouraria).
- **Decisão.** O FCD por ação, o Graham, o valor de mercado e o valor de firma usam as ações em circulação da CVM na data-base do balanço, com as units mantidas e LPA e VPA do Fundamentus reescalados pela razão entre os dois números. Leitura indisponível cai no número do Fundamentus, com o motivo (`f394005` leitura e salvaguardas, `d64dccc` FCD e Graham, `244344e` tela e valor de mercado).
- **Salvaguardas.** Normalização de escala quando a razão fica perto de 1.000; tesouraria acima de 20% do capital descartada como erro de escala (TEND3); integralizado já líquido de tesouraria reconhecido (VALE3), com tesouraria abaixo de 0,5% seguindo o padrão de subtrair; divergência acima de 50% descartada (IGTI11). O aviso na tela só aparece quando o número do Fundamentus não bate nem com o em circulação nem com o integralizado, com diferença acima de 2% (EGIE3 e ISAE4).

### 4.5 Units

- **Problema.** O número de ações das units (KLBN11, TAEE11, ENGI11) podia estar em outra base que o preço (P06 da auditoria técnica); corrigido em `b2d1d2a`, que põe o número de ações das units na base do preço da unit (regeneração em `bb947fe`).
- **Fator da IGTI11 (pergunta 17).** O Fundamentus entrega fator 7 e a CVM tem 1.206 mi de ações contra 296,7 mi de units. **CONFIRMADO:** o fator 7 está certo (1 ON + 2 PN que valem 3 vezes a ON: 1 + 2 × 3 = 7 ordinárias equivalentes), e o P06 acerta o valor por unit.
- **Decisão.** Converter o número da CVM das units por **peso econômico**, com uma tabela de composições em `config.py` e aviso na página quando o fator do Fundamentus não bate com a tabela ou a unit não está nela (`74a8702`). Na IGTI11 o número convertido (296,5 mi) fica 0,09% abaixo do do Fundamentus e deixa de cair na trava de 50%; as outras cinco units (SANB11, KLBN11, TAEE11, BPAC11, ENGI11) batem e não mudam. A mensagem da trava de 50% ficou neutra, com a explicação para units (`f07c15e`).

### 4.6 Valor de firma

O valor de firma da página (mercado + dívida líquida) não incluía os não controladores nem o arrendamento fora da dívida, ao contrário da ponte do FCD. Foi alinhado, só na exibição (`5b0b5e9`).

---

## 5. O vocabulário "Potencial" (P11)

- **Problema.** A coluna "Desconto" é, na verdade, o potencial de valorização (valor justo ÷ preço − 1).
- **Decisão.** O número mostrado passa a se chamar **Potencial** (`26e8002`). A coluna `desconto_percentual` continua no `screener.csv`: renomeá-la seria uma migração de schema, que fica para quando houver outra mudança de schema.

---

## 6. Crescimento e prêmio de risco (P09 e P10)

### 6.1 Crescimento do FCD

- **Problema (CONFIRMADO).** O crescimento explícito era o CAGR entre o fluxo de 2025 e o de 2020, limitado a −20% e +30% ao ano, e depois caía de uma vez para o IPCA na perpetuidade. Entre as 53 ações: 12 no teto de 30%, 1 no piso, 9 no IPCA (base ausente ou não positiva) e 31 no meio. O valor terminal pesa 56% do FCD (mediana). O teto quase sempre vinha de ano-base pequeno ou atípico.
- **Alternativas.** **A:** médias de três anos nas pontas. **B:** fluxo-base médio. **C:** tetos menores (15% e 20%). **D:** teto pelo crescimento da receita no mesmo período. **E:** convergência linear para o crescimento da perpetuidade.
- **Decisão.** **D + E**, mantendo a faixa de −20% a +30% como limite externo. Sem receita disponível (AURE3), vale a regra anterior, com o motivo na tela. A, B e C ficaram de fora. Implementação: convergência em `5535891`, teto pela receita em `05781a3`, textos em `31fb06a`, regeneração em `c27f3ed`.
- **Por quê.** O salto de até 30% para 4,2% de um ano para o outro não tem explicação na economia da empresa, e a convergência gradual é a forma padrão de tratar essa fase; a regra é simétrica (sobe o valor de quem cresce abaixo do IPCA, como a PETR4). Um fluxo que cresce mais que a receita por cinco anos exige margem melhorando sem limite; o teto pela receita assume margem constante, premissa neutra e igual para todas, com dado que já está nos zips da CVM. A não remove a volatilidade e pede quatro anos a mais; qualquer valor de C é arbitrário; B não resolve o caso da MGLU3.
- **Efeito.** D + E reduz a mediana do FCD em 10,8% (53,6% nas 12 do teto) e deixa só 3 ações no teto; muda o sinal de 3 (CSAN3, EGIE3, VALE3).
- **Limitações.** A receita pode estar inflada por aquisições (AZZA3 cresce 49%); D não age quando o fluxo cresce menos que a receita; D + E não corrigem o fluxo-base inflado (ver seção 7).

### 6.2 Prêmio de risco

- **Problema.** O custo do capital próprio somava a Selic ao prêmio total de risco do Brasil de 7,47% (prêmio de mercado maduro de 4,23% + risco-país de 3,24%, tabela do Damodaran de 05/01/2026). Somar o prêmio-país a uma Selic que já embute o risco soberano é dupla contagem (conceitualmente CONFIRMADO; que a Selic equivalha a essa taxa é HIPÓTESE).
- **Alternativas.** **P1:** descartar o risco-país do prêmio de ações. **P2:** tirar o spread de default da taxa livre de risco e manter o prêmio total.
- **Decisão.** **P2:** custo do capital próprio = (Selic − spread de default de 2,13%) + Beta × prêmio total (`37b7b99`). O custo da dívida continua Selic + 2 p.p., por representar o custo real de captação em reais. Atualização do prêmio e do spread uma vez por ano, em janeiro, com conferência manual.
- **Por quê.** O próprio Damodaran orienta tirar o spread de default da taxa livre de risco em moeda local. A P1 só seria equivalente para Beta 1: o spread na Selic entra com peso 1 e o prêmio-país entra multiplicado pelo Beta. Efeito: −1,5 p.p. na mediana do WACC e +16% na do FCD.
- **Limitações.** Pressupõe que os 2,13% (rating Ba1) são o que está dentro da Selic (HIPÓTESE); a Selic é overnight, e o texto do Damodaran fala de títulos longos; o prêmio e o spread são constantes que precisam de atualização manual.

---

## 7. Fluxo-base: capital de giro e risco sacado

- **Problema.** O fluxo de um único ano pode vir inflado por capital de giro. Na MGLU3 o 6.01 de 2024 e 2025 inclui R$ 13 a 15 bi na linha "Fornecedores", compensados quase um a um no caixa de financiamento (6.03).
- **Alternativas.** **N1:** tirar o capital de giro do fluxo. **N2:** capital de giro médio. **N3:** margem média × receita. **N4:** reclassificar como operacional a saída líquida de convênio com fornecedores (risco sacado) que está em 6.03. **N5:** N2 + N4, com N3 nas cíclicas.
- **Decisão (04/10).** **N4 adotado, só para saídas**: as linhas de 6.03 identificadas pela descrição como convênio, risco sacado, *forfait* ou cessão de crédito por fornecedores são somadas ao caixa operacional, no ano de referência e no ano-base, na mesma demonstração. Quando um mesmo programa tem entrada e saída no mesmo ano (FLRY3, 2025), vale o saldo anual, só se for saída. O cartão do FCD mostra o valor reclassificado e o motivo. Implementação: `a3b78ee`, `5127245`, `a7d5f05`, `6b7d114` e `edf8e31`; dados regenerados em `5ee4248` e contagens corrigidas em `189fa45`. **N1 e N2 descartadas; N3 adiada** (seção 8).
- **Por quê.** N4 é correção de classificação com base em linhas explícitas, não um ajuste de nível: não depende de janela nem de critério de ciclo e só mexe nas ações com saída identificada (MGLU3, RENT3 e, de forma mínima, FLRY3). Na MGLU3 as linhas somam −R$ 12,3 bi (2024) e −R$ 13,5 bi (2025), 92% a 93% do aumento de fornecedores, e o FCD vai de R$ 102,16 para −R$ 1,14. N1 superestima quem cresce (eleva o FCD em 47%, mediana, nas 29 ações que crescem 12% ao ano ou mais); N2 depende de janelas arbitrárias e move o FCD nos dois sentidos.
- **VIVA3 (decidido em 04/10).** As entradas de convênio (+R$ 48,2 mi em 2024 e +R$ 146,6 mi em 2025) **não** são ajustadas: na apresentação bruta, o pagamento ao fornecedor já está no caixa operacional como saída, então não há o que reclassificar. Ressalva: em 2024 o padrão não aparece, e a natureza das entradas fica como HIPÓTESE (`3b468ff`).
- **Natureza do convênio da MGLU3.** Fica como HIPÓTESE apoiada pelos números; não foi verificada nas notas explicativas.

---

## 8. Empresas cíclicas

- **Problema.** Nas cíclicas o crescimento medido entre dois anos reflete a posição desses anos no ciclo, e a convergência atenua, mas não corrige (VALE3: 2020 perto do pico e 2025 perto do vale; GGBR4: 2025 perto do vale). Normalizar o fluxo-base (método N3) é a resposta conceitual, mas a janela de 2019 a 2025 não cobre um ciclo completo.
- **Dados (CONFIRMADO).** Os zips da DFP existem desde 2010 e o layout é o mesmo em todos os anos (6.01.01, 6.01.02, 6.01.03, 6.02 e 6.03 em 100% das 751 DFC indiretas). 33 das 53 ações têm os 16 anos completos. O IFRS 16 faz o pagamento de arrendamento em 6.03 passar de 0,00% da receita (mediana, 2018) para 0,44% (2019).
- **Critério de cíclica: alternativas.** (a) setor da B3 sozinho (13 ações); (b) variabilidade da margem (nenhuma das três cíclicas de referência entra: VALE3 é a 41ª de 47); (c1) receita nominal em queda em pelo menos um terço dos anos (inclui B3SA3, POMO4 e VBBR3, que não são cíclicas de commodities); **(c2) setor da B3 e queda da receita em um terço dos anos**.
- **Decisão.** Critério **(c2)**, com a **CSAN3 fora da lista** (as reorganizações de 2013 e 2021 tornam a série não comparável). Lista: GGBR4, GOAU4, PETR3, PETR4, USIM5 e VALE3 (na prática, 4 companhias, porque GGBR4/GOAU4 e PETR3/PETR4 são o mesmo negócio). Método **M1** (margem média do fluxo do FCD × receita do ano de referência) com **G1** (CAGR da receita na janela, dentro da faixa de −20% a +30%), **janela de 2015 a 2025** e **ajuste do IFRS 16** nos anos até 2018, aplicado **só às cíclicas** da lista. **M3 com G2** (depreciação de 2025 como capex de manutenção e crescimento só da inflação) fica registrado como alternativa.
- **Por quê.** O (c2) separa as ações por causa econômica (setor de preço dado pelo mercado) mais um sinal observado (queda da receita), e não pela distância ao preço. Não deve valer para todas as 53: a variação mediana vai de −30% a +36%, com P10 a P90 de −91% a +343%. A janela de 2015 a 2025 cobre cerca de 1,5 ciclo, mais perto de um ciclo completo que os sete anos posteriores ao IFRS 16 e com menos lacunas que 2010 a 2025.
- **Efeito esperado.** VALE3 de R$ 5,40 para R$ 45 a R$ 101, GGBR4 de R$ 0,14 para R$ 14 a R$ 24 e PETR4 de R$ 44,55 para R$ 64 a R$ 128, conforme janela e método.
- **Situação.** **Não implementada.** A implementação foi adiada para a migração para um banco de dados (seção 9). Até lá, `docs/limitacoes-conhecidas.md` traz a faixa de valores normalizados de VALE3, GGBR4 e PETR4 e diz que a sensibilidade à janela é a principal limitação (`4b2a186`).
- **Viabilidade (CONFIRMADO).** Ler 16 anos por empresa em lote leva cerca de 31 s para as 53 ações, contra cerca de 85 minutos se cada empresa-ano reabrir o zip (como hoje). Os zips de 2010 a 2025 somam 175,1 MB (+108 MB sobre o cache do workflow, longe do limite de 10 GB). A série pré-calculada ocupa 63 KB (751 linhas).

---

## 9. Em aberto

O que foi decidido e ainda não foi implementado, ou que ficou sem decisão:

| Assunto | Situação | Depende de |
|---|---|---|
| **Normalização das cíclicas** | Decidida (seção 8): M1 com G1, janela de 2015 a 2025, ajuste do IFRS 16, só VALE3, GGBR4, GOAU4, PETR3, PETR4 e USIM5. Sem implementação; hoje a limitação está documentada | Série histórica de 2010 a 2025 por empresa, gravada pela rodada do screener (migração para o banco de dados), para a página ler sem abrir os zips |
| **Arrendamento nos pesos do WACC** | Fora dos pesos enquanto eles forem contábeis (seção 4.1). Onde o arrendamento já está na dívida (PETR4, CSAN3), há uma pequena dupla contagem dos juros | Pesos a valor de mercado |
| **Pesos do WACC a valor de mercado** | Limitação do P09: os pesos são contábeis (dívida líquida ÷ patrimônio total) | Decisão própria, junto com o arrendamento |
| **Taxa livre de risco** | O prêmio usa a Selic menos o spread de default (seção 6.2). Falta investigar se a taxa livre de risco deveria ser a de um título de 10 anos em reais, e a moeda do prêmio (dólar ou real) | Investigação própria |
| **Atualização do prêmio e do spread** | Constantes fixas, atualizadas uma vez por ano, em janeiro, com conferência manual | Rotina manual |
| **Simulador com prazo (opção A)** | Evolução opcional, com prazo e crescimento escolhidos pelo usuário (seção 2) | Decisão de produto |
| **Capex de manutenção e de expansão** | Separação cogitada pela conta de depreciação e amortização; o código da subconta não é fixo entre empresas | Investigação própria |
| **Hipóteses não verificadas** | Natureza do convênio da MGLU3 e das entradas da VIVA3 (seção 7); as causas dos saltos de receita da CSAN3, TIMS3 e SUZB3; que a regra de montagem da dívida do Fundamentus valha para as 76 ações | Leitura das notas explicativas |
