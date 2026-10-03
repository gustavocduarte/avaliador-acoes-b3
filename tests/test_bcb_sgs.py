import json
import logging
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import _retry, bcb_sgs, ibge_sidra


def test_montar_url_sem_datas():
    url = bcb_sgs._montar_url(11, None, None)
    assert url == "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json"


def test_montar_url_com_datas():
    url = bcb_sgs._montar_url(432, "01/01/2024", "01/03/2024")
    assert "dataInicial=01/01/2024" in url
    assert "dataFinal=01/03/2024" in url


def test_parsear_resposta_valida():
    texto = '[{"data":"01/01/2024","valor":"11.75"}]'
    registros = bcb_sgs._parsear_resposta(texto, codigo=432)
    assert registros == [{"data": "01/01/2024", "valor": "11.75"}]


def test_parsear_resposta_invalida_levanta_erro_claro():
    texto_html = "<html><body>Requisição inválida!</body></html>"
    with pytest.raises(ValueError, match="série 999999999"):
        bcb_sgs._parsear_resposta(texto_html, codigo=999999999)


def test_registros_para_dataframe_tipos_e_ordenacao():
    registros = [
        {"data": "02/01/2024", "valor": "11.25"},
        {"data": "01/01/2024", "valor": "11.75"},
    ]
    df = bcb_sgs._registros_para_dataframe(registros)

    assert list(df["data"]) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert list(df["valor"]) == [11.75, 11.25]
    assert df["valor"].dtype == float


def test_registros_para_dataframe_vazio():
    df = bcb_sgs._registros_para_dataframe([])
    assert df.empty
    assert list(df.columns) == ["data", "valor"]


def test_caminho_cache_sem_datas_nao_tem_sufixo_de_janela(tmp_path):
    # Compatibilidade com o único caso onde isso era chamado sem datas
    # até agora (testes) — todo chamador real (app/main.py) sempre passa
    # data_inicial/data_final.
    caminho = bcb_sgs._caminho_cache(432, None, None, tmp_path)
    assert caminho.name == "serie_432.csv"


def test_caminho_cache_inclui_janela_quando_datas_sao_passadas(tmp_path):
    caminho = bcb_sgs._caminho_cache(432, "01/01/2024", "01/03/2024", tmp_path)
    assert caminho.name == "serie_432_01-01-2024_01-03-2024.csv"


def test_caminho_cache_janelas_diferentes_geram_arquivos_diferentes(tmp_path):
    # Regressão: essa era a causa raiz do bug real — duas janelas
    # diferentes pro mesmo código de série precisam virar dois arquivos de
    # cache diferentes, senão uma busca com janela rolante (ex:
    # app/main.py._buscar_cambio_correlacao, recalculada a cada execução a
    # partir de "hoje") fica presa pra sempre na janela do primeiro fetch.
    caminho_1 = bcb_sgs._caminho_cache(432, "01/01/2024", "01/03/2024", tmp_path)
    caminho_2 = bcb_sgs._caminho_cache(432, "15/06/2024", "15/08/2024", tmp_path)
    assert caminho_1 != caminho_2


def test_obter_serie_janelas_diferentes_nao_compartilham_cache(tmp_path, monkeypatch):
    # Fim a fim: duas janelas diferentes do mesmo código de série batem na
    # rede duas vezes (não reaproveitam o cache uma da outra), e reler a
    # mesma janela de novo volta a usar cache.
    respostas_por_chamada = []

    class RespostaFalsa:
        def __init__(self, texto):
            self.text = texto

        def raise_for_status(self):
            pass

    def get_falso(url, timeout):
        respostas_por_chamada.append(url)
        return RespostaFalsa('[{"data":"01/01/2024","valor":"11.75"}]')

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)

    bcb_sgs.obter_serie(432, "01/01/2024", "01/03/2024", diretorio_cache=tmp_path)
    bcb_sgs.obter_serie(432, "15/06/2024", "15/08/2024", diretorio_cache=tmp_path)
    # Reler a primeira janela: deve vir do cache, não bater na rede de novo.
    bcb_sgs.obter_serie(432, "01/01/2024", "01/03/2024", diretorio_cache=tmp_path)

    assert len(respostas_por_chamada) == 2
    assert (tmp_path / "bcb" / "serie_432_01-01-2024_01-03-2024.csv").exists()
    assert (tmp_path / "bcb" / "serie_432_15-06-2024_15-08-2024.csv").exists()


