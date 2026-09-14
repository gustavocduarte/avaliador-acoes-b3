"""Adapter para demonstrações financeiras da CVM (Comissão de Valores
Mobiliários) — dados abertos, dataset DFP (Demonstrações Financeiras
Padronizadas, anuais). Existe pra resolver a pendência que ficou do
adapter do Fundamentus: crescimento de lucro ano a ano, que o Fundamentus
não tem (só mostra o resultado dos últimos 12 meses).

Esse é o adapter mais "bruto" do projeto — não é uma API nem uma página
HTML formatada, é um zip anual (~13 MB) com vários CSVs de dados contábeis
em formato de plano de contas padronizado, ";"-separado, ISO-8859-1.

Duas coisas exigiram investigação antes de implementar (documentadas com
mais detalhe em config.py):

1. Cada arquivo anual já traz DOIS períodos por conta (ORDEM_EXERC
   "ÚLTIMO"/"PENÚLTIMO"), então um ano baixado basta para crescimento ano
   a ano — não precisa baixar dois zips.
2. O código da conta de "Lucro Líquido" NÃO é fixo entre empresas — muda
   conforme o tipo de negócio (ex: bancos têm plano de contas diferente de
   empresas não-financeiras). A extração usa uma regra posicional (última
   conta de nível 2 antes de "3.99", que é sempre Lucro por Ação) com uma
   checagem de sanidade na descrição da conta.

Processamento incremental: o zip é baixado uma vez por ano (cacheado em
disco) e nunca carregado inteiro em memória — os CSVs de interesse são
lidos linha a linha direto de dentro do zip, filtrando por CNPJ, sem passar
por um DataFrame com todas as ~700+ empresas do Brasil.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

import requests

from avaliador_b3.config import (
    CONTA_LUCRO_POR_ACAO_CVM,
    DATA_RAW_DIR,
    FATOR_ESCALA_MOEDA_CVM,
    URL_CVM_DFP_ZIP,
)

TIMEOUT_SEGUNDOS = 60
TAMANHO_PEDACO_DOWNLOAD = 256 * 1024
CODIFICACAO_CVM = "iso-8859-1"
PADRAO_CONTA_NIVEL_2 = re.compile(r"^3\.\d{2}$")


class ErroCVM(Exception):
    """Base para erros do adapter da CVM."""


class CnpjNaoEncontrado(ErroCVM):
    """O CNPJ não aparece nem na DRE consolidada nem na individual daquele ano."""


class ContaLucroNaoEncontrada(ErroCVM):
    """A empresa foi encontrada, mas não foi possível localizar com
    confiança a conta de Lucro Líquido — sinal de que o plano de contas ou
    o layout do zip da CVM mudou. Não tenta adivinhar um valor."""


def _normalizar_cnpj(cnpj: str) -> str:
    return "".join(c for c in cnpj if c.isdigit())


def _caminho_zip_ano(ano: int, diretorio_cache: Path) -> Path:
    return diretorio_cache / "cvm" / f"dfp_cia_aberta_{ano}.zip"


def _caminho_cache_resultado(cnpj_normalizado: str, ano: int, diretorio_cache: Path) -> Path:
    return diretorio_cache / "cvm" / f"lucro_{cnpj_normalizado}_{ano}.json"


def _baixar_zip_ano(ano: int, diretorio_cache: Path, forcar_atualizacao: bool) -> Path:
    """Baixa (com streaming, sem carregar tudo em memória) o zip anual do
    DFP, ou devolve o caminho do já cacheado. Um único zip serve para
    qualquer número de empresas consultadas naquele ano."""
    caminho = _caminho_zip_ano(ano, diretorio_cache)
    if caminho.exists() and not forcar_atualizacao:
        return caminho

    url = URL_CVM_DFP_ZIP.format(ano=ano)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho_temporario = caminho.with_suffix(".zip.tmp")

    with requests.get(url, timeout=TIMEOUT_SEGUNDOS, stream=True) as resposta:
        resposta.raise_for_status()
        with open(caminho_temporario, "wb") as arquivo:
            for pedaco in resposta.iter_content(chunk_size=TAMANHO_PEDACO_DOWNLOAD):
                arquivo.write(pedaco)

    caminho_temporario.replace(caminho)
    return caminho


def _linhas_da_empresa(
    caminho_zip: Path, ano: int, tipo: str, cnpj_normalizado: str
) -> list[dict]:
    """Lê o CSV de DRE ("con" ou "ind") de dentro do zip linha a linha,
    devolvendo só as linhas do CNPJ pedido — nunca materializa o arquivo
    inteiro (que cobre todas as companhias abertas do Brasil) em memória."""
    nome_membro = f"dfp_cia_aberta_DRE_{tipo}_{ano}.csv"
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        if nome_membro not in arquivo_zip.namelist():
            raise ContaLucroNaoEncontrada(
                f"Membro {nome_membro!r} não existe no zip da CVM para {ano} — "
                "o layout do pacote de dados pode ter mudado."
            )
        with arquivo_zip.open(nome_membro) as bruto:
            texto = io.TextIOWrapper(bruto, encoding=CODIFICACAO_CVM, newline="")
            leitor = csv.DictReader(texto, delimiter=";")
            return [
                linha
                for linha in leitor
                if _normalizar_cnpj(linha["CNPJ_CIA"]) == cnpj_normalizado
            ]


def _linha_lucro_liquido(linhas_periodo: list[dict]) -> dict:
    """Localiza a linha de Lucro Líquido dentro de um período (ÚLTIMO ou
    PENÚLTIMO): a última conta de nível 2 ("3.XX") antes de "3.99" (Lucro
    por Ação). Levanta ContaLucroNaoEncontrada se não achar candidata, ou
    se a descrição da conta não parecer mesmo ser de lucro/prejuízo."""
    candidatas = [
        linha
        for linha in linhas_periodo
        if PADRAO_CONTA_NIVEL_2.fullmatch(linha["CD_CONTA"])
        and linha["CD_CONTA"] != CONTA_LUCRO_POR_ACAO_CVM
    ]
    if not candidatas:
        raise ContaLucroNaoEncontrada(
            "Nenhuma conta de nível 2 (3.XX) encontrada antes de "
            f"{CONTA_LUCRO_POR_ACAO_CVM} — plano de contas pode ter mudado."
        )

    linha = max(candidatas, key=lambda linha: linha["CD_CONTA"])
    descricao = linha["DS_CONTA"].lower()
    if "lucro" not in descricao and "prejuízo" not in descricao and "prejuizo" not in descricao:
        raise ContaLucroNaoEncontrada(
            f"Conta {linha['CD_CONTA']!r} (esperada como Lucro Líquido) tem "
            f"descrição inesperada {linha['DS_CONTA']!r} — plano de contas "
            "pode ter mudado."
        )
    return linha


def _valor_conta(linha: dict) -> float:
    escala = linha["ESCALA_MOEDA"]
    if escala not in FATOR_ESCALA_MOEDA_CVM:
        raise ContaLucroNaoEncontrada(f"Escala monetária desconhecida: {escala!r}.")
    return float(linha["VL_CONTA"]) * FATOR_ESCALA_MOEDA_CVM[escala]


def _montar_resultado(ano: int, tipo: str, linhas: list[dict]) -> dict:
    linhas_atual = [linha for linha in linhas if linha["ORDEM_EXERC"] == "ÚLTIMO"]
    linhas_anterior = [linha for linha in linhas if linha["ORDEM_EXERC"] == "PENÚLTIMO"]

    if not linhas_atual:
        raise ContaLucroNaoEncontrada(
            f"Nenhuma linha com ORDEM_EXERC='ÚLTIMO' para o ano {ano} — "
            "formato do arquivo pode ter mudado."
        )

    linha_lucro_atual = _linha_lucro_liquido(linhas_atual)
    lucro_atual = _valor_conta(linha_lucro_atual)

    lucro_anterior = None
    periodo_anterior_fim = None
    if linhas_anterior:
        linha_lucro_anterior = _linha_lucro_liquido(linhas_anterior)
        lucro_anterior = _valor_conta(linha_lucro_anterior)
        periodo_anterior_fim = linha_lucro_anterior["DT_FIM_EXERC"]

    crescimento_percentual = None
    if lucro_anterior not in (None, 0):
        crescimento_percentual = (lucro_atual - lucro_anterior) / abs(lucro_anterior) * 100

    primeira_linha = linhas[0]
    return {
        "cnpj": primeira_linha["CNPJ_CIA"],
        "cd_cvm": primeira_linha["CD_CVM"],
        "denominacao": primeira_linha["DENOM_CIA"],
        "tipo_demonstracao": "consolidado" if tipo == "con" else "individual",
        "conta_lucro_liquido": linha_lucro_atual["CD_CONTA"],
        "ano_referencia": ano,
        "periodo_atual_fim": linha_lucro_atual["DT_FIM_EXERC"],
        "lucro_liquido_atual": lucro_atual,
        "periodo_anterior_fim": periodo_anterior_fim,
        "lucro_liquido_anterior": lucro_anterior,
        "crescimento_lucro_percentual": crescimento_percentual,
    }


def obter_lucro_liquido(
    cnpj: str,
    ano: int,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> dict:
    """Busca o Lucro Líquido de uma empresa para `ano` (mais o valor do
    ano anterior e o crescimento percentual entre eles, já que cada
    arquivo anual da CVM traz os dois períodos).

    Prefere a demonstração consolidada; cai para a individual se a empresa
    não tiver consolidado (comum em empresas sem subsidiárias). Levanta
    `CnpjNaoEncontrado` se o CNPJ não aparecer em nenhuma das duas, ou
    `ContaLucroNaoEncontrada` se a conta de Lucro Líquido não puder ser
    localizada com confiança (formato/plano de contas mudou).
    """
    cnpj_normalizado = _normalizar_cnpj(cnpj)
    caminho_resultado = _caminho_cache_resultado(cnpj_normalizado, ano, diretorio_cache)

    if usar_cache and not forcar_atualizacao and caminho_resultado.exists():
        return json.loads(caminho_resultado.read_text(encoding="utf-8"))

    caminho_zip = _baixar_zip_ano(ano, diretorio_cache, forcar_atualizacao)

    resultado = None
    for tipo in ("con", "ind"):
        linhas = _linhas_da_empresa(caminho_zip, ano, tipo, cnpj_normalizado)
        if not linhas:
            continue
        resultado = _montar_resultado(ano, tipo, linhas)
        break

    if resultado is None:
        raise CnpjNaoEncontrado(f"CNPJ {cnpj!r} não encontrado no DFP da CVM para {ano}.")

    if usar_cache:
        caminho_resultado.parent.mkdir(parents=True, exist_ok=True)
        caminho_resultado.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")

    return resultado
