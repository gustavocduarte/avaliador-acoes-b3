"""Fluxo de Caixa Descontado (FCD).

Projeta o fluxo de caixa livre (caixa das operações menos o capex mais os
juros pagos líquidos de imposto, ver `calcular_fluxo_caixa_fcd` e a
justificativa em config.py) por `config.HORIZONTE_PROJECAO_FCD_ANOS`
anos, mais uma perpetuidade (Gordon Growth), descontados pelo WACC —
resultado que é Enterprise Value (valor da empresa, dívida incluída), não
Equity Value. Convertido pra Equity Value subtraindo a dívida líquida
(Fundamentus) quando disponível, só então dividido pelo número de ações
pra chegar num valor justo por ação comparável a Graham/Bazin — ver
`calcular_valor_justo_fcd` pro caso em que a dívida líquida não está
disponível.

É "não aplicável" quando falta dado essencial pra sequer montar a conta
(FCF atual ausente na CVM, número de ações ausente no Fundamentus, WACC
calculado que não é positivo), quando o FCF do ano de referência é zero
ou negativo (perpetuar um fluxo negativo não estima valor), ou quando a
empresa é banco, seguradora ou a Itaúsa (ver
`config.SEGMENTOS_FCD_NAO_APLICAVEL` e `config.TICKERS_FCD_NAO_APLICAVEL`)
— nesses casos a metodologia (fluxo de caixa descontado pelo WACC) não tem
interpretação econômica válida: em bancos a dívida e os depósitos são a
própria operação, e seguradoras e holdings vivem de prêmios e de
dividendos de participações, não de um fluxo operacional a descontar.

Premissas de WACC/crescimento documentadas e justificadas em config.py:
- Custo de capital próprio via CAPM (Selic + Beta × prêmio de risco Brasil).
  Beta vem de `empresa.comportamento.calcular_beta` (janela de 1 ano) quando
  disponível; cai pra `BETA_PADRAO`=1,0 quando não é calculável (histórico
  curto demais, ou sem overlap suficiente com o Ibovespa) — não deixa o FCD
  inteiro ficar inaplicável só por falta de Beta real.
- Custo de capital de terceiros = Selic + spread de crédito, pós-imposto.
- Estrutura de capital derivada de Dívida Líquida/Patrimônio (Fundamentus);
  quando ausente ou não-positiva (ex: bancos), trata a empresa como não
  alavancada (WACC = custo de capital próprio) — simplificação explícita.
- Taxa de crescimento explícita: CAGR de FCF entre hoje e
  `ANOS_HISTORICO_CRESCIMENTO_FCD` anos atrás; se não for calculável
  (dado ausente ou base não-positiva), cai pro IPCA como taxa neutra.
- Taxa de crescimento na perpetuidade: IPCA, sempre travada abaixo do WACC
  por uma margem de segurança — nunca deixa o denominador da perpetuidade
  (WACC - g) chegar perto de zero.
"""

from __future__ import annotations

from avaliador_b3.config import (
    ALIQUOTA_IR_CSLL_PADRAO,
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    BETA_PADRAO,
    HORIZONTE_PROJECAO_FCD_ANOS,
    MARGEM_SEGURANCA_PERPETUIDADE_FCD,
    MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE,
    MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA,
    MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX,
    MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO,
    MOTIVO_FCD_FLUXO_NAO_POSITIVO,
    MOTIVO_FCD_HOLDING_FINANCEIRA,
    MOTIVOS_FCD_POR_SEGMENTO,
    PREMIO_RISCO_MERCADO_BRASIL,
    SEGMENTOS_FCD_NAO_APLICAVEL,
    SPREAD_CREDITO_PADRAO,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
    TICKERS_FCD_NAO_APLICAVEL,
)


def calcular_proporcao_reinvestimento_percentual(
    caixa_operacional: float, caixa_investimento: float
) -> float | None:
    """Quanto do caixa operacional foi consumido pelo caixa de
    investimento no ano usado pelo FCD — `-caixa_investimento /
    caixa_operacional × 100`. Compartilhada entre `app/main.py` (caption
    no cartão do FCD) e `screener.py` (coluna "Reinvestimento"), pra não
    duplicar a conta nem correr o risco dos dois lugares divergirem sobre
    o que "reinvestimento" significa — mesmo padrão de
    `modelos.combinado.calcular_divergencia_metodos`.

    `None` (sem proporção, não "0%") em dois casos, cada um com leitura
    própria pro chamador mostrar: caixa operacional zero ou negativo (a
    empresa não gera caixa suficiente nem pra cobrir a própria operação —
    problema mais grave que "investir demais", ver caso real VAMO3 na
    investigação de config.py) e caixa de investimento positivo (a
    empresa está desinvestindo — vendeu mais ativos do que comprou no
    ano, ver caso real ALOS3/BBSE3/ITSA4/HAPV3/MRVE3) — nos dois casos a
    razão não tem leitura útil como "proporção reinvestida".

    Ver a investigação completa (correlação de -0,79 entre essa
    proporção e o quanto o FCD diverge de Graham, em `config.py`, junto
    da definição do FCF) que motivou essa função."""
    if caixa_operacional <= 0:
        return None
    if caixa_investimento > 0:
        return None
    return -caixa_investimento / caixa_operacional * 100