def test_obter_serie_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    class RespostaFalsa:
        text = '[{"data":"01/01/2024","valor":"11.75"}]'

        def raise_for_status(self):
            pass

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return RespostaFalsa()

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)

    df1 = bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)
    df2 = bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1
    pd.testing.assert_frame_equal(df1, df2)
    assert (tmp_path / "bcb" / "serie_432.csv").exists()


def test_obter_serie_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    chamadas = {"contador": 0}

    class RespostaFalsa:
        text = '[{"data":"01/01/2024","valor":"11.75"}]'

        def raise_for_status(self):
            pass

    def get_falso(url, timeout):
        chamadas["contador"] += 1
        return RespostaFalsa()

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)

    bcb_sgs.obter_serie(432, diretorio_cache=tmp_path)
    bcb_sgs.obter_serie(432, diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2


# --- _get_com_retry: nova tentativa em falha temporária ---------------------


class _Resposta:
    def __init__(self, status_code, texto="", headers=None):
        self.status_code = status_code
        self.text = texto
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"erro {self.status_code}", response=self)


def test_get_com_retry_502_depois_sucesso_usa_o_valor_novo(monkeypatch):
    chamadas = {"n": 0}

    def get_falso(url, timeout):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return _Resposta(502)
        return _Resposta(200, '[{"data":"01/01/2024","valor":"11.75"}]')

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: None)

    resposta = bcb_sgs._get_com_retry("https://exemplo")

    assert chamadas["n"] == 2
    assert resposta.status_code == 200


def test_get_com_retry_502_persistente_espera_2_e_5_segundos_e_desiste(monkeypatch):
    chamadas = {"n": 0}
    pausas = []

    def get_falso(url, timeout):
        chamadas["n"] += 1
        return _Resposta(502)

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: pausas.append(segundos))

    with pytest.raises(requests.HTTPError):
        bcb_sgs._get_com_retry("https://exemplo")

    assert chamadas["n"] == 3  # tentativa original + 2 novas
    assert pausas == [2, 5]


def test_get_com_retry_404_nao_tenta_de_novo(monkeypatch):
    chamadas = {"n": 0}

    def get_falso(url, timeout):
        chamadas["n"] += 1
        return _Resposta(404)

    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: None)

    with pytest.raises(requests.HTTPError):
        bcb_sgs._get_com_retry("https://exemplo")

    assert chamadas["n"] == 1


def _get_429_depois_sucesso(headers):
    chamadas = {"n": 0}

    def get_falso(url, timeout):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return _Resposta(429, headers=headers)
        return _Resposta(200, '[{"data":"01/01/2024","valor":"11.75"}]')

    return chamadas, get_falso


def test_get_com_retry_429_depois_sucesso_usa_o_valor_novo(monkeypatch):
    chamadas, get_falso = _get_429_depois_sucesso({})
    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: None)

    resposta = bcb_sgs._get_com_retry("https://exemplo")

    assert chamadas["n"] == 2
    assert resposta.status_code == 200


def test_get_com_retry_429_respeita_retry_after_em_segundos(monkeypatch):
    _, get_falso = _get_429_depois_sucesso({"Retry-After": "12"})
    pausas = []
    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: pausas.append(segundos))

    bcb_sgs._get_com_retry("https://exemplo")

    assert pausas == [12]


def test_get_com_retry_429_retry_after_limitado_ao_teto_de_30_segundos(monkeypatch):
    _, get_falso = _get_429_depois_sucesso({"Retry-After": "600"})
    pausas = []
    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: pausas.append(segundos))

    bcb_sgs._get_com_retry("https://exemplo")

    assert pausas == [30]


@pytest.mark.parametrize("retry_after", [{}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}])
def test_get_com_retry_429_sem_retry_after_numerico_usa_a_pausa_padrao(monkeypatch, retry_after):
    _, get_falso = _get_429_depois_sucesso(retry_after)
    pausas = []
    monkeypatch.setattr(bcb_sgs.requests, "get", get_falso)
    monkeypatch.setattr(_retry.time, "sleep", lambda segundos: pausas.append(segundos))

    bcb_sgs._get_com_retry("https://exemplo")

    assert pausas == [2]


