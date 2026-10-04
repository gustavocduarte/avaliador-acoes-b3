# Regras do projeto

- Responder sempre em português do Brasil.
- Antes de começar qualquer tarefa, rodar `git pull`: o GitHub Actions commita o `screener.csv` e o `macro_referencia.json` automaticamente.
- Antes de corrigir algo apontado em relatório (vistoria, auditoria), confirmar no código que o problema existe.
- Rodar `pytest`, `ruff` e `python -m mypy` e informar a contagem de testes pela diferença real desde o último commit, não por estimativa, junto com o resultado do mypy.
- Mostrar o diff e esperar aprovação antes de commitar.
- Um commit por assunto. Nunca usar `--amend`.
- Mensagens de commit em português com acentuação correta, sem nenhum trailer de atribuição (nada de `Co-Authored-By`).
- Comentários curtos, sem histórico de correção nem referência a vistorias ou relatórios.
- Constantes (prazos, limites, timeouts, URLs) ficam em `src/avaliador_b3/config.py`.
- Nos testes de interface, selecionar botões pelo texto (label), nunca pela posição.
- Testes não gravam em `data/` nem acessam a rede.
- Arquivos temporários, scripts de investigação e testes descartáveis ficam em `%TEMP%`, nunca dentro do repositório.
- Nunca usar `git stash` com trabalho não commitado; para comparar com o `HEAD` (ex.: contar testes), usar um `git worktree` temporário em `%TEMP%`.
