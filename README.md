# Cron Macroeconômico

Agregador de notícias macroeconômicas e crypto com priorização inteligente por keywords.

## Stack

- **Python 3.11+**
- **Supabase** (PostgreSQL cloud)
- **GitHub Actions** - Cron ilimitado

## Fontes (61 RSS feeds)

| Região | Fontes |
|--------|--------|
| Crypto | CoinDesk, The Block, Cointelegraph, Decrypt, Bitcoin Magazine, CryptoSlate, Blockworks |
| Macro Global | Bloomberg, WSJ, CNBC, Economist, MarketWatch, Yahoo Finance |
| Bancos Centrais | Fed, ECB, BoE, BoJ, RBA, BoC, SNB |
| Europa | BBC, Guardian, DW, Euronews, Spiegel, Handelsblatt |
| Ásia | Nikkei, SCMP, Economic Times, Straits Times, CNA |
| América Latina | BCB, InfoMoney, Ámbito, Investing BR, MercoPress |
| Oriente Médio | Al Jazeera, Times of Israel, Middle East Eye |
| África | AllAfrica, Business Daily Africa, Morocco World News |
| Oceania | ABC Australia, SMH, RNZ |
| Commodities | OilPrice, Mining.com, Rigzone, Seeking Alpha |

## Setup Rápido

### 1. Criar projeto no Supabase

1. Acesse [supabase.com](https://supabase.com) e crie uma conta
2. Crie um novo projeto
3. Copie a connection string em **Settings > Database > Connection string > URI**

### 2. Criar repositório no GitHub

```bash
# Inicializar repo
git init
git add .
git commit -m "Initial commit"

# Criar repo no GitHub e fazer push
gh repo create cron-macroeconomic --public --source=. --push
```

### 3. Configurar secrets no GitHub

Vá em **Settings > Secrets and variables > Actions** e adicione:

| Secret | Valor |
|--------|-------|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/postgres` |

### 4. Executar setup inicial

Vá em **Actions > Setup Database > Run workflow**

### 5. Ativar cron automático

O workflow `fetch_news.yml` já está configurado para rodar a cada hora.

## Uso Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Com SQLite local
python main.py setup
python main.py fetch
python main.py stats

# Com Supabase
export DATABASE_URL="postgresql://..."
python main_cloud.py setup
python main_cloud.py fetch
```

## Estrutura

```
├── .github/workflows/
│   ├── fetch_news.yml      # Cron horário
│   ├── process_blog.yml    # Processa blog a cada 2h
│   └── setup_db.yml        # Setup inicial
├── sources.json            # Fontes RSS
├── database_supabase.py    # Driver PostgreSQL/Supabase
├── fetcher_cloud.py        # Coletor RSS
├── main_cloud.py           # CLI principal
├── processor.py            # Reescrita com IA
└── deduplication.py        # Detecção de duplicatas
```

## Keywords de Priorização

### Alta prioridade (score +1 a +2)
- **Crypto**: SEC, ETF, CBDC, BlackRock, Grayscale, stablecoin, regulation
- **Macro**: Fed, ECB, inflation, recession, GDP, interest rate, FOMC
- **Geopolítica**: sanctions, BRICS, G7, IMF, trade war, tariff

### Filtradas (ignoradas)
- meme coin, NFT drop, airdrop, price prediction, shitcoin

## Custos

| Serviço | Uso estimado | Limite grátis |
|---------|--------------|---------------|
| Supabase | ~60MB/mês | 500MB |
| GitHub Actions | ~3000 min/mês | Ilimitado (repo público) |

**Total: $0/mês**

## Processamento para Blog

O sistema pode reescrever notícias automaticamente para formato de blog:

```bash
# Inicializar tabelas de blog
python processor.py init

# Adicionar notícias de alta prioridade à fila
python processor.py queue --min-score 2.0 --limit 20

# Processar notícias (reescrever com IA)
python processor.py process --limit 10

# Ver estatísticas
python processor.py stats
```

### Estrutura do Blog Post

| Campo | Descrição |
|-------|-----------|
| `title_pt` / `title_en` | Título em PT-BR e EN |
| `content_pt` / `content_en` | Conteúdo reescrito |
| `summary_pt` / `summary_en` | Resumo para preview |
| `image_url` | Imagem de capa extraída |
| `source_url` | Link da fonte original |
| `source_name` | Nome da fonte |
| `tags` | Tags geradas pela IA |

### Secrets necessários

| Secret | Descrição |
|--------|-----------|
| `DATABASE_URL` | Connection string Supabase |
| `OPENAI_API_KEY` | API key OpenAI (para reescrita) |

## Próximos Passos

- [ ] API REST para servir ao blog
- [ ] Notificações Telegram para alta prioridade
- [ ] Dashboard de métricas
