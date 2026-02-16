"""
Schema de banco de dados para blog com suporte a tradução.
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL")
LOCAL_DB_PATH = Path(__file__).parent / "news.db"


def get_connection():
    if DATABASE_URL and HAS_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(str(LOCAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


def is_postgres():
    return DATABASE_URL and HAS_POSTGRES


def init_blog_tables():
    """Cria tabelas para o blog."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        # Tabela de posts do blog (notícias processadas)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id SERIAL PRIMARY KEY,
                news_id INTEGER REFERENCES news(id),

                -- Conteúdo em Português
                title_pt TEXT NOT NULL,
                slug_pt TEXT UNIQUE,
                content_pt TEXT NOT NULL,
                summary_pt TEXT,

                -- Conteúdo em Inglês
                title_en TEXT NOT NULL,
                slug_en TEXT UNIQUE,
                content_en TEXT NOT NULL,
                summary_en TEXT,

                -- Metadata
                image_url TEXT,
                image_local_path TEXT,
                source_url TEXT NOT NULL,
                source_name TEXT NOT NULL,

                -- Categorização
                category TEXT,
                tags TEXT,
                priority_score REAL DEFAULT 0,

                -- Status
                status TEXT DEFAULT 'draft',
                is_published BOOLEAN DEFAULT FALSE,
                published_at TIMESTAMP,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- SEO
                meta_description_pt TEXT,
                meta_description_en TEXT,
                meta_keywords TEXT
            )
        """)

        # Tabela de imagens
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_images (
                id SERIAL PRIMARY KEY,
                post_id INTEGER REFERENCES blog_posts(id),
                original_url TEXT NOT NULL,
                local_path TEXT,
                cdn_url TEXT,
                alt_text_pt TEXT,
                alt_text_en TEXT,
                is_cover BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de processamento (fila)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_queue (
                id SERIAL PRIMARY KEY,
                news_id INTEGER REFERENCES news(id),
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """)

        # Índices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(is_published)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blog_posts_category ON blog_posts(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_queue_status ON processing_queue(status)")

    else:
        # SQLite version
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,

                title_pt TEXT NOT NULL,
                slug_pt TEXT UNIQUE,
                content_pt TEXT NOT NULL,
                summary_pt TEXT,

                title_en TEXT NOT NULL,
                slug_en TEXT UNIQUE,
                content_en TEXT NOT NULL,
                summary_en TEXT,

                image_url TEXT,
                image_local_path TEXT,
                source_url TEXT NOT NULL,
                source_name TEXT NOT NULL,

                category TEXT,
                tags TEXT,
                priority_score REAL DEFAULT 0,

                status TEXT DEFAULT 'draft',
                is_published INTEGER DEFAULT 0,
                published_at TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                meta_description_pt TEXT,
                meta_description_en TEXT,
                meta_keywords TEXT,

                FOREIGN KEY (news_id) REFERENCES news(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blog_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                original_url TEXT NOT NULL,
                local_path TEXT,
                cdn_url TEXT,
                alt_text_pt TEXT,
                alt_text_en TEXT,
                is_cover INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES blog_posts(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT,
                FOREIGN KEY (news_id) REFERENCES news(id)
            )
        """)

    conn.commit()
    conn.close()
    print("[DB] Tabelas de blog criadas")


def add_to_processing_queue(news_id: int) -> int:
    """Adiciona notícia à fila de processamento."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            INSERT INTO processing_queue (news_id, status)
            VALUES (%s, 'pending')
            ON CONFLICT DO NOTHING
            RETURNING id
        """, (news_id,))
        result = cursor.fetchone()
        queue_id = result[0] if result else None
    else:
        cursor.execute("""
            INSERT OR IGNORE INTO processing_queue (news_id, status)
            VALUES (?, 'pending')
        """, (news_id,))
        queue_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return queue_id


def get_pending_news(limit: int = 10) -> list:
    """Retorna notícias pendentes para processamento."""
    conn = get_connection()

    if is_postgres():
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT n.*, s.name as source_name, s.category, pq.id as queue_id
            FROM processing_queue pq
            JOIN news n ON pq.news_id = n.id
            JOIN sources s ON n.source_id = s.id
            WHERE pq.status = 'pending'
            ORDER BY n.priority_score DESC
            LIMIT %s
        """, (limit,))
    else:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.*, s.name as source_name, s.category, pq.id as queue_id
            FROM processing_queue pq
            JOIN news n ON pq.news_id = n.id
            JOIN sources s ON n.source_id = s.id
            WHERE pq.status = 'pending'
            ORDER BY n.priority_score DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    news = [dict(row) for row in rows] if rows else []
    conn.close()
    return news


