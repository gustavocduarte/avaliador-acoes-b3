# Correção metodológica do FCD (2026-09-23)

Diferente dos relatórios anteriores em `docs/` (bugs de UI/formatação
confirmados por screenshot), esta correção começou de um achado conceitual
sobre o modelo de valuation em si — uma revisão externa (segunda opinião de
IA, fora desta sessão) apontou que o Fluxo de Caixa Descontado (FCD) estava
misturando dois conceitos de valor que não são a mesma coisa. Investigado
por completo antes de qualquer mudança de código (ver troca anterior nesta
sessão), só depois implementado, testado e verificado ao vivo.

---

## 1. O achado original

A cadeia correta de um FCD é:

```
FCF (fluxo de caixa livre) → descontado pelo WACC → Enterprise Value
Enterprise Value − Dívida Líquida → Equity Value
Equity Value ÷ número de ações → valor justo por ação
```

Enterprise Value é o valor da empresa como um todo (dívida incluída);
Equity Value é só a parte que pertence aos acionistas — a diferença entre
os dois é exatamente a dívida líquida. "Valor justo por ação", pra ser
comparável a Graham/Bazin (que já calculam valor de patrimônio, não valor
de firma), precisa ser Equity Value por ação, não Enterprise Value por
ação.

O projeto pulava o penúltimo passo: `modelos/fcd.py` descontava o FCF pelo
WACC (chegando em Enterprise Value, corretamente) e dividia esse valor
**direto** pelo número de ações, sem nunca subtrair a dívida líquida. Na
prática, tratava Enterprise Value como se já fosse Equity Value — inflando
o valor justo por ação de toda empresa com dívida líquida positiva (a
maioria do universo do Ibovespa).

---

## 2. Investigação que confirmou o achado antes de qualquer código

Três verificações, nessa ordem, antes de escrever uma linha de correção:

1. **Leitura completa de `modelos/fcd.py`**: confirmado que `valor_total`
   (soma do valor presente explícito + valor presente terminal) ia direto
   pra `valor_total / numero_acoes` no retorno — nenhuma subtração de
   dívida em lugar nenhum do arquivo. O único termo relacionado a dívida
   era `divida_liquida_sobre_patrimonio`, usado só como **razão** pra
   ponderar a estrutura de capital do WACC, nunca como valor absoluto
   subtraído do resultado.

2. **O comentário original em `config.py`** já registrava essa
   simplificação como conhecida, não escondida:
   > "tratamos o valor presente desses fluxos como aproximação direta do
   > valor do patrimônio líquido (equity), sem abater dívida líquida
   > absoluta separadamente — outra simplificação, já que ainda não
   > extraímos dívida líquida em valor absoluto do balanço patrimonial da
   > CVM (BPP)."

3. **A descoberta que tornou a correção viável sem trabalho novo de
   extração**: essa premissa — "ainda não extraímos dívida líquida em
   valor absoluto" — era verdade sobre a CVM, mas **desatualizada** sobre
   o projeto como um todo. O campo `"Dív. Líquida"` já vinha do
   Fundamentus desde o início (`divida_liquida` em
   `CAMPOS_FUNDAMENTUS_OPCIONAIS`), já era usado em
   `empresa.valor_mercado.calcular_valor_mercado_e_firma`, e já aparecia
   na tela em "Saúde financeira" — só nunca tinha sido conectado ao FCD.
   Confirmado que a variável já existia em escopo no ponto exato da
   chamada do FCD em `app/main.py` (linha 788, antes da chamada na linha
   824), e que `screener.py` só precisava de uma linha de extração a mais
   (o dict `indicadores` já trazia o campo, só não estava sendo lido ali).

Essa investigação (registrada como troca separada nesta sessão, antes do
pedido de implementação) foi o que permitiu classificar a correção como
"pequena e localizada" em vez de "exige nova fonte de dado".

---

## 3. Cálculo manual prévio e confirmação ao vivo

