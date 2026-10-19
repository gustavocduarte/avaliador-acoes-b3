"""Validade dos zips da CVM (anos fechados também expiram) e dos caches derivados (`fcf_*`,
`lucro_*`, `balanco_*`), que só valem enquanto o zip de origem for o mesmo e estiver no prazo."""

import json
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests

from avaliador_b3.config import (
    DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE,
    DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_FECHADO,
    VERSAO_SCHEMA_CVM_BALANCO,
    VERSAO_SCHEMA_CVM_FCF,
    VERSAO_SCHEMA_CVM_LUCRO,
)
from avaliador_b3.ingest import balanco_cvm, cvm
from avaliador_b3.ingest._cache import ler_json_cache
from tests import test_balanco_cvm as balanco
from tests import test_versoes_cvm as versoes

HOJE = datetime(2027, 1, 1)
ANO_FECHADO = 2024
ANO_CORRENTE = 2026


def _zip_com_idade(caminho: Path, idade: timedelta, hoje: datetime = HOJE) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"zip")
    instante = (hoje - idade).timestamp()
    os.utime(caminho, (instante, instante))
    return caminho


# --- Prazo do zip ---


def test_os_prazos_sao_de_7_dias_para_o_ano_corrente_e_30_para_anos_fechados():
    assert DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_CORRENTE == 7
    assert DIAS_VALIDADE_CACHE_ZIP_CVM_ANO_FECHADO == 30


@pytest.mark.parametrize(
    ("ano", "dias", "expirado"),
    [
        (ANO_FECHADO, 29, False),
        (ANO_FECHADO, 30, True),
        (ANO_FECHADO, 1000, True),
        (2025, 31, True),  # 2025 já é ano fechado em 2027
        (2027, 6, False),
        (2027, 7, True),
        (ANO_CORRENTE, 6, False),
        (ANO_CORRENTE, 7, True),
    ],
)
def test_cache_zip_expirado_por_idade(tmp_path, ano, dias, expirado):
    caminho = _zip_com_idade(tmp_path / "z.zip", timedelta(days=dias))

    assert cvm._cache_zip_expirado(caminho, ano, HOJE) is expirado


def test_zip_de_ano_fechado_dentro_do_prazo_nao_bate_na_rede(tmp_path, monkeypatch):
    caminho = _zip_com_idade(tmp_path / "cvm" / "dfp_cia_aberta_2020.zip", timedelta(days=29))

    def get_falso(*args, **kwargs):
        raise AssertionError("dentro do prazo não deveria bater na rede")

    monkeypatch.setattr(cvm.requests, "get", get_falso)

    assert cvm._baixar_zip_ano(2020, tmp_path, False, hoje=HOJE) == caminho


def test_zip_de_ano_fechado_vencido_e_baixado_de_novo(tmp_path, monkeypatch):
    _zip_com_idade(tmp_path / "cvm" / "dfp_cia_aberta_2020.zip", timedelta(days=31))
    pedidos = []

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"zip novo"

    monkeypatch.setattr(cvm.requests, "get", lambda url, **kw: pedidos.append(url) or Resposta())

    resultado = cvm._baixar_zip_ano(2020, tmp_path, False, hoje=HOJE)

    assert len(pedidos) == 1
    assert resultado.read_bytes() == b"zip novo"


def test_zip_de_ano_fechado_vencido_com_a_cvm_fora_do_ar_usa_o_existente_com_aviso(
    tmp_path, monkeypatch
):
    caminho = _zip_com_idade(tmp_path / "cvm" / "dfp_cia_aberta_2020.zip", timedelta(days=90))

    def get_falho(*args, **kwargs):
        raise requests.ConnectionError("CVM fora do ar (simulado)")

    monkeypatch.setattr(cvm.requests, "get", get_falho)

    with pytest.warns(UserWarning, match="usando a versão em cache"):
        resultado = cvm._baixar_zip_ano(2020, tmp_path, False, hoje=HOJE)

    assert resultado == caminho


# --- Cache derivado do FCF ---


