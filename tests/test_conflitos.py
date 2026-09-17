import pandas as pd
import pytest

from avaliador_b3 import conflitos
from avaliador_b3.config import (
    PAISES_PRODUTORES_MINERIO_FERRO_GDELT,
    PAISES_PRODUTORES_PETROLEO_GDELT,
)


def _evento(codigo_pais: str, evento_id: int = 1) -> dict:
    return {
        "GLOBALEVENTID": evento_id,
        "data": pd.Timestamp("2026-09-16 07:45:00"),
        "ActionGeo_FullName": f"Local em {codigo_pais}",
        "ActionGeo_CountryCode": codigo_pais,
        "GoldsteinScale": -5.0,
        # URL distinta por evento — sem isso, `deduplicar_por_fonte`
        # colapsaria eventos de teste diferentes por terem SOURCEURL vazia
        # em comum (ver ingest.gdelt.deduplicar_por_fonte).
        "SOURCEURL": f"https://example.com/evento-{evento_id}",
    }


def _eventos(codigos: list[str]) -> pd.DataFrame:
    return pd.DataFrame([_evento(codigo, i) for i, codigo in enumerate(codigos)])


# --- determinar_paises_relevantes -------------------------------------------


def test_brasil_sempre_incluso_mesmo_sem_setor_identificado():
    paises = conflitos.determinar_paises_relevantes(None)
    assert "BR" in paises


def test_brasil_sempre_incluso_pra_setor_sem_commodity_associada():
    # Bancos não têm país produtor de commodity nenhum associado — só o
    # Brasil (regra padrão) deve aparecer.
    paises = conflitos.determinar_paises_relevantes("Bancos")
    assert paises == {"BR"}


def test_petroleo_e_gas_ganha_paises_produtores_de_petroleo():
    paises = conflitos.determinar_paises_relevantes("Exploração. Refino e Distribuição")
    assert "BR" in paises
    assert PAISES_PRODUTORES_PETROLEO_GDELT.issubset(paises)
    # não deve trazer os de minério junto
    assert not (PAISES_PRODUTORES_MINERIO_FERRO_GDELT - PAISES_PRODUTORES_PETROLEO_GDELT) & paises


def test_distribuicao_de_combustiveis_tambem_ganha_paises_de_petroleo():
    paises = conflitos.determinar_paises_relevantes("Distribuição de Combustíveis")
    assert PAISES_PRODUTORES_PETROLEO_GDELT.issubset(paises)


def test_mineracao_metalicos_ganha_paises_produtores_de_minerio():
    paises = conflitos.determinar_paises_relevantes("Minerais Metálicos")
    assert "BR" in paises
    assert PAISES_PRODUTORES_MINERIO_FERRO_GDELT.issubset(paises)


def test_siderurgia_tambem_ganha_paises_produtores_de_minerio():
    # CSNA3 (Siderurgia) — vertical integrada com mineração própria, ver
    # justificativa em config.py.
    paises = conflitos.determinar_paises_relevantes("Siderurgia")
    assert PAISES_PRODUTORES_MINERIO_FERRO_GDELT.issubset(paises)


# --- filtrar_eventos_por_paises ---------------------------------------------


def test_filtra_evento_dentro_da_lista_relevante():
    eventos = _eventos(["BR", "US"])
    filtrado = conflitos.filtrar_eventos_por_paises(eventos, {"BR"})
    assert list(filtrado["ActionGeo_CountryCode"]) == ["BR"]


def test_filtra_fora_evento_de_pais_nao_relevante():
    eventos = _eventos(["FR", "DE"])
    filtrado = conflitos.filtrar_eventos_por_paises(eventos, {"BR", "US"})
    assert filtrado.empty


def test_nenhum_evento_relevante_no_snapshot_atual_devolve_vazio_sem_erro():
    # Cenário esperado boa parte do tempo: snapshot de 15 min sem nenhum
    # evento nos países relevantes — resultado vazio, não uma exceção.
    eventos = _eventos(["FR", "DE", "JP"])
    filtrado = conflitos.filtrar_eventos_por_paises(eventos, {"BR"})
    assert isinstance(filtrado, pd.DataFrame)
    assert filtrado.empty
    assert list(filtrado.columns) == list(eventos.columns)


# --- eventos_relevantes_para_acao (atalho combinado) ------------------------


