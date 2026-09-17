from pathlib import Path

import pytest
import requests

from avaliador_b3.ingest import fundamentus

DIRETORIO_FIXTURES = Path(__file__).parent / "fixtures"


def _bytes_fixture(nome: str) -> bytes:
    return (DIRETORIO_FIXTURES / nome).read_bytes()


def _html_fixture(nome: str) -> str:
    return _bytes_fixture(nome).decode("iso-8859-1")


class _RespostaFalsa:
    """Imita o suficiente de requests.Response: `.text` decodifica os bytes
    brutos usando `.encoding`, que pode ser reatribuído depois — igual ao
    comportamento real do requests quando o adapter faz
    `resposta.encoding = "iso-8859-1"`."""

    def __init__(self, conteudo_bytes: bytes, status_ok: bool = True, encoding_padrao="utf-8"):
        self._conteudo_bytes = conteudo_bytes
        self._status_ok = status_ok
        self.encoding = encoding_padrao

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("404 Client Error")

    @property
    def text(self):
        return self._conteudo_bytes.decode(self.encoding, errors="replace")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("27,7%", 27.7),
        ("-2,3%", -2.3),
        ("10,35", 10.35),
        ("0,85", 0.85),
        ("1.844.240.000", 1844240000.0),
        ("-", None),
        ("", None),
    ],
)
def test_parse_numero(texto, esperado):
    assert fundamentus._parse_numero(texto) == esperado


def test_extrair_rotulos_valores_contra_pagina_real_petr4():
    html = _html_fixture("fundamentus_petr4.html")
    rotulos_valores = fundamentus._extrair_rotulos_valores(html)

    assert rotulos_valores["ROE"] == "27,7%"
    assert rotulos_valores["Marg. Líquida"] == "24,4%"
    assert rotulos_valores["LPA"] == "10,35"
    assert rotulos_valores["VPA"] == "37,32"
    assert rotulos_valores["Liquidez Corr"] == "0,85"
    assert rotulos_valores["Dív Líq / Patrim"] == "0,65"
    assert rotulos_valores["Cres. Rec (5a)"] == "-2,3%"
    assert rotulos_valores["Nro. Ações"] == "12.888.700.000"
    # Valor de Mercado/Valor de Firma: confirmado presente na página real
    # (2026-09-17) — "Dív. Líquida" bate com "Dív. Bruta" - "Disponibilidades"
    # (366.533.000.000 - 53.764.000.000), não é um número arbitrário.
    assert rotulos_valores["Patrim. Líq"] == "480.950.000.000"
    assert rotulos_valores["Dív. Líquida"] == "312.769.000.000"


def test_extrair_rotulos_valores_contra_pagina_real_itub4_banco_sem_divida_liquida():
    # Diferente de PETR4: confirmado que "Dív. Líquida" simplesmente não
    # existe como rótulo na página de um banco (nem "-", ausente mesmo) —
    # "Dív Líq / Patrim" continua presente, só com valor "-". Fixture
    # real capturada em 2026-09-17.
    html = _html_fixture("fundamentus_itub4.html")
    rotulos_valores = fundamentus._extrair_rotulos_valores(html)

    assert rotulos_valores["Dív Líq / Patrim"] == "-"
    assert rotulos_valores["Patrim. Líq"] == "207.648.000.000"
    assert "Dív. Líquida" not in rotulos_valores


def test_extrair_rotulos_valores_pagina_de_ticker_invalido_fica_vazia():
    html = _html_fixture("fundamentus_ticker_invalido.html")
    assert fundamentus._extrair_rotulos_valores(html) == {}


def _rotulos_valores_completos(**sobrescritas: str) -> dict[str, str]:
    """Todos os campos obrigatórios de CAMPOS_FUNDAMENTUS com valores
    válidos — `sobrescritas` troca/adiciona rótulos específicos por
    teste (ex: omitir "Dív. Líquida" pra simular um banco)."""
    base = {
        "ROE": "27,7%",
        "Marg. Líquida": "24,4%",
        "LPA": "10,35",
        "VPA": "37,32",
        "Liquidez Corr": "0,85",
        "Dív Líq / Patrim": "0,65",
        "Cres. Rec (5a)": "-2,3%",
        "Nro. Ações": "12.888.700.000",
        "Patrim. Líq": "480.950.000.000",
        "Dív. Líquida": "312.769.000.000",
    }
    base.update(sobrescritas)
    return base


def test_montar_indicadores_caminho_feliz():
    indicadores = fundamentus._montar_indicadores("PETR4", _rotulos_valores_completos())

    assert indicadores == {
        "ticker": "PETR4",
        "roe_percentual": 27.7,
        "margem_liquida_percentual": 24.4,
        "lpa": 10.35,
        "vpa": 37.32,
        "liquidez_corrente": 0.85,
        "divida_liquida_sobre_patrimonio": 0.65,
        "crescimento_receita_5a_percentual": -2.3,
        "numero_acoes": 12888700000.0,
        "patrimonio_liquido": 480950000000.0,
        "divida_liquida": 312769000000.0,
    }


def test_montar_indicadores_levanta_erro_quando_falta_campo():
    rotulos_valores = {"ROE": "27,7%", "LPA": "10,35"}  # faltam os outros
    with pytest.raises(fundamentus.EstruturaPaginaMudou, match="PETR4"):
        fundamentus._montar_indicadores("PETR4", rotulos_valores)


