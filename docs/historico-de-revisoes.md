# Histórico de revisões

Este documento reúne as auditorias, vistorias, baterias de testes, correções e revisões de código feitas no projeto entre 18/09/2026 e 06/10/2026 (com o tratamento da última, concluído em 19/10/2026), mais o registro do redesenho do app e do catálogo enxuto de 20 a 23/10/2026. O processo foi o mesmo em todas: um achado aponta um problema, o problema é confirmado no código antes de qualquer correção, a correção sai com teste e o resultado é registrado aqui. As decisões de metodologia do modelo (o que calcular e como) estão em [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md); as limitações que ficaram para quem usa o app estão em [`limitacoes-conhecidas.md`](limitacoes-conhecidas.md).

## Como ler

Cada seção traz a data, o escopo, os achados principais com a gravidade dada no relatório original, como foram resolvidos e os commits. Os hashes são os do histórico do Git (`git show <hash>`). Os relatórios originais foram removidos da pasta `docs/` e continuam no histórico: todos existem no commit `90327ec`, o último antes da remoção.

### Relatórios que este documento substitui

Para ler o texto original de qualquer relatório:

```bash
git show 90327ec:docs/<arquivo>.md
# ou, para gravar num arquivo fora do repositório (PowerShell):
git show 90327ec:docs/<arquivo>.md > $env:TEMP\<arquivo>.md
# lista de tudo o que existia na pasta naquele commit:
git ls-tree --name-only 90327ec docs/
```

| Arquivo removido | Seção deste documento | Recuperar |
|---|---|---|
| `auditoria-2026-09-18.md` | 18/09, auditoria analítica | `git show 90327ec:docs/auditoria-2026-09-18.md` |
| `vistoria-pre-publicacao-2026-09-20.md` | 20/09, vistoria pré-publicação | `git show 90327ec:docs/vistoria-pre-publicacao-2026-09-20.md` |
| `bateria-testes-2026-09-21.md` | 21/09, bateria de testes | `git show 90327ec:docs/bateria-testes-2026-09-21.md` |
| `correcoes-2026-09-22.md` | 22/09, correções de interface | `git show 90327ec:docs/correcoes-2026-09-22.md` |
| `correcao-fcd-2026-09-23.md` | 23/09, dívida líquida e bancos (síntese aqui; decisão em `decisoes-de-metodologia.md`) | `git show 90327ec:docs/correcao-fcd-2026-09-23.md` |
| `correcao-ano-fcd-2026-09-23.md` | 23/09, ano de referência (síntese aqui; decisão em `decisoes-de-metodologia.md`) | `git show 90327ec:docs/correcao-ano-fcd-2026-09-23.md` |
| `correcao-cnpj-2026-09-25.md` | 25/09, CNPJ sem zero à esquerda | `git show 90327ec:docs/correcao-cnpj-2026-09-25.md` |
| `auditoria-tecnica-2026-09-27.md` | 27/09, auditoria técnica (P01 a P17) | `git show 90327ec:docs/auditoria-tecnica-2026-09-27.md` |
| `vistoria-2026-09-28.md` | 28/09, vistoria de acompanhamento (N01 a N08) | `git show 90327ec:docs/vistoria-2026-09-28.md` |
| `vistoria-2026-09-28-b.md` | 28/09, terceira passada (V01 a V10) | `git show 90327ec:docs/vistoria-2026-09-28-b.md` |
| `auditoria-externa-2026-10-05.md` | 05/10, auditoria externa | `git show 90327ec:docs/auditoria-externa-2026-10-05.md` |
| `revisao-codigo-2026-10-05.md` | 05/10, revisão de código | `git show 90327ec:docs/revisao-codigo-2026-10-05.md` |
| `revisao-codigo-2026-10-06.md` | 06/10, revisão de código e tratamento de 19/10 | `git show 90327ec:docs/revisao-codigo-2026-10-06.md` |
| `especificacao.md` | Sem seção própria: era o planejamento anterior ao código. O escopo (só ações do Ibovespa, sem FIIs nem small caps) e o backtest fora de escopo passaram para o README | `git show 90327ec:docs/especificacao.md` |

As investigações de 02/10 a 04/10 (P03/P04, P10, fluxo-base e cíclicas) estão em [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md), que tem a sua própria tabela de recuperação.

## Linha do tempo

