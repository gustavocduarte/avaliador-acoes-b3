# Correção do ano de referência do FCD (2026-09-23)

Terceiro achado de revisão externa no mesmo dia das duas correções
anteriores do FCD (dedução de dívida líquida e exclusão de bancos, ambas
já documentadas em `docs/correcao-fcd-2026-09-23.md`). Diferente das duas
anteriores, começou de uma suspeita concreta e verificável — "o ano fixo
2024 já deveria ter sido atualizado pra 2025, pelo prazo legal da CVM" —
investigada por completo (existência do zip, completude do dado, cache,
streaming) antes de qualquer mudança de código, depois implementada,
testada e verificada ao vivo. No meio da implementação, o próprio
processo de verificação (não a revisão externa que motivou o achado
original) encontrou mais dois problemas reais (cache do zip permanente,
motivo do FCD invisível no Screener) que viraram parte da correção, não
só o ano em si.

---

## 1. O achado

`config.py` tinha uma constante fixa:

```python
# Ano de referência pro FCD: 2025 ainda não estava publicado pela CVM na
# época em que isso foi escrito (confirmado no adapter da CVM), então usa
# 2024 como padrão fixo por ora — trocar por uma detecção automática do
# ano mais recente disponível é um refinamento futuro. Compartilhado entre
# app/main.py e screener.py, pra não divergir entre os dois.
ANO_REFERENCIA_FCD = 2024
```

A premissa ("2025 ainda não publicado") não era mais verdadeira — o prazo
legal de entrega da DFP (3 meses após o fim do exercício) já tinha
passado havia meses. Com a constante fixa, o FCD de toda ação ficava um
exercício inteiro atrasado, sem nenhum aviso na tela indicando isso.

---

## 2. Investigação (antes de qualquer código)

1. **Existência confirmada por HTTP, não assumida pelo prazo legal**: o
   zip anual `dfp_cia_aberta_2025.zip` foi checado direto na URL real da
   CVM e baixado de fato — 12.753.312 bytes, tamanho comparável aos
   outros anos (2019: 11,2 MB; 2020: 12,6 MB; 2024: 13,4 MB) — não um
   stub ou placeholder.

2. **Completude confirmada, não só existência do arquivo**: `obter_
   fluxo_caixa_livre` rodado com `ano=2025` pra 4 empresas de setores
   diferentes (PETR4 — óleo e gás, VALE3 — mineração, WEGE3 — motores
   industriais, RADL3 — varejo farmacêutico), comparando com 2024:

   | Ticker | FCF 2024 | FCF 2025 |
   |---|---|---|
   | PETR4 | R$ 131,67 bi | R$ 114,22 bi |
   | VALE3 | R$ 19,42 bi | R$ 10,30 bi |
   | WEGE3 | R$ 3,16 bi | R$ 3,54 bi |
   | RADL3 | R$ 1,36 bi | R$ 1,02 bi |

   Todos não-nulos, não-zero, em magnitude plausível — dado real, não
   lacuna.

3. **Ano-base do crescimento**: confirmado que `ano_anterior =
   ANO_REFERENCIA_FCD - ANOS_HISTORICO_CRESCIMENTO_FCD` (5 anos) faria o
   ano-base saltar de 2019 pra 2020 junto com a mudança do ano de
   referência — e que o zip de 2020 também já estava disponível e
   resolvia FCF pras mesmas 4 empresas sem erro.

4. **Cache por ano confirmado, streaming confirmado**: `data/raw/cvm/`
   tinha 4 zips coexistindo (2019, 2020, 2024, 2025), nenhum
   sobrescrevendo o outro — trocar o ano de referência não invalida os
   demais. O download em si já era streaming de verdade (`requests.get(
   ..., stream=True)` + `iter_content(chunk_size=256*1024)`, escrevendo
   em `.zip.tmp` com troca atômica só no final) — confirmado lendo o
   código, não assumido.

Só depois dessa investigação — sem nenhuma mudança de código ainda — a
implementação foi proposta e discutida.

---

## 3. Reconciliação do passo 0 (achado de verificação, não de investigação original)

A primeira estimativa do efeito ano-a-ano (item "9" da investigação) deu
FCD de PETR4 em 2024 = R$68,81 — mas o app ao vivo mostrava R$94,83, uma
diferença de 27%. Isso disparou uma pausa: **nenhuma implementação
prosseguiu até essa divergência ser explicada**, por instrução explícita.

