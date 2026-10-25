# Limitações conhecidas

Este documento é para quem usa o app. Ele explica o que os números **não** capturam e como o app avisa disso na tela. Para a metodologia resumida, veja o `README.md`.

**Aviso:** os valores do app são estimativas de modelos com premissas simplificadas, para estudo. Não são recomendação de investimento. Um valor justo muito acima ou muito abaixo do preço quase sempre diz mais sobre as premissas do modelo do que sobre a empresa.

Os exemplos usam os dados de 04/10/2026 (preços do fechamento de 02/10/2026, balanços de 30/06/2026). Os números mudam a cada atualização do Screener, então trate os exemplos como ilustrações. Em cada item, "Efeito" diz se a limitação tende a empurrar o valor para cima ou para baixo, quando isso dá para saber, e "Na tela" diz como o app sinaliza.

## Graham, Bazin e valor combinado

- **Graham só olha o passado.** A fórmula usa o lucro e o patrimônio por ação mais recentes e não projeta crescimento. Só se aplica com os dois positivos: em 04/10/2026, 7 das 76 ações ficam sem Graham (CSAN3, USIM5, AURE3, HAPV3, MRVE3, CSNA3 e NATU3).
  - *Na tela:* o cartão mostra "Não aplicável" com o motivo.
- **O Bazin é um preço teto, não um valor justo.** Ele diz quanto pagar, no máximo, para receber 6% ao ano em dividendos, com base nos dividendos dos últimos 12 meses. Só se aplica a quem pagou dividendos em cada um dos 5 anos anteriores (25 das 76 ações ficam sem Bazin em 04/10/2026).
- **Dividendos extraordinários inflam o Bazin.** A fonte dos dividendos (Yahoo Finance) não separa pagamento ordinário de extraordinário.
  - *Efeito:* um pagamento pontual grande eleva o preço teto.
  - *Na tela:* quando os dividendos dos últimos 12 meses passam de 200% da mediana dos 5 anos anteriores, o cartão do Bazin avisa. Em 04/10/2026, isso vale para 16 ações (por exemplo, ALOS3 com 639% e RDOR3 com 650%). Pode ser crescimento real dos pagamentos, e o app não consegue distinguir.
- **O valor combinado é uma média simples.** Os métodos aplicáveis têm o mesmo peso, e o preço teto do Bazin entra na média como se fosse um valor justo. Quando só um método se aplica, o combinado é ele mesmo: em 04/10/2026, CSAN3, USIM5, AURE3, HAPV3 e MRVE3 têm só o FCD.
  - *Na tela:* o cartão do valor combinado lista os métodos usados, e a divergência entre eles aparece na coluna própria do Screener.

## Fluxo de caixa descontado (FCD)

O FCD projeta o fluxo de caixa livre da empresa por 5 anos, soma uma perpetuidade (o valor depois do 5º ano) e traz tudo a valor presente pelo **WACC**, o custo médio ponderado de capital: a taxa mínima de retorno que sócios e credores exigem. Do resultado, desconta o que é de credores e de minoritários e divide pelas ações. Cada etapa tem limitações.

### Quando o FCD não se aplica

Em 04/10/2026, 23 das 76 ações ficam sem FCD, por estes motivos:

- **Bancos** (BBAS3, BBDC3, BBDC4, ITUB4, SANB11 e BPAC11): dívida e depósitos são a própria operação, e o fluxo de caixa varia com a expansão do crédito.
- **Seguradoras** (BBSE3, PSSA3 e CXSE3) e a **Itaúsa** (ITSA4): o caixa vem de prêmios e sinistros, ou de dividendos das empresas em que a holding participa.
- **Fluxo de caixa livre do último ano zero ou negativo** (12 ações: CMIG4, CMIN3, CSMG3, CSNA3, CYRE3, ENEV3, EQTL3, ISAE4, MOTV3, NATU3, SBSP3 e VAMO3): projetar um fluxo negativo para sempre não estima valor.
- **Gasto em investimento (capex) não identificado** (IGTI11): ver "O fluxo de caixa" abaixo.
- Também não é calculado quando a CVM não traz o fluxo de caixa da empresa ou o número de ações não está disponível.

Casos que o app **não** exclui: a B3 (B3SA3), por exemplo, continua com FCD, mas não foi verificado se o modelo é adequado a uma bolsa de valores. Interprete com cautela.

