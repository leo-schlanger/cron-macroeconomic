import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


DB_PATH = Path(__file__).parent / "news.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa o banco de dados com as tabelas necessárias."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabela de fontes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            country TEXT,
            region TEXT,
            focus TEXT,
            is_active BOOLEAN DEFAULT 1,
            last_fetch TIMESTAMP,
            fetch_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela de notícias
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            description TEXT,
            content TEXT,
            author TEXT,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            priority_score REAL DEFAULT 0,
            matched_keywords TEXT,
            is_processed BOOLEAN DEFAULT 0,
            is_published_blog BOOLEAN DEFAULT 0,
            blog_post_id TEXT,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
    """)

    # Tabela de keywords
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            is_negative BOOLEAN DEFAULT 0
        )
    """)

    # Tabela de logs de fetch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            news_count INTEGER DEFAULT 0,
            error_message TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
    """)

    # Índices para performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_priority ON news(priority_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_processed ON news(is_processed)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_blog ON news(is_published_blog)")

    conn.commit()
    conn.close()
    print(f"Banco de dados inicializado em: {DB_PATH}")


def load_sources_from_json():
    """Carrega as fontes do arquivo JSON para o banco de dados."""
    sources_path = Path(__file__).parent / "sources.json"

    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    conn = get_connection()
    cursor = conn.cursor()

    count = 0
    for category, cat_data in data.items():
        if category == "keywords":
            continue

        if "feeds" not in cat_data:
            continue

        for feed in cat_data["feeds"]:
            try:
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
    print(f"{count} fontes carregadas no banco de dados.")


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
                cursor.execute("""
                    INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                    VALUES (?, ?, ?, ?)
                """, (term.lower(), category, 1.0, False))
                if cursor.rowcount > 0:
                    count += 1
            except Exception as e:
                print(f"Erro ao inserir keyword {term}: {e}")

    # Keywords negativas (para filtrar)
    filter_out = keywords_data.get("filter_out", {})
    for term in filter_out.get("terms", []):
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                VALUES (?, ?, ?, ?)
            """, (term.lower(), "filter", -1.0, True))
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"Erro ao inserir keyword negativa {term}: {e}")

    conn.commit()
    conn.close()
    print(f"{count} keywords carregadas no banco de dados.")


def get_active_sources() -> list:
    """Retorna todas as fontes ativas."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE is_active = 1")
    sources = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sources


def get_keywords() -> tuple[list, list]:
    """Retorna keywords positivas e negativas."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT keyword FROM keywords WHERE is_negative = 0")
    positive = [row["keyword"] for row in cursor.fetchall()]

    cursor.execute("SELECT keyword FROM keywords WHERE is_negative = 1")
    negative = [row["keyword"] for row in cursor.fetchall()]

    conn.close()
    return positive, negative


def insert_news(source_id: int, title: str, link: str, description: str = None,
                content: str = None, author: str = None, published_at: datetime = None,
                priority_score: float = 0, matched_keywords: list = None) -> Optional[int]:
    """Insere uma notícia no banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO news
            (source_id, title, link, description, content, author, published_at, priority_score, matched_keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_id,
            title,
            link,
            description,
            content,
            author,
            published_at,
            priority_score,
            json.dumps(matched_keywords) if matched_keywords else None
        ))
        conn.commit()
        news_id = cursor.lastrowid if cursor.rowcount > 0 else None
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

    if success:
        cursor.execute("""
            UPDATE sources
            SET last_fetch = CURRENT_TIMESTAMP, fetch_count = fetch_count + 1
            WHERE id = ?
        """, (source_id,))
    else:
        cursor.execute("""
            UPDATE sources
            SET error_count = error_count + 1
            WHERE id = ?
        """, (source_id,))

    cursor.execute("""
        INSERT INTO fetch_logs (source_id, status, news_count, error_message, duration_ms)
        VALUES (?, ?, ?, ?, ?)
    """, (source_id, "success" if success else "error", news_count, error_message, duration_ms))

    conn.commit()
    conn.close()


def get_unprocessed_news(limit: int = 100) -> list:
    """Retorna notícias não processadas ordenadas por prioridade."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, s.name as source_name, s.category
        FROM news n
        JOIN sources s ON n.source_id = s.id
        WHERE n.is_processed = 0
        ORDER BY n.priority_score DESC, n.published_at DESC
        LIMIT ?
    """, (limit,))
    news = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return news


def get_news_stats() -> dict:
    """Retorna estatísticas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) as total FROM sources")
    stats["total_sources"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM sources WHERE is_active = 1")
    stats["active_sources"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM news")
    stats["total_news"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM news WHERE is_processed = 0")
    stats["unprocessed_news"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM news WHERE is_published_blog = 1")
    stats["published_blog"] = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM sources
        GROUP BY category
    """)
    stats["sources_by_category"] = {row["category"]: row["count"] for row in cursor.fetchall()}

    conn.close()
    return stats


if __name__ == "__main__":
    init_db()
    load_sources_from_json()
    load_keywords_from_json()

    stats = get_news_stats()
    print("\nEstatísticas:")
    print(f"  Fontes totais: {stats['total_sources']}")
    print(f"  Fontes ativas: {stats['active_sources']}")
    print(f"  Notícias: {stats['total_news']}")
    print("\n  Por categoria:")
    for cat, count in stats['sources_by_category'].items():
        print(f"    {cat}: {count}")
