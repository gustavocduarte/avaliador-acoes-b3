# Bateria de testes e procura de bugs (2026-09-21)

Foco diferente das duas auditorias anteriores (`docs/auditoria-2026-09-18.md`,
`docs/vistoria-pre-publicacao-2026-09-20.md`), que cobriram o código-fonte
estaticamente, módulo a módulo. Esta rodada tem três partes: (A) fechar uma
decisão pendente do truncamento de valores grandes, com mudança de código;
(B) auditoria estática só do que nunca foi revisado formalmente (introduzido
nas duas últimas sessões); (C) testes exploratórios ao vivo no app, focados
em casos de borda de dado real. B e C são só investigação — nenhuma correção
aplicada nesta fase.

---

## Parte A — Generalização do `_fmt_bilhoes`

Implementado, testado e verificado visualmente (ver diff e screenshot
enviados separadamente pra aprovação). Resumo: piso de R$ 1 milhão — abaixo
disso mostra o valor completo por extenso ("R$ X.XXX,XX"), a partir daí
abrevia mi/bi como antes. Aplicado também nas 4 métricas de "Total da
carteira" (Investido/Pessimista/Base/Otimista). 2 casos de teste novos
(abaixo do piso, no piso exato) adicionados ao parametrize já existente —
total 6 casos, todos passando. Screenshot confirma R$ 1.000 (default do
campo) continua "R$ 1.000,00", não virou "R$ 0,0 mi".

---

## Parte B — Auditoria estática do que ainda não foi revisado

### `.streamlit/config.toml`

Sem achados. 9 linhas, só chaves de tema suportadas (confirmadas contra a
doc oficial na sessão do tema), sem lógica.

### `config.py` — constantes `COR_*` e `CORES_CENARIO`

**Achado — DOCUMENTAÇÃO (prioridade média)**: o comentário de
`COR_GRAFICO_CONTEXTO` (`config.py:569-572`) descreve seu uso como "marca a
série de comparação (**benchmark: Ibovespa ou petróleo**)" — mas o token é
reutilizado em mais dois lugares que não são esse tipo de comparação:

- A linha de Dividend Yield no gráfico de histórico de dividendos
  (`app/main.py:1047-1048`) — é uma segunda métrica da **mesma** ação, não
  um benchmark externo.
- A linha de inflação (IPCA) no gráfico de projeção de carteira
  (`app/main.py:1508`) — também não é Ibovespa nem petróleo.

Funcionalmente correto (a cor É neutra/discreta nos dois casos, cumpre bem o
papel), só o comentário descreve um escopo mais estreito do que o token
realmente cobre hoje. Não corrigido nesta fase.

**Achado — cosmético (prioridade baixa)**: o cabeçalho da seção,
`# --- Paleta de tema (2026-09-19) ---` (`config.py:559`), data só a adição
original (`COR_GRAFICO_*`/`COR_GANHO`/`COR_PERDA`/`COR_NEUTRA`, commit
`b6b3ca9`, 2026-09-19). `CORES_CENARIO`, adicionado um dia depois (commit
`e45723b`, 2026-09-20, no lote de correção da vistoria pré-publicação), cai
dentro da mesma seção sem cabeçalho próprio — a data no topo não cobre todo
o conteúdo do bloco. Puramente cosmético, sem impacto funcional.

Confirmado por grep que todos os imports de `COR_GRAFICO_*`/`CORES_CENARIO`
em `app/main.py` são usados (nenhum import morto) — `COR_GANHO`/`COR_PERDA`/
`COR_NEUTRA` não são importados individualmente em `main.py` porque só são
consumidos indiretamente via `CORES_CENARIO`, já montado dentro do próprio
`config.py` — consistente com a decisão tomada na correção anterior.

### Nota de rodapé (`app/main.py:1568-1576`) e comentário que a justifica