MOTIVO_NAO_APLICAVEL_INSTITUICAO_FINANCEIRA = (
    "Instituição financeira: o FCD mede valor pela geração de caixa "
    "operacional descontada pelo custo de capital, mas em bancos a dívida e "
    "os depósitos são a própria operação, e o fluxo de caixa varia com a "
    "expansão do crédito, não com a geração de valor. Graham e Bazin "
    "continuam válidos."
)


def calcular_fluxo_caixa_fcd(cfo: float, capex: dict, juros_pagos: dict) -> float | None:
    """Fluxo de caixa do FCD: caixa das operações (6.01) menos o capex, mais
    os juros pagos em 6.01 já líquidos do imposto. `capex` e `juros_pagos`
    são os dicts de `ingest.cvm` (`capex_atual`/`juros_pagos_atual`). `None`
    se o capex não foi identificado: sem ele o fluxo não é calculado."""
    if capex["status"] != "identificado":
        return None
    return cfo - capex["valor"] + juros_pagos["valor"] * (1 - ALIQUOTA_IR_CSLL_PADRAO)


def montar_fluxos_fcd(resultado_cvm: dict | None) -> dict:
    """Fluxo do FCD dos dois anos (referência e base do crescimento) a partir
    do resultado de `ingest.cvm.obter_fluxo_caixa_livre_com_fallback`, mais o
    motivo de cada fluxo indisponível. As chaves são os parâmetros
    homônimos de `calcular_valor_justo_fcd`, então o chamador usa
    `**fluxos`. `None` (sem dado da CVM) devolve tudo `None`."""
    if resultado_cvm is None:
        return {
            "fcf_atual": None,
            "fcf_ha_n_anos": None,
            "motivo_sem_fcf_atual": None,
            "motivo_sem_fcf_ha_n_anos": None,
        }
    fcf_atual = calcular_fluxo_caixa_fcd(
        resultado_cvm["cfo_atual"],
        resultado_cvm["capex_atual"],
        resultado_cvm["juros_pagos_atual"],
    )
    if resultado_cvm["capex_ha_n_anos"] is None:
        fcf_ha_n_anos, motivo_base = None, MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE
    else:
        fcf_ha_n_anos = calcular_fluxo_caixa_fcd(
            resultado_cvm["cfo_ha_n_anos"],
            resultado_cvm["capex_ha_n_anos"],
            resultado_cvm["juros_pagos_ha_n_anos"],
        )
        motivo_base = None if fcf_ha_n_anos is not None else MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX
    return {
        "fcf_atual": fcf_atual,
        "fcf_ha_n_anos": fcf_ha_n_anos,
        "motivo_sem_fcf_atual": (
            None if fcf_atual is not None else MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO
        ),
        "motivo_sem_fcf_ha_n_anos": motivo_base,
    }


def _motivo_exclusao_do_fcd(segmento_setorial: str | None, ticker: str | None) -> str | None:
    """Motivo pelo qual o FCD não se aplica à empresa (por segmento ou por
    ticker), ou `None` se a exclusão não vale pra ela."""
    if segmento_setorial in SEGMENTOS_FCD_NAO_APLICAVEL:
        return MOTIVOS_FCD_POR_SEGMENTO.get(
            segmento_setorial, MOTIVO_NAO_APLICAVEL_INSTITUICAO_FINANCEIRA
        )
    if ticker in TICKERS_FCD_NAO_APLICAVEL:
        return MOTIVO_FCD_HOLDING_FINANCEIRA
    return None


def _custo_capital_proprio(selic_meta: float, beta: float) -> float:
    """CAPM: Ke = Selic + Beta × prêmio de risco de mercado (Brasil)."""
    return selic_meta + beta * PREMIO_RISCO_MERCADO_BRASIL


def _custo_capital_terceiros_pos_imposto(selic_meta: float) -> float:
    kd_pre_imposto = selic_meta + SPREAD_CREDITO_PADRAO
    return kd_pre_imposto * (1 - ALIQUOTA_IR_CSLL_PADRAO)


