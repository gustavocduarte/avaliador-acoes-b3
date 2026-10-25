"""Formatadores de números, datas e textos em português do Brasil (sem Streamlit)."""

from datetime import datetime

import pandas as pd

from avaliador_b3.config import (
    CORRECOES_EXIBICAO_SEGMENTO_SETORIAL,
    LIMITE_SINAL_INDICADOR,
    NOMES_METODOS,
    OPCAO_TODOS_OS_SETORES,
    POTENCIAL_MINIMO_FILTRO_DESLIGADO,
    TEXTO_ACAO_SINGULAR,
    TEXTO_ACOES_DO_SETOR,
    TEXTO_ACOES_PLURAL,
    TEXTO_FILTRO_SEM_FILTRO,
    TEXTO_SEM_DADO_NA_TABELA,
)


def _rotulo_segmento_setorial(segmento: str | None) -> str | None:
    """Texto do segmento setorial para exibir; o dado e o agrupamento usam o original."""
    return CORRECOES_EXIBICAO_SEGMENTO_SETORIAL.get(segmento, segmento) if segmento else segmento


def _pt_br(texto: str) -> str:
    """Converte um texto já formatado no padrão americano (ponto decimal,
    vírgula de milhar) pra convenção brasileira (vírgula decimal, ponto de
    milhar) — troca em três passos com um placeholder intermediário pra
    "," e "." não se pisarem (ex: "1,234.56" -> "1_234.56" -> "1_234,56"
    -> "1.234,56"). Não depende de locale de sistema/navegador (idem
    `graficos.ticks_mensais_pt_br` pros meses do eixo dos gráficos) —
    Python/JS não garantem qual locale está instalado em produção."""
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt(valor: float | None, template: str = "{:.2f}") -> str:
    """Formata um número, na convenção brasileira (vírgula decimal), ou
    "N/D" se ausente — indicador individual faltando (ex: banco sem Dív
    Líq/Patrim no Fundamentus) não deve quebrar a tela nem virar um "None"
    cru na tela. `pd.isna` (não `is None`) porque também roda sobre
    valores vindos direto de coluna de DataFrame/CSV (tabelas com
    NumberColumn convertidas pra texto) — lá, ausente é NaN, não None."""
    return _pt_br(template.format(valor)) if not pd.isna(valor) else "N/D"


def _fmt_percentual(valor: float | None, casas: int = 1) -> str:
    """Formata um percentual na convenção brasileira (vírgula decimal,
    ponto de milhar acima de 1.000%) — usado pros deltas de upside dos
    cartões de Valor Justo e pelas colunas de potencial; não passa por
    `_fmt` porque não é só "número + template fixo" (delta é opcional/
    `None`, o potencial já vem multiplicado por 100 antes de chamar).
    "N/D" se ausente (`pd.isna`, ver `_fmt`)."""
    if pd.isna(valor):
        return "N/D"
    return _pt_br(f"{valor:,.{casas}f}%")


def _fmt_potencial(valor: float | None) -> str:
    """Potencial com sinal explícito ("+13,5%", "-21,0%"), como no cartão do topo."""
    texto = _fmt_percentual(valor)
    if valor is None or pd.isna(valor) or valor <= LIMITE_SINAL_INDICADOR:
        return texto
    return f"+{texto}"


def _nomes_dos_metodos(metodos: list[str]) -> str:
    """Nomes dos métodos como aparecem na tela ("Graham, Bazin, FCD"), a partir dos
    identificadores em minúsculas (`resultado_combinado["metodos_utilizados"]`)."""
    return ", ".join(NOMES_METODOS.get(metodo, metodo) for metodo in metodos)


def _nomes_dos_metodos_do_csv(valor: str) -> str:
    """O mesmo para a célula do CSV do screener, onde os métodos vêm separados por vírgula."""
    return _nomes_dos_metodos([m for m in valor.split(",") if m])


def _fmt_bilhoes_ou_traco(valor: float | None) -> str:
    """`_fmt_bilhoes`, mas com "—" (e não "N/D") quando o valor não existe."""
    return "—" if valor is None or pd.isna(valor) else _fmt_bilhoes(valor)


def _lista_em_texto(itens: list[str]) -> str:
    """ "A", "A e B" ou "A, B e C"."""
    if len(itens) <= 1:
        return "".join(itens)
    return f"{', '.join(itens[:-1])} e {itens[-1]}"


