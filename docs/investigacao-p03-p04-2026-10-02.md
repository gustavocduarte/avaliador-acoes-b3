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

## Casos levantados na implementação do P04

- **Fluxo perto de zero:** o FCD só é calculado quando o fluxo de caixa do último ano é positivo, e o corte em zero é abrupto: o valor fica muito sensível perto dele. A RDOR3 tem FCD calculado com um fluxo de R$ 79 milhões, positivo só porque somamos de volta os juros pagos (R$ 4,3 bilhões). A CMIN3 (fluxo de −R$ 34 milhões) e a CSMG3 (−R$ 29 milhões) ficam sem FCD por pouco.
- **Entradas e saídas que não são da operação:** vendas de participações, operações descontinuadas, resgates de aplicações e aquisições de participações não entram no fluxo, de propósito: só contam o caixa das operações, a compra de imobilizado e intangível e os juros. Isso muda bastante o resultado de empresas como EQTL3, MOTV3, ENEV3, NATU3 e PRIO3 em relação a quando o fluxo incluía todo o caixa de investimentos.
- **Gasto em imobilizado e intangível não identificado (IGTI11):** o app procura essa linha pela descrição que cada empresa escreve. Se não a encontra no ano mais recente, o FCD não é calculado; hoje isso acontece só com a IGTI11. Se não a encontra no ano-base do crescimento, o crescimento do fluxo passa a ser a inflação (IPCA), e o cartão do FCD avisa.
- **Juros pagos:** somamos de volta só as linhas dedicadas a juros de empréstimos, financiamentos e debêntures no caixa das operações. Linhas de juros de arrendamento e linhas que misturam juros com outras coisas ficam de fora.
- **Linha mista de juros (MRVE3):** a única linha de juros da MRVE3 no caixa das operações (cerca de R$ 70,9 milhões) mistura juros da compra de terrenos com arrendamentos. Ela fica fora da soma, e para essa empresa os juros contam como zero.
- **Arrendamentos:** o pagamento de arrendamentos (aluguéis de longo prazo) não entra no fluxo. A dívida líquida do Fundamentus só inclui o arrendamento quando a empresa o registra como empréstimo ou financiamento (é o caso de PETR4 e CSAN3); nas demais (por exemplo RADL3, KLBN11, WEGE3, MGLU3 e TIMS3), o passivo de arrendamento é somado à dívida na hora de descontar o valor do acionista. Esse passivo não entra nos pesos do custo de capital, que são contábeis: mais dívida contábil baixaria o custo de capital e empurraria o valor para cima. Onde o arrendamento está na dívida do Fundamentus, há uma pequena dupla contagem, porque os juros dele continuam descontados do fluxo.
- **Porcentagem "reinvestida":** a frase "reinvestiu X% do caixa gerado" no cartão do FCD usa todo o caixa das atividades de investimento (inclui aplicações e participações), e não só a compra de imobilizado e intangível usada no fluxo. Por isso pode não bater com o fluxo.

## Participação dos não controladores e número de ações

- **Participação dos não controladores:** o FCD parte do fluxo de caixa da empresa inteira (consolidado), então desconta a parte que pertence aos sócios minoritários das empresas controladas, pelo **valor contábil** do balanço consolidado da CVM. O valor contábil costuma ficar abaixo do valor de mercado dos minoritários, então o desconto pode ficar curto. Em empresas com muitos minoritários, como a GOAU4 (Metalúrgica Gerdau, com 64% do patrimônio em não controladores), o valor justo por ação pode ficar negativo. O valor negativo é mostrado como está, com o aviso "Valor justo zero ou negativo", sem ser limitado a zero: não quer dizer que a ação valha menos que zero, e sim que o fluxo da empresa não cobre a dívida e a parte dos minoritários.
- **Número de ações:** o FCD, o Graham e o valor de mercado usam as ações em circulação (capital integralizado menos tesouraria) da composição de capital da CVM, na data-base do balanço do Fundamentus. Quando a CVM não traz o número, ou ele é descartado, vale o número do Fundamentus (que na maioria das empresas inclui a tesouraria) e o cartão diz o motivo.
- **Eventos depois da data-base do balanço:** ofertas, bonificações e cancelamentos de ações depois da data-base só entram no balanço seguinte. Exemplo: a oferta de ações da EGIE3 em 14/07/2026 (cerca de R$ 8,36 bi) ainda não está no balanço de 30/06/2026; o FCD usa o número de ações e a dívida de 30/06, e a página avisa que o número do Fundamentus (que já inclui as ações novas) difere do da CVM.
- **Dependência das salvaguardas de escala e tesouraria:** a composição de capital da CVM nem sempre é consistente (22 empresas informam em milhares, a TEND3 tem a tesouraria em ações e o resto em milhares, e a Vale informa o integralizado já líquido de tesouraria desde 2026). O app corrige a escala, descarta a tesouraria acima de 20% do capital e um número da CVM que difira mais de 50% do Fundamentus, e reconhece o integralizado já líquido; fora desses casos, um erro novo nos dados da CVM pode passar sem ser notado.
- **Valor de firma:** o valor de firma exibido na página (mercado + dívida líquida) não inclui os não controladores nem o arrendamento fora da dívida, diferente da ponte usada no FCD.

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
15. **Patrimônio usado nos pesos do WACC:** o índice Dív Líq / Patrim do Fundamentus usa o patrimônio dos controladores (seção 11.3). Proposta: usar o patrimônio líquido total (controladores + não controladores), coerente com o fluxo e a dívida consolidados. Os pesos a valor de mercado continuam como limitação do P09.
16. **Número de ações divergente da CVM:** EGIE3 (+24%), VALE3 (+4,3%) e AXIA3 (−3,9%) têm no Fundamentus um número de ações diferente do da composição de capital da CVM (seção 11.4). Investigar a causa (bonificação, cancelamento de tesouraria, classes de ações) e o efeito no FCD por ação, como no P06.
17. **Fator de unit da IGTI11:** o Fundamentus entrega fator 7 ações por unit, o que não bate com a CVM (1.206 mi de ações contra 296,7 mi de units no app). Investigar a composição real da unit e se o P06 trata a IGTI11 corretamente. Hoje sem efeito no FCD (não aplicável por capex), mas pode afetar o Graham.
18. **Valor de firma da página:** **implementada** (commit "Calcula o valor de firma da página pela ponte do FCD"). O valor de firma passa a ser mercado + dívida líquida + não controladores + arrendamento fora da dívida, a mesma ponte do FCD; componente indisponível fica de fora, com legenda dizendo qual (só exibição).

**Hipóteses não confirmadas deste relatório (para o item 4 e 5):** composição da "Dív. Líquida" do Fundamentus (arrendamento e aplicações financeiras); moeda do prêmio do Damodaran; dupla contagem do risco-país; peso do valor terminal de ~55% (da auditoria, não reconferido).

---

## 9. Decisões (02/10/2026)

Cada decisão está ligada ao número da pergunta em aberto da seção 8 que ela responde. Pergunta sem decisão fica como "Em aberto".

