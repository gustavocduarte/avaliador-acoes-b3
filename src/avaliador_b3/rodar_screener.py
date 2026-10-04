"""Roda o screener pela linha de comando, pelo mesmo procedimento do botão
"Rodar screener agora" (`screener.rodar_screener`): `python -m avaliador_b3.rodar_screener`.

Saída 0 quando a rodada é aceita; 1 quando a checagem a rejeita (o `screener.csv` anterior
fica como estava); 2 quando uma exceção interrompe a rodada. O resumo vai para a saída padrão
e, com `--resumo`, também para um arquivo."""

import argparse
import sys
import traceback
import warnings
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from avaliador_b3 import screener
from avaliador_b3.config import (
    CODIGO_SAIDA_RODADA_ACEITA,
    CODIGO_SAIDA_RODADA_COM_EXCECAO,
    CODIGO_SAIDA_RODADA_REJEITADA,
    PERIODO_HISTORICO_COMPORTAMENTO,
    RESUMO_ACOES,
    RESUMO_ARQUIVO_REJEITADO,
    RESUMO_AVISO,
    RESUMO_DATA_PRECOS,
    RESUMO_DATA_PRECOS_INDISPONIVEL,
    RESUMO_FALHAS,
    RESUMO_MACRO,
    RESUMO_MACRO_GUARDADO,
    RESUMO_MACRO_INDISPONIVEL,
    RESUMO_MOTIVO,
    RESUMO_RODADA_ACEITA,
    RESUMO_RODADA_EXCECAO,
    RESUMO_RODADA_REJEITADA,
    RESUMO_SEM_FALHAS,
    TTL_CACHE_RESUMO_RODADA_SEGUNDOS,
)
from avaliador_b3.ingest.precos import FalhaFontePreco, TickerInvalido, obter_historico


def _pct(valor: float) -> str:
    return f"{valor * 100:.2f}%".replace(".", ",")


def _data_dos_precos(resultado: pd.DataFrame) -> str | None:
    """Data do último preço lido na rodada (a mais recente entre as ações com preço), pelo
    cache de preços; sem rede."""
    datas = []
    for ticker in resultado.loc[resultado["preco_atual"].notna(), "ticker"]:
        try:
            historico = obter_historico(
                ticker,
                periodo=PERIODO_HISTORICO_COMPORTAMENTO,
                ttl_segundos=TTL_CACHE_RESUMO_RODADA_SEGUNDOS,
            )
            datas.append(pd.Timestamp(historico["data"].iloc[-1]))
        except (TickerInvalido, FalhaFontePreco, KeyError, IndexError):
            continue
    return f"{max(datas):%Y-%m-%d}" if datas else None


def _linhas_do_resultado(resultado: pd.DataFrame | None) -> list[str]:
    if resultado is None:
        return []
    linhas = [
        RESUMO_ACOES.format(
            total=len(resultado), com_fcd=int(resultado["fcd_valor_justo"].notna().sum())
        )
    ]
    falhas = resultado.attrs.get("falhas_de_fonte") or {}
    if falhas:
        por_fonte = Counter(fonte for fontes in falhas.values() for fonte in fontes)
        linhas.append(
            RESUMO_FALHAS.format(
                por_fonte=", ".join(f"{fonte}: {n}" for fonte, n in sorted(por_fonte.items())),
                acoes=", ".join(sorted(falhas)),
            )
        )
    else:
        linhas.append(RESUMO_SEM_FALHAS)
    macro = resultado.attrs.get("macro")
    if macro is None:
        linhas.append(RESUMO_MACRO_INDISPONIVEL)
    else:
        linhas.append(
            RESUMO_MACRO.format(
                selic=_pct(macro.selic_meta),
                fonte_selic=macro.fonte_selic,
                ipca=_pct(macro.ipca_12m),
                fonte_ipca=macro.fonte_ipca,
                data_ipca=f"{macro.data_ipca:%Y-%m-%d}",
            )
        )
        if macro.usou_valor_guardado:
            linhas.append(RESUMO_MACRO_GUARDADO)
    data_precos = _data_dos_precos(resultado)
    linhas.append(
        RESUMO_DATA_PRECOS.format(data=data_precos)
        if data_precos
        else RESUMO_DATA_PRECOS_INDISPONIVEL
    )
    return linhas


def _ler_argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m avaliador_b3.rodar_screener",
        description="Roda o screener (o mesmo procedimento do botão 'Rodar screener agora').",
    )
    parser.add_argument("--resumo", type=Path, help="grava também o resumo neste arquivo")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = _ler_argumentos(argv)
    resultado = None
    linhas: list[str]
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        try:
            resultado = screener.rodar_screener()
            codigo = CODIGO_SAIDA_RODADA_ACEITA
            linhas = [RESUMO_RODADA_ACEITA]
        except screener.RodadaScreenerRejeitada as erro:
            resultado = erro.resultado
            codigo = CODIGO_SAIDA_RODADA_REJEITADA
            linhas = [
                RESUMO_RODADA_REJEITADA,
                RESUMO_MOTIVO.format(motivo=erro.motivo),
                RESUMO_ARQUIVO_REJEITADO.format(caminho=erro.caminho_rejeitado),
            ]
        except Exception as erro:  # qualquer falha interrompe a rodada, com código próprio
            traceback.print_exc()
            codigo = CODIGO_SAIDA_RODADA_COM_EXCECAO
            linhas = [
                RESUMO_RODADA_EXCECAO,
                RESUMO_MOTIVO.format(motivo=f"{type(erro).__name__}: {erro}"),
            ]
    for aviso in avisos:
        warnings.warn_explicit(aviso.message, aviso.category, aviso.filename, aviso.lineno)

    linhas += _linhas_do_resultado(resultado)
    linhas += [RESUMO_AVISO.format(aviso=aviso.message) for aviso in avisos]
    resumo = "\n".join(linhas)
    print(resumo)
    if argumentos.resumo is not None:
        argumentos.resumo.write_text(resumo + "\n", encoding="utf-8")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
