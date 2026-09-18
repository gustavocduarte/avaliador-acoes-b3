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

# GDELT Event Database, formato 2.0 (atualizado a cada 15 min). Confirmado em
# 2026-09-14 baixando data.gdeltproject.org/gdeltv2/lastupdate.txt e o
# .export.CSV.zip mais recente por ele apontado: 61 colunas separadas por
# tab, sem cabeçalho, na ordem oficial do codebook —
# http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
# Ordem conferida campo a campo contra uma linha real do arquivo baixado.
URL_GDELT_LASTUPDATE = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# O nome de arquivo de um snapshot passado segue um padrão previsível —
# confirmado em 2026-09-16 checando o timestamp real apontado por
# lastupdate.txt (20260915083000, alinhado exatamente a um múltiplo de 15
# min) e testando 96 URLs passadas construídas manualmente
# (https://data.gdeltproject.org/gdeltv2/{timestamp}.export.CSV.zip, com
# {timestamp} indo de 15 em 15 min pra trás a partir do mais recente): as
# 96 responderam HTTP 200. Gaps (horário sem arquivo publicado) são raros
# mas conhecidos — tratados isoladamente por horário, sem travar a janela
# inteira (ver conflitos.obter_eventos_relevantes_ultimas_24h).
INTERVALO_SNAPSHOT_GDELT_MINUTOS = 15
JANELA_MONITOR_CONFLITOS_HORAS = 24.0

# Delay entre requisições ao buscar vários snapshots em sequência (janela
# de 24h = ~96 arquivos) — mesmo princípio do yfinance/Fundamentus, mas
# um valor menor: os arquivos do GDELT são estáticos (já publicados, sem
# risco de "lock" concorrente) servidos de um storage tipo CDN, não uma
# raspagem de HTML frágil como o Fundamentus — um delay pequeno já é
# suficiente pra não bater rápido demais, sem tornar a janela de 24h
# proibitivamente lenta (96 arquivos × alguns segundos de download já é
# bastante tempo por si só).
DELAY_GDELT_SEGUNDOS = 0.5

COLUNAS_EVENTO_GDELT = [
    "GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
    "GoldsteinScale", "NumMentions", "NumSources", "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_FullName", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_ADM2Code", "Actor1Geo_Lat", "Actor1Geo_Long",
    "Actor1Geo_FeatureID",
    "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_ADM2Code", "Actor2Geo_Lat", "Actor2Geo_Long",
    "Actor2Geo_FeatureID",
    "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_ADM2Code", "ActionGeo_Lat", "ActionGeo_Long",
    "ActionGeo_FeatureID",
    "DATEADDED", "SOURCEURL",
]
assert len(COLUNAS_EVENTO_GDELT) == 61

# Categorias CAMEO "raiz" (2 dígitos) de conflito, conforme o codebook CAMEO
# oficial: 17=COERCE, 18=ASSAULT, 19=FIGHT.
CATEGORIAS_CONFLITO_CAMEO = {
    "17": "COERCE",
    "18": "ASSAULT",
    "19": "FIGHT",
}

