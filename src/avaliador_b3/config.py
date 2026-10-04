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

# Prazo de validade só da série "diaria" — a correlação usa uma janela de 2
# anos que termina hoje, então um GPR diário congelado faz a ponta recente
# da janela ficar sem dado, sem aviso nenhum (o número de observações só
# vai caindo). 7 dias (escolha redonda, mesmo raciocínio de
# DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE) — a "mensal" continua sem
# prazo, muda pouco e cobre um histórico bem mais longo.
DIAS_VALIDADE_CACHE_GPR_DIARIO = 7

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

# Período separado só pro card "Preço atual": o endpoint de histórico DIÁRIO do
# yfinance (period="3mo"/"5d", usado em PERIODO_HISTORICO_COMPORTAMENTO)
# atrasa um pregão inteiro — não só o candle do dia ainda em aberto, mesmo
# o fechamento do dia anterior, já encerrado, pode estar ausente. Testado
# diretamente contra o yfinance: period="5d" parou em 2026-09-14 (uma
# segunda-feira), enquanto period="1d" já trazia o fechamento de
# 2026-09-15 (R$ 50,43, batendo com o TradingView). O "preço atual" usa
# esse período separado; volume médio/volatilidade (mesmo bloco de
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
URL_B3_PORTFOLIO_DIA = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{parametros_base64}"

# 120 foi o tamanho de página que trouxe os 76 ativos do Ibovespa numa
# única página (ver comentário acima) — não é um limite confirmado da API
# (diferente de TAMANHO_PAGINA_API_B3_CATALOGO abaixo, onde >100 quebra a
# resposta): só o suficiente pro volume de dados desse endpoint específico,
# sem teste do teto real.
TAMANHO_PAGINA_API_B3_UNIVERSO = 120

# Prazo de validade do cache do universo do Ibovespa — a carteira teórica é
# rebalanceada 3x/ano (janeiro, maio, setembro); sem prazo, o app local
# continua ranqueando a composição antiga depois de um rebalanceamento, sem
# nenhum aviso. 7 dias (escolha redonda, mesmo raciocínio de
# DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE) é folgado pra uma carteira que
# só muda a cada ~4 meses, mas já evita ficar preso por meses.
DIAS_VALIDADE_CACHE_UNIVERSO_IBOVESPA = 7

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
#    busca nova é feita. Evita servir um cache sem o campo novo depois de uma
#    mudança em CAMPOS_FUNDAMENTUS/CAMPOS_FUNDAMENTUS_OPCIONAIS (a leitura da
#    chave nova quebraria com KeyError). Começa em 2 porque o schema já tinha
#    mudado antes de existir esse controle.
# 2. TTL (TTL_CACHE_FUNDAMENTUS_SEGUNDOS): rede de segurança geral pra
#    dado que fica desatualizado mesmo SEM mudança de schema — indicador
#    fundamentalista (ROE, margem, LPA/VPA, etc.) muda no máximo por
#    trimestre de resultado, e sem TTL o cache só existia ou não existia, sem
#    limite temporal. 24h é
#    suficiente pra nunca segurar um resultado por mais de um dia, sem
#    tornar o cache inútil (o adapter é batido dezenas de vezes em
#    sequência pelo screener).
#
# Cada campo novo do envelope de indicadores incrementa a versão (ex.:
# `data_balanco_fundamentus`, data do campo "Últ balanço processado", ver
# ROTULO_FUNDAMENTUS_DATA_BALANCO abaixo): é exatamente o cenário que esse
# mecanismo existe pra cobrir — campo novo, cache velho sem ele.
VERSAO_SCHEMA_FUNDAMENTUS = 5
TTL_CACHE_FUNDAMENTUS_SEGUNDOS = 24 * 60 * 60

# Rótulos usados só pra converter "Nro. Ações" na base do preço do ticker
# (ver ingest.fundamentus._numero_acoes_na_base_da_cotacao). Não fazem
# parte de CAMPOS_FUNDAMENTUS: a falta deles deixa o número de ações
# indisponível, não invalida a página inteira.
ROTULO_FUNDAMENTUS_COTACAO = "Cotação"
ROTULO_FUNDAMENTUS_VALOR_MERCADO = "Valor de mercado"

# Tolerância (relativa ao inteiro mais próximo) do fator "ações por
# cotação" calculado em ingest.fundamentus. A Cotação vem com 2 casas
# decimais, então em ativos de preço baixo o fator calculado se afasta do
# inteiro em até ~0,25%; 2% cobre esse ruído e ainda rejeita fator que
# claramente não é inteiro.
TOLERANCIA_FATOR_ACOES_POR_COTACAO = 0.02

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
URL_CVM_ITR_ZIP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{ano}.zip"
URLS_CVM_ZIP = {"dfp": URL_CVM_DFP_ZIP, "itr": URL_CVM_ITR_ZIP}
FATOR_ESCALA_MOEDA_CVM = {"MIL": 1000.0, "UNIDADE": 1.0}
CONTA_LUCRO_POR_ACAO_CVM = "3.99"

# O zip anual da CVM é cacheado com prazo de validade só pro(s) ano(s) ainda
# em preenchimento: anos fechados não mudam mais, mas a CVM atualiza o zip do
# ano corrente conforme as empresas entregam a DFP (inclusive fora do prazo).
# Sem prazo, um zip baixado cedo (ex: na janela jan-mar, ainda incompleto)
# ficaria preso localmente e as empresas que entregassem depois nunca
# apareceriam. Ver docs/correcao-ano-fcd-2026-09-23.md.
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

# Versionamento do cache por (CNPJ, ano) de `ingest.cvm.obter_fluxo_caixa_
# livre` (`data/raw/cvm/fcf_<cnpj>_<ano>.json`) — mesmo mecanismo e mesmo
# motivo de `VERSAO_SCHEMA_FUNDAMENTUS` (ver comentário completo mais
# abaixo, na seção do Fundamentus): sem a versão, um cache gravado antes de
# um campo novo (como `cfo_atual`/`cfi_atual`) seria servido sem a chave e
# quebraria com KeyError pra qualquer CNPJ/ano já cacheado. Cada mudança de
# schema incrementa a versão.
VERSAO_SCHEMA_CVM_FCF = 5

# Receita líquida da DRE (conta 3.01), lida junto com a DFC de cada ano na mesma demonstração
# (tipo e versão): o crescimento do fluxo do FCD é limitado pelo da receita no mesmo período.
# Um fluxo que cresce mais que a receita por 5 anos exige margem ou intensidade de capital
# melhorando sem limite; limitar ao crescimento da receita assume margem constante, premissa
# neutra e igual para todas as ações. Sem receita utilizável, vale o crescimento do fluxo.
CONTA_RECEITA_LIQUIDA_CVM = "3.01"
MOTIVO_RECEITA_NAO_LIDA = "a receita líquida não foi lida"
MOTIVO_RECEITA_SEM_DRE = "a empresa não tem a DRE desse ano na CVM"
MOTIVO_RECEITA_SEM_CONTA = "a DRE da CVM não traz a receita líquida (conta 3.01)"
MOTIVO_RECEITA_NAO_POSITIVA = (
    "a receita líquida do ano-base ou do ano de referência é zero ou negativa"
)
TEXTO_CRESCIMENTO_LIMITADO_PELA_RECEITA = (
    "Crescimento do fluxo limitado ao da receita líquida ({taxa} ao ano, no mesmo período)."
)
TEXTO_CRESCIMENTO_SEM_LIMITE_DA_RECEITA = (
    "Crescimento do fluxo sem o limite da receita líquida: {motivo}."
)

