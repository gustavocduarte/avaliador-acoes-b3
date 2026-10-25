import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from avaliador_b3 import config, rodada


def test_salvar_grava_a_data_e_hora_com_o_fuso(tmp_path):
    caminho = tmp_path / "rodada.json"
    momento = datetime(2026, 10, 23, 21, 41, 12, tzinfo=timezone(timedelta(hours=-3)))

    rodada.salvar_data_rodada(caminho, momento)

    assert json.loads(caminho.read_text(encoding="utf-8")) == {
        "data_rodada": "2026-10-23T21:41:12-03:00"
    }
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rodada.json"]


def test_carregar_devolve_o_momento_gravado(tmp_path):
    caminho = tmp_path / "rodada.json"
    caminho.write_text('{"data_rodada": "2026-10-23T21:41:12-03:00"}', encoding="utf-8")

    momento = rodada.carregar_data_rodada(caminho)

    assert momento == pd.Timestamp("2026-10-24 00:41:12", tz="UTC")
    assert momento.strftime("%d/%m/%Y") == "23/10/2026"


def test_carregar_usa_o_caminho_padrao_da_config(tmp_path):
    config.CAMINHO_RODADA.write_text(
        '{"data_rodada": "2026-10-23T21:41:12-03:00"}', encoding="utf-8"
    )

    assert rodada.carregar_data_rodada() is not None


def test_carregar_sem_arquivo_devolve_none(tmp_path):
    assert rodada.carregar_data_rodada(tmp_path / "rodada.json") is None


def test_carregar_arquivo_invalido_devolve_none(tmp_path):
    for conteudo in ("{", "[]", "{}", '{"data_rodada": "ontem"}', '{"data_rodada": null}'):
        caminho = tmp_path / "rodada.json"
        caminho.write_text(conteudo, encoding="utf-8")

        assert rodada.carregar_data_rodada(caminho) is None, conteudo


def test_agora_da_rodada_esta_no_fuso_de_brasilia():
    momento = rodada.agora_da_rodada()

    assert momento.utcoffset() == timedelta(hours=-3)
    assert config.FUSO_RODADA == "America/Sao_Paulo"