| Pergunta (seção 8) | Decisão | Situação |
|---|---|---|
| 1 — P03: qual opção para o Simulador | **Opção B**: potencial sem prazo, sem taxa anual e sem "ganho real". | Decidido; implementado nos commits `9bea4c6` e `c878f10` |
| 2 — P04: definição do fluxo | Direção: **capex explícito**. Quando o capex não for identificado, o FCD fica **"não aplicável"**, com o motivo na tela, **sem voltar para 6.01 + 6.02** (substitui o fallback proposto na seção 4.7). **Decidido: alt3.** Etapa seguinte, depois da alt3: somar o passivo de arrendamento à dívida líquida quando ele estiver fora de 2.01.04/2.02.01. **Decisão (03/10/2026):** o passivo de arrendamento fora da dívida do Fundamentus é somado só na dedução do valor do acionista; **arrendamento nos pesos do WACC: não incluído enquanto os pesos forem contábeis** (mais dívida contábil baixa o WACC e empurra o valor para cima); revisitar no P09 junto com os pesos a valor de mercado. | Decidido; alt3 implementada (extração no commit `78f671e`, FCD no `e23397b`); arrendamento implementado no commit `83246eb` (leitura única do balanço no `f394005`) |
| 3 — Bug do TIMS3 (consolidada zerada) | Corrigir agora, em etapa própria. Regra: se a consolidada do ano tem 6.01 e 6.02 iguais a zero (ou ausentes), ela é tratada como inexistente e o app usa a individual daquele ano; se as duas forem zeradas, o comportamento atual continua. | Decidido; corrigido no commit `4e23afb` (inclui subir `VERSAO_SCHEMA_CVM_FCF` para 2) |
| 4 — Dívida líquida do Fundamentus (arrendamento e aplicações financeiras) | Verificação só de leitura nas empresas do relatório (mais o TIMS3), comparando com o balanço da CVM; o resultado decide alt2 ou alt3. | Verificado (seção 10); decidido alt3 (pergunta 2) |
| 5 — Prêmio do Damodaran (moeda e dupla contagem) | Adiado para a rodada do P10. **Decidida e implementada no P10 (opção P2):** custo do capital próprio com a Selic menos o spread de default (2,13%) e o prêmio total de risco do Brasil; ver `docs/investigacao-p10-2026-10-04.md`. | Implementada (commit `37b7b99`) |
| 6 — Financeiras não bancárias | FCD **não aplicável** para as seguradoras (BBSE3, PSSA3, CXSE3) e para ITSA4. **B3SA3 continua com FCD**, com a limitação documentada. | Decidido; implementado no commit `81a7f4a` |
| 7 — FCD extremo (16 ações) | Fluxo-base ≤ 0: FCD **não aplicável** (não perpetuar fluxo negativo). As regras de aplicabilidade usam só as entradas do modelo, nunca a comparação com o preço. **Descartado:** excluir ou limitar o FCD com base na razão FCD ÷ preço. **Implementado em 04/10/2026:** aviso mais forte no cartão do FCD (só informativo, não altera o cálculo nem o valor combinado), com a causa provável nas entradas do modelo. Dispara com FCD ≤ 0, FCD ≥ 3 vezes o preço ou FCD positivo até 10% do preço (17 das 53 ações), e as causas são deduções acima ou perto do valor da empresa, crescimento no teto ou perto do piso, perpetuidade com 70% ou mais, WACC baixo e fluxo do ano a partir de 50% do valor de mercado. | Implementada; fluxo ≤ 0 no commit `81a7f4a` e, desde `e23397b`, aplicado ao fluxo da alt3; aviso de valor extremo no commit `940a1a3` |
| 8 — MGLU3 (linha "Fornecedores" e crescimento no teto) | Adiado para a rodada do P10. **Resolvida na investigação do fluxo-base (risco sacado, N4):** a saída líquida de convênio com fornecedores em 6.03 passa a reduzir o caixa operacional do FCD; ver `docs/investigacao-fluxo-base-2026-10-04.md`. | Implementada (commit `a3b78ee`) |
| 9 — Vocabulário "Potencial" (P11) | **Aprovado** o vocabulário da seção 6; a coluna `desconto_percentual` continua no CSV. | Decidido; implementado no commit `26e8002` |
| 10 — Implementação do capex por descrição | Implementar com a alt3 decidida (pergunta 2), com fixtures e teste de cobertura. Nos zips locais, o capex é identificado em 63 das 64 empresas não financeiras em 2025 (a exceção é a IGTI11) e em 63 de 63 em 2020. | Decidido; implementado no commit `78f671e` |
| 11 — Teste frágil (`tests/test_conftest.py:14`) | Corrigir agora, em etapa própria: o teste não pode depender de o arquivo real existir ou não. | Decidido; corrigido no commit `e29e83b` |
| 12 — Participação de não controladores | Verificar se o FCD subtrai a participação de não controladores do balanço consolidado, além da dívida líquida; medir depois, nas 76, o peso dos não controladores sobre o patrimônio. **Decisão sobre o ajuste A (03/10/2026):** o valor negativo depois do ajuste A é mostrado com o aviso "Valor justo zero ou negativo", sem limitar a zero; o caso GOAU4 vai para as limitações conhecidas (rascunho na seção 7). **Decisão (03/10/2026): ajuste A**, subtrair o valor contábil dos não controladores junto com a dívida líquida. | Investigado (seção 11); decidido e implementado no commit `7b206e6` (leitura única do balanço no `f394005`) |
| 13 — Juros de arrendamento em 6.01 na alt3 | A soma de volta considera só linhas dedicadas a juros de empréstimos, financiamentos e debêntures em 6.01. Linhas de juros de arrendamento e linhas mistas (principal e juros, ou juros de arrendamento e de outra dívida) ficam de fora, independentemente de o arrendamento estar dentro da dívida do Fundamentus. Isso simplifica a proposta original, que incluía os juros de arrendamento quando o arrendamento está na dívida. A etapa do arrendamento como dívida (commit `83246eb`) não alterou essa decisão; a revisão fica para quando o arrendamento entrar nos pesos do WACC (P09). Onde o arrendamento já está dentro da dívida do Fundamentus (PETR4 e CSAN3), gera uma pequena dupla contagem: os juros do arrendamento continuam descontados do fluxo e o passivo também é subtraído na dívida líquida. Caso conhecido: MRVE3, cuja única linha de juros em 6.01 mistura terrenos e arrendamentos (cerca de R$ 70,9 mi) e não entra na soma. | Decidido; implementado no commit `78f671e` |
| 14 — Mesmo tipo de demonstração nos dois anos do crescimento | Quando o ano de referência e o ano-base usam demonstrações diferentes e a do ano de referência existe, com valores, também no ano-base, o ano-base usa a mesma; senão vale a escolha padrão. Com a alt3, o crescimento da ASAI3 passa de 19,5% para 15,1% e o FCD de R$ 44,53 para R$ 36,55 (o 4,2% → 10,8% da seção 10.6 era do fluxo antigo, 6.01 + 6.02). TIMS3, BRAP4 e SANB11 trocam a demonstração do ano-base sem efeito relevante (no SANB11 o crescimento já estava no piso de −20% e o FCD não se aplica). SBSP3 não muda: a consolidada de 2020 não existe com valores. | Decidido; implementado no commit `77530c4` |
| 15 — Patrimônio usado nos pesos do WACC | Usar o patrimônio líquido total (controladores + não controladores), coerente com o fluxo e a dívida consolidados. Os pesos a valor de mercado continuam como limitação do P09. **Decisão (03/10/2026):** patrimônio líquido total nos pesos do WACC (dívida líquida ÷ patrimônio total), com a razão do Fundamentus como fallback e o motivo no cartão. | Decidido; implementado no commit `b3cacb6` |
| 16 — Número de ações divergente da CVM | Investigar a causa nas ações EGIE3 (+24%), VALE3 (+4,3%) e AXIA3 (−3,9%) (bonificação, cancelamento de tesouraria, classes de ações) e o efeito no FCD por ação, como no P06. **Decisão (03/10/2026):** o FCD por ação, o Graham, o valor de mercado e o valor de firma usam as ações em circulação (integralizado menos tesouraria) da composição do capital da CVM na data-base do balanço do Fundamentus, com as units mantidas; LPA e VPA do Fundamentus reescalados pela razão entre os dois números; leitura indisponível cai no número do Fundamentus, com o motivo. Salvaguardas: normalização de escala (razão perto de 1.000), tesouraria acima de 20% do capital descartada (TEND3), integralizado já líquido de tesouraria reconhecido (VALE3; tesouraria abaixo de 0,5% do capital segue o padrão de subtrair) e divergência acima de 50% descartada (IGTI11). Aviso na tela só quando o número do Fundamentus não bate nem com o em circulação nem com o integralizado, com diferença acima de 2% (EGIE3 e ISAE4). | Investigado (seção 12); decidido e implementado nos commits `f394005` (leitura e salvaguardas), `d64dccc` (FCD e Graham) e `244344e` (tela e valor de mercado) |
| 17 — Fator de unit da IGTI11 | Investigar a composição real da unit (o Fundamentus entrega fator 7; a CVM tem 1.206 mi de ações contra 296,7 mi de units no app) e se o P06 trata a IGTI11 corretamente. Hoje sem efeito no FCD (não aplicável por capex), mas pode afetar o Graham. **Investigação (04/10/2026, seção 13):** o fator 7 está certo (1 ON + 2 PN que valem 3 vezes a ON: 1 + 2×3 = 7 ordinárias equivalentes), o P06 acerta o valor por unit (descarta a CVM, que ele converte pela contagem física, e fica com as 296,7 mi do Fundamentus), o Graham muda só 0,1% a 0,3% com a conversão por peso econômico, e as outras cinco units (SANB11, KLBN11, TAEE11, BPAC11, ENGI11) batem. **Implementado em 04/10/2026:** tabela de composições em `config.py` e conversão da CVM por peso econômico, com aviso na página quando o fator do Fundamentus não bate com a tabela ou a unit não está nela; na IGTI11 o número da CVM convertido (296,5 mi) fica 0,09% abaixo do do Fundamentus e deixa de cair na trava de 50%, e as outras cinco units não mudam. | Implementada (commit `74a8702`) |
| 18 — Valor de firma da página | Valor de firma (mercado + dívida líquida) não incluía os não controladores nem o arrendamento fora da dívida, diferente da ponte usada no FCD; alinhado (só exibição). | Implementada (commit "Calcula o valor de firma da página pela ponte do FCD") |

**Em aberto:** só o arrendamento nos pesos do WACC (revisitar no P09 junto com os pesos a valor de mercado). As perguntas 5, 7 (aviso de FCD extremo), 8 e 17 (fator de unit) foram resolvidas em 04/10/2026.

**Fora desta rodada:** a regeneração do `data/processed/screener.csv`, que ainda reflete o cálculo anterior aos ajustes do balanço (prompt separado, depois desta rodada).

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


---

## 11. Pergunta 12: participação de não controladores (03/10/2026)

Investigação só de leitura; nada no código, nos testes ou em `data/` foi alterado. Scripts e dados em `%TEMP%\investigacao_p12`. Fontes: CVM, balanço consolidado (BPP) do ITR de 30/06/2026 (a mesma data-base da dívida do Fundamentus); CVM, DRE consolidada da DFP de 2025; composição de capital do ITR de 30/06/2026; caches do Fundamentus e `screener.csv` de 03/10/2026 (commit `23f0e16`). O universo é o das 53 ações com FCD aplicável (6 bancos, 3 seguradoras, ITSA4, IGTI11 e 12 com fluxo ≤ 0 não têm FCD). Não controladores e controladores abaixo são os rótulos da CVM: conta 2.03.09 do balanço ("Participação dos Acionistas Não Controladores") e linhas 3.11.01 e 3.11.02 da DRE.

### 11.1 Do valor da empresa ao valor por ação (CONFIRMADO no código)

| Passo | Onde |
|---|---|
| Valor presente dos 5 anos explícitos | `fcd.py:343-347` |
| Valor terminal e seu valor presente | `fcd.py:349-350` |
| Valor da empresa (Enterprise Value) = soma dos dois | `fcd.py:352` (`valor_total`) |
| **Única dedução:** dívida líquida do Fundamentus (Dív. Líquida = 2.01.04 + 2.02.01 − 1.01.01 − 1.01.02, ver seção 10.2) | `fcd.py:357-359` |
| Valor por ação = `valor_total` ÷ número de ações | `fcd.py:363` |