# --- Risco sacado e convênio com fornecedores no caixa de financiamento (6.03) ---
#
# Quando o banco paga o fornecedor e a empresa quita o banco depois (risco sacado, convênio com
# fornecedores, forfait, cessão de crédito por fornecedores), o aumento de fornecedores aparece
# no caixa operacional (6.01.02) e o pagamento ao banco, em 6.03, sem mudar o caixa total: o
# caixa operacional fica inflado. As linhas de 6.03 identificadas pelos termos abaixo (regex
# sobre a descrição normalizada, só subcontas de primeiro nível, 6.03.xx) são somadas por ano; se
# o saldo for saída (negativo), ele reduz o caixa operacional do fluxo do FCD, no ano de
# referência e no ano-base, na mesma demonstração. Saldo de entrada ou zero não muda nada: não dá
# para afirmar que uma entrada seja a mesma operação (VIVA3). "Parcelamento" fica de fora: é
# dívida com fornecedores, não financiamento da cadeia de suprimento.
TERMOS_RISCO_SACADO = (
    "risco sacado",
    "convenio",
    "cessao de credito por fornecedores",
    "forfait",
)
TERMOS_RISCO_SACADO_EXCLUIDOS = ("parcelamento",)

# --- Capex e juros pagos da DFC, por descrição das subcontas ---
#
# 6.01 e 6.02 vêm pelo código; o capex (6.02.xx) e os juros pagos (6.01.xx)
# vêm da DESCRIÇÃO da subconta, que cada empresa escreve de um jeito. Os
# termos abaixo são fragmentos de regex aplicados à descrição normalizada
# (sem acento, minúscula).
#
# Capex = linhas de 6.02.xx que citam TERMOS_CAPEX, sem nenhum dos
# TERMOS_CAPEX_EXCLUIDOS (venda, baixa, recebimento...) nem dos
# TERMOS_NAO_CAPEX (participações, controladas...). "Redução" só entra
# quando a linha também diz "acréscimo" (valor líquido de compras).
TERMOS_CAPEX = (
    "imobilizado",
    "intangivel",
    "intangiveis",
    "ativos? fixos?",
    "capex",
    "propriedades? para investimento",
    "ativos? de contrato",
    "ativos? contratu(?:al|ais)",
    "concess",
    "ativo biologico",
    "bens do ativo",
    "obras",
    "infraestrutura",
)
TERMOS_CAPEX_EXCLUIDOS = (
    "venda",
    "alienacao",
    "baixa",
    "recebimento",
    "resgate",
    "dividendo",
    "valores mobiliarios",
    "titulos",
    "emprestimo",
    "financiamento",
)
TERMOS_NAO_CAPEX = (
    "participac",
    "controlad",
    "coligad",
    r"\bempresas?\b",
    "negocio",
    r"\bacoes\b",
    r"\bcotas\b",
    "investidas",
    "joint",
    r"\bfundos\b",
    "sociedade",
    "combinacao",
    "caixa adquirido",
    "incorporac",
)
TERMO_CAPEX_REDUCAO = "reducao"
TERMO_CAPEX_ACRESCIMO = "acrescimo"

# Juros pagos em 6.01 = linhas dedicadas a juros (TERMOS_JUROS) pagos
# (TERMOS_JUROS_PAGOS) de empréstimos, financiamentos e debêntures. Ficam
# de fora juros de arrendamento (TERMOS_ARRENDAMENTO), juros recebidos,
# rendimentos de aplicações e juros sobre capital próprio
# (TERMOS_JUROS_EXCLUIDOS) e linhas mistas de principal e juros
# (TERMOS_JUROS_MISTOS).
TERMOS_JUROS = ("juros", "encargos")
TERMOS_JUROS_PAGOS = (
    "pago",
    "pagos",
    "pagamento",
    "pagamentos",
    "desembolso",
    "amortiza",
    "liquida",
)
TERMOS_JUROS_EXCLUIDOS = (
    "recebid",
    "receb",
    "capital proprio",
    "jcp",
    "dividend",
    "ativos",
    "aplicac",
    "provisao",
    "apropriad",
    "despesa",
    "variac",
    "monetaria",
    "cambia",
    "partes relacionadas",
    "derivativ",
)
TERMOS_JUROS_MISTOS = ("principal",)
TERMOS_ARRENDAMENTO = ("arrendamento", "leasing", "alugue", "locacao", "locacoes")

# --- Balanço consolidado e composição do capital (ITR e DFP) ---
#
# Uma leitura só, na data-base do balanço do Fundamentus, alimenta o desconto dos
# não controladores, os pesos do WACC (patrimônio total), o passivo de
# arrendamento fora da dívida do Fundamentus e o número de ações em circulação.
# 31/03, 30/06 e 30/09 vêm do ITR; 31/12 vem do DFP.
VERSAO_SCHEMA_CVM_BALANCO = 1
CODIGO_PATRIMONIO_LIQUIDO_CVM = "2.03"
TERMO_NAO_CONTROLADORES = "nao controlador"
# A dívida do Fundamentus é 2.01.04 + 2.02.01; arrendamento nessas contas já está nela.
PREFIXOS_CONTAS_DIVIDA_FUNDAMENTUS = ("2.01.04", "2.02.01")
PREFIXOS_CONTAS_PASSIVO = ("2.01.", "2.02.")
TERMOS_PASSIVO_ARRENDAMENTO = ("arrendamento", "locacao", "locacoes")
MESES_DIAS_BALANCO_ITR = ("03-31", "06-30", "09-30")
MES_DIA_BALANCO_DFP = "12-31"
# Salvaguardas do número de ações em circulação:
# 22 empresas informam a composição em milhares (o número do Fundamentus é cerca
# de 1.000 vezes o da CVM); tesouraria acima do limite indica erro de escala nos
# dados (TEND3); o integralizado já líquido de tesouraria (VALE3) é reconhecido
# quando integralizado + tesouraria bate com o Fundamentus; e uma divergência
# implausível (IGTI11, em que a CVM conta ações físicas e a unit é medida pelo peso
# econômico das ações) deixa o número da CVM de lado.
FATOR_ESCALA_MILHARES_CVM = 1000.0
FAIXA_RAZAO_ESCALA_MILHARES_CVM = (500.0, 2000.0)
LIMITE_TESOURARIA_SOBRE_CAPITAL = 0.20
TOLERANCIA_INTEGRALIZADO_LIQUIDO = 0.005
# Diferença entre o número do Fundamentus e o em circulação da CVM (ou o integralizado,
# quando a diferença é só a tesouraria) acima da qual a tela avisa.
LIMITE_DIVERGENCIA_ACOES = 0.02
LIMITE_DIVERGENCIA_ACOES_IMPLAUSIVEL = 0.5
MOTIVO_BALANCO_DATA_FORA_DO_TRIMESTRE = "A data-base do balanço ({data}) não é um fim de trimestre."
MOTIVO_BALANCO_SEM_DATA_BASE = "A data-base do balanço não está disponível."
MOTIVO_BALANCO_ARQUIVO_NAO_PUBLICADO = (
    "O arquivo {documento} da CVM de {ano} ainda não foi publicado."
)
MOTIVO_BALANCO_SEM_DEMONSTRACAO = (
    "A empresa não tem balanço consolidado de {data} no {documento} da CVM."
)
MOTIVO_BALANCO_NAO_LIDO = "o balanço da CVM não foi lido para essa empresa."
MOTIVO_ACOES_EM_CIRCULACAO_INDISPONIVEL = "número de ações da CVM indisponível."
# Valor de firma da página: mesma ponte do FCD (valor de mercado + dívida líquida + não
# controladores + arrendamento fora da dívida); componentes indisponíveis ficam de fora.
TOOLTIP_VALOR_FIRMA = (
    "Valor de mercado + dívida líquida + participação dos não controladores + "
    "arrendamento fora da dívida, a mesma ponte entre empresa e acionista usada no FCD."
)
ROTULOS_COMPONENTES_VALOR_FIRMA = {
    "divida_liquida": "dívida líquida",
    "nao_controladores": "não controladores",
    "arrendamento_fora_da_divida": "arrendamento fora da dívida",
}
TEXTO_FIRMA_SEM_COMPONENTES = "Valor de firma calculado sem {componentes} (dado indisponível)."