@pytest.mark.parametrize(
    ("segmento_setorial", "codigos_presentes", "esperado"),
    [
        ("Bancos", ["BR", "US"], ["BR"]),  # US só é relevante p/ petróleo/minério
        ("Exploração. Refino e Distribuição", ["BR", "SA", "FR"], ["BR", "SA"]),
        ("Minerais Metálicos", ["AS", "FR"], ["AS"]),
    ],
)
def test_eventos_relevantes_para_acao(segmento_setorial, codigos_presentes, esperado):
    eventos = _eventos(codigos_presentes)
    filtrado = conflitos.eventos_relevantes_para_acao(eventos, segmento_setorial)
    assert sorted(filtrado["ActionGeo_CountryCode"]) == sorted(esperado)


# --- descrever_escopo_paises -------------------------------------------------


def test_descrever_escopo_so_brasil_pra_setor_sem_commodity():
    descricao = conflitos.descrever_escopo_paises("Bancos")
    assert "Brasil" in descricao
    assert "petróleo" not in descricao.lower()
    assert "minério" not in descricao.lower()


def test_descrever_escopo_menciona_petroleo_pro_setor_certo():
    descricao = conflitos.descrever_escopo_paises("Exploração. Refino e Distribuição")
    assert "Brasil" in descricao
    assert "petróleo" in descricao.lower()
    assert "Arábia Saudita" in descricao


# --- PAISES_MONITORADOS / descrever_paises_monitorados (escopo universal, ---
# --- não depende de nenhuma ação/setor escolhido) ----------------------------


def test_paises_monitorados_e_uniao_de_brasil_petroleo_e_minerio():
    assert conflitos.PAISES_MONITORADOS == (
        {"BR"} | PAISES_PRODUTORES_PETROLEO_GDELT | PAISES_PRODUTORES_MINERIO_FERRO_GDELT
    )


def test_descrever_paises_monitorados_menciona_brasil_petroleo_e_minerio():
    descricao = conflitos.descrever_paises_monitorados()
    assert "Brasil" in descricao
    assert "petróleo" in descricao.lower()
    assert "minério" in descricao.lower()
    assert "Arábia Saudita" in descricao  # produtor de petróleo
    assert "Austrália" in descricao  # produtor de minério de ferro


# --- obter_eventos_relevantes_ultimas_24h (janela, processamento incremental)


def _evento_com_data(codigo_pais: str, data: str, evento_id: int) -> dict:
    return {
        "GLOBALEVENTID": evento_id,
        "data": pd.Timestamp(data),
        "ActionGeo_FullName": f"Local em {codigo_pais}",
        "ActionGeo_CountryCode": codigo_pais,
        "GoldsteinScale": -5.0,
        # Ver comentário equivalente em `_evento` acima.
        "SOURCEURL": f"https://example.com/evento-{evento_id}",
    }


@pytest.fixture
def _quatro_timestamps(monkeypatch):
    """Ancora a janela num timestamp fixo e restringe a 1h (4 passos de 15
    min) — rápido de testar sem precisar de 96 timestamps reais."""
    monkeypatch.setattr(conflitos, "obter_timestamp_mais_recente", lambda: "20260916074500")
    return ["20260916074500", "20260916073000", "20260916071500", "20260916070000"]


def test_acumula_incrementalmente_so_o_filtrado_por_pais(monkeypatch, _quatro_timestamps):
    # Cada "snapshot" tem um evento relevante (BR) e um irrelevante (FR) —
    # só o BR de cada um deve sobreviver na tabela acumulada final.
    por_timestamp = {
        ts: pd.DataFrame(
            [
                _evento_com_data("BR", "2026-09-16 07:00:00", i * 2),
                _evento_com_data("FR", "2026-09-16 07:00:00", i * 2 + 1),
            ]
        )
        for i, ts in enumerate(_quatro_timestamps)
    }
    monkeypatch.setattr(
        conflitos, "obter_eventos_conflito_do_snapshot", lambda ts, **kw: por_timestamp[ts]
    )

    resultado = conflitos.obter_eventos_relevantes_ultimas_24h("Bancos", horas=1)

    assert len(resultado) == 4  # 1 evento relevante (BR) por snapshot, 4 snapshots
    assert (resultado["ActionGeo_CountryCode"] == "BR").all()


def test_pula_snapshot_que_falha_sem_quebrar_a_janela_inteira(monkeypatch, _quatro_timestamps):
    def buscar_falso(timestamp, **kwargs):
        if timestamp == "20260916073000":
            raise RuntimeError("gap simulado — horário sem arquivo publicado")
        # evento_id (e portanto SOURCEURL) varia por timestamp — sem isso,
        # os 3 snapshots que têm sucesso devolveriam o "mesmo" artigo e
        # `deduplicar_por_fonte` colapsaria os 3 numa linha só, mascarando
        # o que este teste quer provar (nenhum é de fato perdido).
        return pd.DataFrame([_evento_com_data("BR", "2026-09-16 07:00:00", int(timestamp))])

    monkeypatch.setattr(conflitos, "obter_eventos_conflito_do_snapshot", buscar_falso)

    resultado = conflitos.obter_eventos_relevantes_ultimas_24h("Bancos", horas=1)

    # 3 dos 4 snapshots tiveram sucesso (1 evento BR cada) — o que falhou
    # foi pulado, não travou a busca inteira nem levantou exceção.
    assert len(resultado) == 3


