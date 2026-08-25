"""Cliente somente-leitura para a API do Mercado Livre. Ver [[feedback_ml_api_readonly]] —
este módulo nunca deve fazer POST/PUT/DELETE contra a API do ML.

O refresh token roda e é persistido na tabela `credentials` do Turso (nunca no
arquivo local compartilhado com o projeto do catálogo) — mesmo padrão usado no
antigo projeto financeiro. Na primeira execução, semeia a partir de
ML_CLIENT_ID/ML_CLIENT_SECRET/ML_REFRESH_TOKEN/ML_USER_ID (env, st.secrets, ou o
arquivo local .ml_credentials\\jcautoparts_catalogo_leitura.env, só leitura)."""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import db
from config import ML_API_BASE

_LOCAL_ML_ENV_FALLBACK = os.path.join(
    os.path.expanduser("~"), ".ml_credentials", "jcautoparts_catalogo_leitura.env"
)


def _read_local_ml_env_fallback():
    values = {}
    if os.path.exists(_LOCAL_ML_ENV_FALLBACK):
        with open(_LOCAL_ML_ENV_FALLBACK, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def _get_ml_secret(key):
    """env -> st.secrets (via db.get_secret) -> arquivo local .ml_credentials (só leitura, nunca gravado)."""
    val = db.get_secret(key)
    if val:
        return val
    return _read_local_ml_env_fallback().get(key)


_session = requests.Session()


def _get_access_token():
    refresh_token = db.get_credential("ML_REFRESH_TOKEN") or _get_ml_secret("ML_REFRESH_TOKEN")
    client_id = _get_ml_secret("ML_CLIENT_ID")
    client_secret = _get_ml_secret("ML_CLIENT_SECRET")
    if not all([refresh_token, client_id, client_secret]):
        raise RuntimeError("Credenciais ML incompletas (ML_CLIENT_ID/ML_CLIENT_SECRET/ML_REFRESH_TOKEN)")

    resp = _session.post(
        f"{ML_API_BASE}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tok = resp.json()
    # Persiste o refresh_token rotacionado no Turso — nunca no arquivo local compartilhado.
    db.set_credential("ML_REFRESH_TOKEN", tok["refresh_token"])
    db.set_credential("ML_ACCESS_TOKEN", tok["access_token"])
    return tok["access_token"]


def _auth_headers():
    return {"Authorization": f"Bearer {_get_access_token()}"}


def listar_todos_os_item_ids():
    user_id = _get_ml_secret("ML_USER_ID")
    ids = []
    offset = 0
    limit = 100
    headers = _auth_headers()
    while True:
        resp = _session.get(
            f"{ML_API_BASE}/users/{user_id}/items/search",
            headers=headers,
            params={"limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        ids.extend(results)
        paging = data.get("paging", {})
        offset += limit
        if offset >= paging.get("total", 0) or not results:
            break
    return ids


def get_item(item_id):
    resp = _session.get(f"{ML_API_BASE}/items/{item_id}", headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_item_description(item_id):
    resp = _session.get(f"{ML_API_BASE}/items/{item_id}/description", headers=_auth_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def buscar_itens_em_paralelo(item_ids, max_workers=12):
    """Retorna (sucesso, erros). sucesso: [{item, description}]. erros: [(id, exceção)]."""
    sucesso, erros = [], []

    def _fetch(item_id):
        item = get_item(item_id)
        try:
            desc = get_item_description(item_id)
        except requests.HTTPError:
            desc = {"plain_text": ""}
        return item, desc

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch, iid): iid for iid in item_ids}
        for fut in as_completed(futures):
            iid = futures[fut]
            try:
                item, desc = fut.result()
                sucesso.append({"item": item, "description": desc})
            except Exception as e:
                erros.append((iid, e))
    return sucesso, erros