**Causa raiz encontrada**: a estimativa tinha sido calculada com
`beta=None` (cai pro `BETA_PADRAO` genérico dentro do WACC), em vez do
beta real calculado a partir do histórico de preços — que é o que o app
de fato usa. Todos os outros insumos (Selic, IPCA, número de ações,
dívida líquida, dívida líquida/patrimônio) já estavam corretos.

**Reconciliação confirmada ao vivo**: recalculado com o beta real de
PETR4 (0,3932, mesma janela de 1 ano que o app usa), o script deu
**R$94,96**. O app, aberto no navegador na hora, mostrava **R$94,96** —
igual ao centavo (beta no WACC exibido: `0,39 (calculado, 1a)`, batendo
com o valor usado no script).

Com a reconciliação fechada, a tabela do item 9 foi refeita com os
mesmos insumos exatos do app (beta real incluso):

| Ticker | Beta usado | FCD 2024 | FCD 2025 | Variação |
|---|---|---|---|---|
| PETR4 | 0,3932 | R$ 94,96 | R$ 48,22 | -49,2% |
| VALE3 | 0,8607 | R$ 12,06 | -R$ 8,53 | -170,7% (fica negativo) |
| WEGE3 | 0,7450 | R$ 7,63 | R$ 5,31 | -30,4% |
| RADL3 | 1,2025 | R$ 5,70 | R$ 2,55 | -55,3% |

Essa tabela reconciliada foi confirmada de novo ao vivo depois da
implementação completa (seção 7): PETR4 mostrou R$48,22 (depois R$48,34
numa segunda verificação, minutos depois — diferença de dado de mercado
do dia, não da lógica) e VALE3 mostrou -R$8,53, ambos com a caption "FCD
calculado com a demonstração financeira anual de 2025 (CVM)."

---

## 4. Detecção em dois níveis

**Nível arquivo** (`ingest.cvm.resolver_ano_mais_recente_disponivel`):
ano candidato = ano corrente − 1 (o último exercício que já deveria ter
fechado). Se a CVM ainda não publicou esse zip (404 — janela jan-mar,
antes do prazo legal), cai pro ano anterior inteiro. Chamado uma vez por
execução, reaproveitado entre todas as ações (mesmo padrão do zip em
si).

**Nível empresa** (`ingest.cvm.obter_fluxo_caixa_livre_com_fallback`): o
zip do ano mais recente pode existir sem que uma empresa específica
ainda tenha entregado a DFP daquele exercício. Se `CnpjNaoEncontrado`
acontecer pra essa empresa no ano mais recente, cai um ano só pra ELA,
sem afetar as demais — e o ano-base do crescimento anda junto com o ano
efetivamente usado, mantendo sempre o intervalo de
`ANOS_HISTORICO_CRESCIMENTO_FCD` anos entre os dois pontos da CAGR (não
fica preso a `ano_mais_recente - 5` se o ano atual caiu).

**Por que `ContaFluxoCaixaNaoEncontrada` NÃO dispara esse fallback**: essa
exceção significa que a empresa entregou a demonstração, mas as contas
6.01/6.02 não estão no formato esperado — sinal de mudança de
layout/parsing da CVM, não de "ainda não publicado". Cair pro ano
anterior nesse caso esconderia um erro real de parsing atrás de um
número (de outro ano) que parece válido. A exceção propaga normalmente,
como sempre propagou.

---

## 5. Bug do cache do zip na janela de transição — encontrado e corrigido antes do commit

Depois da implementação inicial (dois níveis de detecção) já revisada e
aprovada, uma pergunta de verificação levantou um bug real antes do
commit: **o cache do zip da CVM (`_baixar_zip_ano`) era permanente** — a
única checagem era "o arquivo existe no disco?", sem prazo de validade.

Isso é inofensivo pra anos fechados (a CVM não reabre exercícios
encerrados). Mas quebra o ano ainda em preenchimento: a CVM atualiza esse
mesmo zip ao longo do ano conforme empresas entregam a DFP (inclusive
fora do prazo), então um zip baixado cedo — ex.: na janela jan-mar, ainda
incompleto — ficaria preso pra sempre localmente. Empresas que entregassem
depois nunca mais apareceriam nesse zip **local**, mesmo com a CVM já
tendo atualizado o arquivo remoto há meses (no Streamlit Community Cloud
isso se corrige sozinho, porque o disco é apagado a cada "sleep" do app —
o problema é só em ambientes com disco persistente, como esta máquina).

