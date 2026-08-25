import streamlit as st

import db
from ai_lookup import BuscaIAIndisponivel, pesquisar_codigo_via_ia
from codigos import normalizar_codigo
from config import APP_ICON, APP_TITLE
from placa_client import ConsultaPlacaIndisponivel, consultar_placa, normalizar_placa

st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout="centered")

st.title(f"{APP_ICON} Referência Cruzada de Peças")

if "resultado_ia" not in st.session_state:
    st.session_state.resultado_ia = None
if "resultado_ia_codigo" not in st.session_state:
    st.session_state.resultado_ia_codigo = None
if "resultado_ia_do_cache" not in st.session_state:
    st.session_state.resultado_ia_do_cache = False
if "resultado_placa" not in st.session_state:
    st.session_state.resultado_placa = None
if "resultado_placa_valor" not in st.session_state:
    st.session_state.resultado_placa_valor = None
if "resultado_placa_do_cache" not in st.session_state:
    st.session_state.resultado_placa_do_cache = False


def _render_produto(produto):
    with st.container(border=True):
        st.markdown(f"**{produto['titulo']}**")
        cols = st.columns(3)
        cols[0].markdown(f"**SKU:** {produto['sku'] or '—'}")
        cols[1].markdown(f"**Categoria:** {produto['categoria'] or '—'}")
        cols[2].markdown(f"[Abrir no Mercado Livre ↗]({produto['link']})")
        ano_inicio, ano_fim = produto.get("ano_inicio"), produto.get("ano_fim")
        if ano_inicio and ano_fim:
            faixa = f"{ano_inicio}" if ano_inicio == ano_fim else f"{ano_inicio}–{ano_fim}"
            st.caption(f"Aplicação (pelo título do anúncio): {faixa}")
        if produto["codigos"]:
            with st.expander("Códigos de fabricante conhecidos deste item"):
                for c in produto["codigos"]:
                    marca = f" ({c['marca']})" if c.get("marca") else ""
                    st.write(f"- {c['codigo_original']}{marca}")


aba_codigo, aba_veiculo, aba_placa = st.tabs(["🔎 Por código", "🚗 Por veículo", "🚙 Por placa"])

with aba_codigo:
    st.caption(
        "Digite um código OEM, de fábrica, de uma marca conhecida ou o seu próprio SKU "
        "para achar compatibilidades e conferir se você já vende a peça."
    )
    codigo_input = st.text_input("Código da peça", placeholder="Ex.: 1S0407151, 15900459S, BD040...")

    if codigo_input:
        codigo_norm = normalizar_codigo(codigo_input)
        produtos = db.buscar_por_codigo(codigo_norm)

        if produtos:
            st.success(f"🎯 Encontrado no seu catálogo — {len(produtos)} item(ns) compatível(is):")
            for p in produtos:
                _render_produto(p)
        else:
            st.warning("Não encontrado no índice local do seu catálogo.")

            buscar = st.button("🔍 Pesquisar com IA em catálogos de fabricantes")
            forcar = False
            if st.session_state.resultado_ia_codigo == codigo_norm and st.session_state.resultado_ia is not None:
                forcar = st.button("🔄 Forçar nova busca (ignorar cache)")

            if buscar or forcar:
                with st.spinner("Pesquisando em catálogos de fabricantes..."):
                    try:
                        resultado, veio_do_cache = pesquisar_codigo_via_ia(codigo_input, forcar=forcar)
                        st.session_state.resultado_ia = resultado
                        st.session_state.resultado_ia_codigo = codigo_norm
                        st.session_state.resultado_ia_do_cache = veio_do_cache
                    except BuscaIAIndisponivel as e:
                        st.session_state.resultado_ia = None
                        st.error(f"Busca por IA indisponível: {e}")

            resultado = (
                st.session_state.resultado_ia
                if st.session_state.resultado_ia_codigo == codigo_norm
                else None
            )
            if resultado:
                if st.session_state.resultado_ia_do_cache:
                    st.caption("📦 Resultado em cache (buscado anteriormente).")
                st.info("ℹ️ Resultado de busca por IA — confirme antes de usar comercialmente.")
                st.markdown(f"**Peça:** {resultado['descricao_peca']}")

                if resultado["aplicacoes"]:
                    st.markdown("**Aplicações:**")
                    for ap in resultado["aplicacoes"]:
                        st.write(f"- {ap['marca_veiculo']} {ap['modelo']} ({ap['anos']})")

                st.markdown("**Códigos equivalentes encontrados:**")
                algum_match = False
                for eq in resultado["codigos_equivalentes"]:
                    eq_norm = normalizar_codigo(eq["codigo"])
                    matches_locais = db.buscar_por_codigo(eq_norm)
                    if matches_locais:
                        algum_match = True
                        st.success(f"🎯 {eq['codigo']} ({eq['marca']}) — você já vende! Veja abaixo.")
                        for p in matches_locais:
                            _render_produto(p)
                    else:
                        st.write(f"- {eq['codigo']} ({eq['marca']})")

                if not algum_match:
                    st.info("Nenhum dos códigos equivalentes encontrados bate com seu catálogo atual.")

                if resultado.get("observacao"):
                    st.caption(resultado["observacao"])