- *Na tela:* o cartão mostra "Não aplicável" com o motivo.

### O fluxo de caixa

O fluxo é o caixa das operações menos o **capex** (gasto em máquinas, prédios, software e outros ativos duráveis). Os juros de empréstimos que a empresa lançou no caixa das operações são somados de volta, líquidos do imposto, para o fluxo ficar antes do financiamento.

- **O capex é achado pela descrição das linhas** do demonstrativo da CVM, e cada empresa escreve de um jeito. Nos dados de 04/10/2026, o capex foi identificado em todas as empresas não financeiras, exceto a IGTI11, que ficou sem FCD. Uma descrição ambígua pode ser classificada de modo diferente do que um analista faria.
  - *Na tela:* sem capex no ano mais recente, o cartão do FCD mostra o motivo. Sem capex no ano-base do crescimento, o crescimento passa a ser o IPCA, e a tela diz isso.
- **Os juros só são somados de volta quando estão no caixa das operações** e em uma linha dedicada a juros de empréstimos, financiamentos ou debêntures. Linhas que misturam juros com outras coisas ficam de fora. Na MRVE3, os juros contam como zero por isso.
  - *Efeito:* nessas empresas o fluxo sai menor do que seria.
- **Um único ano de fluxo.** O caixa das operações de um ano inclui variações de capital de giro (fornecedores, estoques), que podem ser pontuais e não refletem a geração recorrente. O app só corrige a parte que é financiamento de fornecedores (item seguinte); o resto do capital de giro fica como a empresa registrou.
- **Risco sacado e convênio com fornecedores.** Quando um banco paga o fornecedor e a empresa quita o banco depois, o aumento de fornecedores entra no caixa das operações e o pagamento ao banco, no caixa de financiamento, e o caixa das operações parece maior do que a geração de caixa. O app soma ao caixa das operações a saída líquida das linhas de financiamento descritas como convênio, risco sacado, forfait ou cessão de crédito por fornecedores, no ano de referência e no ano-base. Na MGLU3, foram R$ 13,5 bi em 2025 (92% do aumento de fornecedores no caixa das operações), e o FCD passou de R$ 102,16 para −R$ 1,14 por ação. O saldo continua em fornecedores, fora da dívida líquida.
  - *A regra depende da descrição escrita pela empresa:* uma operação com outro nome, ou sem linha própria no financiamento, não é ajustada.
  - *Entradas não são ajustadas, por decisão.* Na VIVA3, a linha "Captação de financiamentos fornecedores convênio" (R$ 146,6 mi em 2025) é uma entrada de financiamento. Na apresentação bruta do convênio (o banco paga o fornecedor e a empresa registra uma entrada de financiamento), o pagamento ao fornecedor já está no caixa das operações como saída, e o caixa das operações não fica inflado; por isso a entrada não é ajustada. Em 2024 esse padrão não aparece (entrada de R$ 48 mi contra aumento de fornecedores de R$ 201 mi), então a natureza dessas entradas é uma hipótese, não confirmada.
  - *A natureza do convênio da MGLU3 é uma inferência pelos números* (a saída no financiamento é quase igual ao aumento de fornecedores no caixa das operações), não confirmada nas notas explicativas.
  - *Na tela:* o cartão do FCD diz o valor reclassificado e o motivo.
- **Arrendamento.** É o aluguel de longo prazo (lojas, frotas, equipamentos) registrado como passivo. O app o trata em três pontos, cada um com seu efeito:
  - *O pagamento dos aluguéis fica fora do fluxo*, porque quase sempre está no caixa de financiamento. Em relação a tratar o aluguel como custo da operação, isso **eleva** o fluxo e o valor.
  - *O passivo de arrendamento existente é descontado no fim*, do valor do acionista. Em relação a ignorá-lo, isso **reduz** o valor e compensa parte do ponto anterior, mas só cobre os contratos de hoje, não os aluguéis futuros nem as renovações.
  - *O arrendamento não entra nos pesos do WACC.* Enquanto os pesos forem contábeis, somá-lo à dívida baixaria o WACC e empurraria o valor para cima; deixá-lo de fora faz o WACC ficar um pouco **mais alto** e o valor **menor** do que ficaria com ele nos pesos.
  - *No conjunto*, o valor de quem aluga muito (varejo, logística) tende a ficar acima do que seria se o aluguel fosse tratado como custo da operação, porque o desconto do passivo não cobre os aluguéis futuros.