# --- Refinamento de ruído no Monitor de conflitos (2026-09-17) ---
#
# Investigação rodada contra os ~8.456 eventos já capturados pelo Monitor
# (data/processed/conflitos_24h.csv, janela real de 24h) mais ~1.782 eventos
# buscados ao vivo preservando NumSources (não fica salvo no pipeline normal
# — ver COLUNAS_RESULTADO em ingest/gdelt.py), cobrindo os 3 sinais abaixo.
# Só o primeiro (EventCode) se mostrou útil; os outros dois foram
# investigados e descartados — documentados aqui pra não serem
# re-investigados do zero no futuro.
#
# 1) EventCode (granularidade maior que EventRootCode) — SINAL ÚTIL,
#    aplicado via CODIGOS_EVENTO_COERCE_RUIDO abaixo. Dentro da categoria
#    "17" (COERCE), dois códigos específicos dominam o volume e, amostrando
#    as SOURCEURL reais, são quase inteiramente ruído:
#    - "172" (Impose administrative sanctions/restrições administrativas) —
#      707 de 3.447 eventos de COERCE (20,5%); inclui literalmente o
#      exemplo do bar que motivou essa investigação (notícia local sobre
#      bares abrindo em Portland, Maine, virou 9 "eventos de conflito" —
#      um por local mencionado no texto).
#    - "173" (Arrest, detain, or charge with legal action) — 2.319 de 3.447
#      (67,3%); quase todo crime/julgamento local dos EUA (sentenças,
#      prisões por tráfico, etc.) sem relação com risco geopolítico.
#    Juntos, 172+173 = 87,8% do volume de COERCE. Checagem de palavra-chave
#    de conflito ("war/attack/military/killed/...") nas 1.412 SOURCEURL
#    únicas desses dois códigos: só 7,2% continham algum termo, e a leitura
#    manual mostrou que a maioria mesmo assim era falso positivo (op-ed,
#    "bomb bomb bar" — nome de restaurante, política doméstica de
#    impeachment) — perda real de sinal genuíno é bem menor que isso. Os
#    demais códigos de COERCE (170, 171x, 174, 175, 172x/1724) somam só
#    12,2% do volume e são mais mistos (ex: choques na RD Congo, apreensão
#    de barco iranês, estado de emergência) — mantidos sem filtro adicional.
#    ASSAULT (18) e FIGHT (19) não mostraram esse padrão de concentração —
#    amostrados e já majoritariamente violência física real (força militar,
#    confronto armado, assassinato) — sem refinamento adicional por ora.
# 2) NumSources — INVESTIGADO, NÃO aplicado como filtro. Vale 1 em 98,3%
#    dos eventos de ruído (172/173) E em 98,0% dos eventos de conflito real
#    (raiz 19) — sem poder de separação nos dados do GDELT 2.0 gratuito
#    (campo pouco populado mesmo pra notícias com múltiplas fontes reais).
#    Um corte tipo NumSources >= 2 descartaria ~98% de TUDO, ruído e sinal
#    genuíno juntos — pior que não filtrar nada.
# 3) AvgTone — INVESTIGADO, NÃO aplicado como filtro. Direção OPOSTA à
#    esperada: o grupo de ruído (172/173) teve tom mediano MAIS negativo
#    (-5,0) que o grupo de conflito real da raiz 19 (-3,9) — crime local
#    (sentença de homicídio, tráfico) carrega tom tão ou mais negativo que
#    conflito geopolítico genuíno, sem ser o risco que o projeto monitora.
#    Um corte por tom mais negativo pegaria preferencialmente RUÍDO, não
#    conflito real — na direção contrária do que se buscava.
CODIGOS_EVENTO_COERCE_RUIDO = {"172", "173"}