O número de ações vem do campo "Nro. Ações" do Fundamentus (`config.py:245`), convertido para a base da cotação nas units (`fundamentus.py:119-151`) e passado em `app/main.py:985` e `:1032` e em `screener.py:351` e `:460`. **A participação dos não controladores não é subtraída em nenhum ponto**: uma busca por "controlador" e "minorit" em `src/` não encontra tratamento nenhum. Como o fluxo de caixa usado é o consolidado (6.01 e capex da empresa inteira), o valor da empresa inclui a parte que pertence aos minoritários das controladas, e o valor por ação a atribui toda aos acionistas da empresa.

### 11.2 Peso dos não controladores nas ações com FCD (CONFIRMADO nos dados)

Participação dos não controladores ÷ patrimônio líquido total consolidado (2.03), em 30/06/2026. 12 das 53 empresas não têm não controladores, 2 (ASAI3 e BRAP4) ficaram sem balanço consolidado na base e 27 têm até 10%; **11 passam de 10%**:

| Ticker | Não controladores (R$ bi) | PL total (R$ bi) | Peso |
|---|---|---|---|
| CSAN3 | 26,94 | 31,91 | 84,4% |
| GOAU4 | 34,56 | 53,80 | 64,2% |
| KLBN11 | 6,49 | 15,97 | 40,6% |
| BEEF3 | 0,60 | 2,18 | 27,6% |
| CURY3 | 0,39 | 2,05 | 19,2% |
| MBRF3 | 2,40 | 13,79 | 17,4% |
| ENGI11 | 3,49 | 22,98 | 15,2% |
| DIRR3 | 0,41 | 2,74 | 15,0% |
| USIM5 | 2,89 | 23,65 | 12,2% |
| MRVE3 | 0,62 | 5,20 | 12,0% |
| UGPA3 | 2,07 | 20,03 | 10,3% |

Logo abaixo do corte: AURE3 (9,8%), EMBJ3 (9,7%) e RDOR3 (9,6%). Os demais ficam em 7% ou menos (EGIE3 6,7%, WEGE3 6,6%, CPFE3 4,0%, VALE3 2,4%). **Limitação:** ASAI3 e BRAP4 não têm balanço consolidado no ITR de 30/06/2026 na base usada e ficaram sem medida.

### 11.3 O patrimônio do Fundamentus é só o dos controladores (CONFIRMADO nos dados)

O "Patrim. Líq" do Fundamentus (`config.py:251`, cache `patrimonio_liquido`) é o **patrimônio atribuído aos controladores** (2.03 menos 2.03.09), não o total. Nas 51 empresas não financeiras com não controladores, o valor do Fundamentus bate com o dos controladores (diferença de até 1%) em 51 e com o total em nenhuma (as 23 que também batem com o total têm não controladores abaixo de 1%). Os 6 bancos não batem com nenhum dos dois (estrutura de balanço diferente; o FCD não se aplica a eles).

| Ticker | PL no Fundamentus (R$ bi) | PL total CVM | PL controladores CVM | Não controladores |
|---|---|---|---|---|
| CSAN3 | 4,968 | 31,910 | 4,968 | 26,942 |
| KLBN11 | 9,487 | 15,974 | 9,487 | 6,487 |
| ENEV3 | 20,356 | 21,998 | 20,356 | 1,642 |
| MBRF3 | 11,384 | 13,786 | 11,384 | 2,403 |
| BEEF3 | 1,579 | 2,182 | 1,579 | 0,603 |
| CURY3 | 1,655 | 2,049 | 1,655 | 0,394 |
| DIRR3 | 2,327 | 2,737 | 2,327 | 0,410 |

**Consequência nos pesos do WACC (CONFIRMADO).** O WACC usa o índice "Dív Líq / Patrim" do Fundamentus (`config.py:240`; `fcd.py:175-185` e `:198`), e nas 53 empresas com FCD esse índice é exatamente a dívida líquida (consolidada, com os financiamentos de todas as controladas) dividida pelo patrimônio **dos controladores** (diferença menor que 0,02). Com não controladores relevantes, a dívida total é comparada com um patrimônio sem a parte dos minoritários, e o peso da dívida (barata, pós-imposto) sobe e puxa o WACC para baixo. Na CSAN3 o índice é 9,57 (dívida líquida 47,53 bi ÷ 4,97 bi), contra 1,49 com o patrimônio total.

### 11.4 Número de ações (CONFIRMADO nos dados, com ressalvas)

Comparação do "Nro. Ações" do Fundamentus com a composição de capital da CVM de 30/06/2026 (a data mais recente disponível; ações integralizadas, com a tesouraria à parte):

- **CSAN3:** Fundamentus 3.966.570.000, CVM 3.966.570.932. O mesmo número consta em 31/12/2025, 31/03/2026 e 30/06/2026, então **não há aumento de capital que ainda não esteja refletido até 30/06/2026**. A tesouraria caiu de 47,6 milhões (31/03) para 22,2 milhões de ações (30/06), 0,56% do total; descontando a tesouraria, o FCD sobe de R$ 29,96 para R$ 30,13 (+0,6%), efeito mínimo e de sinal contrário ao que explicaria a distância para o preço. Um aumento de capital depois de 30/06/2026 não aparece nos arquivos disponíveis (HIPÓTESE não testável aqui).
- **Escala:** para várias empresas (por exemplo ABEV3, VALE3, AXIA3, LREN3) o arquivo da CVM informa a composição em milhares (razão de 1.000 contra o Fundamentus), e para as units a razão é a da unit (KLBN11 e ENGI11, 0,20: 1 unit = 5 ações; TAEE11, 1/3: 1 unit = 3 ações), coerente com a conversão do `fundamentus.py:119-151`.
- **Das 11 empresas acima de 10%**, CSAN3, GOAU4 (−0,2%), BEEF3, CURY3, DIRR3, UGPA3, USIM5 e MRVE3 batem com a CVM (diferença abaixo de 1%, corrigida a escala); MBRF3 fica 1,5% abaixo do total, mas bate (0,998) descontada a tesouraria; KLBN11 e ENGI11 batem pela razão da unit.
- **Fora do padrão e sem relação com a pergunta 12 (HIPÓTESE; não investigado):** EGIE3 com 1.416 mi de ações no Fundamentus contra 1.142 mi na CVM (+24%); VALE3 +4,3% e AXIA3 −3,9%. Registrado como pergunta 16 (seções 8 e 9).

### 11.5 CSAN3 decomposta (R$ por ação; ações 3,9666 bi)

| Item | Valor |
|---|---|
| Valor da empresa (FCD antes da dívida) | R$ 166,37 bi (R$ 41,94 por ação) |
| Dívida líquida (Fundamentus) | R$ 47,53 bi (R$ 11,98 por ação) |
| Valor do acionista (FCD atual) | R$ 118,84 bi = **R$ 29,96 por ação** |
| Não controladores (valor contábil) | R$ 26,94 bi (R$ 6,79 por ação; 84,4% do PL total) |
| PL total / PL dos controladores | R$ 31,91 bi / R$ 4,97 bi |
| Preço | R$ 3,72 (preço de partida desta pergunta; R$ 3,98 no `screener.csv` de 03/10) |

Distância de R$ 26,24 entre o FCD (29,96) e o preço (3,72), por fator, na ordem de aplicação (os dois efeitos não dependem da ordem, porque o desconto dos não controladores é uma subtração fixa por ação):

| Fator | Efeito no FCD por ação | Parte da distância |
|---|---|---|
| Pesos do WACC com o PL total no lugar do PL dos controladores (índice 9,57 para 1,49; WACC de 11,96% para 17,04%) | −18,15 (29,96 para 11,81) | 69% |
| Subtrair os não controladores pelo valor contábil | −6,79 (para 5,02) | 26% |
| Número de ações (descontando a tesouraria) | +0,17, em sentido contrário | — |
| **Restante** em relação ao preço (5,02 contra 3,72) | 1,30 | 5% |

Nenhum dos fatores acima mexe no fluxo de caixa projetado. A hipótese do número de ações **não** explica a distância. A subtração dos não controladores explica cerca de um quarto, e o **maior fator é o peso da dívida no WACC**, que decorre de a mesma base de patrimônio (controladores) ser usada para ponderar uma dívida consolidada.

### 11.6 Duas formas de ajuste, com a função existente

Calculadas importando `calcular_valor_justo_fcd` sem alteração: o ajuste **A** passa `divida_liquida + não controladores` (valor contábil de 30/06/2026) como dívida a deduzir; o **B** multiplica o FCD atual pela fração do lucro de 2025 atribuída aos controladores (3.11.01 ÷ 3.11, DRE consolidada da DFP). Para comparação, a coluna **C** só troca o índice dos pesos do WACC para dívida líquida ÷ PL total, e a coluna **A + patrimônio total nos pesos do WACC** (A+C) aplica os dois, também com a função existente importada sem alteração. R$ por ação, preços do `screener.csv` de 03/10/2026:

