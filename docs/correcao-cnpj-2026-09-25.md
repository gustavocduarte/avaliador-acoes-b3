# Correção do CNPJ/código CVM sem zero à esquerda (2026-09-25)

Investigação partiu de uma limitação registrada em
`docs/correcao-ano-fcd-2026-09-23.md` ("ABEV3 sem FCD em nenhum ano, por
`CnpjNaoEncontrado`... não investigado a fundo"). A investigação revelou que
o problema não é do ABEV3 especificamente — é um bug sistêmico que afeta
**20 das 76 ações do Ibovespa**, todas com o mesmo defeito de origem.
Investigado por completo antes de qualquer mudança de código, só depois
implementado, testado e verificado com dado real.

---

## 1. O escopo real: não é só o ABEV3

No `screener.csv` vigente na época da investigação, 26 das 76 ações não
tinham FCD calculado:

- **6 por exclusão estrutural** (segmento "Bancos", comportamento esperado
  do projeto, não é bug): BBDC3, BBDC4, SANB11, BBAS3, ITUB4, BPAC11.
- **20 por `CnpjNaoEncontrado`** — a CVM não reconhecia o CNPJ que o
  crosswalk `ingest/crosswalk_cnpj.py` devolvia: COGN3, ISAE4, CURY3,
  BRAP4, TAEE11, RDOR3, HYPE3, CPFE3, CMIN3, ENGI11, YDUQ3, **ABEV3**,
  TIMS3, EGIE3, B3SA3, EQTL3, MBRF3, ENEV3, HAPV3, MRVE3.

Essas 20 ações — não só o ABEV3 — falhavam pela mesma causa raiz (seção 3).

---

## 2. Rastreando o ABEV3: registro bruto vs. CVM

O catálogo de emissores da B3 (`data/raw/b3/catalogo_emissores.csv`, usado
por `crosswalk_cnpj.resolver_cnpj`) trazia, pra ABEV3:

```
codigo_emissor  codigo_cvm  cnpj            nome_empresa  segmento_setorial
ABEV            23264       7526557000100   AMBEV S.A.    Cervejas e Refrigerantes
```

`cnpj` tem **13 dígitos** — um CNPJ válido sempre tem 14.

Buscando "AMBEV" por nome (`DENOM_CIA`) nos DRE consolidados da CVM de 2025
e 2024:

```
2025 ('07.526.557/0001-00', '023264', 'AMBEV S.A.')
2024 ('07.526.557/0001-00', '023264', 'AMBEV S.A.')
```

CNPJ real: `07.526.557/0001-00` (14 dígitos, com zero à esquerda). CD_CVM:
`023264` (6 dígitos) — o catálogo da B3 trazia `23264` (5 dígitos), mesma
perda de zero.

---

## 3. Causa raiz, na origem

É o **mesmo CNPJ e a mesma empresa** nas duas fontes — só falta o zero à
esquerda no valor que o catálogo da B3 guarda. A causa: a API não-oficial
da B3 usada pelo crosswalk (`GetInitialCompanies`, `crosswalk_cnpj.py`)
devolve os campos `cnpj` e `codeCVM` como **número JSON**, não como texto.
Um literal numérico JSON não pode ter zero à esquerda — é inválido pela
própria especificação do formato (RFC 8259) — então o dígito já se perde
na resposta da API, antes de qualquer código deste projeto rodar. Não é um
bug de normalização do projeto; é um defeito de tipagem na origem que
precisa ser compensado.

**Por que a validação manual original (2026-09-14, documentada em
`config.py`) não pegou o defeito**: ela testou o `cnpj` devolvido pela API
contra a CVM pra três empresas — Petrobras, Vale e Itaú Unibanco Holding —
e bateu nos três casos. Nenhuma das três tem CNPJ começando com zero
(Petrobras: `33.000.167/0001-01`; Vale: `33.592.510/0001-54`; Itaú
Unibanco Holding: `60.872.504/0001-23`), então a perda de dígito não tinha
como aparecer nessa amostra — o teste estava correto para os casos
testados, só não cobria o caso que quebra.

**Confirmação de que é sistêmico, não um caso isolado**: no catálogo
completo da B3 (~3523 emissores, todos os tipos de ativo, não só
Ibovespa), **954 registros (27%) têm `cnpj` com menos de 14 dígitos**, e
906 têm `codigo_cvm` com menos de 6. Um segundo caso confirmado contra a
CVM, pra reforçar o padrão: ENGI11 (Energisa) tem CNPJ real
`00.864.214/0001-06` (**dois** zeros à esquerda) e o catálogo da B3
guardava `864214000106` (12 dígitos — os dois sumiram), provando que mais
de um dígito pode se perder.

---

## 4. Hipóteses descartadas, com evidência

- **CNPJ diferente por reestruturação societária** — descartada. É o
  mesmo CNPJ nas duas fontes (`07526557000100`), só faltando o(s) zero(s)
  à esquerda num dos dois lados.
- **Crosswalk pegando o emissor errado** — descartada. O código de emissor
  "ABEV" resolveu corretamente pra AMBEV S.A.; só o valor do campo `cnpj`
  veio corrompido pela API.
- **Ambev ausente dos arquivos da DFP que o projeto lê** — descartada.
  Confirmado presente nos DRE consolidados de 2025 e 2024, com o CD_CVM
  batendo (`023264` vs. `23264` da B3, mesmo número).

---

## 5. Correção em três camadas

Sem mapeamento manual `ticker → CNPJ` — a correção resolve as 20 ações de
uma vez, na origem do dado:

1. **`crosswalk_cnpj._registro_para_linha`** (novo helper
   `_completar_zeros`): completa `cnpj` até 14 dígitos e `codigo_cvm` até
   6, logo depois de ler a resposta da API. Aplicado a dado NOVO vindo da
   API.
2. **`crosswalk_cnpj.obter_catalogo_emissores`**: reaplica a mesma
   normalização na leitura do cache em disco (`catalogo_emissores.csv`,
   que não tem TTL) — corrige automaticamente qualquer cache já salvo de
   antes desta correção, sem precisar apagar o arquivo nem baixar de novo
   (~36 páginas da API).
3. **`cvm._normalizar_cnpj`**: ganha a mesma normalização como camada
   defensiva, protegendo contra qualquer outra fonte futura de CNPJ com o
   mesmo defeito que chame o adapter da CVM sem passar pelo crosswalk.

CNPJ (14 dígitos) e código CVM (6 dígitos) têm largura fixa — confirmada
contra os zips da CVM lidos por este projeto — então completar com zero
nunca cria ambiguidade com outra empresa, só restaura um dígito que já
sabíamos que existia.

Todos os pontos do projeto que consomem `cnpj`/`codigo_cvm` do catálogo da
B3 passam pela correção: `crosswalk_cnpj.resolver_cnpj` (usado por
`app/main.py._buscar_cnpj` e `screener.py._calcular_linha_ticker`) e
`crosswalk_cnpj.obter_crosswalk_ibovespa` (não usado em produção hoje, só
testado) — ambos leem do `catalogo` já corrigido. O cache de resultado por
CNPJ (`data/raw/cvm/fcf_<cnpj>_<ano>.json`/`lucro_<cnpj>_<ano>.json`) não
tinha nenhuma entrada órfã sob o CNPJ errado, porque essas 20 buscas sempre
falhavam antes de chegar no passo de gravar cache.

---

## 6. Antes e depois: as 20 ações

Recalculado com dado real de mercado (25/09/2026), pelo botão "Rodar
screener agora":

| Ticker | FCD novo | Comb. antes | Comb. depois | Desc. antes | Desc. depois | Divergência | Novo aviso extremo |
|---|---|---|---|---|---|---|---|
| HAPV3 | 75,50 | — (0 métodos) | 75,50 | — | **+1035,3%** | — | **sim (positivo c/ FCD)** |
| CURY3 | 30,40 | 51,95 | 44,76 | +90,3% | +64,0% | 228% | não |
| MRVE3 | 7,08 | — (0 métodos) | 7,08 | — | +35,1% | — | não |
| COGN3 | -0,96 | 7,13 | 3,09 | +210,1% | +34,3% | 352% | não |
| BRAP4 | 7,62 | 32,74 | 24,37 | +59,2% | +18,5% | 154% | não |
| HYPE3 | 11,65 | 26,12 | 21,30 | +7,2% | -12,6% | 91% | não |
| ABEV3 | 12,24 | 12,86 | 12,65 | -16,0% | -17,3% | 16% | não |
| YDUQ3 | 7,06 | 9,91 | 8,48 | -8,8% | -21,9% | 26% | não |
| TAEE11 | -5,89 | 50,00 | 31,37 | +21,1% | -24,0% | 136% | não |
| RDOR3 | -10,06 | 44,11 | 26,05 | +15,8% | -31,6% | 202% | não |
| TIMS3 | 0,79 | 14,70 | 10,06 | -21,1% | -46,0% | 145% | não |
| B3SA3 | 4,06 | 12,23 | 9,51 | -32,2% | -47,3% | 61% | não |
| CPFE3 | -6,92 | 48,08 | 20,58 | +6,7% | -54,3% | 122% | não |
| ISAE4 | -32,82 | 53,32 | 10,25 | +96,9% | -62,1% | 318% | não |
| ENGI11 | -13,69 | 51,20 | 18,76 | -1,8% | -64,0% | 124% | não |
| CMIN3 | -4,65 | 5,02 | 1,80 | -1,5% | -64,7% | 217% | não |
| EGIE3 | -19,98 | 22,22 | 8,15 | -24,3% | -72,2% | 156% | não |
| ENEV3 | -9,94 | 10,85 | 0,46 | -60,9% | -98,4% | 75% | não |
| EQTL3 | -34,98 | 18,83 | -8,07 | -52,9% | -120,2% | 135% | **sim (negativo c/ FCD)** |
| MBRF3 | -18,65 | 6,95 | -5,85 | -59,1% | -134,5% | 151% | **sim (negativo c/ FCD)** |

**Nenhuma das 20 continua sem FCD.** Notas:

- **HAPV3 e MRVE3** iam de "erro: nenhum dos 3 métodos aplicável" pra
  "aplicável, só via FCD" — Graham/Bazin continuam indisponíveis por
  motivos próprios, sem relação com este bug.
- Vários descontos **trocam de sinal** (ex.: ISAE4 de +97% pra -62%,
  TAEE11 de +21% pra -24%) — o combinado muda de forma material pra boa
  parte do universo, não é um efeito cosmético.
- 16 das 20 passam a ter divergência acima de 50% entre métodos —
  esperado, dado que o FCD é o método mais sensível (CAGR de 2 pontos, já
  documentado em `config.py`).

---

## 7. O que a correção revelou: FCD negativo concentrado no setor elétrico

Registrado aqui como **limitação conhecida a investigar depois**, não como
bug desta correção — o bug escondia esse efeito, não o causava.

**11 das 20 ações passaram a ter FCD negativo**: COGN3, ISAE4, TAEE11,
RDOR3, CPFE3, CMIN3, ENGI11, EGIE3, EQTL3, MBRF3, ENEV3.

**7 dessas 11 são do setor "Energia Elétrica"** (confirmado no catálogo de
emissores da B3): CPFE3 (CPFL Energia), EGIE3 (Engie Brasil Energia),
ENEV3 (Eneva), ENGI11 (Energisa), EQTL3 (Equatorial), ISAE4 (Isa Energia
Brasil), TAEE11 (Transmissora Aliança de Energia Elétrica). As outras 4:
CMIN3 (Minerais Metálicos), COGN3 (Serviços Educacionais), MBRF3 (Carnes e
Derivados), RDOR3 (Serv. Médico Hospitalares).

**Hipótese a investigar (não confirmada, registrada como ponto de partida
pra uma investigação futura)**: o FCF deste projeto é definido como Caixa
Líquido de Atividades Operacionais + Caixa Líquido de Atividades de
Investimento (`CODIGO_CFO_CVM` + `CODIGO_CFI_CVM`, ver `config.py`). Esse
cálculo penaliza empresas em fase de investimento pesado financiado com
dívida — o CFI vem fortemente negativo (capex alto) sem que o CFO cresça
na mesma proporção ainda, e a dedução da dívida líquida (correção de
2026-09-23, `docs/correcao-fcd-2026-09-23.md`) amplia o efeito por cima
disso. Concessionárias de energia elétrica (transmissão/distribuição/
geração) são um perfil clássico de capex pesado e alavancado, o que é
consistente com a concentração observada — mas essa é uma hipótese, não
uma conclusão: não foi feita nenhuma análise adicional (ex.: comparar
FCF/dívida líquida por setor além destes 20 casos) pra confirmá-la.

---

## 8. Testes e verificação

- 5 testes novos (diferença real de `pytest --collect-only`: 400 → 405):
  4 em `tests/test_crosswalk_cnpj.py` (zero-pad do CNPJ da Ambev — 1
  zero —, da Energisa — 2 zeros —, do código CVM, e leitura de cache
  antigo sem zero corrigida sem nova requisição), 1 em `tests/test_cvm.py`
  (`_normalizar_cnpj` completando zero perdido).
- `pytest`: 405 passaram. `ruff check .`: sem apontamentos.
- Verificação com dado real: `screener.csv` regenerado pelo botão "Rodar
  screener agora" (25/09/2026) — confirmado que as 20 ações têm FCD e que
  as 6 ações sem FCD remanescentes são exatamente os 6 bancos (exclusão
  estrutural, não bug).