def _fmt_bilhoes(valor: float | None) -> str:
    """Formata um valor monetário — Valor de Mercado/Firma, Dívida Líquida
    ("Saúde financeira"), e os totais da carteira ("Total da carteira") —
    abreviando a partir de R$ 1 milhão (em módulo, então um valor negativo
    grande — ex: dívida líquida em posição de caixa líquido — também abrevia
    com o sinal preservado): "X,X bi" a partir de R$ 1 bilhão, "X,X mi" de
    R$ 1 milhão até ali. Abaixo de R$ 1 milhão mostra o valor completo,
    formatado por extenso ("R$ X.XXX,XX", convenção brasileira de milhar/
    decimal) — não faz sentido abreviar R$ 1.000 pra "R$ 0,0 mi". "N/D" se
    ausente.

    Sem essa abreviação (ou com o piso baixo demais), valores grandes seriam
    truncados com reticências pelo st.metric dentro das colunas estreitas de 4
    do projeto (ex: "R$ 625,1..." em "Saúde financeira"). "N/D" se ausente
    (`pd.isna`, ver `_fmt`)."""
    if valor is None or pd.isna(valor):
        return "N/D"
    if abs(valor) >= 1e9:
        return _pt_br(f"R$ {valor / 1e9:,.1f} bi")
    if abs(valor) >= 1e6:
        return _pt_br(f"R$ {valor / 1e6:,.1f} mi")
    return _pt_br(f"R$ {valor:,.2f}")


def _fmt_bilhoes_md(valor: float | None) -> str:
    """`_fmt_bilhoes` com o "$" escapado (`\\$`) — pra uso dentro de
    `st.caption`/`st.markdown`, nunca em `st.metric` (que exibe o valor
    cru, sem markdown — a barra invertida apareceria literalmente na
    tela). Sem isso, DUAS chamadas de `_fmt_bilhoes` na mesma caption
    (ex: "de R$ X a R$ Y") criam um par de "$" que o Streamlit interpreta
    como abre/fecha de fórmula LaTeX: o
    trecho entre os dois cifrões virava matemática renderizada, cortando
    o texto ("R" de um lado, o valor seguinte do outro). Escapar os dois
    "$" resolve sem precisar reescrever o texto pra evitar o padrão."""
    return _fmt_bilhoes(valor).replace("$", "\\$")


def _fmt_data(valor: pd.Timestamp | str | None, template: str = "%d/%m/%Y") -> str:
    """Formata uma data (Timestamp do pandas, vindo direto da coluna
    `data` dos DataFrames de preço, ou string ISO "aaaa-mm-dd", vinda de
    `data_balanco_fundamentus`) no padrão brasileiro, ou "N/D" se ausente
    — mesmo padrão de `_fmt` pra dado faltante. Usado só no bloco "Datas
    de referência dos dados usados" da seção Valor Justo. `template`
    customizável pro caso do IPCA, mensal — só faz sentido mostrar mês/
    ano, não um dia exato que a série não tem."""
    if valor is None or pd.isna(valor):
        return "N/D"
    if isinstance(valor, str):
        valor = datetime.strptime(valor, "%Y-%m-%d")
    return pd.Timestamp(valor).strftime(template)


def _acoes_por_extenso(quantidade: int, setor: str) -> str:
    texto = (
        TEXTO_ACAO_SINGULAR if quantidade == 1 else TEXTO_ACOES_PLURAL.format(quantidade=quantidade)
    )
    if setor == OPCAO_TODOS_OS_SETORES:
        return texto
    return TEXTO_ACOES_DO_SETOR.format(acoes=texto, setor=setor)


def _texto_potencial_minimo(valor: int) -> str:
    """Valor do slider do potencial mínimo; na posição que desliga o filtro, "Sem filtro"."""
    if valor == POTENCIAL_MINIMO_FILTRO_DESLIGADO:
        return TEXTO_FILTRO_SEM_FILTRO
    return f"{valor}%"


def _percentual_ou_traco(valor: float) -> str:
    return TEXTO_SEM_DADO_NA_TABELA if pd.isna(valor) else f"{valor:.0f}%"


def _fmt_quantidade(quantidade: int) -> str:
    return f"{quantidade:,}".replace(",", ".")