TEXTO_SEM_ACOES_EM_CIRCULACAO = (
    "Número de ações do Fundamentus (sem as ações em circulação da CVM): {motivo}"
)
MOTIVO_ARRENDAMENTO_INDISPONIVEL = "passivo de arrendamento não encontrado no balanço."
MOTIVO_PATRIMONIO_TOTAL_INDISPONIVEL = "patrimônio líquido total não encontrado no balanço."
MOTIVO_PATRIMONIO_TOTAL_NAO_POSITIVO = "patrimônio líquido total zero ou negativo."
MOTIVO_DIVIDA_LIQUIDA_INDISPONIVEL = "dívida líquida do Fundamentus indisponível."
TEXTO_SEM_AJUSTES_DO_BALANCO = (
    "Sem os ajustes do balanço da CVM (não controladores, arrendamento e "
    "patrimônio total nos pesos do custo de capital): {motivo}"
)
TEXTO_FCD_AJUSTES_DO_BALANCO = (
    "Do valor da empresa saem a dívida líquida (do Fundamentus), o passivo de "
    "arrendamento que ficou fora dessa dívida e a participação dos sócios não "
    "controladores das empresas controladas, pelo valor contábil do balanço "
    "consolidado da CVM. O custo de capital pesa a dívida líquida contra o "
    "patrimônio total (dos controladores e dos não controladores), pelos valores "
    "contábeis e sem o arrendamento. O valor por ação usa as ações em circulação "
    "(capital integralizado menos tesouraria, da composição de capital da CVM), e "
    "o Graham e o valor de mercado usam o mesmo número. Balanço e ações são da "
    "data-base do balanço do Fundamentus (a mesma de 'Saúde financeira'); "
    "ofertas, bonificações e cancelamentos de ações depois dessa data só entram no "
    "balanço seguinte, e a página avisa quando o número de ações do Fundamentus "
    "difere do da CVM. Se a CVM não trouxer o balanço, o FCD segue sem esses "
    "ajustes e o cartão diz o motivo. O resultado pode ser negativo (aviso 'Valor "
    "justo zero ou negativo') e não é limitado a zero."
)
TEXTO_SEM_ARRENDAMENTO_NA_DIVIDA = (
    "Sem o desconto do passivo de arrendamento que está fora da dívida: {motivo}"
)
TEXTO_SEM_PATRIMONIO_TOTAL_NOS_PESOS = (
    "Pesos do custo de capital com a razão do Fundamentus (patrimônio só dos "
    "controladores): {motivo}"
)
TEXTO_SEM_DESCONTO_NAO_CONTROLADORES = (
    "Sem o desconto da participação dos não controladores: {motivo}"
)
MOTIVO_ACOES_SEM_REFERENCIA = (
    "Número de ações do Fundamentus indisponível: sem ele não dá para validar a escala "
    "da composição do capital da CVM."
)
MOTIVO_ACOES_SEM_COMPOSICAO = (
    "A empresa não tem composição do capital de {data} no {documento} da CVM."
)
MOTIVO_ACOES_TESOURARIA_ALTA = (
    "Tesouraria de {percentual} do capital na composição da CVM, acima do limite de "
    "{limite}: provável erro de escala nos dados da CVM."
)
MOTIVO_ACOES_DIVERGENCIA_IMPLAUSIVEL = (
    "O número de ações da CVM ({cvm}) difere {divergencia} do do Fundamentus "
    "({fundamentus}); mantido o do Fundamentus."
)
# Acrescentado ao motivo acima quando a ação é uma unit.
COMPLEMENTO_ACOES_DIVERGENCIA_UNIT = (
    "Em units, a diferença pode vir de a CVM contar ações físicas enquanto a unit é medida "
    "pelo peso econômico das ações que a formam."
)
AVISO_DIVERGENCIA_ACOES = (
    "O número de ações do Fundamentus ({fundamentus}) difere em {divergencia} do da CVM "
    "em {data} ({cvm}). Pode ter havido oferta, bonificação ou cancelamento de ações "
    "depois dessa data."
)

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

# Prazo de validade do cache do catálogo de emissores — traz o segmento
# setorial (decide exclusão do FCD e monta a Comparação setorial), CNPJ e
# código CVM; mudanças são raras (empresa nova, mudança de segmento ou de
# CNPJ), por isso um prazo bem mais longo que os outros caches do projeto.
DIAS_VALIDADE_CACHE_CATALOGO_EMISSORES_B3 = 30

