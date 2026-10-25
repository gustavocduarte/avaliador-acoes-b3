"""O app chama os adaptadores e os caminhos que os testes substituem pelo módulo de origem
(`precos.obter_historico(...)`), nunca por um nome importado (`from ...precos import
obter_historico`): o nome importado fica preso ao valor que existia quando o módulo foi
importado pela primeira vez, e um patch posterior nem chegaria ao código do app (ou o fake de um
teste vazaria para os seguintes)."""

import ast
from pathlib import Path

RAIZ = Path(__file__).parent.parent
TESTES = RAIZ / "tests"
APP = RAIZ / "src" / "avaliador_b3" / "app"


def _modulos_importados_pelo_teste(arvore: ast.Module) -> dict[str, str]:
    """Apelido usado no teste -> módulo completo (`cvm` -> `avaliador_b3.ingest.cvm`)."""
    apelidos = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module and no.module.startswith("avaliador_b3"):
            for nome in no.names:
                apelidos[nome.asname or nome.name] = f"{no.module}.{nome.name}"
    return apelidos


def _alvos_de_patch() -> set[tuple[str, str]]:
    """`(módulo, nome)` de cada atributo de módulo do projeto que algum teste substitui."""
    alvos = set()
    for arquivo in sorted(TESTES.glob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        apelidos = _modulos_importados_pelo_teste(arvore)
        for no in ast.walk(arvore):
            if not (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "setattr"
                and no.args
            ):
                continue
            primeiro = no.args[0]
            if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
                modulo, _, nome = primeiro.value.rpartition(".")
                if modulo.startswith("avaliador_b3"):
                    alvos.add((modulo, nome))
            elif (
                isinstance(primeiro, ast.Name)
                and primeiro.id in apelidos
                and len(no.args) > 1
                and isinstance(no.args[1], ast.Constant)
                and isinstance(no.args[1].value, str)
            ):
                alvos.add((apelidos[primeiro.id], no.args[1].value))
    return alvos


def test_o_guarda_enxerga_os_patches_conhecidos():
    alvos = _alvos_de_patch()

    assert ("avaliador_b3.ingest.precos", "obter_historico") in alvos
    assert ("avaliador_b3.screener", "CAMINHO_SAIDA_PADRAO") in alvos
    assert ("avaliador_b3.config", "CAMINHO_CATALOGO_EMISSORES") in alvos


def test_nenhum_modulo_do_app_importa_pelo_nome_o_que_os_testes_substituem():
    alvos = _alvos_de_patch()
    importados_por_nome = []
    for arquivo in sorted(APP.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                for nome in no.names:
                    if (no.module, nome.name) in alvos:
                        importados_por_nome.append(
                            f"{arquivo.relative_to(RAIZ)}: from {no.module} import {nome.name}"
                        )

    assert importados_por_nome == []
