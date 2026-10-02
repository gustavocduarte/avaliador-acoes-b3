# Investigação P03 e P04 (com P09/P10 e P11) — 2026-10-02

Investigação só de leitura sobre a auditoria `docs/auditoria-tecnica-2026-09-27.md`.
Nenhum arquivo de código, teste ou configuração foi alterado e nada foi commitado;
este relatório é o único arquivo novo.

**Convenções.** Toda afirmação sobre o código traz `arquivo:linha`. **CONFIRMADO** =
lido no código ou medido nos dados. **HIPÓTESE** = plausível, não verificada.
Valores de preço, `screener.csv` e Selic/IPCA são os de 29/09/2026 (Selic meta 13,75%,
IPCA 12m 4,2235%), tal como estão no repositório.

**Como foi feito.** Scripts em `%TEMP%\investigacao_p03_p04` (fora do repositório).
Lidos só para leitura: `data/processed/screener.csv`, `data/raw/cvm/dfp_cia_aberta_{2020,2024,2025}.zip`,
`data/raw/fundamentus/*.json`, `data/raw/b3/catalogo_emissores.csv`,
`data/raw/precos/*_dividendos.csv`, `data/raw/bcb/ultimo_macro.json`.
**Baixado:** `dfp_cia_aberta_2022.zip` (13,4 MB) da CVM, salvo em
`%TEMP%\investigacao_p03_p04\cvm\` (os anos de 2021 e 2023 saem da coluna PENÚLTIMO dos
zips de 2022 e 2024; 2019 sai do PENÚLTIMO do zip de 2020). Nada foi gravado em `data/`.

---

## 1. Resumo executivo

1. **P03 CONFIRMADO.** O Simulador trata o valor justo de hoje como preço em 5 anos
   (`main.py:1895`, `carteira.py:157-159`) e deflaciona esse valor pelo IPCA
   (`carteira.py:187`). No código o IPCA é descontado uma vez; o problema é conceitual:
   o valor justo já está em reais de hoje. Exemplo LREN3, cenário base: o Simulador mostra
   "ganho real" de R$ 4.132 sobre R$ 10.000, enquanto o mesmo valor justo, com o valor
   crescendo à inflação, dá R$ 7.379 em reais de hoje (+73,8%).
2. **Recomendação P03: opção B** (potencial sem prazo, sem taxa anual nem ganho real). A
   opção A fica como evolução opcional; a C não é recomendada agora.
3. **P04 CONFIRMADO.** O fluxo é `6.01 + 6.02` do último ano (`cvm.py:374`), dois pontos para
   o crescimento (`cvm.py:553-560`). Mistura aplicações financeiras, venda de participações
   e capex; os juros pagos ficam em 6.01 em 30 de 64 empresas e em 6.03 em 24; o arrendamento
   (IFRS 16) fica em 6.03 em 51 de 64.
4. **Capex por descrição:** 63 de 64 empresas não financeiras (98,4%) em 2025 e 63 de 63 em
   2020. As regras foram ajustadas duas vezes sobre os mesmos dados (89,1% na primeira
   versão), então o número é **dentro da amostra**, não de generalização.
5. **CSAN3:** o 6.02 de 2025 é −R$ 76 mi porque o capex (−R$ 8.460 mi) foi anulado por
   +R$ 8.945 mi de venda de investimentos. O FCD de R$ 32,06 sobre preço de R$ 3,72 vem disso.
6. **FCD em 8 empresas** (atual → só capex → capex + arrendamento + juros): a definição
   muda o resultado muito para PETR4 (48,26 → 26,55 → −10,13), KLBN11 (101,95 → 78,09 → 38,65)
   e RADL3 (2,53 → 2,56 → 0,24); pouco para WEGE3 (5,31 → 6,62 → 6,94) e MGLU3.
7. **Achado novo (bug de dado):** TIMS3 tem a DFC **consolidada zerada** na CVM em 2024 e 2025
   e o app a usa (`cvm.py:442-446`): FCF = 0 e FCD de R$ 0,79. Com a demonstração individual
   seria R$ 57,67.
8. **P09/P10:** 16 das 70 ações com FCD têm FCD acima de 3× o preço (7) ou abaixo de −1× (9);
   30 têm FCD negativo.
9. **P11:** a coluna "Desconto" é potencial de valorização (valor ÷ preço − 1); proposta de
   vocabulário "Potencial" na seção 6.
10. Histórico do Git: nenhum PDF jamais foi commitado.

---

## 2. Histórico do Git (PDFs)

CONFIRMADO, só leitura. `git log --all --oneline -- "docs/*.pdf"` não devolve nada. A busca
por qualquer `*.pdf` em todos os commits (nome e data) também não achou nenhum, e
`git ls-files "*.pdf"` está vazio. Só existem `master` e `origin/master` (sem outras
branches nem tags) e o stash está vazio. Não verifiquei objetos soltos nem o reflog, só as
referências. Nada foi removido nem reescrito. Os dois PDFs pessoais já saíram de `docs/`.

---

## 3. P03 — Simulador

### 3.1 O cálculo hoje (CONFIRMADO)

1. **Origem do valor justo.** O screener grava por ação `graham_valor_justo`, `bazin_preco_teto`,
   `fcd_valor_justo` e `valor_combinado` (`screener.py:425-441`, `COLUNAS_RESULTADO` em
   `screener.py:144`). O combinado é a média simples dos métodos aplicáveis
   (`modelos/combinado.py:65`).
2. **Cenários por ação** (`carteira.py:41-62`): pessimista = menor valor entre os métodos
   aplicáveis, otimista = maior, base = `valor_combinado`.
3. **De valor a "retorno"** (`carteira.py:107-114`): `retorno% = (valor_do_cenário ÷ preço_atual − 1) × 100`,
   com piso em −100% (`carteira.py:110-112`, a correção da perda > 100%); `projeção = investido × (1 + retorno/100)`.
   Nenhum prazo aparece até aqui: é apenas potencial.
4. **O "prazo".** `n_anos = HORIZONTE_PROJECAO_FCD_ANOS` (`main.py:1895`, valor 5 em
   `config.py:537`), o horizonte de projeção explícita do FCD, sem relação com o tempo que o
   mercado levaria para convergir.
5. **Taxa anual.** `valor_por_cenario` = soma das projeções (`main.py:1898-1902`) e
   `CAGR = (valor_por_cenario ÷ soma_investida_com_cenario)^(1/5) − 1`
   (`main.py:1909-1912`, `carteira.py:157-159`).
6. **Curvas** (`main.py:2019-2020` composta, `main.py:2042-2043` linear, `main.py:2078-2079` inflação
   pelo IPCA 12m composto 5 anos) e **"ganho real"** (`main.py:2130-2134` → `carteira.py:187-191`):
   `valor_destino_real = valor_destino ÷ (1 + IPCA)^5` e `ganho_real = valor_destino_real − investido`.
7. **Onde a inflação é descontada.** No código, **uma vez** (`carteira.py:187`); a curva de
   inflação (`main.py:2078`) é só linha de referência. O "duas vezes" da auditoria é
   conceitual: o valor justo já está em reais de hoje (valor presente), e deflacioná-lo trata
   um valor de hoje como se fosse um preço futuro nominal. Dividendos não entram em nenhuma
   parte do Simulador (`carteira.py` inteiro e `main.py:1895-2140`).
8. **Textos de tela hoje:** `main.py:1937-1939` ("podem valer entre X (pessimista) e Y (otimista) em 5
   anos"), `main.py:1949-1958` ("equivale a X% ao ano"), `main.py:2118` ("Ganho nominal vs. real
   (descontado o IPCA) em 5 anos"), colunas `main.py:1847-1854`.

### 3.2 Termos nominais/reais e "valor de hoje" (CONFIRMADO)

| Método | Fórmula | Natureza |
|---|---|---|
| Graham | `√(22,5 × LPA × VPA)` (`modelos/graham.py:42`, `config.py:422`); LPA e VPA vêm do Fundamentus (`config.py:223-224`) | R$ correntes (nominal), balanço recente: valor de hoje |
| Bazin | dividendos dos últimos 12 meses ÷ 6% (`modelos/bazin.py:145`, `config.py:431`) | R$ correntes, **preço teto** de hoje; não é estimativa de valor (o app já diz isso em `main.py:1977-1980`) |
| FCD | fluxo projetado descontado pelo WACC nominal, menos dívida líquida (`modelos/fcd.py:256-276`) | nominal, valor presente (confirmado no item 7) |
| Combinado | média simples (`modelos/combinado.py:65`) | mistura os três, valor de hoje |

Nenhum dos três é um preço futuro. O Simulador usa os três como se fossem o preço em 5 anos.

### 3.3 Exemplo numérico (2 ações reais, R$ 10.000 investidos, N = 5, g = IPCA 4,2235%)

Dados de `screener.csv`; dividend yield de `data/raw/precos/*_dividendos.csv` (últimos 12 meses).
**LREN3** (preço 11,35; Graham 18,52; Bazin 15,34; FCD 25,31; combinado 19,72; yield 8,11%) e
**VALE3** (preço 69,61; Graham 48,29; Bazin 93,54; FCD −8,53; combinado 44,43; yield 8,06%).

| Ação / cenário | Hoje (Simulador) | A: prazo, VJ cresce | B: sem prazo | C: retorno total |
|---|---|---|---|---|
| LREN3 pessimista (VJ 15,34) | R$ 13.516 (+35,2%); 6,21% a.a.; "ganho real" +R$ 991 | R$ 16.622 em 5 anos; 10,70% a.a.; em R$ de hoje R$ 13.516 | potencial +35,2%; R$ 13.516 | 18,81% a.a. (real 13,99%) |
| LREN3 base (VJ 19,72) | R$ 17.379 (+73,8%); 11,69% a.a.; "ganho real" +R$ 4.132 | R$ 21.372; 16,40% a.a.; em R$ de hoje R$ 17.379 (+73,8%) | potencial +73,8%; R$ 17.379 | 24,51% a.a. (real 19,47%) |
| LREN3 otimista (VJ 25,31) | R$ 22.303 (+123,0%); 17,40% a.a.; "ganho real" +R$ 8.136 | R$ 27.427; 22,36% a.a.; em R$ de hoje R$ 22.303 | potencial +123,0%; R$ 22.303 | 30,47% a.a. (real 25,18%) |
| VALE3 pessimista (VJ −8,53) | R$ 0 (−100%, piso); CAGR n/d; ganho real −R$ 10.000 | R$ 0; n/d | potencial −100%; R$ 0 | n/d (perda total) |
| VALE3 base (VJ 44,43) | R$ 6.383 (−36,2%); −8,59% a.a.; "ganho real" −R$ 4.809 | R$ 7.850; −4,73% a.a.; em R$ de hoje R$ 6.383 (−36,2%) | potencial −36,2%; R$ 6.383 | +3,34% a.a. (real −0,85%) |
| VALE3 otimista (VJ 93,54) | R$ 13.438 (+34,4%); 6,09% a.a.; "ganho real" +R$ 927 | R$ 16.526; 10,57% a.a.; em R$ de hoje R$ 13.438 | potencial +34,4%; R$ 13.438 | +18,63% a.a. (real 13,82%) |

Leitura: com valor justo crescendo à inflação, a opção A em reais de hoje é igual à B; o
Simulador de hoje subestima o ganho real (LREN3 base: +R$ 4.132 contra +R$ 7.379) por
deflacionar um valor que já é de hoje e por ignorar o crescimento do próprio valor justo.
A opção C soma dividendos (que podem incluir proventos extraordinários) e fica
bem mais alta, o que ilustra a fragilidade de somar premissas sobre insumos já frágeis.

### 3.4 Três opções

**A) Convergência com prazo.** O preço converge ao valor justo em N anos; o valor justo cresce no período; a inflação é descontada uma vez, de forma explícita.
- Fórmulas (VJ = valor justo do cenário, P = preço, I = investido, g = crescimento do VJ, π = IPCA):
  `VJ_N = max(VJ, 0) × (1 + g)^N`; valor em N anos `= I × VJ_N ÷ P`; taxa nominal `= (VJ_N ÷ P)^(1/N) − 1`;
  valor em R$ de hoje `= valor_N ÷ (1 + π)^N`. Com g = π, o valor em R$ de hoje é `I × VJ ÷ P`.
- Textos de tela: subtítulo "Se o preço convergir ao valor justo em N anos"; seletor "Prazo até a convergência (anos)"
  (tooltip: "Premissa sua, não uma previsão: em quantos anos o preço chegaria ao valor justo."); seletor "Crescimento do valor
  justo ao ano" (tooltip: "O valor justo de hoje é corrigido por esta taxa até o prazo escolhido; padrão: IPCA dos últimos 12 meses.
  Zero deixa o valor justo parado em reais de hoje."); colunas "Valor em N anos (R$ correntes)", "Valor em R$ de hoje",
  "Taxa anual nominal", "Taxa anual real" (tooltip: "(1 + nominal) ÷ (1 + IPCA) − 1: a inflação é descontada uma única vez.").
  Frase-resumo: "R$ X investidos hoje podem valer entre R$ A (pessimista) e R$ B (otimista) em N anos, em reais correntes,
  se os preços convergirem aos valores justos de hoje corrigidos por 4,2% ao ano. Não inclui dividendos."
- Testes existentes que mudariam: `tests/test_carteira.py:345-380` (4 testes de `calcular_ganho_nominal_vs_real`, trocados por testes da
  nova função), `tests/test_app_main.py:1829` (`test_projecao_carteira_usa_base_com_cenario_nao_a_base_total`, que espia
  `calcular_ganho_nominal_vs_real` e as curvas), e os textos "Com juros compostos"/"ao ano" em `test_app_main.py`. Os 5 testes de CAGR
  (`test_carteira.py:312-344`) e os de curvas (`test_graficos.py:174-250`) continuam.
- Complexidade: **média** (parâmetros novos na tela, nova função, reajuste de testes e gráficos).

**B) Sem prazo.** Só potencial e valor da carteira se os preços convergissem.
- Fórmulas: `potencial = max(VJ, 0) ÷ P − 1` (−100% no piso, já em `carteira.py:110-112`); valor ao convergir `= I × max(VJ, 0) ÷ P`.
- Textos de tela: subtítulo "Potencial de valorização da carteira"; legenda "Quanto a carteira valeria se o preço de cada ação
  chegasse ao valor justo do cenário — sem prazo, sem dividendos e sem inflação. Não é previsão."; colunas "Potencial (pessimista/base/otimista)"
  (tooltip: "Valor justo do cenário ÷ preço atual − 1. Mostra o quanto o preço está abaixo (+) ou acima (−) do valor justo; não é retorno esperado.")
  e "Valor ao convergir (pessimista/base/otimista)"; frase-resumo: "R$ X investidos hoje equivaleriam a entre R$ A (pessimista) e R$ B (otimista) se
  os preços chegassem aos valores justos calculados, sem prazo definido." O aviso do piso continua ("valor justo ≤ 0 conta como perda total").
  Saem o CAGR "ao ano", as curvas e a tabela "Ganho real (IPCA)".
- Testes que mudariam: `test_carteira.py:312-344` e `:345-380` (CAGR e ganho real, se as funções saírem), `test_graficos.py:174-250`
  (curvas, se saírem do app), `test_app_main.py:1829` (reescrito) e os textos em `test_app_main.py`. `test_carteira.py:100-195`
  (cenários, piso, projeção) ficam, salvo renomear colunas.
- Complexidade: **baixa** (remove blocos de tela e renomeia).

**C) Retorno total estimado.** Dividend yield + crescimento + convergência amortizada em N anos, como estimativa.
- Fórmula: `r ≈ yield12m + (1 + g) × (max(VJ, 0) ÷ P)^(1/N) − 1`; valor em N anos `= I × (1 + r)^N`; real `= (1 + r) ÷ (1 + π) − 1`.
  Com VJ ≤ 0 não há raiz: o caso precisa de regra própria (perda total do capital; dividendos até lá ficam de fora).
- Textos de tela: subtítulo "Retorno total estimado ao ano"; coluna "Retorno estimado (a.a.)" (tooltip: "Soma de três partes: dividendos dos últimos 12 meses
  ÷ preço, crescimento do valor justo (IPCA) e a parcela anual da distância até o valor justo. Estimativa, não previsão; dividendos extraordinários
  inflam o resultado."); frase-resumo: "Se os dividendos se mantiverem e o preço convergir ao valor justo em N anos, a estimativa é de x% a y% ao ano (nominal)."
- Testes que mudariam: os mesmos da A, mais `tests/test_screener.py` (nova coluna de dividend yield no `COLUNAS_RESULTADO`, `screener.py:144`) e regeneração do `screener.csv`.
- Complexidade: **alta** (nova coluna no screener e regeneração do CSV, nova regra para VJ ≤ 0, premissa de yield constante).

### 3.5 Recomendação (P03)

**Opção B agora.** Razões: (i) o Simulador mistura métodos com fragilidades diferentes: o FCD sai extremo em 16 de 70 ações
(seção 5) e o Bazin é um preço teto, não uma estimativa de valor (`main.py:1977-1980`); acrescentar prazo, crescimento e
dividendos (A e C) multiplica premissas sobre insumos frágeis e dá precisão falsa. (ii) A opção B remove exatamente os três
problemas confirmados (prazo arbitrário, inflação sobre valor de hoje, dividendos ausentes) sem inventar um substituto.
(iii) Menor complexidade e testes. A pode vir depois como evolução, com prazo e crescimento escolhidos pelo usuário; C não é
recomendada: depende de yield constante (proventos extraordinários) e de uma regra à parte para VJ ≤ 0.

**A correção da perda > 100% continua válida** em B (`carteira.py:110-112` não muda) e em A (o piso é aplicado ao valor justo antes do
crescimento, `max(VJ, 0)`); na C exige regra própria para VJ ≤ 0.

---

## 4. P04 — Fluxo de caixa do FCD

### 4.1 Como o fluxo é calculado (CONFIRMADO)

- **Contas:** `CODIGO_CFO_CVM = "6.01"` e `CODIGO_CFI_CVM = "6.02"` (`config.py:332-333`), lidas pelo código exato da conta
  (`ingest/cvm.py:338-344`, `:347-367`); `FCF = 6.01 + 6.02` (`cvm.py:373-374`). Não há uso de subcontas nem de descrição.
- **DFC_MD e/ou DFC_MI:** o código tenta primeiro o método indireto (MI), depois o direto (MD), e em cada um a demonstração consolidada
  antes da individual, e **usa a primeira combinação que tenha qualquer linha** (`cvm.py:440-446`).
- **Anos e agregação:** dois pontos, o ano mais recente e o de 5 anos antes (`cvm.py:553-560`, `ANOS_HISTORICO_CRESCIMENTO_FCD = 5` em
  `config.py:538`). **Último ano**, não média; o crescimento é o CAGR entre os dois (`modelos/fcd.py:136-144`), limitado a −20% e +30%
  (`config.py:609-610`); a perpetuidade parte do FCF projetado do ano 5 (`fcd.py:262`).
- **Sinais:** soma algébrica; `VL_CONTA × escala` (`cvm.py:251-263`); 6.02 normalmente negativo.
- **Bancos:** FCD não aplicável para segmento "Bancos" (`fcd.py:212-217`, `config.py:573`: BBDC3, BBDC4, SANB11, BBAS3, ITUB4, BPAC11).
- **Seguradoras e outras financeiras:** **não** são excluídas. No `screener.csv` o FCD é aplicado em BBSE3 (76,82), PSSA3 (29,66), CXSE3 (18,13),
  ITSA4 (21,92) e B3SA3 (4,07). O próprio `config.py:563-572` registra isso como "questão em aberto, limitação conhecida".

### 4.2 Coerência fluxo × taxa × dívida

O desconto é pelo WACC nominal (`fcd.py:237`) e a dívida líquida do Fundamentus é subtraída depois do valor presente
(`fcd.py:270-272`), a modelagem FCFF → WACC → menos dívida líquida. O fluxo `6.01 + 6.02` não é um FCFF. O próprio `config.py:470-472` admite
"não é FCFF nem FCFE". Inconsistências:

1. **Juros pagos dentro do caixa operacional (CONFIRMADO).** Em 30 das 64 empresas não financeiras os juros pagos estão em 6.01 (24 em 6.03, 4 nos dois,
   3 só em linha mista com principal; 3 não identificadas). Com juros dentro de 6.01, o fluxo é "depois de juros" (tipo FCFE); descontá-lo pelo
   WACC e depois subtrair a dívida líquida penaliza o custo da dívida duas vezes. Seis empresas mudam a localização entre anos (KLBN11: 6.01 em 2019-2020, 6.03
   desde 2023), o que torna a série do próprio fluxo atual heterogênea.
2. **6.02 mistura capex com tesouraria e participações (CONFIRMADO)** (CSAN3, seção 4.4). A dívida líquida do Fundamentus **provavelmente** abate
   as aplicações financeiras (**HIPÓTESE**, não verifiquei a composição do campo na página); se for assim, contá-las no fluxo e também na dívida é dupla contagem.
3. **Arrendamento (IFRS 16) (CONFIRMADO o local; HIPÓTESE a consequência).** O pagamento do principal está em 6.03 em 51 das 64 empresas (39 só 6.03, 12 com os juros em 6.01),
   portanto fora do FCF. Se a dívida líquida do Fundamentus **não** incluir o passivo de arrendamento (**HIPÓTESE**), o custo do aluguel some do valor.
4. **Datas (CONFIRMADO):** FCF de dezembro/2025 contra dívida líquida e número de ações de 30/06/2026 (`fcd.py:270-276`; já documentado como P15).
5. **Ano único e capital de giro (CONFIRMADO):** o fluxo perpetuado é o de um só ano; em MGLU3, 6.01 de 2025 (R$ 15,7 bi) vem de +R$ 14,7 bi na linha
   "Fornecedores" (6.01.02.08), variação de capital de giro, não de geração recorrente.
6. **Demonstração consolidada zerada (CONFIRMADO, achado novo).** `cvm.py:442-446` só pula uma demonstração se ela não tiver linhas; uma consolidada
   com todos os valores zero é aceita. TIMS3: consolidada (MI/con) tem 6.01 = 6.02 = 0 em 2024 e 2025 (e nos PENÚLTIMOS de 2019 e 2021), enquanto a individual tem
   6.01 de R$ 13.440 mi e 6.02 de −R$ 3.561 mi em 2025. Resultado: FCF 2025 = 0 e FCD de **R$ 0,79** no `screener.csv`; com a individual seria **R$ 57,67**
   (preço R$ 18,53).

### 4.3 Cobertura da conta de capex por descrição (CONFIRMADO, dentro da amostra)

Universo: 76 tickers; excluí 11 financeiros/seguradoras/holding financeira/bolsa (BBDC3, BBDC4, BBSE3, SANB11, ITSA4, BBAS3, ITUB4, PSSA3, CXSE3, BPAC11, B3SA3);
sobram **65 tickers = 64 empresas** (PETR3/PETR4 e outras classes dividem CNPJ). Regra: nas subcontas `6.02.*` (normalizadas sem acento e caixa), linha "forte" se a descrição cita imobilizado,
intangível, ativo fixo, capex, propriedade para investimento, ativo de contrato/contratual, concessão, ativo biológico, bens do ativo, obras ou infraestrutura; excluídas
"venda/alienação/baixa/recebimento/resgate/dividendos/títulos e valores mobiliários/empréstimos/financiamento", e participações/controladas/coligadas/combinação de negócios; linha
"fraca" = "aquisição/adições/compra de/investimentos em" sem esses termos. Se há linha pai e filha marcadas, vale a pai (sem dupla contagem).

| Medida | Resultado |
|---|---|
| Capex identificado, DFP 2025 (último) | **63 de 64 (98,4%)**; 1 só com linha fraca (IGTI11) |
| Capex identificado, DFP 2020 (ano-base do CAGR) | **63 de 63 (100%)**; AURE3 não tem DFC em 2019-2020 |
| Empresa-ano 2021-2025 | 315 de 320 identificados (98,4%); 5 "só fraco" (todos IGTI11) |
| Empresas com capex nos 5 anos | 63 de 64 |
| Primeira versão das regras (antes de duas correções) | 57 de 64 (89,1%) em 2025; as correções foram (1) "aplicação" deixou de excluir linhas que citam imobilizado e a palavra "ações" passou a ser buscada como palavra inteira ("aplicações" a continha), (2) "acréscimo/(redução)" e valor zero passaram a contar |

**Cuidado:** as regras foram ajustadas olhando estes mesmos dados; o número é dentro da amostra. Uma implementação precisa de testes com fixtures reais e de um teste de cobertura que
avise se a taxa cair.

**Casos que falharam (descrições de 6.02, 2025), IGTI11:** "Aquisições de Ativo Não Circulante" −R$ 1.104 mi (mistura imobilizado e propriedades
para investimento), "Venda de Ativo Permanente" +R$ 310 mi, "Aplicações Financeiras Mantidas para Negociação" +R$ 264 mi, "Dividendos Recebidos de Controladas" +R$ 1,6 mi, demais zeradas.
Sem a palavra "imobilizado/intangível/ativo fixo" a linha cai em "fraca".

**Casos ambíguos (2025):** 38 empresas têm mais de uma linha de capex (imobilizado e intangível separados, ex. WEGE3, SUZB3); 25 têm uma só linha agregada; 28 também têm linhas "fracas".
Exemplos: EGIE3 (R$ 1.752 mi de "Aplicação no imobilizado e no intangível" + R$ 844 mi de "Pagamento de parcelas de concessões (UBP)", direito de concessão que pode ou não ser capex);
CURY3 ("(Acréscimo) redução do imobilizado", valor líquido de vendas); ENGI11 (linhas de "linhas de transmissão" separadas); MOTV3 (linha forte com sinal positivo). Oito empresas têm capex
abaixo de 50% do |6.02| (ISAE4, ALOS3, TAEE11, CMIN3, PRIO3, SUZB3, VBBR3, TOTS3) e seis acima de 150% (MOTV3, EQTL3, MULT3, CSAN3, CYRE3, CPLE3), sinal de entradas grandes em 6.02 (vendas, resgates) ou de capex dentro de ativo de contrato.
BRAP4 e TIMS3 têm a linha de capex, mas zerada (holding; consolidada zerada). **Capex dentro de controladas** não aparece em 6.02 da controladora: não avaliado.

### 4.4 CSAN3, em números

6.02 de 2025 = −R$ 76 mi, composto por (R$ mi): "Adições ao imobilizado, intangível e ativos de contrato" **−8.460**; "Venda de investimentos, líquido de caixa cedido" **+8.945**;
"Venda (compra) de títulos e valores mobiliários" **+989**; "Aquisição de controladas" −616; "Pagamento de instrumentos financeiros derivativos" −1.130; demais pequenas.
Logo o FCF de 2025 (R$ 12.951 mi) inclui uma venda de participação de R$ 8,9 bi; sem ela, 6.01 − capex = R$ 4.567 mi. Em 2022 o 6.02 foi −R$ 20.609 mi, dos quais
−R$ 13.912 mi em "Títulos e valores mobiliários" (aplicação de caixa, não capex; capex de R$ 4.531 mi). Série (R$ mi, 6.02 total / capex): 2020 −2.341/1.053;
2021 +5.005/4.067; 2022 −20.609/4.531; 2023 −4.303/6.268; 2024 −4.488/7.835; 2025 −76/8.460.

### 4.5 Juros pagos e arrendamento (64 empresas, DFP 2025; levantamento por descrição)

| Item | Só 6.01 | Só 6.03 | 6.01 e 6.03 | Só linha mista (principal + juros) | Não identificado |
|---|---|---|---|---|---|
| Juros pagos (linha dedicada) | 30 | 24 | 4 | 3 | 3 (BRAP4, UGPA3*, BEEF3) |
| Arrendamento pago (principal e/ou juros) | n/d | 39 | 12 | n/d | 13 |

Notas: além das 64 acima, 4 empresas têm também uma linha mista de principal e juros (2 em 6.01 e 2 em 6.03); 3 delas são as "só linha mista" da tabela.
Arrendamento: "6.01 e 6.03" são os casos com juros de arrendamento em 6.01 e o principal em 6.03. *UGPA3 tem "Juros e Derivativos Pagos" em 6.03.03,
que a regra descartou por conter "derivativos". Descrições mais comuns de juros: "juros pagos", "pagamento de juros de empréstimos, financiamentos e debêntures", "pagamento de juros sobre empréstimos
e financiamentos", "encargos de dívidas e debêntures pagos", "amortizações de juros de financiamentos". De arrendamento: "pagamento de juros de arrendamento mercantil", "pagamentos de arrendamentos",
"pagamento de passivo(s) de arrendamento", "amortização de principal de arrendamento mercantil", "contraprestação de arrendamento". As 13 sem arrendamento incluem empresas que de fato não têm
(WEGE3, SBSP3, MULT3, EGIE3) e algumas em que a linha existe zerada (TIMS3). **Limitação do método:** é uma busca por texto, um limite inferior; vários resultados (VIVT3, UGPA3, MRVE3) misturam
juros de dívida e de arrendamento na mesma linha.

### 4.6 FCD em 8 empresas

Escolhas: CSAN3, SBSP3, PETR4, RADL3, KLBN11 (pedidas); **CPFE3** (elétrica integrada, não transmissora: capex bem identificado em 3 linhas, juros pagos em 6.01, o caso que testa o ajuste
pelos juros); **WEGE3** (controle bem-comportado: sem arrendamento, juros pequenos); **MGLU3** (varejo: arrendamento e o caso de FCD de R$ 226 citado no P10). A reprodução do FCD atual com a mesma função
(`calcular_valor_justo_fcd`, importada sem alteração) bate com o `screener.csv` ao centavo nas 8 (32,06; −26,74; 48,26; 2,53; 101,95; −6,94; 5,31; 225,66).

Definições: **atual** = 6.01 + 6.02. **alt1** = 6.01 − capex. **alt2** = 6.01 − capex − arrendamento pago em 6.03 + juros pagos em 6.01 × (1 − 34%) (arrendamento já em 6.01 não é subtraído de novo).
**alt3** (acrescentada por mim) = alt1 + juros pagos em 6.01 × (1 − 34%), sem subtrair arrendamento.

| Ticker | Preço | FCD atual | alt1 | alt2 | alt3 |
|---|---|---|---|---|---|
| CSAN3 | 3,72 | 32,06 | 30,03 | 15,22 | 30,03 |
| SBSP3 | 27,06 | −26,74 | −22,19 | −18,06 | −18,06 |
| PETR4 | 49,10 | 48,26 | 26,55 | −10,13 | 26,55 |
| RADL3 | 18,14 | 2,53 | 2,56 | 0,24 | 4,90 |
| KLBN11 | 18,27 | 101,95 | 78,09 | 38,65 | 48,43 |
| CPFE3 | 44,50 | −6,94 | −16,68 | −6,08 | −6,08 |
| WEGE3 | 50,29 | 5,31 | 6,62 | 6,94 | 6,94 |
| MGLU3 | 6,63 | 225,66 | 227,36 | 214,81 | 227,36 |

**Fluxo por ano (R$ mi)** — colunas: 6.01, 6.02, capex, juros em 6.01, juros em 6.03, arrendamento em 6.03; depois atual / alt1 / alt2. `n/d` = não identificado.

CSAN3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 2.808 | 686 | 820 | 0 | 631 | 9 | 3.494 | 1.988 | 1.979 |
| 2020 | 2.143 | −2.341 | 1.053 | 0 | 796 | 29 | −198 | 1.090 | 1.062 |
| 2021 | 5.222 | 5.005 | 4.067 | 0 | 1.916 | 564 | 10.227 | 1.155 | 591 |
| 2022 | 9.972 | −20.609 | 4.531 | 0 | 3.442 | 612 | −10.637 | 5.441 | 4.829 |
| 2023 | 10.276 | −4.303 | 6.268 | 0 | 3.552 | 727 | 5.973 | 4.008 | 3.282 |
| 2024 | 13.081 | −4.488 | 7.835 | 0 | 4.760 | 1.072 | 8.593 | 5.247 | 4.175 |
| 2025 | 13.027 | −76 | 8.460 | 0 | 4.732 | 1.173 | 12.951 | 4.567 | 3.394 |

SBSP3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 4.197 | −3.267 | 3.273 | 737 | 0 | 0 | 930 | 924 | 1.410 |
| 2020 | 4.978 | −6.769 | 3.342 | 627 | 0 | 0 | −1.790 | 1.636 | 2.050 |
| 2021 | 3.914 | −2.663 | 3.747 | 845 | 0 | 0 | 1.251 | 167 | 725 |
| 2022 | 3.968 | −2.878 | 3.625 | 1.505 | 0 | 0 | 1.089 | 343 | 1.336 |
| 2023 | 4.854 | −4.906 | 4.139 | 1.936 | 0 | 0 | −51 | 716 | 1.994 |
| 2024 | 7.405 | −9.976 | 8.031 | 1.977 | 0 | 0 | −2.571 | −626 | 679 |
| 2025 | 8.361 | −15.704 | 13.740 | 2.696 | 0 | 0 | −7.343 | −5.379 | −3.600 |

PETR4
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 101.766 | −7.952 | 34.010 | 0 | 17.623 | 20.660 | 93.814 | 67.756 | 47.096 |
| 2020 | 148.106 | −23.455 | 29.974 | 0 | 15.828 | 30.275 | 124.651 | 118.132 | 87.857 |
| 2021 | 203.126 | 11.073 | 34.134 | 0 | 12.155 | 31.400 | 214.199 | 168.992 | 137.592 |
| 2022 | 255.410 | −4.377 | 49.656 | 0 | 9.664 | 28.049 | 251.033 | 205.754 | 177.705 |
| 2023 | 215.696 | −39.495 | 60.315 | 0 | 9.900 | 31.335 | 176.201 | 155.381 | 124.046 |
| 2024 | 204.037 | −72.363 | 79.856 | 0 | 10.276 | 42.672 | 131.674 | 124.181 | 81.509 |
| 2025 | 200.333 | −86.114 | 108.714 | 0 | 10.311 | 52.437 | 114.219 | 91.619 | 39.182 |

RADL3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 749 | −3 | 287 | 62 | 0 | 778 | 746 | 462 | −275 |
| 2020 | 1.477 | −673 | 676 | 40 | 0 | 535 | 804 | 801 | 292 |
| 2021 | 1.557 | −886 | 856 | 65 | 0 | 678 | 671 | 701 | 67 |
| 2022 | 1.682 | −1.230 | 1.189 | 259 | 0 | 843 | 453 | 493 | −179 |
| 2023 | 1.785 | −1.307 | 1.305 | 329 | 0 | 823 | 478 | 481 | −125 |
| 2024 | 2.771 | −1.413 | 1.284 | 373 | 0 | 859 | 1.358 | 1.488 | 875 |
| 2025 | 2.431 | −1.406 | 1.403 | 470 | 0 | 921 | 1.025 | 1.028 | 417 |

KLBN11
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 2.953 | −2.553 | 1.769 | 1.185 | 0 | 102 | 400 | 1.184 | 1.864 |
| 2020 | 5.791 | −5.069 | 4.161 | 1.220 | 0 | 159 | 722 | 1.630 | 2.277 |
| 2021 | 4.891 | −3.676 | 2.904 | 0 | 0 | 243 | 1.215 | 1.987 | 1.744 |
| 2022 | 8.421 | −7.877 | 5.909 | 0 | 0 | 337 | 544 | 2.512 | 2.175 |
| 2023 | 6.745 | −3.145 | 3.459 | 0 | 1.891 | 534 | 3.600 | 3.286 | 2.753 |
| 2024 | 7.425 | −8.604 | 2.357 | 0 | 2.192 | 526 | −1.178 | 5.068 | 4.542 |
| 2025 | 6.396 | −1.882 | 1.762 | 0 | 2.116 | 497 | 4.514 | 4.634 | 4.137 |

CPFE3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 5.768 | −3.048 | 2.241 | 1.132 | 0 | 0 | 2.720 | 3.526 | 4.274 |
| 2020 | 6.361 | −3.124 | 2.671 | 761 | 0 | 0 | 3.238 | 3.691 | 4.193 |
| 2021 | 3.862 | −4.207 | 3.603 | 652 | 0 | 0 | −345 | 258 | 689 |
| 2022 | 8.980 | −6.259 | 5.187 | 1.463 | 0 | 0 | 2.721 | 3.793 | 4.759 |
| 2023 | 8.900 | −4.641 | 4.491 | 1.862 | 0 | 0 | 4.259 | 4.409 | 5.638 |
| 2024 | 6.789 | −5.531 | 5.075 | 2.143 | 0 | 0 | 1.258 | 1.714 | 3.129 |
| 2025 | 7.163 | −4.400 | 5.354 | 2.085 | 0 | 0 | 2.763 | 1.808 | 3.184 |

WEGE3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 1.908 | −60 | 524 | 0 | 68 | 0 | 1.848 | 1.383 | 1.383 |
| 2020 | 3.930 | 207 | 559 | 0 | 12 | 0 | 4.137 | 3.371 | 3.371 |
| 2021 | 1.056 | −684 | 847 | 0 | 53 | 0 | 372 | 209 | 209 |
| 2022 | 2.983 | −1.346 | 1.174 | 0 | 56 | 0 | 1.637 | 1.809 | 1.809 |
| 2023 | 7.022 | −1.714 | 1.659 | 128 | 0 | 0 | 5.308 | 5.363 | 5.447 |
| 2024 | 7.252 | −4.095 | 1.850 | 160 | 0 | 0 | 3.158 | 5.402 | 5.508 |
| 2025 | 6.451 | −2.911 | 2.691 | 177 | 0 | 0 | 3.540 | 3.760 | 3.877 |

MGLU3
| Ano | 6.01 | 6.02 | capex | juros 6.01 | juros 6.03 | arrend. 6.03 | atual | alt1 | alt2 |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | −3.330 | −929 | 522 | 0 | 52 | 367 | −4.258 | −3.851 | −4.218 |
| 2020 | 2.604 | −651 | 544 | 0 | 1 | 488 | 1.952 | 2.060 | 1.572 |
| 2021 | −7.571 | −1.317 | 1.164 | 0 | 131 | 618 | −8.888 | −8.735 | −9.354 |
| 2022 | 3.064 | −1.044 | 695 | 0 | 616 | 809 | 2.021 | 2.369 | 1.560 |
| 2023 | 15.903 | −148 | 641 | 0 | 743 | 841 | 15.755 | 15.262 | 14.421 |
| 2024 | 15.835 | −1.291 | 730 | 0 | 1.133 | 823 | 14.545 | 15.106 | 14.283 |
| 2025 | 15.719 | −1.001 | 892 | 0 | 784 | 804 | 14.719 | 14.828 | 14.024 |

Nota: PETR4 também tem R$ 3.407 mi de arrendamento em 6.01 em 2025 (juros de arrendamento), que já reduz o 6.01 e não é subtraído de novo.
Em RADL3 há arrendamento em 6.01 (R$ 479 mi em 2025) pela mesma razão. Mesma metodologia de cálculo em todos os anos; os anos 2021 e 2023 vêm do PENÚLTIMO do zip seguinte (valores podem ter sido reapresentados).

**Leitura por empresa.**
- **CSAN3.** O FCD "atual" (32,06) usa crescimento = IPCA, porque o fluxo de 2020 é negativo (−198); com capex, a base de 2020 passa a ser positiva e o crescimento sobe ao teto de 30% (alt1). Valores quase iguais por coincidência (32,06 e 30,03), mas por razões opostas: no atual o fluxo de 2025 está inflado em R$ 8,9 bi pela venda de participação; no alt1 é o crescimento que compensa. Ambos são muito sensíveis ao par de anos.
- **SBSP3.** Negativo em todas as definições (−26,74, −22,19, −18,06): o capex de 2025 (R$ 13,7 bi) é investimento de crescimento e o modelo perpetua um fluxo negativo. A definição do fluxo não corrige isso; é uma limitação do modelo para empresas em fase de investimento (P10).
- **PETR4.** O capex de 2025 (R$ 108,7 bi) é maior que o 6.02 inteiro (R$ 86,1 bi): há entradas em 6.02. O arrendamento pago (R$ 52,4 bi em 6.03) derruba o alt2 a −10,13 (crescimento −14,9% ao ano sobre base de 2020).
- **RADL3.** O arrendamento (R$ 921 mi em 2025) praticamente iguala o fluxo (R$ 1.025 mi): FCD cai de 2,53 para 0,24. É o caso de varejo com IFRS 16 do P04.
- **KLBN11.** 101,95 → 78,09 → 38,65. O alt1 e alt2 mudam o crescimento (30% → 23% → 13%) porque 2020 tinha 6.02 de −R$ 5,1 bi com capex de R$ 4,2 bi, e porque os juros mudam de 6.01 (2019-2020) para 6.03 (2023-2025).
- **CPFE3.** Negativo em todas; o alt1 é pior (−16,68) por trocar 6.02 (R$ 4,4 bi) por capex maior (R$ 5,4 bi) com juros em 6.01.
- **WEGE3 (controle).** Estável: 5,31 / 6,62 / 6,94. Mesmo bem-comportada, o FCD fica ~87% abaixo do preço (R$ 50,29): o modelo é conservador, o mercado paga por crescimento.
- **MGLU3.** 225,66 / 227,36 / 214,81: a definição do fluxo não importa; o resultado vem de 6.01 de R$ 15,7 bi (variação de fornecedores), e o crescimento em 30% (teto) por 5 anos. Aqui o problema é P10, não P04.

### 4.7 Recomendação (P04)

**Adotar a definição alt3 (6.01 − capex + juros pagos em 6.01 × (1 − 34%)), por etapas, sem subtrair o arrendamento ainda.**
- **Por que não alt1 sozinha:** corrige 6.02 mas deixa os juros de 30 empresas dentro do fluxo (inconsistência 1 da seção 4.2).
- **Por que não alt2 agora:** depende de uma hipótese não verificada (se a dívida líquida do Fundamentus inclui o passivo de arrendamento). Se incluir, subtrair o pagamento de arrendamento é dupla contagem; o impacto é grande (PETR4 −10,13; RADL3 0,24). Verificar a composição do campo "Dív. Líquida" na página antes de decidir.
- **Efeito esperado:** corrige o caso CSAN3 (capex em vez de 6.02), KLBN11 (de 101,95 para 48,43) e RADL3 (de 2,53 para 4,90); não conserta SBSP3, CPFE3 nem MGLU3 (problemas de modelo, P10).
- **Fallback quando o capex não é identificado:** manter `6.01 + 6.02` e marcar a ação com "Fluxo de caixa aproximado: investimento total (6.02), sem separar capex". No screener, uma coluna `base_fluxo` com valores `capex_identificado` ou `6.01+6.02`; no cartão do FCD, uma legenda. Se os juros não forem localizados, não somar nada e marcar "juros não identificados".
- **Antes de implementar:** (a) tratar demonstração zerada (TIMS3): pular para a próxima demonstração quando 6.01 e 6.02 forem ambos zero, ou sinalizar; (b) fixtures reais de ~10 DFCs e um teste de cobertura; (c) lembrar que a identificação é por texto livre.

---

## 5. P09/P10 — taxa de desconto e crescimento (item 7)

Como o WACC e o crescimento são montados (CONFIRMADO; `modelos/fcd.py`, constantes em `config.py`):

- **Ke** = Selic meta (série 432 do BCB, % a.a. nominal) + Beta × prêmio de risco 7,47% (`fcd.py:97-99`, `config.py:626`, Damodaran, conferido em 14/09/2026 e fixo no código).
- **Beta:** `calcular_beta` (`empresa/comportamento.py:45-76`), `PERIODO_BETA = "1y"` (`config.py:83`), retornos diários contra o Ibovespa, sem ajuste; sem exigência de número mínimo de observações além de 2 retornos pareados (`comportamento.py:68`); fallback 1,0 (`config.py:618`).
- **Kd** = (Selic + 2 p.p.) × (1 − 34%) (`fcd.py:102-104`, `config.py:635`, `:640`).
- **Pesos:** Dívida Líquida ÷ Patrimônio contábil do Fundamentus; ausente ou ≤ 0 = 100% capital próprio (`fcd.py:107-116`).
- **Nominal.** Selic nominal, FCF em reais correntes, perpetuidade pelo IPCA.
- **Crescimento explícito:** CAGR entre dois anos, limitado a −20% e +30% (`fcd.py:136-144`, `config.py:609-610`); sem base positiva, IPCA (`fcd.py:248-252`).
- **Perpetuidade:** `g = min(IPCA 12m, WACC − 1 p.p.)` (`fcd.py:147-151`, `config.py:663`); a trava é só contra o WACC, não contra o PIB nem contra o crescimento explícito.
- **Horizonte:** 5 anos (`config.py:537`), desconto no fim de cada ano, valor terminal sobre o FCF do ano 5 (`fcd.py:256-263`).

### Resultado do ajuste (b): FCD extremo

Entre as **70 ações com FCD aplicável** (76 menos os 6 bancos): **7** têm FCD acima de 3× o preço, **9** abaixo de −1× o preço: **16 (22,9% das 70; 21,1% das 76)**. **30** têm FCD negativo. Nas 4 que só têm FCD (HAPV3, CSAN3, AURE3, CSNA3) o valor combinado é o próprio FCD. Nas 12 restantes:

| Ticker | Preço | FCD | FCD ÷ preço | Métodos | Combinado | Combinado sem FCD | Deslocamento (R$) | Potencial com FCD → sem FCD |
|---|---|---|---|---|---|---|---|---|
| MGLU3 | 6,63 | 225,66 | 34,0 | graham, fcd | 115,81 | 5,97 | +109,84 | +1.646,8% → −10,0% |
| BEEF3 | 3,92 | 37,05 | 9,5 | graham, fcd | 20,55 | 4,04 | +16,50 | +424,1% → +3,2% |
| POMO4 | 4,13 | 15,92 | 3,9 | graham, bazin, fcd | 13,29 | 11,98 | +1,31 | +221,9% → +190,1% |
| KLBN11 | 18,27 | 101,95 | 5,6 | graham, bazin, fcd | 43,36 | 14,06 | +29,30 | +137,3% → −23,0% |
| ALOS3 | 28,77 | 88,95 | 3,1 | graham, bazin, fcd | 58,94 | 43,94 | +15,00 | +104,9% → +52,7% |
| CMIG4 | 10,96 | −14,27 | −1,3 | graham, bazin, fcd | 9,16 | 20,87 | −11,71 | −16,5% → +90,4% |
| ISAE4 | 26,71 | −32,83 | −1,2 | graham, fcd | 10,24 | 53,32 | −43,08 | −61,7% → +99,6% |
| ENGI11 | 51,88 | −68,45 | −1,3 | graham, bazin, fcd | 0,57 | 35,08 | −34,51 | −98,9% → −32,4% |
| MBRF3 | 16,85 | −18,66 | −1,1 | graham, fcd | −5,85 | 6,95 | −12,80 | −134,7% → −58,8% |
| BRAV3 | 18,23 | −34,79 | −1,9 | graham, fcd | −13,17 | 8,45 | −21,62 | −172,2% → −53,7% |
| PRIO3 | 61,60 | −147,53 | −2,4 | graham, fcd | −45,38 | 56,78 | −102,15 | −173,7% → −7,8% |
| VAMO3 | 4,00 | −16,81 | −4,2 | graham, bazin, fcd | −3,50 | 3,15 | −6,66 | −187,5% → −21,1% |

Nas 4 ações só com FCD: HAPV3 (FCD 75,07, potencial +1.095%), CSAN3 (32,06, +762%), AURE3 (−18,57, −246%), CSNA3 (−85,67, −1.687%). Nas 12 com outro método, o FCD desloca o combinado em média −R$ 5,05 (mediana −R$ 9,18) e o potencial em média +122 p.p. (mediana −71 p.p.); a mediana de (combinado ÷ combinado sem FCD − 1) é −68%. O sinal depende de a ação ser de FCD alto ou negativo.

### Limitações (para o rascunho)

1. Pesos pelo valor contábil: ações negociadas bem acima do patrimônio recebem peso de dívida exagerado e WACC menor (CONFIRMADO, `fcd.py:107-116`).
2. Selic como taxa livre de risco: o WACC do universo inteiro sobe e desce com o ciclo de juros (`fcd.py:97-99`).
3. Benefício fiscal de 34% para todas, inclusive empresas com prejuízo (`config.py:640`).
4. Prêmio de risco constante (7,47%), sem atualização automática (`config.py:626`).
5. Beta frágil: janela de 1 ano, retornos diários, sem ajuste e sem mínimo de observações (`comportamento.py:68`, `config.py:83`); valores baixos reduzem o Ke (PETR4: Beta 0,39).
6. Crescimento explícito de dois pontos, limitado a +30% (`fcd.py:136-144`); base atípica leva ao teto por 5 anos (MGLU3 e KLBN11).
7. Salto na perpetuidade: do crescimento explícito (até 30%) para o IPCA (≈ 4,2%) de um ano para o outro; o valor terminal pesa cerca de 55% do total (auditoria, não reconferido aqui).
8. g = IPCA 12m: um ponto no tempo, volátil, equivale a crescimento real zero (`fcd.py:147-151`).
9. FCF negativo: sem base positiva o crescimento vira IPCA e o fluxo negativo é perpetuado (SBSP3, PRIO3, CSNA3).
10. FCF de dezembro/2025 contra dívida líquida de 30/06/2026 (`fcd.py:270-276`).
11. **HIPÓTESE a confirmar (dois argumentos independentes, não verificados na fonte hoje):**
    - **(a) Mistura de moeda.** Pelo meu conhecimento da metodologia do Damodaran, o prêmio de risco por país costuma estar em dólares; somá-lo a uma Selic nominal em reais mistura bases. Verificar na tabela citada em `config.py:620-626` em que moeda o prêmio é expresso.
    - **(b) Dupla contagem do risco-país.** A Selic já embute o risco soberano do Brasil, e o prêmio de 7,47% já inclui o prêmio de risco-país (3,24%) e o spread de default (2,13%), segundo o comentário do próprio `config.py:620-626`; parte do risco-país pode estar contada duas vezes. Os dois argumentos são independentes: (a) pode ser verdadeiro sem (b) e vice-versa.

---

## 6. P11 — "Desconto" na interface

**Onde aparece (CONFIRMADO):** fórmula em `screener.py:407-411`; coluna `desconto_percentual` em `screener.py:425`; docstrings `screener.py:3-4` e `:453`; colunas "Desconto" em `main.py:1584`
(comparação setorial) e `main.py:1739` (Screener); textos `main.py:1638-1639`, `1644-1646`, `1662-1665`, `1731-1732`; avisos `config.py:766-800`; constantes `config.py:752-753`.

**O número é potencial de valorização**, `(valor_combinado − preço) ÷ preço × 100` (`screener.py:408-411`), e não desconto (`1 − preço ÷ valor`). Exemplos do `screener.csv` atual: KLBN11 "Desconto" +137,32% (valor 43,36 contra
preço 18,27; o desconto verdadeiro seria 57,9%); ENGI11 −98,90%. Os cartões de Valor Justo já usam a conta certa (`_delta_percentual_upside`, `main.py:496-512`), mas sem palavra nenhuma ao lado do "↑ 89,9%".

**Vocabulário proposto (independente do P03; vale para Screener, comparação setorial, avisos e cartões):**

| Onde | Rótulo | Tooltip / texto exato |
|---|---|---|
| Coluna do Screener e da comparação setorial | "Potencial" | "Quanto o valor justo combinado está acima (+) ou abaixo (−) do preço atual (valor justo ÷ preço − 1). Não é prazo nem retorno esperado." |
| Cartões de Valor Justo (delta) | manter o delta; adicionar `help` | "Diferença entre este valor e o preço atual (valor ÷ preço − 1)." |
| Aviso (texto positivo) | "Potencial extremo — …" no lugar de "Desconto extremo — …" | restante do texto igual |
| Aviso genérico | "Potencial fora do comum — …" | restante igual |
| Aviso global na tela | "N ação(ões) com potencial fora do comum (valor justo muito acima ou muito abaixo do preço)" | — |
| Expander "Como ler esta tabela" | "**Potencial** — quanto o valor justo combinado está acima ou abaixo do preço atual…" | — |

O nome da coluna `desconto_percentual` no CSV pode ficar (a própria auditoria permite); renomear exigiria regenerar o CSV e ajustar os testes (`tests/test_screener.py` e `tests/test_app_main.py` citam `desconto_percentual`/"Desconto"). A parte do **Simulador** deste vocabulário não está decidida e está nos textos de tela das opções A, B e C do P03 (seção 3.4).

---

## 7. Rascunho de `docs/limitacoes-conhecidas.md` (linguagem para o usuário do app)

> Rascunho; hipóteses não confirmadas ficam fora (estão na seção 8).

# Limitações conhecidas

Este app estima valores por três métodos simples (Graham, Bazin e fluxo de caixa descontado) a partir de dados públicos. São estimativas feitas por fórmulas, não recomendações de investimento, e todas têm limitações. Esta página lista as principais.

## Quando o FCD não se aplica

- **Bancos** (hoje: Bradesco, Banco do Brasil, Itaú, Santander e BTG): o fluxo de caixa de um banco varia com a expansão do crédito, e dívida e depósitos são a própria operação. Para essas ações só valem Graham e Bazin.
- **Sem dado:** o FCD não é calculado se a CVM não trouxer o fluxo de caixa da empresa ou se o número de ações não estiver disponível.
- **Seguradoras, holdings e outras financeiras** (BBSE3, PSSA3, CXSE3, ITSA4, B3SA3): o FCD é mostrado, mas não sabemos se a metodologia é adequada para esse tipo de empresa. Interprete com cautela.

## O fluxo de caixa usado no FCD é uma aproximação

- Usamos o caixa das operações mais o caixa dos investimentos (contas 6.01 e 6.02 da CVM). Isso **não é** um fluxo de caixa livre "limpo": o caixa de investimentos inclui aplicações e resgates financeiros, compra e venda de participações e de ativos, e não só a compra de imobilizado. Exemplo: em 2025 a Cosan teve R$ 8,9 bilhões de venda de investimentos que entraram no fluxo.
- Os **juros pagos** aparecem no caixa das operações em cerca de metade das empresas e no caixa de financiamento na outra metade, então o fluxo não é comparável entre empresas.
- O **pagamento de arrendamentos** (aluguéis de lojas, frotas, equipamentos) fica quase sempre fora do fluxo. Em varejistas como a Raia Drogasil, o pagamento de arrendamentos é do mesmo tamanho do fluxo calculado, e isso faz o valor justo sair maior do que deveria.
- Usamos o fluxo de **um único ano** e o crescimento entre **dois anos**. Variações pontuais de capital de giro, vendas de ativos ou um ano-base atípico mudam muito o resultado.
- Se a CVM publicar uma demonstração consolidada zerada, o app pode usar zero. (Isso é um defeito conhecido que será corrigido; ver perguntas em aberto.)

## Taxa de desconto e crescimento

(Seção "FCD: taxa de desconto e crescimento": itens 1 a 10 da lista da seção 5 deste relatório, em linguagem de usuário: pesos de dívida pelo valor contábil; Selic como taxa livre de risco; benefício fiscal de 34% para todas; prêmio de risco fixo; Beta de 1 ano e sem ajuste; crescimento de dois anos limitado a +30%; salto para o IPCA na perpetuidade e peso do valor terminal; g = IPCA de 12 meses; fluxo negativo perpetuado; datas diferentes entre fluxo e dívida.)

## Valores extremos

Em perto de 1 em cada 4 ações com FCD (16 de 70), o valor calculado fica muito acima (mais de 3 vezes) ou muito abaixo (negativo e menor que o preço) do preço de mercado. Valores assim quase sempre indicam sensibilidade do modelo às premissas, não uma oportunidade ou um desastre. O app sinaliza esses casos na coluna "Aviso".

## Bazin e Graham

- O **preço teto do Bazin** é o máximo a pagar para receber 6% ao ano em dividendos; não é uma estimativa de valor. Dividendos extraordinários o distorcem.
- O **Graham** usa lucro e patrimônio por ação recentes e não projeta nada.
- O **valor combinado** é a média simples dos métodos aplicáveis a cada ação; quando só um método se aplica, o combinado é esse método.

## Simulador de carteira

O Simulador é uma **estimativa, não uma previsão**. Os valores de cada cenário (pessimista, base e otimista) são o menor, a média e o maior valor entre os métodos, e valem como "se o preço chegasse a esse valor". [Se for adotada a opção B do P03:] Não há prazo nem dividendos, e o valor justo de hoje não é tratado como preço futuro. [Se for adotada a A ou a C: descrever o prazo e as premissas escolhidas.] Um valor justo zero ou negativo conta como perda total (−100%).

## Dados

- Os dados vêm de fontes públicas (CVM, Fundamentus, Banco Central, B3, Yahoo Finance) e podem ter atraso ou erro. O Fundamentus não tem API oficial: se o site mudar, o app pode ficar sem dado.
- A leitura das contas da CVM depende dos códigos (6.01, 6.02). Qualquer refinamento por descrição de conta (por exemplo, isolar o investimento em imobilizado) dependeria de texto livre, que cada empresa escreve de um jeito; em tal caso o app mostraria um aviso quando a linha não fosse encontrada.

---

## 8. Perguntas em aberto para você decidir

1. **P03:** qual opção para o Simulador (recomendo B; A como evolução opcional; C não)? Se for A, qual prazo padrão e qual crescimento do valor justo?
2. **P04:** adotar a definição alt3 por etapas, com `base_fluxo` e fallback, e deixar o arrendamento para depois? Ou prefere alt1 ou alt2?
3. **Bug TIMS3 (demonstração consolidada zerada):** corrigir em um commit à parte? Quando 6.01 e 6.02 forem ambos zero, o app deve usar a individual ou marcar o FCD como não aplicável?
4. **Dívida líquida do Fundamentus:** verificar na página se o campo inclui passivo de arrendamento e se abate aplicações financeiras (decide o tratamento do arrendamento e o item 2 da seção 4.2). Quer que eu investigue?
5. **Prêmio do Damodaran:** investigar os dois argumentos (moeda e dupla contagem) na tabela citada em `config.py:620-626`?
6. **Financeiras não bancárias:** manter o FCD para BBSE3, PSSA3, CXSE3, ITSA4 e B3SA3 ou excluí-las como os bancos?
7. **FCD extremo:** o que fazer com as 16 ações (22,9%)? Opções: aviso mais forte, excluir o FCD do combinado quando |FCD ÷ preço| passar de um limite, ou nada.
8. **MGLU3:** vale investigar a linha "Fornecedores" (+R$ 14,7 bi em 6.01 de 2025)? É variação de capital de giro ou reclassificação?
9. **Vocabulário "Potencial" (P11):** aprova os rótulos da seção 6 e a decisão de manter `desconto_percentual` no CSV?
10. **Capex por descrição:** depois da decisão do item 2, quer a implementação com fixtures reais e teste de cobertura?
11. **Achado colateral (teste frágil):** `tests/test_conftest.py:14` (`test_busca_bem_sucedida_nao_toca_o_data_raw_real`) exige que `data/raw/bcb/ultimo_macro.json` **não exista**.
    Na máquina local ele existe, criado pela rodada real do screener de 29/09/2026 às 23:47 (pelo botão do app; o arquivo está no `.gitignore`), então o teste falha aqui
    (505 passam, 1 falha, 506 coletados) e passa num clone limpo (foi o que aconteceu nos worktrees da verificação por commit). Não é regressão do código. A correção seria o teste
    comparar o conteúdo/data de modificação antes e depois, em vez de exigir ausência. Quer que eu corrija em um commit à parte?

12. **Participação de não controladores:** verificar se o FCD subtrai a participação de não controladores do balanço consolidado, além da dívida líquida. Se não subtrai, o valor de holdings com minoritários relevantes (hipótese principal para a CSAN3 seguir em 30,03 contra preço de 3,72) fica superestimado. Medir depois, nas 76, o peso dos não controladores sobre o patrimônio.
13. **Juros de arrendamento em 6.01:** na alt3, definir se a soma de volta dos juros pagos em 6.01 inclui os juros de arrendamento. Proposta: incluir quando o arrendamento está dentro da dívida do Fundamentus; não incluir quando está fora.
14. **Mesmo tipo de demonstração nos dois anos do crescimento:** quando o ano de referência e o ano-base usam tipos diferentes e o mesmo tipo existe nos dois, usar o mesmo tipo (caso ASAI3: 4,2% → 10,8%).

**Hipóteses não confirmadas deste relatório (para o item 4 e 5):** composição da "Dív. Líquida" do Fundamentus (arrendamento e aplicações financeiras); moeda do prêmio do Damodaran; dupla contagem do risco-país; peso do valor terminal de ~55% (da auditoria, não reconferido).

---

## 9. Decisões (02/10/2026)

Cada decisão está ligada ao número da pergunta em aberto da seção 8 que ela responde. Pergunta sem decisão fica como "Em aberto".

| Pergunta (seção 8) | Decisão | Situação |
|---|---|---|
| 1 — P03: qual opção para o Simulador | **Opção B**: potencial sem prazo, sem taxa anual e sem "ganho real". | Decidido |
| 2 — P04: definição do fluxo | Direção: **capex explícito**. Quando o capex não for identificado, o FCD fica **"não aplicável"**, com o motivo na tela, **sem voltar para 6.01 + 6.02** (substitui o fallback proposto na seção 4.7). **Decidido: alt3.** Etapa seguinte, depois da alt3: somar o passivo de arrendamento à dívida líquida quando ele estiver fora de 2.01.04/2.02.01. | Decidido: alt3 |
| 3 — Bug do TIMS3 (consolidada zerada) | Corrigir agora, em etapa própria. Regra: se a consolidada do ano tem 6.01 e 6.02 iguais a zero (ou ausentes), ela é tratada como inexistente e o app usa a individual daquele ano; se as duas forem zeradas, o comportamento atual continua. | Decidido; corrigido no commit `4e23afb` (inclui subir `VERSAO_SCHEMA_CVM_FCF` para 2) |
| 4 — Dívida líquida do Fundamentus (arrendamento e aplicações financeiras) | Verificação só de leitura nas empresas do relatório (mais o TIMS3), comparando com o balanço da CVM; o resultado decide alt2 ou alt3. | Verificado (seção 10); a escolha entre alt2 e alt3 continua com você |
| 5 — Prêmio do Damodaran (moeda e dupla contagem) | Adiado para a rodada do P10. | Em aberto |
| 6 — Financeiras não bancárias | FCD **não aplicável** para as seguradoras (BBSE3, PSSA3, CXSE3) e para ITSA4. **B3SA3 continua com FCD**, com a limitação documentada. | Decidido |
| 7 — FCD extremo (16 ações) | Fluxo-base ≤ 0: FCD **não aplicável** (não perpetuar fluxo negativo). As regras de aplicabilidade usam só as entradas do modelo, nunca a comparação com o preço. **Descartado:** excluir ou limitar o FCD com base na razão FCD ÷ preço. **Em aberto:** aviso mais forte na tela para FCD extremo (só informativo, não altera o cálculo nem o valor combinado). | Decidido em parte |
| 8 — MGLU3 (linha "Fornecedores" e crescimento no teto) | Adiado para a rodada do P10. | Em aberto |
| 9 — Vocabulário "Potencial" (P11) | **Aprovado** o vocabulário da seção 6; a coluna `desconto_percentual` continua no CSV. | Decidido |
| 10 — Implementação do capex por descrição | Outra tarefa, já com a alt3 decidida (pergunta 2). | Em aberto |
| 11 — Teste frágil (`tests/test_conftest.py:14`) | Corrigir agora, em etapa própria: o teste não pode depender de o arquivo real existir ou não. | Decidido; corrigido no commit `e29e83b` |
| 12 — Participação de não controladores | Verificar se o FCD subtrai a participação de não controladores do balanço consolidado, além da dívida líquida; medir depois, nas 76, o peso dos não controladores sobre o patrimônio. | Em aberto |
| 13 — Juros de arrendamento em 6.01 na alt3 | Definir se a soma de volta dos juros pagos em 6.01 inclui os juros de arrendamento. Proposta: incluir quando o arrendamento está dentro da dívida do Fundamentus; não incluir quando está fora. | Em aberto |
| 14 — Mesmo tipo de demonstração nos dois anos do crescimento | Quando o ano de referência e o ano-base usam tipos diferentes e o mesmo tipo existe nos dois, usar o mesmo tipo (caso ASAI3: 4,2% → 10,8%). | Em aberto |

**Em aberto:** perguntas 5, 8, 10, 12, 13 e 14; e, na pergunta 7, o aviso mais forte na tela para FCD extremo (só informativo, não altera o cálculo nem o valor combinado).

**Fora desta rodada:** a implementação do P03, do P11 e do P04 (será outra tarefa); a regeneração do `data/processed/screener.csv`.

---

## 10. Complemento: dívida líquida e arrendamento (02/10/2026)

Objetivo: decidir entre alt2 e alt3 (seção 4.6) a partir de como a "Dív. Líquida" do Fundamentus é montada. Só leitura; nada no código foi alterado por esta seção.

### 10.1 Fontes e desvio do combinado

- **Fundamentus:** "Dív. Bruta", "Disponibilidades" e "Dív. Líquida" das páginas de 02/10/2026, data-base 30/06/2026 nas nove empresas. O cache local (`data/raw/fundamentus/*.json`) só guarda a dívida líquida, o patrimônio e o número de ações, **não** a dívida bruta nem as disponibilidades. Por isso busquei as **9 páginas** (uma requisição cada, as mesmas do app) e as salvei em `%TEMP%\investigacao_p03_p04\fund_html`. A dívida líquida das páginas é igual à do cache nas nove.
- **CVM:** `itr_cia_aberta_2026.zip` (19,6 MB, ITR 2026, baixado para `%TEMP%\investigacao_p03_p04`), balanço consolidado (BPA e BPP) com `DT_REFER = 2026-06-30`, versão mais recente de cada empresa.
- **Empresas:** as 8 do relatório mais **TIMS3** (a nona), com a regra nova de demonstração (commit `4e23afb`).

### 10.2 Como o Fundamentus monta a dívida (CONFIRMADO nas 9 empresas)

Comparação com o balanço da CVM, em R$ mi. Em todas as nove, a diferença é 0,0% (até o arredondamento):

- **Dív. Bruta** = conta 2.01.04 + conta 2.02.01 do passivo ("Empréstimos e Financiamentos", circulante e não circulante). Essas contas **incluem as debêntures** e a subconta padrão **"Financiamento por Arrendamento"**.
- **Disponibilidades** = conta 1.01.01 ("Caixa e Equivalentes de Caixa") + conta 1.01.02 ("Aplicações Financeiras" do circulante).
- **Dív. Líquida** = Dív. Bruta − Disponibilidades.

| Ticker | Dív. Bruta (Fund. = CVM) | Disponibilidades (Fund. = CVM) | Caixa + aplicações (1.01.01 + 1.01.02) | Dív. Líquida |
|---|---|---|---|---|
| CSAN3 | 60.890 | 13.358 | 13.358 + 0 | 47.532 |
| SBSP3 | 51.658 | 17.441 | 4.243 + 13.197 | 34.217 |
| PETR4 | 366.533 | 53.764 | 33.560 + 20.204 | 312.769 |
| RADL3 | 3.453 | 653 | 537 + 116 | 2.800 |
| KLBN11 | 34.860 | 10.109 | 9.322 + 787 | 24.751 |
| CPFE3 | 31.552 | 3.988 | 2.165 + 1.823 | 27.564 |
| WEGE3 | 5.066 | 8.801 | 7.750 + 1.051 | −3.735 |
| MGLU3 | 4.946 | 1.762 | 905 + 857 | 3.184 |
| TIMS3 | 2.649 | 4.530 | 2.677 + 1.852 | −1.881 |

A regra foi verificada só nestas nove; que valha para as 76 é **HIPÓTESE** (a verificar).

### 10.3 Conclusão por empresa

**O passivo de arrendamento está dentro da dívida do Fundamentus?** Só quando a empresa o registra na subconta padrão "Financiamento por Arrendamento" dentro de Empréstimos e Financiamentos. Se o registra em "outras obrigações" (contas 2.01.05 e 2.02.02, ou 2.01.06 e 2.02.04), fica **fora**.

| Ticker | Arrendamento na dívida do Fundamentus? | Passivo de arrendamento (R$ mi) | A líquida desconta aplicações financeiras? |
|---|---|---|---|
| CSAN3 | **Sim** | 6.631 dentro | Só o caixa (1.01.02 é zero). Ficam **fora**: títulos e valores mobiliários de R$ 5.491 mi (1.01.08.03.01), caixa restrito (R$ 37 mi + R$ 194 mi) e títulos não circulantes (R$ 64 mi) |
| SBSP3 | Sem passivo de arrendamento | — | Sim (R$ 13.197 mi em 1.01.02); caixa restrito de R$ 28 mi fica fora |
| PETR4 | **Sim** | 232.799 dentro (63,5% da dívida bruta; R$ 179.740 mi só no não circulante) | Sim (R$ 20.204 mi) |
| RADL3 | **Não** | 5.140 fora ("Arrendamentos a pagar": 1.025 + 4.115) | Sim (R$ 116 mi) |
| KLBN11 | **Não** | 1.840 fora (381 + 1.459) | Sim (R$ 787 mi) |
| CPFE3 | Sem passivo de arrendamento | — | Sim (R$ 1.823 mi) |
| WEGE3 | **Não** | 768 fora (184 + 585) | Sim (R$ 1.051 mi); aplicações não circulantes de R$ 12 mi ficam fora |
| MGLU3 | **Não** | 3.566 fora (439 + 3.127) | Sim (R$ 857 mi) |
| TIMS3 | **Não** | 13.848 fora (1.674 + 12.175) | Sim (R$ 1.852 mi); aplicação não circulante de R$ 34 mi fica fora |

Resumo: o arrendamento está **dentro** da dívida em 2 das 9 (CSAN3, PETR4), **fora** em 5 (RADL3, KLBN11, WEGE3, MGLU3, TIMS3) e **inexistente** em 2 (SBSP3, CPFE3). A líquida desconta as aplicações financeiras **da conta 1.01.02**, mas não as que a empresa classifica em outras contas (CSAN3, R$ 5,5 bi). No TIMS3, a dívida líquida de −R$ 1,9 bi (caixa líquido) viraria dívida de R$ 12,0 bi se o passivo de arrendamento entrasse.

### 10.4 FCD em quatro versões (as 9 empresas)

**atual** = 6.01 + 6.02 (com a regra nova de demonstração); **só capex** = 6.01 − capex; **alt2** = 6.01 − capex − arrendamento pago em 6.03 + juros pagos em 6.01 × (1 − 34%); **alt3** = 6.01 − capex + juros pagos em 6.01 × (1 − 34%), sem subtrair arrendamento. Última coluna, informativa: alt3 com o passivo de arrendamento que está **fora** da dívida somado à dívida líquida (alt3 menos passivo fora ÷ número de ações). Mesma função `calcular_valor_justo_fcd`, importada sem alteração; os valores "atual" batem com o `screener.csv` (exceto TIMS3, ver nota).

| Ticker | Preço | `screener.csv` | atual | só capex | alt2 | alt3 | alt3 + arrend. como dívida |
|---|---|---|---|---|---|---|---|
| CSAN3 | 3,72 | 32,06 | 32,06 | 30,03 | 15,22 | 30,03 | 30,03 |
| SBSP3 | 27,06 | −26,74 | −26,74 | −22,19 | −18,06 | −18,06 | −18,06 |
| PETR4 | 49,10 | 48,26 | 48,26 | 26,55 | −10,13 | 26,55 | 26,55 |
| RADL3 | 18,14 | 2,53 | 2,53 | 2,56 | 0,24 | 4,90 | 1,97 |
| KLBN11 | 18,27 | 101,95 | 101,95 | 78,09 | 38,65 | 48,43 | 46,95 |
| CPFE3 | 44,50 | −6,94 | −6,94 | −16,68 | −6,08 | −6,08 | −6,08 |
| WEGE3 | 50,29 | 5,31 | 5,31 | 6,62 | 6,94 | 6,94 | 6,75 |
| MGLU3 | 6,63 | 225,66 | 225,66 | 227,36 | 214,81 | 227,36 | 222,77 |
| TIMS3 | 18,53 | 0,79 | 57,67 | 36,06 | 23,32 | 36,06 | 30,24 |

Nota TIMS3: o `screener.csv` ainda traz 0,79 (não regenerado); "atual" é o que o código corrigido calcula (FCF 2025 = R$ 9.879 mi pela demonstração individual). O arrendamento pago do TIMS3 em 6.03 é R$ 3.210 mi em 2025 (a individual traz o principal e os juros de arrendamento em 6.03), e o passivo de R$ 13.848 mi está fora da dívida.

### 10.5 Recomendação: alt3

**Alt3, não alt2**, com base na seção 10.3:

1. **Alt2 só é coerente onde o arrendamento está fora da dívida do Fundamentus** (5 das 9). Onde ele está **dentro** (CSAN3, PETR4), subtrair o pagamento de arrendamento do fluxo conta o mesmo custo duas vezes: o passivo já está na dívida subtraída. Os dois casos são grandes: PETR4 vai de 26,55 (alt3) para −10,13 (alt2), efeito quase todo do arrendamento pago de R$ 52,4 bi; CSAN3, de 30,03 para 15,22.
2. **Alt3 ignora o custo do arrendamento onde ele está fora da dívida**, o que superestima o valor nessas cinco: a coluna "alt3 + arrend. como dívida" mostra o tamanho (RADL3 4,90 → 1,97; TIMS3 36,06 → 30,24; KLBN11 48,43 → 46,95; MGLU3 227,36 → 222,77; WEGE3 6,94 → 6,75). É a limitação a documentar com a alt3.
3. **O desenho consistente a médio prazo** é o da última coluna: fluxo antes do pagamento do arrendamento (alt3) **e** passivo de arrendamento somado à dívida líquida quando o Fundamentus não o inclui. Exige ler o passivo de arrendamento do balanço (contas fora de 2.01.04/2.02.01, identificadas por descrição, a mesma fragilidade do capex) e fica como etapa seguinte à alt3.
4. **As disponibilidades** do Fundamentus (1.01.01 + 1.01.02) não incluem os títulos em outras contas (CSAN3, R$ 5,5 bi). Isso reforça tirar do fluxo a parte financeira de 6.02, como alt3 faz ao usar só o capex.

Não corrige o que é de modelo (SBSP3 e CPFE3 seguem negativos; MGLU3 segue em ~R$ 227): ver P10.

### 10.6 Verificação extra: tipo e método da demonstração diferentes entre o ano de referência e o ano-base

Para as 76 ações (74 CNPJs), comparei a demonstração escolhida em 2025 (ano de referência) e em 2020 (ano-base do crescimento), aplicando a regra atual (commit `4e23afb`). **68 CNPJs usam o mesmo método e tipo nos dois anos; 5 usam diferentes; 1 (AURE3) não tem DFC em 2020.** Sem proposta de correção, só o levantamento.

| Ticker | 2025 | 2020 | FCF 2025 / 2020 (R$ mi) | Crescimento atual | Mesmo tipo nos dois anos |
|---|---|---|---|---|---|
| ASAI3 | MI/individual | MI/consolidada | 4.725 / −1.289 | 4,2% (IPCA, base negativa) | **10,8%** (CAGR) com a individual de 2020 (FCF 2.835). FCD de R$ 22,45 passa a R$ 31,39 (preço R$ 10,54) |
| TIMS3 | MI/individual | MI/consolidada | 9.879 / 3.381 | 23,9% (CAGR) | 23,9% (a individual de 2020 também dá 3.381) |
| BRAP4 | MI/individual | MI/consolidada | 670 / 979 | −7,3% (CAGR) | −7,3% (a individual de 2020 dá 978); em 2025 só existe a individual |
| SBSP3 | MI/consolidada | MI/individual | −7.343 / −1.790 | 4,2% (IPCA, fluxo negativo) | 4,2% (IPCA) com qualquer tipo: em 2020 só existe a individual |
| SANB11 (banco, FCD não aplicável) | MI/individual | MI/consolidada | 10.179 / 41.155 | −20,0% (CAGR no piso) | −19,1% com a individual nos dois anos (2020: 29.398) |

Notas: (i) o SANB11 também tem diferença de **método**: em 2025 a DFC consolidada existe só no método direto (MD, FCF R$ 1.669 mi) e a ordem MI-antes-de-MD escolhe a individual indireta; como banco, o FCD não se aplica, então não afeta nenhum valor justo. (ii) Entre as ações com FCD aplicável, a diferença é de **tipo** (consolidada contra individual), não de método.

**TIMS3, em particular.** Em 2020 foi usada a **consolidada** (MI/con); em 2025, depois da correção, a **individual** (MI/ind). Isso **não** explica o salto de 4,2% para 23,9%: em 2020 as duas demonstrações trazem o mesmo FCF (R$ 3.381 mi), então o CAGR é 23,9% com qualquer combinação. O salto vem de o FCF de 2025 ter passado de 0 para R$ 9.879 mi: antes da correção o fluxo atual era zero, o CAGR não era calculável (`fcd.py:141`, fluxo atual ≤ 0) e o crescimento caía para o IPCA (4,2%). Com a correção, o crescimento passa a ser o CAGR de 23,9% (limite de 30%). Quem quiser olhar com cautela o FCD de R$ 57,67 deve considerar que 23,9% por 5 anos é um crescimento alto para uma telecom.