# O catálogo da B3 ("GetInitialCompanies") devolve "cnpj" e "codeCVM" como
# NÚMERO JSON, e um literal numérico não tem zero à esquerda: o dígito já se
# perde na resposta, antes de qualquer código do projeto. É sistêmico: 954
# dos ~3523 registros do catálogo (27%) têm "cnpj" com menos de 14 dígitos e
# 906 têm "codigo_cvm" com menos de 6. Ex.: ABEV3 vem com cnpj="7526557000100"
# e codigo_cvm="23264", enquanto a CVM tem CNPJ_CIA="07.526.557/0001-00" e
# CD_CVM="023264"; ENGI11 perde dois zeros ("864214000106" contra
# "00.864.214/0001-06").
#
# Os campos são completados com zeros à esquerda até a largura fixa: CNPJ
# sempre tem 14 dígitos e CD_CVM sempre tem 6 (em todos os registros dos zips
# da CVM lidos pelo projeto). Isso só restaura dígitos que existiam, sem
# colidir com outra empresa. Aplicado em três camadas (ver
# docs/correcao-cnpj-2026-09-25.md): na origem
# (crosswalk_cnpj._registro_para_linha), na leitura do cache
# (crosswalk_cnpj.obter_catalogo_emissores, pra caches já gravados) e como
# camada defensiva em cvm._normalizar_cnpj.
TAMANHO_CNPJ = 14
TAMANHO_CODIGO_CVM = 6

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

# Corte de "razão de dividendos atípica": o preço teto usa a soma dos
# dividendos dos últimos 12 meses, mas
# o yfinance (fonte, ver ingest.precos.obter_dividendos) não distingue
# pagamento ordinário de extraordinário — um provento pontual grande entra
# na mesma soma e pode inflar o preço teto sem aviso nenhum.
#
# Investigado: pra todo o universo Bazin-aplicável do Ibovespa (40 ações),
# calculada a razão entre os dividendos dos últimos 12 meses e a MEDIANA dos
# totais anuais dos 5 anos anteriores (mesmos anos que
# ANOS_HISTORICO_MINIMO_BAZIN já exige). Distribuição contínua de 0,35 a
# 6,21, sem um único penhasco dramático — mas com um "vale" visível entre
# 1,9 e 2,6: o maior salto entre valores vizinhos nessa faixa, fora dos 2
# outliers mais extremos (RDOR3, CURY3), fica entre PSSA3 (2,58) e B3SA3
# (2,25), com outro salto logo depois entre ITSA4 (2,16) e VIVA3 (1,92).
#
# Cogitado um corte estatístico mais formal (regra de outlier de Tukey, Q3 +
# 1,5×IQR ≈ 3,31) e descartado: pegaria só 4 ações (RDOR3, CURY3, WEGE3,
# POMO4), deixando de fora ITUB4 (2,79x) e B3SA3 (2,25x), que também estão
# claramente acima do padrão histórico da própria empresa. 2,0 cai dentro do
# vale observado, fica logo acima do 3º quartil da distribuição (1,84) e tem
# leitura direta em linguagem simples ("recebeu mais que o dobro do que
# pagava tipicamente por ano") — trade-off assumido entre rigor estatístico
# e um corte explicável na tela.
RAZAO_DIVIDENDOS_ATIPICA_BAZIN = 2.0

# --- Fluxo de Caixa Descontado (FCD) ---
#
# Base do fluxo de caixa livre: caixa gerado pela operação (conta 6.01 da
# DFC), menos o capex (compras de imobilizado e intangível, subcontas de
# 6.02 identificadas pela descrição) e mais os juros pagos em 6.01, já
# líquidos do imposto (ALIQUOTA_IR_CSLL_PADRAO). Os juros voltam ao fluxo
# porque o custo da dívida já está no WACC e a dívida líquida é subtraída
# depois; sem isso a dívida seria penalizada duas vezes. Ficam de fora o
# resto de 6.02 (aplicações financeiras, compra e venda de participações e
# de ativos, que não são geração de caixa recorrente) e o pagamento de
# arrendamentos (IFRS 16), que fica em 6.03. O valor presente desses
# fluxos é o Enterprise Value — valor da empresa como um todo, dívida
# incluída.
#
# O Enterprise Value é convertido em Equity Value (valor só do patrimônio dos
# acionistas) subtraindo a dívida líquida ANTES de dividir pelo número de
# ações (ver `modelos.fcd.calcular_valor_justo_fcd`); sem isso o valor justo
# por ação de empresa com dívida líquida positiva seria inflado. A dívida
# líquida vem do campo "Dív. Líquida" do Fundamentus (`divida_liquida` em
# `CAMPOS_FUNDAMENTUS_OPCIONAIS`), o mesmo de
# `empresa.valor_mercado.calcular_valor_mercado_e_firma` e de "Saúde
# financeira". Dívida líquida negativa (posição de caixa líquido) soma ao
# valor normalmente, sem caso especial. Quando a dívida líquida não está
# disponível pra uma empresa, o EV é dividido direto pelo número de ações,
# com aviso explícito na UI (`divida_liquida_deduzida=False` no retorno da
# função).
#
# Dividido pelo número de ações (Fundamentus, campo "Nro. Ações") pra
# chegar num valor justo por ação comparável a Graham/Bazin.
#
# Investigação em 2026-09-25 (limitação registrada em
# docs/correcao-cnpj-2026-09-25.md, seção 7 — FCD sistematicamente muito
# abaixo de Graham/Bazin em empresas de investimento pesado): pra todas as
# 70 ações com FCD aplicável no Ibovespa, calculada a proporção reinvestida
# do caixa operacional (na época, -CFI/CFO; hoje o capex ÷ caixa operacional do FCD de
# `modelos.fcd.calcular_proporcao_capex_caixa_operacional_percentual`) e
# comparada com o quanto o FCD diverge de Graham. Correlação de Spearman entre
# as duas: -0,79 (forte) — ações com
# reinvestimento acima da mediana (49,7%) têm FCD 130,7% abaixo de Graham
# na mediana, contra só 28,8% nas de reinvestimento abaixo da mediana. A
# hipótese se sustenta como padrão geral: o modelo trata TODO investimento
# como saída de caixa que reduz o valor presente, sem diferenciar
# investimento de manutenção (só repõe o que já existe) de expansão (gera
# crescimento futuro que o FCD não capta na CAGR de 2 pontos). Efeito
# concentrado, mas não exclusivo, em energia elétrica (10 de 11 ações do
# setor com FCD negativo) e saneamento (2 de 2).
#
# Dívida líquida alta amplia o efeito e, num caso (AXIA3: FCD 91% abaixo de
# Graham com reinvestimento de só 38%, abaixo da mediana), é o fator
# dominante sozinho — a dedução da dívida líquida (acima) pesa mais que o
# reinvestimento nesse caso específico. Reinvestimento
# não explica tudo sozinho, por isso a decisão foi mostrar a proporção
# reinvestida como contexto (ver `_cartao_metodo`/coluna "Reinvestimento" no
# Screener), não excluir setores nem ajustar o cálculo do FCF.
#
# Opção cogitada e descartada por enquanto: usar a conta de Depreciação e
# Amortização da DFC (reconciliação dentro de 6.01, método indireto) como
# proxy de investimento de manutenção, pra separar do que é expansão. Só
# existe pro método indireto (a maioria das empresas, mas não todas) E o
# código da subconta NÃO é fixo entre empresas — testado contra CPFE3
# (D&A no código 6.01.01.02) e EQTL3 (D&A no código 6.01.01.19, código
# totalmente diferente) — mesmo problema já documentado pra
# `CONTA_LUCRO_POR_ACAO_CVM` (a conta de Lucro Líquido da DRE também não é
# fixa). Extrair de forma confiável exigiria busca por descrição (texto
# contendo "epreciaç"/"mortiza"), o mesmo tipo de heurística frágil já usado
# pro Lucro Líquido — evolução futura possível, não implementada.
HORIZONTE_PROJECAO_FCD_ANOS = 5
ANOS_HISTORICO_CRESCIMENTO_FCD = 5

