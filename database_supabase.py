"""
Database module para Supabase (PostgreSQL).
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Tenta importar psycopg2, fallback para sqlite3
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    import sqlite3

# Configuração
DATABASE_URL = os.getenv("DATABASE_URL")
LOCAL_DB_PATH = Path(__file__).parent / "news.db"


def get_connection():
    """Retorna conexão com o banco de dados."""
    if DATABASE_URL and HAS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        print("[DB] Conectado ao Supabase")
        return conn
    else:
        conn = sqlite3.connect(str(LOCAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        print(f"[DB] Usando SQLite local: {LOCAL_DB_PATH}")
        return conn


def is_postgres():
    """Verifica se está usando PostgreSQL."""
    return DATABASE_URL and HAS_POSTGRES


def init_db():
    """Inicializa o banco de dados com as tabelas necessárias."""
    conn = get_connection()
    cursor = conn.cursor()

    # Sintaxe compatível com PostgreSQL e SQLite
    if is_postgres():
        # PostgreSQL
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                country TEXT,
                region TEXT,
                focus TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                last_fetch TIMESTAMP,
                fetch_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES sources(id),
                title TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL,
                description TEXT,
                content TEXT,
                author TEXT,
                published_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                priority_score REAL DEFAULT 0,
                matched_keywords TEXT,
                is_processed BOOLEAN DEFAULT FALSE,
                is_published_blog BOOLEAN DEFAULT FALSE,
                blog_post_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id SERIAL PRIMARY KEY,
                keyword TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                is_negative BOOLEAN DEFAULT FALSE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fetch_logs (
                id SERIAL PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES sources(id),
                status TEXT NOT NULL,
                news_count INTEGER DEFAULT 0,
                error_message TEXT,
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_priority ON news(priority_score DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_processed ON news(is_processed)")

    else:
        # SQLite
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                country TEXT,
                region TEXT,
                focus TEXT,
                is_active INTEGER DEFAULT 1,
                last_fetch TEXT,
                fetch_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                link TEXT UNIQUE NOT NULL,
                description TEXT,
                content TEXT,
                author TEXT,
                published_at TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                priority_score REAL DEFAULT 0,
                matched_keywords TEXT,
                is_processed INTEGER DEFAULT 0,
                is_published_blog INTEGER DEFAULT 0,
                blog_post_id TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                is_negative INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fetch_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                news_count INTEGER DEFAULT 0,
                error_message TEXT,
                duration_ms INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_priority ON news(priority_score)")

    conn.commit()
    conn.close()
    print("[DB] Tabelas inicializadas")


def load_sources_from_json():
    """Carrega as fontes do arquivo JSON para o banco de dados."""
    sources_path = Path(__file__).parent / "sources.json"

    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    count = 0
    for category, cat_data in data.items():
        if category == "keywords" or "feeds" not in cat_data:
            continue

        for feed in cat_data["feeds"]:
            try:
                if is_postgres():
                    cursor.execute("""
                        INSERT INTO sources (name, url, category, country, region, focus)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO NOTHING
                    """, (
                        feed["name"],
                        feed["url"],
                        category,
                        feed.get("country"),
                        feed.get("region"),
                        json.dumps(feed.get("focus", []))
                    ))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO sources (name, url, category, country, region, focus)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        feed["name"],
                        feed["url"],
                        category,
                        feed.get("country"),
                        feed.get("region"),
                        json.dumps(feed.get("focus", []))
                    ))
                if cursor.rowcount > 0:
                    count += 1
            except Exception as e:
                print(f"Erro ao inserir {feed['name']}: {e}")

    conn.commit()
    conn.close()
    print(f"[DB] {count} fontes carregadas")


def load_keywords_from_json():
    """Carrega as keywords do arquivo JSON para o banco de dados."""
    sources_path = Path(__file__).parent / "sources.json"

    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    keywords_data = data.get("keywords", {})
    conn = get_connection()
    cursor = conn.cursor()

    count = 0

    # Keywords de alta prioridade
    high_priority = keywords_data.get("high_priority", {})
    for category, terms in high_priority.items():
        if category == "description":
            continue
        for term in terms:
            try:
                if is_postgres():
                    cursor.execute("""
                        INSERT INTO keywords (keyword, category, weight, is_negative)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (keyword) DO NOTHING
                    """, (term.lower(), category, 1.0, False))
                else:
                    cursor.execute("""
                        INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                        VALUES (?, ?, ?, ?)
                    """, (term.lower(), category, 1.0, 0))
                if cursor.rowcount > 0:
                    count += 1
            except Exception as e:
                print(f"Erro keyword {term}: {e}")

    # Keywords negativas
    filter_out = keywords_data.get("filter_out", {})
    for term in filter_out.get("terms", []):
        try:
            if is_postgres():
                cursor.execute("""
                    INSERT INTO keywords (keyword, category, weight, is_negative)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (keyword) DO NOTHING
                """, (term.lower(), "filter", -1.0, True))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                    VALUES (?, ?, ?, ?)
                """, (term.lower(), "filter", -1.0, 1))
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"Erro keyword negativa {term}: {e}")

    conn.commit()
    conn.close()
    print(f"[DB] {count} keywords carregadas")