# --- obter_selic_e_ipca: valor guardado como último recurso -----------------


def _bcb_falho(*args, **kwargs):
    raise RuntimeError("BCB fora do ar (simulado)")


def _semear_ultimo_macro(diretorio_cache, dias_atras: int) -> None:
    caminho = diretorio_cache / "bcb" / "ultimo_macro.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    data_busca = datetime.now() - timedelta(days=dias_atras)
    caminho.write_text(
        json.dumps(
            {
                "selic_meta": 0.1375,
                "ipca_12m": 0.045,
                "data_ipca": "2026-08-01",
                "data_busca": data_busca.isoformat(),
            }
        )
    )


def test_salvar_e_carregar_ultimo_macro_ida_e_volta(tmp_path):
    data_busca = datetime(2026, 9, 15, 14, 30)
    bcb_sgs._salvar_ultimo_macro(tmp_path, 0.1375, 0.045, pd.Timestamp("2026-08-01"), data_busca)

    carregado = bcb_sgs._carregar_ultimo_macro(tmp_path)

    assert carregado["selic_meta"] == pytest.approx(0.1375)
    assert carregado["ipca_12m"] == pytest.approx(0.045)
    assert carregado["data_ipca"] == pd.Timestamp("2026-08-01")
    assert carregado["data_busca"] == pd.Timestamp(data_busca)


def test_obter_selic_e_ipca_usa_valor_guardado_recente_quando_bcb_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca", _bcb_falho)
    _semear_ultimo_macro(tmp_path, dias_atras=10)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert resultado.selic_meta == pytest.approx(0.1375)
    assert resultado.ipca_12m == pytest.approx(0.045)


