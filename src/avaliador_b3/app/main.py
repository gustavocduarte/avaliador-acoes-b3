"""Dashboard (Streamlit) do Avaliador de Ações da B3 — valor justo das ações do
Ibovespa por Graham, Bazin e fluxo de caixa descontado, com o valor combinado
e o simulador de carteira em três cenários (pessimista/base/otimista). Só chama
os adapters/modelos que já existem e organiza o resultado na tela; nenhuma lógica
de cálculo é reimplementada aqui.

Rodar com: streamlit run src/avaliador_b3/app/main.py
"""

import sys
from html import escape
from pathlib import Path

# O projeto não está instalado como pacote (sem pyproject [project]/pip
# install -e . ainda) — `streamlit run` não adiciona src/ ao sys.path
# sozinho como o pytest faz via pythonpath, então isso resolve na mão.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from avaliador_b3.app import barra_lateral
from avaliador_b3.app.css import (
    _CSS_DA_PAGINA,
)
from avaliador_b3.app.paginas.analise import (
    pagina_analisar,
)
from avaliador_b3.app.paginas.carteira import (
    pagina_carteira,
)
from avaliador_b3.app.paginas.screener import (
    pagina_screener,
)
from avaliador_b3.config import (
    CHAVE_BARRA_ANALISAR,
    CHAVE_BARRA_CARTEIRA,
    CHAVE_BARRA_SCREENER,
    DESCRICOES_DAS_PAGINAS,
    ICONE_PAGINA_ANALISAR,
    ICONE_PAGINA_CARTEIRA,
    ICONE_PAGINA_SCREENER,
    TEXTO_AVISO_ESTIMATIVAS,
    TEXTO_RODAPE_APP_DORMINDO,
    TITULO_ABA_NAVEGADOR,
    TITULO_PAGINA_ANALISAR,
    TITULO_PAGINA_CARTEIRA,
    TITULO_PAGINA_SCREENER,
    URL_PAGINA_ANALISAR,
    URL_PAGINA_CARTEIRA,
    URL_PAGINA_SCREENER,
)

_paginas = {
    CHAVE_BARRA_ANALISAR: st.Page(
        pagina_analisar,
        title=TITULO_PAGINA_ANALISAR,
        icon=ICONE_PAGINA_ANALISAR,
        url_path=URL_PAGINA_ANALISAR,
        default=True,
    ),
    CHAVE_BARRA_SCREENER: st.Page(
        pagina_screener,
        title=TITULO_PAGINA_SCREENER,
        icon=ICONE_PAGINA_SCREENER,
        url_path=URL_PAGINA_SCREENER,
    ),
    CHAVE_BARRA_CARTEIRA: st.Page(
        pagina_carteira,
        title=TITULO_PAGINA_CARTEIRA,
        icon=ICONE_PAGINA_CARTEIRA,
        url_path=URL_PAGINA_CARTEIRA,
    ),
}
# Menu próprio (um bloco por página), no lugar do menu padrão do Streamlit.
pagina_atual = st.navigation(list(_paginas.values()), position="hidden")
# Fora de uma execução do Streamlit (importação nos testes) a página não tem título.
_titulo_da_pagina_atual = getattr(pagina_atual, "title", TITULO_PAGINA_ANALISAR)
# O título da aba é o da página aberta, por isso a configuração vem depois do menu.
st.set_page_config(
    page_title=TITULO_ABA_NAVEGADOR.format(pagina=_titulo_da_pagina_atual),
    page_icon="📈",
    layout="wide",
)
# Único bloco de CSS da página (ver `_CSS_DA_PAGINA`).
st.html(_CSS_DA_PAGINA)
barra_lateral.montar_barra_lateral(_paginas, pagina_atual)
# Cabeçalho: o título é o da página aberta; abaixo, o que ela faz e o aviso de estimativas.
st.html(f'<div class="ab-app-titulo">{escape(_titulo_da_pagina_atual)}</div>')
st.caption(f"{DESCRICOES_DAS_PAGINAS[_titulo_da_pagina_atual]}  \n{TEXTO_AVISO_ESTIMATIVAS}")
st.html('<div class="ab-app-divisoria"></div>')
pagina_atual.run()
barra_lateral._rodape_da_barra_lateral()

# Nota de rodapé, fora de qualquer página (aparece nas três) — Streamlit
# Community Cloud "adormece" apps sem acesso recente. Diferente do que se
# poderia supor, não é uma tela em branco automática: a plataforma mostra
# sua própria página de "app dormindo", com um botão que o visitante
# precisa clicar pra acordar o container (confirmado contra a documentação
# oficial, 2026-09-21) — só depois disso começa a espera de carregamento.
# Sem esse aviso, o clique extra pareceria um link quebrado.
st.caption(TEXTO_RODAPE_APP_DORMINDO)
