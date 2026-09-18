"""Constantes do projeto. Toda constante aqui deve citar a fonte que a valida."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DATA_CACHE_DIR = ROOT_DIR / "data" / "cache"

# Códigos de série do SGS (Sistema Gerenciador de Séries Temporais) do Banco
# Central do Brasil. Confirmados em 2026-09-14 consultando diretamente
# https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados
# e o catálogo em https://dadosabertos.bcb.gov.br/.
SERIES_BCB_SGS = {
    "selic_diaria": 11,  # Taxa Selic diária (% a.d.), série "Taxa de juros - Selic"
    "selic_meta": 432,  # Meta Selic definida pelo Copom (% a.a.)
    "ipca_mensal": 433,  # IPCA, variação mensal (%)
    "cambio_usd_venda": 1,  # Câmbio livre - dólar americano (venda), diário - PTAX
    "m2_saldo": 27810,  # Meios de pagamento amplos - M2 (saldo em final de período)
}

# Arquivos do índice GPR (Geopolitical Risk Index, Caldara & Iacoviello).
# Confirmados em 2026-09-14 em https://www.matteoiacoviello.com/gpr.htm —
# links reais extraídos do HTML da página, resposta HTTP 200 com
# Content-Type: application/vnd.ms-excel para ambos.
URLS_GPR = {
    "mensal": "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls",
    "diaria": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
}

# Preço de ação via yfinance (ticker B3 + sufixo ".SA", ex: PETR4.SA).
# Confirmado em 2026-09-14 com yfinance 1.7.0 contra PETR4.SA/VALE3.SA reais.
# Diferente dos outros adapters, o cache de preço usa TTL curto: o dado já
# vem com delay de ~15 min do próprio Yahoo, então cachear por muito tempo
# só atrasaria mais o preço exibido sem necessidade.
SUFIXO_TICKER_B3 = ".SA"
TTL_CACHE_PRECOS_SEGUNDOS = 5 * 60

# Delay entre requisições reais ao yfinance (não aplicado em cache hit) —
# mesmo raciocínio do DELAY_FUNDAMENTUS_SEGUNDOS. O screener bate no
# yfinance várias vezes por ação (histórico em 2 janelas + dividendos) ×
# ~76 ações do Ibovespa = centenas de requisições em sequência. yfinance é
# uma API não-oficial sem limite de taxa documentado (ao contrário do
# BCB/CVM, fontes governamentais estáveis) mas conhecida por limitar
# agressivamente rajadas de requisições — 1,5s (igual ao Fundamentus,
# decisão de 2026-09-14) é uma margem de segurança conservadora, não uma
# cifra pesquisada numa fonte externa.
DELAY_PRECOS_SEGUNDOS = 1.5

# Índice Ibovespa via yfinance — confirmado em 2026-09-14 que "^BVSP" (sem
# sufixo ".SA", diferente de uma ação B3) devolve histórico real com
# Close/Volume. Usado pro cálculo de Beta (bloco de comportamento da ação)
# e, futuramente, pra sobreposição no gráfico de preço.
TICKER_IBOVESPA = "^BVSP"

# Janelas de histórico pro bloco de "comportamento da ação" — duas
# janelas diferentes de propósito, não uma reaproveitada pra tudo:
#
# - Volume médio e volatilidade são métricas de curto prazo — 3 meses é
#   suficiente e mantém a busca rápida.
# - Beta tradicionalmente usa uma janela bem mais longa (6 meses a alguns
#   anos de retorno diário/semanal) — 3 meses de retorno diário (~60
#   observações) é amostra pequena demais pra uma estimativa de
#   covariância estável, fica ruidosa. Usamos 1 ano (~252 observações)
#   como meio-termo pragmático — não é uma convenção de mercado pesquisada
#   numa fonte externa (ao contrário do prêmio de risco do WACC), é só uma
#   escolha razoável de engenharia.
#
#   IMPORTANTE: esse mesmo Beta (empresa.comportamento.calcular_beta) é
#   candidato natural a substituir BETA_PADRAO=1,0 no FCD (modelos/fcd.py)
#   no futuro. Quando isso acontecer, reconsiderar se PERIODO_BETA
#   continua adequado pra esse uso — FCD é uma projeção de longo prazo,
#   pode ser que valha uma janela ainda mais longa que a usada aqui pro
#   dashboard.
PERIODO_HISTORICO_COMPORTAMENTO = "3mo"
PERIODO_BETA = "1y"

# Período separado só pro card "Preço atual" (2026-09-16): investigando uma
# discrepância real (PETR4 mostrando R$ 48,92 no nosso card contra R$ 50,43
# ao vivo no widget do TradingView, ~3% de diferença batendo com a alta
# intradiária do dia), confirmamos que o endpoint de histórico DIÁRIO do
# yfinance (period="3mo"/"5d", usado em PERIODO_HISTORICO_COMPORTAMENTO)
# atrasa um pregão inteiro — não só o candle do dia ainda em aberto, mesmo
# o fechamento do dia anterior, já encerrado, pode estar ausente. Testado
# diretamente contra o yfinance: period="5d" parou em 2026-09-14 (uma
# segunda-feira), enquanto period="1d" já trazia o fechamento de
# 2026-09-15 (R$ 50,43, batendo com o TradingView). "Preço atual" passou a
# usar esse período separado; volume médio/volatilidade (mesmo bloco de
# "Comportamento da ação") continuam em PERIODO_HISTORICO_COMPORTAMENTO —
# o atraso de um pregão é um problema real pro preço mostrado como "atual"
# na tela, mas irrelevante pra uma métrica de janela de 3 meses.
PERIODO_PRECO_ATUAL = "1d"

# Dividendos via yfinance (`Ticker.dividends`) — mesma fonte de preço,
# confirmado em 2026-09-14 que já traz o histórico completo (ex: PETR4 tem
# registros desde 2005). Diferente do preço, dividendo é declarado poucas
# vezes por ano, então o cache pode ter TTL bem mais longo.
TTL_CACHE_DIVIDENDOS_SEGUNDOS = 24 * 60 * 60

# Universo de "ações principais" (carteira teórica do Ibovespa) e segmento
# de listagem. Confirmado em 2026-09-14 chamando diretamente:
#   GET https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{params_base64}
# com params_base64 = base64(json.dumps({"language":"pt-br","pageNumber":N,
# "pageSize":P,"index":"IBOV","segment":"1"})). API não-documentada da B3,
# usada por vários projetos open-source da comunidade — pode mudar sem
# aviso. Retornou os 76 ativos do Ibovespa numa única página (pageSize=120).
#
# O campo "type" de cada resultado (ex: "ON      NM", "PN  EJ  N1", "UNT")
# traz o segmento de listagem como último token — checado contra as 13
# combinações reais observadas nos 76 ativos do índice nessa data.
URL_B3_PORTFOLIO_DIA = (
    "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{parametros_base64}"
)

SEGMENTOS_LISTAGEM_B3 = {
    "NM": "Novo Mercado",
    "N2": "Nível 2",
    "N1": "Nível 1",
}
SEGMENTO_LISTAGEM_PADRAO = "Tradicional"

# Fundamentus (fundamentus.com.br) — sem API oficial, via scraping.
# Confirmado em 2026-09-14:
#   - o site bloqueia requisições sem User-Agent de navegador (HTTP 403 sem
#     User-Agent, 200 com um realista);
#   - a página é servida em ISO-8859-1, não UTF-8 (Content-Type: text/html;
#     charset=iso-8859-1) — decodificar como UTF-8 corrompe os acentos
#     silenciosamente, sem erro;
#   - cada indicador é um par <td class="label"><span class="txt">Rótulo
#     </span></td> seguido do <td> irmão com o valor.
#
# A página NÃO tem "Dívida Líquida/EBITDA" nem crescimento de lucro. Só tem
# "Dív Líq / Patrim" (dívida líquida/patrimônio líquido — índice de
# alavancagem diferente) e "Cres. Rec (5a)" (crescimento de receita em 5
# anos, sem equivalente de lucro). Decisão alinhada com o usuário: usar
# Dív Líq/Patrim como está, sem fingir que é a mesma coisa que Dív
# Líq/EBITDA, e deixar crescimento de lucro pendente para outra fonte
# (ex: CVM) no futuro.
URL_FUNDAMENTUS_DETALHES = "https://www.fundamentus.com.br/detalhes.php"
CABECALHOS_FUNDAMENTUS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}
DELAY_FUNDAMENTUS_SEGUNDOS = 1.5

CAMPOS_FUNDAMENTUS = {
    "ROE": "roe_percentual",
    "Marg. Líquida": "margem_liquida_percentual",
    "LPA": "lpa",
    "VPA": "vpa",
    "Liquidez Corr": "liquidez_corrente",
    "Dív Líq / Patrim": "divida_liquida_sobre_patrimonio",
    "Cres. Rec (5a)": "crescimento_receita_5a_percentual",
    # Adicionado para o FCD: converte valor total (firma/patrimônio) em
    # valor justo por ação. Confirmado presente na página de PETR4/VALE3/
    # ITUB4 em 2026-09-14.
    "Nro. Ações": "numero_acoes",
    # Adicionado pra Valor de Mercado/Valor de Firma (junto com "Nro.
    # Ações" acima e "Dív. Líquida" em CAMPOS_FUNDAMENTUS_OPCIONAIS
    # abaixo). Confirmado presente tanto em empresa não-financeira
    # (PETR4) quanto banco (ITUB4) em 2026-09-17 — diferente de "Dív.
    # Líquida", que só existe pra não-financeiras.
    "Patrim. Líq": "patrimonio_liquido",
}

# Campos que podem estar totalmente AUSENTES da página do Fundamentus pra
# certos tipos de empresa — diferente dos campos de CAMPOS_FUNDAMENTUS
# acima (sempre presentes como rótulo na página; só o VALOR vira "-"
# quando não aplicável, ex: "Dív Líq / Patrim" pra banco). "Dív. Líquida"
# simplesmente não aparece como rótulo na página de bancos — confirmado
# contra ITUB4 real em 2026-09-17 (nem o <td class="label"> existe).
# Exigir esse campo em CAMPOS_FUNDAMENTUS quebraria TODA busca de
# indicadores de banco com EstruturaPaginaMudou, por isso um dict
# separado — ausência vira None (indicador opcional), não erro.
CAMPOS_FUNDAMENTUS_OPCIONAIS = {
    "Dív. Líquida": "divida_liquida",
}

# CVM (Comissão de Valores Mobiliários), Dados Abertos — Demonstrações
# Financeiras Padronizadas (DFP), anuais. Confirmado em 2026-09-14:
#   GET https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip
# Cada zip anual traz vários CSVs (";" separado, ISO-8859-1), um por tipo de
# demonstração — usamos só a DRE (Demonstração do Resultado), em duas
# versões: "_con" (consolidado, grupo econômico) e "_ind" (individual, só
# a controladora). Cada arquivo já traz DOIS períodos por conta (coluna
# ORDEM_EXERC = "ÚLTIMO"/"PENÚLTIMO"), então um único ano baixado já permite
# calcular crescimento ano a ano, sem precisar de dois downloads.
#
# O plano de contas NÃO é fixo entre empresas: conferido contra dados reais
# de 2024, a Petrobras (não-financeira) tem "Lucro/Prejuízo do Período" na
# conta 3.11, enquanto o Itaú Unibanco (banco) tem "Lucro/Prejuízo
# Consolidado do Período" na conta 3.09 — bancos têm estrutura de DRE
# diferente (não têm "Custo dos Bens e/ou Serviços Vendidos", por exemplo).
# A regra usada aqui — pegar a última conta de nível 2 ("3.XX") antes de
# "3.99" (sempre reservada para Lucro por Ação em ambos os casos reais
# testados) — funcionou para os dois. Tem uma checagem de sanidade extra no
# adapter (a descrição da conta precisa conter "lucro"/"prejuízo") para não
# aceitar silenciosamente uma conta errada se essa regra falhar para algum
# outro tipo de empresa (seguradora, etc.) ainda não testado.
URL_CVM_DFP_ZIP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
FATOR_ESCALA_MOEDA_CVM = {"MIL": 1000.0, "UNIDADE": 1.0}
CONTA_LUCRO_POR_ACAO_CVM = "3.99"

# Catálogo de emissores da B3 (todos os tipos de ativo negociado, não só
# ações do Ibovespa) — usado para o crosswalk ticker (B3) -> CNPJ (CVM).
# Confirmado em 2026-09-14 chamando diretamente:
#   GET https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/{parametros_base64}
# API não-documentada da B3 (mesma família da usada em b3_universo.py, mas
# endpoint diferente: "listedCompaniesProxy", não "indexProxy"). pageSize
# acima de 100 quebra a resposta (a API devolve totalRecords/totalPages
# nulos) — usar 100 (36 páginas para os ~3523 registros atuais).
#
# O campo "cnpj" da resposta vem sem pontuação (ex: "33000167000101") e
# bate, conferido manualmente, com o CNPJ_CIA usado nos arquivos da CVM
# (com pontuação: "33.000.167/0001-01" para a Petrobras) e com o CD_CVM do
# cadastro de companhias abertas da CVM
# (dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv) —
# conferido para Petrobras (codeCVM 9512), Vale (4170) e Itaú Unibanco
# Holding (19348; o cadastro da CVM também lista um CD_CVM antigo, 1279,
# com SIT=CANCELADA para o mesmo CNPJ — reforça CNPJ como a chave estável
# entre as fontes, não CD_CVM, que pode ser reemitido ao longo do tempo).
#
# O código do emissor (campo "issuingCompany", único em todo o catálogo —
# conferido) é o prefixo do ticker sem o dígito de classe final (ex:
# ticker "PETR4" -> emissor "PETR"; "B3SA3" -> "B3SA", só o último dígito
# sai). Validado contra os 76 tickers reais do Ibovespa: 100% resolvidos
# por esse prefixo, sem precisar de casamento de nome como fallback.
URL_B3_CATALOGO_EMISSORES = (
    "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
    "CompanyCall/GetInitialCompanies/{parametros_base64}"
)

# Fórmula de Benjamin Graham ("Graham Number"): VI = sqrt(22,5 × LPA × VPA).
# 22,5 = 15 (P/L máximo considerado razoável por Graham) × 1,5 (P/VP máximo
# razoável). Fonte: The Intelligent Investor (Graham). Só aplicável com
# LPA > 0 e VPA > 0 — raiz de produto negativo não existe no domínio real.
FATOR_GRAHAM = 22.5

# Método Bazin (Preço Teto): preço_teto = dividendos dos últimos 12 meses /
# yield mínimo desejado. 6% a.a. é o valor clássico usado por Décio Bazin.
# Critério de "histórico de dividendo relevante" confirmado em 2026-09-14
# em https://investilize.com.br/blog/metodo-bazin-preco-teto/: "a empresa
# deve ter distribuído lucros ininterruptamente nos últimos 5 anos" —
# usado aqui como pelo menos um pagamento em cada um dos últimos 5 anos
# civis, sem lacuna.
YIELD_MINIMO_BAZIN = 0.06
ANOS_HISTORICO_MINIMO_BAZIN = 5

# --- Fluxo de Caixa Descontado (FCD) ---
#
# Base do fluxo de caixa livre: FCF = Caixa Líquido Atividades Operacionais
# (conta 6.01 da DFC) + Caixa Líquido Atividades de Investimento (6.02).
# Investigado em 2026-09-14: esses dois códigos de nível 2 são estáveis
# entre empresas de perfis bem diferentes — Petrobras (método indireto,
# não-financeira), Itaú Unibanco (método indireto, banco) e uma empresa
# que usa método direto — ao contrário da conta de Lucro Líquido da DRE
# (ver `CONTA_LUCRO_POR_ACAO_CVM` e o comentário do crosswalk/cvm.py), que
# varia por tipo de empresa. Como 6.02 normalmente vem negativo, somar os
# dois já desconta capex e outros investimentos do caixa operacional.
# Simplificação assumida (não é FCFF nem FCFE no sentido estritamente
# acadêmico, que exigiria reconstruir EBIT-CapEx-ΔWC ou separar juros de
# financiamento item a item — dado que a CVM não padroniza essa quebra de
# forma uniforme entre empresas): tratamos o valor presente desses fluxos
# como aproximação direta do valor do patrimônio líquido (equity), sem
# abater dívida líquida absoluta separadamente — outra simplificação, já
# que ainda não extraímos dívida líquida em valor absoluto do balanço
# patrimonial da CVM (BPP). Dividido pelo número de ações (Fundamentus,
# campo "Nro. Ações") pra chegar num valor justo por ação comparável a
# Graham/Bazin.
HORIZONTE_PROJECAO_FCD_ANOS = 5
ANOS_HISTORICO_CRESCIMENTO_FCD = 5

# Ano de referência pro FCD: 2025 ainda não estava publicado pela CVM na
# época em que isso foi escrito (confirmado no adapter da CVM), então usa
# 2024 como padrão fixo por ora — trocar por uma detecção automática do
# ano mais recente disponível é um refinamento futuro. Compartilhado entre
# app/main.py e screener.py, pra não divergir entre os dois.
ANO_REFERENCIA_FCD = 2024

# Taxa de crescimento explícita: CAGR do FCF entre o ano de referência e
# `ANOS_HISTORICO_CRESCIMENTO_FCD` anos antes (dois pontos, não a série
# inteira — CAGR só precisa dos extremos). Só é calculável se os dois
# valores forem positivos (raiz de negativo não existe); do contrário, cai
# no valor de IPCA (ver abaixo) como taxa neutra. Mesmo quando calculável,
# a CAGR de só 2 pontos pode ser um outlier (ex: ano-base com resultado
# atípico) — por isso é limitada a essa faixa antes de entrar na projeção,
# uma trava de bom senso, não um número pesquisado numa fonte externa.
TAXA_CRESCIMENTO_FCD_MINIMA = -0.20
TAXA_CRESCIMENTO_FCD_MAXIMA = 0.30

# WACC via CAPM simplificado: WACC = We×Ke + Wd×Kd×(1-alíquota).
#
# Ke (custo de capital próprio) = Selic (meta, via BCB) + Beta × prêmio de
# risco de mercado. Beta ainda não temos calculado (isso é o bloco de
# comportamento da ação, futuro) — usa BETA_PADRAO=1,0 (risco médio de
# mercado) como placeholder documentado até lá.
BETA_PADRAO = 1.0

# Prêmio de risco de mercado do Brasil: confirmado em 2026-09-14 direto na
# fonte (Damodaran, atualizada mensalmente) —
# https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html
# — Equity Risk Premium total do Brasil = 7,47% (spread de default
# ajustado 2,13% + country risk premium 3,24% sobre o prêmio "mercado
# maduro" ~4,23%, de países com rating AAA).
PREMIO_RISCO_MERCADO_BRASIL = 0.0747

# Kd (custo de capital de terceiros, pré-imposto) = Selic + spread de
# crédito. Pesquisa em 2026-09-14 achou o prêmio pago por empresas com
# melhor perfil de crédito na casa de "CDI + 1%" (ex:
# investnews.com.br/economia/corte-menor-da-selic-teria-custo-bilionario-
# para-as-empresas/); usamos 2 p.p. como margem um pouco mais conservadora
# pra cobrir o universo mais amplo do Ibovespa, não só as poucas empresas
# com o melhor rating de crédito.
SPREAD_CREDITO_PADRAO = 0.02

# Alíquota combinada padrão de IRPJ+CSLL no regime de lucro real (25%
# IRPJ + 10% adicional + 9% CSLL = 34%) — taxa estatutária padrão usada
# pra levar o custo de dívida a valor pós-imposto.
ALIQUOTA_IR_CSLL_PADRAO = 0.34

# Estrutura de capital (pesos We/Wd): derivada de
# `divida_liquida_sobre_patrimonio` (Fundamentus) por empresa, em vez de
# um peso fixo genérico igual pra todas as 76 ações do Ibovespa. Quando
# esse dado está ausente (ex: bancos — Fundamentus não reporta Dív
# Líq/Patrim pra instituição financeira, ver CAMPOS_FUNDAMENTUS/
# fundamentus.py) ou não-positivo (empresa em posição de caixa líquido,
# mais caixa que dívida), a empresa é tratada como não alavancada pro
# WACC (peso de dívida = 0, WACC = Ke) — simplificação conservadora e
# explícita, não uma estimativa real de estrutura de capital; refinar
# quando houver extração de dívida absoluta do balanço patrimonial (BPP)
# da CVM.

# Taxa de crescimento na perpetuidade: usa o IPCA acumulado em 12 meses
# (via BCB) como proxy de crescimento nominal de longo prazo da economia.
# Regra clássica de FCD (Gordon Growth): g nunca pode se aproximar/
# ultrapassar a taxa de desconto, senão o valor presente da perpetuidade
# diverge (denominador WACC-g tende a zero ou fica negativo). Em condições
# normais IPCA < Selic < WACC (Selic = IPCA + juro real; WACC ainda soma
# prêmio de risco sobre a Selic), então essa escolha já devria satisfazer
# a regra na prática — mas o cálculo trava explicitamente por segurança
# (ver `MARGEM_SEGURANCA_PERPETUIDADE_FCD`), nunca confia só na teoria.
MARGEM_SEGURANCA_PERPETUIDADE_FCD = 0.01

# --- Nota de validação do FCD (2026-09-14) ---
#
# Comparei o valor justo calculado com o preço de mercado real (via
# ingest.precos) pra duas empresas reais, com Selic/IPCA reais da mesma
# data:
#   PETR4: valor justo R$ 91,49 vs. preço R$ 49,00 (+87%)
#   VALE3: valor justo R$ 25,61 vs. preço R$ 78,20 (-67%)
#
# Refiz o cálculo por fora do módulo, passo a passo (FCF do ano-base, FCF
# projetado e valor presente de cada um dos 5 anos, valor terminal, valor
# presente do terminal, soma final ÷ número de ações) e reproduzi os dois
# valores exatamente — não achei inversão de escala (milhares/milhões:
# ESCALA_MOEDA="MIL" da CVM está sendo aplicada uma vez só, no adapter,
# nunca de novo no modelo) nem confusão entre valor de firma e valor de
# patrimônio na divisão final.
#
# As diferenças grandes têm explicação nas premissas assumidas, não em
# erro de conta:
#
# 1. WACC atual (17,2% pra PETR4, 18,6% pra VALE3) reflete a Selic em 14%
#    (patamar alto no momento da checagem) somada ao prêmio de risco de
#    mercado do Brasil — desconta bastante o fluxo futuro dos dois papéis
#    igualmente, então sozinho não explica a diferença de sinal entre os
#    dois resultados.
#
# 2. A CAGR de 5 anos (2 pontos só — ver ANOS_HISTORICO_CRESCIMENTO_FCD) é
#    sensível ao par de anos escolhido. Pra PETR4, CFO+CFI cresceu 7,0%
#    a.a. de 2019 pra 2024 mesmo com o lucro contábil (DRE) caindo bastante
#    no mesmo período (~R$125bi pra ~R$37bi, ver histórico validado em
#    ingest/cvm.py) — CFO+CFI diverge de lucro líquido por itens não-caixa
#    (variação cambial, impairment, imposto diferido), então esse
#    descolamento entre "lucro caindo" e "FCF subindo" é esperado dado a
#    base escolhida (CFO+CFI, não lucro líquido), não um bug de extração.
#    Pra VALE3 a CAGR deu levemente negativa (-1,3% a.a.), mais alinhada
#    com a leitura de que o papel estaria "caro" no modelo.
#
# 3. A simplificação já documentada acima (não abater dívida líquida
#    absoluta do valor calculado, por falta de extração do balanço
#    patrimonial da CVM) infla mais o valor calculado pra empresas mais
#    alavancadas. PETR4 (Dív Líq/Patrim=0,65) é bem mais alavancada que
#    VALE3 (0,35) — então essa simplificação pesa mais pra PETR4,
#    empurrando o valor calculado pra cima do que uma conta que abatesse a
#    dívida de verdade chegaria. É um viés conhecido na direção certa pra
#    explicar parte do porquê PETR4 destoa mais.
#
# 4. Somar a Selic (taxa nominal local) ao "Total Equity Risk Premium" do
#    Damodaran (que já embute risco-país) é uma convenção híbrida comum
#    entre analistas no Brasil, mas não é a aplicação mais "pura" de CAPM
#    (que usaria taxa livre de risco em dólar antes de converter pra
#    reais) — mantém o WACC estruturalmente mais alto do que uma
#    abordagem alternativa chegaria, achatando o valor presente de fluxos
#    distantes com mais força.
#
# Conclusão: nenhum erro de escala encontrado; a diferença é o resultado
# esperado de premissas conservadoras/simplificadas empilhadas (WACC alto,
# CAGR de 2 pontos, sem abater dívida absoluta) — não um motivo pra
# desconfiar da implementação, mas um lembrete de que o número do FCD
# sozinho não deve ser lido como "preço-alvo", e sim como um dos três
# métodos a serem combinados (ver o combinador de valor justo).

# --- Limiares de "desconto extremo" do screener (2026-09-14) ---
#
# O screener roda o pipeline completo nas ~76 ações do Ibovespa e ordena
# por desconto = (valor_combinado - preço_atual) / preço_atual × 100. A
# fragilidade da CAGR de 2 pontos do FCD (documentada acima) pode produzir
# descontos absurdos numa ação isolada sem que isso seja sinal de
# oportunidade real. Em vez de filtrar essas linhas (o usuário quer vê-las,
# só sinalizadas), marcamos as que passam de um limiar.
#
# Os limiares abaixo foram checados contra a distribuição real das 74
# ações com valor combinado aplicável, na mesma rodada de validação do
# screener:
#
# - Lado positivo: a sugestão inicial de +200% se confirmou um bom corte —
#   a distribuição é densa e contínua até ~206% (COGN3), com um salto
#   grande pro próximo valor (763%, MGLU3). +200% separa 4 outliers claros
#   do resto sem cortar no meio de um aglomerado.
# - Lado negativo: a sugestão inicial de -70% foi trocada por -100%. Com
#   -70%, 8 das 74 ações (11%) seriam marcadas, numa faixa contínua e sem
#   quebra visível (de -73% a -109%) — não parecia capturar "extremo", só
#   "bem descontado". -100% tem uma justificativa estrutural, não só
#   estatística: desconto < -100% só é matematicamente possível quando o
#   valor_combinado é negativo — um "valor justo negativo" é sempre
#   artefato das premissas do modelo (nunca uma leitura literal de que a
#   empresa vale menos que zero), então qualquer ocorrência já é suspeita
#   por construção. Na prática, isso pegou só 3 das 74 ações na validação
#   real — um recorte bem mais seletivo.
DESCONTO_EXTREMO_LIMITE_SUPERIOR = 200.0
DESCONTO_EXTREMO_LIMITE_INFERIOR = -100.0
AVISO_DESCONTO_EXTREMO = (
    "Desconto extremo — provavelmente reflete sensibilidade da CAGR de 2 "
    "pontos do FCD (ver nota de validação em config.py), não "
    "necessariamente uma oportunidade real."
)

# --- Painel de correlação com fatores externos (2026-09-15) ---
#
# Ticker do petróleo Brent no Yahoo Finance (futuro contínuo, contrato
# mais próximo). Escolhido em vez do WTI (CL=F) porque é o benchmark que
# a própria Petrobras e a OPEP usam como referência de preço internacional
# — mais relevante pra correlacionar com ações da B3 do que o WTI
# americano. Confirmado estável em 2026-09-15: 503 pregões num período de
# 2 anos via `yfinance.Ticker("BZ=F").history(period="2y")`, sem nulos.
TICKER_PETROLEO_BRENT = "BZ=F"

# Janela de histórico usada nas três correlações (ação × petróleo, ação ×
# câmbio, ação × GPR) — 2 anos é curto o bastante pra refletir o regime de
# mercado recente (não uma média histórica diluída de décadas) e longo o
# bastante pra ter uma amostra razoável de retornos diários (~500 pregões).
ANOS_JANELA_CORRELACAO = 2

# Mínimo de observações (retornos diários já alinhados pelas datas em
# comum) pra considerar uma correlação minimamente confiável. 30 é o
# "número mágico" clássico do Teorema Central do Limite — abaixo disso a
# distribuição amostral do coeficiente de correlação não tem garantia
# nenhuma de se comportar bem, e reportar um número ali passaria uma
# falsa sensação de precisão. Abaixo do mínimo, a correlação daquele par
# específico fica marcada como indisponível (não trava as outras duas).
MINIMO_OBSERVACOES_CORRELACAO = 30

# Cortes de magnitude pra leitura textual da correlação (fraca/moderada/
# forte) — regra de bolso comum em estatística aplicada a finanças (ex:
# Evans, 1996, "Straightforward Statistics for the Behavioral Sciences",
# que usa faixas semelhantes para |r|). Um heurístico de leitura rápida,
# não um limiar estatístico rígido — por isso documentado aqui, igual aos
# outros limiares do projeto, em vez de escondido no código.
LIMIAR_CORRELACAO_FRACA = 0.3
LIMIAR_CORRELACAO_FORTE = 0.6
