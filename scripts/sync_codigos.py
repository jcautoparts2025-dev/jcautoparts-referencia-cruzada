"""Reconstrói do zero o índice de códigos (produtos + codigos_index) no Turso,
buscando os anúncios ativos direto na API do Mercado Livre (somente leitura —
ver [[feedback_ml_api_readonly]]). Rodar manualmente ou via
.github/workflows/sync_codigos.yml (cron diário)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import ml_client
from codigos import (
    extrair_ano_range,
    extrair_codigo_ref_da_descricao,
    extrair_codigos_do_atributo_oem,
    extrair_referencias_compativeis,
    normalizar_codigo,
)

_REGRAS_CATEGORIA = [
    (r"repar\w+.*dire[çc][ãa]o", "Reparo de Caixa de Direção (Kit de Reparo)"),
    (r"dire[çc][ãa]o.*el[ée]tric", "Caixa de Direção Elétrica"),
    (r"caixa.*dire[çc][ãa]o", "Caixa de Direção Mecânica"),
    (r"bandeja|balan[çc]a", "Par Bandeja/Balança de Suspensão"),
    (r"mola.*diant", "Mola Dianteira"),
    (r"mola.*tras", "Mola Traseira"),
    (r"batente|coxim.*amortecedor", "Kit Batente/Coxim de Amortecedor"),
    (r"amortecedor", "Amortecedor + Kit de Suspensão"),
    (r"bra[çc]o oscilante", "Braço Oscilante"),
    (r"morceguinho|barra tensora", "Morceguinho / Suporte Barra Tensora"),
    (r"coxim.*motor", "Coxim de Motor"),
]


def inferir_categoria(titulo):
    t = titulo.lower()
    for padrao, categoria in _REGRAS_CATEGORIA:
        if re.search(padrao, t):
            return categoria
    return "Outros"


def _attr(attributes, nome):
    for a in attributes:
        if (a.get("name") or "").strip() == nome:
            return a.get("value_name")
    return None


def processar_item(item, description):
    mlb_id = item["id"]
    attributes = item.get("attributes", [])
    titulo = item.get("title", "")
    sku = _attr(attributes, "SKU") or item.get("seller_custom_field")
    marca = _attr(attributes, "Marca")
    numero_peca = _attr(attributes, "Número de peça")
    codigo_oem = _attr(attributes, "Código OEM")
    texto_desc = description.get("plain_text", "") or ""

    codigos_brutos = []  # (codigo_original, marca, fonte)
    if sku:
        codigos_brutos.append((sku, "JC Auto Parts", "sku"))
    if numero_peca:
        codigos_brutos.append((numero_peca, marca, "numero_de_peca"))
    for codigo, marca_tok in extrair_codigos_do_atributo_oem(codigo_oem):
        codigos_brutos.append((codigo, marca_tok or marca, "codigo_oem"))
    ref = extrair_codigo_ref_da_descricao(texto_desc)
    if ref:
        codigos_brutos.append((ref, marca, "codigo_ref"))
    for codigo in extrair_referencias_compativeis(texto_desc):
        codigos_brutos.append((codigo, marca, "referencias_compativeis"))

    # Dedup por (codigo_normalizado, fonte) preservando o primeiro rótulo original.
    vistos = set()
    codigos_unicos = []
    for codigo_original, marca_tok, fonte in codigos_brutos:
        chave = (normalizar_codigo(codigo_original), fonte)
        if not chave[0] or chave in vistos:
            continue
        vistos.add(chave)
        codigos_unicos.append({"codigo_original": codigo_original, "marca": marca_tok, "fonte": fonte})

    ano_inicio, ano_fim = extrair_ano_range(titulo)
    produto = {
        "mlb_id": mlb_id,
        "sku": sku,
        "titulo": titulo,
        "categoria": inferir_categoria(titulo),
        "marca": marca,
        "link": item.get("permalink"),
        "codigos": codigos_unicos,
        "ano_inicio": ano_inicio,
        "ano_fim": ano_fim,
    }
    codigos_index = [
        {
            "codigo_normalizado": normalizar_codigo(c["codigo_original"]),
            "mlb_id": mlb_id,
            "codigo_original": c["codigo_original"],
            "marca": c["marca"],
            "fonte": c["fonte"],
        }
        for c in codigos_unicos
    ]
    return produto, codigos_index


def main():
    print("Buscando lista de anúncios ativos...")
    item_ids = ml_client.listar_todos_os_item_ids()
    print(f"{len(item_ids)} anúncios encontrados. Buscando detalhes...")

    resultados, erros = ml_client.buscar_itens_em_paralelo(item_ids)
    if erros:
        print(f"AVISO: {len(erros)} itens falharam ao buscar:")
        for iid, e in erros[:10]:
            print(f"  {iid}: {e}")

    produtos, codigos_index = [], []
    for r in resultados:
        produto, codigos = processar_item(r["item"], r["description"])
        produtos.append(produto)
        codigos_index.extend(codigos)

    print(f"Gravando {len(produtos)} produtos e {len(codigos_index)} códigos no Turso...")
    db.substituir_catalogo(produtos, codigos_index)
    print("Concluído.")


if __name__ == "__main__":
    main()
