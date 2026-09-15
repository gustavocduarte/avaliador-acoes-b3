"""Testes do dashboard Streamlit (app/main.py) via `streamlit.testing.v1.AppTest`
— roda o script de verdade (mesmo runner que `streamlit run` usa por baixo),
sem precisar de navegador. Cobre especificamente a degradação graciosa do
dropdown de ticker na aba "Analisar uma ação": ver a investigação e o teste
manual no navegador (URL de `obter_universo_ibovespa` apontada pra um domínio
inválido de propósito, revertida depois) que motivou este teste.

Só o carregamento inicial da aba é testado aqui (sem clicar em "Buscar") —
nesse ponto, `obter_universo_ibovespa` é a única fonte externa chamada sem
depender de nenhuma ação do usuário, o que mantém o teste rápido e
determinístico (sem rede de verdade, só o adapter mockado).
"""

from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

# Caminho absoluto: AppTest.from_file resolve caminho relativo contra o
# arquivo que CHAMA from_file (este arquivo de teste), não contra o cwd do
# pytest — relativo a "tests/" ficaria errado.
CAMINHO_APP = str(Path(__file__).resolve().parents[1] / "src/avaliador_b3/app/main.py")


@pytest.fixture(autouse=True)
def _limpar_cache_streamlit():
    """`st.cache_data` guarda o resultado numa memória global do processo,
    não por execução do AppTest — sem limpar entre testes, o segundo teste
    leria o resultado (bom ou com falha) já cacheado pelo primeiro, em vez
    de chamar `obter_universo_ibovespa` (mockado de novo) de verdade."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _universo_falso() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["PETR4", "VALE3"],
            "nome": ["PETROBRAS", "VALE S.A."],
            "segmento_listagem": ["Nível 2", "Novo Mercado"],
            "tipo_bruto": ["PN N2", "ON NM"],
        }
    )


def test_dropdown_lista_acoes_do_ibovespa_quando_universo_disponivel(monkeypatch):
    monkeypatch.setattr(
        "avaliador_b3.ingest.b3_universo.obter_universo_ibovespa",
        lambda **kwargs: _universo_falso(),
    )

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert len(at.selectbox) == 1
    assert at.selectbox[0].label == "Ação (Ibovespa)"
    assert any("PETR4" in opcao and "PETROBRAS" in opcao for opcao in at.selectbox[0].options)
    assert not any("indispon" in aviso.value.lower() for aviso in at.warning)


def test_cai_pro_campo_de_texto_livre_quando_universo_falha(monkeypatch):
    # Reproduz o cenário confirmado manualmente no navegador (API da B3 fora
    # do ar): a aba não pode travar, tem que degradar pro texto livre com um
    # aviso claro nomeando o motivo.
    def falha(**kwargs):
        raise RuntimeError("falha simulada de rede")

    monkeypatch.setattr("avaliador_b3.ingest.b3_universo.obter_universo_ibovespa", falha)

    at = AppTest.from_file(CAMINHO_APP)
    at.run(timeout=60)

    assert not at.exception
    assert len(at.selectbox) == 0

    rotulos_texto = [ti.label for ti in at.text_input]
    assert "Ticker (ex: PETR4)" in rotulos_texto

    avisos = [aviso.value for aviso in at.warning]
    assert any(
        "indisponível" in aviso and "falha simulada de rede" in aviso for aviso in avisos
    )