def test_montar_indicadores_campo_opcional_ausente_vira_none_sem_erro():
    # "Dív. Líquida" (CAMPOS_FUNDAMENTUS_OPCIONAIS) pode faltar como
    # rótulo inteiro (não só valor "-") pra banco — não pode levantar
    # EstruturaPaginaMudou como um campo obrigatório faltando levantaria.
    rotulos_valores = _rotulos_valores_completos()
    del rotulos_valores["Dív. Líquida"]

    indicadores = fundamentus._montar_indicadores("ITUB4", rotulos_valores)

    assert indicadores["divida_liquida"] is None
    assert indicadores["patrimonio_liquido"] == 480950000000.0


def test_obter_indicadores_banco_real_nao_levanta_erro_e_divida_liquida_fica_none(
    tmp_path, monkeypatch
):
    # Fim a fim contra a página real de um banco (ITUB4): confirma que a
    # ausência de "Dív. Líquida" como rótulo não derruba obter_indicadores
    # inteiro (EstruturaPaginaMudou) — só aquele indicador específico
    # fica None, mesmo padrão já usado pra outros campos ausentes em banco.
    conteudo = _bytes_fixture("fundamentus_itub4.html")
    monkeypatch.setattr(fundamentus.requests, "get", lambda *a, **k: _RespostaFalsa(conteudo))
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    indicadores = fundamentus.obter_indicadores("ITUB4", diretorio_cache=tmp_path)

    assert indicadores["divida_liquida"] is None
    assert indicadores["patrimonio_liquido"] == 207648000000.0
    assert indicadores["divida_liquida_sobre_patrimonio"] is None  # "-" na página


def test_obter_indicadores_caminho_feliz_corrige_encoding_e_grava_cache(tmp_path, monkeypatch):
    conteudo = _bytes_fixture("fundamentus_petr4.html")
    # Resposta chega com um encoding padrão errado (ascii) — o adapter
    # precisa corrigir para iso-8859-1 antes de ler `.text`, senão os
    # rótulos acentuados ("Marg. Líquida" etc.) não batem e o parsing quebra.
    resposta_falsa = _RespostaFalsa(conteudo, encoding_padrao="ascii")
    monkeypatch.setattr(
        fundamentus.requests, "get", lambda *a, **k: resposta_falsa
    )
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    indicadores = fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)

    assert indicadores["ticker"] == "PETR4"
    assert indicadores["roe_percentual"] == 27.7
    assert (tmp_path / "fundamentus" / "PETR4.json").exists()


def test_obter_indicadores_levanta_ticker_nao_encontrado(tmp_path, monkeypatch):
    conteudo = _bytes_fixture("fundamentus_ticker_invalido.html")
    monkeypatch.setattr(
        fundamentus.requests, "get", lambda *a, **k: _RespostaFalsa(conteudo)
    )
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    with pytest.raises(fundamentus.TickerNaoEncontrado, match="TICKERINVALIDO"):
        fundamentus.obter_indicadores("TICKERINVALIDO", diretorio_cache=tmp_path)


def test_obter_indicadores_levanta_estrutura_pagina_mudou(tmp_path, monkeypatch):
    html_quebrado = """
    <html><body>
    <td class="label"><span class="txt">ROE</span></td><td><span class="txt">27,7%</span></td>
    </body></html>
    """
    monkeypatch.setattr(
        fundamentus.requests,
        "get",
        lambda *a, **k: _RespostaFalsa(html_quebrado.encode("iso-8859-1")),
    )
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    with pytest.raises(fundamentus.EstruturaPaginaMudou):
        fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)


def test_obter_indicadores_usa_cache_e_nao_bate_na_rede_de_novo(tmp_path, monkeypatch):
    conteudo = _bytes_fixture("fundamentus_petr4.html")
    chamadas = {"contador": 0}

    def get_falso(*args, **kwargs):
        chamadas["contador"] += 1
        return _RespostaFalsa(conteudo)

    monkeypatch.setattr(fundamentus.requests, "get", get_falso)
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)
    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)

    assert chamadas["contador"] == 1


def test_obter_indicadores_forcar_atualizacao_ignora_cache(tmp_path, monkeypatch):
    conteudo = _bytes_fixture("fundamentus_petr4.html")
    chamadas = {"contador": 0}

    def get_falso(*args, **kwargs):
        chamadas["contador"] += 1
        return _RespostaFalsa(conteudo)

    monkeypatch.setattr(fundamentus.requests, "get", get_falso)
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)
    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path, forcar_atualizacao=True)

    assert chamadas["contador"] == 2


def test_obter_indicadores_aplica_delay_antes_de_requisicao_real_mas_nao_em_cache(
    tmp_path, monkeypatch
):
    conteudo = _bytes_fixture("fundamentus_petr4.html")
    monkeypatch.setattr(fundamentus.requests, "get", lambda *a, **k: _RespostaFalsa(conteudo))

    esperas = []
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: esperas.append(segundos))

    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]

    fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path, delay_segundos=2.5)
    assert esperas == [2.5]  # segunda chamada veio do cache, não dormiu de novo


def test_obter_indicadores_propaga_erro_quando_site_fora_do_ar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fundamentus.requests, "get", lambda *a, **k: _RespostaFalsa(b"", status_ok=False)
    )
    monkeypatch.setattr(fundamentus.time, "sleep", lambda segundos: None)

    with pytest.raises(requests.HTTPError):
        fundamentus.obter_indicadores("PETR4", diretorio_cache=tmp_path)