- **Perto de zero, o valor é muito sensível.** A RDOR3, em 04/10/2026: caixa das operações de R$ 538 milhões, capex de R$ 3.287 milhões e R$ 4.284 milhões de juros pagos, somados de volta líquidos do imposto (R$ 2.827 milhões). O fluxo fica em R$ 79 milhões, positivo só por causa dos juros, e o FCD é de −R$ 6,04 por ação.
  - *Na tela:* se a conta der zero ou negativa, o FCD fica "Não aplicável", com o motivo (ver "Empresas com deduções acima do valor da empresa", abaixo). Nenhum valor negativo aparece.
- **Empresas que investem muito ficam com FCD baixo.** Em energia e saneamento, por exemplo, o modelo trata todo o investimento como saída de caixa e só projeta crescimento por dois pontos de dados.
  - *Efeito:* o FCD tende a ficar baixo, ou não aplicável quando fica zero ou negativo, mesmo em empresas saudáveis.
  - *Na tela:* o cartão do FCD mostra quanto do caixa operacional foi reinvestido, dividindo o capex pelo mesmo caixa que o FCD usa (com os juros somados de volta e o ajuste de risco sacado). A coluna "Reinvestimento" do Screener usa a mesma conta.

### Crescimento e perpetuidade

- **Crescimento por dois pontos, limitado pela receita.** O crescimento dos 5 anos projetados começa na taxa composta anual entre o fluxo do último ano (2025) e o de 5 anos antes. Ele é limitado por cima pelo crescimento da receita líquida no mesmo período, porque um fluxo que cresce mais que a receita por 5 anos exigiria margem melhorando sem limite; limitar ao crescimento da receita assume margem constante. A faixa de −20% a +30% ao ano continua valendo como limite externo. Em 04/10/2026, 17 das 53 ações com FCD ficam limitadas pela receita, 3 ficam no teto de +30% (AZZA3, CURY3 e RENT3) e uma no piso (ENGI11).
  - *Efeito:* reduz o valor de quem tinha um crescimento do fluxo bem acima do da receita. Por exemplo, a TIMS3 (receita de R$ 17,3 bi em 2020 para R$ 26,6 bi em 2025, 9,0% ao ano) fica com FCD de R$ 27,63 contra o preço de R$ 18,55.
  - *Na tela:* o cartão do FCD diz quando o crescimento foi limitado pela receita e qual foi a taxa; sem receita utilizável (a BRAP4 tem receita não positiva), vale o crescimento do fluxo, e o cartão diz o motivo.
- **Convergência para a perpetuidade.** O crescimento do ano 1 é o calculado, e ele cai em passos iguais até o da perpetuidade no ano 5, sem salto de um ano para o outro. A regra vale nos dois sentidos: reduz o valor de quem tem crescimento alto e aumenta o de quem tem crescimento negativo (a PETR4, com crescimento de −5,0%, converge para cima).
- **Sem histórico utilizável, o crescimento é o IPCA.** Isso vale quando a empresa não tem demonstração do ano-base, ou o fluxo dele não é positivo. Em 04/10/2026, são 9 ações (AURE3, BRAV3, EMBJ3, HYPE3, MRVE3, MULT3, RAIL3, RDOR3 e SMFT3).
  - *Na tela:* o cartão do FCD diz que o crescimento foi estimado pelo IPCA e o motivo.
