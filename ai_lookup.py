"""Busca de referência cruzada via API da Claude (web search + saída estruturada),
usada como fallback quando o código não está no índice local. Resultado é
cacheado no Turso (ver db.get_cache_ia/salvar_cache_ia)."""
import json

import anthropic

import db
from codigos import normalizar_codigo
from config import IA_CACHE_DIAS, MARCAS_PRIORITARIAS

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "codigo_pesquisado": {"type": "string"},
        "descricao_peca": {"type": "string"},
        "aplicacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marca_veiculo": {"type": "string"},
                    "modelo": {"type": "string"},
                    "anos": {"type": "string"},
                },
                "required": ["marca_veiculo", "modelo", "anos"],
                "additionalProperties": False,
            },
        },
        "codigos_equivalentes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string"},
                    "marca": {"type": "string"},
                },
                "required": ["codigo", "marca"],
                "additionalProperties": False,
            },
        },
        "observacao": {"type": "string"},
    },
    "required": ["codigo_pesquisado", "descricao_peca", "aplicacoes", "codigos_equivalentes", "observacao"],
    "additionalProperties": False,
}


class BuscaIAIndisponivel(Exception):
    """Erro amigável para exibir na UI em vez de stack trace."""


def _client():
    api_key = db.get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise BuscaIAIndisponivel("ANTHROPIC_API_KEY não configurada.")
    return anthropic.Anthropic(api_key=api_key)


def _montar_prompt(codigo):
    marcas = ", ".join(MARCAS_PRIORITARIAS)
    return (
        f"Pesquise o código de autopeça \"{codigo}\" (pode ser um código OEM de "
        "montadora ou um código de marca/fabricante de reposição). Priorize catálogos "
        "oficiais de fabricantes e das marcas conhecidas do mercado brasileiro de "
        f"autopeças ({marcas}). Identifique: (1) que peça é essa e sua descrição breve, "
        "(2) em quais veículos (marca, modelo, anos) ela é aplicada, (3) a lista mais "
        "completa possível de códigos equivalentes/compatíveis dessa peça em outras "
        "marcas e o código OEM original, se houver. Se não encontrar informação "
        "confiável, diga isso claramente no campo de observação em vez de inventar."
    )


def pesquisar_codigo_via_ia(codigo, forcar=False):
    """Retorna (resultado: dict, veio_do_cache: bool). Lança BuscaIAIndisponivel
    em caso de erro tratável (sem crédito, chave ausente, rate limit, etc.)."""
    codigo_norm = normalizar_codigo(codigo)

    if not forcar:
        cache = db.get_cache_ia(codigo_norm, IA_CACHE_DIAS)
        if cache is not None:
            return cache, True

    client = _client()
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=16000,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
            output_config={"format": {"type": "json_schema", "schema": _JSON_SCHEMA}, "effort": "high"},
            messages=[{"role": "user", "content": _montar_prompt(codigo)}],
        )
    except anthropic.AuthenticationError as e:
        raise BuscaIAIndisponivel(
            "Chave da API da Claude inválida ou sem crédito carregado na conta Anthropic."
        ) from e
    except anthropic.PermissionDeniedError as e:
        raise BuscaIAIndisponivel("A chave da API da Claude não tem permissão para este recurso.") from e
    except anthropic.RateLimitError as e:
        raise BuscaIAIndisponivel("Limite de requisições da API da Claude atingido — tente novamente em instantes.") from e
    except anthropic.APIStatusError as e:
        raise BuscaIAIndisponivel(f"Erro na API da Claude ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise BuscaIAIndisponivel("Não foi possível conectar à API da Claude — verifique a conexão.") from e

    texto = next((b.text for b in response.content if b.type == "text"), None)
    if texto is None:
        raise BuscaIAIndisponivel("A IA não retornou um resultado de texto válido.")

    resultado = json.loads(texto)
    db.salvar_cache_ia(codigo_norm, codigo, resultado)
    return resultado, False