Antes de escrever qualquer código, a correção foi calculada à mão com os
números já vistos nesta sessão pra PETR4 — dívida líquida ~R$312,8 bi,
~12,89 bilhões de ações, FCD antigo ~R$118,99/ação:

```
dívida líquida por ação = 312,8 bi / 12,89 bi ações ≈ R$24,27/ação
FCD novo = 118,99 − 24,27 ≈ R$94,72/ação
```

Depois de implementada a correção e reiniciado o servidor, o valor real
mostrado ao vivo pra PETR4 foi **R$94,83** — a poucos centavos da
estimativa manual (R$94,72), a diferença explicada por dado de mercado
(preço atual, dívida líquida, Selic/IPCA do dia) ter mudado ligeiramente
entre o momento do cálculo manual e o momento da verificação ao vivo, não
por erro na lógica. Essa proximidade entre estimativa e resultado real foi
a confirmação final de que a subtração estava matematicamente correta
antes de considerar a correção pronta pra aprovação.

---

## 4. Decisão de design: `divida_liquida=None` (bancos)

Quando a dívida líquida absoluta não está disponível pra uma empresa — o
mesmo campo opcional do Fundamentus que já falta pra bancos em "Saúde
financeira" (`CAMPOS_FUNDAMENTUS_OPCIONAIS`) — havia duas opções coerentes
com o resto do projeto:

- **(a)** Pular a subtração só nesse caso específico, mantendo o FCD
  "aplicável" com a aproximação antiga (Enterprise Value ≈ Equity Value),
  avisando explicitamente na UI que a dedução não foi feita;
- **(b)** Tornar o FCD inteiro "não aplicável" quando faltar dívida
  líquida.

A opção **(a)** foi escolhida, por dois motivos alinhados com decisões já
tomadas no projeto:

- O FCD é documentado desde sua criação como pensado pra ser "quase
  sempre aplicável" — inclusive pra empresa com FCF negativo, que só faz o
  valor sair baixo ou negativo, nunca "não aplicável" por causa disso. A
  opção (b) quebraria esse princípio pra um universo inteiro de empresas
  (bancos) sem necessidade — Graham e Bazin continuam funcionando
  normalmente pra elas.
- Resultado impreciso e sinalizado como tal já é um padrão aceito no
  projeto (FCD negativo, ex: AURE3 com R$-36,92 na bateria de testes de
  2026-09-21, é "resultado válido, não erro") — a diferença aqui é que
  agora existe um jeito de sinalizar a imprecisão explicitamente
  (`divida_liquida_deduzida=False` no retorno), então silenciar a
  aproximação seria pior do que mostrá-la com um aviso.

