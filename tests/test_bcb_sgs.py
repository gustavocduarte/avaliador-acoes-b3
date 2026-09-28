import json
from datetime import datetime, timedelta

import pandas as pd
import pytest
import requests

from avaliador_b3.ingest import bcb_sgs


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
    def __init__(self, status_code, texto=""):
        self.status_code = status_code
        self.text = texto

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
    monkeypatch.setattr(bcb_sgs.time, "sleep", lambda segundos: None)

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
    monkeypatch.setattr(bcb_sgs.time, "sleep", lambda segundos: pausas.append(segundos))

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
    monkeypatch.setattr(bcb_sgs.time, "sleep", lambda segundos: None)

    with pytest.raises(requests.HTTPError):
        bcb_sgs._get_com_retry("https://exemplo")

    assert chamadas["n"] == 1


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
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca_do_bcb", _bcb_falho)
    _semear_ultimo_macro(tmp_path, dias_atras=10)

    with pytest.warns(UserWarning, match="Falha ao buscar Selic/IPCA do BCB"):
        resultado = bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)

    assert resultado.usou_valor_guardado is True
    assert resultado.selic_meta == pytest.approx(0.1375)
    assert resultado.ipca_12m == pytest.approx(0.045)


def test_obter_selic_e_ipca_ignora_valor_guardado_com_mais_de_45_dias(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca_do_bcb", _bcb_falho)
    _semear_ultimo_macro(tmp_path, dias_atras=46)

    with pytest.raises(bcb_sgs.MacroIndisponivelError):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)


def test_obter_selic_e_ipca_sem_valor_guardado_mensagem_amigavel(tmp_path, monkeypatch):
    monkeypatch.setattr(bcb_sgs, "_buscar_selic_e_ipca_do_bcb", _bcb_falho)

    with pytest.raises(bcb_sgs.MacroIndisponivelError) as excinfo:
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


def test_ipca_incompleto_nao_cai_pro_valor_guardado(tmp_path, monkeypatch):
    # Dado insuficiente não é falha de rede — não deve usar o valor
    # guardado mesmo que exista um recente (ver docstring de
    # DadosMacroInsuficientesError).
    selic_df = pd.DataFrame({"data": [pd.Timestamp("2026-08-01")], "valor": [13.75]})
    ipca_df = pd.DataFrame(
        {"data": pd.date_range("2026-01-01", periods=5, freq="MS"), "valor": [0.3] * 5}
    )

    def obter_serie_falso(codigo, **kwargs):
        return selic_df if codigo == bcb_sgs.SERIES_BCB_SGS["selic_meta"] else ipca_df

    monkeypatch.setattr(bcb_sgs, "obter_serie", obter_serie_falso)
    _semear_ultimo_macro(tmp_path, dias_atras=1)

    with pytest.raises(bcb_sgs.DadosMacroInsuficientesError):
        bcb_sgs.obter_selic_e_ipca(diretorio_cache=tmp_path)
