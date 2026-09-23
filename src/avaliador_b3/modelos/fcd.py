"""Fluxo de Caixa Descontado (FCD).

Projeta o fluxo de caixa livre (FCF, ver `ingest.cvm.obter_fluxo_caixa_livre`
e a justificativa em config.py) por `config.HORIZONTE_PROJECAO_FCD_ANOS`
anos, mais uma perpetuidade (Gordon Growth), descontados pelo WACC —
resultado que é Enterprise Value (valor da empresa, dívida incluída), não
Equity Value. Convertido pra Equity Value subtraindo a dívida líquida
(Fundamentus) quando disponível, só então dividido pelo número de ações
pra chegar num valor justo por ação comparável a Graham/Bazin — ver
`calcular_valor_justo_fcd` pro caso em que a dívida líquida não está
disponível.

Diferente de Graham/Bazin, o FCD é pensado pra ser "quase sempre
aplicável" — inclusive pra empresa com prejuízo/FCF negativo atual, que só
faz o valor calculado sair baixo ou negativo (um resultado válido, não um
erro). Só é "não aplicável" quando falta dado essencial pra sequer montar
a conta: FCF atual ausente na CVM, número de ações ausente no Fundamentus,
ou um WACC calculado que não é positivo (cenário macro fora do esperado
pro modelo).

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
    PREMIO_RISCO_MERCADO_BRASIL,
    SPREAD_CREDITO_PADRAO,
    TAXA_CRESCIMENTO_FCD_MAXIMA,
    TAXA_CRESCIMENTO_FCD_MINIMA,
)


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
    `BETA_PADRAO` dentro de `calcular_wacc`, não impede o FCD de rodar).

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
    Quando `divida_liquida` é `None` (ausente — mesmo campo opcional que
    falta pra bancos, ver `config.CAMPOS_FUNDAMENTUS_OPCIONAIS`), o FCD
    continua aplicável, só sem a dedução — `divida_liquida_deduzida=False`
    no retorno sinaliza esse caso pro chamador avisar na tela.

    Devolve um dict com `aplicavel` (bool), `valor_justo` (float ou None),
    `motivo_nao_aplicavel` (str ou None), `divida_liquida_deduzida` (bool)
    e, quando aplicável, as premissas usadas (`wacc`, `beta_utilizado`,
    `taxa_crescimento_explicita`, `taxa_crescimento_perpetuidade`) para
    transparência do cálculo.
    """
    if fcf_atual is None:
        return {
            "aplicavel": False,
            "valor_justo": None,
            "motivo_nao_aplicavel": "Sem dado de fluxo de caixa livre da CVM para projetar.",
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
    if taxa_crescimento is None:
        # Sem CAGR confiável (histórico ausente ou base não-positiva):
        # assume crescimento neutro, igual à inflação.
        taxa_crescimento = ipca_12m

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
    }
