# Cron Macroeconômico

Agregador de notícias macroeconômicas e crypto com priorização inteligente por keywords.

## Stack

- **Python 3.11+**
- **Turso** (SQLite cloud) - 9GB grátis
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

### 1. Criar conta no Turso

```bash
# Instalar CLI
curl -sSfL https://get.tur.so/install.sh | bash

# Login
turso auth login

# Criar database
turso db create macro-news

# Pegar credenciais
turso db show macro-news --url
turso db tokens create macro-news
```

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
| `TURSO_DATABASE_URL` | `libsql://macro-news-seu-usuario.turso.io` |
| `TURSO_AUTH_TOKEN` | Token gerado pelo Turso |

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

# Com Turso
export TURSO_DATABASE_URL="libsql://..."
export TURSO_AUTH_TOKEN="..."
python main_turso.py setup
python main_turso.py fetch
```

## Estrutura

```
├── .github/workflows/
│   ├── fetch_news.yml      # Cron horário
│   └── setup_db.yml        # Setup inicial
├── sources.json            # Fontes RSS
├── database_turso.py       # DB com suporte Turso
├── fetcher_turso.py        # Coletor RSS
├── main_turso.py           # CLI principal
└── test_feeds_turso.py     # Testa feeds
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
| Turso | ~60MB/mês | 9GB |
| GitHub Actions | ~3000 min/mês | Ilimitado (repo público) |

**Total: $0/mês**

## Próximos Passos

- [ ] API REST para servir ao blog
- [ ] Notificações Telegram para alta prioridade
- [ ] Tradução automática
- [ ] Dashboard de métricas