def _pesos_estrutura_capital(divida_liquida_sobre_patrimonio: float | None) -> tuple[float, float]:
    """Devolve (peso capital próprio, peso dívida). Quando o índice Dívida
    Líquida/Patrimônio está ausente (ex: bancos, onde o Fundamentus não
    reporta esse campo) ou não-positivo (empresa em posição de caixa
    líquido), trata a empresa como não alavancada — ver justificativa em
    config.py."""
    if divida_liquida_sobre_patrimonio is None or divida_liquida_sobre_patrimonio <= 0:
        return 1.0, 0.0
    de = divida_liquida_sobre_patrimonio
    return 1 / (1 + de), de / (1 + de)


def calcular_wacc(
    selic_meta: float,
    divida_liquida_sobre_patrimonio: float | None,
    beta: float | None = None,
) -> float:
    """WACC = peso_capital_próprio × Ke + peso_dívida × Kd_pós_imposto.

    `beta` é o Beta real da ação (ver `empresa.comportamento.calcular_beta`)
    quando disponível. Se vier None — não calculável, ver docstring do
    módulo — cai pra `BETA_PADRAO` (risco médio de mercado)."""
    beta_efetivo = beta if beta is not None else BETA_PADRAO
    peso_capital_proprio, peso_divida = _pesos_estrutura_capital(divida_liquida_sobre_patrimonio)
    ke = _custo_capital_proprio(selic_meta, beta_efetivo)
    kd_pos_imposto = _custo_capital_terceiros_pos_imposto(selic_meta)
    return peso_capital_proprio * ke + peso_divida * kd_pos_imposto


def _taxa_crescimento_explicita(fcf_atual: float, fcf_ha_n_anos: float | None) -> float | None:
    """CAGR entre `fcf_ha_n_anos` e `fcf_atual`, limitada a uma faixa de
    bom senso. Devolve None (sinal para o chamador usar um valor de
    fallback) se não for calculável — base ausente ou não-positiva, já
    que a raiz de um número negativo não existe no domínio real."""
    if fcf_ha_n_anos is None or fcf_atual <= 0 or fcf_ha_n_anos <= 0:
        return None
    taxa = (fcf_atual / fcf_ha_n_anos) ** (1 / ANOS_HISTORICO_CRESCIMENTO_FCD) - 1
    return max(TAXA_CRESCIMENTO_FCD_MINIMA, min(TAXA_CRESCIMENTO_FCD_MAXIMA, taxa))


def _taxa_perpetuidade(ipca_12m: float, wacc: float) -> float:
    """IPCA, travado a pelo menos `MARGEM_SEGURANCA_PERPETUIDADE_FCD`
    abaixo do WACC — nunca deixa o denominador da perpetuidade (WACC - g)
    chegar perto de zero, independente de qual dos dois seja maior."""
    return min(ipca_12m, wacc - MARGEM_SEGURANCA_PERPETUIDADE_FCD)