**Achado — CORRETUDE de conteúdo (prioridade ALTA, é texto público)**: tanto
o comentário interno quanto o texto exibido pro usuário partem de uma
premissa **factualmente incorreta** sobre o comportamento do Streamlit
Community Cloud. O comentário diz: *"sem indicação nenhuma nativa da
plataforma de que isso está acontecendo (a tela só fica em branco/
carregando)"*. Confirmei contra a documentação oficial
(`docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app`):
quando alguém visita um app dormindo, a plataforma mostra uma **página
própria de "app dormindo"**, e a pessoa precisa **clicar num botão** ("Yes,
get this app back up!") pra acordar o app — não é automático, e não é uma
tela em branco.

Isso significa que o texto do rodapé em si (*"se o app estiver 'dormindo',
o primeiro acesso pode levar cerca de 1 minuto pra carregar"*) está
incompleto: não menciona que é preciso clicar em algo, dá a entender que
basta esperar. Prioridade alta porque é conteúdo público, visível pra
qualquer visitante do app — vale corrigir o texto pra mencionar o clique
explicitamente (algo como "a plataforma vai pedir um clique pra acordar o
app, depois leva ~1 minuto"). Não corrigido nesta fase, só documentado.

### Exceção do `screener.csv` no `.gitignore`

Sem achados — texto confere com o comportamento real do app (`_carregar_
screener_ou_avisar` mostra instrução clara quando o arquivo não existe, não
"vazio sem explicação").

---

## Parte C — Testes exploratórios ao vivo

Todos os 6 testes rodados contra o app real (`streamlit run`, servidor
reiniciado com o código da Parte A). Nenhuma correção aplicada — só
documentado, conforme pedido.

### 6. Ação bancária (ITUB4) — **passou**

Campos ausentes no Fundamentus pra bancos (`Liquidez corrente`, `Dív.
líq./patrim.`, `Dívida líquida`, `Valor de firma`) aparecem como "N/D"
limpo, layout intacto, caption explicativo visível. `Valor de mercado`
(não depende de dívida líquida) calculado normalmente: R$ 472,8 bi.

### 7. Par de classes (PETR3 vs. PETR4) — **passou, com observação**

Preço, delta e métricas calculadas corretamente e **diferentes** entre as
duas classes (PETR3 R$ 53,45 vs. PETR4 ~R$ 48,50 no início da sessão).
**Observação**: LPA, VPA, ROE, margem líquida, dívida líquida e patrimônio
líquido são **idênticos** entre PETR3 e PETR4 (confirmado nos dois JSONs de
cache: `lpa: 10.35`, `vpa: 37.32` em ambos). Investiguei se era vazamento
de dado entre tickers — **não é**: verifiquei direto contra
`fundamentus.com.br/detalhes.php?papel=PETR3` ao vivo e o site real também
mostra LPA=10,35/VPA=37,32 pra PETR3. Fundamentus reporta esses indicadores
em nível de empresa (lucro/patrimônio total ÷ total de ações, somando as
classes), não por classe — nosso adapter está extraindo corretamente o que
a fonte publica. Nenhum código a corrigir; achado é só a confirmação de que
o comportamento é fiel à fonte, não um bug.

### 8. Graham/Bazin não aplicável — **passou**

- **AURE3** (LPA=-1,04, confirmado no cache): Graham mostra "—" com "Não
  aplicável: Fórmula de Graham exige LPA>0 e VPA>0 (LPA=-1,04, VPA=10,96)."
  FCD continua aplicável (R$ -36,92, valor negativo válido pro modelo, não
  um erro). Valor combinado = FCD sozinho.
- **ALOS3**: Bazin mostra "—" com "Não aplicável: Empresa não distribuiu
  dividendos em cada um dos últimos 5 anos — histórico não é relevante o
  suficiente para o método Bazin." Graham e FCD aplicáveis normalmente,
  caso isolado (só Bazin falha).

Nenhuma quebra de layout, nenhum valor cru (`None`/`nan`) na tela.

### 9. Ticker com histórico curto — **não reproduzível hoje; verificado por código**

Chequei os 76 arquivos `*_1y.csv` cacheados em `data/raw/precos/` — **todos
têm exatamente 250 linhas** (um ano cheio de pregões), incluindo `MBRF3`
(ticker mais "novo" cogitado, resultado da fusão BRF+Marfrig — já tem
histórico completo sob esse símbolo). Nenhum dos 76 componentes atuais do
Ibovespa tem histórico curto o suficiente pra disparar esse caso de borda
com dado real hoje.

Não reproduzido ao vivo, mas confirmado por leitura de código que o
caminho degrada graciosamente por construção: `calcular_beta` devolve
`None` com menos de 2 retornos pareados (`empresa/comportamento.py:68-69`);
`calcular_volatilidade_anualizada` devolve `None` se não houver ao menos 2
preços (`empresa/comportamento.py:40-41`); a taxa de crescimento do FCD
cai pro IPCA como fallback quando a base de 5 anos atrás não está
disponível (`modelos/fcd.py`, já documentado em sessão anterior). A UI já
trata `None` como "—"/"Histórico curto demais pra calcular" nesses três
pontos (confirmado em sessões anteriores). Risco baixo — não é um caso
alcançável com o universo real atual, e o código já se protege por
construção.

### 10. Carteira sem nenhum método aplicável (HAPV3 + MRVE3) — **passou**

Cada ticker recebe um aviso individual nomeado: *"HAPV3: R$ 1000.00
investidos, mas sem cenário — Nenhum método (Graham, Bazin, FCD) aplicável
— sem cenário pra projetar."* (idem MRVE3). "Total da carteira" mostra
*"Nenhuma das ações selecionadas tem cenário disponível — sem projeção pra
somar (ver avisos acima)."* — sem tabela vazia, sem zero inventado, sem
erro.

### 11. "Rodar screener agora" via botão real — **passou**

Rodado duas vezes nesta sessão (uma pra popular o cold-start dos testes de
Parte A/C, outra especificamente pro item 11) — **76 ações, 0 erros** nas
duas vezes. Coluna "Erro" existe na tabela e ficaria visível se algum
ticker falhasse; nas duas execuções ficou vazia pra todas as linhas.
`data/processed/screener.csv` foi regenerado com dado de mercado mais
recente como efeito colateral real desses dois runs — sinalizado
separadamente na entrega, não faz parte do diff da Parte A.

---

## Resumo executivo

| # | Prioridade | Parte | Local | Achado |
|---|---|---|---|---|
| 1 | **ALTA** | B | `app/main.py:1568-1576` (+ comentário) | Nota de rodapé e seu comentário afirmam que uma tela em branco é a única indicação de app dormindo — mas o Community Cloud mostra uma página própria com botão de "acordar" que precisa ser clicado. Texto público, visível a qualquer visitante. |
| 2 | Média | B | `config.py:569-572` | Comentário de `COR_GRAFICO_CONTEXTO` descreve só o uso "benchmark Ibovespa/petróleo", mas o token também é usado pra Dividend Yield (mesma ação) e linha de inflação (IPCA) — nenhum dos dois é benchmark externo. |
| 3 | Baixa | B | `config.py:559` | Cabeçalho "(2026-09-19)" da seção de paleta não cobre `CORES_CENARIO`, adicionado um dia depois na mesma seção sem data própria. Cosmético. |
| 4 | Informativo | C | PETR3 vs. PETR4 | LPA/VPA/ROE idênticos entre classes — confirmado como comportamento real do Fundamentus (métricas de empresa, não por classe), não um bug de vazamento de dado. |
| 5 | Informativo | C | Item 9 | Nenhum dos 76 tickers atuais do Ibovespa tem histórico de preço curto o suficiente pra reproduzir esse caso de borda hoje — código já teria degradado graciosamente por construção (verificado por leitura, não por reprodução ao vivo). |

Nenhum bug de corretude/crash encontrado na Parte C — os 6 testes
exploratórios (bancos, classes duplas, métodos não aplicáveis, carteira
sem cenário, screener via botão) passaram todos. Os únicos achados reais
desta bateria são de **conteúdo/documentação** (#1 e #2), não de lógica —
diferente do padrão das duas auditorias anteriores, que tinham achados de
corretude confirmados.

Nada foi corrigido nas Partes B/C — aguardando decisão sobre o que vira
lote de correção (a Parte A já está implementada, testada, e aguardando
aprovação em separado).