**Correção**: `DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE = 7` (`config.py`)
— prazo de validade que só vale pro(s) ano(s) ainda em preenchimento
(`ano >= ano corrente - 1`, checado via `mtime` do arquivo em
`ingest.cvm._cache_zip_expirado`). Anos fechados continuam com cache
permanente, sem custo de rede repetido à toa. Se o prazo vencer e o
download de atualização falhar (CVM fora do ar, timeout), e já existir um
zip em cache, usa o arquivo existente (com `warnings.warn`, não
silenciosamente) em vez de propagar o erro — só propaga se não houver
nenhum arquivo em cache pra usar. Confirmado que o download continua indo
pro `.zip.tmp` com troca atômica (`.replace()`) só no final — uma falha
no meio do download nunca corrompe o arquivo já cacheado.

---

## 6. Motivo do FCD nunca chega na coluna "erro" do Screener — outro achado no meio da implementação

Ao implementar a visibilidade da causa quando `resolver_ano_mais_recente_
disponivel` falha no Screener, a verificação revelou que a abordagem
inicial (só ajustar `motivo_nao_aplicavel` do FCD) não funcionava:
`modelos.combinado.calcular_valor_combinado` sempre usa sua **própria**
mensagem genérica ("Nenhum dos três métodos... é aplicável a essa ação")
quando nada é aplicável, e não usa mensagem nenhuma quando pelo menos um
método (ex.: Graham) funciona — o motivo individual do FCD nunca aparece
na coluna `erro` do CSV, em nenhum dos dois casos.

**Correção de verdade**: `rodar_screener` emite um `warnings.warn`
(categoria própria, `DeteccaoAnoCvmFalhouWarning`, pra não se confundir
com o aviso de cache desatualizado da seção 5) uma vez por rodada quando
a detecção falha — sinal global, já que a falha afeta o FCD de todas as
ações da rodada, não uma linha específica. Rodando fora da UI (script,
CI), isso já aparece no log/stderr normalmente.

Rodando pela UI (botão "Rodar screener agora"), esse aviso iria só pro
log do servidor, invisível pra quem clicou — outra lacuna encontrada e
corrigida: `app/main.py` agora captura os avisos da rodada com `warnings.
catch_warnings(record=True)`, reemite **todos** pro canal normal (log)
antes de filtrar, preservando o comportamento do aviso de cache da seção
5 (que continua só no log, sem mudança), e guarda os de
`DeteccaoAnoCvmFalhouWarning` em `st.session_state` pra mostrar com
`st.warning` depois do `st.rerun()` que a rotina já fazia ao final
(sem isso, a mensagem se perderia no rerun). Verificado com teste de UI:
clicar no botão com a detecção falhando mostra o aviso na tela, com a
causa.

---

## 7. O que foi implementado

- **`ingest/cvm.py`**: `resolver_ano_mais_recente_disponivel` (nível
  arquivo), `obter_fluxo_caixa_livre_com_fallback` (nível empresa),
  `_cache_zip_expirado` + prazo de validade em `_baixar_zip_ano` (com
  `hoje` injetável nos três, pra testar sem depender do relógio real).
- **`config.py`**: `ANO_REFERENCIA_FCD` removida, comentário reescrito
  (premissa antiga mantida como contexto histórico); nova constante
  `DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE = 7`.
- **`app/main.py`**: `_buscar_ano_fcd_mais_recente` (cacheada 1h) e
  `_buscar_fcf_fcd` substituindo a antiga `_buscar_fcf`; novo rótulo no
  cartão do FCD indicando o ano usado (`"FCD calculado com a
  demonstração financeira anual de {ano} (CVM)."`, ou a variante de
  fallback quando a empresa ainda não entregou o ano mais recente);
  captura+reexibição de avisos no botão "Rodar screener agora".
- **`screener.py`**: coluna `ano_referencia_fcd` (nula quando o FCD não
  se aplica); `ano_referencia` (parâmetro fixo) virou `ano_mais_recente_
  fcd` (detectado uma vez por rodada, `None` cai pro auto-detect);
  classe `DeteccaoAnoCvmFalhouWarning`.