def test_processa_um_snapshot_de_cada_vez_nao_em_lote(monkeypatch, _quatro_timestamps):
    chamadas_em_ordem = []

    def buscar_falso(timestamp, **kwargs):
        chamadas_em_ordem.append(timestamp)
        return pd.DataFrame([_evento_com_data("BR", "2026-09-16 07:00:00", 1)])

    monkeypatch.setattr(conflitos, "obter_eventos_conflito_do_snapshot", buscar_falso)

    conflitos.obter_eventos_relevantes_ultimas_24h("Bancos", horas=1)

    # Uma chamada por timestamp gerado, na ordem esperada — não uma busca
    # em lote de todos os timestamps de uma vez.
    assert chamadas_em_ordem == _quatro_timestamps


def test_sem_nenhum_evento_relevante_devolve_tabela_vazia_com_colunas(
    monkeypatch, _quatro_timestamps
):
    # Todo snapshot tem só eventos de países irrelevantes pro setor —
    # resultado vazio, não erro.
    monkeypatch.setattr(
        conflitos,
        "obter_eventos_conflito_do_snapshot",
        lambda ts, **kw: pd.DataFrame([_evento_com_data("FR", "2026-09-16 07:00:00", 1)]),
    )

    resultado = conflitos.obter_eventos_relevantes_ultimas_24h("Bancos", horas=1)

    assert resultado.empty
    assert list(resultado.columns) == conflitos.COLUNAS_RESULTADO_GDELT


# --- obter_eventos_conflito_ultimas_24h (mesmo processamento incremental, --
# --- mas escopo universal — sem depender de nenhuma ação/setor) -------------


def test_universal_acumula_eventos_de_pais_monitorado_fora_do_brasil(
    monkeypatch, _quatro_timestamps
):
    # Sem nenhum segmento setorial: um evento na Arábia Saudita (produtor
    # de petróleo) já entra — diferente do escopo por setor "Bancos" usado
    # nos testes acima, que não incluiria a Arábia Saudita.
    por_timestamp = {
        ts: pd.DataFrame(
            [
                _evento_com_data("SA", "2026-09-16 07:00:00", i * 2),
                _evento_com_data("FR", "2026-09-16 07:00:00", i * 2 + 1),
            ]
        )
        for i, ts in enumerate(_quatro_timestamps)
    }
    monkeypatch.setattr(
        conflitos, "obter_eventos_conflito_do_snapshot", lambda ts, **kw: por_timestamp[ts]
    )

    resultado = conflitos.obter_eventos_conflito_ultimas_24h(horas=1)

    assert len(resultado) == 4  # 1 evento relevante (SA) por snapshot, 4 snapshots
    assert (resultado["ActionGeo_CountryCode"] == "SA").all()


def test_universal_pula_snapshot_que_falha_sem_quebrar_a_janela_inteira(
    monkeypatch, _quatro_timestamps
):
    def buscar_falso(timestamp, **kwargs):
        if timestamp == "20260916073000":
            raise RuntimeError("gap simulado — horário sem arquivo publicado")
        # Ver comentário equivalente na versão não-universal deste teste
        # acima (evento_id por timestamp, pra não colidir no dedup por URL).
        return pd.DataFrame([_evento_com_data("BR", "2026-09-16 07:00:00", int(timestamp))])

    monkeypatch.setattr(conflitos, "obter_eventos_conflito_do_snapshot", buscar_falso)

    resultado = conflitos.obter_eventos_conflito_ultimas_24h(horas=1)

    assert len(resultado) == 3


def test_universal_sem_nenhum_evento_relevante_devolve_tabela_vazia_com_colunas(
    monkeypatch, _quatro_timestamps
):
    monkeypatch.setattr(
        conflitos,
        "obter_eventos_conflito_do_snapshot",
        lambda ts, **kw: pd.DataFrame([_evento_com_data("FR", "2026-09-16 07:00:00", 1)]),
    )

    resultado = conflitos.obter_eventos_conflito_ultimas_24h(horas=1)

    assert resultado.empty
    assert list(resultado.columns) == conflitos.COLUNAS_RESULTADO_GDELT


