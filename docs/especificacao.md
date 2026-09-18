# Especificação — Avaliador de Ações da B3

> Documento de referência do projeto. Escrito antes de qualquer código de
> implementação. Deve ser consultado (e atualizado, se decisões mudarem) ao
> longo de todo o desenvolvimento.

## Objetivo central

Calcular o valor justo de ações da B3 com projeções de futuro, apresentado
sempre como cenários (pessimista / base / otimista, ou uma média) — **nunca**
como um número seco.

## Escopo

Somente B3 (ações brasileiras). Somente as ações principais da bolsa —
excluir fundos imobiliários (FIIs) e small caps.

## Núcleo: modelo de valor justo

Calcular com **três métodos lado a lado**, mais um valor combinado.

### 1. Fluxo de Caixa Descontado (FCD)

Projeta fluxo de caixa livre futuro, traz a valor presente via WACC.
Praticamente sempre aplicável.

### 2. Fórmula de Benjamin Graham

Raiz quadrada de `22,5 × LPA × VPA`. **Só aplicável se LPA > 0 e VPA > 0**
(a fórmula quebra matematicamente com negativo).

### 3. Método Bazin (Preço Teto)

Preço máximo para um dividend yield mínimo de 6% a.a., baseado no histórico
de dividendos. **Só aplicável se a empresa tiver histórico de dividendo
relevante.**

### Valor combinado

Média **apenas dos métodos aplicáveis** àquela empresa específica — não uma
média fixa dos 3 sempre. Essa decisão precisa ser feita **programaticamente
por ação**, nunca hardcoded.

## Contexto macro (fonte: Banco Central do Brasil, API SGS)

Bloco de "condições monetárias" tratado de forma coordenada (não como
variáveis independentes soltas, para evitar multicolinearidade):

- Selic (o "preço" do dinheiro)
- Crescimento de M2 (a "quantidade" de dinheiro)

Além disso, separadamente:

- IPCA — para corrigir o retorno nominal e chegar no retorno real
- Câmbio (USD/BRL) — relevante para empresas exportadoras/importadoras

## Fatores setoriais: guerra, petróleo e metais

- **Geopolitical Risk Index (GPR)**, Caldara & Iacoviello, Federal Reserve —
  índice histórico mensal/diário, baixável em matteoiacoviello.com/gpr.htm —
  alimenta o risco/desconto de ações sensíveis a conflito geopolítico.
- **Preço de petróleo e metais** como variável de ajuste para as ações
  desses setores.

## Três blocos de variáveis por empresa

1. **Saúde financeira**: Dívida Líquida/EBITDA, Liquidez Corrente, ROE,
   margem líquida, crescimento de receita/lucro. Dado vindo dos relatórios
   de Relações com Investidores (RI) de cada empresa.
2. **Governança**: segmento de listagem da B3 (Novo Mercado, Nível 2, Nível
   1, Tradicional) + free float (% de ações em circulação).
3. **Comportamento da ação**: volatilidade, beta (vs. Ibovespa), volume
   médio negociado — cruzado com o bloco de saúde financeira, para sinalizar
   quando o preço sobe sem sustentação em resultado real (lucro/ROE não
   acompanhando a alta do preço).

## Visualizações

- Gráfico de preço da ação com atualização periódica (delay de ~15 min é
  aceitável — dado em tempo real de bolsa é pago, isso já foi discutido e
  aceito).
- Sobreposição com o Ibovespa no mesmo gráfico (reaproveita o histórico que
  o Beta já precisa).
- Histórico de dividendos pagos, em gráfico de barras por ano (reaproveita o
  dado que o método Bazin já precisa).
- Tabela comparando a ação com as concorrentes do mesmo setor (reaproveita
  os valores justos já calculados para cada ação).

## Funcionalidades extras

- **Screener/ranking**: rodar o modelo combinado para todas as ações
  principais da B3 de uma vez, ordenado por "quanto abaixo do valor justo
  está o preço atual".
- **Simulador de carteira**: usuário distribui um valor entre ações
  escolhidas, e o simulador projeta o total da carteira nos mesmos 3
  cenários calculados por ação.
- **Painel de correlação**: medir estatisticamente (não assumir) a
  correlação histórica entre cada ação e petróleo/câmbio/GPR.

## Explicitamente fora do escopo por agora

**Backtest do modelo** (comparar valor justo calculado no passado vs. preço
real que veio depois) — ideia boa, mas exige dado fundamentalista histórico
que pode ser difícil de achar de graça. Investigar viabilidade depois, não
prometer agora.

