"""Coleta a categoria 'Caixas de Direção' da Camillo Parts (distribuidora de
autopeças, camilloparts.com.br) — fonte pública, gratuita, sem precisar de
IA nem login. Cada página da categoria embute um JSON com os produtos
(`var dataVitrine... = {..., itens: [...]}`), então não precisa nem de
parsing de HTML. Serve como referência externa (independente dos próprios
anúncios) pra comparar códigos/aplicações.

Uso: python scripts/scrape_camilloparts.py
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import db
from codigos import eh_nome_de_marca, extrair_ano_range, normalizar_codigo

BASE_URL = "https://www.camilloparts.com.br/caixas-de-direcao"
FONTE = "camilloparts"
MAX_PAGINAS = 100  # trava de segurança
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_RE_ITENS = re.compile(r"itens:\s*\[")
_RE_CODIGOS_LISTA = re.compile(r"C[oó]digos?:?\s*(.+)", re.IGNORECASE)


def _extrair_itens_da_pagina(html):
    m = _RE_ITENS.search(html)
    if not m:
        return []
    start = m.end() - 1  # posição do '['
    depth, end = 0, start
    for i in range(start, len(html)):
        if html[i] == "[":
            depth += 1
        elif html[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(html[start:end])


def _extrair_codigos_do_texto(texto):
    """Acha a lista de códigos depois de 'Código(s):' num texto livre e
    devolve os tokens limpos (sem sufixo tipo '- Produto Novo' grudado)."""
    if not texto:
        return []
    m = _RE_CODIGOS_LISTA.search(texto)
    if not m:
        return []
    tokens = []
    for token in m.group(1).split(","):
        token = token.strip()
        # remove sufixos tipo "1322687 - Produto Novo" que grudam no último token
        token = re.split(r"\s+-\s+", token)[0].strip()
        if token and not eh_nome_de_marca(token):
            tokens.append(token)
    return tokens


def buscar_pagina(pagina):
    url = BASE_URL if pagina == 1 else f"{BASE_URL}?p={pagina}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return _extrair_itens_da_pagina(resp.text)


def processar_item(item):
    produto_id = str(item.get("codigo") or item.get("derivacao_id") or item.get("link"))
    titulo = item.get("titulo") or item.get("nome") or ""
    aplicacao = item.get("complemento") or ""
    marca_item = item.get("marca")
    link = "https://www.camilloparts.com.br" + item["link"] if item.get("link") else None
    categoria = item.get("categoria")

    codigos_brutos = set(_extrair_codigos_do_texto(titulo)) | set(_extrair_codigos_do_texto(aplicacao))
    ano_inicio, ano_fim = extrair_ano_range(f"{titulo} {aplicacao}")

    produto = {
        "produto_id": produto_id,
        "titulo": titulo,
        "aplicacao": aplicacao,
        "marca_item": marca_item,
        "link": link,
        "categoria": categoria,
        "ano_inicio": ano_inicio,
        "ano_fim": ano_fim,
    }
    codigos = [
        {
            "codigo_normalizado": normalizar_codigo(c),
            "produto_id": produto_id,
            "codigo_original": c,
            "marca": None,
        }
        for c in codigos_brutos
        if normalizar_codigo(c)
    ]
    return produto, codigos


def main():
    print("Coletando Camillo Parts — Caixas de Direção...")
    todos_produtos, todos_codigos = [], []
    vistos_ids = set()

    for pagina in range(1, MAX_PAGINAS + 1):
        try:
            itens = buscar_pagina(pagina)
        except requests.RequestException as e:
            print(f"  página {pagina}: erro ({e}), parando.")
            break
        if not itens:
            print(f"  página {pagina}: vazia, fim da paginação.")
            break

        novos_nesta_pagina = 0
        for item in itens:
            produto, codigos = processar_item(item)
            if produto["produto_id"] in vistos_ids:
                continue
            vistos_ids.add(produto["produto_id"])
            todos_produtos.append(produto)
            todos_codigos.extend(codigos)
            novos_nesta_pagina += 1

        print(f"  página {pagina}: {len(itens)} itens ({novos_nesta_pagina} novos)")
        time.sleep(0.5)  # gentileza com o servidor deles

    print(f"\nTotal: {len(todos_produtos)} produtos, {len(todos_codigos)} códigos extraídos.")
    print("Gravando no Turso...")
    db.substituir_referencia_externa(FONTE, todos_produtos, todos_codigos)
    print("Concluído.")


if __name__ == "__main__":
    main()