def test_obter_selic_e_ipca_ignora_valor_guardado_com_mais_de_45_dias(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca", _bcb_falho)
    _semear_ultimo_macro(tmp_path, dias_atras=46)

    with (
        pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"),
        pytest.raises(bcb_sgs.MacroIndisponivelError),
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def test_obter_selic_e_ipca_sem_valor_guardado_mensagem_amigavel(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca", _bcb_falho)

    with (
        pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"),
        pytest.raises(bcb_sgs.MacroIndisponivelError) as excinfo,
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    mensagem = str(excinfo.value)
    assert mensagem == bcb_sgs.MENSAGEM_MACRO_INDISPONIVEL
    assert "api.bcb.gov.br" not in mensagem


def test_ipca_com_menos_de_12_meses_levanta_erro(tmp_path, monkeypatch):
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-08-01")], "valor": [13.75]})
    ipca_df = pd.DataFrame(
        {"data": pd.date_range("2026-01-01", periods=5, freq="MS"), "valor": [0.3] * 5}
    )

    def obter_serie_falso(codigo, **kwargs):
        return selic_df if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"] else ipca_df

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)

    with pytest.raises(bcb_sgs.DadosMacroInsuficientesError, match="5 leitura"):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def test_ipca_incompleto_em_todas_as_fontes_cai_no_valor_guardado_recente(tmp_path, monkeypatch):
    # IPCA com menos de 12 meses conta como falha da fonte: a cadeia tenta a próxima e, sem
    # nenhuma que traga os 12 meses, usa o valor guardado recente.
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-08-01")], "valor": [13.75]})
    ipca_df = pd.DataFrame(
        {"data": pd.date_range("2026-01-01", periods=5, freq="MS"), "valor": [0.3] * 5}
    )

    def obter_serie_falso(codigo, **kwargs):
        return selic_df if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"] else ipca_df

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)
    _semear_ultimo_macro(tmp_path, dias_atras=1)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert resultado.ipca_12m == pytest.approx(0.045)


# --- Segunda fonte: SOAP do SGS no www3 do BCB -------------------------------

CAMINHO_FIXTURES = Path(__file__).parent / "fixtures"
HOJE_FIXO = datetime(2026, 10, 3, 12, 0)


def _soap_selic() -> str:
    return (CAMINHO_FIXTURES / "bcb_soap_selic_meta_com_datas_futuras.xml").read_text("utf-8")


def _soap_ipca() -> str:
    return (CAMINHO_FIXTURES / "bcb_soap_ipca_mensal.xml").read_text("utf-8")


class _RespostaSoapFalsa:
    def __init__(self, texto):
        self.text = texto


def _soap_responde(monkeypatch, selic=None, ipca=None, chamadas=None):
    """Substitui o POST do SOAP: devolve o XML gravado da série pedida."""

    def post(url, timeout, pausas, data, headers):
        corpo = data.decode("utf-8")
        if chamadas is not None:
            chamadas.append(corpo)
        if ">432<" in corpo:
            return _RespostaSoapFalsa(selic if selic is not None else _soap_selic())
        return _RespostaSoapFalsa(ipca if ipca is not None else _soap_ipca())

    monkeypatch.setattr(bcb_sgs, "post_com_retry", post)


def _rest_fora_do_ar(monkeypatch, chamadas=None):
    def obter_serie_falso(codigo, *args, **kwargs):
        if chamadas is not None:
            chamadas.append(codigo)
        raise requests.ConnectionError("api.bcb.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)


def test_parsear_resposta_soap_da_selic_traz_as_datas_futuras_como_o_servico_devolve():
    registros = bcb_sgs._parsear_resposta_soap(_soap_selic(), 432)

    assert len(registros) == 38
    assert registros[0] == {"data": "28/09/2026", "valor": "13.75"}
    assert registros[-1] == {"data": "04/11/2026", "valor": "13.75"}


def test_parsear_resposta_soap_do_ipca_mensal_usa_o_dia_1_do_mes():
    registros = bcb_sgs._parsear_resposta_soap(_soap_ipca(), 433)

    assert len(registros) == 14
    assert registros[0] == {"data": "01/07/2025", "valor": "0.26"}
    assert registros[-1] == {"data": "01/08/2026", "valor": "-0.32"}


@pytest.mark.parametrize("texto", ["isso não é xml", "<a><b/></a>", ""])
def test_parsear_resposta_soap_sem_valores_levanta_erro_claro(texto):
    with pytest.raises(ValueError, match="série 432"):
        bcb_sgs._parsear_resposta_soap(texto, 432)


def test_obter_serie_soap_pede_a_serie_e_as_datas_e_devolve_o_dataframe(monkeypatch):
    chamadas = []
    _soap_responde(monkeypatch, chamadas=chamadas)

    df = bcb_sgs.obter_serie_soap(433, "01/07/2025", "03/10/2026")

    assert list(df.columns) == ["data", "valor"]
    assert len(df) == 14
    assert df["valor"].iloc[-1] == pytest.approx(-0.32)
    assert "<item xsi:type=\"xsd:long\">433</item>" in chamadas[0]
    assert "<in1>01/07/2025</in1><in2>03/10/2026</in2>" in chamadas[0]


def test_ate_hoje_ignora_as_datas_posteriores_a_hoje():
    df = bcb_sgs._registros_para_dataframe(bcb_sgs._parsear_resposta_soap(_soap_selic(), 432))

    ate_hoje = bcb_sgs._ate_hoje(df, HOJE_FIXO)

    assert ate_hoje["data"].max() == pd.Timestamp("2026-10-03")
    assert len(ate_hoje) == 6  # 28/09 a 03/10


def test_rest_falha_e_soap_responde_selic_e_ipca_vem_do_soap(monkeypatch, tmp_path, caplog):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="avaliador_b3.ingest.bcb_sgs"):
        selic, ipca, data_ipca, fonte_selic, fonte_ipca = bcb_sgs._buscar_selic_e_ipca(
            HOJE_FIXO, tmp_path
        )

    assert selic == pytest.approx(0.1375)
    assert ipca == pytest.approx(0.042234527370682784)
    assert data_ipca == pd.Timestamp("2026-08-01")
    assert (fonte_selic, fonte_ipca) == ("BCB (SOAP)", "BCB (SOAP)")
    # A falha do REST vai para o log, não para um aviso do Python.
    assert "Falha ao buscar Selic/IPCA do BCB (API)" in caplog.text


def test_falha_intermediaria_de_uma_fonte_nao_emite_aviso_do_python(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.fonte_selic == "BCB (SOAP)"


def test_soap_ignora_datas_futuras_da_selic_na_cadeia(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)
    df = bcb_sgs._registros_para_dataframe(bcb_sgs._parsear_resposta_soap(_soap_selic(), 432))
    df.loc[df["data"] > pd.Timestamp("2026-10-03"), "valor"] = 99.0  # só as futuras
    original = bcb_sgs.obter_serie_soap

    def soap_com_futuras_alteradas(codigo, data_inicial, data_final):
        return df if codigo == 432 else original(codigo, data_inicial, data_final)

    monkeypatch.setattr(bcb_sgs, "obter_serie_soap", soap_com_futuras_alteradas)
    _soap_responde(monkeypatch)

    selic = bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)[0]

    assert selic == pytest.approx(0.1375)


def test_rest_fora_do_ar_e_abandonado_no_ipca_depois_de_falhar_na_selic(monkeypatch, tmp_path):
    codigos_pedidos_ao_rest = []
    _rest_fora_do_ar(monkeypatch, chamadas=codigos_pedidos_ao_rest)
    _soap_responde(monkeypatch)

    bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    assert codigos_pedidos_ao_rest == [432]  # o IPCA (433) nem tenta o REST


def test_selic_pelo_rest_e_ipca_pelo_soap_quando_so_o_ipca_falha_no_rest(monkeypatch, tmp_path):
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-10-01")], "valor": [13.75]})

    def obter_serie_falso(codigo, *args, **kwargs):
        if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"]:
            return selic_df
        raise requests.ConnectionError("IPCA fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)
    _soap_responde(monkeypatch)

    resultado = bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    assert resultado[3:] == ("BCB (API)", "BCB (SOAP)")


def test_rest_com_ipca_incompleto_e_soap_completo_usa_o_soap(monkeypatch, tmp_path, caplog):
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-10-01")], "valor": [13.75]})
    ipca_incompleto = pd.DataFrame(
        {"data": pd.date_range("2026-04-01", periods=5, freq="MS"), "valor": [0.3] * 5}
    )

    def obter_serie_falso(codigo, *args, **kwargs):
        if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"]:
            return selic_df
        return ipca_incompleto

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)
    _soap_responde(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="avaliador_b3.ingest.bcb_sgs"):
        resultado = bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    selic, ipca, data_ipca, fonte_selic, fonte_ipca = resultado
    assert ipca == pytest.approx(0.042234527370682784)  # os 12 meses completos do SOAP
    assert (fonte_selic, fonte_ipca) == ("BCB (API)", "BCB (SOAP)")
    assert "IPCA voltou com 5 leitura(s)" in caplog.text


def _sidra_responde(monkeypatch, chamadas=None):
    texto = (CAMINHO_FIXTURES / "ibge_sidra_ipca_mensal.json").read_text("utf-8")

    def sidra(meses):
        if chamadas is not None:
            chamadas.append(meses)
        return ibge_sidra._parsear_resposta_sidra(texto)

    monkeypatch.setattr(bcb_sgs, "obter_ipca_mensal_sidra", sidra)


def _selic_rest_ok_e_ipca_rest_fora(monkeypatch):
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-10-01")], "valor": [13.75]})

    def obter_serie_falso(codigo, *args, **kwargs):
        if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"]:
            return selic_df
        raise requests.ConnectionError("IPCA fora do ar no REST (simulado)")

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)


def _soap_ipca_fora_do_ar(monkeypatch):
    def post(url, timeout, pausas, data, headers):
        if ">433<" in data.decode("utf-8"):
            raise requests.ConnectionError("IPCA fora do ar no SOAP (simulado)")
        return _RespostaSoapFalsa(_soap_selic())

    monkeypatch.setattr(bcb_sgs, "post_com_retry", post)


def test_rest_e_soap_do_ipca_falham_e_o_sidra_responde(monkeypatch, tmp_path, caplog):
    _selic_rest_ok_e_ipca_rest_fora(monkeypatch)
    _soap_ipca_fora_do_ar(monkeypatch)
    _sidra_responde(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="avaliador_b3.ingest.bcb_sgs"):
        selic, ipca, data_ipca, fonte_selic, fonte_ipca = bcb_sgs._buscar_selic_e_ipca(
            HOJE_FIXO, tmp_path
        )

    assert ipca == pytest.approx(0.042234527370682784)
    assert data_ipca == pd.Timestamp("2026-08-01")  # o mês de referência vem junto
    assert (fonte_selic, fonte_ipca) == ("BCB (API)", "IBGE (SIDRA)")
    assert "do BCB (SOAP)" in caplog.text


def test_selic_pelo_soap_e_ipca_pelo_sidra_quando_o_ipca_falha_no_bcb_inteiro(
    monkeypatch, tmp_path
):
    _rest_fora_do_ar(monkeypatch)
    _soap_ipca_fora_do_ar(monkeypatch)
    _sidra_responde(monkeypatch)

    resultado = bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    assert resultado[0] == pytest.approx(0.1375)
    assert resultado[3:] == ("BCB (SOAP)", "IBGE (SIDRA)")


def test_ipca_incompleto_no_rest_e_no_soap_cai_no_sidra_completo(monkeypatch, tmp_path):
    ipca_incompleto = pd.DataFrame(
        {"data": pd.date_range("2026-04-01", periods=5, freq="MS"), "valor": [0.3] * 5}
    )
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-10-01")], "valor": [13.75]})

    def obter_serie_falso(codigo, *args, **kwargs):
        if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"]:
            return selic_df
        return ipca_incompleto

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)
    _soap_responde(monkeypatch, ipca=_soap_ipca_so_com_os_ultimos_meses())
    _sidra_responde(monkeypatch)

    resultado = bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    assert resultado[1] == pytest.approx(0.042234527370682784)
    assert resultado[3:] == ("BCB (API)", "IBGE (SIDRA)")


