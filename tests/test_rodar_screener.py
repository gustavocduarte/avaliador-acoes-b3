import warnings
from pathlib import Path

import pandas as pd
import pytest

from avaliador_b3 import rodar_screener, screener
from avaliador_b3.ingest import bcb_sgs
from avaliador_b3.ingest.precos import FalhaFontePreco

MACRO = bcb_sgs.ResultadoMacro(
    selic_meta=0.1375,
    ipca_12m=0.0422,
    data_ipca=pd.Timestamp("2026-08-01"),
    usou_valor_guardado=False,
    data_busca=pd.Timestamp("2026-10-04 12:00"),
    fonte_selic="BCB (API)",
    fonte_ipca="BCB (API)",
)


def _resultado(falhas=None, macro=MACRO):
    tabela = pd.DataFrame(
        {
            "ticker": ["AAAA4", "BBBB4", "CCCC4"],
            "preco_atual": [10.0, 20.0, float("nan")],
            "fcd_valor_justo": [12.0, float("nan"), float("nan")],
        }
    )
    tabela.attrs["falhas_de_fonte"] = falhas or {}
    if macro is not None:
        tabela.attrs["macro"] = macro
    return tabela


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def historico(ticker, **kwargs):
        if ticker == "BBBB4":
            raise FalhaFontePreco("sem cache")
        return pd.DataFrame({"data": pd.to_datetime(["2026-10-01", "2026-10-02"]), "Close": [1, 2]})

    monkeypatch.setattr(rodar_screener, "obter_historico", historico)


def test_rodada_aceita_sai_com_zero_e_resume(monkeypatch, capsys):
    monkeypatch.setattr(screener, "rodar_screener", lambda: _resultado())

    codigo = rodar_screener.main([])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "Rodada: ACEITA" in saida
    assert "Ações na rodada: 3 | com FCD: 1" in saida
    assert "Falhas de fonte: nenhuma" in saida
    assert "Selic meta: 13,75% (fonte: BCB (API))" in saida
    assert "IPCA 12m: 4,22% (fonte: BCB (API), referência 2026-08-01)" in saida
    assert "Data dos preços: 2026-10-02" in saida


def test_resumo_mostra_as_falhas_por_fonte(monkeypatch, capsys):
    falhas = {"AAAA4": ["Yahoo"], "BBBB4": ["Fundamentus", "Yahoo"]}
    monkeypatch.setattr(screener, "rodar_screener", lambda: _resultado(falhas))

    rodar_screener.main([])

    assert (
        "Falhas de fonte: Fundamentus: 1, Yahoo: 2 (ações: AAAA4, BBBB4)" in capsys.readouterr().out
    )


def test_resumo_avisa_quando_a_selic_e_o_ipca_vieram_de_valor_guardado(monkeypatch, capsys):
    guardado = bcb_sgs.ResultadoMacro(
        selic_meta=0.10,
        ipca_12m=0.04,
        data_ipca=pd.Timestamp("2026-08-01"),
        usou_valor_guardado=True,
        data_busca=pd.Timestamp("2026-10-04"),
        fonte_selic="valor guardado de 29/09/2026",
        fonte_ipca="valor guardado de 29/09/2026",
    )
    monkeypatch.setattr(screener, "rodar_screener", lambda: _resultado(macro=guardado))

    rodar_screener.main([])

    saida = capsys.readouterr().out
    assert "fonte: valor guardado de 29/09/2026" in saida
    assert "Atenção: Selic e IPCA vieram de valor guardado" in saida


def test_rodada_rejeitada_sai_com_codigo_diferente_de_zero_e_traz_o_motivo(monkeypatch, capsys):
    def rejeita():
        raise screener.RodadaScreenerRejeitada(
            "8 ações sem preço (limite: 5).", Path("screener.rejeitado.csv"), _resultado()
        )

    monkeypatch.setattr(screener, "rodar_screener", rejeita)

    codigo = rodar_screener.main([])

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "Rodada: REJEITADA" in saida
    assert "Motivo: 8 ações sem preço (limite: 5)." in saida
    assert "screener.rejeitado.csv" in saida
    assert "Ações na rodada: 3 | com FCD: 1" in saida


def test_excecao_na_rodada_sai_com_codigo_diferente_de_zero_e_diz_o_erro(monkeypatch, capsys):
    def quebra():
        raise RuntimeError("zip da CVM corrompido")

    monkeypatch.setattr(screener, "rodar_screener", quebra)

    codigo = rodar_screener.main([])

    captura = capsys.readouterr()
    assert codigo == 2
    assert "Rodada: FALHOU POR EXCEÇÃO" in captura.out
    assert "Motivo: RuntimeError: zip da CVM corrompido" in captura.out
    assert "RuntimeError" in captura.err  # a pilha vai para o erro padrão


def test_resumo_vai_tambem_para_o_arquivo_pedido(monkeypatch, tmp_path):
    monkeypatch.setattr(screener, "rodar_screener", lambda: _resultado())
    destino = tmp_path / "resumo.txt"

    rodar_screener.main(["--resumo", str(destino)])

    texto = destino.read_text(encoding="utf-8")
    assert texto.startswith("Rodada: ACEITA")
    assert "Data dos preços: 2026-10-02" in texto


def test_avisos_da_rodada_entram_no_resumo(monkeypatch, capsys):
    def com_aviso():
        warnings.warn(
            "Fundamentus indisponível: 5 ações seguidas falharam.",
            screener.FundamentusIndisponivelWarning,
        )
        return _resultado()

    monkeypatch.setattr(screener, "rodar_screener", com_aviso)

    with pytest.warns(screener.FundamentusIndisponivelWarning):
        rodar_screener.main([])

    assert "Aviso: Fundamentus indisponível: 5 ações seguidas falharam." in capsys.readouterr().out