- **Empresas cíclicas.** Com o crescimento medido entre dois anos, a posição dos anos no ciclo decide o resultado, e a convergência atenua, mas não corrige. Na VALE3, em 04/10/2026, o fluxo de 2020 (R$ 55,1 bi) está perto do pico (1,5 vez a mediana de 2019 a 2025) e o de 2025 (R$ 19,1 bi) perto do vale (0,5 vez a mediana), o que dá um crescimento de −19,1% ao ano. Na GGBR4, o fluxo de 2025 (R$ 2,1 bi) é 0,35 vez a mediana de 2019 a 2025.
  - *Efeito:* o crescimento negativo é um retrato do ponto do ciclo, e não da trajetória da empresa; o valor sai baixo nessas ações, e o sinal do FCD pode mudar com pequenas variações das premissas (a GGBR4 fica em R$ 0,14 por ação).
  - *Valores normalizados (investigação de 04/10/2026, ainda não implementada; ver a seção 8 de [`decisoes-de-metodologia.md`](decisoes-de-metodologia.md)):* se o fluxo-base fosse a margem média do fluxo na janela vezes a receita de 2025, com o crescimento pela receita da janela e o ajuste da quebra de 2019 (IFRS 16), o FCD por ação ficaria, para a janela de 2010 a 2025, de 2015 a 2025 e de 2019 a 2025: VALE3 R$ 48,2, R$ 67,9 e R$ 72,6 (hoje R$ 5,40); GGBR4 R$ 14,8, R$ 17,4 e R$ 20,4 (hoje R$ 0,14); PETR4 R$ 78,6, R$ 96,2 e R$ 127,8 (hoje R$ 44,55). **A sensibilidade à janela é a principal limitação**: a escolha entre 7, 11 e 16 anos muda o valor em 38% (GGBR4), 51% (VALE3) e 63% (PETR4), do menor para o maior, porque a média depende de quanto do superciclo de 2020 a 2022 entra nela. Por isso a normalização ainda não foi adotada; a decisão é normalizar só GGBR4, GOAU4, PETR3, PETR4, USIM5 e VALE3 (setor de commodities e receita nominal em queda em pelo menos 1/3 dos anos), pela janela de 2015 a 2025, depois da migração para o Supabase.
- **Receita que cresce por mudança de perímetro deixa o teto frouxo.** A receita pode crescer por aquisições ou reorganização societária, e não por crescimento operacional, e então limitar o fluxo a esse crescimento deixa de ser um limite. Na CSAN3, a receita vai de R$ 13,5 bi em 2020 para R$ 40,4 bi em 2025 (24,5% ao ano), com saltos em 2021 e 2022 compatíveis com mudanças de perímetro (a causa não foi verificada nas notas explicativas).
  - *Efeito:* o crescimento do fluxo limitado por uma receita inflada fica alto, e o valor, para mais.
- **Concessões podem registrar receita de construção.** Em concessões, a receita pode incluir uma receita de construção que acompanha o investimento, e isso distorce o teto pela receita. É uma hipótese não verificada: na EGIE3, a receita varia pouco (de R$ 12,3 bi em 2020 para R$ 12,9 bi em 2025, 1,0% ao ano) enquanto o fluxo cresce 20,5% ao ano, e o teto pela receita derruba o crescimento do fluxo para 1,0%.
- **A perpetuidade pesa muito no valor.** Depois do 5º ano, vale o crescimento do IPCA de 12 meses (4,22% em 04/10/2026), e a mediana do peso da perpetuidade é 57% do valor do FCD (de 42% a 72% entre as ações calculadas). A premissa de longo prazo importa mais do que a projeção explícita.
- **A perpetuidade cresce pelo IPCA de 12 meses**, um número de um momento só, que muda de mês a mês. Isso equivale a crescimento real zero. O app limita o crescimento a 1 ponto percentual abaixo do WACC, mas esse limite não foi acionado em nenhuma ação em 04/10/2026.
- **Tudo é nominal**: Selic nominal, fluxos em reais correntes e perpetuidade pelo IPCA.

### Taxa de desconto (WACC)

- **A taxa livre de risco é a Selic menos o spread de default do Brasil.** O custo do capital próprio é a Selic meta menos o spread de default (2,13%), mais Beta vezes o prêmio de risco do Brasil. O spread sai da Selic porque ela já embute o risco de default do país, e o prêmio de risco (que inclui o risco-país) o conta de novo. Com a Selic em 13,75% (04/10/2026), o WACC das ações com FCD vai de 11,3% a 24,2% (mediana de 16,5%). O custo da dívida continua sendo a Selic mais 2 pontos percentuais, o custo real de captação em reais. Quando os juros sobem, o FCD tende a cair para todas as ações.
  - *Hipótese:* que a Selic embuta o spread de 2,13% como um título longo do governo; a Selic é uma taxa de um dia, e a taxa de um título de 10 anos em reais não foi estudada.
  - *Na tela:* o bloco "Datas de referência dos dados usados" informa a data da Selic; a origem do dado está em "Dados e fontes", mais abaixo.
