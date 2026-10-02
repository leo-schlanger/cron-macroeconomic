"""Blog hygiene: take broken or stale posts off the blog without deleting them.

Two rules, run weekly (and on demand):

1. Language defects: posts whose Portuguese text is not Portuguese, mixes
   other languages, or kept an English title (the curator's quality gate,
   language checks only). Mostly from the Ollama era (Jul-Oct/2026).
2. Archive: legacy short posts (no "## " sections, i.e. written before the
   curator) older than ARCHIVE_MONTHS. Curator articles are kept forever.

"Unpublish" = status 'draft' + ``unpublished_reason``; the blog only shows
status 'published', and nothing is deleted. To restore a post:
    UPDATE blog_posts SET status='published', unpublished_reason=NULL WHERE id=...
"""

import argparse
import os

from utils import logger

ARCHIVE_MONTHS = int(os.getenv("BLOG_ARCHIVE_MONTHS", "6"))

LANGUAGE_REASONS = ("não parece português", "palavras em outro idioma", "título PT com palavra",
                    "título PT igual ao título EN")


def language_problems(post: dict) -> list[str]:
    """Only the language checks of the curator gate (old posts are short by design)."""
    from curator import quality_problems
    probs = quality_problems({**post, "tags": post.get("tags") or ["x"]})
    return [p for p in probs if any(r in p for r in LANGUAGE_REASONS)]


def _conn():
    from database_supabase import get_connection
    return get_connection()


def ensure_column(conn) -> None:
    cur = conn.cursor()
    cur.execute("ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS unpublished_reason TEXT")
    conn.commit()


def find_language_defects(conn) -> list[tuple[int, str]]:
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""SELECT id, title_pt, summary_pt, content_pt, title_en, summary_en, content_en
                   FROM blog_posts WHERE status = 'published'""")
    out = []
    for row in cur.fetchall():
        probs = language_problems(dict(row))
        if probs:
            out.append((row["id"], "idioma: " + "; ".join(probs)))
    return out


def find_archivable(conn, months: int = ARCHIVE_MONTHS) -> list[tuple[int, str]]:
    cur = conn.cursor()
    cur.execute("""SELECT id FROM blog_posts
                   WHERE status = 'published'
                     AND created_at < NOW() - make_interval(months => %s)
                     AND content_pt NOT LIKE %s""", (months, "%## %"))
    return [(r[0], f"arquivo: post legado com mais de {months} meses") for r in cur.fetchall()]


def unpublish(conn, items: list[tuple[int, str]]) -> int:
    cur = conn.cursor()
    for pid, reason in items:
        cur.execute("""UPDATE blog_posts SET status = 'draft', unpublished_reason = %s
                       WHERE id = %s AND status = 'published'""", (reason[:500], pid))
    conn.commit()
    return len(items)


def run(dry_run: bool = False, months: int = ARCHIVE_MONTHS) -> dict:
    conn = _conn()
    try:
        if not dry_run:
            ensure_column(conn)
        lang = find_language_defects(conn)
        lang_ids = {i for i, _ in lang}
        old = [(i, r) for i, r in find_archivable(conn, months) if i not in lang_ids]
        stats = {"language_defects": len(lang), "archived": len(old), "dry_run": dry_run}
        logger.info(f"[blog] defeitos de idioma: {len(lang)} | legados > {months} meses: {len(old)}"
                    + (" (simulação, nada alterado)" if dry_run else ""))
        if not dry_run:
            unpublish(conn, lang + old)
        return stats
    finally:
        conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Higiene do blog: despublica posts com defeito ou antigos")
    p.add_argument("command", choices=["run", "dry-run"])
    p.add_argument("--months", type=int, default=ARCHIVE_MONTHS)
    a = p.parse_args()
    print(run(dry_run=a.command == "dry-run", months=a.months))
