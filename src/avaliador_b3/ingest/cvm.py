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
    CODIGO_CFI_CVM,
    CODIGO_CFO_CVM,
    CONTA_LUCRO_POR_ACAO_CVM,
    DATA_RAW_DIR,
    FATOR_ESCALA_MOEDA_CVM,
    URL_CVM_DFP_ZIP,
)

TIMEOUT_SEGUNDOS = 60
# Baixado em pedaços (streaming, nunca o zip inteiro de uma vez em memória)
# porque a máquina onde o projeto roda tem RAM limitada — o zip anual do
# DFP tem ~13 MB, pequeno perto do limite de RAM de qualquer máquina atual,
# mas o princípio (nunca materializar um arquivo grande inteiro em memória
# só porque "hoje" ele é pequeno) é o mesmo aplicado ao resto do adapter:
# os CSVs de dentro do zip também são lidos linha a linha, nunca com todas
# as ~700+ empresas do Brasil num DataFrame só. 256 KiB é um tamanho de
# pedaço comum/razoável pra streaming HTTP, não um valor medido/otimizado
# especificamente pra esse download.
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


class ContaFluxoCaixaNaoEncontrada(ErroCVM):
    """A empresa foi encontrada na DFC, mas as contas 6.01/6.02 (Caixa
    Líquido Atividades Operacionais/Investimento) não estão lá — sinal de
    que o layout do zip da CVM mudou. Não tenta adivinhar um valor."""


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