- **O prêmio de risco e o spread de default são fixos** (7,47% e 2,13%, da tabela do Damodaran de 05/01/2026, rating Ba1 do Brasil, lida em 04/10/2026). A tabela é atualizada uma vez por ano, em janeiro, e as constantes são conferidas à mão a cada atualização; entre elas, os valores ficam parados.
- **O Beta é frágil.** É calculado com os retornos diários de 1 ano contra o Ibovespa, sem ajuste e com no mínimo 2 observações. Em 04/10/2026, os valores vão de 0,18 a 1,97 (PETR4: 0,40).
  - *Efeito:* um Beta baixo reduz o custo do capital próprio e eleva o valor.
  - *Na tela:* o cartão do FCD mostra o Beta usado e se foi calculado ou padrão (1,0).
- **O benefício fiscal de 34% vale para todas as empresas**, inclusive as que têm prejuízo ou pagam menos imposto.
  - *Efeito:* custo da dívida subestimado nessas empresas, WACC menor e valor maior.
- **Os pesos usam valores contábeis, não de mercado:** dívida líquida sobre patrimônio líquido total. Quem negocia bem acima do valor contábil fica com peso de dívida exagerado, e a dívida é mais barata que o capital próprio.
  - *Efeito:* WACC menor e valor maior. Sem dívida líquida positiva, a empresa é tratada como sem dívida (100% capital próprio).
- **O arrendamento não entra nos pesos** (explicação completa em "Arrendamento", na seção do fluxo de caixa).

### Do valor da empresa ao valor por ação

- **A dívida líquida vem do Fundamentus.** Em 9 empresas conferidas com o balanço da CVM (02/10/2026), ela é a dívida bruta (empréstimos, financiamentos e debêntures) menos o caixa e as aplicações financeiras de curto prazo (duas contas do balanço). O passivo de arrendamento só entra nela quando a empresa o registra como financiamento (PETR4 e CSAN3); o tratamento nos demais casos está em "Arrendamento", na seção do fluxo de caixa. Aplicações que a empresa classifica em outras contas não são descontadas: na CSAN3, são R$ 5,5 bilhões em títulos e valores mobiliários.
  - *Efeito:* dívida líquida superestimada em casos como esse, e valor menor.
- **A participação dos não controladores** (a parte das controladas que pertence a sócios minoritários) é descontada pelo valor contábil do balanço consolidado, que costuma ficar abaixo do valor de mercado.
  - *Efeito:* o desconto pode ficar curto. Em empresas com muitos minoritários o efeito é grande: na GOAU4 (04/10/2026), os não controladores são R$ 34,6 bilhões, 64% do patrimônio total, e o FCD era de −R$ 24,84 por ação (valor combinado de −R$ 1,49), antes de o FCD ≤ 0 virar "não aplicável".
  - *Na tela:* quando as deduções passam o valor da empresa, o FCD fica "Não aplicável" (ver o item seguinte).
- **Empresas com deduções acima do valor da empresa ficam sem FCD.** Se a dívida líquida, o arrendamento e os minoritários somam mais que o valor da empresa pelo fluxo de caixa, o valor por ação sai zero ou negativo. Isso não quer dizer que a ação valha zero, e sim que o modelo consolidado não captura o valor dela (comum em holdings, empresas muito alavancadas e com muitos minoritários, como CSAN3, ENGI11 e GOAU4). Em 21/10/2026, 13 das 76 ações do `screener.csv` estavam nessa situação.
  - *Na tela:* o FCD é "Não aplicável", com o motivo (total das deduções e valor da empresa) na legenda do gráfico de valor justo; a coluna "Observação" do Screener mostra só "FCD não aplicável: dívidas superam o valor da empresa", sem os valores; nenhum valor negativo aparece. Se nenhum método se aplicar, o Valor combinado e o Potencial mostram "—" e o "?" traz o motivo de cada método.
  - *Efeito:* o valor combinado dessas ações passa a vir só de Graham e/ou Bazin, o que tende a ser mais otimista (no `screener.csv` de 21/10/2026, a GOAU4 foi de −110% para −15% de potencial e a RDOR3 de −35% para +4%).
  - *Melhoria futura:* avaliar holdings como Cosan, Itaúsa e Simpar pela soma das partes (SOTP).