# --- Filtro por seção da URL (2026-09-18) ---
#
# Achado real depois do filtro acima já em produção: a notícia
# "couple bought Marilyn Monroe's former home... to tear it down" (disputa
# imobiliária/preservação histórica, zero relação com conflito geopolítico)
# passou pelo filtro de EventCode. Investigando: o GDELT deu a ela
# EventCode "190" — dentro de FIGHT (19), não COERCE — o código "genérico"
# de "Use conventional military force", pra quando o classificador não
# consegue ser mais específico.
#
# Diferente de "172"/"173" (concentrados e majoritariamente ruído), "190"
# é MISTO e enorme: 859 de 2.023 eventos já capturados (42,5% de TUDO, não
# só de FIGHT) — amostrando as URLs reais, tem tanto sinal genuíno forte
# ("Houthis seize Red Sea islands, oil supply risks", "Russian drone found
# off Poland coast carried explosive warhead", "Russian intelligence plot
# to commit murder-for-hire in the US foiled by FBI") quanto ruído puro
# (a casa da Marilyn Monroe, batida de helicóptero em LA, briga de
# clube náutico, fofoca de celebridade). Excluir "190" inteiro pelo
# EventCode cortaria quase metade de TODO o sinal do Monitor, sinal
# genuíno junto — abordagem errada aqui (diferente de CODIGOS_EVENTO_COERCE_RUIDO
# acima, onde o corte por EventCode era limpo).
#
# Solução: filtrar pela SEÇÃO da URL de origem (primeiro segmento do path,
# ex: "real-estate" em .../real-estate/news/...) em vez do EventCode —
# ataca o ruído pela editoria do site (imóveis, entretenimento, esporte,
# etc.), não pela classificação CAMEO do evento. Lista abaixo construída
# investigando TODOS os ~520 segmentos distintos presentes nos 2.023
# eventos já capturados: cada seção só entrou depois de amostrar as URLs
# reais daquele segmento e confirmar que é inequivocamente não-geopolítico
# (checagem final: aplicando a lista completa contra os 2.023 eventos,
# as 34 linhas afetadas são 100% ruído do mesmo tipo, nenhum falso
# positivo). Descartei candidatos ambíguos mesmo quando pareciam óbvios à
# primeira vista — ex: "theaters" (seção do Stars & Stripes, jornal
# militar — lá significa "teatro de operações militares", não cinema;
# incluiria pra excluir e cortaria notícia real de tropas) e "shows"
# (uma amostra era true crime irrelevante, outra era um clipe do PBS
# Newshour sobre "war with Iran") — ambíguos demais pra generalizar sem
# mais dados, diferente das seções abaixo, todas de tópico único e claro.
# "astrology"/"horoscope"/"sports"/"sport"/"recipe" não apareceram nos
# dados atuais (0 eventos) — mantidos mesmo assim por serem categorias
# estruturalmente não-geopolíticas (mesmo raciocínio das que apareceram),
# não uma extrapolação de amostra.
SECOES_URL_RUIDO = {
    "real-estate",
    "entertainment",
    "entertainment_life",
    "life-style",
    "lifestyle",
    "sports",
    "sport",
    "mlb",
    "horse-racing",
    "astrology",
    "horoscope",
    "recipes",
    "recipe",
    "dining",
    "celebrities",
    "celebrity-news",
    "gay-celebrities",
    "showbiz",
    "tvshowbiz",
    "us-showbiz",
    "movies",
    "tv",
    "music",
    "comics",
    "on-screen",
    "vertical-galleries",
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

# --- Monitor de conflitos: escopo de países relevantes por setor (2026-09-16) ---
#
# Toda ação tem o Brasil como país relevante por padrão — é uma empresa
# brasileira, risco doméstico (greve, instabilidade política, crise
# cambial etc.) afeta qualquer setor, independente do que a empresa
# produz ou vende. Ações de setores ligados a uma commodity específica
# ganham PAÍSES ADICIONAIS: os principais produtores/exportadores daquela
# commodity, porque conflito ou instabilidade nesses países pode afetar
# preço/oferta global e, por tabela, o valuation da ação (ex: petróleo:
# escalada no Oriente Médio tende a subir o Brent, o que muda a tese de
# investimento em PETR4 mesmo sem nenhum evento em solo brasileiro).
#
# Códigos no padrão FIPS 10-4 — o mesmo usado pelo campo
# ActionGeo_CountryCode do GDELT (ver ingest/gdelt.py), que DIFERE do ISO
# 3166 pra vários países relevantes aqui (ex: Rússia é "RS" não "RU",
# Iraque é "IZ" não "IQ", China é "CH" não "CN", Austrália é "AS" não
# "AU", África do Sul é "SF" não "ZA", Ucrânia é "UP" não "UA", Kuwait é
# "KU" não "KW"). O código do Brasil ("BR") foi confirmado contra dado
# REAL baixado do GDELT em 2026-09-15: o evento do snapshot
# 20260915074500 traz ActionGeo_CountryCode="BR" junto com
# ActionGeo_FullName="Brazil". Os demais códigos foram checados contra a
# tabela de referência FIPS 10-4 -> ISO 3166
# (github.com/mysociety/gaze/blob/master/data/fips-10-4-to-iso-country-codes.csv),
# um crosswalk público amplamente usado — não adivinhados a partir do
# código ISO.
CODIGO_GDELT_BRASIL = "BR"

# Petróleo: união dos maiores produtores de petróleo cru — EUA, Rússia,
# Arábia Saudita, Canadá, Iraque, China, Irã, Emirados Árabes Unidos e
# Kuwait (fonte: EIA/U.S. Energy Information Administration, dados de
# 2025, via Forbes "Top 10 Oil-Producing Countries In The World,
# According To The EIA", 2026-07-16) — com os maiores exportadores —
# Arábia Saudita, Rússia, EUA, Canadá, EAU, Noruega, Irã, Nigéria e
# Cazaquistão (fonte: World Population Review, "Oil Exports by Country",
# dados de 2024). Brasil já está coberto pela regra padrão acima (e é,
# ele mesmo, um produtor relevante — via OPEP+), por isso não repetido
# aqui.
PAISES_PRODUTORES_PETROLEO_GDELT = {
    "US",  # Estados Unidos
    "RS",  # Rússia
    "SA",  # Arábia Saudita
    "CA",  # Canadá
    "IZ",  # Iraque
    "CH",  # China
    "IR",  # Irã
    "AE",  # Emirados Árabes Unidos
    "KU",  # Kuwait
    "NO",  # Noruega
    "NI",  # Nigéria
    "KZ",  # Cazaquistão
}

# Minério de ferro: união dos maiores produtores — Austrália, China,
# Índia, Rússia, Irã, África do Sul, Canadá, EUA e Ucrânia (fonte: USGS
# "Mineral Commodity Summaries", dados 2022-24, via Wikipedia "List of
# countries by iron ore production") — com os maiores exportadores por
# volume/valor — Austrália, África do Sul, Canadá e Ucrânia (fonte:
# worldstopexports.com "Iron Ore Exports by Country", dados 2025 YTD/
# valor 2024). Brasil já coberto pela regra padrão (e é, ele mesmo, o
# 2º maior exportador global, atrás só da Austrália).
PAISES_PRODUTORES_MINERIO_FERRO_GDELT = {
    "AS",  # Austrália
    "CH",  # China
    "IN",  # Índia
    "RS",  # Rússia
    "IR",  # Irã
    "SF",  # África do Sul
    "CA",  # Canadá
    "US",  # Estados Unidos
    "UP",  # Ucrânia
}

# Segmentos setoriais (campo `segmento_setorial` de ingest/crosswalk_cnpj.py,
# a classificação oficial da B3) que disparam cada conjunto de países
# extras acima. Valores conferidos contra o catálogo real de emissores da
# B3 pras 76 ações do Ibovespa em 2026-09-16.
#
# "Distribuição de Combustíveis" (ex: VBBR3/Vibra Energia) entra junto
# com "Exploração. Refino e Distribuição" (ex: PETR4/PRIO3) porque a
# margem de uma distribuidora de combustível também depende do preço do
# petróleo cru, mesmo sem operação de exploração própria.
SEGMENTOS_SETORIAIS_PETROLEO_GAS = {
    "Exploração. Refino e Distribuição",
    "Distribuição de Combustíveis",
}

# "Siderurgia" (ex: CSNA3) entra junto com "Minerais Metálicos" (ex:
# VALE3) porque siderúrgicas brasileiras — CSN em particular — são
# conhecidas por operar minas de minério de ferro próprias (ex: mina de
# Casa de Pedra da CSN, em Minas Gerais), além de consumirem minério como
# insumo principal: o setor inteiro fica exposto a choques de oferta/
# preço do minério, não só quem extrai puro.
SEGMENTOS_SETORIAIS_MINERACAO_METALICOS = {
    "Minerais Metálicos",
    "Siderurgia",
}

# --- Mapa do monitor de conflitos (2026-09-16) ---
#
# Escala de Goldstein (Goldstein, 1992, "A Conflict-Cooperation Scale for
# WEIS Events Data") — de -10 (mais conflituoso) a +10 (mais cooperativo).
# O GDELT usa essa mesma escala pro campo GoldsteinScale (ver
# ingest/gdelt.py). Usado como range FIXO (não dinâmico por busca) pra
# normalizar cor/tamanho dos marcadores de evento no mapa — assim o
# significado de uma cor/tamanho é sempre o mesmo entre buscas diferentes,
# não relativo só aos eventos daquela busca específica.
GOLDSTEIN_SCALE_MINIMO = -10.0
GOLDSTEIN_SCALE_MAXIMO = 10.0

# Pontos estratégicos (estreitos/canais) marcados no mapa como contexto
# fixo, sem dado ao vivo — os mesmos 5 principais "chokepoints" de
# petróleo do mundo citados pela EIA (U.S. Energy Information
# Administration) em "World Oil Transit Chokepoints"
# (eia.gov/todayinenergy/detail.php?id=18991): Estreito de Ormuz, Canal
# de Suez, Bab-el-Mandeb, Estreito de Malaca e Canal do Panamá.
#
# Coordenadas: Ormuz, Suez e Bab-el-Mandeb vêm direto da caixa de
# coordenadas do artigo da Wikipédia de cada um (checado em 2026-09-16).
# O Estreito de Malaca não tem um único ponto na Wikipédia — é definido
# por dois pares de limites (o corpo d'água é extenso) — então foi usado
# o ponto médio do par de limites do lado leste/mais estreito (perto de
# Singapura: Tanjong Piai 1°16′N 103°31′E e The Brothers 1°11.5′N
# 103°21′E), onde fica o gargalo de navegação mais crítico (canal de
# Phillips, ~2,8 km de largura).
PONTOS_ESTRATEGICOS_MAPA_CONFLITOS = [
    {"nome": "Estreito de Ormuz", "lat": 26.6, "lon": 56.5},
    {"nome": "Canal de Suez", "lat": 30.705, "lon": 32.344},
    {"nome": "Estreito de Bab-el-Mandeb", "lat": 12.583, "lon": 43.333},
    {"nome": "Estreito de Malaca", "lat": 1.23, "lon": 103.43},
    {"nome": "Canal do Panamá", "lat": 9.12, "lon": -79.75},
]