def _linhas_do_membro(
    caminho_zip: Path,
    nome_membro: str,
    ano: int,
    cnpj_normalizado: str,
    classe_erro: type[Exception],
) -> list[dict]:
    """Lê um CSV de dentro do zip (DRE ou DFC) linha a linha, devolvendo só
    as linhas do CNPJ pedido — nunca materializa o arquivo inteiro (que
    cobre todas as companhias abertas do Brasil) em memória. Compartilhada
    entre `_linhas_da_empresa` (DRE) e `_linhas_da_empresa_dfc` (DFC), que
    só diferem no padrão do nome do membro e na exceção a levantar se ele
    não existir no zip."""
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        if nome_membro not in arquivo_zip.namelist():
            raise classe_erro(
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


def _linhas_da_empresa(
    caminho_zip: Path, ano: int, tipo: str, cnpj_normalizado: str
) -> list[dict]:
    """Lê o CSV de DRE ("con" ou "ind") de dentro do zip — ver
    `_linhas_do_membro`."""
    nome_membro = f"dfp_cia_aberta_DRE_{tipo}_{ano}.csv"
    return _linhas_do_membro(
        caminho_zip, nome_membro, ano, cnpj_normalizado, ContaLucroNaoEncontrada
    )


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


def _valor_conta(linha: dict, classe_erro: type[Exception] = ContaLucroNaoEncontrada) -> float:
    """Converte VL_CONTA pra float na escala monetária correta.
    `classe_erro` decide qual exceção levantar se a escala for desconhecida
    — compartilhada entre o caminho de Lucro Líquido (padrão,
    `ContaLucroNaoEncontrada`) e o de Fluxo de Caixa (`_fcf_do_periodo`
    passa `ContaFluxoCaixaNaoEncontrada` explicitamente), pra que a
    mensagem de erro corresponda ao caminho que realmente falhou em vez de
    sempre citar "Lucro Líquido" mesmo quando o problema é numa conta da
    DFC."""
    escala = linha["ESCALA_MOEDA"]
    if escala not in FATOR_ESCALA_MOEDA_CVM:
        raise classe_erro(f"Escala monetária desconhecida: {escala!r}.")
    return float(linha["VL_CONTA"]) * FATOR_ESCALA_MOEDA_CVM[escala]


def _linhas_por_periodo(
    linhas: list[dict], ano: int, classe_erro: type[Exception]
) -> tuple[list[dict], list[dict]]:
    """Separa as linhas de uma consulta em ÚLTIMO/PENÚLTIMO — cada arquivo
    anual da CVM já traz os dois períodos por conta (ver docstring do
    módulo). Compartilhada entre `_montar_resultado` (DRE) e
    `_montar_resultado_fcf` (DFC); `classe_erro` mantém a exceção
    correspondente ao caminho que chamou quando falta 'ÚLTIMO'."""
    linhas_atual = [linha for linha in linhas if linha["ORDEM_EXERC"] == "ÚLTIMO"]
    linhas_anterior = [linha for linha in linhas if linha["ORDEM_EXERC"] == "PENÚLTIMO"]
    if not linhas_atual:
        raise classe_erro(
            f"Nenhuma linha com ORDEM_EXERC='ÚLTIMO' para o ano {ano} — "
            "formato do arquivo pode ter mudado."
        )
    return linhas_atual, linhas_anterior


def _metadados_empresa(primeira_linha: dict, tipo: str) -> dict:
    """Metadados comuns extraídos da primeira linha de qualquer consulta
    (DRE ou DFC) — cnpj/código CVM/denominação e se é a demonstração
    consolidada ou individual. Compartilhado entre `_montar_resultado` e
    `_montar_resultado_fcf`."""
    return {
        "cnpj": primeira_linha["CNPJ_CIA"],
        "cd_cvm": primeira_linha["CD_CVM"],
        "denominacao": primeira_linha["DENOM_CIA"],
        "tipo_demonstracao": "consolidado" if tipo == "con" else "individual",
    }


def _montar_resultado(ano: int, tipo: str, linhas: list[dict]) -> dict:
    linhas_atual, linhas_anterior = _linhas_por_periodo(linhas, ano, ContaLucroNaoEncontrada)

    linha_lucro_atual = _linha_lucro_liquido(linhas_atual)
    lucro_atual = _valor_conta(linha_lucro_atual, ContaLucroNaoEncontrada)

    lucro_anterior = None
    periodo_anterior_fim = None
    if linhas_anterior:
        linha_lucro_anterior = _linha_lucro_liquido(linhas_anterior)
        lucro_anterior = _valor_conta(linha_lucro_anterior, ContaLucroNaoEncontrada)
        periodo_anterior_fim = linha_lucro_anterior["DT_FIM_EXERC"]

    crescimento_percentual = None
    if lucro_anterior not in (None, 0):
        crescimento_percentual = (lucro_atual - lucro_anterior) / abs(lucro_anterior) * 100

    return {
        **_metadados_empresa(linhas[0], tipo),
        "conta_lucro_liquido": linha_lucro_atual["CD_CONTA"],
        "ano_referencia": ano,
        "periodo_atual_fim": linha_lucro_atual["DT_FIM_EXERC"],
        "lucro_liquido_atual": lucro_atual,
        "periodo_anterior_fim": periodo_anterior_fim,
        "lucro_liquido_anterior": lucro_anterior,
        "crescimento_lucro_percentual": crescimento_percentual,
    }


def _linhas_da_empresa_dfc(
    caminho_zip: Path, ano: int, metodo: str, tipo: str, cnpj_normalizado: str
) -> list[dict]:
    """Lê o CSV da DFC (Demonstração de Fluxo de Caixa) de dentro do zip —
    ver `_linhas_do_membro`. `metodo` é "MI" (indireto, a grande maioria
    das empresas) ou "MD" (direto, minoria)."""
    nome_membro = f"dfp_cia_aberta_DFC_{metodo}_{tipo}_{ano}.csv"
    return _linhas_do_membro(
        caminho_zip, nome_membro, ano, cnpj_normalizado, ContaFluxoCaixaNaoEncontrada
    )


def _linha_por_codigo(linhas_periodo: list[dict], codigo: str) -> dict:
    candidatas = [linha for linha in linhas_periodo if linha["CD_CONTA"] == codigo]
    if not candidatas:
        raise ContaFluxoCaixaNaoEncontrada(
            f"Conta {codigo!r} não encontrada na DFC — layout pode ter mudado."
        )
    return candidatas[0]


def _fcf_do_periodo(linhas_periodo: list[dict]) -> float:
    """FCF = Caixa Líquido Atividades Operacionais + Caixa Líquido
    Atividades de Investimento (ver justificativa em config.py). Como o
    de Investimento normalmente vem negativo, somar os dois já desconta
    capex e outros investimentos do caixa operacional.

    `_valor_conta` recebe `ContaFluxoCaixaNaoEncontrada` explicitamente —
    sem isso, uma escala monetária desconhecida numa conta CFO/CFI
    levantaria o erro padrão de `_valor_conta` (`ContaLucroNaoEncontrada`),
    citando "Lucro Líquido" num contexto que é de Fluxo de Caixa."""
    cfo = _valor_conta(
        _linha_por_codigo(linhas_periodo, CODIGO_CFO_CVM), ContaFluxoCaixaNaoEncontrada
    )
    cfi = _valor_conta(
        _linha_por_codigo(linhas_periodo, CODIGO_CFI_CVM), ContaFluxoCaixaNaoEncontrada
    )
    return cfo + cfi


def _montar_resultado_fcf(ano: int, tipo: str, metodo: str, linhas: list[dict]) -> dict:
    linhas_atual, linhas_anterior = _linhas_por_periodo(linhas, ano, ContaFluxoCaixaNaoEncontrada)

    fcf_atual = _fcf_do_periodo(linhas_atual)
    fcf_anterior = _fcf_do_periodo(linhas_anterior) if linhas_anterior else None

    return {
        **_metadados_empresa(linhas[0], tipo),
        "metodo_dfc": metodo,
        "ano_referencia": ano,
        "fcf_atual": fcf_atual,
        "fcf_anterior": fcf_anterior,
    }


def obter_fluxo_caixa_livre(
    cnpj: str,
    ano: int,
    usar_cache: bool = True,
    forcar_atualizacao: bool = False,
    diretorio_cache: Path = DATA_RAW_DIR,
) -> dict:
    """Busca o fluxo de caixa livre (FCF, aproximado por CFO+CFI — ver
    config.py) de uma empresa para `ano`, mais o valor do ano anterior.

    Tenta a DFC pelo método indireto (a maioria das empresas) antes do
    direto, e a demonstração consolidada antes da individual. Levanta
    `CnpjNaoEncontrado` se o CNPJ não aparecer em nenhuma combinação, ou
    `ContaFluxoCaixaNaoEncontrada` se as contas 6.01/6.02 não puderem ser
    localizadas (formato mudou).
    """
    cnpj_normalizado = _normalizar_cnpj(cnpj)
    caminho_resultado = diretorio_cache / "cvm" / f"fcf_{cnpj_normalizado}_{ano}.json"

    if usar_cache and not forcar_atualizacao and caminho_resultado.exists():
        return json.loads(caminho_resultado.read_text(encoding="utf-8"))

    caminho_zip = _baixar_zip_ano(ano, diretorio_cache, forcar_atualizacao)

    resultado = None
    for metodo in ("MI", "MD"):
        for tipo in ("con", "ind"):
            linhas = _linhas_da_empresa_dfc(caminho_zip, ano, metodo, tipo, cnpj_normalizado)
            if not linhas:
                continue
            resultado = _montar_resultado_fcf(ano, tipo, metodo, linhas)
            break
        if resultado is not None:
            break

    if resultado is None:
        raise CnpjNaoEncontrado(f"CNPJ {cnpj!r} não encontrado na DFC da CVM para {ano}.")

    if usar_cache:
        caminho_resultado.parent.mkdir(parents=True, exist_ok=True)
        caminho_resultado.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")

    return resultado


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