# Convergência do crescimento explícito: o ano 1 cresce pela taxa calculada (CAGR ou IPCA) e
# o crescimento converge linearmente para o da perpetuidade, que o ano indicado aqui já usa.
# Sem a convergência, o crescimento cairia de até 30% para o da perpetuidade (~4%) de um ano
# para o outro (do ano 5 para o 6), um salto sem base na economia da empresa, e o valor
# terminal, que pesa mais da metade do FCD, ficaria refém dele.
ANO_FIM_CONVERGENCIA_CRESCIMENTO_FCD = HORIZONTE_PROJECAO_FCD_ANOS

# FCD "não aplicável" pra instituições financeiras, pelo segmento setorial
# oficial da B3
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
# Seguradoras e a Itaúsa também ficam sem FCD: o caixa de uma seguradora
# vem de prêmios e sinistros (as reservas técnicas não são dívida
# comum), e o da Itaúsa, de dividendos das empresas em que participa
# (principalmente o Itaú Unibanco). O segmento "Seguradoras" da B3 pega
# só BBSE3, PSSA3 e CXSE3 no Ibovespa; a Itaúsa (segmento "Holdings
# Diversificadas") é identificada pelo ticker, pra não arrastar outras
# holdings. B3SA3 (bolsa) segue com FCD, com a limitação documentada.
SEGMENTOS_FCD_NAO_APLICAVEL = {"Bancos", "Seguradoras"}
TICKERS_FCD_NAO_APLICAVEL = {"ITSA4"}

# Motivos mostrados na tela quando o FCD não se aplica (o dos bancos fica
# em modelos/fcd.py, `MOTIVO_NAO_APLICAVEL_INSTITUICAO_FINANCEIRA`).
MOTIVO_FCD_SEGURADORA = (
    "Seguradora: o caixa de uma seguradora vem de prêmios recebidos e "
    "sinistros pagos, e as reservas técnicas não são dívida comum, então "
    "o fluxo de caixa descontado não tem interpretação confiável aqui. "
    "Os outros métodos continuam sendo calculados quando se aplicam."
)
MOTIVOS_FCD_POR_SEGMENTO = {"Seguradoras": MOTIVO_FCD_SEGURADORA}
MOTIVO_FCD_HOLDING_FINANCEIRA = (
    "Holding financeira: o caixa da Itaúsa vem dos dividendos das empresas "
    "em que ela participa (principalmente o Itaú Unibanco), não de uma "
    "operação própria, então o fluxo de caixa descontado não mede o valor "
    "dessas participações. Os outros métodos continuam sendo calculados quando se aplicam."
)
TEXTO_COMPLEMENTO_SEM_METODO = "Veja o motivo de cada método nos cartões ao lado."
# Preço atual vazio, zero ou negativo (a fonte não trouxe um preço válido).
MENSAGEM_PRECO_INDISPONIVEL_SCREENER = "Preço atual indisponível"
AVISO_PRECO_INDISPONIVEL = (
    "Preço atual indisponível: a fonte de preços não trouxe um valor válido "
    "agora, então o potencial não foi calculado. Tente de novo mais tarde."
)

# Checagem da rodada do screener antes de substituir o screener.csv: com mais
# ações sem preço, ou com falha de fonte, do que estes limites, a rodada é
# descartada e o resultado anterior fica.
LIMITE_ACOES_SEM_PRECO_SCREENER = 5
LIMITE_ACOES_COM_FALHA_SCREENER = 5
FONTE_FUNDAMENTUS = "Fundamentus"
FONTE_CVM = "CVM"
FONTE_YAHOO = "Yahoo"
FONTE_BCB = "Banco Central"
TEXTO_SCREENER_CONCLUIDO = "Screener concluído — resultado salvo em disco."
TEXTO_SCREENER_CONCLUIDO_COM_FALHAS = (
    "Screener concluído com falhas de fonte em: {acoes}. Nessas ações, algum "
    "método pode ter ficado de fora."
)
MOTIVO_RODADA_SEM_PRECO = "{quantidade} ações sem preço (limite: {limite})."
MOTIVO_RODADA_COM_FALHA_DE_FONTE = (
    "{quantidade} ações com falha de fonte (limite: {limite}); por fonte: {por_fonte}."
)
MOTIVO_RODADA_LINHAS_FALTANDO = "{linhas} linhas para {universo} ações do universo."
# Resumo impresso por `python -m avaliador_b3.rodar_screener` (uma linha por item).
TTL_CACHE_RESUMO_RODADA_SEGUNDOS = 24 * 60 * 60  # lê só o cache de preços, sem rede
CODIGO_SAIDA_RODADA_ACEITA = 0
CODIGO_SAIDA_RODADA_REJEITADA = 1
CODIGO_SAIDA_RODADA_COM_EXCECAO = 2
RESUMO_RODADA_ACEITA = "Rodada: ACEITA"
RESUMO_RODADA_REJEITADA = "Rodada: REJEITADA (o screener.csv anterior foi mantido)"
RESUMO_RODADA_EXCECAO = "Rodada: FALHOU POR EXCEÇÃO"
RESUMO_MOTIVO = "Motivo: {motivo}"
RESUMO_ARQUIVO_REJEITADO = "Rodada descartada em: {caminho}"
RESUMO_ACOES = "Ações na rodada: {total} | com FCD: {com_fcd}"
RESUMO_SEM_FALHAS = "Falhas de fonte: nenhuma"
RESUMO_FALHAS = "Falhas de fonte: {por_fonte} (ações: {acoes})"
RESUMO_MACRO = (
    "Selic meta: {selic} (fonte: {fonte_selic}) | IPCA 12m: {ipca} (fonte: {fonte_ipca}, "
    "referência {data_ipca})"
)
RESUMO_MACRO_GUARDADO = (
    "Atenção: Selic e IPCA vieram de valor guardado; o arquivo de referência não foi atualizado."
)
RESUMO_MACRO_INDISPONIVEL = "Selic meta e IPCA 12m: indisponíveis"
RESUMO_DATA_PRECOS = "Data dos preços: {data}"
RESUMO_DATA_PRECOS_INDISPONIVEL = "Data dos preços: indisponível"
RESUMO_AVISO = "Aviso: {aviso}"

