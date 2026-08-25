"""Normalização e parsing de códigos de peça. Sem dependências externas —
usado tanto pelo app (busca) quanto pelo script de sync (extração)."""
import re

_SEPARADORES = re.compile(r"[\s.\-/_]")

# Aliases conhecidos -> nome canônico das marcas mais comuns do setor.
# Mantém qualquer marca fora dessa lista como está (ex.: XINTEC, JTEKT, ZF)
# em vez de forçar num rótulo genérico.
_MARCA_ALIASES = {
    "TRW": "TRW",
    "TRW AUTOMOTIVE": "TRW",
    "NAKATA": "NAKATA",
    "NAKATA AUTOMOTIVA": "NAKATA",
    "COFAP": "COFAP",
    "MONROE": "MONROE",
    "MONROE AXIOS": "MONROE",
    "AXIOS": "AXIOS",
    "PERFECT": "PERFECT",
    "INDISA": "INDISA",
    "AMPRI": "AMPRI",
    "AMP": "AMPRI",
}


def eh_nome_de_marca(codigo):
    """True se o 'código' é na verdade só o nome de uma marca conhecida
    (ex.: um anúncio que preencheu 'Número de peça' com 'TRW' em vez de um
    código de verdade)."""
    return bool(codigo) and codigo.strip().upper() in _MARCA_ALIASES


def normalizar_marca(marca):
    """Mapeia abreviações conhecidas (ex.: 'AMP' -> 'AMPRI') para o nome
    canônico da marca. Marcas fora do dicionário voltam como vieram
    (title-case), sem forçar num rótulo genérico."""
    if not marca:
        return None
    chave = marca.strip().upper()
    if chave in _MARCA_ALIASES:
        return _MARCA_ALIASES[chave]
    return marca.strip()


def normalizar_codigo(codigo):
    """Chave de busca: maiúsculas, sem espaço/ponto/hífen/barra/underscore."""
    if not codigo:
        return ""
    return _SEPARADORES.sub("", codigo).upper()


def separar_codigo_e_marca(token):
    """Um token de 'Código OEM' pode vir como 'CODIGO' ou 'CODIGO MARCA'
    (ex.: '15900459S TRW', 'NCD30206S NAKATA', 'CODIGO (MARCA)'). Primeira
    palavra é o código, o resto (se houver, sem parênteses) é a marca."""
    token = token.strip()
    if not token:
        return None, None
    partes = token.split(None, 1)
    codigo = partes[0]
    marca = partes[1].strip().strip("()").strip() if len(partes) > 1 else None
    return codigo, (marca or None)


def extrair_codigos_do_atributo_oem(valor):
    """'Código OEM' vem como lista separada por vírgula (às vezes também por
    barra). Retorna [(codigo_original, marca_ou_none), ...]. Alguns anúncios
    preenchem esse campo só com o nome de uma marca (ex.: 'TRW') em vez de
    um código de verdade — esses tokens são descartados."""
    if not valor:
        return []
    out = []
    for bruto in valor.split(","):
        for token in bruto.split("/"):
            codigo, marca = separar_codigo_e_marca(token)
            if codigo and not eh_nome_de_marca(codigo):
                out.append((codigo, normalizar_marca(marca) if marca else "OEM"))
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


_RE_CODIGO_REF = re.compile(
    r"C[oó]digo\s+Ref\.?:?\s*([A-Za-z0-9][A-Za-z0-9.\-/]*)"
    r"(?:\s*\n\s*Marca:\s*(.+))?",
    re.IGNORECASE,
)
_RE_REFERENCIAS_SECAO = re.compile(
    r"Refer[êe]ncias\s+Compat[íi]veis:?\s*\n((?:.+\n?)+?)(?:\n\s*\n|\Z)",
    re.IGNORECASE,
)


def extrair_codigo_ref_da_descricao(texto):
    """Procura 'Código Ref.: XXXX' (e, se houver logo abaixo, 'Marca: YYYY')
    no corpo da descrição (texto livre). Retorna (codigo, marca_ou_none) —
    a marca daqui é mais confiável que o atributo "Marca" do item, que às
    vezes descreve o sistema original (ex.: "TRW") em vez da marca do kit
    de reparo em si."""
    if not texto:
        return None, None
    m = _RE_CODIGO_REF.search(texto)
    if not m:
        return None, None
    codigo = m.group(1).strip()
    marca = m.group(2).strip() if m.group(2) else None
    return codigo, marca


def extrair_referencias_compativeis(texto):
    """Procura uma seção 'Referências Compatíveis:' e devolve a lista de
    códigos dentro dela — um por linha, ou vários por linha separados por
    vírgula (os dois formatos aparecem nos anúncios reais)."""
    if not texto:
        return []
    m = _RE_REFERENCIAS_SECAO.search(texto)
    if not m:
        return []
    codigos = []
    for linha in m.group(1).splitlines():
        linha = linha.strip("•- \t")
        if not linha:
            continue
        codigos.extend(c.strip() for c in linha.split(",") if c.strip())
    return codigos
