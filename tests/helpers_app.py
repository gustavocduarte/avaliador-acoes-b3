"""Auxiliares dos testes de interface compartilhados entre os arquivos de teste do app."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def abrir_pagina(at: AppTest, titulo: str, timeout: int = 60) -> AppTest:
    """Troca para a página de título `titulo` e roda o app.

    Usa atributos privados do `AppTest` porque o `switch_page` do Streamlit 1.63 só aceita
    página baseada em arquivo, e as páginas do app são funções.
    """
    if not hasattr(at, "_registered_pages") or not hasattr(at, "_page_hash"):
        raise AssertionError(
            "AppTest mudou: _registered_pages/_page_hash não existem nesta versão do "
            "Streamlit; ajuste abrir_pagina"
        )
    if not at._registered_pages:
        at.run(timeout=timeout)
    paginas = {info["page_name"]: hash_ for hash_, info in at._registered_pages.items()}
    if titulo not in paginas:
        raise AssertionError(
            f"Página {titulo!r} não existe; títulos disponíveis: {sorted(paginas)}"
        )
    at._page_hash = paginas[titulo]
    return at.run(timeout=timeout)


def paginas_do_menu(at: AppTest) -> list[tuple[str, str, str]]:
    """`(título, ícone, caminho de URL)` das páginas registradas na última rodada, na ordem do
    menu. Atributo privado, pelo mesmo motivo de `abrir_pagina`."""
    return [
        (info["page_name"], info["icon"], info["url_pathname"])
        for info in at._registered_pages.values()
    ]


def blocos_da_barra(at: AppTest) -> list[tuple[str, list]]:
    """`(key, filhos)` de cada bloco da barra lateral, na ordem. O `key` sai do id do bloco
    (`$$ID-<hash>-<key>`), que o `AppTest` não expõe de outra forma."""
    return [
        (bloco.proto.id.split("-", 2)[-1], list(bloco.children.values()))
        for bloco in at.sidebar.children.values()
        if bloco.type == "flex_container"
    ]


def adicionar_a_carteira(at: AppTest, ticker: str, quantidade: int, timeout: int = 60) -> AppTest:
    """Põe uma posição na carteira do Simulador pelos campos da barra lateral."""
    from avaliador_b3.config import (
        CHAVE_CARTEIRA_ACAO,
        CHAVE_CARTEIRA_QUANTIDADE,
        ROTULO_ADICIONAR_A_CARTEIRA,
    )

    at.sidebar.selectbox(key=CHAVE_CARTEIRA_ACAO).select(ticker)
    at.sidebar.number_input(key=CHAVE_CARTEIRA_QUANTIDADE).set_value(quantidade)
    at.run(timeout=timeout)  # o botão só habilita depois de a ação ser escolhida
    botao = next(b for b in at.sidebar.button if b.label == ROTULO_ADICIONAR_A_CARTEIRA)
    return botao.click().run(timeout=timeout)