def _zip_dfc_no_cache(tmp_path, ano):
    caminho = tmp_path / "cvm" / f"dfp_cia_aberta_{ano}.zip"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr(f"dfp_cia_aberta_DFC_MI_con_{ano}.csv", versoes._csv(versoes.V2))
        for metodo, tipo in (("MI", "ind"), ("MD", "con"), ("MD", "ind")):
            arquivo.writestr(f"dfp_cia_aberta_DFC_{metodo}_{tipo}_{ano}.csv", versoes._csv([]))
        for tipo in ("con", "ind"):
            arquivo.writestr(f"dfp_cia_aberta_DRE_{tipo}_{ano}.csv", versoes._csv([]))
    return caminho


@pytest.fixture
def leituras_do_zip(monkeypatch):
    """Conta quantas vezes o zip foi lido para extrair o FCF e quantas vezes foi pedido."""
    contagem = {"leituras": 0, "pedidos": 0}
    escolher_real = cvm._escolher_dfc
    baixar_real = cvm._baixar_zip_ano

    def escolher(*args, **kwargs):
        contagem["leituras"] += 1
        return escolher_real(*args, **kwargs)

    def baixar(*args, **kwargs):
        contagem["pedidos"] += 1
        return baixar_real(*args, **kwargs)

    monkeypatch.setattr(cvm, "_escolher_dfc", escolher)
    monkeypatch.setattr(cvm, "_baixar_zip_ano", baixar)
    return contagem


def _fcf(tmp_path, ano=2025):
    return cvm.obter_fluxo_caixa_livre(versoes.CNPJ, ano, diretorio_cache=tmp_path)


def test_fcf_gravado_com_a_identificacao_do_zip_de_origem(tmp_path, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)

    _fcf(tmp_path)

    envelope = ler_json_cache(tmp_path / "cvm" / "fcf_00000000000400_2025.json")
    assert envelope["versao_schema"] == VERSAO_SCHEMA_CVM_FCF
    assert envelope["zip_origem"] == {
        "tamanho": zip_.stat().st_size,
        "modificado_em": int(zip_.stat().st_mtime),
    }


def test_fcf_com_o_mesmo_zip_vem_do_cache(tmp_path, leituras_do_zip):
    _zip_dfc_no_cache(tmp_path, 2025)

    _fcf(tmp_path)
    segundo = _fcf(tmp_path)

    assert leituras_do_zip == {"leituras": 1, "pedidos": 1}
    assert segundo["fcf_atual"] == 180.0


def test_fcf_e_refeito_quando_o_tamanho_do_zip_muda(tmp_path, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)
    _fcf(tmp_path)
    instante = zip_.stat().st_mtime

    with zipfile.ZipFile(zip_, "a") as arquivo:
        arquivo.writestr("acrescimo.txt", "mais bytes")
    os.utime(zip_, (instante, instante))
    _fcf(tmp_path)

    assert leituras_do_zip["leituras"] == 2


def test_fcf_e_refeito_quando_a_data_do_zip_muda_com_o_mesmo_tamanho(tmp_path, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)
    _fcf(tmp_path)

    novo = time.time() - 3600
    os.utime(zip_, (novo, novo))
    _fcf(tmp_path)

    assert leituras_do_zip["leituras"] == 2


def test_fcf_de_ano_fechado_e_refeito_quando_o_zip_vence(tmp_path, monkeypatch, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, ANO_FECHADO)
    velho = time.time() - 40 * 86400
    os.utime(zip_, (velho, velho))
    # o zip vencido seria renovado por `_baixar_zip_ano`; aqui só interessa o cache derivado
    monkeypatch.setattr(
        cvm,
        "_baixar_zip_ano",
        lambda *a, **k: (leituras_do_zip.update(pedidos=leituras_do_zip["pedidos"] + 1), zip_)[1],
    )
    _fcf(tmp_path, ANO_FECHADO)

    _fcf(tmp_path, ANO_FECHADO)

    assert leituras_do_zip["leituras"] == 2
    assert leituras_do_zip["pedidos"] == 2


def test_fcf_de_ano_fechado_dentro_do_prazo_continua_vindo_do_cache(tmp_path, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, ANO_FECHADO)
    recente = time.time() - 20 * 86400
    os.utime(zip_, (recente, recente))

    _fcf(tmp_path, ANO_FECHADO)
    _fcf(tmp_path, ANO_FECHADO)

    assert leituras_do_zip["leituras"] == 1