TEXTO_RODADA_DESCARTADA = (
    "Rodada descartada: {motivo} O resultado anterior foi mantido. A rodada "
    "descartada ficou em {caminho} para diagnóstico."
)
MOTIVO_FCD_CAPEX_NAO_IDENTIFICADO = (
    "Não foi possível identificar o gasto em imobilizado e intangível "
    "(capex) na demonstração de fluxo de caixa da empresa, e sem ele o "
    "fluxo de caixa livre não é calculado. Os outros métodos continuam "
    "sendo calculados quando se aplicam."
)
# Legenda do cartão do FCD: capex (o mesmo do fluxo do FCD) sobre o caixa operacional.
LEGENDA_REINVESTIMENTO_CAPEX = (
    "Em {ano}, reinvestiu {proporcao:.0f}% do caixa gerado pela operação "
    "(investimento em imobilizado e intangível)."
)
# Legenda do cartão do FCD quando a saída líquida de risco sacado/convênio (6.03) é tratada como
# operacional: {valor} já vem formatado (ex.: "R$ 13,5 bi").
TEXTO_RISCO_SACADO_RECLASSIFICADO = (
    "Em {ano}, {valor} pagos a bancos em operações de convênio com fornecedores (risco sacado "
    "ou similar), registrados no caixa de financiamento, foram tratados como operacionais: "
    "esses pagamentos substituem pagamentos a fornecedores, e sem o ajuste o caixa operacional "
    "pode parecer maior do que a geração de caixa da empresa."
)
# Motivos mostrados quando o crescimento do fluxo cai para o IPCA.
TEXTO_CRESCIMENTO_IPCA = "Crescimento do fluxo estimado pelo IPCA: {motivo}."
MOTIVO_CRESCIMENTO_IPCA_BASE_AUSENTE = "a empresa não tem demonstração do ano-base na CVM"
MOTIVO_CRESCIMENTO_IPCA_BASE_SEM_CAPEX = (
    "o gasto em imobilizado e intangível do ano-base não foi identificado"
)
MOTIVO_CRESCIMENTO_IPCA_BASE_NAO_POSITIVA = (
    "o fluxo de caixa livre do ano-base foi zero ou negativo"
)
MOTIVO_FCD_FLUXO_NAO_POSITIVO = (
    "O fluxo de caixa livre do último ano foi zero ou negativo; projetá-lo "
    "para o futuro não dá uma estimativa de valor confiável, então o "
    "fluxo de caixa descontado não é calculado. Os outros métodos continuam "
    "sendo calculados quando se aplicam."
)

# O ano de referência do FCD não é uma constante fixa: um valor fixo (ex.:
# 2024) defasaria o FCD de TODAS as empresas por um exercício inteiro, sem
# nenhum aviso na tela, assim que a CVM publicasse o exercício seguinte — ver
# docs/correcao-ano-fcd-2026-09-23.md.
#
# A detecção é automática, em dois níveis, sem constante fixa aqui (cada
# busca resolve o ano em tempo de execução):
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
# uma trava de bom senso, não um número pesquisado numa fonte externa. O crescimento do fluxo
# também é limitado por cima pelo CAGR da receita líquida no mesmo período (ver
# `CONTA_RECEITA_LIQUIDA_CVM`), e a faixa continua valendo como limite externo.
TAXA_CRESCIMENTO_FCD_MINIMA = -0.20
TAXA_CRESCIMENTO_FCD_MAXIMA = 0.30

# WACC via CAPM simplificado: WACC = We×Ke + Wd×Kd×(1-alíquota).
#
# Ke (custo de capital próprio) = (Selic meta, via BCB, menos o spread de default do Brasil) +
# Beta × prêmio de risco total. A Selic, taxa em reais do governo, já embute o risco de default
# do Brasil, e o prêmio total inclui o risco-país; por isso o spread é tirado da taxa livre de
# risco, para não contar o risco duas vezes (orientação do Damodaran em "What is the riskfree
# rate? A Search for the Basic Building Block", 2008). BETA_PADRAO=1,0 (risco médio de mercado)
# é o valor usado quando o Beta da ação não é calculável.
BETA_PADRAO = 1.0

# Prêmio de risco de ações do Brasil e spread de default, da tabela "Country Default Spreads and
# Risk Premiums" do Damodaran —
# https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html
# — lida em 04/10/2026, com "Last updated: January 5, 2026". Linha do Brasil: rating Moody's Ba1,
# spread de default ajustado de 2,13% e prêmio total de risco de ações de 7,47%, soma de 4,23%
# (mercado maduro) e 3,24% (risco-país). O risco-país é o spread de default multiplicado pela
# volatilidade relativa das ações contra a dos títulos (cerca de 1,52), então os 2,13% estão
# dentro dos 3,24%, e não somados a eles.
#
# A tabela é atualizada uma vez por ano, em janeiro. A cada atualização, conferir à mão, na
# página, as constantes PREMIO_RISCO_MERCADO_BRASIL e SPREAD_DEFAULT_BRASIL (e o rating) e
# registrar aqui a nova data da página.
PREMIO_RISCO_MERCADO_BRASIL = 0.0747
SPREAD_DEFAULT_BRASIL = 0.0213

# Kd (custo de capital de terceiros, pré-imposto) = Selic + spread de
# crédito, sem tirar o spread de default: é o custo real de captação das
# empresas em reais. Pesquisa em 2026-09-14 achou o prêmio pago por empresas com
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

# --- Limiares de "potencial extremo" do screener (2026-09-14) ---
#
# O screener roda o pipeline completo nas ~76 ações do Ibovespa e ordena
# por potencial = (valor_combinado - preço_atual) / preço_atual × 100. A
# fragilidade da CAGR de 2 pontos do FCD (documentada acima) pode produzir
# potenciais absurdos numa ação isolada sem que isso seja sinal de
# oportunidade real. Em vez de filtrar essas linhas (o usuário quer vê-las,
# só sinalizadas), marcamos as que passam de um limiar.
#
# Os limiares abaixo foram checados contra a distribuição real das 74
# ações com valor combinado aplicável, na mesma rodada de validação do
# screener:
#
# - Lado positivo: +200% é um bom corte —
#   a distribuição é densa e contínua até ~206% (COGN3), com um salto
#   grande pro próximo valor (763%, MGLU3). +200% separa 4 outliers claros
#   do resto sem cortar no meio de um aglomerado.
# - Lado negativo: -100% em vez de -70%. Com -70%, 8 das 74 ações (11%)
#   seriam marcadas, numa faixa contínua e sem quebra visível (de -73% a
#   -109%) — não capturaria "extremo", só "preço bem acima do valor". -100%
#   tem uma justificativa estrutural, não só
#   estatística: potencial < -100% só é matematicamente possível quando o
#   valor_combinado é negativo — um "valor justo negativo" é sempre
#   artefato das premissas do modelo (nunca uma leitura literal de que a
#   empresa vale menos que zero), então qualquer ocorrência já é suspeita
#   por construção. Na prática, isso pegou só 3 das 74 ações na validação
#   real — um recorte bem mais seletivo.
DESCONTO_EXTREMO_LIMITE_SUPERIOR = 200.0
DESCONTO_EXTREMO_LIMITE_INFERIOR = -100.0