def test_sidra_nao_e_consultado_quando_o_soap_traz_o_ipca(monkeypatch, tmp_path):
    chamadas_sidra = []
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)
    _sidra_responde(monkeypatch, chamadas=chamadas_sidra)

    bcb_sgs._buscar_selic_e_ipca(HOJE_FIXO, tmp_path)

    assert chamadas_sidra == []


def test_sidra_so_pede_o_ipca_e_a_selic_nao_tem_fonte_equivalente(monkeypatch, tmp_path):
    # BCB inteiro fora do ar: sem Selic, o SIDRA sozinho não resolve e cai no valor guardado.
    chamadas_sidra = []
    _rest_fora_do_ar(monkeypatch)

    def soap_fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("www3.bcb.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", soap_fora_do_ar)
    _sidra_responde(monkeypatch, chamadas=chamadas_sidra)
    _semear_ultimo_macro(tmp_path, dias_atras=3)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert chamadas_sidra == []


def test_todas_as_fontes_do_ipca_falham_e_cai_no_valor_guardado(monkeypatch, tmp_path):
    _selic_rest_ok_e_ipca_rest_fora(monkeypatch)
    _soap_ipca_fora_do_ar(monkeypatch)

    def sidra_fora_do_ar(meses):
        raise requests.ConnectionError("apisidra.ibge.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "obter_ipca_mensal_sidra", sidra_fora_do_ar)
    _semear_ultimo_macro(tmp_path, dias_atras=3)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True


def test_obter_selic_e_ipca_com_o_sidra_grava_a_fonte_do_ipca(monkeypatch, tmp_path):
    _selic_rest_ok_e_ipca_rest_fora(monkeypatch)
    _soap_ipca_fora_do_ar(monkeypatch)
    _sidra_responde(monkeypatch)

    resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert (resultado.fonte_selic, resultado.fonte_ipca) == ("BCB (API)", "IBGE (SIDRA)")
    gravado = json.loads((tmp_path / "bcb" / "ultimo_macro.json").read_text())
    assert gravado["fonte_ipca"] == "IBGE (SIDRA)"
    assert gravado["data_ipca"] == "2026-08-01"


def test_obter_selic_e_ipca_pelo_soap_nao_usa_o_valor_guardado_e_grava_as_fontes(
    monkeypatch, tmp_path
):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)
    _semear_ultimo_macro(tmp_path, dias_atras=10)  # existe, mas a fonte viva vem antes

    resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is False
    assert resultado.fonte_selic == resultado.fonte_ipca == "BCB (SOAP)"
    gravado = json.loads((tmp_path / "bcb" / "ultimo_macro.json").read_text())
    assert gravado["fonte_selic"] == gravado["fonte_ipca"] == "BCB (SOAP)"
    assert gravado["selic_meta"] == pytest.approx(0.1375)


