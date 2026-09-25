"""Crosswalk ticker (B3) <-> CNPJ (CVM) — a peça que faltava para conectar
`b3_universo.py` (universo de ações, indexado por ticker) a `cvm.py`
(demonstrações financeiras, indexado por CNPJ).

Investigação feita antes de implementar:

1. A resposta de `indexProxy/indexCall/GetPortfolioDay` (usada em
   b3_universo.py) só traz `cod`/`asset`/`type`/`part`/`partAcum`/
   `theoricalQty` — nenhum identificador além de ticker e nome.
2. Outro endpoint não-documentado da B3, `listedCompaniesProxy/CompanyCall/
   GetInitialCompanies`, traz o catálogo completo de emissores (~3500
   registros) com CNPJ, código CVM e nome — já suficiente sozinho, sem
   precisar do dataset de cadastro da CVM. O CNPJ dessa resposta foi
   conferido manualmente contra o cadastro de companhias abertas da CVM
   (dados.cvm.gov.br) para três empresas reais e bateu nos três casos —
   ver o comentário em config.py com os detalhes.

Chave usada: o código do emissor (4 letras, campo "issuingCompany"), que é
sempre o prefixo do ticker sem o dígito de classe final. Validado contra os
76 tickers reais do Ibovespa: 100% resolvidos por essa chave — não foi
preciso cair para casamento de nome (frágil, evitado de propósito).

Classificação setorial (2026-09-16): o mesmo registro de
`GetInitialCompanies` já traz um campo "segment" — não confundir com o
"market" (esse sim é o segmento de LISTAGEM, Novo Mercado/N1/N2, já usado
em `b3_universo.py`). "segment" é a classificação setorial oficial da B3
(a granularidade mais fina do que a B3 chama de "Segmento" na página
pública "Classificação Setorial", dentro de Setor Econômico > Subsetor >
Segmento — não temos os dois níveis mais amplos, só esse). Validado
manualmente contra pares óbvios do Ibovespa real: PETR4 e PRIO3 caem
ambos em "Exploração. Refino e Distribuição"; ITUB4/BBDC4/BBAS3 caem
todos em "Bancos"; VALE3 cai em "Minerais Metálicos" (setor diferente dos
dois grupos acima, como esperado).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from avaliador_b3.config import (
    DATA_RAW_DIR,
    DELAY_PAGINACAO_B3_SEGUNDOS,
    TAMANHO_CNPJ,
    TAMANHO_CODIGO_CVM,
    TAMANHO_PAGINA_API_B3_CATALOGO,
    URL_B3_CATALOGO_EMISSORES,
)
from avaliador_b3.ingest._paginacao import buscar_registros_paginados, parametros_base64
from avaliador_b3.ingest.b3_universo import obter_universo_ibovespa

CAMPOS_OBRIGATORIOS_REGISTRO = {"issuingCompany", "codeCVM", "cnpj", "companyName", "segment"}
PADRAO_SUFIXO_CLASSE = re.compile(r"\d+$")


class ErroCrosswalk(Exception):
    """Base para erros do crosswalk ticker <-> CNPJ."""


class EmissorNaoEncontrado(ErroCrosswalk):
    """O código de emissor derivado do ticker não está no catálogo da B3."""


def _codigo_emissor(ticker: str) -> str:
    """Deriva o código do emissor removendo o sufixo numérico de classe do
    final do ticker. Ex: "PETR4" -> "PETR", "TAEE11" -> "TAEE", "B3SA3" ->
    "B3SA" (só o último dígito sai, não o "3" no meio do código)."""
    return PADRAO_SUFIXO_CLASSE.sub("", ticker)


def _montar_url(pagina: int, tamanho_pagina: int) -> str:
    parametros = {"language": "pt-br", "pageNumber": pagina, "pageSize": tamanho_pagina}
    return URL_B3_CATALOGO_EMISSORES.format(parametros_base64=parametros_base64(parametros))


def _completar_zeros(valor, tamanho: int) -> str:
    """Completa `valor` (str ou int) com zeros à esquerda até `tamanho`
    dígitos. Bug real encontrado em 2026-09-25 (ver o comentário completo em
    config.py, junto de TAMANHO_CNPJ/TAMANHO_CODIGO_CVM): a API
    "GetInitialCompanies" devolve "cnpj" e "codeCVM" como NÚMERO JSON, e um
    literal numérico JSON não pode ter zero à esquerda — o dígito já se
    perde na resposta da API, antes de qualquer código deste projeto rodar.
    `str()` sozinho (usado antes aqui só pra "codigo_cvm") corrige o TIPO
    (int -> str) mas não restaura o zero perdido — só `.zfill` faz isso.
    Seguro porque CNPJ e código CVM têm largura FIXA e conhecida (14 e 6
    dígitos respectivamente, confirmado contra os zips da CVM): completar
    com zero só restaura um dígito que sabemos que existia, nunca cria
    ambiguidade com outra empresa."""
    return str(valor).zfill(tamanho)


def _registro_para_linha(registro: dict) -> dict:
    faltando = CAMPOS_OBRIGATORIOS_REGISTRO - registro.keys()
    if faltando:
        raise ValueError(
            "Formato do catálogo de emissores da B3 mudou: campos "
            f"{sorted(faltando)} não encontrados no registro {registro}."
        )
    return {
        "codigo_emissor": registro["issuingCompany"],
        "codigo_cvm": _completar_zeros(registro["codeCVM"], TAMANHO_CODIGO_CVM),
        "cnpj": _completar_zeros(registro["cnpj"], TAMANHO_CNPJ),
        "nome_empresa": registro["companyName"],
        "segmento_setorial": registro["segment"],
    }


def _caminho_cache_catalogo(diretorio_cache: Path) -> Path:
    return diretorio_cache / "b3" / "catalogo_emissores.csv"


def obter_catalogo_emissores(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    tamanho_pagina: int = TAMANHO_PAGINA_API_B3_CATALOGO,
    delay_segundos: float = DELAY_PAGINACAO_B3_SEGUNDOS,
) -> pd.DataFrame:
    """Busca o catálogo completo de emissores da B3 (todos os tipos de
    ativo — ações, BDRs, ETFs, etc., não só o Ibovespa) e devolve um
    DataFrame com `codigo_emissor`, `codigo_cvm`, `cnpj` e `nome_empresa`.

    É um catálogo de referência que muda pouco, então o cache (em
    `data/raw/b3/catalogo_emissores.csv`) não tem TTL.

    `delay_segundos` é aplicado entre uma página e a próxima (~36 páginas
    pro catálogo completo de ~3523 registros, ver
    TAMANHO_PAGINA_API_B3_CATALOGO em config.py) — ver
    `ingest._paginacao.buscar_registros_paginados`.
    """
    caminho = _caminho_cache_catalogo(diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        # A normalização de zeros à esquerda (ver _completar_zeros) é
        # aplicada aqui de novo, não só em _registro_para_linha — cache já
        # em disco de ANTES da correção (2026-09-25) ainda tem "cnpj"/
        # "codigo_cvm" sem o(s) zero(s) perdido(s), e o cache não tem TTL
        # (não expira sozinho). Reaplicar na leitura corrige qualquer cache
        # antigo automaticamente, sem precisar apagar o arquivo nem baixar
        # de novo (~36 páginas da API) só por causa desse bug específico.
        df = pd.read_csv(caminho, dtype=str)
        df["cnpj"] = df["cnpj"].apply(lambda v: _completar_zeros(v, TAMANHO_CNPJ))
        df["codigo_cvm"] = df["codigo_cvm"].apply(lambda v: _completar_zeros(v, TAMANHO_CODIGO_CVM))
        return df

    registros = buscar_registros_paginados(
        montar_url=lambda pagina: _montar_url(pagina, tamanho_pagina),
        contexto="catálogo de emissores da B3",
        delay_segundos=delay_segundos,
    )

    linhas = [_registro_para_linha(registro) for registro in registros]
    df = pd.DataFrame(linhas).sort_values("codigo_emissor").reset_index(drop=True)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df


def resolver_cnpj(ticker: str, catalogo: pd.DataFrame) -> dict:
    """Resolve um ticker isolado no catálogo de emissores (já carregado em
    `catalogo`, ver `obter_catalogo_emissores`). Levanta
    `EmissorNaoEncontrado` se o código do emissor derivado do ticker não
    estiver no catálogo."""
    codigo_emissor = _codigo_emissor(ticker)
    linhas = catalogo[catalogo["codigo_emissor"] == codigo_emissor]
    if linhas.empty:
        raise EmissorNaoEncontrado(
            f"Ticker {ticker!r} (emissor {codigo_emissor!r}) não encontrado "
            "no catálogo de emissores da B3."
        )
    linha = linhas.iloc[0]
    return {
        "ticker": ticker,
        "codigo_emissor": codigo_emissor,
        "cnpj": linha["cnpj"],
        "codigo_cvm": linha["codigo_cvm"],
        "nome_empresa": linha["nome_empresa"],
        "segmento_setorial": linha["segmento_setorial"],
    }


def resolver_segmentos_setoriais(tickers: list[str], catalogo: pd.DataFrame) -> pd.DataFrame:
    """Resolve o segmento setorial (ver `_registro_para_linha`) de uma
    lista de tickers contra o catálogo já carregado, devolvendo um
    DataFrame com `ticker` e `segmento_setorial`.

    Tickers que não resolverem (`EmissorNaoEncontrado`) são simplesmente
    omitidos do resultado — usado pra achar pares do mesmo setor entre um
    conjunto de tickers (ex: os do screener), onde o interesse é só nos
    que SÃO identificáveis, não é um erro que deva travar a busca toda.
    """
    linhas = []
    for ticker in tickers:
        try:
            info = resolver_cnpj(ticker, catalogo)
        except EmissorNaoEncontrado:
            continue
        linhas.append({"ticker": ticker, "segmento_setorial": info["segmento_setorial"]})
    return pd.DataFrame(linhas, columns=["ticker", "segmento_setorial"])


def _caminho_cache_crosswalk(diretorio_cache: Path) -> Path:
    return diretorio_cache / "b3" / "crosswalk_ibovespa.csv"


def obter_crosswalk_ibovespa(
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> pd.DataFrame:
    """Cruza o universo do Ibovespa (`b3_universo.obter_universo_ibovespa`)
    com o catálogo de emissores da B3, devolvendo um DataFrame com
    `ticker`, `codigo_emissor`, `cnpj`, `codigo_cvm` e `nome_empresa` para
    cada ação do índice.

    Levanta `EmissorNaoEncontrado` se algum ticker do Ibovespa não resolver
    para um emissor conhecido — tratado como um problema a investigar, não
    como uma linha a pular silenciosamente (na validação contra os 76
    tickers reais em 2026-09-14, isso nunca aconteceu).

    Testada e pública, mas **não é usada por nenhum código de produção do
    projeto hoje** (nem `app/main.py`, nem `screener.py`) — de propósito,
    não por esquecimento. `screener.py` resolve CNPJ ticker a ticker,
    dentro de um loop, chamando `resolver_cnpj` diretamente pra cada ação:
    isso isola erro por ticker (uma falha de resolução derruba só a linha
    daquele ticker na tabela final, não as outras ~75). Resolver em lote
    aqui, de uma vez, perderia essa granularidade — `EmissorNaoEncontrado`
    de um único ticker derruba a função inteira, sem sinalizar qual dos
    ~76 falhou, a menos que quem chamasse tratasse cada falha
    individualmente por fora, o que essa função hoje não faz. Fica como
    candidata a uso futuro (ex: uma ferramenta de linha de comando
    separada, fora do fluxo interativo do dashboard, onde "tudo ou nada"
    é aceitável) — não uma sobra esquecida do desenvolvimento.
    """
    caminho = _caminho_cache_crosswalk(diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho.exists():
        return pd.read_csv(caminho, dtype=str)

    universo = obter_universo_ibovespa(
        usar_cache=usar_cache,
        forcar_atualizacao=forcar_atualizacao,
        diretorio_cache=diretorio_cache,
    )
    catalogo = obter_catalogo_emissores(
        usar_cache=usar_cache,
        forcar_atualizacao=forcar_atualizacao,
        diretorio_cache=diretorio_cache,
    )

    linhas = [resolver_cnpj(ticker, catalogo) for ticker in universo["ticker"]]
    df = pd.DataFrame(linhas)

    if usar_cache:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho, index=False)

    return df
