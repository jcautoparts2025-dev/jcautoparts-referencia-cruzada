"""Normalização e parsing de códigos de peça. Sem dependências externas —
usado tanto pelo app (busca) quanto pelo script de sync (extração)."""
import re

_SEPARADORES = re.compile(r"[\s.\-/_]")


def normalizar_codigo(codigo):
    """Chave de busca: maiúsculas, sem espaço/ponto/hífen/barra/underscore."""
    if not codigo:
        return ""
    return _SEPARADORES.sub("", codigo).upper()


def separar_codigo_e_marca(token):
    """Um token de 'Código OEM' pode vir como 'CODIGO' ou 'CODIGO MARCA'
    (ex.: '15900459S TRW', 'NCD30206S NAKATA'). Primeira palavra é o código,
    o resto (se houver) é a marca."""
    token = token.strip()
    if not token:
        return None, None
    partes = token.split(None, 1)
    codigo = partes[0]
    marca = partes[1].strip() if len(partes) > 1 else None
    return codigo, marca


def extrair_codigos_do_atributo_oem(valor):
    """'Código OEM' vem como lista separada por vírgula. Retorna
    [(codigo_original, marca_ou_none), ...]."""
    if not valor:
        return []
    out = []
    for token in valor.split(","):
        codigo, marca = separar_codigo_e_marca(token)
        if codigo:
            out.append((codigo, marca))
    return out


_RE_ANO = re.compile(r"(19|20)\d{2}")


def extrair_ano_range(titulo):
    """Acha todo ano de 4 dígitos plausível (1960-2035) no título e devolve
    (ano_inicio, ano_fim) = (min, max). (None, None) se não achar nenhum."""
    anos = [int(m.group(0)) for m in _RE_ANO.finditer(titulo or "")]
    anos = [a for a in anos if 1960 <= a <= 2035]
    if not anos:
        return None, None
    return min(anos), max(anos)


_RE_CODIGO_REF = re.compile(r"C[oó]digo\s+Ref\.?:?\s*([A-Za-z0-9][A-Za-z0-9.\-/]*)", re.IGNORECASE)
_RE_REFERENCIAS_SECAO = re.compile(
    r"Refer[êe]ncias\s+Compat[íi]veis:?\s*\n((?:.+\n?)+?)(?:\n\s*\n|\Z)",
    re.IGNORECASE,
)


def extrair_codigo_ref_da_descricao(texto):
    """Procura 'Código Ref.: XXXX' no corpo da descrição (texto livre)."""
    if not texto:
        return None
    m = _RE_CODIGO_REF.search(texto)
    return m.group(1).strip() if m else None


def extrair_referencias_compativeis(texto):
    """Procura uma seção 'Referências Compatíveis:' e devolve a lista de
    códigos (uma por linha) dentro dela."""
    if not texto:
        return []
    m = _RE_REFERENCIAS_SECAO.search(texto)
    if not m:
        return []
    linhas = [l.strip("•- \t") for l in m.group(1).splitlines()]
    return [l for l in linhas if l]
