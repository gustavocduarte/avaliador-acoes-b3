"""Balanço consolidado e composição do capital da CVM (ITR e DFP).

Uma leitura só, na data-base do balanço do Fundamentus, devolve o patrimônio
líquido total, a participação dos não controladores, o passivo de
arrendamento que ficou fora da dívida do Fundamentus e o número de ações em
circulação. 31/03, 30/06 e 30/09 vêm do ITR; 31/12 vem do DFP, sempre na
versão mais recente do documento. Módulo próprio (e não `ingest/cvm.py`)
porque lê outros arquivos do zip (BPP e composição do capital) e tem regras
próprias, mas reaproveita o download, o cache do zip e a leitura linha a
linha de `ingest/cvm.py`.

Se a data-base não existir na CVM, o resultado diz que está indisponível e
por quê; nunca cai para outra data em silêncio.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import requests

from avaliador_b3.config import (
    AVISO_DIVERGENCIA_ACOES,
    AVISO_UNIT_FATOR_DIFERENTE,
    AVISO_UNIT_FORA_DA_TABELA,
    CODIGO_PATRIMONIO_LIQUIDO_CVM,
    COMPLEMENTO_ACOES_DIVERGENCIA_UNIT,
    DATA_RAW_DIR,
    FAIXA_RAZAO_ESCALA_MILHARES_CVM,
    FATOR_ESCALA_MILHARES_CVM,
    FATOR_ESCALA_MOEDA_CVM,
    LIMITE_DIVERGENCIA_ACOES,
    LIMITE_DIVERGENCIA_ACOES_IMPLAUSIVEL,
    LIMITE_TESOURARIA_SOBRE_CAPITAL,
    MES_DIA_BALANCO_DFP,
    MESES_DIAS_BALANCO_ITR,
    MOTIVO_ACOES_DIVERGENCIA_IMPLAUSIVEL,
    MOTIVO_ACOES_SEM_COMPOSICAO,
    MOTIVO_ACOES_SEM_REFERENCIA,
    MOTIVO_ACOES_TESOURARIA_ALTA,
    MOTIVO_BALANCO_ARQUIVO_NAO_PUBLICADO,
    MOTIVO_BALANCO_DATA_FORA_DO_TRIMESTRE,
    MOTIVO_BALANCO_SEM_DATA_BASE,
    MOTIVO_BALANCO_SEM_DEMONSTRACAO,
    PREFIXOS_CONTAS_DIVIDA_FUNDAMENTUS,
    PREFIXOS_CONTAS_PASSIVO,
    TERMO_NAO_CONTROLADORES,
    TERMOS_PASSIVO_ARRENDAMENTO,
    TOLERANCIA_FATOR_UNIT_TABELA,
    TOLERANCIA_INTEGRALIZADO_LIQUIDO,
    UNITS_COMPOSICAO,
    VERSAO_SCHEMA_CVM_BALANCO,
)
from avaliador_b3.ingest.cvm import (
    ErroCVM,
    _baixar_zip_ano,
    _linhas_do_membro,
    _normalizar_cnpj,
    _normalizar_descricao,
    _sem_ancestral_marcado,
)


class MembroDoZipAusente(ErroCVM):
    """O CSV esperado não existe no zip (o layout do pacote pode ter mudado)."""


def _documento_e_ano(data_base: date) -> tuple[str, int] | None:
    """("itr" ou "dfp", ano) da data-base, ou `None` se não for fim de trimestre."""
    mes_dia = f"{data_base.month:02d}-{data_base.day:02d}"
    if mes_dia in MESES_DIAS_BALANCO_ITR:
        return "itr", data_base.year
    if mes_dia == MES_DIA_BALANCO_DFP:
        return "dfp", data_base.year
    return None


def _indisponivel(motivo: str, data_base: str | None = None) -> dict:
    return {"disponivel": False, "motivo": motivo, "data_base": data_base}


def _texto_documento(documento: str, data_base: date) -> str:
    return f"{documento.upper()} de {data_base:%d/%m/%Y}"


def _mais_recente(linhas: list[dict]) -> list[dict]:
    """Só as linhas da versão mais recente do documento."""
    if not linhas:
        return []
    versao = max(int(linha["VERSAO"]) for linha in linhas)
    return [linha for linha in linhas if int(linha["VERSAO"]) == versao]


def _valor(linha: dict) -> float:
    return float(linha["VL_CONTA"]) * FATOR_ESCALA_MOEDA_CVM[linha["ESCALA_MOEDA"]]


def _contas_do_balanco(linhas: list[dict], data_base: str) -> dict:
    """Patrimônio total, não controladores e passivo de arrendamento do balanço
    consolidado já filtrado na data-base e na versão mais recente."""
    contas = [
        {
            "codigo": linha["CD_CONTA"],
            "descricao": linha["DS_CONTA"],
            "nds": _normalizar_descricao(linha["DS_CONTA"]),
            "valor": _valor(linha),
        }
        for linha in linhas
        if linha["ORDEM_EXERC"] == "ÚLTIMO" and linha["DT_FIM_EXERC"] == data_base
    ]
    patrimonio = next(
        (c["valor"] for c in contas if c["codigo"] == CODIGO_PATRIMONIO_LIQUIDO_CVM), None
    )
    nao_controladores = sum(
        c["valor"]
        for c in contas
        if c["codigo"].startswith(CODIGO_PATRIMONIO_LIQUIDO_CVM + ".")
        and c["codigo"].count(".") == 2
        and TERMO_NAO_CONTROLADORES in c["nds"]
    )

    def e_arrendamento(conta: dict) -> bool:
        return conta["codigo"].startswith(PREFIXOS_CONTAS_PASSIVO) and any(
            termo in conta["nds"] for termo in TERMOS_PASSIVO_ARRENDAMENTO
        )

    def na_divida_do_fundamentus(conta: dict) -> bool:
        return any(
            conta["codigo"] == prefixo or conta["codigo"].startswith(prefixo + ".")
            for prefixo in PREFIXOS_CONTAS_DIVIDA_FUNDAMENTUS
        )

    arrendamentos = [c for c in contas if e_arrendamento(c)]
    dentro = _sem_ancestral_marcado([c for c in arrendamentos if na_divida_do_fundamentus(c)])
    fora = _sem_ancestral_marcado([c for c in arrendamentos if not na_divida_do_fundamentus(c)])
    return {
        "patrimonio_liquido_total": patrimonio,
        "nao_controladores": nao_controladores,
        "arrendamento_fora_da_divida": sum(c["valor"] for c in fora),
        "arrendamento_na_divida": sum(c["valor"] for c in dentro),
        "linhas_arrendamento_fora": [
            {"codigo": c["codigo"], "descricao": c["descricao"], "valor": c["valor"]} for c in fora
        ],
    }


def _capital(linhas: list[dict], data_base: str) -> dict | None:
    """Composição do capital na data-base (versão mais recente), nas unidades do
    arquivo (a escala é tratada em `calcular_acoes_em_circulacao`)."""
    do_dia = _mais_recente([linha for linha in linhas if linha["DT_REFER"] == data_base])
    if not do_dia:
        return None
    linha = do_dia[0]

    def n(campo: str) -> float:
        return float(linha[campo] or 0)

    return {
        "ordinarias": n("QT_ACAO_ORDIN_CAP_INTEGR"),
        "preferenciais": n("QT_ACAO_PREF_CAP_INTEGR"),
        "integralizado": n("QT_ACAO_TOTAL_CAP_INTEGR"),
        "tesouraria": n("QT_ACAO_TOTAL_TESOURO"),
        "versao": int(linha["VERSAO"]),
    }


def _caminho_cache(cnpj_normalizado: str, data_base: str, diretorio_cache: Path) -> Path:
    return diretorio_cache / "cvm" / f"balanco_{cnpj_normalizado}_{data_base}.json"


def _ler_cache(caminho: Path) -> dict | None:
    """Lê o cache só se a versão do schema bater (mesmo mecanismo do FCF)."""
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if bruto.get("versao_schema") != VERSAO_SCHEMA_CVM_BALANCO:
        return None
    return bruto.get("resultado")


def _membro(documento: str, demonstracao: str, ano: int) -> str:
    return f"{documento}_cia_aberta_{demonstracao}_{ano}.csv"


def obter_balanco_cvm(
    cnpj: str,
    data_base: str | None,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> dict:
    """Balanço consolidado e composição do capital da CVM de `cnpj` em
    `data_base` ("AAAA-MM-DD", fim de trimestre), sem tratar o número de
    ações (ver `calcular_acoes_em_circulacao`).

    Devolve `{"disponivel": True, ...}` com `data_base`, `fonte`,
    `patrimonio_liquido_total`, `nao_controladores`,
    `arrendamento_fora_da_divida`, `arrendamento_na_divida`,
    `linhas_arrendamento_fora` e `capital` (ou `None` se a empresa não tem
    composição nessa data), ou `{"disponivel": False, "motivo": ...}`.
    Erros de rede propagam, como nas outras leituras da CVM."""
    if not data_base:
        return _indisponivel(MOTIVO_BALANCO_SEM_DATA_BASE)
    data = date.fromisoformat(data_base)
    alvo = _documento_e_ano(data)
    if alvo is None:
        motivo = MOTIVO_BALANCO_DATA_FORA_DO_TRIMESTRE.format(data=f"{data:%d/%m/%Y}")
        return _indisponivel(motivo, data_base)
    documento, ano = alvo
    cnpj_normalizado = _normalizar_cnpj(cnpj)
    caminho_cache = _caminho_cache(cnpj_normalizado, data_base, diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho_cache.exists():
        em_cache = _ler_cache(caminho_cache)
        if em_cache is not None:
            return em_cache

    try:
        caminho_zip = _baixar_zip_ano(ano, diretorio_cache, forcar_atualizacao, documento=documento)
    except requests.HTTPError as erro:
        if erro.response is not None and erro.response.status_code == 404:
            return _indisponivel(
                MOTIVO_BALANCO_ARQUIVO_NAO_PUBLICADO.format(documento=documento.upper(), ano=ano),
                data_base,
            )
        raise

    try:
        linhas_bpp = _linhas_do_membro(
            caminho_zip,
            _membro(documento, "BPP_con", ano),
            ano,
            cnpj_normalizado,
            MembroDoZipAusente,
        )
    except MembroDoZipAusente as erro:
        return _indisponivel(str(erro), data_base)
    linhas_bpp = _mais_recente([linha for linha in linhas_bpp if linha["DT_REFER"] == data_base])
    try:
        linhas_capital = _linhas_do_membro(
            caminho_zip,
            _membro(documento, "composicao_capital", ano),
            ano,
            cnpj_normalizado,
            MembroDoZipAusente,
        )
        capital = _capital(linhas_capital, data_base)
    except MembroDoZipAusente:
        capital = None
    if not linhas_bpp:
        # Sem balanço consolidado, mas a composição do capital ainda serve ao número
        # de ações; este resultado parcial não vai para o cache.
        motivo = MOTIVO_BALANCO_SEM_DEMONSTRACAO.format(
            data=f"{data:%d/%m/%Y}", documento=documento.upper()
        )
        return {
            **_indisponivel(motivo, data_base),
            "documento": documento.upper(),
            "capital": capital,
        }

    contas = _contas_do_balanco(linhas_bpp, data_base)

    resultado = {
        "disponivel": True,
        "motivo": None,
        "data_base": data_base,
        "fonte": f"{_texto_documento(documento, data)} (versão {int(linhas_bpp[0]['VERSAO'])})",
        "documento": documento.upper(),
        **contas,
        "capital": capital,
    }
    if usar_cache:
        caminho_cache.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"versao_schema": VERSAO_SCHEMA_CVM_BALANCO, "resultado": resultado}
        caminho_cache.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    return resultado


def _fmt_acoes(valor: float) -> str:
    """Milhões de ações com vírgula decimal e ponto de milhar (convenção brasileira)."""
    texto = f"{valor / 1e6:,.2f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".") + " mi"


def _ordinarias_equivalentes_por_unit(composicao_unit: dict) -> float:
    """Ordinárias equivalentes de uma unit: ON + peso econômico da PN × PN."""
    return (
        composicao_unit["ordinarias"]
        + composicao_unit["peso_preferencial"] * composicao_unit["preferenciais"]
    )


def montar_aviso_unit(ticker: str | None, acoes_por_cotacao: int | None) -> str | None:
    """Aviso quando o fator de unit do Fundamentus não bate com a tabela de composições
    (`config.UNITS_COMPOSICAO`) ou quando uma unit não está na tabela. `None` nos demais casos
    (inclusive ação comum, fator 1, e fator ou ticker indisponível)."""
    if not ticker or not acoes_por_cotacao:
        return None
    composicao = UNITS_COMPOSICAO.get(ticker)
    if composicao is None:
        if acoes_por_cotacao > 1:
            return AVISO_UNIT_FORA_DA_TABELA.format(ticker=ticker, fator=acoes_por_cotacao)
        return None
    esperado = _ordinarias_equivalentes_por_unit(composicao)
    if abs(acoes_por_cotacao / esperado - 1) <= TOLERANCIA_FATOR_UNIT_TABELA:
        return None
    return AVISO_UNIT_FATOR_DIFERENTE.format(
        fundamentus=acoes_por_cotacao,
        ticker=ticker,
        esperado=esperado,
        ordinarias=composicao["ordinarias"],
        preferenciais=composicao["preferenciais"],
        peso=composicao["peso_preferencial"],
    )


def calcular_acoes_em_circulacao(
    capital: dict | None,
    acoes_fundamentus: float | None,
    acoes_por_cotacao: int | None,
    data_base: str,
    documento: str,
    composicao_unit: dict | None = None,
) -> dict:
    """Ações em circulação (integralizado menos tesouraria) na base da cotação.

    `acoes_fundamentus` está na base da cotação (units já convertidas) e
    `acoes_por_cotacao` é o número de ações por cotação (1, ou o da unit).
    Com `composicao_unit` (uma linha de `config.UNITS_COMPOSICAO`), a composição da CVM é
    convertida por peso econômico: o integralizado conta ON + peso × PN e o fator é
    ON por unit + peso × PN por unit, em vez de ações físicas e do fator do Fundamentus.
    Salvaguardas: (1) escala: se o número do Fundamentus for cerca de 1.000
    vezes a composição, ela está em milhares; (2) tesouraria acima de
    `LIMITE_TESOURARIA_SOBRE_CAPITAL` do capital é tratada como erro de
    escala dos dados e o número fica indisponível; (3) se integralizado mais
    tesouraria bate com o Fundamentus, o integralizado já vem líquido da
    tesouraria e é o próprio número em circulação.

    Devolve `acoes` (ou `None`), `motivo` (quando `None`), `aviso_divergencia`
    (texto quando o Fundamentus não bate nem com o número em circulação nem com
    o integralizado, com diferença acima de `LIMITE_DIVERGENCIA_ACOES`) e os
    números usados."""
    data = date.fromisoformat(data_base)
    if capital is None:
        return {
            "acoes": None,
            "motivo": MOTIVO_ACOES_SEM_COMPOSICAO.format(
                data=f"{data:%d/%m/%Y}", documento=documento
            ),
            "aviso_divergencia": None,
        }
    if not acoes_fundamentus or acoes_fundamentus <= 0:
        return {"acoes": None, "motivo": MOTIVO_ACOES_SEM_REFERENCIA, "aviso_divergencia": None}

    fator: float = acoes_por_cotacao or 1
    referencia = acoes_fundamentus * fator  # em ações, como a CVM
    integralizado = capital["integralizado"]
    tesouraria = capital["tesouraria"]

    razao = referencia / integralizado if integralizado else 0.0
    minimo, maximo = FAIXA_RAZAO_ESCALA_MILHARES_CVM
    em_milhares = minimo <= razao <= maximo
    if em_milhares:
        integralizado *= FATOR_ESCALA_MILHARES_CVM
        tesouraria *= FATOR_ESCALA_MILHARES_CVM

    ordinarias = capital.get("ordinarias") or 0.0
    preferenciais = capital.get("preferenciais") or 0.0
    if composicao_unit is not None and ordinarias + preferenciais > 0:
        escala = FATOR_ESCALA_MILHARES_CVM if em_milhares else 1.0
        peso = composicao_unit["peso_preferencial"]
        integralizado = (ordinarias + peso * preferenciais) * escala
        fator = _ordinarias_equivalentes_por_unit(composicao_unit)
        referencia = acoes_fundamentus * fator

    base = {
        "escala_em_milhares": em_milhares,
        "integralizado": integralizado,
        "tesouraria": tesouraria,
    }
    percentual_tesouraria = tesouraria / integralizado if integralizado else 0.0
    if percentual_tesouraria > LIMITE_TESOURARIA_SOBRE_CAPITAL:
        return {
            "acoes": None,
            "motivo": MOTIVO_ACOES_TESOURARIA_ALTA.format(
                percentual=f"{percentual_tesouraria:.0%}",
                limite=f"{LIMITE_TESOURARIA_SOBRE_CAPITAL:.0%}",
            ),
            "aviso_divergencia": None,
            **base,
        }

    # Tesouraria menor que a tolerância não distingue os dois casos (e o efeito seria
    # menor que ela), então vale o padrão: integralizado menos tesouraria.
    ja_liquido = percentual_tesouraria > TOLERANCIA_INTEGRALIZADO_LIQUIDO and (
        abs((integralizado + tesouraria) / referencia - 1) <= TOLERANCIA_INTEGRALIZADO_LIQUIDO
    )
    em_circulacao = integralizado if ja_liquido else integralizado - tesouraria
    com_tesouraria = em_circulacao + tesouraria

    aviso = None
    divergencia = min(abs(referencia / em_circulacao - 1), abs(referencia / com_tesouraria - 1))
    if divergencia > LIMITE_DIVERGENCIA_ACOES_IMPLAUSIVEL:
        return {
            "acoes": None,
            "motivo": MOTIVO_ACOES_DIVERGENCIA_IMPLAUSIVEL.format(
                cvm=_fmt_acoes(em_circulacao / fator),
                divergencia=f"{referencia / em_circulacao - 1:+.0%}",
                fundamentus=_fmt_acoes(acoes_fundamentus),
            )
            + (f" {COMPLEMENTO_ACOES_DIVERGENCIA_UNIT}" if fator > 1 else ""),
            "aviso_divergencia": None,
            "descartada_por_divergencia": True,
            **base,
        }
    if divergencia > LIMITE_DIVERGENCIA_ACOES:
        aviso = AVISO_DIVERGENCIA_ACOES.format(
            fundamentus=_fmt_acoes(acoes_fundamentus),
            cvm=_fmt_acoes(em_circulacao / fator),
            divergencia=f"{referencia / em_circulacao - 1:+.1%}".replace(".", ","),
            data=f"{data:%d/%m/%Y}",
        )
    return {
        "acoes": em_circulacao / fator,
        "motivo": None,
        "aviso_divergencia": aviso,
        "integralizado_ja_liquido": ja_liquido,
        **base,
    }


def obter_leitura_balanco(
    cnpj: str,
    data_base: str | None,
    acoes_fundamentus: float | None,
    acoes_por_cotacao: int | None,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
    ticker: str | None = None,
) -> dict:
    """Leitura única: `obter_balanco_cvm` mais as ações em circulação
    (`calcular_acoes_em_circulacao`), com `acoes_em_circulacao`,
    `motivo_acoes`, `aviso_divergencia_acoes` e `aviso_unit`. Com o `ticker` de uma unit da
    tabela `config.UNITS_COMPOSICAO`, a composição da CVM é convertida por peso econômico."""
    balanco = obter_balanco_cvm(cnpj, data_base, usar_cache, forcar_atualizacao, diretorio_cache)
    aviso_unit = montar_aviso_unit(ticker, acoes_por_cotacao)
    if "documento" not in balanco:  # nem o arquivo da data-base foi lido
        return {
            **balanco,
            "acoes_em_circulacao": None,
            "motivo_acoes": balanco["motivo"],
            "aviso_unit": aviso_unit,
        }
    acoes = calcular_acoes_em_circulacao(
        balanco["capital"],
        acoes_fundamentus,
        acoes_por_cotacao,
        balanco["data_base"],
        balanco["documento"],
        composicao_unit=UNITS_COMPOSICAO.get(ticker) if ticker else None,
    )
    return {
        **balanco,
        "aviso_unit": aviso_unit,
        "acoes_em_circulacao": acoes["acoes"],
        "motivo_acoes": acoes["motivo"],
        "aviso_divergencia_acoes": acoes["aviso_divergencia"],
        "detalhe_acoes": {
            chave: valor
            for chave, valor in acoes.items()
            if chave not in ("acoes", "motivo", "aviso_divergencia")
        },
    }
