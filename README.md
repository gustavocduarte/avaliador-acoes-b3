# Avaliador de Ações da B3

Ferramenta de avaliação de valor justo para as ações do Ibovespa (bolsa
brasileira), com projeções apresentadas como cenários
(pessimista/base/otimista) — nunca como um número único.

**App publicado:** https://gustavocduarte-avaliador-acoes-b3.streamlit.app

**Aviso:** os valores são estimativas de modelos com premissas simplificadas, para estudo. Não é recomendação de investimento.

## O que o app faz

Para cada ação, calcula o valor justo por três métodos e um valor combinado:

- **Graham** — raiz quadrada de `22,5 × LPA × VPA`; só se aplica com LPA e VPA
  positivos.
- **Bazin** — preço teto para um dividend yield mínimo de 6% a.a., sobre os
  dividendos dos últimos 12 meses; só se aplica com histórico de dividendos
  relevante (5 anos).
- **FCD** (Fluxo de Caixa Descontado) — projeta o fluxo de caixa livre e
  desconta pelo WACC (ver a metodologia abaixo).
- **Combinado** — média simples só dos métodos que se aplicam àquela ação.

O dashboard (Streamlit) tem três abas:

- **Analisar uma ação** — valor justo pelos três métodos e o combinado contra o
  preço atual, saúde financeira (ROE, margem, dívida, valor de mercado e de
  firma), governança, comportamento da ação (volume, volatilidade, Beta),
  preço contra o Ibovespa, histórico de dividendos, **Comparação setorial** e
  correlação com fatores externos (petróleo, câmbio e risco geopolítico).
- **Screener (todas as ações)** — a mesma avaliação para todo o Ibovespa, com
  potencial, divergência entre métodos, avisos e a proporção do caixa
  operacional reinvestida. O resultado fica salvo em
  `data/processed/screener.csv` (versionado, para o app publicado ter dados
  desde o primeiro acesso) e é atualizado pelo botão "Rodar screener agora".
- **Simulador de carteira** — dado um valor investido por ação, mostra o
  potencial da carteira nos cenários pessimista (menor valor entre os métodos
  aplicáveis), base (valor combinado) e otimista (maior valor), a partir do
  resultado já salvo do screener. É potencial sem prazo: o valor justo é um
  valor de hoje, não uma previsão de retorno anual.

## Metodologia do FCD

- **Fluxo de caixa livre:** caixa das operações (6.01) menos o capex explícito (compras de
  imobilizado e intangível nas subcontas de 6.02, identificadas pela descrição), somando de
  volta os juros de empréstimos lançados em 6.01, líquidos do imposto (34%). Sem capex
  identificado, o FCD não é calculado.
- **Projeção:** 5 anos com crescimento pelo CAGR do fluxo entre o ano de referência e 5 anos
  antes, limitado entre −20% e +30% ao ano; perpetuidade (Gordon) crescendo pelo IPCA de 12
  meses, limitado a 1 p.p. abaixo do WACC. Sem histórico utilizável (base ausente ou não
  positiva), o crescimento cai para o IPCA, e a tela diz o motivo.
- **WACC:** custo do capital próprio pelo CAPM (Selic + Beta × prêmio de risco do Brasil de
  7,47%; Beta calculado contra o Ibovespa em 1 ano, ou 1,0 se não for calculável) e custo da
  dívida de (Selic + 2 p.p.) pós-imposto. Os pesos usam valores contábeis, não de mercado:
  dívida líquida sobre patrimônio líquido total (controladores e não controladores); sem dívida
  líquida positiva, a empresa é tratada como não alavancada.
- **Do valor da empresa ao valor por ação:** do valor presente (Enterprise
  Value) subtrai-se a dívida líquida, o arrendamento fora da dívida e a
  participação dos não controladores, e divide-se pelas ações em circulação
  (capital integralizado menos tesouraria, pela composição do capital da CVM).
  Os ajustes vêm do balanço consolidado da CVM na data-base do Fundamentus;
  componente indisponível fica de fora, e a tela avisa.
- **Não aplicável:** bancos, seguradoras e a Itaúsa (a dívida e os depósitos são a própria
  operação, ou a empresa vive de dividendos de participações); capex não identificado; fluxo
  de caixa livre do ano de referência zero ou negativo; empresa sem dados de fluxo de caixa na
  CVM; número de ações indisponível; WACC não positivo. Valor justo zero ou negativo é mostrado
  com aviso, não zerado.

A justificativa de cada constante está em `src/avaliador_b3/config.py`.

## Fontes de dados

| Fonte | Para quê |
|---|---|
| Yahoo Finance (`yfinance`) | preços, dividendos, Ibovespa (Beta), petróleo e câmbio |
| Fundamentus | indicadores (LPA, VPA, ROE, margem, dívida líquida) e número de ações |
| CVM (dados abertos) | fluxo de caixa (DFP/ITR), balanço consolidado e composição do capital |
| B3 | universo do Ibovespa, catálogo de emissores (CNPJ e segmento setorial) |
| Banco Central (SGS) | Selic meta (série 432), IPCA mensal (433) e câmbio (série 1) |
| IBGE (SIDRA) | IPCA mensal, terceira fonte do IPCA |
| GPR (Caldara e Iacoviello) | índice de risco geopolítico |

A Selic e o IPCA seguem uma cadeia de fontes: API REST do Banco Central,
serviço SOAP do Banco Central, IBGE (só o IPCA), o último valor obtido com
sucesso (guardado em disco, válido por 45 dias) e, por fim, o arquivo de
referência `data/processed/macro_referencia.json`, gravado a cada rodada
aceita do screener e versionado junto com o `screener.csv` (válido por 90 dias).
Quando o dado não vem da API REST do Banco Central, a página informa a fonte
efetiva, e quando vem do valor guardado ou do arquivo de referência, mostra um
aviso com a data.

## Instalação e execução

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

Para desenvolver (inclui pytest, ruff e mypy):

```bash
pip install -r requirements-dev.txt
```

Rodar o dashboard, a partir da raiz do repositório:

```bash
streamlit run src/avaliador_b3/app/main.py
```

Rodar os testes e as verificações de código:

```bash
pytest
ruff check .
ruff format --check src tests
python -m mypy
```

Os testes não acessam a rede e não gravam em `data/`.

## Documentação técnica

A pasta `docs/` guarda a especificação e os relatórios técnicos do projeto:

- `especificacao.md` — especificação original do projeto.
- Auditorias e vistorias: `auditoria-2026-09-18.md`,
  `vistoria-pre-publicacao-2026-09-20.md`, `bateria-testes-2026-09-21.md`,
  `auditoria-tecnica-2026-09-27.md`, `vistoria-2026-09-28.md` e
  `vistoria-2026-09-28-b.md`.
- Correções: `correcoes-2026-09-22.md`, `correcao-fcd-2026-09-23.md`,
  `correcao-ano-fcd-2026-09-23.md` e `correcao-cnpj-2026-09-25.md`.
- Investigações: `investigacao-p03-p04-2026-10-02.md` (valor por ação do FCD,
  não controladores, número de ações e as decisões que resultaram nele).

## Sobre o uso de IA no desenvolvimento

Desenvolvido com o Claude Code como ferramenta de implementação, com revisão crítica de cada
etapa numa sessão separada do Claude e auditorias registradas em `docs/`. As decisões de escopo
e de metodologia (o que construir, o que descartar, como tratar cada limitação do modelo) e a
aprovação de cada mudança antes do commit foram minhas. Exemplo de algo descartado: um monitor
de risco geopolítico via GDELT, removido depois de mostrar falsos positivos recorrentes que os
filtros não resolviam.
