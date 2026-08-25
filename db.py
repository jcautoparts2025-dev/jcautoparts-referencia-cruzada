"""Acesso ao banco Turso. Toda conexão é aberta e fechada aqui (try/finally).
Este módulo não fala com a API do Mercado Livre nem com a API da Claude."""
import json
import os
from datetime import datetime, timedelta

import libsql_client

try:
    import streamlit as st
except ImportError:  # scripts standalone (scripts/) não precisam do streamlit
    st = None

_LOCAL_ENV_FALLBACK = os.path.join(
    os.path.expanduser("~"), ".turso_credentials", "jcautoparts_referencia_cruzada.env"
)


def _read_local_env_fallback():
    values = {}
    if os.path.exists(_LOCAL_ENV_FALLBACK):
        # utf-8-sig: tolera BOM (arquivos gerados via PowerShell costumam ter um).
        with open(_LOCAL_ENV_FALLBACK, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def get_secret(key):
    """Lê um segredo de env vars -> st.secrets -> arquivo local de fallback, nessa ordem."""
    if key in os.environ:
        return os.environ[key]
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return _read_local_env_fallback().get(key)


def _normalize_url(url):
    # libsql:// (websocket/Hrana) falha o handshake neste ambiente; https:// funciona.
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url


def get_connection():
    url = _normalize_url(get_secret("TURSO_DATABASE_URL"))
    token = get_secret("TURSO_AUTH_TOKEN")
    if not url or not token:
        raise RuntimeError(
            "TURSO_DATABASE_URL/TURSO_AUTH_TOKEN não encontrados (env, st.secrets ou "
            f"{_LOCAL_ENV_FALLBACK})"
        )
    return libsql_client.create_client_sync(url=url, auth_token=token)


def init_schema():
    conn = get_connection()
    try:
        conn.batch([
            """
            CREATE TABLE IF NOT EXISTS produtos (
                mlb_id          TEXT PRIMARY KEY,
                sku             TEXT,
                titulo          TEXT,
                categoria       TEXT,
                marca           TEXT,
                link            TEXT,
                codigos_json    TEXT,
                atualizado_em   TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS codigos_index (
                codigo_normalizado  TEXT NOT NULL,
                mlb_id              TEXT NOT NULL,
                codigo_original     TEXT NOT NULL,
                marca               TEXT,
                fonte               TEXT,
                PRIMARY KEY (codigo_normalizado, mlb_id, codigo_original)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_codigos_normalizado ON codigos_index(codigo_normalizado)",
            """
            CREATE TABLE IF NOT EXISTS consultas_ia_cache (
                codigo_normalizado  TEXT PRIMARY KEY,
                codigo_pesquisado   TEXT,
                resposta_json       TEXT,
                consultado_em       TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS credentials (
                chave   TEXT PRIMARY KEY,
                valor   TEXT
            )
            """,
        ])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Escrita (usada só pelo scripts/sync_codigos.py)
# ---------------------------------------------------------------------------

def substituir_catalogo(produtos, codigos):
    """Regrava as tabelas produtos/codigos_index do zero a partir de uma
    lista completa nova (mesma filosofia do refresh do catálogo).
    produtos: [{mlb_id, sku, titulo, categoria, marca, link, codigos_json}]
    codigos:  [{codigo_normalizado, mlb_id, codigo_original, marca, fonte}]
    """
    conn = get_connection()
    try:
        agora = datetime.utcnow().isoformat()
        stmts = ["DELETE FROM codigos_index", "DELETE FROM produtos"]
        for p in produtos:
            stmts.append((
                """INSERT INTO produtos
                   (mlb_id, sku, titulo, categoria, marca, link, codigos_json, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [p["mlb_id"], p.get("sku"), p.get("titulo"), p.get("categoria"),
                 p.get("marca"), p.get("link"), json.dumps(p.get("codigos", []), ensure_ascii=False),
                 agora],
            ))
        for c in codigos:
            stmts.append((
                """INSERT OR IGNORE INTO codigos_index
                   (codigo_normalizado, mlb_id, codigo_original, marca, fonte)
                   VALUES (?, ?, ?, ?, ?)""",
                [c["codigo_normalizado"], c["mlb_id"], c["codigo_original"], c.get("marca"), c.get("fonte")],
            ))
        conn.batch(stmts)
    finally:
        conn.close()


def get_credential(chave):
    conn = get_connection()
    try:
        rs = conn.execute("SELECT valor FROM credentials WHERE chave = ?", [chave])
        return rs.rows[0][0] if rs.rows else None
    finally:
        conn.close()


def set_credential(chave, valor):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO credentials (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            [chave, valor],
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Leitura (usada pelo app.py)
# ---------------------------------------------------------------------------

def buscar_por_codigo(codigo_normalizado):
    """Retorna a lista de produtos (dict) cujo mlb_id bate com o código normalizado."""
    conn = get_connection()
    try:
        rs = conn.execute(
            "SELECT DISTINCT mlb_id FROM codigos_index WHERE codigo_normalizado = ?",
            [codigo_normalizado],
        )
        mlb_ids = [row[0] for row in rs.rows]
        if not mlb_ids:
            return []
        placeholders = ",".join("?" * len(mlb_ids))
        rs2 = conn.execute(
            f"SELECT mlb_id, sku, titulo, categoria, marca, link, codigos_json "
            f"FROM produtos WHERE mlb_id IN ({placeholders})",
            mlb_ids,
        )
        produtos = []
        for row in rs2.rows:
            produtos.append({
                "mlb_id": row[0], "sku": row[1], "titulo": row[2], "categoria": row[3],
                "marca": row[4], "link": row[5],
                "codigos": json.loads(row[6]) if row[6] else [],
            })
        return produtos
    finally:
        conn.close()


def total_produtos_indexados():
    conn = get_connection()
    try:
        rs = conn.execute("SELECT COUNT(*) FROM produtos")
        return rs.rows[0][0] if rs.rows else 0
    finally:
        conn.close()


def get_cache_ia(codigo_normalizado, max_idade_dias):
    conn = get_connection()
    try:
        rs = conn.execute(
            "SELECT resposta_json, consultado_em FROM consultas_ia_cache WHERE codigo_normalizado = ?",
            [codigo_normalizado],
        )
        if not rs.rows:
            return None
        resposta_json, consultado_em = rs.rows[0]
        try:
            idade = datetime.utcnow() - datetime.fromisoformat(consultado_em)
        except ValueError:
            return None
        if idade > timedelta(days=max_idade_dias):
            return None
        return json.loads(resposta_json)
    finally:
        conn.close()


def salvar_cache_ia(codigo_normalizado, codigo_pesquisado, resposta):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO consultas_ia_cache (codigo_normalizado, codigo_pesquisado, resposta_json, consultado_em) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(codigo_normalizado) DO UPDATE SET "
            "codigo_pesquisado = excluded.codigo_pesquisado, "
            "resposta_json = excluded.resposta_json, "
            "consultado_em = excluded.consultado_em",
            [codigo_normalizado, codigo_pesquisado, json.dumps(resposta, ensure_ascii=False),
             datetime.utcnow().isoformat()],
        )
    finally:
        conn.close()
