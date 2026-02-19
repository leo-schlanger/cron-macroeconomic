# Macroeconomic News Aggregator (Cron Macroeconomic)

A powerful, automated macroeconomic and cryptocurrency news aggregator with intelligent keyword-based prioritization and AI-driven content processing.

## 🚀 Overview

This project is a high-efficiency news aggregator designed to monitor global economic shifts and crypto market trends. It collects data from over **60 RSS feeds**, prioritizes them based on strategic keywords, and can automatically rewrite selected high-impact news into professional blog posts using OpenAI or Anthropic AI.

### Key Features

*   **Intelligent Prioritization**: Uses customized keyword scores to highlight critical events (e.g., Fed decisions, SEC regulations, GDP shifts).
*   **Multi-Source Agnostic**: Monitors 61 sources across Macro Global, Crypto, Central Banks, and regional news (Europe, Asia, LATAM, etc.).
*   **Dual Storage Engine**: Supports local **SQLite** for development and **Supabase (PostgreSQL)** for production.
*   **Smart Deduplication**: Custom normalization and hashing algorithm to prevent duplicate stories without the cost of LLM tokens.
*   **AI Content Processor**: Automatically rewrites news into professional blog format in both **English** and **Portuguese (PT-BR)**, including automatic tag generation and lead image extraction.
*   **Zero-Cost Infrastructure**: Designed to run entirely on free tiers (GitHub Actions + Supabase).

---

## 🛠 Tech Stack

*   **Language**: Python 3.11+
*   **Database**: Supabase (PostgreSQL) / SQLite
*   **Automation**: GitHub Actions (Unlimited cron jobs for public repos)
*   **AI Engine**: OpenAI (GPT-4o-mini) or Anthropic (Claude 3 Haiku)
*   **Libraries**: `feedparser`, `requests`, `rich`, `psycopg2`, `schedule`, `python-dateutil`

---

## 📊 News Sources (61 Feeds)

| Category | High-Profile Sources |
| :--- | :--- |
| **Crypto** | CoinDesk, The Block, Cointelegraph, Decrypt, Blockworks |
| **Global Macro** | Bloomberg, Wall Street Journal, CNBC, The Economist |
| **Central Banks** | Fed, ECB, BoE, BoJ, BCB |
| **Geopolitics** | Al Jazeera, Nikkei, BBC, Guardian, SCMP |
| **Commodities** | OilPrice, Mining.com, Rigzone, Seeking Alpha |

---

## ⚙️ Quick Start

### 1. Database Setup (Supabase)

1.  Create a project at [supabase.com](https://supabase.com).
2.  Go to **Settings > Database > Connection string > URI** and copy your connection string.

### 2. GitHub Configuration

1.  Initialize your repository:
    ```bash
    git init
    git add .
    git commit -m "Initial commit"
    gh repo create cron-macroeconomic --public --source=. --push
    ```
2.  Add Secrets in **Settings > Secrets and variables > Actions**:
    *   `DATABASE_URL`: Your Supabase connection string.
    *   `OPENAI_API_KEY`: (Optional) For AI blog processing.

### 3. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Option A: Local SQLite setup
python main.py setup
python main.py fetch
python main.py stats

# Option B: Remote Supabase setup
export DATABASE_URL="postgresql://user:pass@host:5432/postgres"
python main_cloud.py setup
python main_cloud.py fetch
```

---

## 🤖 AI Blog Processing

The system includes a dedicated module (`processor.py`) to turn raw news into structured blog articles.

```bash
# Initialize blog tables
python processor.py init

# Queue high-priority news (score > 2.0)
python processor.py queue --min-score 2.0 --limit 20

# Process the queue (IA Rewriting)
python processor.py process --limit 10

# View statistics
python processor.py stats
```

---

## 📁 Project Structure

*   `.github/workflows/`: Automated Fetch/Process/Setup jobs.
*   `sources.json`: Master list of RSS feed configurations.
*   `fetcher_cloud.py`: Core RSS collection logic.
*   `processor.py`: AI rewriting and translation engine.
*   `deduplication.py`: Text-normalization based duplicate detection.
*   `database_supabase.py`: PostgreSQL driver for cloud deployment.
*   `main_cloud.py`: CLI entry point for automated environments.

---

## 📢 Priorities & Filters

Matches are weighted differently depending on where they appear:
*   **High Priority (+2.0)**: Keywords found in the title (Fed, SEC, ETF, Inflation, Recession).
*   **Standard Priority (+1.0)**: Keywords found in the description.
*   **Negative Filter**: Automatically skips meme coins, NFTs, and low-quality price predictions.

---

## ☕ Support the Project

If this tool helps you stay ahead of the markets, consider supporting the continued development!

[![Donate with PayPal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/donate/?hosted_button_id=UAB9LYC87EVBC)

---
*Created with ❤️ for the Macro & Crypto community.*