def test_fcf_sem_o_zip_no_disco_dentro_do_prazo_vale_o_cache(
    tmp_path, monkeypatch, leituras_do_zip
):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)
    _fcf(tmp_path)
    zip_.unlink()

    def sem_pedido(*args, **kwargs):
        raise AssertionError("o zip não deveria ser pedido: o cache vale")

    monkeypatch.setattr(cvm, "_baixar_zip_ano", sem_pedido)

    assert _fcf(tmp_path)["fcf_atual"] == 180.0


def test_fcf_sem_o_zip_no_disco_fora_do_prazo_e_refeito(tmp_path, monkeypatch, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)
    _fcf(tmp_path)
    zip_.unlink()
    caminho = tmp_path / "cvm" / "fcf_00000000000400_2025.json"
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    bruto["zip_origem"]["modificado_em"] -= 31 * 24 * 3600
    caminho.write_text(json.dumps(bruto), encoding="utf-8")
    pedidos = []

    def pedido(ano, *args, **kwargs):
        pedidos.append(ano)
        raise cvm.ErroCVM("sem rede")

    monkeypatch.setattr(cvm, "_baixar_zip_ano", pedido)

    with pytest.raises(cvm.ErroCVM):
        _fcf(tmp_path)
    assert pedidos == [2025]


def test_fcf_do_schema_anterior_sem_origem_e_ignorado(tmp_path, leituras_do_zip):
    _zip_dfc_no_cache(tmp_path, 2025)
    caminho = tmp_path / "cvm" / "fcf_00000000000400_2025.json"
    caminho.write_text('{"versao_schema": 5, "resultado": {"fcf_atual": 999.0}}', encoding="utf-8")

    assert _fcf(tmp_path)["fcf_atual"] == 180.0


def test_fcf_do_schema_atual_sem_a_origem_do_zip_e_ignorado(tmp_path, leituras_do_zip):
    _zip_dfc_no_cache(tmp_path, 2025)
    caminho = tmp_path / "cvm" / "fcf_00000000000400_2025.json"
    caminho.write_text(
        f'{{"versao_schema": {VERSAO_SCHEMA_CVM_FCF}, "resultado": {{"fcf_atual": 999.0}}}}',
        encoding="utf-8",
    )

    assert _fcf(tmp_path)["fcf_atual"] == 180.0


def test_fcf_do_tipo_tambem_segue_o_zip_de_origem(tmp_path, leituras_do_zip):
    zip_ = _zip_dfc_no_cache(tmp_path, 2025)
    pedir = lambda: cvm.obter_fluxo_caixa_livre_do_tipo(  # noqa: E731
        versoes.CNPJ, 2025, "MI", "con", diretorio_cache=tmp_path
    )
    pedir()
    pedir()
    assert leituras_do_zip["pedidos"] == 1

    novo = time.time() - 3600
    os.utime(zip_, (novo, novo))
    pedir()

    assert leituras_do_zip["pedidos"] == 2


# --- Cache do lucro líquido ---


def _zip_dre_no_cache(tmp_path, ano):
    caminho = tmp_path / "cvm" / f"dfp_cia_aberta_{ano}.zip"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho, "w") as arquivo:
        arquivo.writestr(
            f"dfp_cia_aberta_DRE_con_{ano}.csv", versoes._csv(versoes._dre_da_versao(2, 1200, 80))
        )
        arquivo.writestr(f"dfp_cia_aberta_DRE_ind_{ano}.csv", versoes._csv([]))
    return caminho