- **19 testes novos** (`test_cvm.py`: 13; `test_app_main.py`: 3;
  `test_screener.py`: 3 — conferido função por função contra o commit
  anterior a esta correção, `345 → 364` testes, nenhum removido ou
  substituído), cobrindo: detecção de ano em si (candidato existe,
  candidato 404, janela jan-mar simulada), fallback por empresa
  (`CnpjNaoEncontrado` cai um ano com o ano-base andando junto,
  `ContaFluxoCaixaNaoEncontrada` propaga sem fallback), TTL do cache do
  zip (expira/não expira, ano fechado nunca expira, falha de rede com e
  sem cache existente), coluna nova no Screener, os dois rótulos no
  cartão do FCD, e o aviso visível na tela do Screener.

364 testes passando, `ruff` limpo.

---

## 8. Limitações conhecidas

1. **Sensibilidade do FCD ao par de anos usado no crescimento.** A
   mudança de ano de referência não afeta só o FCF "atual" — também
   desloca o ano-base da CAGR (2019 → 2020), reconfigurando a taxa de
   crescimento implícita usada na projeção. O efeito no valor justo é bem
   maior do que a variação isolada do FCF sugeriria: o FCF de PETR4 caiu
   13,3% (2024→2025), mas o FCD caiu 49% (R$94,96 → R$48,22); VALE3 teve
   FCF caindo 47% e o FCD saiu de R$12,06 pra -R$8,53 (deixa de ser
   positivo). Esse efeito é agravado pelo novo ano-base (2020) ser ano de
   pandemia — um ano atípico na maioria dos setores, o que torna a CAGR
   de 2 pontos calculada a partir dele ainda menos representativa do que
   já é por natureza (já documentado como limitação do método antes desta
   correção, com uma trava de bom senso em `TAXA_CRESCIMENTO_FCD_MINIMA`/
   `MAXIMA`). Não é um bug desta correção — é uma característica do
   método CAGR-de-2-pontos que a atualização do ano deixou mais visível.

2. **ABEV3 sem FCD em nenhum ano, por `CnpjNaoEncontrado`.** Encontrado
   como efeito colateral da investigação do item 3 (precisou ser trocado
   por RADL3 na amostra de 4 tickers): `obter_fluxo_caixa_livre` falha
   pra ABEV3 tanto em 2024 quanto em 2025. Não é causado por esta
   correção (o comportamento já existia antes, com o ano fixo) nem
   investigado a fundo — fica registrado como bug preexistente conhecido,
   não resolvido aqui.

   **Atualização (2026-09-25):** investigado e corrigido — não era só o
   ABEV3, eram 20 das 76 ações. Ver `docs/correcao-cnpj-2026-09-25.md`.

---

## 9. Nota: datas erradas corrigidas depois do commit `7a29e7f`

O commit `7a29e7f` foi feito com "2026-09-24" em vários comentários de
código e teste (`config.py`, `ingest/cvm.py`, `app/main.py`,
`test_cvm.py`, `test_app_main.py`, `test_screener.py`, `test_fcd.py`),
no nome deste relatório (`correcao-ano-fcd-2026-09-24.md`), e no adendo
de `docs/correcao-fcd-2026-09-23.md` (que dizia a revisão da exclusão de
bancos tinha acontecido "um dia depois" da decisão original).

`git log --format="%h %ci %s"` confirma que TODOS os commits desta
sessão — incluindo `7a29e7f` e o da exclusão de bancos (`f285819`) — são
de **2026-09-23**; não havia nenhum "dia seguinte". A data real do
commit (`git log`), não a memória da conversa, foi usada como fonte de
verdade pra corrigir. Corrigido no commit seguinte a este relatório: as
datas nos comentários de código e teste, o nome deste arquivo (renomeado
de `correcao-ano-fcd-2026-09-24.md` pra `correcao-ano-fcd-2026-09-23.md`)
e o texto do adendo em `docs/correcao-fcd-2026-09-23.md`.

---

## 10. Commits

| Commit | O que contém |
|---|---|
| `7a29e7f` | Detecção automática do ano de referência do FCD (dois níveis), rótulo no cartão, coluna `ano_referencia_fcd`, TTL do cache do zip, aviso visível no Screener — código + testes (datas erradas, ver seção 9) |
| `1560fac` | `screener.csv` regenerado pelo botão real, todas as ações aplicáveis com `ano_referencia_fcd=2025` |
| *(este commit)* | Corrige as datas "2026-09-24" → "2026-09-23" em código/testes/docs (seção 9) e adiciona este relatório |