| Ticker | Preço | FCD atual | A (não controladores) | B (fração do lucro) | Fração do lucro dos controladores | C (WACC com PL total) | A + patrimônio total nos pesos do WACC |
|---|---|---|---|---|---|---|---|
| CSAN3 | 3,98 | 29,96 | 23,17 | 28,57 | 95,4% (prejuízo) | 11,81 | 5,02 |
| GOAU4 | 11,24 | 0,50 | −25,63 | 0,17 | 33,7% | −0,15 | −26,28 |
| KLBN11 | 18,02 | 48,51 | 43,31 | 0,00 | 0% (linhas zeradas) | 41,62 | 36,42 |
| BEEF3 | 3,92 | 38,43 | 37,82 | 36,72 | 95,5% | 36,24 | 35,64 |
| CURY3 | 27,30 | 34,36 | 33,08 | 31,00 | 90,2% | 34,36 | 33,08 |
| MBRF3 | 16,78 | 30,99 | 29,25 | 14,55 | 47,0% | 28,40 | 26,66 |
| ENGI11 | 53,37 | −63,11 | −70,03 | −44,51 | 70,5% | −63,21 | −70,13 |
| DIRR3 | 10,03 | 2,42 | 1,63 | 1,95 | 80,6% | 2,35 | 1,57 |
| USIM5 | 7,13 | 4,58 | 2,27 | 4,84 | 105,8% (prejuízo dos minoritários) | 4,58 | 2,27 |
| MRVE3 | 5,44 | −14,13 | −15,24 | −14,12 | 100% (prejuízo) | −14,15 | −15,25 |
| UGPA3 | 38,19 | 24,08 | 22,23 | 23,25 | 96,5% | 23,43 | 21,58 |

**Casos em que o resultado combinado (A + patrimônio total nos pesos do WACC) fica negativo:** GOAU4 (−26,28), ENGI11 (−70,13) e MRVE3 (−15,25).

- **GOAU4:** é o único em que o ajuste muda o sinal (FCD atual de R$ 0,50 para −26,28). O valor do acionista no FCD é de apenas R$ 0,66 bi (0,50 por ação × 1.322,7 mi de ações), e os não controladores valem R$ 34,56 bi no balanço (R$ 26,13 por ação), cerca de 52 vezes mais. O balanço consolidado é o da Metalúrgica Gerdau (denominação na CVM; a Gerdau S.A., GGBR4, também está no universo), com 64% do patrimônio em não controladores: subtrair o valor contábil dos minoritários de um fluxo desse tamanho dá um valor sem sentido econômico, porque a responsabilidade do acionista é limitada e a ação não vale menos que zero. A tela já tem o aviso "Valor justo zero ou negativo" para esses casos.
- **ENGI11 e MRVE3:** já eram negativos (−63,11 e −14,13) e continuam; a dedução soma −6,9 e −1,1 por ação, e a causa do sinal vem do fluxo e da dívida, não dos minoritários.
- **Decisão em aberto (não tomada aqui):** se o valor negativo deve ser mostrado como está, com o aviso, ou limitado a zero. A recomendação do A não depende disso.
- **CSAN3** fica positivo com o ajuste combinado (R$ 5,02 contra o preço de R$ 3,98).

**Recomendação: A (subtrair o valor contábil dos não controladores junto com a dívida líquida).**

- **Motivo:** o fluxo e o valor da empresa são consolidados, então a parte dos minoritários tem de sair do mesmo jeito que a dívida; é um dado de balanço padronizado (conta 2.03.09), disponível para todas as empresas com FCD e na mesma data-base da dívida, sem depender do sinal do lucro.
- **Limitações do A:** usa o valor **contábil**, que costuma ser menor que o de mercado dos minoritários (na CSAN3, Rumo e Compass; a subtração tende a ficar curta); pode deixar o valor muito negativo quando os não controladores são grandes e o fluxo pequeno (GOAU4 vai de 0,50 para −25,63); e só entra na dedução, sem ajustar o peso do WACC.
- **Limitações do B:** depende do lucro de **um** ano e perde o sentido com prejuízo (CSAN3, MRVE3 e USIM5 dão frações de 95%, 100% e 106%, que não representam participação nenhuma); na KLBN11 a CVM publica as linhas "atribuído a controladores e a não controladores" zeradas, e o B zera o valor; multiplica o valor do acionista (já depois da dívida) por uma fração do lucro, em vez de retirar a parte dos minoritários do valor da empresa; e a fração do lucro nem sempre acompanha a do patrimônio (MBRF3: 47% do lucro e 83% do patrimônio são dos controladores).
- **Pesos do WACC (achado desta investigação; precisa de decisão à parte):** a coluna C mostra que corrigir o denominador do índice Dív Líq / Patrim (patrimônio total no lugar do dos controladores) pesa mais que o ajuste A nas empresas com muitos minoritários (CSAN3 −18,15 contra −6,79; KLBN11 −6,89 contra −5,20; BEEF3 −2,19 contra −0,61). É o complemento coerente do A (registrado como pergunta 15, seções 8 e 9): dívida e minoritários saem do valor da empresa, e o custo de capital passa a ser ponderado pela estrutura consolidada. É uma decisão separada do A.

### 11.7 Confirmado e hipóteses

**Dependência comum de dados.** O ajuste A, a pergunta 15 (pesos do WACC com o patrimônio total) e o arrendamento como dívida (pergunta 2, etapa seguinte à alt3) dependem do mesmo dado novo: o balanço consolidado da CVM (BPP) na data-base da dívida do Fundamentus de cada empresa (coluna `data_balanco_fundamentus`, hoje 30/06/2026). Os três devem ser implementados sobre **uma única leitura** do ITR/DFP, por exemplo uma função que devolve, para uma empresa e uma data, o patrimônio líquido total (2.03), a participação dos não controladores (2.03.09 ou a conta equivalente, identificada pela descrição) e o passivo de arrendamento, em vez de três leituras separadas do mesmo zip.

**CONFIRMADO no código:** a única dedução entre o valor da empresa e o valor por ação é a dívida líquida (`fcd.py:357-359`); a participação dos não controladores não é subtraída em lugar nenhum de `src/`; os pesos do WACC usam o índice Dív Líq / Patrim do Fundamentus (`fcd.py:175-185`, `:198`).

**CONFIRMADO nos dados (CVM e Fundamentus de 30/06/2026):** o "Patrim. Líq" e o índice do Fundamentus usam o patrimônio dos controladores (51 de 51 empresas não financeiras com não controladores; índice = dívida líquida ÷ PL dos controladores nas 53 com FCD); 11 empresas com FCD passam de 10% de não controladores, com a CSAN3 em 84,4%; o número de ações da CSAN3 do Fundamentus é igual ao da CVM nas três datas disponíveis (31/12/2025, 31/03/2026 e 30/06/2026); a decomposição da seção 11.5.

**HIPÓTESE (não testada):** o valor de mercado dos minoritários da CSAN3 (Rumo e Compass) é maior que o contábil de R$ 26,9 bi; um aumento de capital da Cosan depois de 30/06/2026; as diferenças de número de ações de EGIE3, VALE3 e AXIA3; e a origem do restante de R$ 1,30 da CSAN3 contra o preço (por exemplo, premissas de fluxo e crescimento, ver seção 5).


---

## 12. Pergunta 16: número de ações (03/10/2026)

Investigação só de leitura; nada no código, nos testes ou em `data/` foi alterado. Scripts e dados em `%TEMP%\investigacao_p16`. Fontes: composição do capital da CVM em 7 datas (DFP 2024 e 2025; ITR de 2025 e de 2026, de 31/12/2024 a 30/06/2026; para o ITR de 2025 foi baixado o zip, 31,7 MB); páginas e caches do Fundamentus de 03/10/2026; coluna "Stock Splits" do histórico de 1 ano do Yahoo; balanço consolidado (BPP) do ITR de 30/06/2026; fontes externas, listadas em 12.3 (as páginas que não puderam ser abertas estão marcadas).

### 12.1 De onde vem o número e onde é usado (CONFIRMADO no código)

- **Origem:** campo "Nro. Ações" do Fundamentus (`config.py:245`), convertido para a base da cotação nas units por `_numero_acoes_na_base_da_cotacao` (`fundamentus.py:119-136`, chamada em `fundamentus.py:150-154`): divide o número pelo fator `Nro. Ações × Cotação ÷ Valor de mercado`, que deve ser inteiro (tolerância de 2%, `config.py:232`), senão o número fica indisponível. O site não informa a data a que o número se refere.
- **Onde é usado:** o FCD por ação (`fcd.py:307` valida, `fcd.py:363` divide; chamadas em `app/main.py:1032` e `screener.py:460`) e o valor de mercado e valor da firma (`app/main.py:1301` para `empresa/valor_mercado.py:29-30`, preço × número de ações).
- **Graham e Bazin não usam o número diretamente.** O Graham usa o LPA e o VPA do Fundamentus, mas esses são calculados sobre o mesmo número (CONFIRMADO nos dados: VPA × número de ações = patrimônio dos controladores, e LPA × número de ações = lucro dos 12 meses até 30/06/2026, com razão entre 0,99 e 1,01 nas 23 divergentes que dá para conferir; KLBN11 e ASAI3 não dá para conferir o LPA), então o Graham muda na mesma proporção do número. O Bazin usa os dividendos por ação do Yahoo e o preço do Yahoo, na mesma base por ação, e não depende do número.
- **O número inclui as ações em tesouraria?** Na maioria, sim: 68 das 76 ações ficam a menos de 1% do capital integralizado da CVM (que inclui a tesouraria), contra 51 das 76 a menos de 1% do número em circulação (integralizado menos tesouraria).

### 12.2 Comparação nas 76 ações (CONFIRMADO nos dados)

Referência: composição do capital do ITR de 30/06/2026, em ações ordinárias, preferenciais e tesouraria, com o **número em circulação** (integralizado menos tesouraria) como referência principal. Dois cuidados: em 22 empresas a CVM informa a composição em milhares (razão de 1.000 contra o Fundamentus), o que foi normalizado; e nas units o número do app está na base da unit, então a comparação usa o fator de ações por unit (KLBN11 e ENGI11, 5; IGTI11, 4; TAEE11 e BPAC11, 3; SANB11, 2). Sinal: **positivo = Fundamentus maior que a CVM.** Datas: a CVM é de 30/06/2026; o do Fundamentus não é informado pelo site e, como mostra 12.3, em vários casos é posterior a 30/06.

