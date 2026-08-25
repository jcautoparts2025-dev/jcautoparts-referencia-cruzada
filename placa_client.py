"""Consulta de placa via API Placas (apiplacas.com.br, backend WDAPI2 —
https://wdapi2.com.br/consulta/{placa}/{token}). Serviço pago de terceiro
(R$0,03/consulta aprox.) — resultado é sempre cacheado no Turso
(db.get_cache_placa/salvar_cache_placa) para nunca pagar duas vezes pela
mesma placa."""
import re

import requests

import db

_WDAPI2_BASE = "https://wdapi2.com.br"
_RE_PLACA = re.compile(r"^[A-Z]{3}\d[A-Z0-9]\d{2}$")


class ConsultaPlacaIndisponivel(Exception):
    """Erro amigável para exibir na UI em vez de stack trace."""


def normalizar_placa(placa):
    return re.sub(r"[\s\-]", "", (placa or "").strip().upper())


def placa_valida(placa_normalizada):
    return bool(_RE_PLACA.match(placa_normalizada))


def consultar_placa(placa, forcar=False):
    """Retorna (dados: dict, veio_do_cache: bool). Lança ConsultaPlacaIndisponivel
    para formato inválido, token ausente/inválido, placa sem resultado ou
    limite diário atingido — sempre com mensagem amigável."""
    placa_norm = normalizar_placa(placa)
    if not placa_valida(placa_norm):
        raise ConsultaPlacaIndisponivel(
            "Placa inválida — use o formato AAA0X00 (Mercosul) ou AAA9999 (antigo)."
        )

    if not forcar:
        cache = db.get_cache_placa(placa_norm)
        if cache is not None:
            return cache, True

    token = db.get_secret("APIPLACAS_TOKEN")
    if not token:
        raise ConsultaPlacaIndisponivel("APIPLACAS_TOKEN não configurado.")

    try:
        resp = requests.get(f"{_WDAPI2_BASE}/consulta/{placa_norm}/{token}", timeout=20)
    except requests.RequestException as e:
        raise ConsultaPlacaIndisponivel("Não foi possível conectar à API de consulta de placa.") from e

    if resp.status_code == 401:
        raise ConsultaPlacaIndisponivel("Placa inválida segundo a API — confira o formato.")
    if resp.status_code == 402:
        raise ConsultaPlacaIndisponivel("Token da API de placas inválido — confira o APIPLACAS_TOKEN.")
    if resp.status_code == 406:
        raise ConsultaPlacaIndisponivel("Nenhum resultado encontrado para essa placa.")
    if resp.status_code == 429:
        raise ConsultaPlacaIndisponivel("Limite diário de consultas de placa atingido — tente amanhã.")
    resp.raise_for_status()

    dados = resp.json()
    db.salvar_cache_placa(placa_norm, dados)
    return dados, False