# O aviso tem 4 textos, escolhidos em avaliador_b3.screener.
# _aviso_desconto_extremo por sinal do potencial (positivo/negativo) ×
# presença de "fcd" em `metodos_utilizados`: um texto único culpando sempre o
# FCD estaria errado quando o valor combinado vem só do Graham (ex.: COGN3).
# Nenhum cita nome de arquivo/código nem jargão técnico (linguagem visível ao
# usuário).
AVISO_DESCONTO_EXTREMO_POSITIVO_COM_FCD = (
    "Potencial extremo — provavelmente vem da taxa de crescimento "
    "estimada pelo FCD, que usa só dois anos de dados e pode exagerar o "
    "resultado. Não é necessariamente uma oportunidade real."
)
AVISO_DESCONTO_EXTREMO_POSITIVO_SEM_FCD = (
    "Potencial extremo — calculado só com Graham e/ou Bazin. Potenciais "
    "desse tamanho costumam indicar que o mercado está precificando um "
    "risco que essas fórmulas não captam (como dívida alta ou lucro que "
    "pode não se repetir). Confira os valores individuais antes de "
    "considerar uma oportunidade real."
)
AVISO_DESCONTO_EXTREMO_NEGATIVO_COM_FCD = (
    "Valor justo zero ou negativo — o FCD saiu negativo, o que acontece "
    "quando a dívida líquida, somada à parte dos sócios não controladores, "
    "supera o valor do fluxo de caixa projetado. "
    "Não quer dizer que a ação "
    "valha menos que zero, mas indica que, pelas premissas do modelo, a "
    "geração de caixa não sustenta o preço atual. Confira o "
    "endividamento em 'Saúde financeira'."
)
# Reserva pra qualquer combinação não coberta acima — hoje, na prática,
# só "potencial negativo extremo SEM FCD entre os métodos". Essa
# combinação é INALCANÇÁVEL com os modelos atuais: Graham é uma raiz
# quadrada (`modelos.graham`, sempre ≥ 0 quando calculável) e Bazin só
# fica "aplicável" quando o dividendo dos últimos 12 meses é positivo
# (`modelos.bazin`, preco_teto sempre > 0 nesse caso) — sem o FCD (o
# único dos três que pode dar negativo), a média de Graham e/ou Bazin
# nunca é negativa, então potencial ≤ LIMITE_INFERIOR (que exige
# valor_combinado ≤ 0) não pode acontecer. Existe mesmo assim, sem
# inventar uma explicação específica, pra não deixar essa combinação sem
# texto nenhum se um dos dois modelos mudar no futuro e passar a
# permitir valor negativo.
AVISO_DESCONTO_EXTREMO_GENERICO = (
    "Potencial fora do comum — confira os valores individuais de cada "
    "método antes de tirar qualquer conclusão."
)

# Vocabulário do "Potencial" (valor justo ÷ preço − 1) na tela: rótulo da
# coluna e tooltips do Screener, da comparação setorial e dos cartões de
# Valor Justo. A coluna `desconto_percentual` do CSV mantém o nome.
ROTULO_POTENCIAL = "Potencial"
TOOLTIP_POTENCIAL_COLUNA = (
    "Quanto o valor justo combinado está acima (+) ou abaixo (−) do preço "
    "atual (valor justo ÷ preço − 1). Não é prazo nem retorno esperado."
)
TOOLTIP_POTENCIAL_CARTAO = "Diferença entre este valor e o preço atual (valor ÷ preço − 1)."