def save_blog_post(
    news_id: int,
    title_pt: str,
    content_pt: str,
    title_en: str,
    content_en: str,
    summary_pt: str,
    summary_en: str,
    image_url: str,
    source_url: str,
    source_name: str,
    category: str,
    tags: list,
    priority_score: float
) -> int:
    """Salva post do blog processado."""
    conn = get_connection()
    cursor = conn.cursor()

    # Gerar slugs
    slug_pt = generate_slug(title_pt)
    slug_en = generate_slug(title_en)

    tags_str = json.dumps(tags) if tags else None

    if is_postgres():
        cursor.execute("""
            INSERT INTO blog_posts (
                news_id, title_pt, slug_pt, content_pt, summary_pt,
                title_en, slug_en, content_en, summary_en,
                image_url, source_url, source_name, category, tags, priority_score,
                meta_description_pt, meta_description_en,
                status, published_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'published', NOW()
            ) RETURNING id
        """, (
            news_id, title_pt, slug_pt, content_pt, summary_pt,
            title_en, slug_en, content_en, summary_en,
            image_url, source_url, source_name, category, tags_str, priority_score,
            summary_pt[:160] if summary_pt else None,
            summary_en[:160] if summary_en else None
        ))
        post_id = cursor.fetchone()[0]
    else:
        cursor.execute("""
            INSERT INTO blog_posts (
                news_id, title_pt, slug_pt, content_pt, summary_pt,
                title_en, slug_en, content_en, summary_en,
                image_url, source_url, source_name, category, tags, priority_score,
                meta_description_pt, meta_description_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            news_id, title_pt, slug_pt, content_pt, summary_pt,
            title_en, slug_en, content_en, summary_en,
            image_url, source_url, source_name, category, tags_str, priority_score,
            summary_pt[:160] if summary_pt else None,
            summary_en[:160] if summary_en else None
        ))
        post_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return post_id


def update_queue_status(queue_id: int, status: str, error_message: str = None):
    """Atualiza status na fila de processamento."""
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            UPDATE processing_queue
            SET status = %s, error_message = %s, processed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (status, error_message, queue_id))
    else:
        cursor.execute("""
            UPDATE processing_queue
            SET status = ?, error_message = ?, processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, error_message, queue_id))

    conn.commit()
    conn.close()


def get_blog_posts(status: str = None, limit: int = 50) -> list:
    """Retorna posts do blog."""
    conn = get_connection()

    if is_postgres():
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if status:
            cursor.execute("""
                SELECT * FROM blog_posts WHERE status = %s
                ORDER BY created_at DESC LIMIT %s
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT * FROM blog_posts ORDER BY created_at DESC LIMIT %s
            """, (limit,))
    else:
        cursor = conn.cursor()
        if status:
            cursor.execute("""
                SELECT * FROM blog_posts WHERE status = ?
                ORDER BY created_at DESC LIMIT ?
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT * FROM blog_posts ORDER BY created_at DESC LIMIT ?
            """, (limit,))

    rows = cursor.fetchall()
    posts = [dict(row) for row in rows] if rows else []
    conn.close()
    return posts


def generate_slug(title: str) -> str:
    """Gera slug a partir do título."""
    import re
    import unicodedata

    # Normalizar e remover acentos
    slug = unicodedata.normalize('NFKD', title)
    slug = slug.encode('ascii', 'ignore').decode('ascii')

    # Converter para minúsculas e substituir espaços
    slug = slug.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')

    return slug[:100]  # Limitar tamanho


def get_blog_stats() -> dict:
    """Retorna estatísticas do blog."""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) FROM blog_posts")
    stats["total_posts"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM blog_posts WHERE status = 'draft'")
    stats["drafts"] = cursor.fetchone()[0]

    if is_postgres():
        cursor.execute("SELECT COUNT(*) FROM blog_posts WHERE is_published = TRUE")
    else:
        cursor.execute("SELECT COUNT(*) FROM blog_posts WHERE is_published = 1")
    stats["published"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM processing_queue WHERE status = 'pending'")
    stats["pending_processing"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM processing_queue WHERE status = 'completed'")
    stats["processed"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM processing_queue WHERE status = 'error'")
    stats["errors"] = cursor.fetchone()[0]

    conn.close()
    return stats


if __name__ == "__main__":
    print("Inicializando tabelas de blog...")
    init_blog_tables()

    stats = get_blog_stats()
    print(f"\nEstatísticas:")
    print(f"  Posts: {stats['total_posts']}")
    print(f"  Rascunhos: {stats['drafts']}")
    print(f"  Publicados: {stats['published']}")
    print(f"  Pendentes: {stats['pending_processing']}")
