# Referência Cruzada de Peças — JC Auto Parts

Dashboard para achar, a partir de um código OEM/marca/SKU, do nome+ano do
veículo, ou da placa, quais peças do catálogo (Mercado Livre) da JC Auto Parts
atendem.

## Como funciona

1. **Índice local** (`codigos_index` no Turso): construído por
   `scripts/sync_codigos.py`, que lê todos os anúncios ativos direto da API do
   Mercado Livre (somente leitura) e extrai os campos `Código OEM`,
   `Número de peça`, `Código Ref.` (na descrição) e `Referências Compatíveis`.
   A maioria das buscas é resolvida só com esse índice, sem custo de IA.
2. **Fallback por IA** (`ai_lookup.py`): quando o código não está no índice
   local, chama a API da Claude com busca na web, priorizando catálogos de
   fabricantes e marcas conhecidas. Os códigos equivalentes encontrados são
   re-checados contra o índice local. Resultado fica em cache no Turso por
   `IA_CACHE_DIAS` (ver `config.py`).
3. **Busca por veículo** (aba "Por veículo"): busca `produtos.titulo` por
   nome/modelo do carro, com filtro opcional de ano usando `ano_inicio`/
   `ano_fim` (extraídos do título pelo sync, ver `codigos.extrair_ano_range`).
4. **Busca por placa** (aba "Por placa", `placa_client.py`): consulta a API
   Placas (apiplacas.com.br, backend WDAPI2 — serviço pago de terceiro) para
   descobrir marca/modelo/ano a partir da placa, e reaproveita a busca por
   veículo acima. Resultado cacheado no Turso (`consultas_placa_cache`), sem
   expiração — cada consulta nova custa dinheiro, então nunca paga duas vezes
   pela mesma placa a menos que o usuário force (dados do veículo raramente
   mudam).

## Setup local

```
pip install -r requirements.txt
python scripts/init_schema.py     # cria as tabelas no Turso
python scripts/sync_codigos.py    # popula o índice a partir da API do ML
streamlit run app.py
```

Segredos lidos via variáveis de ambiente, `.streamlit/secrets.toml` (não
versionado) ou os arquivos locais de fallback (`~/.turso_credentials/...`,
`~/.ml_credentials/...`) — ver `db.py:get_secret()`.

## Segredos necessários (GitHub Actions + Streamlit Cloud)

| Segredo | Origem |
|---|---|
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | Banco Turso deste projeto |
| `ML_CLIENT_ID` / `ML_CLIENT_SECRET` / `ML_REFRESH_TOKEN` / `ML_USER_ID` | App OAuth do ML já existente (somente leitura) — o refresh token só é usado para semear a tabela `credentials` no Turso na primeira sincronização; depois disso ele roda e se persiste sozinho lá, sem tocar em nenhum arquivo local |
| `ANTHROPIC_API_KEY` | Conta Anthropic — precisa ter crédito carregado para a busca por IA funcionar |
| `APIPLACAS_TOKEN` | Conta em apiplacas.com.br (pago, ~R$0,03/consulta via PIX) — só necessário na busca por placa; sem ele essa aba mostra um erro amigável, o resto do app funciona normal |

## Sync automático

`.github/workflows/sync_codigos.yml` roda 1x/dia (cron) + sob demanda
(`workflow_dispatch`). Inclui um guard que bloqueia o deploy se qualquer
chamada de escrita (`PUT/POST/DELETE/PATCH`) for introduzida contra a API do
Mercado Livre — este projeto é estritamente somente leitura lá.
