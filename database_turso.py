"""
Database module com suporte a Turso (SQLite cloud).
Usa libsql-experimental para conectar ao Turso.
Fallback para SQLite local se variáveis de ambiente não estiverem configuradas.
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# Tenta importar libsql, fallback para sqlite3
try:
    import libsql_experimental as libsql
    USING_TURSO = True
except ImportError:
    import sqlite3 as libsql
    USING_TURSO = False

# Configuração
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
LOCAL_DB_PATH = Path(__file__).parent / "news.db"


def get_connection():
    """
    Retorna conexão com o banco de dados.
    Usa Turso se configurado, senão SQLite local.
    """
    if TURSO_URL and TURSO_TOKEN and USING_TURSO:
        conn = libsql.connect(
            database=TURSO_URL,
            auth_token=TURSO_TOKEN
        )
        print("[DB] Conectado ao Turso")
    else:
        conn = libsql.connect(str(LOCAL_DB_PATH))
        if not USING_TURSO:
            conn.row_factory = libsql.Row
        print(f"[DB] Usando SQLite local: {LOCAL_DB_PATH}")
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
            is_active INTEGER DEFAULT 1,
            last_fetch TEXT,
            fetch_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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

    # Tabela de keywords
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            is_negative INTEGER DEFAULT 0
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
    """)

    # Índices para performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_priority ON news(priority_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_processed ON news(is_processed)")

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
                cursor.execute("""
                    INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                    VALUES (?, ?, ?, ?)
                """, (term.lower(), category, 1.0, 0))
                if cursor.rowcount > 0:
                    count += 1
            except Exception as e:
                print(f"Erro ao inserir keyword {term}: {e}")

    # Keywords negativas
    filter_out = keywords_data.get("filter_out", {})
    for term in filter_out.get("terms", []):
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO keywords (keyword, category, weight, is_negative)
                VALUES (?, ?, ?, ?)
            """, (term.lower(), "filter", -1.0, 1))
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"Erro ao inserir keyword negativa {term}: {e}")

    conn.commit()
    conn.close()
    print(f"[DB] {count} keywords carregadas")


def get_active_sources() -> list:
    """Retorna todas as fontes ativas."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE is_active = 1")
    rows = cursor.fetchall()

    # Converter para dict (compatível com Turso e SQLite)
    if rows:
        columns = [desc[0] for desc in cursor.description]
        sources = [dict(zip(columns, row)) for row in rows]
    else:
        sources = []

    conn.close()
    return sources


def get_keywords() -> tuple:
    """Retorna keywords positivas e negativas."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT keyword FROM keywords WHERE is_negative = 0")
    positive = [row[0] for row in cursor.fetchall()]

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
        pub_str = published_at.isoformat() if published_at else None
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
            pub_str,
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

    rows = cursor.fetchall()
    if rows:
        columns = [desc[0] for desc in cursor.description]
        news = [dict(zip(columns, row)) for row in rows]
    else:
        news = []

    conn.close()
    return news


def get_news_stats() -> dict:
    """Retorna estatísticas do banco de dados."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) as total FROM sources")
    stats["total_sources"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total FROM sources WHERE is_active = 1")
    stats["active_sources"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total FROM news")
    stats["total_news"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total FROM news WHERE is_processed = 0")
    stats["unprocessed_news"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) as total FROM news WHERE is_published_blog = 1")
    stats["published_blog"] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM sources
        GROUP BY category
    """)
    stats["sources_by_category"] = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return stats


def cleanup_old_news(days: int = 30):
    """Remove notícias antigas para economizar espaço."""
    conn = get_connection()
    cursor = conn.cursor()

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