- **Número de ações.** O FCD, o Graham e o valor de mercado usam as ações em circulação da CVM (capital integralizado menos tesouraria), na data-base do balanço. Quando a CVM não traz o número, ou ele é descartado por inconsistência, vale o do Fundamentus, e o cartão diz o motivo. O app corrige erros conhecidos de escala e de tesouraria na composição do capital, mas um erro novo nesses dados pode passar sem ser notado. Nas units, a composição da CVM conta ações físicas, mas a unit é medida pelo peso econômico das ações que a formam. O app converte a composição da CVM com uma tabela de composições: na IGTI11, 1 ordinária e 2 preferenciais que valem 3 vezes a ordinária, ou 7 ordinárias equivalentes; nas outras cinco units (KLBN11, TAEE11, ENGI11, SANB11 e BPAC11), as preferenciais valem o mesmo que as ordinárias. O valor por unit segue o fator do Fundamentus, e o número convertido da CVM (na IGTI11, 296,5 milhões) fica 0,09% abaixo do dele (296,7 milhões).
  - *Limitação:* a composição de SANB11 e BPAC11 vem de fontes secundárias, e o peso igual a 1 das preferenciais de SANB11, BPAC11, TAEE11 e ENGI11 é uma hipótese; as preferenciais do SANB11, por exemplo, recebem dividendo 10% maior. Se as preferenciais dessas units valessem 1,1 vez a ordinária, o Graham mudaria em até cerca de 3%.
  - *Na tela:* a página avisa quando o fator de unit do Fundamentus não bate com a tabela e quando uma unit não está na tabela.

### Valores extremos

Em 04/10/2026, entre as 53 ações com FCD, 1 tinha FCD acima de 3 vezes o preço (BEEF3), 13 tinham FCD negativo e 3 estavam abaixo de −1 vez o preço (ENGI11, GOAU4 e MRVE3); desde 21/10/2026 o FCD negativo é "não aplicável" e essas contagens são só um retrato daquele dia. Quase sempre isso reflete a sensibilidade do modelo às premissas acima, e não uma oportunidade ou um desastre.

- *Na tela:* o Screener marca com um aviso as ações cujo potencial passa de +200% ou fica abaixo de −100% (6 ações em 04/10/2026; com o FCD ≤ 0 não aplicável, o lado negativo não ocorre mais), e o texto do aviso depende dos métodos que entraram no valor combinado.
- *Na tela, no cartão do FCD:* um aviso mais forte aparece quando o FCD é a partir de 3 vezes o preço, ou positivo mas até 10% do preço (em 04/10/2026, contando também o FCD negativo, eram 17 das 53 ações: as 13 com FCD negativo, a BEEF3 e GGBR4, MULT3 e VALE3). O texto aponta a causa provável nas entradas do modelo: deduções (dívida líquida, arrendamento e não controladores) acima ou perto do valor da empresa, crescimento do fluxo no teto da faixa ou no piso (ou a 5 p.p. dele), perpetuidade com 70% ou mais do valor da empresa, WACC baixo (12% ou menos) e fluxo do ano a partir de 50% do valor de mercado. O aviso é só informativo: não altera o FCD nem o valor combinado.
  - *Limitação:* a causa é uma leitura das entradas, não uma verificação; o app não sabe, por exemplo, se o caixa do ano foi pontual, e o texto só diz que, se foi, o valor fica inflado.

## Dados e fontes

- **O Fundamentus não tem API oficial.** O app lê as páginas do site. LPA, VPA, ROE, margem, dívida líquida e número de ações vêm de lá. Se o site mudar, o app pode ficar sem esses dados.
  - *Na tela:* o erro aparece como aviso, e a rodada do Screener é protegida (ver abaixo).
- **Datas diferentes na mesma conta.** O fluxo de caixa é do exercício anual (31/12/2025), enquanto a dívida, os não controladores e o número de ações são do balanço trimestral mais recente (30/06/2026 para as 76 ações).
  - *Na tela:* o bloco "Datas de referência dos dados usados" mostra cada data.
- **Eventos depois da data-base.** Ofertas de ações, bonificações e cancelamentos feitos depois de 30/06/2026 só entram no balanço seguinte.
  - *Na tela:* quando o número de ações do Fundamentus não bate com o da CVM por mais de 2%, a página avisa. Em 04/10/2026, isso acontece com a EGIE3 (+24,0%, 1.416,38 milhões contra 1.142,30 milhões) e a ISAE4 (+6,7%).
