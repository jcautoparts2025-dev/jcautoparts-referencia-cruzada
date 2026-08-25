"""Constantes não-sensíveis do app. Segredos NUNCA ficam aqui — ver db.py:get_secret()."""

APP_TITLE = "Referência Cruzada de Peças — JC Auto Parts"
APP_ICON = "🔎"

ML_API_BASE = "https://api.mercadolibre.com"

# Quantos dias uma resposta de busca por IA fica em cache antes de ser refeita.
IA_CACHE_DIAS = 60

# Marcas/fabricantes a priorizar na busca por IA (mercado brasileiro de autopeças).
MARCAS_PRIORITARIAS = [
    "TRW", "Nakata", "Cofap", "SKF", "Bosch", "Delphi", "Mahle", "ZF",
    "Magneti Marelli", "Sabó", "Fras-le", "Axios", "GKN", "Continental",
    "NGK", "Monroe", "Hipper Freios", "Fremax", "Nakata Automotiva",
]

DASHBOARD_URL = "https://jcautoparts-referencia-cruzada.streamlit.app"
