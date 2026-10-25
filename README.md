# Avaliador de Ações da B3

Dashboard em Python que estima o valor justo das ações do Ibovespa por Graham, Bazin e fluxo de caixa descontado, com os dados atualizados todo dia útil por um workflow do GitHub Actions.

[![CI](https://github.com/gustavocduarte/avaliador-acoes-b3/actions/workflows/ci.yml/badge.svg)](https://github.com/gustavocduarte/avaliador-acoes-b3/actions/workflows/ci.yml)
[![Atualiza o screener](https://github.com/gustavocduarte/avaliador-acoes-b3/actions/workflows/atualiza-screener.yml/badge.svg)](https://github.com/gustavocduarte/avaliador-acoes-b3/actions/workflows/atualiza-screener.yml)

**App publicado:** https://gustavocduarte-avaliador-acoes-b3.streamlit.app

**Aviso:** os valores são estimativas de modelos com premissas simplificadas, para estudo. Não é recomendação de investimento. As limitações dos modelos e dos dados estão em [`docs/limitacoes-conhecidas.md`](docs/limitacoes-conhecidas.md).

## Arquitetura

```mermaid
flowchart LR
    subgraph fontes["Fontes de dados"]
        direction TB
        YF["Yahoo Finance"]
        FU["Fundamentus"]
        CV["CVM (dados abertos)"]
        B3["B3"]
        BC["Banco Central e IBGE"]
        GP["GPR"]
    end

    subgraph gha["GitHub Actions (seg a sex, 19:17 de Brasília)"]
        direction LR
        ING["Ingestão<br/>cache por validade e por schema,<br/>cadeia de fontes com fallback"]
        CALC["Cálculo<br/>Graham, Bazin, FCD<br/>e valor combinado"]
        CHK{"Checagem<br/>da rodada"}
        ING --> CALC --> CHK
    end

    CSV[("screener.csv e<br/>catalogo_emissores.csv<br/>versionados")]
    APP["App Streamlit<br/>Community Cloud"]
    REJ["Rodada rejeitada:<br/>mantém o CSV anterior<br/>e a execução falha"]

    fontes --> ING
    CHK -- aceita --> CSV
    CHK -- rejeitada --> REJ
    CSV --> APP
    fontes -. "página de uma ação (ao vivo)" .-> APP
```

## Destaques técnicos

- **Cadeia de fontes com fallback:** a Selic e o IPCA passam pela API do Banco Central, pelo serviço SOAP, pelo IBGE (só o IPCA), pelo último valor guardado e pelo arquivo de referência versionado; a tela informa a fonte efetiva. O ano da demonstração da CVM é detectado por empresa, e a empresa que ainda não entregou o ano mais recente usa o anterior.
- **Checagem que impede publicar rodada ruim:** a rodada só substitui o `screener.csv` se tiver ao menos uma linha, uma linha por ação, no máximo 5 ações sem preço, no máximo 5 com falha de fonte, nenhum valor não finito (`NaN` ou infinito) e, quando o universo vem do Ibovespa, ao menos 60 ações; senão vira `screener.rejeitado.csv`, o resultado anterior fica e a execução do workflow falha.
- **Gravação atômica:** o screener, os caches em disco e os zips da CVM são gravados num arquivo temporário de nome único por escritor e trocados no fim, então uma falha no meio, ou duas gravações simultâneas, nunca corrompem o arquivo anterior. O screener é publicado na ordem referência macro (`macro_referencia.json`), catálogo, CSV e, por último, a data da rodada (`rodada.json`): se a publicação falhar no meio, o CSV anterior fica intacto e a data nunca fica mais nova que os dados.
- **Cache versionado por schema:** cada cache em disco leva a versão do formato, e uma mudança de formato invalida os arquivos antigos; os zips da CVM expiram em 7 dias (ano em preenchimento) ou 30 dias (anos fechados), e os resultados derivados deles (fluxo de caixa, lucro e balanço) são refeitos quando o zip de origem muda ou vence.
- **Abertura mais rápida:** a primeira abertura da página de análise caiu de cerca de 86 s para cerca de 24 s ao trocar a busca do catálogo completo da B3 (36 páginas da API) por um catálogo enxuto gravado pelo pipeline (`data/processed/catalogo_emissores.csv`, versionado, com CNPJ e segmento de cada ação do screener). **Medido localmente**, com a PETR4 e o cache vazio: só a busca do CNPJ e do segmento foi de 64 s para 0,02 s. Uma ação fora do universo do screener ainda espera cerca de 1 minuto, e o spinner avisa.
- **Testes sem rede:** mais de 1.700 testes, com **98% de cobertura** (linhas e ramos), sem acessar a rede nem gravar em `data/`; inclui testes de interface com o `AppTest` do Streamlit.
- **Tipagem e CI:** `mypy` e `ruff` em todo o código, e um workflow que roda testes, lint, formatação e tipos a cada push e pull request.
- **Decisões registradas:** cada mudança de metodologia passa por uma investigação só de leitura, com relatório que separa o confirmado nos dados da hipótese, e as decisões ficam em [`docs/decisoes-de-metodologia.md`](docs/decisoes-de-metodologia.md).

## Tecnologias

- **Aplicação:** Python 3.12 ou mais recente (o CI roda na 3.14), Streamlit, pandas, NumPy, Plotly, `yfinance`, `requests`, Beautiful Soup e `xlrd`.
- **Qualidade:** pytest com pytest-cov, ruff e mypy.
- **Entrega:** GitHub Actions (CI e atualização agendada) e Streamlit Community Cloud (o app publicado).

## O que o app faz

O escopo é só o das ações do Ibovespa (as principais da B3): fundos imobiliários e small caps ficam de fora. Para cada ação, calcula o valor justo por três métodos e um valor combinado:

- **Graham** — raiz quadrada de `22,5 × LPA × VPA`; só se aplica com LPA e VPA
  positivos.
- **Bazin** — preço teto para um dividend yield mínimo de 6% a.a., sobre os
  dividendos dos últimos 12 meses; só se aplica com histórico de dividendos
  relevante (5 anos).
- **FCD** (Fluxo de Caixa Descontado) — projeta o fluxo de caixa livre e
  desconta pelo WACC (ver a metodologia abaixo).
- **Combinado** — média simples só dos métodos que se aplicam àquela ação.

O dashboard tem três páginas, escolhidas no menu da barra lateral. Cada página põe os seus
controles na própria barra lateral (a ação e o botão Buscar, os filtros do Screener ou a montagem
da carteira), e o rodapé mostra a data da última atualização do screener e o link do repositório.

- **Analisar uma ação** — valor justo pelos três métodos e o combinado contra o
  preço atual, saúde financeira (ROE, margem, dívida, valor de mercado e de
  firma), governança, comportamento da ação (volume, volatilidade, Beta),
  preço contra o Ibovespa, histórico de dividendos, **Comparação setorial** (as ações
  do mesmo segmento, pelo `screener.csv`) e correlação com fatores externos (petróleo,
  câmbio e risco geopolítico). A página também abre direto numa ação por `?acao=TICKER`, o
  link que o ticker do Screener usa.

  ![Analisar uma ação: PETR4 com preço atual, valor combinado, potencial e valor justo por Graham, Bazin e FCD](docs/img/analise-acao-1.png)

  <details><summary>Mais capturas</summary>

  ![Dividendos por ano e comparação setorial da PETR4](docs/img/analise-acao-2.png)

  *Dividendos por ano e comparação setorial da PETR4.*

  ![ABEV3: valor justo por método abaixo do preço atual](docs/img/analise-acao-3.png)

  *Outra ação (ABEV3), com potencial negativo: o valor justo de cada método fica abaixo do preço.*

  </details>

- **Screener** — a mesma avaliação para todo o Ibovespa. A barra lateral tem os filtros (setor,
  potencial mínimo, exigir método e esconder as ações sem valor combinado), e a página traz
  cartões de resumo, a distribuição do potencial, os cartões "Atenção" (potencial extremo e ações
  sem nenhum método) e o "Ranking por potencial", com divergência entre métodos, dividendos contra
  o histórico, proporção do caixa operacional reinvestida e uma coluna "Observação". Clicar no
  ticker abre a análise da ação. O resultado fica salvo em
  `data/processed/screener.csv` (versionado, para o app publicado ter dados
  desde o primeiro acesso) e é atualizado pelo workflow agendado. O arquivo traz o segmento
  setorial de cada ação (coluna `segmento_setorial`), que a página lê sem buscar o catálogo da B3.
  O botão "Rodar screener agora" só aparece com o opt-in explícito
  (`AVALIADOR_B3_PERMITIR_RODAR_SCREENER`), descrito em "Instalação, execução e testes".

  ![Screener com os filtros padrão: cartões de resumo, distribuição do potencial e avisos](docs/img/screener-1.png)

  <details><summary>Mais capturas</summary>

  ![Screener filtrado por setor (Aluguel de carros)](docs/img/screener-2.png)

  *Filtro por setor (Aluguel de carros): o histograma e o ranking mostram só as ações do setor.*

  ![Ranking por potencial com Graham, Bazin e FCD marcados](docs/img/screener-3.png)

  *Ranking por potencial com os três métodos marcados em "Só ações em que se aplicam": só aparecem as ações em que os três se aplicam.*

  </details>

- **Simulador de carteira** — a carteira é montada na barra lateral, com a **quantidade** de cada
  ação, a partir do resultado já salvo do screener. A página mostra o valor investido, o valor
  justo, o potencial e a concentração; os cenários pessimista (menor valor entre os métodos
  aplicáveis), base (valor combinado) e otimista (maior valor); a contribuição de cada ação; a
  composição por ação e por setor; a tabela de posições; e o **histórico de 1, 2 ou 5 anos** da
  carteira (com as proporções de hoje, sem rebalancear) contra o IPCA e o CDI. Os cenários são
  potencial sem prazo: o valor justo é um valor de hoje, não uma previsão de retorno anual. O
  histórico é desempenho passado, com preços ajustados por dividendos e desdobramentos, e
  também não é previsão.

  ![Simulador de carteira com três posições: valor investido, cenários, contribuição e composição por ação e por setor](docs/img/simulador-2.png)

  <details><summary>Mais capturas</summary>

  ![Simulador com duas posições](docs/img/simulador-1.png)

  *Carteira com duas posições (ABEV3 e BBAS3), com a concentração em bancos em destaque.*

  ![Posições e histórico da carteira contra IPCA e CDI](docs/img/simulador-3.png)

  *Posições e histórico da carteira contra IPCA e CDI.*

  </details>

Funciona também em tela estreita:

<img src="docs/img/celular.png" alt="Análise da PETR4 em tela de celular" width="400">

## Metodologia do FCD

- **Fluxo de caixa livre:** caixa das operações (6.01) menos o capex explícito (compras de
  imobilizado e intangível nas subcontas de 6.02, identificadas pela descrição), somando de
  volta os juros de empréstimos lançados em 6.01, líquidos do imposto (34%). Sem capex
  identificado, o FCD não é calculado. A saída líquida de linhas de 6.03 descritas como
  convênio com fornecedores, risco sacado, forfait ou cessão de crédito por fornecedores é
  tratada como operacional e reduz o caixa das operações, no ano de referência e no ano-base;
  entradas não são ajustadas, e a tela diz o valor reclassificado. A coluna Reinvestimento e a
  legenda "reinvestiu X%" usam esse mesmo caixa das operações (com os juros somados de volta).
- **Projeção:** 5 anos com crescimento pelo CAGR do fluxo entre o ano de referência e 5 anos
  antes, limitado por cima pelo CAGR da receita líquida (DRE, conta 3.01) no mesmo período e
  mantido entre −20% e +30% ao ano; sem receita utilizável, vale o do fluxo, e a tela diz o
  motivo. O crescimento do ano 1 converge linearmente para o da perpetuidade no ano 5, sem salto.
  A perpetuidade (Gordon) cresce pelo IPCA de 12 meses, limitado a 1 p.p. abaixo do WACC. Sem
  histórico utilizável (base ausente ou não positiva), o crescimento cai para o IPCA, e a tela
  diz o motivo.
- **WACC:** custo do capital próprio pelo CAPM ((Selic − spread de default do Brasil de 2,13%)
  + Beta × prêmio de risco do Brasil de 7,47%, da tabela do Damodaran de janeiro de 2026; Beta
  calculado contra o Ibovespa em 1 ano, ou 1,0 se não for calculável) e custo da dívida de
  (Selic + 2 p.p.) pós-imposto. Os pesos usam valores contábeis, não de mercado:
  dívida líquida sobre patrimônio líquido total (controladores e não controladores); sem dívida
  líquida positiva, a empresa é tratada como não alavancada.
- **Do valor da empresa ao valor por ação:** do valor presente (Enterprise
  Value) subtrai-se a dívida líquida, o arrendamento fora da dívida e a
  participação dos não controladores, e divide-se pelas ações em circulação
  (capital integralizado menos tesouraria, pela composição do capital da CVM).
  Os ajustes vêm do balanço consolidado da CVM na data-base do Fundamentus;
  componente indisponível fica de fora, e a tela avisa. Nas units, a composição
  da CVM é convertida pelo peso econômico das ações que formam a unit (tabela de
  composições em `config.py`), e o fator de unit do Fundamentus segue como a fonte
  do valor por unit; a tela avisa quando ele não bate com a tabela.
- **Não aplicável:** bancos, seguradoras e a Itaúsa (a dívida e os depósitos são a própria
  operação, ou a empresa vive de dividendos de participações); capex não identificado; fluxo
  de caixa livre do ano de referência zero ou negativo; empresa sem dados de fluxo de caixa na
  CVM; número de ações indisponível; WACC não positivo; valor por ação zero ou negativo (as
  deduções passam o valor da empresa). Nesses casos o FCD fica não aplicável, com o motivo na tela e no
  Screener, o valor combinado usa só os métodos positivos e nenhum valor negativo aparece.
- **Aviso de valor extremo:** quando o FCD é a partir de 3 vezes o preço ou positivo mas até
  10% do preço, o cartão do FCD mostra a causa provável nas entradas do modelo
  (deduções perto do valor da empresa, crescimento no teto ou no piso da faixa, perpetuidade
  pesada, WACC baixo). É só informativo: não altera o valor.

A justificativa de cada constante está em `src/avaliador_b3/config.py`.

## Fontes de dados

| Fonte | Para quê |
|---|---|
| Yahoo Finance (`yfinance`) | preços, dividendos, Ibovespa (Beta), petróleo e câmbio, e o histórico ajustado da carteira |
| Fundamentus | indicadores (LPA, VPA, ROE, margem, dívida líquida) e número de ações |
| CVM (dados abertos) | fluxo de caixa (DFP/ITR), balanço consolidado e composição do capital |
| B3 | universo do Ibovespa e catálogo de emissores (CNPJ e segmento setorial), do qual o app lê o catálogo enxuto versionado |
| Banco Central (SGS) | Selic meta (série 432), IPCA mensal (433), câmbio (série 1) e CDI diário (série 12) |
| IBGE (SIDRA) | IPCA mensal, terceira fonte do IPCA |
| GPR (Caldara e Iacoviello) | índice de risco geopolítico |

A página de análise lê o CNPJ e o segmento de `data/processed/catalogo_emissores.csv`, regravado a
cada rodada aceita do screener; só a ação que não está nele espera cerca de 1 minuto pelo
catálogo completo da B3.

A Selic e o IPCA seguem uma cadeia de fontes: API REST do Banco Central,
serviço SOAP do Banco Central, IBGE (só o IPCA), o último valor obtido com
sucesso (guardado em disco, válido por 45 dias) e, por fim, o arquivo de
referência `data/processed/macro_referencia.json`, gravado a cada rodada
aceita do screener e versionado junto com o `screener.csv` (válido por 90 dias).
Quando o dado não vem da API REST do Banco Central, a página informa a fonte
efetiva, e quando vem do valor guardado ou do arquivo de referência, mostra um
aviso com a data.

## Instalação, execução e testes

Requer **Python 3.12 ou mais recente**.

```bash
python -m venv .venv

# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

Para só rodar o app (é o que o Streamlit Community Cloud instala):

```bash
pip install -r requirements.txt
```

Para desenvolver (inclui pytest, pytest-cov, ruff e mypy; o `-e .` instala o pacote em modo
editável, o que permite rodar `python -m avaliador_b3.rodar_screener` de qualquer pasta):

```bash
pip install -r requirements-dev.txt -e .
```

Rodar o dashboard, a partir da raiz do repositório:

```bash
streamlit run src/avaliador_b3/app/main.py
```

O botão "Rodar screener agora" (página Screener) **não aparece por padrão**: no app publicado,
qualquer visitante poderia disparar uma rodada de ~228 requisições, então o screener só é
atualizado pelo workflow. Para habilitá-lo na sua máquina, ligue a variável de ambiente
`AVALIADOR_B3_PERMITIR_RODAR_SCREENER` (valores aceitos: `1`, `true`, `yes`, `sim` ou `on`)
antes de iniciar o app:

```powershell
# Windows (PowerShell), na sessão em que vai rodar o app:
$env:AVALIADOR_B3_PERMITIR_RODAR_SCREENER = "1"
streamlit run src/avaliador_b3/app/main.py
```

```bash
# Linux/macOS:
AVALIADOR_B3_PERMITIR_RODAR_SCREENER=1 streamlit run src/avaliador_b3/app/main.py
```

Alternativa, sem repetir a variável a cada sessão: crie o arquivo `.streamlit/secrets.toml`
(já ignorado pelo Git) com a mesma chave.

```toml
AVALIADOR_B3_PERMITIR_RODAR_SCREENER = true
```

Sem o opt-in, a página mostra que o workflow atualiza o screener nos dias úteis, com a data da
última atualização.

Rodar os testes e as verificações de código (as mesmas do CI):

```bash
pytest
ruff check .
ruff format --check src tests
python -m mypy
```

Relatório de cobertura (hoje, 98%):

```bash
pytest --cov --cov-report=term-missing:skip-covered
```

Os testes não acessam a rede e não gravam em `data/`.

## Atualização do screener

O `data/processed/screener.csv` é atualizado por um workflow do GitHub Actions, o "Atualiza o screener" (`.github/workflows/atualiza-screener.yml`). Ele roda **de segunda a sexta às 19:17 de Brasília** (22:17 UTC, depois do fechamento da B3; o GitHub pode atrasar a execução em alguns minutos) e também pode ser **disparado manualmente**. A cada execução faz a rodada completa e publica o resultado como arquivo da execução (artifact).

- **Quando commita:** só quando a rodada é aceita e algum dos quatro arquivos mudou. Como o `rodada.json` leva o horário da rodada, toda rodada aceita muda pelo menos ele e é commitada, mesmo num feriado: o commit registra que o pipeline rodou. Aí grava o `screener.csv`, o `catalogo_emissores.csv` (catálogo enxuto de emissores: ticker, CNPJ e segmento, que a página de análise lê no lugar do catálogo de 36 páginas da B3), o `macro_referencia.json` e o `rodada.json` no `master`, com autor `github-actions[bot]` e mensagem "Atualiza o screener (rodada de AAAA-MM-DD)", com a data de Brasília; o corpo do commit traz o resumo da rodada. O catálogo só substitui o anterior se cobrir todas as ações da rodada; se vier incompleto, o anterior é mantido (sem anterior, grava o que houver) e o resumo lista os tickers que faltaram.
- **Quando falha:** se a rodada é rejeitada pela checagem ou termina com exceção, a execução fica em **falha** (vermelha na aba Actions; o GitHub avisa por e-mail conforme as notificações de quem mantém o agendamento) e nada é commitado, então o screener anterior continua valendo. Os arquivos da rodada, inclusive o `screener.rejeitado.csv`, continuam disponíveis como artifact.
- **Sincronizar:** como o workflow commita no `master`, convém rodar `git pull` antes de começar a trabalhar.
- **Agendamento parado:** em repositório público, o GitHub desliga os agendamentos depois de 60 dias sem atividade no repositório; para reativar, use a aba Actions.
- **Onde ver as execuções:** na aba **Actions** do repositório (<https://github.com/gustavocduarte/avaliador-acoes-b3/actions>), workflow "Atualiza o screener". Cada execução mostra o resumo da rodada (aceita ou rejeitada, falhas de fonte, fonte da Selic e do IPCA, data dos preços, se houve commit) e, no fim da página, o artifact `screener-<número>` para baixar. Os commits do workflow aparecem no histórico do `master` com o autor `github-actions[bot]`.
- **Rodar manualmente:** Actions, "Atualiza o screener", "Run workflow". Uma execução manual no `master` também commita, nas mesmas condições.
- **Pela linha de comando**, a partir da raiz do repositório e com o pacote instalado (`pip install -e .`); é o mesmo procedimento do botão "Rodar screener agora" (que só existe com o opt-in acima) e grava o `data/processed/screener.csv`:

  ```bash
  python -m avaliador_b3.rodar_screener
  ```

  Sai com 0 quando a rodada é aceita, 1 quando a checagem a rejeita e 2 quando uma exceção a interrompe.

### As datas que o app mostra

Cada data tem um significado próprio, e elas podem ser diferentes (por exemplo, a Selic pode ser de uma busca anterior à rodada):

| Data | Onde aparece | De onde vem |
|---|---|---|
| **Rodada** (dia e hora, no fuso de Brasília) | Rodapé "Screener atualizado em", aviso do workflow no Screener e legenda da Comparação setorial | `data/processed/rodada.json`, gravado quando uma rodada é aceita. Sem esse arquivo, o app usa a data da busca de Selic e IPCA |
| **Preços** | "Datas de referência dos dados usados" (último fechamento) e preço de cada ação no screener | Último fechamento do Yahoo Finance no momento da rodada (ou da busca ao vivo, na página de análise) |
| **Balanço** | "Datas de referência dos dados usados" ("balanço de dd/mm/aaaa") e coluna `data_balanco_fundamentus` do screener | Último balanço processado que o Fundamentus informa; vale para LPA, VPA, ROE, margem e dívida |
| **Selic e IPCA** | "Datas de referência dos dados usados" e avisos de valor guardado | Data da busca no Banco Central (`data_busca` do `macro_referencia.json`); o IPCA mostra também o mês de referência. Quando a busca falha e o valor vem do guardado ou do arquivo de referência, é a data dessa busca antiga, não a da rodada |

## Documentação técnica

A pasta `docs/` tem três documentos. O processo é sempre o mesmo: um achado (de uma auditoria, vistoria ou revisão) aponta um problema, o problema é confirmado no código antes de qualquer correção, a correção sai com teste e o resultado é registrado. Quando a questão é de metodologia, uma investigação só de leitura compara as alternativas, separando o confirmado nos dados da hipótese, e a decisão é registrada antes de implementar.

- [`limitacoes-conhecidas.md`](docs/limitacoes-conhecidas.md): as limitações dos modelos e dos dados, para quem usa o app.
- [`decisoes-de-metodologia.md`](docs/decisoes-de-metodologia.md): o problema, as alternativas, a decisão, o porquê e os commits de cada mudança no modelo (valor do acionista e bancos, fluxo de caixa, número de ações, crescimento, prêmio de risco, risco sacado, empresas cíclicas), mais o que ficou decidido e ainda não foi implementado.
- [`historico-de-revisoes.md`](docs/historico-de-revisoes.md): as auditorias, vistorias, baterias de testes, correções e revisões de código de 18/09 a 06/10/2026, mais o registro do redesenho e do catálogo enxuto de 20 a 23/10/2026, com a gravidade dos achados, como foram resolvidos e os commits.

Os relatórios originais foram consolidados nesses dois últimos documentos e continuam no histórico do Git; cada um traz o comando para recuperá-los.

## Próximos passos

O que ficou para depois:

- **Normalização das cíclicas.** Decidida (critério, método e janela estão em `docs/decisoes-de-metodologia.md`), mas aguardando a série histórica de 2010 a 2025 por empresa. Hoje é uma limitação documentada.
- **Banco de dados (Supabase)** para o histórico das rodadas do screener e para a série histórica que a normalização das cíclicas precisa. Hoje o resultado é só o `screener.csv` mais recente.
- **Divisão do `app/main.py` em módulos.** É o maior arquivo do projeto.
- **Pesos do WACC a valor de mercado**, junto com o passivo de arrendamento nos pesos (hoje os pesos são contábeis).
- **Backtest do modelo** (comparar o valor justo calculado no passado com o preço que veio depois) está fora do escopo: exige dado fundamentalista histórico, que é difícil de obter de graça.

## Sobre o uso de IA no desenvolvimento

Desenvolvido com o Claude Code como ferramenta de implementação, com revisão crítica de cada
etapa numa sessão separada do Claude e auditorias registradas em `docs/historico-de-revisoes.md`. As decisões de escopo
e de metodologia (o que construir, o que descartar, como tratar cada limitação do modelo) e a
aprovação de cada mudança antes do commit foram minhas. Exemplo de algo descartado: um monitor
de risco geopolítico via GDELT, removido depois de mostrar falsos positivos recorrentes que os
filtros não resolviam.

## Licença

Distribuído sob a licença MIT. Veja o arquivo [`LICENSE`](LICENSE).