| Data | Relatório | Tipo | Gravidade máxima | Testes na época |
|---|---|---|---|---|
| 18/09 | Auditoria analítica (Fase 1) | Leitura do código | Alta | n/d |
| 20/09 | Vistoria pré-publicação | Leitura do código e do repositório | Alta (documentação) | 316 |
| 21/09 | Bateria de testes | Código, leitura e testes ao vivo | Alta (texto público) | n/d |
| 22/09 | Correções de interface | Correção | n/a | 326 a 336 |
| 23/09 | Dívida líquida e bancos no FCD | Correção de metodologia | n/a | 341 |
| 23/09 | Ano de referência do FCD | Correção de metodologia | n/a | n/d |
| 25/09 | CNPJ sem zero à esquerda | Correção de dados | n/a (afetava 20 de 76 ações) | 400 a 405 |
| 27/09 | Auditoria técnica | Leitura e reprodução | Alta | 444 |
| 28/09 | Vistoria de acompanhamento | Leitura e reprodução | Alta | 465 |
| 28/09 | Vistoria, terceira passada | Leitura e reprodução | Média | 466 |
| 05/10 | Auditoria externa | Leitura de um ZIP do projeto | Média/alta | 844 a 1216 |
| 05/10 | Revisão de código | Leitura e reprodução | Média/alta | 1216 a 1302 |
| 06/10 | Revisão de código | Leitura e reprodução | Alta | 1317 a 1372 |
| 20 a 23/10 | Redesenho, FCD ≤ 0 e catálogo enxuto | Mudança de produto, com defeitos achados no caminho | n/a | 1372 a 1724 |

---

## 18/09/2026: auditoria analítica (Fase 1)

**Escopo.** Auditoria só de leitura de todo o `src/avaliador_b3/`, módulo a módulo (19 módulos), em seis categorias: corretude, consistência, código morto, duplicação, números mágicos e type hints.

**Achados principais.** 13 de corretude, 5 de consistência, 2 de código morto, 6 de duplicação, 9 de números mágicos e 3 de type hints; o `app/main.py` concentrava cerca de um terço do total.

| Gravidade | Achado |
|---|---|
| Alta | Volume médio devolvia `NaN` para histórico vazio e a tela mostrava "nan" |
| Alta | A chave do cache do Banco Central ignorava as datas: a série de câmbio ficava presa na janela da primeira busca |
| Alta | Cache do Fundamentus sem prazo nem versão de formato, que já tinha causado um `KeyError` ao vivo |
| Média | Histórico vazio sem tratamento no gráfico; exceção errada em `_valor_conta`; contrato duplicado entre Graham e os métodos não aplicáveis |
| Baixa | Duas divisões por zero não alcançáveis hoje; tipo inconsistente de `codigo_cvm` entre execução fresca e cache |

**Resolução.** Cinco lotes, um commit por lote: `cdb0ec5` (lote 1: bugs de cache e exceção no `ingest`, e helper de paginação), `891fa99` (lote 2: volume médio e Bazin com DataFrame vazio), `433598e` (lote 3: triplicação em `correlacao.py` e dois `ZeroDivisionError`), `f595e1b` (lote 4: histórico vazio e duplicações no `main.py`) e `6de2a45` (lote 5: `DATA_CACHE_DIR` e os pacotes vazios `macro/` e `setorial/`).

## 20/09/2026: vistoria pré-publicação

**Escopo.** Duas partes: as mudanças desde a auditoria anterior (a sessão do tema de cores) e a prontidão do repositório para publicação (README, licença, `.gitignore`, dependências, estrutura). `pytest` com 316 testes e `ruff` passavam limpos.

**Achados principais.** Nenhum de corretude.

| Gravidade | Achado |
|---|---|
| Alta | README desatualizado: dizia que os adapters ainda não estavam implementados |
| Alta | README sem instruções de instalação e execução |
| Média | `CORES_CENARIO` ficava no `main.py` e não no `config.py`, junto das demais cores |
| Baixa | Comentário de `COR_NEUTRA` fora da realidade; `.gitignore` sem os caches das ferramentas; `lxml` e `openpyxl` sem uso confirmado |
| Informativo | `LICENSE` ausente; seção da especificação com o segmento de listagem "Em aberto" já resolvida |

**Resolução.** `e45723b`: README reescrito, cores organizadas, dependências limpas e licença MIT. O tema aplicado antes é o `b6b3ca9`.

## 21/09/2026: bateria de testes e procura de bugs