def get_active_sources() -> list:
    """Retorna todas as fontes ativas."""
    conn = get_connection()

    if is_postgres():
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM sources WHERE is_active = TRUE")
        sources = cursor.fetchall()
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sources WHERE is_active = 1")
        sources = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return sources


def get_keywords() -> tuple:
    """Retorna keywords positivas e negativas."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("SELECT keyword FROM keywords WHERE is_negative = FALSE")
    else:
        cursor.execute("SELECT keyword FROM keywords WHERE is_negative = 0")
    positive = [row[0] for row in cursor.fetchall()]

    if is_postgres():
        cursor.execute("SELECT keyword FROM keywords WHERE is_negative = TRUE")
    else:
        cursor.execute("SELECT keyword FROM keywords WHERE is_negative = 1")
    negative = [row[0] for row in cursor.fetchall()]

    conn.close()
    return positive, negative


def insert_news(source_id: int, title: str, link: str, description: str = None,
                content: str = None, author: str = None, published_at: datetime = None,
                priority_score: float = 0, matched_keywords: list = None) -> Optional[int]:
    """Insere uma notícia no banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        kw_json = json.dumps(matched_keywords) if matched_keywords else None

        if is_postgres():
            cursor.execute("""
                INSERT INTO news
                (source_id, title, link, description, content, author, published_at, priority_score, matched_keywords)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (link) DO NOTHING
                RETURNING id
            """, (source_id, title, link, description, content, author, published_at, priority_score, kw_json))
            result = cursor.fetchone()
            news_id = result[0] if result else None
        else:
            pub_str = published_at.isoformat() if published_at else None
            cursor.execute("""
                INSERT OR IGNORE INTO news
                (source_id, title, link, description, content, author, published_at, priority_score, matched_keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_id, title, link, description, content, author, pub_str, priority_score, kw_json))
            news_id = cursor.lastrowid if cursor.rowcount > 0 else None

        conn.commit()
        conn.close()
        return news_id
    except Exception as e:
        print(f"Erro ao inserir notícia: {e}")
        conn.close()
        return None


def update_source_fetch(source_id: int, success: bool, news_count: int = 0,
                        error_message: str = None, duration_ms: int = 0):
    """Atualiza estatísticas de fetch de uma fonte."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        if success:
            cursor.execute("""
                UPDATE sources
                SET last_fetch = CURRENT_TIMESTAMP, fetch_count = fetch_count + 1
                WHERE id = %s
            """, (source_id,))
        else:
            cursor.execute("""
                UPDATE sources SET error_count = error_count + 1 WHERE id = %s
            """, (source_id,))

        cursor.execute("""
            INSERT INTO fetch_logs (source_id, status, news_count, error_message, duration_ms)
            VALUES (%s, %s, %s, %s, %s)
        """, (source_id, "success" if success else "error", news_count, error_message, duration_ms))
    else:
        if success:
            cursor.execute("""
                UPDATE sources
                SET last_fetch = CURRENT_TIMESTAMP, fetch_count = fetch_count + 1
                WHERE id = ?
            """, (source_id,))
        else:
            cursor.execute("""
                UPDATE sources SET error_count = error_count + 1 WHERE id = ?
            """, (source_id,))

        cursor.execute("""
            INSERT INTO fetch_logs (source_id, status, news_count, error_message, duration_ms)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, "success" if success else "error", news_count, error_message, duration_ms))

    conn.commit()
    conn.close()


def get_news_stats() -> dict:
    """Retorna estatísticas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) FROM sources")
    stats["total_sources"] = cursor.fetchone()[0]

    if is_postgres():
        cursor.execute("SELECT COUNT(*) FROM sources WHERE is_active = TRUE")
    else:
        cursor.execute("SELECT COUNT(*) FROM sources WHERE is_active = 1")
    stats["active_sources"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM news")
    stats["total_news"] = cursor.fetchone()[0]

    if is_postgres():
        cursor.execute("SELECT COUNT(*) FROM news WHERE is_processed = FALSE")
    else:
        cursor.execute("SELECT COUNT(*) FROM news WHERE is_processed = 0")
    stats["unprocessed_news"] = cursor.fetchone()[0]

    if is_postgres():
        cursor.execute("SELECT COUNT(*) FROM news WHERE is_published_blog = TRUE")
    else:
        cursor.execute("SELECT COUNT(*) FROM news WHERE is_published_blog = 1")
    stats["published_blog"] = cursor.fetchone()[0]

    cursor.execute("SELECT category, COUNT(*) FROM sources GROUP BY category")
    stats["sources_by_category"] = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return stats


def cleanup_old_news(days: int = 30):
    """Remove notícias antigas."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            DELETE FROM news
            WHERE fetched_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
            AND is_published_blog = FALSE
        """, (days,))
    else:
        cursor.execute("""
            DELETE FROM news
            WHERE fetched_at < datetime('now', ?)
            AND is_published_blog = 0
        """, (f"-{days} days",))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"[DB] {deleted} notícias antigas removidas")
    return deleted


if __name__ == "__main__":
    print("=== Inicializando banco de dados ===")
    init_db()
    load_sources_from_json()
    load_keywords_from_json()

    stats = get_news_stats()
    print(f"\nEstatísticas:")
    print(f"  Fontes: {stats['total_sources']} (ativas: {stats['active_sources']})")
    print(f"  Notícias: {stats['total_news']}")
