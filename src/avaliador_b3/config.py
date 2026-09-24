"""Constantes do projeto. Toda constante aqui deve citar a fonte que a valida."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"

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

# Dias úteis por ano de pregão — convenção padrão em finança quantitativa
# pra anualizar volatilidade diária (fator √252), citada em praticamente
# todo material introdutório de gestão de risco/precificação (ex:
# Hull, "Options, Futures, and Other Derivatives") e consistente com o
# calendário real da B3 (~250-253 pregões/ano, variando com feriados).
# Não é uma medição específica da B3 pro ano corrente, é a convenção de
# mercado padrão — usada em `empresa.comportamento.calcular_volatilidade_anualizada`.
DIAS_UTEIS_POR_ANO = 252

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

# 120 foi o tamanho de página que trouxe os 76 ativos do Ibovespa numa
# única página (ver comentário acima) — não é um limite confirmado da API
# (diferente de TAMANHO_PAGINA_API_B3_CATALOGO abaixo, onde >100 quebra a
# resposta): só o suficiente pro volume de dados desse endpoint específico,
# sem teste do teto real.
TAMANHO_PAGINA_API_B3_UNIVERSO = 120

# Delay entre páginas ao paginar contra as APIs não-documentadas da B3
# (ingest/_paginacao.py, compartilhado entre b3_universo.py — raramente
# pagina de verdade, tudo cabe numa página — e crosswalk_cnpj.py, que pagina
# até ~36 vezes pro catálogo completo de emissores). Mesmo raciocínio do
# DELAY_FUNDAMENTUS_SEGUNDOS/DELAY_PRECOS_SEGUNDOS: valor conservador por
# analogia, não uma cifra pesquisada especificamente pra esse endpoint.
DELAY_PAGINACAO_B3_SEGUNDOS = 1.5

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

# Cache em disco (data/raw/fundamentus/*.json) protegido por DOIS
# mecanismos independentes, que resolvem problemas diferentes — um não
# substitui o outro:
#
# 1. Versionamento de schema (VERSAO_SCHEMA_FUNDAMENTUS): o cache guarda
#    essa versão dentro do próprio JSON; se o código atual espera uma
#    versão diferente da gravada, o cache é tratado como inválido e uma
#    busca nova é feita. Ataca a causa raiz de um bug real já acontecido
#    nesta sessão: quando CAMPOS_FUNDAMENTUS/CAMPOS_FUNDAMENTUS_OPCIONAIS
#    ganharam um campo novo (Patrim. Líq/Dív. Líquida), o cache antigo
#    continuou sendo servido sem esse campo, e o primeiro código que tentou
#    ler a chave nova quebrou com KeyError — só resolvido apagando o cache
#    manualmente. Começa em 2 (não 1) porque o schema já mudou pelo menos
#    uma vez nesta sessão antes de esse mecanismo existir; nunca houve uma
#    "versão 1" com controle de versão de verdade.
# 2. TTL (TTL_CACHE_FUNDAMENTUS_SEGUNDOS): rede de segurança geral pra
#    dado que fica desatualizado mesmo SEM mudança de schema — indicador
#    fundamentalista (ROE, margem, LPA/VPA, etc.) muda no máximo por
#    trimestre de resultado, mas nada garantia isso até agora (o cache não
#    tinha limite temporal nenhum, só existia/não existia). 24h é
#    suficiente pra nunca segurar um resultado por mais de um dia, sem
#    tornar o cache inútil (o adapter é batido dezenas de vezes em
#    sequência pelo screener).
#
# Incrementada pra 3 em 2026-09-24: `data_balanco_fundamentus` (data do
# campo "Últ balanço processado", ver ROTULO_FUNDAMENTUS_DATA_BALANCO
# abaixo) virou um campo novo do envelope de indicadores — exatamente o
# cenário que esse mecanismo existe pra cobrir (campo novo, cache velho
# sem ele), mesmo caso real do KeyError de "Patrim. Líq/Dív. Líquida"
# citado acima.
VERSAO_SCHEMA_FUNDAMENTUS = 3
TTL_CACHE_FUNDAMENTUS_SEGUNDOS = 24 * 60 * 60

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

# Data do balanço usado como base pros indicadores acima — campo próprio
# (não passa por CAMPOS_FUNDAMENTUS/CAMPOS_FUNDAMENTUS_OPCIONAIS porque o
# valor é uma DATA, não um número; _parse_numero quebraria em cima de
# "30/06/2026"). Confirmado direto no HTML de PETR4 em 2026-09-24: rótulo
# "Últ balanço processado", mesma estrutura <td class="label">/<td> dos
# demais campos, com um tooltip da própria Fundamentus que confirma a
# semântica do dado: "Data do último balanço divulgado pela empresa que
# consta no nosso banco de dados. Todos os indicadores são calculados
# considerando os últimos 12 meses finalizados na data deste balanço." —
# ou seja, todo indicador de fluxo (ROE, margem, LPA, crescimento) é TTM
# terminando nessa data; os de posição (patrimônio, dívida, número de
# ações) são o valor NESSA data, não "hoje". Tratado como opcional (vira
# None se ausente), mesmo espírito de CAMPOS_FUNDAMENTUS_OPCIONAIS, mas
# fora do dict porque o parsing é de data, não de número.
ROTULO_FUNDAMENTUS_DATA_BALANCO = "Últ balanço processado"

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

# Bug real encontrado em 2026-09-23 (ver docs/correcao-ano-fcd-2026-09-23.md):
# ingest.cvm._baixar_zip_ano cacheava o zip anual da CVM pra sempre, sem
# prazo de validade — "existe no disco?" era a única checagem. Isso é
# inofensivo pra anos fechados (a CVM não reabre exercícios encerrados,
# então o arquivo não muda mais), mas quebra o ano ainda em preenchimento:
# a CVM atualiza esse mesmo zip ao longo do ano conforme empresas entregam
# a DFP (inclusive fora do prazo), então um zip baixado cedo (ex: na janela
# jan-mar, ainda incompleto) ficava preso pra sempre localmente — empresas
# que entregassem depois nunca mais apareceriam nesse zip aqui, mesmo com
# a CVM já tendo atualizado o arquivo remoto há meses.
#
# Prazo de validade de 7 dias (escolha redonda, não uma medição — a DFP não
# muda hora a hora, então checar 1x/semana já evita ficar preso por meses,
# sem bater na rede a cada busca) que só vale pro(s) ano(s) ainda em
# preenchimento (`ano >= ano corrente - 1` em ingest.cvm._cache_zip_
# expirado); anos fechados continuam com cache permanente, sem custo de
# rede repetido à toa.
DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE = 7

# Códigos de conta da DFC (Demonstração de Fluxo de Caixa) usados pro Fluxo
# de Caixa Livre (FCF) do FCD — ver a justificativa completa (por que
# CFO+CFI, e a checagem de estabilidade desses dois códigos entre
# Petrobras/Itaú/uma empresa de método direto) na seção "Fluxo de Caixa
# Descontado (FCD)" mais abaixo neste arquivo.
CODIGO_CFO_CVM = "6.01"  # Caixa Líquido Atividades Operacionais
CODIGO_CFI_CVM = "6.02"  # Caixa Líquido Atividades de Investimento

# Catálogo de emissores da B3 (todos os tipos de ativo negociado, não só
# ações do Ibovespa) — usado para o crosswalk ticker (B3) -> CNPJ (CVM).
# Confirmado em 2026-09-14 chamando diretamente:
#   GET https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/{parametros_base64}
# API não-documentada da B3 (mesma família da usada em b3_universo.py, mas
# endpoint diferente: "listedCompaniesProxy", não "indexProxy"). pageSize
# acima de 100 quebra a resposta (a API devolve totalRecords/totalPages
# nulos) — usar 100 (36 páginas para os ~3523 registros atuais). Diferente
# de TAMANHO_PAGINA_API_B3_UNIVERSO acima: este é um limite real, testado
# e confirmado, não só "o que coube".
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
TAMANHO_PAGINA_API_B3_CATALOGO = 100

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
# como Enterprise Value — valor da empresa como um todo, dívida incluída.
#
# Correção em 2026-09-23 (achado numa revisão externa do projeto): até
# então, esse Enterprise Value era dividido direto pelo número de ações,
# sem abater a dívida líquida — na prática tratando o resultado como se
# já fosse Equity Value (valor só do patrimônio dos acionistas), o que
# inflava o valor justo por ação de qualquer empresa com dívida líquida
# positiva. A premissa original registrada aqui era "ainda não extraímos
# dívida líquida em valor absoluto do balanço patrimonial da CVM (BPP)"
# — verdade sobre a CVM, mas o projeto já extraía essa dívida por OUTRA
# fonte desde o início: o campo "Dív. Líquida" do Fundamentus
# (`divida_liquida` em `CAMPOS_FUNDAMENTUS_OPCIONAIS`), o mesmo já usado
# em `empresa.valor_mercado.calcular_valor_mercado_e_firma` e exibido em
# "Saúde financeira" — só não estava sendo passado pro FCD. Agora está:
# o Enterprise Value é convertido pra Equity Value subtraindo essa
# dívida líquida ANTES de dividir pelo número de ações (ver
# `modelos.fcd.calcular_valor_justo_fcd`); dívida líquida negativa
# (posição de caixa líquido) soma ao valor normalmente, mesma convenção
# de `calcular_valor_mercado_e_firma`, sem caso especial. Quando a
# dívida líquida não está disponível pra uma empresa, o cálculo cai de
# volta na aproximação antiga só pra esse caso específico, com um aviso
# explícito na UI
# (`divida_liquida_deduzida=False` no retorno da função).
#
# Dividido pelo número de ações (Fundamentus, campo "Nro. Ações") pra
# chegar num valor justo por ação comparável a Graham/Bazin.
HORIZONTE_PROJECAO_FCD_ANOS = 5
ANOS_HISTORICO_CRESCIMENTO_FCD = 5

# Correção em 2026-09-23 (segundo achado da mesma revisão externa, pouco
# depois da correção EV->Equity acima, ainda no mesmo dia): FCD "não
# aplicável" pra instituições financeiras, pelo segmento setorial oficial da B3
# (`ingest.crosswalk_cnpj`, campo "segment" do catálogo de emissores) —
# NÃO por `divida_liquida is None`, que é lacuna de UMA fonte de dado
# (Fundamentus não reporta "Dív. Líquida" pra banco), não uma
# classificação de tipo de negócio. Os dois coincidiam por acaso no
# universo do Ibovespa em 2026-09-23 (os 6 tickers com
# `divida_liquida=None` eram exatamente os 6 do segmento "Bancos"), mas
# são conceitos diferentes — usar a lacuna de dado como critério
# quebraria silenciosamente se o Fundamentus passasse a reportar esse
# campo pra bancos, ou parasse de reportar pra alguma não-financeira.
#
# Argumento econômico: a metodologia do FCD (FCF via CFO+CFI -> WACC ->
# Enterprise Value -> - dívida líquida -> Equity Value) pressupõe que
# dívida é financiamento externo à operação. Em bancos, dívida e
# depósitos SÃO a própria operação (captação pra emprestar), não
# financiamento dela — e o CFO oscila com a expansão/contração da
# carteira de crédito, não com geração de valor. A conta não tem
# interpretação econômica válida nesse setor. Graham e Bazin continuam
# aplicáveis normalmente (não dependem de estrutura de capital nem de
# fluxo de caixa operacional do mesmo jeito).
#
# Escopo deliberadamente restrito a "Bancos": seguradoras (BBSE3, CXSE3,
# PSSA3) e outras financeiras (B3SA3 — bolsa/infraestrutura de mercado;
# ITSA4 — holding cujo principal ativo é participação no Itaú, mas não é
# ela mesma um banco) ficaram de fora por decisão deliberada, não
# esquecimento: diferente dos bancos, essas empresas TÊM dívida líquida
# reportada pelo Fundamentus normalmente (confirmado uma a uma antes
# dessa decisão), então não compartilham a mesma lacuna de dado nem,
# necessariamente, a mesma distorção — se o FCD também não faz sentido
# econômico pra elas é uma questão em aberto, registrada como limitação
# conhecida, não decidida aqui.
SEGMENTOS_FCD_NAO_APLICAVEL = {"Bancos"}

# Correção em 2026-09-23 (terceiro achado da mesma revisão externa, ainda
# no mesmo dia das duas correções acima): o ano de referência do FCD era
# uma constante fixa aqui, ANO_REFERENCIA_FCD = 2024, com a justificativa
# original de que "2025 ainda não estava publicado pela CVM na época em
# que isso foi escrito (confirmado no adapter da CVM)". Essa premissa
# ficou desatualizada — confirmado em 2026-09-23 que o zip de 2025 já
# estava disponível e completo (FCF calculável, comparado ano a ano, pra
# PETR4/VALE3/WEGE3/RADL3), então o valor fixo defasava o FCD de TODAS as
# empresas por um exercício inteiro sem nenhum aviso na tela — ver
# docs/correcao-ano-fcd-2026-09-23.md.
#
# Substituído por detecção automática em dois níveis, sem constante fixa
# aqui (cada busca resolve o ano em tempo de execução):
# - Nível arquivo (`ingest.cvm.resolver_ano_mais_recente_disponivel`):
#   existe zip da CVM pro ano corrente - 1? Se a CVM ainda não publicou
#   (404 — janela jan-mar, antes do prazo legal de entrega da DFP), cai
#   pro ano anterior inteiro. Chamado uma vez por execução, reaproveitado
#   entre todas as empresas, mesmo padrão do zip em si.
# - Nível empresa (`ingest.cvm.obter_fluxo_caixa_livre_com_fallback`): se
#   uma empresa específica ainda não aparece no zip mais recente
#   (`CnpjNaoEncontrado` — não entregou a DFP daquele exercício ainda),
#   cai um ano só pra ELA, sem afetar as demais; o ano-base do
#   crescimento anda junto, mantendo sempre o intervalo de
#   ANOS_HISTORICO_CRESCIMENTO_FCD anos. `ContaFluxoCaixaNaoEncontrada`
#   (layout mudou) NÃO dispara esse fallback — propaga como erro.

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

# Correção em 2026-09-24: o aviso era um texto ÚNICO, sempre culpando o
# FCD, independente de quais métodos realmente entraram no valor
# combinado daquela ação — achado real, revisando o Screener publicado
# (screenshot da aba Screener): COGN3 disparava o limiar positivo só com
# Graham (FCD nem aplicável ali), mas o texto dizia "sensibilidade da
# CAGR do FCD" mesmo assim. Virou 4 textos, escolhidos em
# avaliador_b3.screener._aviso_desconto_extremo por sinal do desconto
# (positivo/negativo) × presença de "fcd" em `metodos_utilizados` — os
# LIMIARES não mudaram, só qual texto explica cada combinação. Nenhum
# cita nome de arquivo/código nem jargão técnico (linguagem visível ao
# usuário).
AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD = (
    "Desconto extremo — provavelmente vem da taxa de crescimento "
    "estimada pelo FCD, que usa só dois anos de dados e pode exagerar o "
    "resultado. Não é necessariamente uma oportunidade real."
)
AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD = (
    "Desconto extremo — calculado só com Graham e/ou Bazin. Descontos "
    "desse tamanho costumam indicar que o mercado está precificando um "
    "risco que essas fórmulas não captam (como dívida alta ou lucro que "
    "pode não se repetir). Confira os valores individuais antes de "
    "considerar uma oportunidade real."
)
AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD = (
    "Valor justo zero ou negativo — o FCD saiu negativo, o que acontece "
    "quando o fluxo de caixa projetado é negativo ou quando a dívida "
    "líquida supera o valor desse fluxo. Não quer dizer que a ação "
    "valha menos que zero, mas indica que, pelas premissas do modelo, a "
    "geração de caixa não sustenta o preço atual. Confira o "
    "endividamento em 'Saúde financeira'."
)
# Reserva pra qualquer combinação não coberta acima — hoje, na prática,
# só "desconto negativo extremo SEM FCD entre os métodos". Essa
# combinação é INALCANÇÁVEL com os modelos atuais: Graham é uma raiz
# quadrada (`modelos.graham`, sempre ≥ 0 quando calculável) e Bazin só
# fica "aplicável" quando o dividendo dos últimos 12 meses é positivo
# (`modelos.bazin`, preco_teto sempre > 0 nesse caso) — sem o FCD (o
# único dos três que pode dar negativo), a média de Graham e/ou Bazin
# nunca é negativa, então desconto ≤ LIMITE_INFERIOR (que exige
# valor_combinado ≤ 0) não pode acontecer. Existe mesmo assim, sem
# inventar uma explicação específica, pra não deixar essa combinação sem
# texto nenhum se um dos dois modelos mudar no futuro e passar a
# permitir valor negativo.
AVISO_DESCONTO_EXTREMO_GENERICO = (
    "Desconto fora do comum — confira os valores individuais de cada "
    "método antes de tirar qualquer conclusão."
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

# --- Aba "Analisar uma ação" (app/main.py) — 2026-09-18 ---
#
# Meses de acumulação do IPCA: "IPCA acumulado em 12 meses" é o indicador
# padrão de inflação anual usado no Brasil (mesma convenção do IBGE/BCB)
# — usado pra converter a série mensal do IPCA numa taxa anualizada, tanto
# pro WACC do FCD quanto pro ganho real da carteira.
MESES_IPCA_ACUMULADO = 12

# Janelas de busca (em dias) pras séries do BCB usadas no card "Selic/
# IPCA" — margem de segurança pra garantir pelo menos uma leitura recente
# de cada série, não uma medição exata do intervalo entre publicações:
# - Selic: a meta é definida pelo Copom a cada ~45 dias (não diariamente)
#   — 90 dias garante pelo menos uma reunião coberta mesmo com atraso.
# - IPCA: precisa de pelo menos MESES_IPCA_ACUMULADO (12) leituras
#   mensais pra acumular a taxa anual — 730 dias (~2 anos) dá folga
#   generosa mesmo com atraso de publicação do BCB.
JANELA_BUSCA_SELIC_DIAS = 90
JANELA_BUSCA_IPCA_DIAS = 730

# Opções do seletor de janela da seção "Comparando com Petróleo (Brent)"
# — mesmas strings de período aceitas por `ingest.precos.obter_historico`
# (convenção do yfinance: "2y"/"5y"/"10y").
JANELAS_COMPARACAO_PETROLEO = {"2 anos": "2y", "5 anos": "5y", "10 anos": "10y"}

# --- Paleta de tema (2026-09-19 e 2026-09-20) ---
#
# Tema dark navy + dourado, espelhando `.streamlit/config.toml`
# (backgroundColor/secondaryBackgroundColor/primaryColor/textColor) —
# aplicado manualmente aqui porque os gráficos Plotly não herdam o tema
# do Streamlit automaticamente, só os componentes nativos (st.metric,
# st.dataframe, etc.) herdam. Usado em `app/main.py` nos `go.Figure()`.
#
# COR_GRAFICO_FUNDO = secondaryBackgroundColor do tema (fundo do gráfico,
# não o fundo da página, pra manter um leve contraste de "cartão").
# COR_GRAFICO_PROTAGONISTA (dourado) marca a série principal (a ação
# sendo analisada). COR_GRAFICO_CONTEXTO (cinza-azulado neutro) marca
# qualquer série de "pano de fundo" que não deve competir visualmente com
# o protagonista — usado em três lugares: a série de comparação real
# (benchmark: Ibovespa ou petróleo), a linha de Dividend Yield no gráfico
# de histórico de dividendos (uma segunda métrica da mesma ação, não um
# benchmark externo), e a linha de inflação (IPCA) no gráfico de projeção
# de carteira. COR_GRAFICO_GRADE é um tom só um pouco mais claro que
# COR_GRAFICO_FUNDO, pras linhas de grade ficarem discretas.
COR_GRAFICO_FUNDO = "#16212F"
COR_GRAFICO_TEXTO = "#E9E4D8"
COR_GRAFICO_PROTAGONISTA = "#C9982F"
COR_GRAFICO_CONTEXTO = "#5B6B7C"
COR_GRAFICO_GRADE = "#233040"

# Verde/vermelho de ganho/perda em tom mais discreto que o padrão do
# Plotly (que tende a um neon que destoa da paleta escura acima) —
# mesma leitura semântica de mercado (verde=alta, vermelho=baixa),
# só ajustada de tom. Usado nas curvas de cenário da projeção de
# carteira (`aba_carteira`), que não passam pelo tema do Streamlit por
# serem Plotly.
COR_GANHO = "#3FA34D"
COR_PERDA = "#C6483E"

# Cor neutra — mesmo tom de COR_GRAFICO_CONTEXTO (mesma função: neutro,
# não deve chamar atenção). Usada em CORES_CENARIO["base"] (curva "base"
# do gráfico de projeção de carteira, nem ganho nem perda). Cogitada
# originalmente também pros cartões de método/correlação "não aplicável"
# (app/main.py, `_cartao_metodo`/`_cartao_correlacao`), mas esses já usam
# a opacidade nativa do st.caption/st.metric do Streamlit pra ficar
# visualmente neutros — não há como injetar essa cor ali sem HTML bruto
# (nenhum dos dois componentes aceita parâmetro de cor), então não são
# consumidores reais desse token.
COR_NEUTRA = "#5B6B7C"

# Cores das curvas de cenário do gráfico de "Projeção de crescimento"
# (aba Simulador de carteira, `aba_carteira` em app/main.py) — combinação
# dos tokens acima, não uma cor nova: pessimista/otimista usam a mesma
# semântica de mercado dos deltas (vermelho=perda, verde=ganho); "base"
# (nem ganho nem perda) usa o tom neutro, não o azul padrão do Plotly.
CORES_CENARIO = {
    "pessimista": COR_PERDA,
    "base": COR_NEUTRA,
    "otimista": COR_GANHO,
}