**Escopo.** Três partes: (A) generalizar `_fmt_bilhoes`, que truncava valores grandes; (B) auditoria estática do que nunca tinha sido revisado; (C) seis testes exploratórios ao vivo.

**Achados principais.** Nenhum bug de corretude. Os seis testes ao vivo passaram (ITUB4, PETR3 contra PETR4, Graham e Bazin não aplicáveis, ticker de histórico curto, carteira sem cenário e o botão do screener). O PETR3 e o PETR4 mostram LPA, VPA e ROE idênticos porque o Fundamentus publica métricas da empresa, e não da classe: comportamento real, não vazamento de dado.

| Gravidade | Achado |
|---|---|
| Alta | A nota de rodapé dizia que a tela em branco era a única indicação de app dormindo; o Streamlit Community Cloud mostra uma página com um botão para acordar. Texto público |
| Média | Comentário de `COR_GRAFICO_CONTEXTO` descrevia só um dos usos do token |
| Baixa | Cabeçalho de data da seção de paleta sem cobrir `CORES_CENARIO` |

**Resolução.** `7db90a3` (parte A, texto do rodapé e documentação) e `b3d3523` (truncamento dos valores grandes). No mesmo dia, o repositório foi preparado para o deploy: `72e6b9b` e `19f24da` (exceção do `screener.csv` no `.gitignore` e nota sobre o primeiro acesso).

## 22/09/2026: correções de interface

**Escopo.** Quatro commits no mesmo dia, todos motivados por bugs vistos em captura de tela ao vivo, e não por leitura do código.

| Commit | Correção |
|---|---|
| `3b84384` | Texto público desatualizado, "Preço atual" sem vírgula e truncamento em "Saúde financeira" (de 4 para 2 colunas) |
| `b16bf22` | Ponto decimal americano em moeda e percentual (cartões, gráficos e 4 tabelas) e mês em inglês nos eixos |
| `66da64a` | Espaçamento irregular de mês nos eixos, regressão do commit anterior corrigida no mesmo dia |
| `7016921` | Limpeza do código dos três commits acima, com um gap de mock em teste corrigido |

A suíte foi de 326 para 336 testes, com `ruff` limpo em todos. O registro foi feito em `8545f8f`.

## 23/09/2026: dívida líquida e bancos no FCD

**Origem.** Uma revisão externa (segunda opinião fora do desenvolvimento) apontou que o FCD dividia o valor da empresa (*enterprise value*) direto pelo número de ações, sem subtrair a dívida líquida: o valor por ação saía inflado em toda empresa endividada.