def test_rest_e_soap_falham_e_cai_no_valor_guardado_com_a_fonte_e_a_data(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)

    def soap_fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("www3.bcb.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", soap_fora_do_ar)
    _semear_ultimo_macro(tmp_path, dias_atras=10)
    data_esperada = (datetime.now() - timedelta(days=10)).strftime("%d/%m/%Y")

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert resultado.fonte_selic == resultado.fonte_ipca == f"valor guardado de {data_esperada}"


def test_rest_e_soap_falham_sem_valor_guardado_levanta_a_mensagem_amigavel(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)

    def soap_fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("www3.bcb.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", soap_fora_do_ar)

    with (
        pytest.warns(UserWarning),
        pytest.raises(bcb_sgs.MacroIndisponivelError) as excinfo,
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert str(excinfo.value) == bcb_sgs.MENSAGEM_MACRO_INDISPONIVEL


def _semear_referencia(tmp_path, dias_atras: int) -> None:
    resultado = bcb_sgs.ResultadoMacro(
        selic_meta=0.1425,
        ipca_12m=0.05,
        data_ipca=pd.Timestamp("2026-07-01"),
        usou_valor_guardado=False,
        data_busca=pd.Timestamp(datetime.now() - timedelta(days=dias_atras)),
        fonte_selic="BCB (SOAP)",
        fonte_ipca="IBGE (SIDRA)",
    )
    bcb_sgs.salvar_macro_referencia(resultado, tmp_path / "macro_referencia.json")


def _todas_as_fontes_vivas_falham(monkeypatch):
    _rest_fora_do_ar(monkeypatch)

    def fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", fora_do_ar)
    monkeypatch.setattr(bcb_sgs, "obter_ipca_mensal_sidra", fora_do_ar)


def test_tudo_falha_e_o_arquivo_de_referencia_e_usado_com_a_data(monkeypatch, tmp_path):
    _todas_as_fontes_vivas_falham(monkeypatch)
    _semear_referencia(tmp_path, dias_atras=30)
    data_esperada = (datetime.now() - timedelta(days=30)).strftime("%d/%m/%Y")

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert resultado.selic_meta == pytest.approx(0.1425)
    assert resultado.ipca_12m == pytest.approx(0.05)
    assert resultado.fonte_selic == f"arquivo de referência de {data_esperada}"


def test_arquivo_de_referencia_vencido_e_ignorado(monkeypatch, tmp_path):
    _todas_as_fontes_vivas_falham(monkeypatch)
    _semear_referencia(tmp_path, dias_atras=91)

    with (
        pytest.warns(UserWarning),
        pytest.raises(bcb_sgs.MacroIndisponivelError),
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def test_valor_guardado_valido_tem_prioridade_sobre_o_arquivo_de_referencia(
    monkeypatch, tmp_path
):
    _todas_as_fontes_vivas_falham(monkeypatch)
    _semear_ultimo_macro(tmp_path, dias_atras=5)
    _semear_referencia(tmp_path, dias_atras=5)

    with pytest.warns(UserWarning):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.selic_meta == pytest.approx(0.1375)
    assert resultado.fonte_selic.startswith("valor guardado de")


def test_valor_guardado_vencido_cai_no_arquivo_de_referencia(monkeypatch, tmp_path):
    _todas_as_fontes_vivas_falham(monkeypatch)
    _semear_ultimo_macro(tmp_path, dias_atras=46)
    _semear_referencia(tmp_path, dias_atras=60)

    with pytest.warns(UserWarning):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.selic_meta == pytest.approx(0.1425)
    assert resultado.fonte_ipca.startswith("arquivo de referência de")


def test_fonte_viva_tem_prioridade_sobre_o_arquivo_de_referencia(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)
    _semear_referencia(tmp_path, dias_atras=5)

    resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is False
    assert resultado.selic_meta == pytest.approx(0.1375)


def test_arquivo_de_referencia_corrompido_e_ignorado(monkeypatch, tmp_path):
    _todas_as_fontes_vivas_falham(monkeypatch)
    (tmp_path / "macro_referencia.json").write_text("{ não é json", encoding="utf-8")

    with (
        pytest.warns(UserWarning),
        pytest.raises(bcb_sgs.MacroIndisponivelError),
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def _soap_ipca_so_com_os_ultimos_meses():
    ipca_curto = _soap_ipca()
    antigos = ("7/2025", "8/2025", "9/2025", "10/2025", "11/2025", "12/2025", "1/2026")
    for mes in antigos + ("2/2026", "3/2026"):
        ipca_curto = ipca_curto.replace(f"&lt;DATA&gt;{mes}&lt;/DATA&gt;", "")
    return ipca_curto


def test_ipca_incompleto_em_todas_as_fontes_sem_valor_guardado_sobe_o_erro_de_dados(
    monkeypatch, tmp_path
):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch, ipca=_soap_ipca_so_com_os_ultimos_meses())

    with (
        pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"),
        pytest.raises(bcb_sgs.DadosMacroInsuficientesError),
    ):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def test_ipca_incompleto_no_soap_com_valor_guardado_recente_usa_o_guardado(monkeypatch, tmp_path):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch, ipca=_soap_ipca_so_com_os_ultimos_meses())
    _semear_ultimo_macro(tmp_path, dias_atras=1)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True


def test_obter_serie_com_fallback_usa_o_soap_quando_o_rest_falha_e_ignora_datas_futuras(
    monkeypatch, tmp_path, caplog
):
    _rest_fora_do_ar(monkeypatch)
    _soap_responde(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="avaliador_b3.ingest.bcb_sgs"):
        df = bcb_sgs.obter_serie_com_fallback(432, "28/09/2026", "06/11/2026", tmp_path)

    # As leituras de 04/11 só valem se hoje (de verdade) já passou delas.
    assert df["data"].max() <= pd.Timestamp(datetime.now().date())
    assert df["valor"].iloc[-1] == pytest.approx(13.75)
    assert "Falha ao buscar a série 432" in caplog.text


def test_obter_serie_com_fallback_levanta_o_erro_do_rest_quando_o_soap_tambem_falha(
    monkeypatch, tmp_path
):
    _rest_fora_do_ar(monkeypatch)

    def soap_fora_do_ar(*args, **kwargs):
        raise requests.ConnectionError("www3.bcb.gov.br fora do ar (simulado)")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", soap_fora_do_ar)

    with pytest.raises(requests.ConnectionError, match="api.bcb.gov.br"):
        bcb_sgs.obter_serie_com_fallback(1, "01/01/2026", "03/10/2026", tmp_path)


def test_obter_serie_com_fallback_usa_o_rest_quando_ele_responde(monkeypatch, tmp_path):
    esperado = pd.DataFrame({"data": [pd.Timestamp("2026-10-01")], "valor": [5.5]})
    monkeypatch.setattr(bcb_sgs, "obter_serie", lambda *a, **kw: esperado)

    def soap_nao_devia_ser_chamado(*args, **kwargs):
        raise AssertionError("o SOAP não devia ser chamado")

    monkeypatch.setattr(bcb_sgs, "post_com_retry", soap_nao_devia_ser_chamado)

    assert bcb_sgs.obter_serie_com_fallback(1, "01/10/2026", "03/10/2026", tmp_path) is esperado


def test_post_com_retry_502_depois_sucesso_usa_o_valor_novo(monkeypatch):
    pausas = []
    monkeypatch.setattr(_retry.time, "sleep", lambda s: pausas.append(s))
    respostas = iter([502, 200])

    class _R:
        def __init__(self, status):
            self.status_code = status
            self.text = "ok"
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError("erro", response=self)

    monkeypatch.setattr(_retry.requests, "post", lambda url, timeout, **kw: _R(next(respostas)))

    resposta = _retry.post_com_retry("http://x", 10, (2,), data=b"x")

    assert resposta.status_code == 200
    assert pausas == [2]