def calcular_valor_justo_fcd(
    fcf_atual: float | None,
    numero_acoes: float | None,
    selic_meta: float,
    ipca_12m: float,
    fcf_ha_n_anos: float | None = None,
    divida_liquida_sobre_patrimonio: float | None = None,
    beta: float | None = None,
    divida_liquida: float | None = None,
    segmento_setorial: str | None = None,
    ticker: str | None = None,
    motivo_sem_fcf_atual: str | None = None,
    motivo_sem_fcf_ha_n_anos: str | None = None,
) -> dict:
    """Calcula o valor justo por ação pelo Fluxo de Caixa Descontado.

    `fcf_atual`/`fcf_ha_n_anos` tipicamente vêm de
    `ingest.cvm.obter_fluxo_caixa_livre` (ano de referência e
    `ANOS_HISTORICO_CRESCIMENTO_FCD` anos antes); `numero_acoes`,
    `divida_liquida_sobre_patrimonio` e `divida_liquida` de
    `ingest.fundamentus.obter_indicadores` (o mesmo campo "Dív. Líquida"
    já usado em `empresa.valor_mercado.calcular_valor_mercado_e_firma` e
    exibido em "Saúde financeira" — não confundir com
    `divida_liquida_sobre_patrimonio`, que é a RAZÃO usada só pro peso de
    dívida no WACC); `selic_meta`/`ipca_12m` de `ingest.bcb_sgs`; `beta`
    de `empresa.comportamento.calcular_beta` (pode vir None — cai pra
    `BETA_PADRAO` dentro de `calcular_wacc`, não impede o FCD de rodar);
    `segmento_setorial` de `ingest.crosswalk_cnpj.resolver_cnpj` (campo
    "segment" do catálogo de emissores da B3 — ver justificativa completa
    do critério e do escopo em `config.SEGMENTOS_FCD_NAO_APLICAVEL`).

    Se `segmento_setorial` estiver em `config.SEGMENTOS_FCD_NAO_APLICAVEL`
    (hoje "Bancos" e "Seguradoras") ou `ticker` em
    `config.TICKERS_FCD_NAO_APLICAVEL` (hoje só ITSA4), devolve "não
    aplicável" antes de qualquer cálculo, com o motivo da exclusão.
    `segmento_setorial=None` (não resolvido) segue o cálculo normal, não
    é tratado como exclusão. Com `fcf_atual` zero ou negativo também é "não
    aplicável": o FCD só olha entradas do modelo, nunca o preço de mercado.

    O fluxo de caixa livre descontado (`valor_total`) é, por construção,
    Enterprise Value — valor da empresa como um todo, dívida incluída —
    não Equity Value (valor do patrimônio dos acionistas, que é o que
    "valor justo por ação" deveria representar, pra ser comparável a
    Graham/Bazin). Quando `divida_liquida` está disponível, ela é
    subtraída de `valor_total` antes de dividir por `numero_acoes` —
    dívida líquida negativa (empresa em posição de caixa líquido, mais
    caixa que dívida) funciona corretamente com subtração normal, sem
    caso especial, mesma convenção de `calcular_valor_mercado_e_firma`
    (`valor_firma = valor_mercado + divida_liquida`, a operação inversa).
    Quando `divida_liquida` é `None` (ausente), o FCD continua aplicável,
    só sem a dedução — `divida_liquida_deduzida=False` no retorno
    sinaliza esse caso pro chamador avisar na tela. Na prática, hoje isso
    só acontece fora do segmento "Bancos" (banco nunca chega até aqui,
    já é filtrado acima).

    Devolve um dict com `aplicavel` (bool), `valor_justo` (float ou None),
    `motivo_nao_aplicavel` (str ou None), `divida_liquida_deduzida` (bool)
    e, quando aplicável, as premissas usadas (`wacc`, `beta_utilizado`,
    `taxa_crescimento_explicita`, `taxa_crescimento_perpetuidade`) para
    transparência do cálculo.
    """
    motivo_exclusao = _motivo_exclusao_do_fcd(segmento_setorial, ticker)
    if motivo_exclusao is not None:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": motivo_exclusao,
        }

    if fcf_atual is None:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": (
                motivo_sem_fcf_atual or "Sem dado de fluxo de caixa livre da CVM para projetar."
            ),
        }

    if fcf_atual <= 0:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": MOTIVO_FCD_FLUXO_NAO_POSITIVO,
        }

    if numero_acoes is None or numero_acoes <= 0:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": (
                "Número de ações indisponível para converter o valor "
                "calculado em valor justo por ação."
            ),
        }

    beta_utilizado = beta if beta is not None else BETA_PADRAO
    wacc = calcular_wacc(selic_meta, divida_liquida_sobre_patrimonio, beta)
    if wacc <= 0:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": (
                f"WACC calculado não é positivo ({wacc:.2%}) — condições "
                "macro fora do esperado para o modelo."
            ),
        }

    taxa_crescimento = _taxa_crescimento_explicita(fcf_atual, fcf_ha_n_anos)
    motivo_crescimento_ipca = None
    if taxa_crescimento is None:
        # Sem CAGR confiável (histórico ausente ou base não-positiva):
        # assume crescimento neutro, igual à inflação, e diz por quê.
        taxa_crescimento = ipca_12m
        motivo_crescimento_ipca = (
            (motivo_sem_fcf_ha_n_anos or MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE)
            if fcf_ha_n_anos is None
            else MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA
        )

    taxa_perpetuidade = _taxa_perpetuidade(ipca_12m, wacc)

    valor_presente_explicito = 0.0
    fcf_projetado = fcf_atual
    for ano in range(1, HORIZONTE_PROJECAO_FCD_ANOS + 1):
        fcf_projetado *= 1 + taxa_crescimento
        valor_presente_explicito += fcf_projetado / (1 + wacc) ** ano

    valor_terminal = fcf_projetado * (1 + taxa_perpetuidade) / (wacc - taxa_perpetuidade)
    valor_presente_terminal = valor_terminal / (1 + wacc) ** HORIZONTE_PROJECAO_FCD_ANOS

    valor_total = valor_presente_explicito + valor_presente_terminal

    # Enterprise Value -> Equity Value: subtrai dívida líquida ANTES de
    # dividir por número de ações. Negativa (caixa líquido) soma ao valor
    # normalmente, sem caso especial — ver docstring da função.
    divida_liquida_deduzida = divida_liquida is not None
    if divida_liquida_deduzida:
        valor_total -= divida_liquida

    return {
        "aplicavel": True,
        "valor_justo": valor_total / numero_acoes,
        "motivo_nao_aplicavel": None,
        "divida_liquida_deduzida": divida_liquida_deduzida,
        "wacc": wacc,
        "beta_utilizado": beta_utilizado,
        "taxa_crescimento_explicita": taxa_crescimento,
        "taxa_crescimento_perpetuidade": taxa_perpetuidade,
        "motivo_crescimento_ipca": motivo_crescimento_ipca,
    }