**Resolução.** `2f66089` subtrai a dívida líquida antes de dividir por ação. Na regeneração do `screener.csv` (`e26dd69`), o FCD da PETR4 foi de R$ 118,82 para R$ 94,86. Pouco mais de uma hora depois, uma segunda revisão levou a tornar o FCD "não aplicável" para o segmento Bancos (`f285819`, `f197ac5` e o adendo `371f9b3`). A decisão, as alternativas e o efeito nos seis bancos estão em [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md#11-valor-da-empresa-para-valor-do-acionista-e-bancos). Registro: `c72dc93`.

## 23/09/2026: ano de referência do FCD

**Origem.** O ano de referência do FCD era uma constante fixa (2024), e a CVM já tinha publicado 2025. A investigação encontrou outros dois problemas durante a implementação: o cache do zip anual da CVM era permanente (um zip baixado cedo, ainda incompleto, ficaria preso) e o motivo da falha do FCD não chegava à coluna "erro" do Screener.

**Resolução.** `7a29e7f`: detecção automática do ano em dois níveis (arquivo e empresa), prazo de validade de 7 dias para o zip do ano em preenchimento e um aviso global no Screener. `1560fac` regenerou o `screener.csv` com `ano_referencia_fcd=2025`. `fc0d89e` corrigiu datas escritas como 24/09 (todos os commits do dia são de 23/09) e registrou o relatório. O desenho e as limitações estão em [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md#12-ano-de-referência-do-fcd).

## 25/09/2026: CNPJ sem zero à esquerda

**Origem.** O ABEV3 não tinha FCD em nenhum ano, registrado como limitação na correção anterior.

**Achado.** Não era um caso isolado: **20 das 76 ações** falhavam com `CnpjNaoEncontrado`. A API da B3 devolve `cnpj` e `codeCVM` como número JSON, que perde o zero à esquerda; 954 dos cerca de 3.523 emissores do catálogo (27%) tinham o CNPJ com menos de 14 dígitos. A validação manual original tinha testado só Petrobras, Vale e Itaú, nenhum com CNPJ começando em zero.

**Resolução.** Correção em três camadas (leitura da API, leitura do cache do catálogo e normalização defensiva no adapter da CVM), sem mapeamento manual por ticker: `31064bb`. O `screener.csv` foi regenerado em `b280240`: as 20 ações passaram a ter FCD, e as seis sem FCD que sobraram são os seis bancos (exclusão estrutural). Foram 5 testes novos (de 400 para 405). Registro: `3be42d0`. O efeito colateral (FCD negativo concentrado em energia elétrica) está em [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md#14-fcd-baixo-e-reinvestimento).

## 27/09/2026: auditoria técnica

**Escopo.** Auditoria sobre o ZIP do `master` de 27/09: 444 testes passando, `ruff` limpo, 34 erros de `mypy`, verificação numérica manual do FCD (bateu até a última casa). Sem rede nem app ao vivo. Cada achado foi marcado como CONFIRMADO, POSSÍVEL ou NÃO FOI POSSÍVEL VERIFICAR.

| ID | Achado | Gravidade | Resolução |
|---|---|---|---|
| P01 | A janela do Bazin cortava o pagamento mais antigo (filtro por data exata, não por ano civil) | Alta | `3396db0`; 11 ações passaram a ter Bazin (`316cb88`) |
| P02 | O Simulador podia projetar perda acima de 100% | Alta | `15ca3c9` |
| P03 | O Simulador tratava o valor justo de hoje como preço daqui a 5 anos | Alta | Decisão de metodologia; `9bea4c6`, `c878f10` |
| P04 | O fluxo de caixa livre (6.01 + 6.02) misturava itens que não são caixa operacional | Alta | Decisão de metodologia; `78f671e`, `e23397b` |
| P06 | Número de ações das units em outra base que o preço | Alta se confirmado | `b2d1d2a`, `bb947fe` |
| P05 | A correlação calculava retornos antes de alinhar as datas | Média | `5cbc7fe` |
| P07 | Falha do Banco Central no Screener era engolida em silêncio | Média | `eb2324a` |
| P09 | Premissas do WACC | Média (limitação) | Decisão de metodologia; `b3cacb6`, `37b7b99` |
| P10 | Crescimento calculado com dois pontos | Média (limitação) | Decisão de metodologia; `5535891`, `05781a3` |
| P12 | Dependências sem versão fixada | Média | `f3f59bb` |
| P14 | Testes cegos para P01, P02, P05 e P06 | Média | Testes dos itens corrigidos; botões selecionados pelo texto em `6270f0f` |
| P08 | Selic e IPCA buscados por duas implementações | Baixa | `bc89350` (função única e erro com menos de 12 meses de IPCA) |
| P11 | "Desconto" é, na verdade, potencial de valorização | Baixa | `26e8002` |
| P13 | README desatualizado | Baixa | `3d2a102` |
| P15 | Datas diferentes no FCD | Baixa | Já documentado na tela |
| P16 | Avisos com estado global no Streamlit | Baixa | Aceito como risco baixo; sem alteração |
| P17 | `mypy` não aplicado | Baixa | `f7e03b1` |

A auditoria também listou o que **não** precisava mudar: a fórmula do FCD e a conversão para valor do acionista, a exclusão de bancos por segmento, retornos com preço ajustado e dividend yield com preço nominal, o Beta alinhando preços antes dos retornos e a normalização do CNPJ. Registro: `fc25c68`.

## 28/09/2026: vistoria de acompanhamento

**Escopo.** Segunda passada depois das correções do dia anterior: 465 testes passando, mas com 43 avisos (eram 3). As reproduções de P01, P02 e P05 deram o resultado correto.

| ID | Achado | Gravidade | Resolução |
|---|---|---|---|
| N01 | Os testes gravavam Selic e IPCA falsos no cache real do projeto | Alta | `04f98c9`: isolamento por teste e verificação da execução inteira |
| N02 | Docstring de `obter_selic_e_ipca` dizia o contrário do código | Baixa | Corrigido (confirmado na vistoria seguinte) |
| N03 | Mensagem de falha do Banco Central repetida e fora de contexto | Baixa | Corrigido (idem) |
| N05 | 43 avisos novos na execução dos testes | Baixa | Corrigido, restaram 12 esperados |
| N04 | O aviso "Banco Central indisponível agora" podia durar até 1 hora depois da volta | Baixa | Sem correção registrada |
| N06 | O valor guardado não protege o app publicado depois de reinícios | Baixa | Sem correção; limitação do Community Cloud |
| N07 | Pior caso de espera de 74 segundos | Baixa | Recomendação do relatório: aceitar |
| N08 | Correlação e Beta não tratam data duplicada | Baixa | Sem correção registrada |

Registro: `64251a5`.

## 28/09/2026: vistoria, terceira passada

**Escopo.** Passada mais funda nos adapters (Fundamentus, CVM, catálogo da B3, universo do Ibovespa, GPR), nos prazos de cache, no tratamento de erro por ação no screener e na fidelidade dos testes de interface. 466 testes, `data/` idêntico antes e depois do `pytest` (verificado por hash).

| ID | Achado | Gravidade | Resolução |
|---|---|---|---|
| V02 | Universo do Ibovespa em cache sem prazo, mas a carteira muda três vezes por ano | Média | `a5ed7aa` |
| V03 | Série diária do GPR em cache sem prazo | Média | `a5ed7aa` |
| V05 | No Screener, uma falha de rede no Fundamentus ou na CVM derrubava a linha inteira | Média | `cfd653a`: nova tentativa compartilhada com 429 e disjuntor do Fundamentus |
| V01 | 32 testes de interface validavam a tela no estado de falha da CVM | Média | `6270f0f`: ano da CVM simulado e botões selecionados pelo texto |
| V04 | Catálogo de emissores da B3 em cache sem prazo | Baixa | `a5ed7aa` |
| V06 | A leitura da CVM não filtrava a versão do documento | Baixa | `b7b1267` (06/10, ver abaixo) |
| V07 | Rótulos repetidos na página do Fundamentus | Baixa | Sem correção registrada |
| V08 | O isolamento por `__defaults__` não cobre parâmetros só-nomeados | Baixa | Sem correção registrada |
| V09 | Dois rótulos ambíguos na tela ("Último fechamento", "Volume médio") | Baixa | Sem correção registrada |
| V10 | A leitura da CVM varre arquivos inteiros por empresa | Baixa | Recomendação do relatório: aceitar. A leitura em lote só se justifica com a série histórica das cíclicas (ver `decisoes-de-metodologia.md`) |

A vistoria confirmou o que não precisava mudar: o isolamento dos testes, a leitura em streaming da CVM, a normalização do CNPJ e a separação entre dado ausente e erro nos modelos. Registro: `42cf5dc`. A decisão sobre o Simulador (P03) e o FCF (P04) foi tomada na investigação de 02/10.

## 05/10/2026: auditoria externa

**Escopo.** Auditoria técnica feita sobre um ZIP do projeto (57 arquivos Python, 839 funções de teste), sem acesso ao Streamlit nem à rede; os testes de interface não rodaram nela (746 testes passaram). 36 itens e um veredito. A auditoria deu notas por área (arquitetura 8,5, engenharia 8, testes 9, tratamento de dados externos 8,5, robustez de cache 6,5, robustez numérica 6,5, interface 8, metodologia financeira 7, documentação 9; estado geral 8/10) e recomendou **não reescrever** o projeto, e sim fazer correções cirúrgicas.

**Tratamento.** Cada item foi confirmado no código antes de corrigir. A suíte foi de 844 para 1216 testes, com `ruff` e `mypy` limpos.

| Item | Resultado | Commit |
|---|---|---|
| 3. `NaN` e infinito viravam valor justo | Confirmado com reprodução. Graham, Bazin e FCD ficam "não aplicáveis" com o campo inválido no motivo; a rodada do screener é rejeitada se uma linha trouxer valor não finito | `9ac32bc` |
| 4 e 20. Cache corrompido e gravação não atômica | Confirmado: JSON truncado levantava `JSONDecodeError` em 4 adapters e CSV truncado era lido com a última linha cortada. Arquivo inválido passa a valer como cache ausente e todas as gravações usam temporário e troca atômica | `beb52bd` |
| 7. Ticker interpolado no JavaScript do TradingView | Confirmado (baixo impacto). O widget só é montado para ticker no formato da B3 e a configuração é serializada com `json.dumps` | `59e2156` |
| 5. Proveniência da Selic e do IPCA | O valor guardado e o arquivo de referência perdiam a fonte; agora a preservam | `f11012d` |
| 6. Ordem entre `screener.csv` e `macro_referencia.json` | Confirmado com reprodução; a referência é preparada antes da troca do CSV | `f11012d` |
| 23. Alvo do `mypy` | `python_version = "3.12"`, igual ao `requires-python` e ao `ruff` | `1d5ddb0` |
| 24. `SyntaxWarning` nos testes | A correção sugerida (`"R$ 109"`) quebraria os testes, porque o app emite `R\$`; o certo era `"R\$"` | `1d5ddb0` |
| `ruff` e a pasta `docs/` | `ruff format .` reformatava os blocos de código dos Markdown; `docs/` entrou no `extend-exclude` | `1d5ddb0` |
| 8. APIs depreciadas do Streamlit | `use_container_width` virou `width="stretch"`. A auditoria recomendava `st.html`, mas o widget precisa de JavaScript: a substituição certa é `st.iframe` | `854ee29` |
| 21. Concorrência na gravação do cache | Reaberto pela revisão de código do mesmo dia (temporário de nome fixo disputado) | `0859584` |
| 10 e 11. Suíte sem execução completa | Resolvido: a suíte inteira roda no ambiente do projeto | n/a |

**Sem ação, e por quê.**

| Item | Motivo |
|---|---|
| 21. Travas por chave entre sessões | Com o temporário de nome único não há mais arquivo misturado; trava entre processos pediria uma biblioteca de lock |
| 22. Pacote relocável | O uso é o repositório (GitHub e Streamlit Community Cloud) |
| 33. Renomear `desconto_percentual` | É coluna do `screener.csv`, lido pelo app, pelo workflow e pelos testes: seria migração de schema. A tela já mostra "Potencial" |
| 14, 15 e 36. Crescimento por dois pontos e empresas cíclicas | Limitações metodológicas já investigadas em 04/10 (ver `decisoes-de-metodologia.md`) |
| 16 e 36. Selic como taxa livre de risco | Decisão registrada, coerente com o código; pede investigação própria |
| 17, 18, 19 e 36. Valor combinado e cenários do simulador | Escolhas de modelo, documentadas na tela |
| 31 e 32. Risco sacado e sensibilidade ao valor terminal | Decisão metodológica; o aviso de valor extremo já existe |
| 25. Dependência do Yahoo Finance | Risco operacional externo, isolado no adapter de preços |
| 9, 12, 26 a 30 e 34 | Pontos positivos, não são bug |

Registros: `3c21f17` (auditoria) e `5fe36f4` (tratamento).

## 05/10/2026: revisão de código

**Escopo.** Revisão feita sobre um ZIP do repositório, focada no código novo do dia (validação de números finitos, cache seguro e gravação atômica, ticker do TradingView, proveniência da Selic e do IPCA, ordem de gravação do screener) e nas diferenças entre Windows (desenvolvimento) e Linux (CI e GitHub Actions). 7 achados.

| # | Achado | Classificação | Resultado | Commit |
|---|---|---|---|---|
| 1 | `gravar_texto_atomico()` não era seguro contra duas gravações simultâneas | Bug, média/alta | Pior que o relato: com 20 threads houve erro em todas as rodadas e, em 29 de 30, o arquivo final ficou ilegível. Cada escritor passa a usar um temporário de nome único | `0859584` |
| 2 | `screener.csv` e `macro_referencia.json` sem publicação conjunta | Bug | O macro é publicado primeiro e o CSV por último; uma falha no meio deixa o CSV anterior intacto | `a40097e` |
| 3 | `macro_referencia.json.novo` podia ficar abandonado | Bug, baixa | Temporários da rodada apagados em qualquer falha | `a40097e` |
| 4 | Rodadas simultâneas disputando os temporários | Bug, média | Temporários de nome único por rodada; o `screener.rejeitado.csv` mantém o nome fixo (o workflow o publica) e é trocado de forma atômica | `a40097e`, `5e4133c` |
| n/a | O app publicado mostrava o botão "Rodar screener agora" a qualquer visitante | Achado desta rodada | O botão só aparece com o opt-in `AVALIADOR_B3_PERMITIR_RODAR_SCREENER`, negado por padrão | `5e4133c` |
| 5 | `ler_csv_cache()` aceitava um CSV só com cabeçalho | Robustez | Só o cache de dividendos aceita vazio. Agravante achado na reprodução: um universo vazio fazia a rodada ser aceita com zero linhas e trocar o `screener.csv` por um arquivo sem dados; agora é rejeitada | `3d52763`, `a40097e` |
| 6 | `ler_json_cache()` aceitava `NaN` e `Infinity` | Robustez | A leitura os recusa e a gravação nunca os escreve; `VL_CONTA` e a composição do capital da CVM com valor não finito deixam a conta indisponível | `3d52763` |
| 7 | `os.replace()` no Windows e no Linux | Portabilidade | Sem correção possível no código; no Windows a gravação do cache passa a ser tentativa e a publicação da rodada levanta o erro | n/a |

Sem ação adicional: travas contra duas rodadas locais simultâneas (cada rodada publica o seu resultado, e o workflow já tem `concurrency`) e a falha entre as duas trocas da publicação (não há transação entre dois arquivos; a referência é só fallback, com validade de 90 dias). A suíte passou de 1216 para 1302 testes. Registros: `bc93f5b` (revisão) e `16c4626` (tratamento).

## 06/10/2026: revisão de código (tratada em 19/10/2026)

**Escopo.** Segunda revisão de código, feita depois do tratamento da anterior. 7 achados. Foi tratada em etapas, um commit por assunto: `cc7fedf` (Etapa 0, registro da revisão), `b7b1267` (D1), `8a7aaa9` (D2), `a3aaf2d` (D3) e `90327ec` (D4, este registro e o README). A suíte foi de 1317 testes (antes da D2) para 1372, todos passando, com `ruff` e `mypy` limpos.

| # | Achado | Prioridade | Confirmado | Correção | Commit |
|---|---|---|---|---|---|
| 1 | Versões da CVM misturadas no fluxo de caixa | Alta | Reproduzido com DFC sintética. Nos dados reais, efeito nulo: **zero empresas com versão dupla** | Mantém só a maior `VERSAO` por empresa e data, antes de qualquer extração | `b7b1267` |
| 2 | Caches da CVM de anos fechados nunca expiram | Alta | Confirmado no código. Nos dados reais, o **zip de 2024 foi regenerado pela CVM sem mudança nos dados usados** | Zips de anos fechados valem 30 dias (o ano em preenchimento segue com 7). Os caches de fluxo de caixa, lucro e balanço guardam o tamanho e a data do zip de origem e são refeitos quando ele muda ou vence. Schemas do FCF (6) e do balanço (2); o lucro ganha envelope versionado | `8a7aaa9` |
| 3 | Envelope de cache com conteúdo que não é objeto (`[]`, texto, número) | Média | Reproduzido: `[]` era aceito como resultado | Conteúdo que não é `dict` vale como cache ausente e é refeito, com log, no Fundamentus, no fluxo de caixa, no lucro e no balanço | `a3aaf2d` |
| 4 | Divisão por zero em `calcular_acoes_em_circulacao` | Média/baixa | Reproduzido, inclusive com integralizado zero e tesouraria positiva | Sem ações em circulação o número fica indisponível com motivo explícito, e o app usa o do Fundamentus | `a3aaf2d` |
| 5 | Beta e volatilidade com retornos infinitos | Baixa | Confirmado: um fechamento zero no meio da série deixava o Beta e a volatilidade em `NaN` | Retornos infinitos viram `NaN` antes do `dropna` | `a3aaf2d` |
| 6 | `RuntimeWarning` na correlação | Baixa | Confirmado: 2 avisos no teste da série sem variação | A série sem variação é detectada antes do `.corr()`; os avisos da suíte foram de 13 para 11 | `a3aaf2d` |
| 7 | README desatualizado | Portfólio | Confirmado (800 testes, 96% de cobertura, botão "só na execução local") | README e limitações atualizados (mais de 1.300 testes, 97% de cobertura, opt-in do botão, regras da checagem da rodada, gravação atômica dos caches) | `90327ec` |

**Acréscimos além da revisão** (decididos durante o tratamento):

- **Zip ausente sem validade permanente.** Sem o zip no disco, o cache derivado vale o mesmo prazo (30 dias para ano fechado, 7 para o ano corrente), contado pela data do zip guardada no próprio cache. Sem essa data, o cache não vale (`8a7aaa9`).
- **Fechamento não positivo descartado na origem.** `ingest/precos.py` descarta o fechamento zero ou negativo junto com o vazio, o que protege todos os consumidores do histórico, inclusive os gráficos. A troca de ±inf por `NaN` em `comportamento.py` e `correlacao.py` continua como defesa (`a3aaf2d`). A regra vale também para o petróleo: um preço negativo de futuro, como o do WTI em abril de 2020, seria descartado.

## 20 a 23/10/2026: redesenho das três páginas, FCD ≤ 0 e catálogo enxuto

**Escopo.** Não foi uma auditoria: foi uma sequência de mudanças de produto, cada uma com um commit por assunto, testes e conferência na tela antes de commitar. A suíte foi de 1372 para 1724 testes, com `ruff` e `mypy` limpos em cada commit.

**O que mudou.**

- **Redesenho (de `e30028b` a `a0519b9`).** Tema escuro com os tokens de cor no `config.py`; as abas deram lugar a três páginas com menu e controles na barra lateral (`e7c4090`); a análise passou a ter cartões, gráfico de valor justo por método e grade de saúde financeira; o Screener ganhou filtros, quatro cartões, a distribuição do potencial, os cartões "Atenção" e o "Ranking por potencial", cujo ticker abre a análise por `?acao=` (`2284297`); o Simulador passou a montar a carteira por quantidade, com cenários, contribuição, composição por ação e por setor, posições e histórico contra IPCA e CDI (`010bd57` a `ea5c440`).
- **FCD ≤ 0 como não aplicável (`9fcdb76`).** Decisão D, na seção 4.2 de [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md). Em 21/10, 13 das 76 ações mudaram: a GOAU4 foi de −110% para −15% de potencial e a RDOR3, de −35% para +4%.
- **Catálogo enxuto (`f23ed45`, `20aac99`, `14e1ad6`, `6065119`, `e897ca0`).** A rodada do screener grava `data/processed/catalogo_emissores.csv` (ticker, CNPJ e segmento), e a página de análise o lê antes da API da B3. A primeira abertura da análise caiu de cerca de 86 s para cerca de 24 s (medido localmente; só a busca do CNPJ e do segmento foi de 64 s para 0,02 s).

**Defeitos achados no caminho.**

| Defeito | Como apareceu | Correção |
|---|---|---|
| Página de análise caía quando a ação não tinha segmento | Sem a lista do Ibovespa e sem o setor no catálogo, o texto das pílulas ficava vazio e o `st.html("")` levantava erro | A faixa só é desenhada quando há pílula (`6eaf8e6`) |
| Linha do CDI reta no gráfico do histórico | Conferência na tela: com "2 anos" a linha ficava em R$ 7.444 do começo ao fim. As datas de preço do Yahoo vêm com fuso (UTC) e as do Banco Central, sem. O `reindex` não casava nenhuma data e o `fillna(1.0)` escondia o erro | As datas passam a ser comparadas sem fuso, e sem nenhuma taxa nas datas o CDI some em vez de virar linha reta (`ea5c440`) |
| Teste que passava sem verificar nada | Os dados falsos dos testes do histórico usavam datas sem fuso, então a suíte passava com o CDI quebrado | Os dados falsos passaram a usar datas em UTC, e há testes com valores realistas (252 dias úteis a 0,0551% ao dia dão cerca de +14,9%) (`ea5c440`) |
| Observação do Screener cortada na coluna de 360 px | O texto curto do FCD não aplicável (com parcelas e valores) tinha de 124 a 148 caracteres, e os das ações sem método passavam de 400 | Versão mínima só na tabela, limite de 56 caracteres e teste de que todo texto fixo cabe (`a0519b9`) |
| `.gitignore` bloquearia o catálogo enxuto | Notado ao gerar o arquivo localmente: `data/processed/*` é ignorado, então o `git add` do workflow recusaria o arquivo e o `git status` não o enxergaria | Exceção no `.gitignore`, com teste que cobre os três arquivos do commit automático (`6065119`) |
| Checagem de mudança do workflow ignorava arquivo novo | O `git diff --quiet` não vê arquivo ainda fora do git, e o catálogo seria descartado num dia sem mudança no `screener.csv` | Troca por `git status --porcelain` nos dois arquivos, com teste de texto do `.yml` (`f23ed45`) |
| Testes podiam ler o catálogo enxuto do repositório | Com o arquivo versionado, qualquer teste da página o leria no lugar do dublê | O `conftest.py` aponta o caminho do catálogo para uma pasta temporária em cada teste (`20aac99`) |
| Segmento setorial com ponto no texto | A API da B3 devolve "Exploração. Refino e Distribuição" com ponto | Dicionário no `config.py` troca o texto só na exibição (`6403ce8`) |