def test_lucro_liquido_tem_envelope_com_origem_e_e_refeito_se_o_zip_muda(tmp_path, monkeypatch):
    zip_ = _zip_dre_no_cache(tmp_path, 2025)
    leituras = []
    montar_real = cvm._montar_resultado
    monkeypatch.setattr(
        cvm, "_montar_resultado", lambda *a, **k: leituras.append(1) or montar_real(*a, **k)
    )

    primeiro = cvm.obter_lucro_liquido(versoes.CNPJ, 2025, diretorio_cache=tmp_path)
    cvm.obter_lucro_liquido(versoes.CNPJ, 2025, diretorio_cache=tmp_path)
    envelope = ler_json_cache(tmp_path / "cvm" / "lucro_00000000000400_2025.json")

    assert primeiro["lucro_liquido_atual"] == 80.0
    assert len(leituras) == 1
    assert envelope["versao_schema"] == VERSAO_SCHEMA_CVM_LUCRO
    assert envelope["zip_origem"]["tamanho"] == zip_.stat().st_size

    novo = time.time() - 3600
    os.utime(zip_, (novo, novo))
    cvm.obter_lucro_liquido(versoes.CNPJ, 2025, diretorio_cache=tmp_path)

    assert len(leituras) == 2


def test_lucro_liquido_no_formato_antigo_sem_envelope_e_ignorado(tmp_path):
    _zip_dre_no_cache(tmp_path, 2025)
    caminho = tmp_path / "cvm" / "lucro_00000000000400_2025.json"
    caminho.write_text('{"lucro_liquido_atual": 999.0}', encoding="utf-8")

    resultado = cvm.obter_lucro_liquido(versoes.CNPJ, 2025, diretorio_cache=tmp_path)

    assert resultado["lucro_liquido_atual"] == 80.0


# --- Cache do balanço ---


@pytest.fixture
def baixados(monkeypatch):
    """Registra os documentos pedidos a `_baixar_zip_ano` e serve o zip configurado."""
    estado = {"zips": {}, "pedidos": []}

    def baixar(ano, diretorio_cache, forcar_atualizacao, hoje=None, documento="dfp"):
        estado["pedidos"].append((documento, ano))
        return estado["zips"][(documento, ano)]

    monkeypatch.setattr(balanco_cvm, "_baixar_zip_ano", baixar)
    return estado


def _balanco_no_cache(tmp_path, baixados):
    padrao = tmp_path / "cvm" / "itr_cia_aberta_2026.zip"
    padrao.parent.mkdir(parents=True, exist_ok=True)
    origem = balanco._zip(
        tmp_path, "itr", 2026, balanco.BALANCO_BASE, [balanco._linha_capital(900, 100, 50)]
    )
    shutil.move(origem, padrao)
    baixados["zips"][("itr", 2026)] = padrao
    return padrao


def _ler_balanco(tmp_path):
    return balanco_cvm.obter_balanco_cvm(balanco.CNPJ, "2026-06-30", diretorio_cache=tmp_path)


def test_balanco_gravado_com_a_origem_vem_do_cache_e_e_refeito_se_o_zip_muda(tmp_path, baixados):
    padrao = _balanco_no_cache(tmp_path, baixados)

    _ler_balanco(tmp_path)
    _ler_balanco(tmp_path)
    envelope = ler_json_cache(tmp_path / "cvm" / "balanco_12345678000190_2026-06-30.json")

    assert baixados["pedidos"] == [("itr", 2026)]
    assert envelope["versao_schema"] == VERSAO_SCHEMA_CVM_BALANCO
    assert envelope["zip_origem"]["tamanho"] == padrao.stat().st_size

    novo = time.time() - 3600
    os.utime(padrao, (novo, novo))
    _ler_balanco(tmp_path)

    assert baixados["pedidos"] == [("itr", 2026), ("itr", 2026)]


def test_balanco_do_itr_vence_em_7_dias_e_e_refeito(tmp_path, baixados):
    padrao = _balanco_no_cache(tmp_path, baixados)
    _ler_balanco(tmp_path)
    velho = time.time() - 10 * 86400
    os.utime(padrao, (velho, velho))
    # o cache derivado guarda a data antiga do zip: mesma origem, mas vencida
    envelope_caminho = tmp_path / "cvm" / "balanco_12345678000190_2026-06-30.json"
    envelope = ler_json_cache(envelope_caminho)
    envelope["zip_origem"] = cvm.origem_do_zip(padrao)
    envelope_caminho.write_text(json.dumps(envelope), encoding="utf-8")

    _ler_balanco(tmp_path)

    assert len(baixados["pedidos"]) == 2