## Restrições técnicas e de processo (aprendidas no projeto anterior)

- Meu computador tem pouca RAM — ao desenhar o pipeline (principalmente o
  screener, que roda para todas as ações de uma vez), pensar em
  processamento incremental em vez de carregar tudo na memória de uma vez.
- **NUNCA** incluir "Co-Authored-By: Claude" ou "Claude-Session" nas
  mensagens de commit — isso causou um problema sério de vazamento de link
  de sessão no projeto anterior e não deve se repetir. A transparência sobre
  uso de IA no desenvolvimento vai no README, como texto normal, não como
  metadado do commit.
- Seguir o mesmo rigor do projeto de covid: toda constante/código mágico
  usado (tipo os critérios de aplicabilidade do Graham/Bazin) deve ser
  validado contra uma fonte real antes de assumir que está correto. Rodar
  `pytest` e `ruff` antes de cada commit.
- Se este projeto for publicado no Streamlit Community Cloud no futuro,
  usar Python 3.12 ou mais recente no `requirements.txt` desde o início
  (numpy recente exige isso — isso já causou retrabalho de deploy no
  projeto anterior).

## Fontes de dados validadas (pesquisa inicial)

Pesquisa feita antes de qualquer código de implementação, para confirmar o
que é viável de graça. Cada adapter em `src/avaliador_b3/ingest/` deve
citar a fonte real usada, conforme a restrição de rigor acima.

| Peça do projeto | Fonte escolhida | Observações |
|---|---|---|
| Preço de ação B3 | `yfinance` (ticker `XXXX.SA`) | Gratuito, sem chave, cobre o universo todo. Wrapper não-oficial do Yahoo Finance — pode falhar/rate-limitar; exige cache local + retry. |
| Preço de ação (fonte secundária/cross-check) | brapi.dev | Free tier é limitado: sem token só 4 tickers (PETR4, MGLU3, VALE3, ITUB4) funcionam irrestritos; com token grátis, 15k req/mês mas **sem dividendos e sem fundamentos**, histórico só 3 meses. Não serve como fonte única do screener. |
| Fundamentos por empresa (indicadores prontos) | fundamentus.com.br (scraping) | Sem API oficial, mas scraping é prática madura (vários projetos Python consolidados). |
| Fundamentos por empresa (fonte primária/auditoria) | CVM Dados Abertos — `dados.cvm.gov.br` (datasets ITR/DFP) | Fonte oficial, CSV, sem cadastro. Formato de plano de contas padronizado, mais trabalhoso de parsear — usar para validar os números vindos do scraping. |
| Lista de "ações principais" | Carteira teórica do Ibovespa (~76-79 ativos, revisada quadrimestral) | Exclui FIIs/small caps por construção. Endpoint não-documentado da B3 (`indexProxy/indexCall/GetPortfolioDay`) ou download manual do CSV na página do índice. |
| Segmento de listagem (Novo Mercado/N1/N2/Tradicional) | **Em aberto** | Não há um CSV único e limpo confirmado nesta pesquisa. Candidatos: página de classificação setorial da B3, API não-documentada `listedCompaniesProxy/CompanyCall/GetInitialCompanies`, ou scraping por ação em sites como StatusInvest. Investigar a fundo ao implementar `src/avaliador_b3/ingest/b3_universo.py`. |
| Selic, M2, IPCA, Câmbio | BCB API SGS — `api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados` | Oficial e estável. Códigos confirmados: Selic diária = `11`, Meta Selic = `432`, IPCA mensal = `433`, Câmbio USD (venda, PTAX) = `1`, M2 (saldo fim de período) = `27810`. |
| GPR (risco geopolítico) | matteoiacoviello.com/gpr.htm | Download direto (Excel/CSV), gratuito, sem cadastro, atualizado mensalmente. |

## Primeiro passo (este documento antecede)

Antes de escrever qualquer código de implementação: pesquisar e validar
quais fontes de dado gratuitas realmente existem e funcionam para cada peça
acima (preço de ação B3, dado fundamentalista de empresa, lista oficial de
ações principais/segmentos de listagem da B3, séries do Banco Central,
GPR). Depois de validar o que é viável de graça, propor a estrutura de
pastas do projeto (no mesmo espírito do projeto de covid: `data/`, `src/`,
`tests/`, `docs/`) antes de começar a escrever qualquer função.
