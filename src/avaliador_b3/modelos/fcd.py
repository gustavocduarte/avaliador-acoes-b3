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
  (dado ausente ou base não-positiva), cai pro IPCA como taxa neutra. Ela vale
  no ano 1 e converge linearmente para a da perpetuidade, que o ano
  `ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD` já usa (ver `_taxa_do_ano`).
- Taxa de crescimento na perpetuidade: IPCA, sempre travada abaixo do WACC
  por uma margem de segurança — nunca deixa o denominador da perpetuidade
  (WACC - g) chegar perto de zero.
"""

from __future__ import annotations

from avaliador_b3.config import (
    ALIQUOTA_IR_CSLL_PADRAO,
    ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD,
    ANOS_HISTORICO_CRESCIMENTO_FCD,
    BETA_PADRAO,
    HORIZONTE_PROJECAO_FCD_ANOS,
    MARGEM_SEGURANCA_PERPETUIDADE_FCD,
    MOTIVO_ACOES_EM_CIRCULACAO_INDISPONIVEL,
    MOTIVO_ARRENDAMENTO_INDISPONIVEL,
    MOTIVO_BALANCO_NAO_LIDO,
    MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE,
    MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA,
    MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX,
    MOTIVO_DIVIDA_LIQUIDA_INDISPONIVEL,
    MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO,
    MOTIVO_FCD_FLUXO_NAO_POSITIVO,
    MOTIVO_FCD_HOLDING_FINANCEIRA,
    MOTIVO_PATRIMONIO_TOTAL_INDISPONIVEL,
    MOTIVO_PATRIMONIO_TOTAL_NAO_POSITIVO,
    MOTIVO_RECEITA_NAO_LIDA,
    MOTIVO_RECEITA_NAO_POSITIVA,
    MOTIVOS_FCD_POR_SEGMENTO,
    PREMIO_RISCO_MERCADO_BRASIL,
    SEGMENTOS_FCD_NAO_APLICAVEL,
    SPREAD_CREDITO_PADRAO,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
    TICKERS_FCD_NAO_APLICAVEL,
)


def calcular_proporcao_capex_caixa_operacional_percentual(
    caixa_operacional: float, capex: dict
) -> float | None:
    """Quanto do caixa operacional foi para o capex no ano usado pelo FCD:
    `capex ÷ caixa operacional × 100`, com o mesmo capex do fluxo do FCD
    (`capex_atual` de `ingest.cvm`, só imobilizado e intangível). `None` se o
    capex não foi identificado ou se o caixa operacional é zero ou negativo."""
    if capex["status"] != "identificado" or caixa_operacional <= 0:
        return None
    return capex["valor"] / caixa_operacional * 100


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


def _receitas_do_fcd(resultado_cvm: dict) -> dict:
    """Receita líquida do ano de referência e do ano-base (as chaves são parâmetros de
    `calcular_valor_justo_fcd`) e o motivo de uma delas faltar."""
    atual = resultado_cvm.get("receita_atual") or {}
    base = resultado_cvm.get("receita_ha_n_anos") or {}
    motivo = None
    if atual.get("valor") is None:
        motivo = atual.get("motivo") or MOTIVO_RECEITA_NAO_LIDA
    elif base.get("valor") is None:
        motivo = base.get("motivo") or MOTIVO_RECEITA_NAO_LIDA
    return {
        "receita_atual": atual.get("valor"),
        "receita_ha_n_anos": base.get("valor"),
        "motivo_sem_receita": motivo,
    }


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
            "receita_atual": None,
            "receita_ha_n_anos": None,
            "motivo_sem_receita": None,
        }
    fcf_atual = calcular_fluxo_caixa_fcd(
        resultado_cvm["cfo_atual"],
        resultado_cvm["capex_atual"],
        resultado_cvm["juros_pagos_atual"],
    )
    motivo_base: str | None
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
        **_receitas_do_fcd(resultado_cvm),
    }


def montar_ajustes_balanco(leitura_balanco: dict | None) -> dict:
    """Ajustes do valor do acionista a partir da leitura única do balanço da
    CVM (`ingest.balanco_cvm.obter_leitura_balanco`), nos nomes dos parâmetros
    de `calcular_valor_justo_fcd` (o chamador usa `**ajustes`). Leitura
    indisponível (ou `None`, não lida) mantém o cálculo sem o ajuste e traz o
    motivo."""
    # As ações em circulação dependem só da composição do capital, não do balanço.
    acoes = leitura_balanco.get("acoes_em_circulacao") if leitura_balanco else None
    motivo_acoes: str | None
    if leitura_balanco is None:
        motivo_acoes = MOTIVO_BALANCO_NAO_LIDO
    else:
        motivo_acoes = leitura_balanco.get("motivo_acoes") or leitura_balanco.get("motivo")
    ajustes_acoes = {
        "acoes_em_circulacao": acoes,
        "motivo_sem_acoes_em_circulacao": (
            None if acoes is not None else (motivo_acoes or MOTIVO_ACOES_EM_CIRCULACAO_INDISPONIVEL)
        ),
    }
    if leitura_balanco is None:
        motivo = MOTIVO_BALANCO_NAO_LIDO
    elif not leitura_balanco["disponivel"]:
        motivo = leitura_balanco["motivo"]
    else:
        patrimonio_total = leitura_balanco.get("patrimonio_liquido_total")
        return {
            **ajustes_acoes,
            "nao_controladores": leitura_balanco["nao_controladores"],
            "motivo_sem_nao_controladores": None,
            "arrendamento_fora_da_divida": leitura_balanco.get("arrendamento_fora_da_divida"),
            "motivo_sem_arrendamento": (
                None
                if leitura_balanco.get("arrendamento_fora_da_divida") is not None
                else MOTIVO_ARRENDAMENTO_INDISPONIVEL
            ),
            "patrimonio_liquido_total": patrimonio_total,
            "motivo_sem_patrimonio_total": (
                None if patrimonio_total is not None else MOTIVO_PATRIMONIO_TOTAL_INDISPONIVEL
            ),
        }
    return {
        **ajustes_acoes,
        "nao_controladores": None,
        "motivo_sem_nao_controladores": motivo,
        "arrendamento_fora_da_divida": None,
        "motivo_sem_arrendamento": motivo,
        "patrimonio_liquido_total": None,
        "motivo_sem_patrimonio_total": motivo,
    }


def _razao_divida_patrimonio_para_pesos(
    divida_liquida: float | None,
    patrimonio_liquido_total: float | None,
    divida_liquida_sobre_patrimonio: float | None,
    motivo_sem_patrimonio_total: str | None,
) -> tuple[float | None, str | None]:
    """Razão dívida líquida ÷ patrimônio para os pesos do WACC, e o motivo de ter
    ficado na razão do Fundamentus. A dívida e o fluxo são consolidados, então o
    patrimônio é o total (controladores + não controladores); o do Fundamentus é
    só o dos controladores e inflaria o peso da dívida. Sem patrimônio total
    positivo ou sem dívida líquida, vale a razão do Fundamentus."""
    if patrimonio_liquido_total is None:
        motivo = motivo_sem_patrimonio_total or MOTIVO_PATRIMONIO_TOTAL_INDISPONIVEL
    elif patrimonio_liquido_total <= 0:
        motivo = MOTIVO_PATRIMONIO_TOTAL_NAO_POSITIVO
    elif divida_liquida is None:
        motivo = MOTIVO_DIVIDA_LIQUIDA_INDISPONIVEL
    else:
        return divida_liquida / patrimonio_liquido_total, None
    return divida_liquida_sobre_patrimonio, motivo


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


def _taxa_crescimento_receita(
    receita_atual: float | None, receita_ha_n_anos: float | None
) -> float | None:
    """CAGR da receita líquida entre as duas pontas do crescimento do fluxo, ou `None` se
    alguma ponta faltar ou não for positiva."""
    if receita_atual is None or receita_ha_n_anos is None:
        return None
    if receita_atual <= 0 or receita_ha_n_anos <= 0:
        return None
    return (receita_atual / receita_ha_n_anos) ** (1 / ANOS_HISTORICO_CRESCIMENTO_FCD) - 1


def _taxa_do_ano(ano: int, taxa_crescimento: float, taxa_perpetuidade: float) -> float:
    """Crescimento do `ano` (1 = primeiro ano projetado): começa em
    `taxa_crescimento` e converge linearmente para `taxa_perpetuidade` no ano
    `ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD`, sem salto até o valor terminal."""
    passos = max(1, ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD - 1)
    fracao = min(1.0, (ano - 1) / passos)
    return taxa_crescimento + (taxa_perpetuidade - taxa_crescimento) * fracao


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
    nao_controladores: float | None = None,
    motivo_sem_nao_controladores: str | None = None,
    patrimonio_liquido_total: float | None = None,
    motivo_sem_patrimonio_total: str | None = None,
    arrendamento_fora_da_divida: float | None = None,
    motivo_sem_arrendamento: str | None = None,
    acoes_em_circulacao: float | None = None,
    motivo_sem_acoes_em_circulacao: str | None = None,
    receita_atual: float | None = None,
    receita_ha_n_anos: float | None = None,
    motivo_sem_receita: str | None = None,
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
    A participação dos não controladores (`nao_controladores`, valor contábil
    do balanço consolidado) também sai do valor da empresa: o fluxo é
    consolidado e inclui a parte dos sócios minoritários das controladas.
    `None` mantém o cálculo sem esse desconto (`motivo_sem_nao_controladores`
    diz por quê). O resultado pode ser negativo e não é limitado a zero.
    O valor por ação usa `acoes_em_circulacao` (integralizado menos tesouraria, da
    CVM, na base da cotação) no lugar de `numero_acoes` quando disponível; sem
    ele, vale o número do Fundamentus e `motivo_sem_acoes_em_circulacao` diz por
    quê.
    O passivo de arrendamento que ficou fora da dívida do Fundamentus
    (`arrendamento_fora_da_divida`) é somado à dívida líquida só na dedução do
    valor do acionista; os pesos do WACC seguem sem ele, enquanto forem pesos
    contábeis (mais dívida contábil baixaria o WACC e empurraria o valor para
    cima). Sem ele (ou sem dívida líquida) o cálculo segue sem a dedução e
    `motivo_sem_arrendamento` diz por quê.
    Os pesos do WACC usam dívida líquida ÷ `patrimonio_liquido_total` (patrimônio
    dos controladores mais os não controladores, do balanço consolidado). Sem ele
    (ou com patrimônio não positivo), vale `divida_liquida_sobre_patrimonio` do
    Fundamentus e o motivo vai em `motivo_sem_patrimonio_total`.
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

    acoes_utilizadas = numero_acoes
    usar_circulacao = False
    if acoes_em_circulacao is not None and acoes_em_circulacao > 0:
        acoes_utilizadas, usar_circulacao = acoes_em_circulacao, True

    beta_utilizado = beta if beta is not None else BETA_PADRAO
    arrendamento_deduzido = arrendamento_fora_da_divida is not None and divida_liquida is not None
    razao_pesos, motivo_sem_patrimonio_total = _razao_divida_patrimonio_para_pesos(
        divida_liquida,
        patrimonio_liquido_total,
        divida_liquida_sobre_patrimonio,
        motivo_sem_patrimonio_total,
    )
    wacc = calcular_wacc(selic_meta, razao_pesos, beta)
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
    taxa_receita = None
    limitado_pela_receita = False
    motivo_sem_limite_da_receita = None
    if taxa_crescimento is not None:
        # O fluxo não cresce, por 5 anos, mais que a receita (margem constante), dentro da
        # faixa externa; sem receita utilizável vale o crescimento do fluxo.
        taxa_receita = _taxa_crescimento_receita(receita_atual, receita_ha_n_anos)
        if taxa_receita is None:
            tem_as_duas = receita_atual is not None and receita_ha_n_anos is not None
            motivo_sem_limite_da_receita = (
                MOTIVO_RECEITA_NAO_POSITIVA
                if tem_as_duas
                else (motivo_sem_receita or MOTIVO_RECEITA_NAO_LIDA)
            )
        elif taxa_receita < taxa_crescimento:
            taxa_crescimento = max(
                TAXA_CRESCIMENTO_FCD_MINIMA, min(TAXA_CRESCIMENTO_FCD_MAXIMA, taxa_receita)
            )
            limitado_pela_receita = True
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
        fcf_projetado *= 1 + _taxa_do_ano(ano, taxa_crescimento, taxa_perpetuidade)
        valor_presente_explicito += fcf_projetado / (1 + wacc) ** ano

    valor_terminal = fcf_projetado * (1 + taxa_perpetuidade) / (wacc - taxa_perpetuidade)
    valor_presente_terminal = valor_terminal / (1 + wacc) ** HORIZONTE_PROJECAO_FCD_ANOS

    valor_total = valor_presente_explicito + valor_presente_terminal

    # Enterprise Value -> Equity Value: subtrai dívida líquida ANTES de
    # dividir por número de ações. Negativa (caixa líquido) soma ao valor
    # normalmente, sem caso especial — ver docstring da função.
    divida_liquida_deduzida = divida_liquida is not None
    if divida_liquida is not None:
        valor_total -= divida_liquida
    if arrendamento_fora_da_divida is not None and arrendamento_deduzido:
        valor_total -= arrendamento_fora_da_divida
    nao_controladores_deduzidos = nao_controladores is not None
    if nao_controladores is not None:
        valor_total -= nao_controladores

    return {
        "aplicavel": True,
        "valor_justo": valor_total / acoes_utilizadas,
        "motivo_nao_aplicavel": None,
        "divida_liquida_deduzida": divida_liquida_deduzida,
        "acoes_em_circulacao_utilizadas": usar_circulacao,
        "motivo_sem_acoes_em_circulacao": (
            None
            if usar_circulacao
            else (motivo_sem_acoes_em_circulacao or MOTIVO_ACOES_EM_CIRCULACAO_INDISPONIVEL)
        ),
        "arrendamento_deduzido": arrendamento_deduzido,
        "motivo_sem_arrendamento": (
            None
            if arrendamento_deduzido
            else motivo_sem_arrendamento
            or (
                MOTIVO_DIVIDA_LIQUIDA_INDISPONIVEL
                if arrendamento_fora_da_divida is not None
                else None
            )
        ),
        "nao_controladores_deduzidos": nao_controladores_deduzidos,
        "motivo_sem_nao_controladores": (
            None if nao_controladores_deduzidos else motivo_sem_nao_controladores
        ),
        "wacc": wacc,
        "divida_liquida_sobre_patrimonio_utilizada": razao_pesos,
        "motivo_sem_patrimonio_total": motivo_sem_patrimonio_total,
        "beta_utilizado": beta_utilizado,
        "taxa_crescimento_explicita": taxa_crescimento,
        "taxa_crescimento_perpetuidade": taxa_perpetuidade,
        "motivo_crescimento_ipca": motivo_crescimento_ipca,
        "taxa_crescimento_receita": taxa_receita,
        "crescimento_limitado_pela_receita": limitado_pela_receita,
        "motivo_sem_limite_da_receita": motivo_sem_limite_da_receita,
    }
