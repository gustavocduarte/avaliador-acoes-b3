# Avaliador de Ações da B3

Ferramenta de avaliação de valor justo para ações principais da B3 (bolsa
brasileira), com projeções apresentadas sempre como cenários
(pessimista/base/otimista) — nunca como um número único.

Combina três métodos de valuation (Fluxo de Caixa Descontado, Fórmula de
Graham, Método Bazin), contexto macroeconômico (Banco Central), risco
geopolítico (GPR), e indicadores de saúde financeira, governança e
comportamento da ação por empresa.

Ver `docs/especificacao.md` para a especificação completa do projeto.

## Status

Funcional. O projeto tem hoje:

- 7 adapters de dados em `src/avaliador_b3/ingest/` (universo/segmento da
  B3, séries do Banco Central, crosswalk ticker↔CNPJ, CVM, Fundamentus,
  GPR, preços via yfinance);
- 4 modelos de valuation em `src/avaliador_b3/modelos/` (Graham, Bazin,
  Fluxo de Caixa Descontado e o combinador dos três);
- um dashboard Streamlit com 3 abas (Analisar uma ação, Screener, Simulador
  de carteira) e um painel de correlação com fatores externos (petróleo,
  câmbio, risco geopolítico);
- tema visual próprio (dark navy/dourado, ver `.streamlit/config.toml`);
- 316 testes automatizados cobrindo adapters, modelos e o dashboard.

## Instalação e execução

Requer **Python 3.12 ou mais recente** (`target-version` em
`pyproject.toml`).

```bash
python -m venv .venv

# Linux/macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Rodar o dashboard (o comando abaixo assume que você está na raiz do
repositório, já que usa um caminho relativo):

```bash
streamlit run src/avaliador_b3/app/main.py
```

Rodar a suíte de testes (útil pra quem for avaliar o código, não só rodar
o app):

```bash
pytest
```

## Sobre o uso de IA no desenvolvimento

Desenvolvido com Claude Code como ferramenta de pareamento — mas toda
decisão de escopo e arquitetura foi minha: o que construir, o que descartar
(ex.: um monitor de risco geopolítico via GDELT, removido depois de mostrar
falsos positivos recorrentes que os filtros não resolviam), e a aprovação de
cada mudança antes do commit, sempre com a suíte de testes passando. Duas
auditorias de código dedicadas foram feitas ao longo do desenvolvimento — os
relatórios estão em `docs/auditoria-2026-09-18.md` e
`docs/vistoria-pre-publicacao-2026-09-20.md`.