- **Preços, dividendos e Beta vêm do Yahoo Finance**, que pode atrasar ou falhar. O preço usado é o do último fechamento disponível (02/10/2026 no Screener de 04/10/2026).
  - *Na tela:* sem preço válido, a página mostra "Preço atual indisponível" e não calcula o potencial.
- **Fechamento zero ou negativo é descartado como dado inválido, em todos os tickers.** A regra vale para ações, Ibovespa e petróleo. Um preço negativo de futuro, como o do WTI em abril de 2020, seria descartado, mas a correlação usa o Brent, que não fechou negativo.
  - *Efeito:* a linha some do histórico e dos gráficos; o Beta e a volatilidade são calculados com as linhas válidas.
- **Selic e IPCA seguem uma cadeia de fontes:**
  1. a API do Banco Central;
  2. o serviço SOAP do Banco Central;
  3. o IBGE (só para o IPCA);
  4. o último valor obtido com sucesso e guardado no computador do app, aceito por até 45 dias;
  5. o arquivo de referência que acompanha o Screener, aceito por até 90 dias.
  Em 04/10/2026, a API do Banco Central estava fora do ar, e a Selic de 13,75% e o IPCA de 4,2235% (referência 08/2026) vieram do serviço SOAP.
  - *Efeito:* com o valor guardado ou o de referência, a Selic pode estar desatualizada se o Copom mudou a meta nesse intervalo.
  - *Na tela:* quando o dado não vem da API do Banco Central, a página informa a fonte, e quando vem do valor guardado ou do arquivo de referência, mostra um aviso com a data. Se nenhuma fonte responde e não há valor aceitável, o FCD não é calculado.
- **A página "Analisar uma ação" só espera cerca de 1 minuto pelo catálogo de emissores da B3 para uma ação fora do universo do screener.** O catálogo completo (`data/raw/b3/catalogo_emissores.csv`, 36 páginas da API) não é versionado, e o disco do Cloud é apagado quando o app dorme. Para as ações do universo, a página lê o CNPJ e o segmento setorial do catálogo enxuto `data/processed/catalogo_emissores.csv` (ticker, CNPJ e segmento), que a rodada do screener grava e o workflow versiona junto com o `screener.csv`; a Comparação setorial lê o segmento da coluna `segmento_setorial` do `screener.csv`. Medido em 23/10/2026, a busca do CNPJ e do segmento da PETR4 levou 0,02 s com o arquivo e 64 s sem ele.
  - *O que continua:* uma ação que não esteja no arquivo (por exemplo, fora do Ibovespa, ou uma ação nova antes da próxima rodada) ainda cai na API do catálogo completo e espera cerca de 1 minuto no primeiro acesso depois de o app acordar.
  - *Na tela:* nesse caso, o spinner diz "Buscando o catálogo completo da B3 (pode levar cerca de 1 minuto)…".
  - *Defasagem:* o arquivo é regravado a cada rodada aceita, em dias úteis. Uma mudança de CNPJ ou de segmento aparece na rodada seguinte. Se o catálogo da rodada vier incompleto, o arquivo anterior é mantido e o resumo da rodada lista os tickers que faltaram.
  - *Arquivo antigo do screener:* um `screener.csv` sem a coluna `segmento_setorial` faz a Comparação setorial pedir uma nova rodada.

## Screener e Simulador de carteira

- **O Screener mostra dados salvos, não ao vivo.** No app publicado, o resultado só muda quando uma nova rodada é feita e publicada pelo workflow (o botão "Rodar screener agora" só aparece com o opt-in `AVALIADOR_B3_PERMITIR_RODAR_SCREENER`), então os preços podem estar defasados.
  - *Na tela:* a página mostra a data da última atualização.
- **Enquanto não há `rodada.json`, a data de atualização é aproximada.** A data do rodapé vem do `rodada.json`, gravado a cada rodada aceita. Esse arquivo só existe a partir da primeira rodada aceita depois de 25/10/2026; até lá, o app usa a data da última busca ao vivo da Selic e do IPCA (`data_busca` do `macro_referencia.json`), que só é regravada quando essas fontes respondem. Se todas falharem numa rodada aceita, o `screener.csv` é publicado com os preços novos e essa data fica atrás.
  - *Na tela:* o rodapé mostra "Screener atualizado em dd/mm/aaaa (aprox.)", e o "?" explica de onde vem a data. Depois da primeira rodada com `rodada.json`, o "(aprox.)" some.