> ### Revisão pouco mais de uma hora depois, ainda no mesmo dia — decisão acima substituída pra bancos
>
> A decisão de manter o FCD "aplicável" pra bancos (opção (a) acima) foi
> revista pouco mais de uma hora depois, ainda em 2026-09-23, motivada por
> uma segunda revisão externa (outra IA, fora desta sessão) — não uma
> mudança de opinião sem motivo novo, um achado adicional que a decisão
> original não tinha considerado.
>
> **O argumento econômico que faltava**: a decisão de mais cedo tratava
> o problema como uma lacuna de DADO — "dívida líquida não disponível pra
> essa empresa" — resolvida com uma aproximação e um aviso, igual a
> qualquer outro dado faltante no projeto. Mas em bancos o problema não é
> falta de dado, é a METODOLOGIA não fazer sentido: dívida e depósitos
> são a própria operação do banco (captação pra emprestar), não
> financiamento externo à operação como a conta pressupõe, e o fluxo de
> caixa operacional (CFO, base do FCF neste projeto) oscila com a
> expansão ou contração da carteira de crédito, não com geração de valor.
> Não existe "dívida líquida certa" pra deduzir de um banco que resolva
> isso — mesmo com o dado em mãos, a conta inteira (FCF → WACC →
> Enterprise Value) não tem interpretação econômica válida nesse setor.
>
> **Por que a caption de 2026-09-23 não era a resposta certa aqui**: a
> caption aprovada no dia anterior ("Dívida líquida indisponível...
> este valor não desconta a dívida da empresa, então tende a ficar mais
> alto") passa a mensagem de uma imprecisão LEVE e QUANTIFICÁVEL — como
> se o número estivesse só um pouco inflado, faltando uma dedução, e
> ainda fosse útil como referência aproximada. Pior: a caption afirmava a
> direção ERRADA. Nos dados reais o FCD saía ABAIXO de Graham e Bazin —
> não acima — em 4 dos 5 bancos com FCD calculável (ITUB4 R$7,27, BPAC11
> R$0,96, SANB11 negativo em R$-23,33, e BBDC4 R$24,03 — os quatro abaixo
> dos dois métodos ao mesmo tempo; BBDC3 R$24,79 ficava abaixo só de
> Graham, acima do Bazin, R$23,53), puxando o valor combinado pra BAIXO
> em todos os 5, não pra cima (ver "Combinado antes" vs. "Combinado
> depois" na tabela abaixo — sobe em todos). BBAS3 fica fora dessa
> contagem, seu FCD já era "não aplicável" antes desta correção, por
> outro motivo. Pros 6 bancos, isso é enganoso: o número não estava "um
> pouco alto", não tinha base econômica nenhuma pra começo de conversa
> (o caso mais extremo, SANB11, chegava a ser NEGATIVO — um resultado
> sem nenhuma leitura sensata pra um banco lucrativo). Uma caption de
> aviso não é o remédio certo pra um número que não deveria estar na
> tela, e menos ainda uma que erra até a direção do problema.
>
> **Efeito no valor combinado dos 6 bancos** (valores do screener antes e
> depois desta correção, ambos rodados via o botão real):
>
> | Ticker | Graham | Bazin | FCD (removido) | Combinado antes | Combinado depois |
> |---|---|---|---|---|---|
> | BBDC3 | R$29,51 | R$23,53 | R$24,79 | R$25,94 | R$26,52 |
> | BBDC4 | R$29,51 | R$25,88 | R$24,03 | R$26,47 | R$27,69 |
> | BBAS3 | R$42,44 | R$10,92 | *(já não aplicável antes, motivo à parte)* | R$26,68 | R$26,68 |
> | ITUB4 | R$42,33 | R$51,64 | R$7,27 | R$33,75 | **R$46,99** |
> | SANB11 | R$49,46 | R$38,45 | -R$23,33 | R$21,53 | **R$43,96** |
> | BPAC11 | R$46,40 | R$23,67 | R$0,96 | R$23,68 | **R$35,04** |
>
> O efeito não é sutil — ITUB4 sobe 39%, SANB11 mais que dobra — o
> tamanho da mudança é, em si, mais uma evidência de que o FCD estava
> distorcendo a leitura desses 6 papéis, não só "impreciso".
>
> **Escopo continua deliberadamente restrito a "Bancos"**: seguradoras
> (BBSE3, CXSE3, PSSA3) e outras financeiras (B3SA3, ITSA4) permanecem
> aplicáveis — confirmado, antes de decidir o escopo, que essas 5 empresas
> TÊM dívida líquida reportada normalmente pelo Fundamentus (diferente
> dos 6 bancos, que não têm nenhuma), então não compartilham a mesma
> lacuna de dado nem, necessariamente, a mesma distorção econômica dos
> bancos. Se o FCD também não faz sentido pra seguradoras (estrutura de
> reservas técnicas/float é diferente de depósito bancário, mas também
> não é dívida convencional) é uma questão em aberto, registrada como
> limitação conhecida — não decidida nesta correção, pra não estender a
> exclusão além do que a investigação efetivamente confirmou.

---

## 5. O que foi implementado

- **`modelos/fcd.py`**: novo parâmetro `divida_liquida: float | None = None`
  em `calcular_valor_justo_fcd`. Subtraído de `valor_total` **antes** de
  dividir por `numero_acoes`, quando não `None`. Dívida líquida negativa
  (posição de caixa líquido) soma ao valor normalmente, com subtração
  simples, sem caso especial — mesma convenção de
  `calcular_valor_mercado_e_firma` (`valor_firma = valor_mercado +
  divida_liquida`, a operação inversa). Novo campo `divida_liquida_deduzida`
  (bool) no dict de retorno, sinalizando se a dedução foi feita.
- **Wiring**: `app/main.py:824` e `screener.py:233` passam `divida_liquida`
  pra `calcular_valor_justo_fcd` — em `app/main.py` a variável já existia
  em escopo (linha 788); em `screener.py` foi adicionada uma linha de
  extração (`indicadores["divida_liquida"]`) espelhando a que já existia
  em `app/main.py`.
- **Dois textos públicos**, ambos mostrados e aprovados antes de aplicar:
  - Caption de aviso no cartão do FCD, quando `divida_liquida_deduzida`
    é `False`: *"Dívida líquida indisponível pra essa empresa (comum em
    bancos, ver 'Saúde financeira') — sem ela pra deduzir, este valor não
    desconta a dívida da empresa, então tende a ficar mais alto do que se
    a dedução fosse possível."*
  - Parágrafo do FCD no expander "Como funciona esse cálculo?", explicando
    a conversão Enterprise Value → Equity Value e o caso em que ela não
    acontece.
- **`config.py`**: comentário da seção "Fluxo de Caixa Descontado (FCD)"
  reescrito — a premissa desatualizada mantida como contexto histórico
  (não apagada), com uma nota de correção explicando o que mudou e por
  quê.
- **5 testes novos**: dedução linear (`valor_justo` cai exatamente
  `divida_liquida / numero_acoes`), dívida líquida negativa aumentando o
  valor, `divida_liquida=None` preservando o comportamento antigo bit a
  bit (comparado contra a mesma fórmula fechada já usada no teste de
  "caminho feliz sem crescimento"), e dois testes de UI (AppTest)
  confirmando que a caption de aviso aparece quando `divida_liquida_
  deduzida` é `False` e não aparece quando é `True`. Também corrigido, no
  processo, um gap na fixture de testes do Screener (`_indicadores()` em
  `tests/test_screener.py` não tinha o campo `divida_liquida`, o que
  quebrou 10 testes existentes assim que `screener.py` passou a lê-lo —
  fixture atualizada com `divida_liquida=None` como padrão, preservando
  os valores que os testes já esperavam).

341 testes passando, ruff limpo.

---

## 6. Nota final

`screener.csv` foi regenerado depois da correção, rodando o botão real
"Rodar screener agora" (76 ações do Ibovespa) — o ranking de desconto de
todo o universo muda com essa metodologia nova, então o CSV commitado pro
cold-start do Streamlit Community Cloud ficaria desatualizado (valores de
FCD inflados) se não fosse atualizado junto. PETR4 como referência na
regeneração: `fcd_valor_justo` de R$118,82 pra R$94,86, valor combinado de
R$91,04 pra R$83,05, desconto de 88,3% pra 67,7%. Os R$94,86 aqui e os
R$94,83 da seção 3 vêm de duas capturas ao vivo em momentos diferentes
(verificação inicial do cartão do FCD, depois a rodada completa do
screener) — a diferença de poucos centavos é dado de mercado (preço,
dívida líquida, Selic/IPCA) variando entre uma captura e outra, não
mudança nenhuma na lógica do cálculo.

Commits publicados no GitHub:

| Commit | O que contém |
|---|---|
| `2f66089` | Correção metodológica do FCD — `modelos/fcd.py`, `app/main.py`, `screener.py`, `config.py`, testes |
| `e26dd69` | `screener.csv` regenerado com os novos valores |