with aba_veiculo:
    st.caption(
        "Digite o nome/modelo do carro (e, se quiser, o ano) para ver quais peças do seu "
        "catálogo servem nele e os códigos de fabricante conhecidos de cada uma."
    )
    col_nome, col_ano = st.columns([3, 1])
    nome_veiculo = col_nome.text_input(
        "Carro / modelo", placeholder="Ex.: Gol, Uno, Peugeot 306, HB20..."
    )
    ano_texto = col_ano.text_input("Ano (opcional)", placeholder="Ex.: 2015")

    if nome_veiculo:
        ano = None
        if ano_texto.strip():
            if ano_texto.strip().isdigit():
                ano = int(ano_texto.strip())
            else:
                st.error("Ano inválido — digite só números, ex.: 2015.")

        if ano_texto.strip() and ano is None:
            pass  # erro já mostrado acima, não busca
        else:
            produtos_veiculo = db.buscar_por_veiculo(nome_veiculo, ano=ano)
            if produtos_veiculo:
                st.success(
                    f"🎯 {len(produtos_veiculo)} item(ns) do seu catálogo compatível(is) com "
                    f"\"{nome_veiculo}\"" + (f" ({ano})" if ano else "") + ":"
                )
                for p in produtos_veiculo:
                    _render_produto(p)
            else:
                st.warning(
                    "Nenhum item do seu catálogo encontrado para esse veículo"
                    + (" nesse ano" if ano else "") + "."
                )

with aba_placa:
    st.caption(
        "Digite a placa do veículo (Mercosul AAA0X00 ou antiga AAA9999) para identificar o "
        "carro e ver as peças do seu catálogo compatíveis. Cada consulta nova é paga — "
        "resultados já consultados ficam salvos e não geram custo de novo."
    )
    placa_input = st.text_input("Placa", placeholder="Ex.: ABC1D23")

    if placa_input:
        placa_norm = normalizar_placa(placa_input)

        consultar = st.button("🚙 Consultar placa")
        forcar_placa = False
        if st.session_state.resultado_placa_valor == placa_norm and st.session_state.resultado_placa is not None:
            forcar_placa = st.button("🔄 Forçar nova consulta (paga)")

        if consultar or forcar_placa:
            with st.spinner("Consultando placa..."):
                try:
                    dados, veio_do_cache = consultar_placa(placa_input, forcar=forcar_placa)
                    st.session_state.resultado_placa = dados
                    st.session_state.resultado_placa_valor = placa_norm
                    st.session_state.resultado_placa_do_cache = veio_do_cache
                except ConsultaPlacaIndisponivel as e:
                    st.session_state.resultado_placa = None
                    st.error(f"Consulta de placa indisponível: {e}")

        dados_placa = (
            st.session_state.resultado_placa
            if st.session_state.resultado_placa_valor == placa_norm
            else None
        )
        if dados_placa:
            if st.session_state.resultado_placa_do_cache:
                st.caption("📦 Resultado em cache (consultado anteriormente, sem custo extra).")

            marca = dados_placa.get("marca") or dados_placa.get("MARCA") or ""
            modelo = dados_placa.get("modelo") or dados_placa.get("MODELO") or ""
            ano_texto_placa = str(dados_placa.get("anoModelo") or dados_placa.get("ano") or "").strip()
            ano_placa = int(ano_texto_placa) if ano_texto_placa.isdigit() else None

            st.success(f"🚗 {marca} {modelo}" + (f" ({ano_placa})" if ano_placa else ""))

            if modelo:
                produtos_placa = db.buscar_por_veiculo(modelo, ano=ano_placa)
                if produtos_placa:
                    st.success(f"🎯 {len(produtos_placa)} item(ns) do seu catálogo compatível(is):")
                    for p in produtos_placa:
                        _render_produto(p)
                else:
                    st.warning("Nenhum item do seu catálogo encontrado para esse veículo.")
            else:
                st.warning("A consulta não retornou o modelo do veículo.")

st.divider()
try:
    total = db.total_produtos_indexados()
    if total:
        st.caption(f"Índice local: {total} produtos do seu catálogo.")
except Exception:
    pass