51 das 76 ficam a menos de 1% do número em circulação. As **25 que passam de 1%** (milhões de ações; "Grupo" explicado em 12.3):

| Ticker | ON (mi) | PN (mi) | Tesouraria (mi) | Integralizado CVM (mi) | Em circulação CVM (mi) | Fundamentus (mi) | vs. em circulação | vs. integralizado | FCD aplicável | Grupo |
|---|---|---|---|---|---|---|---|---|---|---|
| ASAI3 | 1.353,5 | 0,0 | 15,1 | 1.353,5 | 1.338,4 | 1.354,4 | +1,2% | +0,1% | sim | A |
| KLBN11 | 2.312,8 | 3.928,7 | 88,6 | 6.241,5 | 6.152,9 | 6.241,5 | +1,4% | +0,0% | sim | A |
| ENEV3 | 1.937,0 | 0,0 | 24,0 | 1.937,0 | 1.913,0 | 1.944,4 | +1,6% | +0,4% | não | A |
| RENT3 | 1.082,6 | 41,6 | 19,6 | 1.124,3 | 1.104,6 | 1.124,3 | +1,8% | +0,0% | sim | A |
| USIM5 | 705,3 | 547,8 | 22,1 | 1.253,1 | 1.230,9 | 1.253,1 | +1,8% | +0,0% | sim | A |
| AZZA3 | 206,5 | 0,0 | 4,3 | 206,5 | 202,2 | 206,5 | +2,1% | +0,0% | sim | A |
| UGPA3 | 1.115,8 | 0,0 | 25,1 | 1.115,8 | 1.090,7 | 1.115,8 | +2,3% | +0,0% | sim | A |
| SUZB3 | 1.264,1 | 0,0 | 31,0 | 1.264,1 | 1.233,1 | 1.264,1 | +2,5% | +0,0% | sim | A |
| CEAB3 | 308,2 | 0,0 | 8,2 | 308,2 | 300,0 | 308,2 | +2,7% | -0,0% | sim | A |
| RDOR3 | 2.240,3 | 0,0 | 60,1 | 2.240,3 | 2.180,2 | 2.240,3 | +2,8% | -0,0% | sim | A |
| COGN3 | 2.064,3 | 0,0 | 63,0 | 2.064,3 | 2.001,2 | 2.064,3 | +3,2% | +0,0% | sim | A |
| EMBJ3 | 740,5 | 0,0 | 28,6 | 740,5 | 711,8 | 740,5 | +4,0% | +0,0% | sim | A |
| CYRE3 | 384,0 | 69,4 | 17,7 | 453,4 | 435,8 | 453,4 | +4,1% | +0,0% | não | A |
| MULT3 | 513,2 | 0,0 | 22,1 | 513,2 | 491,0 | 513,2 | +4,5% | +0,0% | sim | A |
| LREN3 | 1.006,8 | 0,0 | 45,6 | 1.006,8 | 961,3 | 1.006,8 | +4,7% | -0,0% | sim | A |
| HAPV3 | 502,6 | 0,0 | 27,5 | 502,6 | 475,1 | 502,6 | +5,8% | +0,0% | sim | A |
| YDUQ3 | 274,1 | 0,0 | 19,6 | 274,1 | 254,4 | 274,1 | +7,7% | +0,0% | sim | A |
| PRIO3 | 872,5 | 0,0 | 74,3 | 872,5 | 798,2 | 872,5 | +9,3% | -0,0% | sim | A |
| ISAE4 | 238,2 | 420,7 | 0,0 | 658,9 | 658,9 | 703,3 | +6,7% | +6,7% | não | B |
| EGIE3 | 1.142,3 | 0,0 | 0,0 | 1.142,3 | 1.142,3 | 1.416,4 | +24,0% | +24,0% | sim | B |
| VALE3 | 4.255,8 | 0,0 | 183,4 | 4.255,8 | 4.255,8 | 4.439,2 | +4,3% | +4,3% | sim | C |
| AXIA3 | 2.337,0 | 606,2 | 75,9 | 2.943,2 | 2.867,3 | 2.828,6 | -1,3% | -3,9% | sim | D |
| IGTI11 | 771,0 | 435,4 | 1,8 | 1.206,4 | 1.204,6 | 1.186,9 | -1,5% | -1,6% | não | E |
| TOTS3 | 599,4 | 0,0 | 26,2 | 599,4 | 573,2 | 579,4 | +1,1% | -3,3% | sim | E |
| TEND3 | 122,6 | 0,0 | 65,1 | 122,6 | 122,5 | 122,6 | +0,1% | +0,0% | sim | F |

Nota para VALE3 e TEND3: na VALE3 o integralizado de 2026 já vem líquido da tesouraria (ver 12.3), então o "em circulação" é o próprio integralizado; na TEND3, a tesouraria de 65.148 da CVM está em ações, não em milhares (ver 12.3), e o "em circulação" usa 0,065 milhão.

### 12.3 Causas

**Grupo A, tesouraria (18 ações: ASAI3, KLBN11, ENEV3, RENT3, USIM5, AZZA3, UGPA3, SUZB3, CEAB3, RDOR3, COGN3, EMBJ3, CYRE3, MULT3, LREN3, HAPV3, YDUQ3, PRIO3).** O Fundamentus é igual ao capital integralizado da CVM (diferença abaixo de 0,5%), então inclui a tesouraria, de 1,1% (ASAI3) a 8,5% (PRIO3) do capital. Para todas, a divergência é só a tesouraria (CONFIRMADO).

**Grupo B, oferta de ações depois do balanço (EGIE3 e ISAE4).**
- **EGIE3 (+24,0%).** A CVM mostra 815,928 mi de ações até 30/09/2025 e 1.142,299 mi desde 31/12/2025: bonificação de 40% (1 ação nova para cada 2,5; data ex em 27/11/2025), que o Yahoo também registra como split de 1,4 em 27/11/2025 (CONFIRMADO). O número do Fundamentus, 1.416,38 mi, é igual a 1.142,299 mi mais 274,083 mi de ações novas de uma oferta primária aprovada em 14/07/2026 (274.082.684 ações a R$ 30,50, cerca de R$ 8,36 bi, com total de 1.416.381.520 ações), posterior ao ITR de 30/06/2026. A coincidência é exata e a causa fica CONFIRMADA; os dados da oferta vêm de resultado de busca (a página abaixo respondeu 403 quando aberta): <https://br.advfn.com/jornal/2026/07/engie-brasil-precifica-oferta-de-acoes-em-r-30-50-e-capta-r-8-36-bilhoes-para-reforcar-capital-social>. A bonificação consta do fato relevante de 05/11/2025: <https://www.engie.com.br/wp-content/uploads/2025/11/251105-Fato-Relevante-Aumento-de-Capital-Bonificacao.pdf>.
- **ISAE4 (+6,7%).** A CVM mostra 658,883 mi de ações, sem mudança desde 2024 (só reclassificação entre ordinárias e preferenciais em 30/06/2026). O Fundamentus tem 703,328 mi, igual a 658,883 mi mais 44,445 mi de uma oferta de ações preferenciais a R$ 27,00 (cerca de R$ 1,2 bi; novas ações negociadas a partir de 27/07/2026; total de 703.327.748 segundo a notícia): <https://www.clubefiinews.com.br/acoes/isa-energia-brasil-aumenta-capital-oferta-publica-acoes-preco-27-reais> (resultado de busca; a página não foi aberta).

