from pathlib import Path

RAIZ = Path(__file__).parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "atualiza-screener.yml"
ARQUIVOS = ("screener.csv", "catalogo_emissores.csv", "macro_referencia.json", "rodada.json")


def _passo_de_commit() -> str:
    texto = WORKFLOW.read_text(encoding="utf-8")
    inicio = texto.index("- name: Commita o screener atualizado")
    return texto[inicio : texto.index("- name:", inicio + 1)]


def test_o_commit_automatico_inclui_o_catalogo_enxuto_no_git_add():
    linha = next(
        linha for linha in _passo_de_commit().splitlines() if linha.strip().startswith("git add")
    )

    for arquivo in ARQUIVOS:
        assert f"data/processed/{arquivo}" in linha


def test_a_checagem_de_mudanca_enxerga_o_catalogo_mesmo_sendo_arquivo_novo():
    passo = _passo_de_commit()

    # `git diff` ignora arquivo ainda fora do git; `git status --porcelain` não.
    assert "git diff --quiet" not in passo
    checagem = next(linha for linha in passo.splitlines() if "git status --porcelain" in linha)
    assert "data/processed/screener.csv" in checagem
    assert "data/processed/catalogo_emissores.csv" in checagem


def test_a_checagem_de_mudanca_olha_os_mesmos_arquivos_do_git_add():
    passo = _passo_de_commit()

    checagem = next(linha for linha in passo.splitlines() if "git status --porcelain" in linha)
    for arquivo in ARQUIVOS:
        assert f"data/processed/{arquivo}" in checagem


def test_a_data_da_mensagem_do_commit_e_a_de_brasilia():
    passo = _passo_de_commit()

    assert "TZ=America/Sao_Paulo date +%Y-%m-%d" in passo
    assert "date -u" not in passo


def test_o_gitignore_libera_os_arquivos_que_o_commit_automatico_adiciona():
    # `data/processed/*` é ignorado; sem a exceção, o `git add` do workflow recusa o arquivo.
    linhas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "data/processed/*" in linhas
    for arquivo in ARQUIVOS:
        assert f"!data/processed/{arquivo}" in linhas
