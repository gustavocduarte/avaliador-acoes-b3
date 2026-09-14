import pytest

from avaliador_b3.modelos.combinado import calcular_valor_combinado


def _graham(aplicavel=True, valor_justo=100.0):
    return {
        "aplicavel": aplicavel,
        "valor_justo": valor_justo if aplicavel else None,
        "motivo_nao_aplicavel": None if aplicavel else "LPA/VPA não positivo.",
    }


def _bazin(aplicavel=True, preco_teto=60.0):
    return {
        "aplicavel": aplicavel,
        "preco_teto": preco_teto if aplicavel else None,
        "motivo_nao_aplicavel": None if aplicavel else "Sem histórico de dividendo relevante.",
    }


def _fcd(aplicavel=True, valor_justo=90.0):
    return {
        "aplicavel": aplicavel,
        "valor_justo": valor_justo if aplicavel else None,
        "motivo_nao_aplicavel": None if aplicavel else "Sem número de ações.",
        "wacc": 0.15,
        "taxa_crescimento_explicita": 0.05,
        "taxa_crescimento_perpetuidade": 0.04,
    }


def test_tres_aplicaveis_media_dos_tres():
    resultado = calcular_valor_combinado(
        _graham(valor_justo=100.0), _bazin(preco_teto=60.0), _fcd(valor_justo=90.0)
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_combinado"] == pytest.approx((100.0 + 60.0 + 90.0) / 3)
    assert sorted(resultado["metodos_utilizados"]) == ["bazin", "fcd", "graham"]
    assert resultado["valores_por_metodo"] == {"graham": 100.0, "bazin": 60.0, "fcd": 90.0}
    assert resultado["motivo_nao_aplicavel"] is None


def test_um_inaplicavel_media_dos_dois_restantes():
    resultado = calcular_valor_combinado(
        _graham(valor_justo=100.0), _bazin(aplicavel=False), _fcd(valor_justo=90.0)
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_combinado"] == pytest.approx((100.0 + 90.0) / 2)
    assert sorted(resultado["metodos_utilizados"]) == ["fcd", "graham"]
    assert resultado["valores_por_metodo"] == {"graham": 100.0, "fcd": 90.0}


def test_dois_inaplicaveis_vira_o_valor_do_unico_restante():
    # Caso mais comum na prática: só o FCD (quase sempre aplicável) sobra.
    resultado = calcular_valor_combinado(
        _graham(aplicavel=False), _bazin(aplicavel=False), _fcd(valor_justo=90.0)
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_combinado"] == pytest.approx(90.0)
    assert resultado["metodos_utilizados"] == ["fcd"]
    assert resultado["valores_por_metodo"] == {"fcd": 90.0}


def test_nenhum_aplicavel_devolve_explicitamente_sem_valor():
    resultado = calcular_valor_combinado(
        _graham(aplicavel=False), _bazin(aplicavel=False), _fcd(aplicavel=False)
    )

    assert resultado["aplicavel"] is False
    assert resultado["valor_combinado"] is None
    assert resultado["metodos_utilizados"] == []
    assert resultado["valores_por_metodo"] == {}
    assert resultado["motivo_nao_aplicavel"] is not None


def test_nao_confunde_a_chave_de_valor_entre_metodos():
    # Bazin usa "preco_teto", não "valor_justo" — garante que o combinador
    # lê a chave certa de cada um, não um valor por acidente/coincidência.
    resultado = calcular_valor_combinado(
        _graham(aplicavel=False), _bazin(preco_teto=42.0), _fcd(aplicavel=False)
    )

    assert resultado["valor_combinado"] == pytest.approx(42.0)
    assert resultado["valores_por_metodo"] == {"bazin": 42.0}


def test_soma_valor_negativo_normalmente_sem_filtro_de_sinal():
    # Um método aplicável pode dar valor negativo (ex: FCD de empresa com
    # projeção de fluxo de caixa ruim — ver test_fcd.py). A média precisa
    # somar isso normalmente, sem nenhum filtro acidental tipo "só conta
    # se for positivo".
    resultado = calcular_valor_combinado(
        _graham(valor_justo=100.0), _bazin(aplicavel=False), _fcd(valor_justo=-20.0)
    )

    assert resultado["aplicavel"] is True
    assert resultado["valor_combinado"] == pytest.approx((100.0 + -20.0) / 2)
    assert sorted(resultado["metodos_utilizados"]) == ["fcd", "graham"]
    assert resultado["valores_por_metodo"] == {"graham": 100.0, "fcd": -20.0}