**Grupo C, VALE3 (+4,3%).** O conselho aprovou em março de 2026 o cancelamento de 99.847.816 ações em tesouraria, o que leva o capital social a 4.439.159.752 ações ordinárias (e 12 preferenciais especiais) e deixa 170.379.611 em tesouraria (resultado de busca; fontes: <https://br.advfn.com/jornal/2026/03/vale-cancela-quase-100-milhoes-de-acoes-em-tesouraria-e-reduz-base-acionaria-na-b3> e <https://www.seudinheiro.com/2026/bolsa-dolar/vale-vale3-cancela-acoes-mantidas-em-tesouraria-entenda-o-que-significa-para-o-acionista/>). O número do Fundamentus, 4.439,16 mi, é o **capital social total**, com a tesouraria dentro. Na CVM, o campo "integralizado" era 4.539,007 mi até 31/12/2025 (capital emitido, com 270,2 mi em tesouraria) e passou a 4.262,534 mi em 31/03/2026 e 4.255,763 mi em 30/06/2026: **este valor é o capital social menos a tesouraria** (4.439,160 − 183,397 = 4.255,763), ou seja, o campo "integralizado" da Vale já vem líquido a partir de 2026. Consequências: o número em circulação da Vale é 4.255,763 mi (o app está 4,3% acima), e subtrair a tesouraria do "integralizado" da CVM descontaria duas vezes (−4,3%).

**Grupo D, AXIA3 (−1,3%).** O integralizado da CVM foi de 2.915,4 mi (31/12/2025, com 886,9 mi de preferenciais) para 2.943,2 mi (30/06/2026: 2.337,0 mi ordinárias e 606,2 mi preferenciais, depois da conversão das preferenciais A1 e B1 em ordinárias, na razão de 1,1 para 1, em 05/06/2026). Em 16/09/2026 a Axia concluiu a terceira fase do programa de conversão e resgate das preferenciais classe C: 69.886.551 convertidas e 41.648.420 resgatadas e canceladas, com total de 2.874.657.070 ações (2.417.135.038 ordinárias e 457.522.031 preferenciais C): <https://www.suno.com.br/noticias/axia-energia-axia3-resgate-conversao-pncs-mt/> (página aberta). O número do Fundamentus, 2.828,64 mi, não coincide com nenhuma data da CVM; está 46,0 mi abaixo do total de 16/09/2026. **HIPÓTESE:** é a contagem posterior a 16/09 descontada a tesouraria (não confirmada).

**Grupo E (HIPÓTESE, não investigados a fundo).** TOTS3 (+1,1%): o Fundamentus (579,40 mi) fica a 0,08% do número em circulação de 31/03/2026 (579,85 mi) e não do de 30/06 (573,2 mi). IGTI11 (−1,5%, sem FCD): o fator de 4 ações por unit pode estar um pouco fora (a conversão exige fator inteiro).

**Grupo F, TEND3 (erro de dado da CVM, CONFIRMADO).** O ITR de 30/06/2026 (versão 2) informa tesouraria de 65.148 em um capital de 122.578 (ambos supostamente em milhares), o que seria 53% do capital, contra zero em 31/03/2026. Mas o balanço do mesmo ITR mostra "Ações em Tesouraria" de apenas R$ 1,9 milhão, o que dá R$ 0,03 por ação se forem 65,1 milhões de ações e R$ 29,8 por ação (perto do preço de R$ 27 a R$ 28) se forem **65.148 ações**. A tesouraria está em ações e não em milhares: o número em circulação é cerca de 122,5 mi, igual ao do Fundamentus. Usar o campo sem cuidado cortaria o número em 53% e dobraria o valor por ação.

### 12.4 Coerência com o preço (CONFIRMADO nos dados)

O preço usado é o último fechamento do Yahoo (preço nominal do dia, sem ajuste, 01/10/2026 no `screener.csv`; a cotação que aparece no Fundamentus é de 02/10/2026). Eventos no histórico de 1 ano do Yahoo (coluna "Stock Splits"): MGLU3 1,05 (30/12/2025), POMO4 1,1 e COGN3 1,1 (26/12/2025), KLBN11 1,01, ITSA4 1,02, ITUB4 1,03, RADL3 1,02, GOAU4 1,3333, ENGI11 1,1, VBBR3 1,0711, EGIE3 1,4 (27/11/2025) e SBSP3 (1,0296 em 26/12/2025, 1,0016 em 20/03/2026 e 5,0 em 29/04/2026). Para essas ações, o número do Fundamentus e o da CVM estão na mesma base do preço (a menos de 1% do integralizado), com duas exceções, ambas por oferta posterior ao balanço:

- **EGIE3 e ISAE4:** o número de ações e o preço são posteriores à oferta, mas a dívida líquida, o patrimônio e o fluxo são de 30/06/2026, sem o caixa captado. O FCD e o Graham ficam subavaliados por isso. Na EGIE3, o valor do acionista no FCD é R$ 10,52 bi (7,43 × 1.416,38 mi); somando os R$ 8,36 bi captados (HIPÓTESE: o caixa entra inteiro na dívida líquida, sem contar o uso dos recursos), o valor por ação seria R$ 13,33, contra R$ 7,43 hoje e R$ 9,21 com o número de 30/06.
- **Os demais:** nenhum tem número e preço em bases diferentes; a divergência vem só da tesouraria ou de um erro de dado.

### 12.5 Efeito por método (CONFIRMADO com a função existente)

Recalculado com `calcular_valor_justo_fcd` e `calcular_valor_justo_graham` importadas sem alteração, com o número em circulação da CVM de 30/06/2026 (VALE3: o próprio integralizado; TEND3: tesouraria de 0,065 mi; AXIA3 e demais: integralizado menos tesouraria). No Graham, LPA e VPA são multiplicados pela razão entre o número do Fundamentus e o da CVM. **O Bazin não muda** (dividendos por ação e preço do Yahoo), então **FCD e Graham ficam, hoje, subavaliados em relação ao Bazin** nas ações com tesouraria ou oferta posterior, e todos os três ficam coerentes entre si com o número da CVM de 30/06. Ordenado pelo tamanho da divergência (razão = Fundamentus ÷ referência; potencial em %):

| Ticker | Fundamentus ÷ referência | FCD atual → novo | Graham atual → novo | Bazin (inalterado) | Valor combinado atual → novo | Potencial atual → novo |
|---|---|---|---|---|---|---|
| EGIE3 | 1.240 | 7,43 → 9,21 | 25,84 → 32,04 | 18,59 | 17,29 → 19,95 | -41,1% → -32,0% |
| PRIO3 | 1.093 | 32,64 → 35,67 | 56,78 → 62,06 | — | 44,71 → 48,87 | -27,3% → -20,5% |
| YDUQ3 | 1.077 | 35,76 → 38,52 | 9,91 → 10,67 | 9,49 | 18,38 → 19,56 | +66,5% → +77,2% |
| ISAE4 | 1.067 | — | 53,32 → 56,92 | — | 53,32 → 56,92 | +92,7% → +105,7% |
| HAPV3 | 1.058 | -0,63 → -0,67 | — | — | -0,63 → -0,67 | -109,1% → -109,7% |
| LREN3 | 1.047 | 26,28 → 27,52 | 18,52 → 19,40 | 15,34 | 20,05 → 20,75 | +74,9% → +81,1% |
| MULT3 | 1.045 | 1,32 → 1,38 | 28,27 → 29,55 | 19,35 | 16,32 → 16,76 | -48,9% → -47,5% |
| VALE3 | 1.043 | -2,28 → -2,38 | 48,29 → 50,38 | 93,54 | 46,52 → 47,18 | -33,9% → -33,0% |
| CYRE3 | 1.041 | — | 49,94 → 51,96 | 45,50 | 47,72 → 48,73 | +75,9% → +79,6% |
| EMBJ3 | 1.040 | 21,21 → 22,06 | 41,40 → 43,06 | — | 31,30 → 32,56 | -67,7% → -66,4% |
| COGN3 | 1.032 | 5,64 → 5,82 | 7,13 → 7,36 | — | 6,39 → 6,59 | +173,0% → +181,6% |
| RDOR3 | 1.028 | -3,16 → -3,25 | 21,15 → 21,74 | 70,13 | 29,37 → 29,54 | -23,4% → -23,0% |
| CEAB3 | 1.027 | 17,82 → 18,31 | 22,48 → 23,10 | — | 20,15 → 20,70 | +103,7% → +109,3% |
| SUZB3 | 1.025 | 105,99 → 108,65 | 75,59 → 77,49 | — | 90,79 → 93,07 | +109,9% → +115,1% |
| UGPA3 | 1.023 | 24,08 → 24,63 | 33,50 → 34,27 | 33,33 | 30,30 → 30,75 | -20,6% → -19,5% |
| AZZA3 | 1.021 | 53,50 → 54,64 | 37,09 → 37,88 | 41,27 | 43,95 → 44,60 | +136,2% → +139,6% |
| USIM5 | 1.018 | 4,58 → 4,66 | — | — | 4,58 → 4,66 | -35,8% → -34,7% |
| RENT3 | 1.018 | 62,98 → 64,10 | 40,68 → 41,40 | 35,49 | 46,38 → 47,00 | +15,3% → +16,8% |
| ENEV3 | 1.016 | — | 10,85 → 11,03 | — | 10,85 → 11,03 | -61,4% → -60,8% |
| IGTI11 | 0.985 | — | 28,37 → 27,96 | — | 28,37 → 27,96 | +3,8% → +2,3% |
| KLBN11 | 1.014 | 48,51 → 49,21 | 8,77 → 8,90 | 19,35 | 25,55 → 25,82 | +41,8% → +43,3% |
| AXIA3 | 0.987 | 45,30 → 44,69 | 64,36 → 63,49 | 31,49 | 47,05 → 46,56 | -14,7% → -15,6% |
| ASAI3 | 1.012 | 36,46 → 36,89 | 8,66 → 8,76 | — | 22,56 → 22,82 | +102,1% → +104,5% |
| TOTS3 | 1.011 | 32,85 → 33,20 | 22,83 → 23,08 | 11,33 | 22,34 → 22,54 | -35,3% → -34,7% |
| TEND3 | 1.001 | 16,28 → 16,28 | 36,52 → 36,54 | — | 26,40 → 26,41 | -3,9% → -3,8% |

O efeito no valor combinado vai de +0,1% (TEND3) a +15,4% na EGIE3 (17,29 para 19,95) e +9,3% na PRIO3 (44,71 para 48,87); em nenhuma das 25 o sinal do valor combinado muda. AXIA3 (−1,1%) e IGTI11 (−1,5%) são as únicas com redução.

### 12.6 Proposta

1. **Qual número usar:** ações **em circulação** (capital integralizado menos tesouraria) da composição do capital do ITR ou DFP mais recente, na **mesma data-base do balanço** usado para a dívida líquida e o patrimônio (a coluna `data_balanco_fundamentus`, hoje 30/06/2026). Assim FCD, Graham, valor de mercado e valor da firma ficam coerentes entre si e com a dívida e o patrimônio.
2. **Units:** manter o tratamento atual (P06): o número da CVM é dividido pelo fator inteiro de ações por unit calculado com os dados do Fundamentus (`Nro. Ações × Cotação ÷ Valor de mercado`), e fator não inteiro continua deixando o número indisponível.
3. **Graham:** reescalar LPA e VPA do Fundamentus pela razão entre o número do Fundamentus e o da CVM (verificado em 12.1), ou recalculá-los com os dados da mesma leitura (lucro dos 12 meses e patrimônio dos controladores ÷ número em circulação).
4. **Salvaguardas** (os dados mostraram os três problemas): (a) **escala:** se a razão contra o Fundamentus ficar perto de 1.000, dividir a composição por 1.000 (22 empresas); (b) **tesouraria improvável:** se a tesouraria passar de 20% do capital (TEND3: 53%), não usar o campo, cair no número do Fundamentus e registrar o motivo; (c) **integralizado já líquido** (VALE3 em 2026): se integralizado mais tesouraria for igual ao número do Fundamentus (diferença menor que 0,5%), tratar o integralizado como o número em circulação; (d) **divergência acima de 2%** entre o número final e o do Fundamentus: registrar a causa provável (oferta ou conversão depois do balanço) e manter o número de 30/06.
5. **Eventos depois do balanço (EGIE3, ISAE4):** com o número de 30/06, o valor por ação fica coerente com a dívida e o patrimônio de 30/06 (e aproximadamente igual ao valor pós-oferta quando as ações novas são emitidas perto do valor da ação), sem o efeito da oferta feita a preço diferente do valor. Fica como limitação conhecida (rascunho na seção 7).
6. **A leitura do ITR planejada na seção 11.7 pode trazer o número de ações.** O arquivo de composição do capital (`itr_cia_aberta_composicao_capital_2026.csv`) está no mesmo zip do balanço e da DRE, tem a mesma data-base e a mesma versão mais recente, e separa ordinárias, preferenciais e tesouraria. Uma única função poderia devolver, para uma empresa e uma data, o patrimônio total, os não controladores, o passivo de arrendamento e o número de ações em circulação. **É melhor que o Fundamentus para a coerência** (data-base igual à da dívida e do patrimônio, fonte oficial, tesouraria separada), com custos: a escala heterogênea, o campo ambíguo da Vale e a defasagem de até um trimestre para eventos recentes. O Fundamentus fica como verificação cruzada.

### 12.7 Confirmado e hipóteses

**CONFIRMADO no código:** origem, conversão e usos do número (12.1).

**CONFIRMADO nos dados:** 51 das 76 ações a menos de 1% do número em circulação e 25 acima; o Fundamentus inclui a tesouraria na maioria (68 de 76 a menos de 1% do integralizado); LPA e VPA do Fundamentus são calculados sobre o mesmo número; bonificação da EGIE3 (CVM e Yahoo); número do EGIE3 e do ISAE4 iguais ao total posterior às ofertas; VALE3 igual ao capital social total, com o "integralizado" da CVM de 2026 já líquido; erro de escala na tesouraria da TEND3 (incoerência com o balanço); efeitos de 12.5.

**CONFIRMADO por fonte externa (resultados de busca, páginas indicadas em 12.3):** oferta de ações da EGIE3 (14/07/2026) e da ISAE4 (julho/2026), cancelamento de ações da Vale (março/2026), conversão e resgate de PNC da AXIA3 (16/09/2026, única página aberta).

**HIPÓTESE (não confirmada):** o número da AXIA3 do Fundamentus ser a contagem de 16/09/2026 descontada a tesouraria; o número da TOTS3 ser o em circulação de 31/03/2026; o fator de unit do IGTI11; o caixa da oferta da EGIE3 entrar integralmente na dívida líquida (pro forma de R$ 13,33).


## 13. Pergunta 17: fator de unit (04/10/2026)

Investigação só de leitura; nada no código, nos testes ou em `data/` foi alterado. Scripts e dados em `%TEMP%\investigacao_p17` (`efeito.py`, `cvm_capital.json`). Estendida a todas as units do Ibovespa. Cálculos com as funções do projeto importadas sem alteração (`calcular_acoes_em_circulacao`, `reescalar_lpa_vpa`, `calcular_valor_justo_graham`, `calcular_valor_mercado_e_firma`), sobre os caches de 04/10/2026 (indicadores do Fundamentus e composição do capital do ITR de 30/06/2026). A réplica reproduz o Graham do `screener.csv` nas seis units (diferença 0).

**Resumo.** O fator 7 da IGTI11 **não é erro**: é o peso econômico da unit (1 ordinária + 2 preferenciais que valem 3 vezes a ordinária = 1 + 2×3 = 7 ações ordinárias equivalentes). O Fundamentus divide as ações ordinárias equivalentes (771,0 mi + 3 × 435,4 mi = 2.077,1 mi) por 7 e chega às 296,7 mi do app, que é a base certa para o valor por unit. O que não bate com a CVM é só a conversão do P06, que divide a contagem física de ações (1.206 mi) pelo fator e chega a 172,1 mi; por isso a salvaguarda descarta o número da CVM e o app fica com o do Fundamentus, que é o correto. Hoje o resultado é certo (Graham R$ 28,37); o que está errado é o motivo mostrado na tela ("provável erro de escala ou de fator de unit"). Trocar o fator para 3 estragaria o valor de mercado (R$ 19,7 bi, 2,3 vezes o correto).

### 13.1 Como o fator é obtido e onde é usado (CONFIRMADO no código)

- **Obtenção:** `_fator_acoes_por_cotacao` (`fundamentus.py:119-136`) calcula `Nro. Ações × Cotação ÷ Valor de mercado` e aceita o fator se for inteiro dentro de `TOLERANCIA_FATOR_ACOES_POR_COTACAO` (2%, `config.py:221`); senão, `None`, nunca aproximado. `_numero_acoes_na_base_da_cotacao` (`fundamentus.py:139-147`) divide o número do Fundamentus pelo fator. `_montar_indicadores` guarda os dois (`fundamentus.py:163-170`): `acoes_por_cotacao` (o fator) e `numero_acoes` (já em units equivalentes). Nas 76 ações, 70 têm fator 1 e seis têm fator maior (as seis units); nenhuma ficou com fator `None`.
- **O fator não vem de uma tabela de composição:** ele sai da identidade entre o número de ações, a cotação e o valor de mercado do Fundamentus, então carrega o peso econômico que o Fundamentus usar (na IGTI11, 7, não 3).
- **Número de ações da CVM convertido para units:** `calcular_acoes_em_circulacao` (`balanco_cvm.py:281`) multiplica o número do Fundamentus pelo fator (`balanco_cvm.py:315-316`), compara com a composição da CVM (integralizado menos tesouraria) e divide a composição pelo mesmo fator (`balanco_cvm.py:374`). Divergência acima de 50% (`LIMITE_DIVERGENCIA_ACOES_IMPLAUSIVEL`) descarta a CVM e mantém o Fundamentus (`balanco_cvm.py:353-364`, texto em `config.py:563-566`).
- **Usos:** Graham: `reescalar_lpa_vpa` (`graham.py:20-40`) troca LPA e VPA do Fundamentus pelo número em circulação da CVM (chamada em `screener.py:441-443` e `app/main.py:1137`); FCD por ação: `numero_acoes` do Fundamentus ou o em circulação da CVM (`fcd.py:467-480`, chamadas em `screener.py:488` e `app/main.py:1152`); valor de mercado: `calcular_valor_mercado_e_firma` (`empresa/valor_mercado.py:33`), com o em circulação da CVM quando existe e o do Fundamentus senão (`app/main.py:1443-1445`); Bazin: não usa o número de ações, só os dividendos por unit do Yahoo e o preço da unit (`bazin.py:60`, `screener.py:372`).
- **LPA e VPA do Fundamentus estão na mesma base das units equivalentes (CONFIRMADO nos dados):** IGTI11, VPA 16,64 × 296,73 mi = R$ 4.937,6 mi, contra o patrimônio líquido de R$ 4.937,1 mi do balanço; KLBN11, 7,60 × 1.248,3 mi = R$ 9.486,8 mi, igual ao patrimônio do balanço.

### 13.2 As seis units: composição real, fator do app e efeito no Graham

Units entre as 76 ações: SANB11, KLBN11, IGTI11, TAEE11, BPAC11 e ENGI11. Fontes consultadas em 04/10/2026 (páginas abertas, salvo indicação):

| Unit | Composição real | Fonte | Fator do app | Bate? | Graham do app → com a conversão certa |
|---|---|---|---|---|---|
| IGTI11 | 1 ON + 2 PN; a PN vale 3 vezes a ON em direitos econômicos; o preço da ON é 1/7 do da unit | Fato Relevante da Iguatemi na B3, 09/09/2022 (<https://b3.com.br/data/files/E7/F5/85/E5/6C1338101E311E28AC094EA8/Fato%20Relevante%20-%20Iguatemi_09.09.pdf>): composição, "3 (três) vezes", "1/7" | 7 | **Bate pelo peso econômico (1 + 2×3 = 7); não bate pela contagem física (3)** | 28,37 → 28,40 a 28,45 (+0,1% a +0,3%) |
| KLBN11 | 1 ON + 4 PN; mesmos direitos econômicos | RI da Klabin, perguntas frequentes (<https://ri.klabin.com.br/en/for-the-investor/faq/>, sem data): composição e "mesmos direitos econômicos" | 5 | Sim | 8,90, sem mudança |
| TAEE11 | 1 ON + 2 PN | RI da Taesa, estrutura societária (<https://ri.taesa.com.br/en/corporate-governance/corporate-structure/>, nota de 29/10/2025): "1 Unit = 1 ON + 2 PN" e 590.714.069 ON + 442.782.652 PN | 3 | Sim | 49,88, sem mudança |
| ENGI11 | 1 ON + 4 PN | RI da Energisa, estrutura societária e perguntas frequentes (<https://ri.energisa.com.br/en/corporate-governance/shareholding-and-corporate-structure/>, tabela de 31/08/2026; <https://ri.energisa.com.br/en/servicos-de-ri/faq/>): 383.566.078 units em circulação | 5 | Sim | 51,26, sem mudança |
| SANB11 | 1 ON + 1 PN (a PN recebe dividendo 10% maior) | **Só resultado de busca**: documentos do Santander (<https://www.santander.com.br/document/wps/AGE_Bonificacao_Grupamento_Units.pdf>, que deu HTTP 403, e a página de governança do RI); **HIPÓTESE** | 2 | Sim (HIPÓTESE da composição) | 49,54, sem mudança relevante (com a PN em 1,1: +0,06% nas ações) |
| BPAC11 | 1 ON + 2 PN classe A | **Só fontes secundárias** (resultados de busca; as páginas do RI do BTG não abriram); **HIPÓTESE** | 3 | Sim (HIPÓTESE da composição) | 46,73, sem mudança |

Conferência com a CVM (CONFIRMADO nos dados, ITR de 30/06/2026; em milhões de ações): fator × número do Fundamentus é igual ao integralizado da CVM nas seis (SANB11 7.498,5, KLBN11 6.241,5, TAEE11 1.033,5, BPAC11 11.670,1, ENGI11 2.518,4); na IGTI11, 296,73 × 7 = 2.077,1 contra 1.206,4 de integralizado, e a diferença é exatamente o peso econômico: 771,0 + 3 × 435,4 = 2.077,1. SANB11 e TAEE11 informam a composição em milhares (o app já trata). Nas cinco que batem, o número do Fundamentus coincide com o integralizado da CVM (que inclui a tesouraria) e a conversão do P06 acerta, sem aviso.

**Efeito no Graham:** em cinco das seis o app já usa o fator correto e nada muda; só na IGTI11 há diferença, de 0,1% a 0,3% (R$ 28,37 contra R$ 28,40 a R$ 28,45, conforme a tesouraria seja de ordinárias ou de preferenciais). **Bazin:** coerente. Os dividendos do Yahoo são por unit (IGTI11: R$ 0,1685 a R$ 0,1690 por trimestre; KLBN11: de R$ 0,04 a R$ 0,90 por pagamento; ENGI11 e TAEE11 na ordem de R$ 0,5 a R$ 1,7), na mesma base do preço da unit; o Bazin não usa número de ações. A IGTI11 não tem Bazin (sem 5 anos de dividendos). **HIPÓTESE:** que o Yahoo some corretamente 1 ON + 2 PN em cada pagamento da IGTI11 (não verificado contra o Iguatemi).

### 13.3 IGTI11 em detalhe

- **Composição (CONFIRMADO, fonte primária):** a unit é 1 ON + 2 PN. As PN dão 3 vezes os direitos econômicos das ON, e o preço por ON é 1/7 do preço da unit (Fato Relevante de 09/09/2022, acima). Capital depois do cancelamento de tesouraria (InfoMoney, 05/02/2025, <https://www.infomoney.com.br/mercados/iguatemi-igti11-cancela-acoes-em-tesouraria-e-aprova-nova-recompra-de-acoes/>): 770.992.429 ON + 435.368.756 PN = 1.206.361.185 ações, igual ao da CVM de 30/06/2026 (771,0 mi + 435,4 mi; tesouraria de 1,79 mi).
- **Por que o fator é 7 (CONFIRMADO nos números):** o Fundamentus pondera as ações pelos direitos econômicos: 770,99 + 3 × 435,37 = 2.077,1 mi ações ordinárias equivalentes, e 2.077,1 ÷ 7 = 296,73 mi, que é o número do app (valor de mercado ÷ cotação). Com isso, VPA × 296,73 mi = R$ 4.937,6 mi, o patrimônio líquido. **HIPÓTESE:** que o Fundamentus use essa ponderação por critério próprio de rateio; a coincidência numérica é exata, mas o site não a descreve.
- **Conversão da CVM para units:**

| Conversão do número da CVM (R$ por unit; 28,47 de preço) | Ações na base da unit (mi) | Razão ao app | Graham | Valor de mercado |
|---|---|---|---|---|
| A) App hoje (CVM descartada, vale o Fundamentus) | 296,73 | 1,000 | 28,37 (−0,3% vs preço) | R$ 8,45 bi |
| B) Peso econômico, tesouraria só de ON | 296,47 | 0,999 | 28,40 | R$ 8,44 bi |
| B') Peso econômico, tesouraria só de PN | 295,96 | 0,997 | 28,45 | R$ 8,43 bi |
| C) Contagem física, 3 ações por unit (1.204,6 ÷ 3) | 401,52 | 1,353 | 20,97 (−26,4%) | R$ 11,43 bi |
| D) Como o P06 faz, ÷ 7 (1.204,6 ÷ 7) | 172,08 | 0,580 | 48,92 (+71,8%) | R$ 4,90 bi |
| E) Units físicas = PN ÷ 2 (**HIPÓTESE**: todas as PN em units) | 217,68 | 0,734 | 38,67 (+35,8%) | R$ 6,20 bi |
| Trocar o fator do app para 3 (Fundamentus × 7 ÷ 3 = 692,4 mi) | 692,37 | 2,333 | 28,37 (a CVM é descartada de novo) | R$ 19,71 bi |

  Só a conversão B reproduz o número do Fundamentus (diferença de 0,1% a 0,3%); as demais (C, D, E) divergem de 27% a 42% porque contam ações e não direitos econômicos. O FCD da IGTI11 não é calculado (capex não identificado), então não há efeito nele.
- **Ações que ficam fora das units (CONFIRMADO só em parte):** as ON do controlador que não formam unit existem: se todas as PN estiverem em units, 217,7 mi das 771,0 mi ON estão em units e **553,3 mi (72%) ficam fora** (**HIPÓTESE** sobre as PN; não achei o número de units em circulação da IGTI11). Para o valor por unit isso **não muda a conversão**: uma unit é dona de 7/2.077,1 mi do capital econômico da empresa, esteja o resto em ON de controlador ou em units; só a contagem física de units (E) usaria o número de units, e ela dá um valor por unit errado (Graham +35,8%). O que fica fora das units só importaria para um valor de mercado que usasse a cotação própria da ON (IGTI3), que o app não usa: o valor de mercado do app avalia todas as ações pelos preços implícitos da unit (ON a 1/7, PN a 3/7 do preço da unit).
- **Verificação do mesmo raciocínio na Energisa (CONFIRMADO):** 1.542,4 mi PN ÷ 4 = 385,6 mi units possíveis, contra 383,6 mi units em circulação no RI (31/08/2026): quase todas as PN estão em units, e as ON do controlador (976,0 − 385,6 = 590,4 mi, 60%) ficam de fora, sem efeito no valor por unit, porque na ENGI11 o fator 5 é a contagem física (as PN têm o mesmo valor por ação, **HIPÓTESE** apoiada no pagamento de R$ 0,38 por ação na ENGI3 e na ENGI4 e R$ 1,90 na ENGI11, em notícia da B3 que não abri).

### 13.4 Proposta (implementada depois, no commit `74a8702`; ver a pergunta 17 da seção 9)

1. **A fonte do fator continua sendo o Fundamentus** (`Nro. Ações × Cotação ÷ Valor de mercado`), que já carrega o peso econômico e dá o valor certo por unit nas seis. Trocar por contagem física da composição (CVM ou RI) pioraria a IGTI11 (valor de mercado de R$ 19,7 bi e Graham distorcido nas conversões C, D e E).
2. **Tabela de composição em `config.py`** (ações ON e PN por unit e peso econômico da PN em ordinárias equivalentes, com a fonte e a data de cada linha), usada para converter a composição da CVM em units por peso econômico, `(ON + peso × PN − tesouraria) ÷ (ON por unit + peso × PN por unit)`, nas units da tabela; fora dela, vale a conversão de hoje. Na IGTI11 isso faz a CVM bater com o Fundamentus (0,1% a 0,3%), a salvaguarda deixa de descartá-la e o motivo "provável erro de escala ou de fator de unit" some da tela; nas outras cinco o resultado é o de hoje (peso 1,0).
3. **Validação:** se o fator do Fundamentus não bater com `ON por unit + peso × PN por unit` da tabela (tolerância de 5%), o app avisa em vez de calcular em silêncio; units fora da tabela com fator maior que 1 também avisam (a lista de units do Ibovespa muda pouco).
4. **Ações fora das units (ON do controlador):** nenhum tratamento adicional; vale o raciocínio da seção 13.3.
5. **Prioridade baixa:** o efeito numérico é de 0,1% a 0,3% no Graham da IGTI11, então a mudança serve à clareza e à robustez (mensagem certa na tela e verificação de um fator errado no futuro), não ao valor.

**Perguntas em aberto:** (a) implementar a tabela e a conversão por peso econômico, ou só registrar a limitação? (b) buscar fontes primárias para SANB11 e BPAC11 (os documentos do RI não abriram); (c) tratar o dividendo 10% maior das PN do SANB11 (e a possível diferença na ENGI11): o efeito estimado no Graham fica abaixo de 3% para qualquer das units com PN a 1,1 vez a ON.

### 13.5 Confirmado e hipóteses

**CONFIRMADO no código:** obtenção, conversão e usos do fator (13.1).

**CONFIRMADO nos dados:** o fator × o número do Fundamentus bate com o integralizado da CVM nas cinco units de peso 1 e, na IGTI11, com o total ponderado (771,0 + 3 × 435,4); VPA × número = patrimônio líquido; réplica do Graham do CSV; efeitos das conversões (13.3).

**CONFIRMADO por fonte primária:** composição, peso econômico (3 vezes) e preço por ON da IGTI11 (Fato Relevante de 09/09/2022); composição da KLBN11 e direitos iguais (RI da Klabin), da TAEE11 (RI da Taesa) e da ENGI11 (RI da Energisa).

**HIPÓTESE:** composição de SANB11 e BPAC11 (só resultados de busca e fontes secundárias); dividendo 10% maior das PN do SANB11; o peso 1,0 das PN do BPAC11, da TAEE11 e da ENGI11; as PN da IGTI11 todas dentro de units (553,3 mi de ON fora); o Fundamentus ponderar por critério próprio; o Yahoo somar os pagamentos das três classes da IGTI11; que a regra de 3 vezes da IGTI11 continue valendo em 2026 (a fonte é de 2022, e a coincidência numérica com o Fundamentus a reforça, mas não a prova).
