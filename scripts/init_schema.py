"""Cria (se não existirem) as tabelas produtos, codigos_index, consultas_ia_cache
e credentials no banco Turso configurado em TURSO_DATABASE_URL/TURSO_AUTH_TOKEN."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db

if __name__ == "__main__":
    db.init_schema()
    print("Schema criado/verificado com sucesso.")
