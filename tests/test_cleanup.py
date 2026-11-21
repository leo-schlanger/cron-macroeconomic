"""cleanup_old_news with foreign keys enforced (SQLite branch)."""

import sqlite3

import pytest

import database_supabase as dbs

# (id, age_days, is_published_blog, priority_score, has_queue_row, has_blog_post, survives)
CASES = [
    (1, 40, 0, 1.0, True, False, False),    # old normal with curator row: removed with its queue row
    (2, 40, 0, 1.0, True, True, True),      # old normal with blog post: kept (blog_posts FK)
    (3, 5, 0, 1.0, True, False, True),      # recent: kept
    (4, 60, 0, 5.0, True, False, True),     # high priority within 90 days: kept
    (5, 100, 0, 5.0, True, False, False),   # high priority past 90 days: removed
    (6, 100, 0, 5.0, False, True, True),    # high priority past 90 days with post: kept
    (7, 40, 1, 1.0, True, False, True),     # flagged as published: kept
    (8, 40, 0, 1.0, False, False, False),   # old normal without children: removed
]


def _schema(con, with_posts=True):
    con.executescript("""
        CREATE TABLE news (id INTEGER PRIMARY KEY, fetched_at TEXT,
                           is_published_blog INTEGER DEFAULT 0, priority_score REAL DEFAULT 0);
        CREATE TABLE processing_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, news_id INTEGER,
                                       status TEXT, FOREIGN KEY (news_id) REFERENCES news(id));
        CREATE TABLE fetch_logs (id INTEGER PRIMARY KEY, created_at TEXT);
    """)
    if with_posts:
        con.execute("CREATE TABLE blog_posts (id INTEGER PRIMARY KEY, news_id INTEGER, "
                    "FOREIGN KEY (news_id) REFERENCES news(id))")
    for nid, age, pub, prio, queue, post, _ in CASES:
        con.execute("INSERT INTO news VALUES (?, datetime('now', ?), ?, ?)", (nid, f"-{age} days", pub, prio))
        if queue:
            con.execute("INSERT INTO processing_queue (news_id, status) VALUES (?, 'skipped')", (nid,))
        if post and with_posts:
            con.execute("INSERT INTO blog_posts (news_id) VALUES (?)", (nid,))
    con.execute("INSERT INTO fetch_logs VALUES (1, datetime('now', '-40 days'))")
    con.commit()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "news.db"

    def connect():
        con = sqlite3.connect(path)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    monkeypatch.setattr(dbs, "DATABASE_URL", None)
    monkeypatch.setattr(dbs, "get_connection", connect)
    return connect


def _ids(con, table, col="id"):
    return {r[0] for r in con.execute(f"SELECT {col} FROM {table}")}


def test_old_implementation_order_violates_fk(db):
    # The failure seen in prod on 2026-11-15: parent deleted before its queue rows
    con = db()
    _schema(con)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        con.execute("DELETE FROM news WHERE id = 1")


def test_cleanup_removes_children_first_and_keeps_posts(db):
    con = db()
    _schema(con)
    con.close()
    deleted = dbs.cleanup_old_news(30, preserve_high_priority=True, high_priority_days=90)
    con = db()
    expected = {c[0] for c in CASES if c[6]}
    assert _ids(con, "news") == expected
    assert deleted == len(CASES) - len(expected)
    assert _ids(con, "processing_queue", "news_id") <= expected
    assert _ids(con, "blog_posts", "news_id") == {2, 6}
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert _ids(con, "fetch_logs") == set()


def test_cleanup_without_priority_split(db):
    con = db()
    _schema(con)
    con.close()
    dbs.cleanup_old_news(30, preserve_high_priority=False)
    con = db()
    # Everything old and unpublished goes, unless it has a blog post
    assert _ids(con, "news") == {2, 3, 6, 7}
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cleanup_without_blog_posts_table(db):
    con = db()
    _schema(con, with_posts=False)
    con.close()
    dbs.cleanup_old_news(30)
    con = db()
    assert _ids(con, "news") == {3, 4, 7}


def test_dry_run_rolls_back(db):
    con = db()
    _schema(con)
    before = {t: _ids(con, t) for t in ("news", "processing_queue", "blog_posts", "fetch_logs")}
    con.close()
    deleted = dbs.cleanup_old_news(30, dry_run=True)
    con = db()
    assert deleted == 3
    assert {t: _ids(con, t) for t in before} == before
