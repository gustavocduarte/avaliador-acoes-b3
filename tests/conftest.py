"""Fixture autouse que isola todos os testes do `data/raw/` real do
projeto — sem isso, um teste cujo mock de rede "dá certo" grava dado
fabricado lá, e o app trataria esse dado como legítimo depois.

Cada adapter declara `diretorio_cache: Path = DATA_RAW_DIR` como default
de parâmetro, valor fixado no momento em que a função é definida (uma
vez só, na importação do módulo) — monkeypatchar `config.DATA_RAW_DIR`
depois disso não alcança esses defaults já vinculados. Por isso cada
função com esse default é reapontada individualmente pra um `tmp_path`
por teste, via `__defaults__`. `bcb_sgs._caminho_ultimo_macro` é
redirecionada à parte, por segurança: mesmo que algum chamador passe
`diretorio_cache` explícito (em vez de usar o default), o arquivo do
último valor guardado nunca é gravado fora do `tmp_path` do teste.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest
import requests
import yfinance as yf

from avaliador_b3 import config, screener
from avaliador_b3.ingest import (
    b3_universo,
    balanco_cvm,
    bcb_sgs,
    crosswalk_cnpj,
    cvm,
    fundamentus,
    gpr,
    precos,
)

_MODULOS_COM_DIRETORIO_CACHE = (
    b3_universo,
    balanco_cvm,
    bcb_sgs,
    crosswalk_cnpj,
    cvm,
    fundamentus,
    gpr,
    precos,
    screener,
)


@pytest.fixture(autouse=True)
def _isolar_cache_de_disco(tmp_path, monkeypatch):
    for modulo in _MODULOS_COM_DIRETORIO_CACHE:
        for obj in vars(modulo).values():
            if not inspect.isfunction(obj) or obj.__module__ != modulo.__name__:
                continue
            parametros_com_default = [
                p
                for p in inspect.signature(obj).parameters.values()
                if p.default is not inspect.Parameter.empty
            ]
            if not any(p.default is config.DATA_RAW_DIR for p in parametros_com_default):
                continue
            novos_defaults = tuple(
                tmp_path if p.default is config.DATA_RAW_DIR else p.default
                for p in parametros_com_default
            )
            monkeypatch.setattr(obj, "__defaults__", novos_defaults)

    monkeypatch.setattr(
        bcb_sgs,
        "_caminho_ultimo_macro",
        lambda diretorio_cache: tmp_path / "bcb" / "ultimo_macro.json",
    )
    monkeypatch.setattr(
        bcb_sgs, "_caminho_macro_referencia", lambda: tmp_path / "macro_referencia.json"
    )


_DIRETORIOS_PROTEGIDOS = (config.DATA_RAW_DIR, config.DATA_PROCESSED_DIR)


def _hash_arquivos(diretorio) -> dict[str, str]:
    if not diretorio.exists():
        return {}
    return {
        str(caminho.relative_to(diretorio)): hashlib.md5(caminho.read_bytes()).hexdigest()
        for caminho in sorted(diretorio.rglob("*"))
        if caminho.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def _verificar_data_intocado():
    """Verificação independente de `_isolar_cache_de_disco` — não depende de conhecer cada
    adapter, então cobre um adapter novo que a lista de módulos daquela fixture não tenha (e
    também `data/processed/screener.csv`, versionado, que não passa por `diretorio_cache`
    nenhum). Snapshot (arquivo + hash) de `data/raw/` e `data/processed/` no início da sessão,
    comparado no fim; qualquer criação, alteração ou remoção derruba a suíte."""
    snapshot_antes = {d: _hash_arquivos(d) for d in _DIRETORIOS_PROTEGIDOS}
    yield
    for diretorio in _DIRETORIOS_PROTEGIDOS:
        antes = snapshot_antes[diretorio]
        depois = _hash_arquivos(diretorio)
        if antes == depois:
            continue
        criados = sorted(set(depois) - set(antes))
        apagados = sorted(set(antes) - set(depois))
        alterados = sorted(a for a in set(antes) & set(depois) if antes[a] != depois[a])
        pytest.fail(
            f"A suíte alterou {diretorio}: criados={criados} apagados={apagados} "
            f"alterados={alterados}"
        )


def _rede_bloqueada(metodo: str, url: str):
    raise RuntimeError(f"Teste tentou acessar a rede: {metodo} {url}")


@pytest.fixture(autouse=True)
def _bloquear_rede_real(monkeypatch):
    """Nenhum teste deve depender da rede de verdade — quem precisa de uma fonte externa mocka
    ela explicitamente. `requests.Session.request` cobre `requests.get`/`.post`/etc. (a
    implementação deles cria uma `Session` e chama `.request` por baixo). `yf.Ticker.history`/
    `.dividends` cobrem o yfinance à parte porque ele não passa pelo `requests` (sessão própria)."""

    def _session_request_bloqueada(self, method, url, *args, **kwargs):
        _rede_bloqueada(method, url)

    monkeypatch.setattr(requests.Session, "request", _session_request_bloqueada)

    def _history_bloqueado(self, *args, **kwargs):
        _rede_bloqueada("yfinance history", getattr(self, "ticker", "?"))

    def _dividends_bloqueado(self):
        _rede_bloqueada("yfinance dividends", getattr(self, "ticker", "?"))

    monkeypatch.setattr(yf.Ticker, "history", _history_bloqueado)
    monkeypatch.setattr(yf.Ticker, "dividends", property(_dividends_bloqueado))