# --- Simulador de carteira: potencial sem prazo ---
#
# O valor justo (Graham, Bazin, FCD) é um valor de hoje: o Simulador mostra
# quanto a carteira valeria se o preço de cada ação chegasse a ele, em reais
# de hoje, sem prazo e sem contar dividendos — nada de taxa anual nem ganho
# real.
TEXTO_ABERTURA_SIMULADOR = (
    "Mostra o potencial de cada cenário (pessimista/base/otimista) para o "
    "valor investido em cada ação — a partir do resultado já salvo do "
    "screener, sem recalcular nada ao vivo."
)
SUBTITULO_POTENCIAL_CARTEIRA = "Potencial de valorização da carteira"
AVISO_SIMULADOR_SEM_PREVISAO = (
    "Quanto a carteira valeria se o preço de cada ação chegasse ao valor "
    "justo do cenário, em reais de hoje, sem prazo e sem contar dividendos. "
    "Não é previsão."
)
ROTULOS_VALOR_AO_CONVERGIR = {
    "pessimista": "Valor ao convergir: pessimista (R$)",
    "base": "Valor ao convergir: base (R$)",
    "otimista": "Valor ao convergir: otimista (R$)",
}
ROTULOS_POTENCIAL_CENARIO = {
    "pessimista": "Potencial: pessimista (%)",
    "base": "Potencial: base (%)",
    "otimista": "Potencial: otimista (%)",
}
ROTULOS_TOTAL_AO_CONVERGIR = {
    "pessimista": "Valor ao convergir: pessimista",
    "base": "Valor ao convergir: base",
    "otimista": "Valor ao convergir: otimista",
}
TOOLTIP_POTENCIAL_CENARIO = (
    "Quanto o valor justo do cenário está acima (+) ou abaixo (−) do preço "
    "atual (valor justo ÷ preço − 1). Não é retorno esperado nem tem prazo."
)
FRASE_RESUMO_SIMULADOR = (
    "{investido} investidos hoje equivaleriam a entre {pessimista} "
    "(pessimista) e {otimista} (otimista) se os preços convergissem aos "
    "valores justos, sem prazo definido."
)
TITULO_EXPANDER_SIMULADOR = "Como funciona este cálculo?"
TEXTO_EXPANDER_SIMULADOR = (
    "Os valores pessimista, base e otimista vêm dos mesmos três cenários "
    "calculados para cada ação (o menor, a média, e o maior entre os "
    "métodos de valor justo aplicáveis — Graham, Bazin e FCD). O potencial "
    "é o valor justo do cenário dividido pelo preço atual, menos 1, e o "
    "valor ao convergir é o valor investido multiplicado por esse valor "
    "justo ÷ preço: quanto o dinheiro valeria se o preço chegasse ao valor "
    "justo, em reais de hoje, sem prazo e sem contar dividendos. Valor "
    "justo zero ou negativo conta como perda total (−100%).\n\n"
    "O cenário base é o valor combinado, a mesma média simples explicada "
    "na aba Analisar uma ação. O pessimista e o otimista são o menor e o "
    "maior valor entre os métodos aplicáveis — e o menor pode ser o preço "
    "teto do Bazin, que não é uma estimativa de valor, e sim o máximo a "
    "pagar pelo retorno em dividendos."
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
# — usado pra converter a série mensal do IPCA numa taxa anualizada pro
# WACC do FCD.
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

# Validade (em dias) do último valor de Selic/IPCA guardado em disco
# (data/raw/bcb/ultimo_macro.json), usado como último recurso quando o BCB
# está fora do ar mesmo depois das novas tentativas — 45 dias porque a
# Selic só muda nas reuniões do Copom (~45 dias de intervalo, mesma
# margem do comentário acima sobre JANELA_BUSCA_SELIC_DIAS), então um
# valor guardado dentro desse prazo ainda é a meta vigente na grande
# maioria dos casos.
VALIDADE_MACRO_GUARDADO_DIAS = 45

# Arquivo de referência versionado com o screener.csv: a cada rodada aceita do screener
# grava a Selic, o IPCA, as fontes e a data da busca. É o último recurso da cadeia, para
# o Streamlit Cloud, cujo disco local (e o valor guardado) some a cada reinício.
# Validade de 90 dias (dois ciclos do Copom): mais folgada que a do valor guardado, porque
# o arquivo só se renova quando alguém roda o screener e commita, e a tela sempre avisa a
# data. Passado o prazo, é melhor recusar o FCD do que usar uma Selic que pode ter mudado.
NOME_ARQUIVO_MACRO_REFERENCIA = "macro_referencia.json"
CAMINHO_MACRO_REFERENCIA = DATA_PROCESSED_DIR / NOME_ARQUIVO_MACRO_REFERENCIA
VALIDADE_MACRO_REFERENCIA_DIAS = 90
PREFIXO_FONTE_ARQUIVO_REFERENCIA = "arquivo de referência"
FONTE_ARQUIVO_REFERENCIA = PREFIXO_FONTE_ARQUIVO_REFERENCIA + " de {data}"

# Pausas entre novas tentativas em erro temporário (5xx, timeout, conexão
# — ver ingest._retry.get_com_retry), compartilhadas por toda fonte que
# usa nova tentativa (hoje: BCB e Fundamentus). Timeout continua por
# fonte, cada uma com seu próprio nome abaixo — fontes diferentes têm
# latência típica diferente.
PAUSAS_RETRY_SEGUNDOS = (2, 5)

# Teto do Retry-After respeitado no erro 429 — um servidor pedindo espera
# maior que isso não trava a rodada inteira; passado o teto, a próxima
# tentativa segue mesmo assim (e falha de novo, se for o caso).
TETO_RETRY_AFTER_SEGUNDOS = 30

# Disjuntor do Fundamentus no screener: depois desta quantidade de ações
# SEGUIDAS com falha de rede (não conta ticker inexistente nem mudança na
# estrutura da página), o screener para de consultá-lo no resto da rodada.
# Site fora do ar custaria 97s por ação (ver TIMEOUT_SEGUNDOS_FUNDAMENTUS)
# nas ~76 ações do Ibovespa; com o disjuntor, no máximo 3 × 97s.
FALHAS_SEGUIDAS_DISJUNTOR_FUNDAMENTUS = 3

# Timeout de cada tentativa de requisição ao SGS do BCB — buscar Selic e
# IPCA faz 2 séries em sequência, cada uma com até 3 tentativas (a
# original + 2 novas): pior caso = 2 × (3 × 10 + 2 + 5) = 74s, contra os
# ~194s que um timeout de 30s daria — 10s já é folgado pra uma API que
# historicamente responde em menos de 1s.
TIMEOUT_SEGUNDOS_BCB_SGS = 10

# Segunda fonte do BCB para as mesmas séries do SGS (432 Selic meta, 433 IPCA
# mensal, 1 câmbio): o serviço SOAP legado do SGS no www3, que seguiu no ar
# quando api.bcb.gov.br deixou de resolver (NXDOMAIN, 03/10/2026). Mesmos
# códigos e valores. Pior caso de espera da cadeia inteira (tudo por timeout),
# com falha rápida (uma fonte que falha na primeira série é abandonada para a
# outra) e uma nova tentativa nas fontes secundárias: REST 3 × 10 + 2 + 5 =
# 37s, SOAP 2 × 10 + 2 = 22s, mais o IBGE (IPCA, 22s) = 81s, contra os 74s do
# REST sozinho (N07). Com falha de DNS cada tentativa falha na hora, e a
# cadeia inteira leva só as pausas (cerca de 11s).
URL_BCB_SOAP = "https://www3.bcb.gov.br/wssgs/services/FachadaWSSGS"
TIMEOUT_SEGUNDOS_BCB_SOAP = 10
PAUSAS_RETRY_FONTE_SECUNDARIA_SEGUNDOS = (2,)
# Janela de busca da Selic no SOAP: a meta vigente é o último valor até hoje.
JANELA_BUSCA_SELIC_SOAP_DIAS = 15
# Terceira fonte, só do IPCA: a API SIDRA do IBGE (tabela 1737, variável 63, IPCA mensal).
# Os meses são os mesmos da série 433 do BCB, e o acumulado de 12 meses sai do mesmo
# cálculo. Busca 14 meses (mínimo de 12, mais uma folga de publicação).
URL_IBGE_SIDRA_IPCA_MENSAL = (
    "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/63/p/last%20{meses}"
)
TIMEOUT_SEGUNDOS_IBGE = 10
MESES_BUSCA_IPCA_SIDRA = 14
FONTE_IBGE = "IBGE (SIDRA)"
FONTE_BCB_API = "BCB (API)"
FONTE_BCB_SOAP = "BCB (SOAP)"
FONTE_VALOR_GUARDADO = "valor guardado de {data}"

# Textos da tela sobre a origem da Selic e do IPCA quando não vêm da API REST do Banco Central.
FRASE_FONTE_MACRO = {
    FONTE_BCB_SOAP: "pelo serviço SOAP do Banco Central",
    FONTE_IBGE: "pelo IBGE (SIDRA)",
}
AVISO_MACRO_MESMA_FONTE = "Selic e IPCA obtidos {frase}."
AVISO_MACRO_SELIC_FONTE = "Selic obtida {frase}."
AVISO_MACRO_IPCA_FONTE = "IPCA obtido {frase}."
AVISO_MACRO_ARQUIVO_REFERENCIA = (
    "Banco Central indisponível agora. Usando a Selic e o IPCA do arquivo de referência "
    "do projeto, obtidos em {data}."
)

# Timeout de cada tentativa de requisição ao Fundamentus. Pior caso por
# ação: 3 tentativas × 30s + pausas de 2s e 5s = 97s.
TIMEOUT_SEGUNDOS_FUNDAMENTUS = 30

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
# o protagonista — usado em dois lugares: a série de comparação real
# (benchmark: Ibovespa ou petróleo) e a linha de Dividend Yield no gráfico
# de histórico de dividendos (uma segunda métrica da mesma ação, não um
# benchmark externo). COR_GRAFICO_GRADE é um tom só um pouco mais claro que
# COR_GRAFICO_FUNDO, pras linhas de grade ficarem discretas.
COR_GRAFICO_FUNDO = "#16212F"
COR_GRAFICO_TEXTO = "#E9E4D8"
COR_GRAFICO_PROTAGONISTA = "#C9982F"
COR_GRAFICO_CONTEXTO = "#5B6B7C"
COR_GRAFICO_GRADE = "#233040"