# --- rodar_monitor_conflitos / carregar_eventos_conflito_salvos (persistência,
# --- mesmo padrão do screener.csv: "carrega o salvo, botão explícito atualiza")


def _evento_completo(codigo_pais: str, event_root_code: str, evento_id: int) -> dict:
    return {
        "GLOBALEVENTID": evento_id,
        "data": pd.Timestamp("2026-09-16 07:45:00"),
        "EventRootCode": event_root_code,
        "categoria_cameo": "FIGHT",
        "EventCode": "190",
        "GoldsteinScale": -5.0,
        "NumMentions": 3,
        "NumArticles": 2,
        "AvgTone": -4.5,
        "ActionGeo_FullName": f"Local em {codigo_pais}",
        "ActionGeo_CountryCode": codigo_pais,
        "ActionGeo_Lat": 10.0,
        "ActionGeo_Long": 20.0,
        "SOURCEURL": "https://example.com",
    }


def _eventos_completos(linhas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(linhas)[conflitos.COLUNAS_RESULTADO_GDELT]


def test_carregar_eventos_conflito_salvos_devolve_none_quando_arquivo_nao_existe(tmp_path):
    caminho = tmp_path / "conflitos_24h.csv"
    assert conflitos.carregar_eventos_conflito_salvos(caminho) is None


def test_carregar_eventos_conflito_salvos_devolve_none_quando_arquivo_vazio(tmp_path):
    # Mesmo cenário de "processo interrompido no meio da escrita" já
    # tratado em app.main._carregar_screener_salvo.
    caminho = tmp_path / "conflitos_24h.csv"
    caminho.write_text("")
    assert conflitos.carregar_eventos_conflito_salvos(caminho) is None


def test_rodar_monitor_conflitos_grava_e_recarrega_preservando_zero_a_esquerda(
    tmp_path, monkeypatch
):
    # EventRootCode "05" precisa continuar "05" (não virar 5) depois de
    # salvo em disco e relido — mesmo cuidado já validado pro cache de
    # snapshot do GDELT (ingest.gdelt.DTYPES_LEITURA_CACHE).
    monkeypatch.setattr(
        conflitos,
        "obter_eventos_conflito_ultimas_24h",
        lambda **kw: _eventos_completos([_evento_completo("BR", "05", 1)]),
    )
    caminho_saida = tmp_path / "conflitos_24h.csv"

    resultado = conflitos.rodar_monitor_conflitos(caminho_saida=caminho_saida)

    assert caminho_saida.exists()
    assert resultado.iloc[0]["EventRootCode"] == "05"

    recarregado = conflitos.carregar_eventos_conflito_salvos(caminho_saida)
    assert recarregado.iloc[0]["EventRootCode"] == "05"
    assert recarregado.iloc[0]["ActionGeo_CountryCode"] == "BR"


def test_rodar_monitor_conflitos_zero_eventos_e_salvo_como_resultado_valido(
    tmp_path, monkeypatch
):
    # Zero eventos na janela não é erro (ver filtrar_eventos_por_paises) —
    # também precisa ser salvo, não só mantido em memória.
    monkeypatch.setattr(
        conflitos,
        "obter_eventos_conflito_ultimas_24h",
        lambda **kw: pd.DataFrame(columns=conflitos.COLUNAS_RESULTADO_GDELT),
    )
    caminho_saida = tmp_path / "conflitos_24h.csv"

    resultado = conflitos.rodar_monitor_conflitos(caminho_saida=caminho_saida)

    assert resultado.empty
    assert caminho_saida.exists()

    recarregado = conflitos.carregar_eventos_conflito_salvos(caminho_saida)
    assert recarregado is not None
    assert recarregado.empty


def test_rodar_monitor_conflitos_sobrescreve_busca_anterior(tmp_path, monkeypatch):
    respostas = iter(
        [
            _eventos_completos([_evento_completo("BR", "05", 1)]),
            _eventos_completos([_evento_completo("US", "19", 2)]),
        ]
    )
    monkeypatch.setattr(
        conflitos, "obter_eventos_conflito_ultimas_24h", lambda **kw: next(respostas)
    )
    caminho_saida = tmp_path / "conflitos_24h.csv"

    conflitos.rodar_monitor_conflitos(caminho_saida=caminho_saida)
    conflitos.rodar_monitor_conflitos(caminho_saida=caminho_saida)

    recarregado = conflitos.carregar_eventos_conflito_salvos(caminho_saida)
    assert list(recarregado["ActionGeo_CountryCode"]) == ["US"]