- **A rodada é protegida por uma checagem.** Se a rodada vier sem linhas ou com linhas faltando, se o universo do Ibovespa tiver menos de 60 ações, se mais de 5 ações ficarem sem preço, se mais de 5 tiverem falha de fonte ou se algum valor não for finito, a rodada é rejeitada, o resultado anterior é mantido e o motivo é mostrado. Isso evita dados quebrados, mas deixa o Screener desatualizado em vez de errado, e até 5 ações com falha ainda passam.
- **Ações sem nenhum método aplicável** ficam sem valor justo: em 04/10/2026, CSNA3 e NATU3. Aparecem no Screener com o motivo, e o Simulador as marca como sem cenário.
- **O histórico da carteira é desempenho passado, com simplificações.** O gráfico mostra como o valor investido hoje teria evoluído em 1, 2 ou 5 anos, com as proporções de hoje e sem rebalancear. Os preços são os ajustados por dividendos e desdobramentos do Yahoo Finance, e o JCP pode não estar incluído em todos os casos. O IPCA é mensal, interpolado dentro do mês, e o CDI é o diário bruto, sem imposto. A ação com histórico mais curto que o período fica fora da linha da carteira, com aviso, e só as 7 maiores posições por peso têm linha própria (as demais entram só na linha "Carteira"). Não é previsão.
  - *Na tela:* o "?" do painel traz o aviso de que é desempenho passado, e a legenda lista as ações que ficaram de fora.
- **O Simulador mostra potencial, não previsão.** Cada cenário compara o valor justo com o preço: o pessimista é o menor valor entre os métodos aplicáveis, o base é o valor combinado e o otimista é o maior. Não há prazo, dividendos, custos nem impostos. O pessimista pode ser o preço teto do Bazin, que não é uma estimativa de valor. Um valor justo zero ou negativo conta como perda total (−100%), regra que hoje só vale para `screener.csv` anteriores a 21/10/2026, porque nenhum método grava valor ≤ 0; o preço usado é o da última rodada do Screener.
  - *Na tela:* o bloco "Como funciona este cálculo?" explica isso, e os cenários limitados a −100% são sinalizados.

## Publicação da rodada e falhas

Uma rodada aceita grava quatro arquivos de `data/processed/`, nesta ordem:

1. `macro_referencia.json` (a Selic e o IPCA), só se foram buscados ao vivo nesta rodada;
2. `catalogo_emissores.csv`, que só substitui o anterior se cobrir todas as ações da rodada;
3. `screener.csv`;
4. `rodada.json` (a data e a hora da rodada), por último.

Cada arquivo é gravado num temporário e trocado no fim, então um arquivo nunca fica pela metade. Uma falha numa etapa levanta exceção e interrompe as seguintes; os temporários são apagados. O que fica no disco:

| Falha em | Fica no disco |
|---|---|
| a rodada (antes de publicar) ou a checagem rejeita | nada é substituído (a rejeitada vai para `screener.rejeitado.csv`) |
| 1. referência macro | os quatro arquivos anteriores |
| 2. catálogo | referência nova; catálogo, CSV e `rodada.json` anteriores |
| 3. CSV | referência e catálogo novos; CSV e `rodada.json` anteriores |
| 4. `rodada.json` | referência, catálogo e CSV novos; `rodada.json` anterior (ou nenhum) |

Nenhuma falha deixa a data da rodada mais nova que os dados.

**Por que o repositório publicado continua coerente.** No workflow, `python -m avaliador_b3.rodar_screener` sai com 0 só se a rodada foi aceita e publicou os quatro arquivos; uma exceção sai com 2 e uma rejeição com 1. Com saída diferente de 0, o passo falha, o passo seguinte (o do commit) não roda e a execução termina em falha, sem commit. O estado parcial só existe no runner descartado (o artifact da execução pode guardar o `screener.csv` desse runner por 14 dias, mas não vai para o repositório) ou, numa execução local, no clone de quem usou o botão "Rodar screener agora" (opt-in). Nesse caso, a próxima rodada aceita regrava o CSV, o catálogo e o `rodada.json`, e a referência macro se a Selic e o IPCA vierem ao vivo.
