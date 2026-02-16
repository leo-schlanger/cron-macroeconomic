"""
Fetcher de RSS - Versão Cloud com deduplicação.
"""
import feedparser
import requests
from datetime import datetime
from typing import Optional
import time
import re
from dateutil import parser as date_parser

from database_supabase import (
    get_active_sources, get_keywords, insert_news, update_source_fetch, get_connection
)
from deduplication import (
    generate_title_hash, get_recent_titles_for_dedup, is_duplicate
)

REQUEST_TIMEOUT = 15
USER_AGENT = "MacroNewsCron/1.0"

# Cache de títulos recentes para deduplicação
_recent_titles_cache = None
_cache_time = None


def get_recent_titles_cached():
    """Retorna títulos recentes com cache de 5 minutos."""
    global _recent_titles_cache, _cache_time

    now = datetime.now()

    # Atualizar cache se expirado ou não existe
    if _recent_titles_cache is None or _cache_time is None or \
       (now - _cache_time).seconds > 300:
        conn = get_connection()
        _recent_titles_cache = get_recent_titles_for_dedup(conn, hours=72)
        conn.close()
        _cache_time = now
        print(f"[Dedup] Cache atualizado: {len(_recent_titles_cache)} títulos")

    return _recent_titles_cache


def add_to_cache(news_id: int, title: str, description: str):
    """Adiciona notícia ao cache local."""
    global _recent_titles_cache
    if _recent_titles_cache is not None:
        _recent_titles_cache.append({
            'id': news_id,
            'title': title,
            'description': description
        })


def calculate_priority(title: str, description: str, positive_keywords: list,
                       negative_keywords: list) -> tuple:
    text = f"{title} {description}".lower()

    for kw in negative_keywords:
        if kw in text:
            return -1.0, []

    matched = []
    score = 0.0

    for kw in positive_keywords:
        if kw in text:
            matched.append(kw)
            score += 2.0 if kw in title.lower() else 1.0

    return score, matched


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return date_parser.parse(date_str)
    except:
        return None


def fetch_feed(url: str):
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return feed if feed.entries or not feed.bozo else None
    except Exception as e:
        raise Exception(str(e)[:100])


def clean_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', text)).strip()


def process_feed(source: dict, positive_kw: list, negative_kw: list) -> dict:
    start = time.time()
    stats = {
        "source_id": source["id"],
        "source_name": source["name"],
        "success": False,
        "news_count": 0,
        "new_count": 0,
        "skipped_count": 0,
        "duplicate_count": 0,
        "error": None
    }

    try:
        feed = fetch_feed(source["url"])
        if not feed:
            raise Exception("Feed vazio")

        stats["news_count"] = len(feed.entries)

        # Carregar títulos recentes para deduplicação
        recent_titles = get_recent_titles_cached()

        for entry in feed.entries:
            title = clean_html(entry.get("title", ""))
            link = entry.get("link", "")
            if not title or not link:
                continue

            description = clean_html(entry.get("summary", "") or entry.get("description", ""))
            content = ""
            if entry.get("content"):
                content = clean_html(entry["content"][0].get("value", ""))

            # Verificar duplicata por similaridade de título
            duplicate_id = is_duplicate(title, description, recent_titles, threshold=0.6)
            if duplicate_id:
                stats["duplicate_count"] += 1
                continue

            published = parse_date(
                entry.get("published") or entry.get("pubDate") or entry.get("updated")
            )

            score, matched = calculate_priority(title, description, positive_kw, negative_kw)

            if score < 0:
                stats["skipped_count"] += 1
                continue

            news_id = insert_news(
                source_id=source["id"],
                title=title,
                link=link,
                description=description,
                content=content,
                author=entry.get("author", ""),
                published_at=published,
                priority_score=score,
                matched_keywords=matched
            )

            if news_id:
                stats["new_count"] += 1
                # Adicionar ao cache para evitar duplicatas no mesmo batch
                add_to_cache(news_id, title, description)

        stats["success"] = True

    except Exception as e:
        stats["error"] = str(e)

    update_source_fetch(
        source_id=source["id"],
        success=stats["success"],
        news_count=stats["new_count"],
        error_message=stats["error"],
        duration_ms=int((time.time() - start) * 1000)
    )

    return stats


def fetch_all_sources(category: str = None) -> list:
    global _recent_titles_cache, _cache_time
    # Reset cache no início
    _recent_titles_cache = None
    _cache_time = None

    sources = get_active_sources()
    if category:
        sources = [s for s in sources if s["category"] == category]

    positive_kw, negative_kw = get_keywords()
    results = []

    total_duplicates = 0

    for i, source in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] {source['name']}...", end=" ")
        result = process_feed(source, positive_kw, negative_kw)

        status = "OK" if result["success"] else "ERRO"
        dup_info = f", {result['duplicate_count']} dup" if result['duplicate_count'] > 0 else ""
        print(f"{status} ({result['new_count']} novas{dup_info})")

        total_duplicates += result['duplicate_count']
        results.append(result)

    if total_duplicates > 0:
        print(f"\n[Dedup] Total de duplicatas ignoradas: {total_duplicates}")

    return results


def get_fetch_summary(results: list) -> dict:
    return {
        "total_sources": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "total_news": sum(r["news_count"] for r in results),
        "new_news": sum(r["new_count"] for r in results),
        "skipped": sum(r["skipped_count"] for r in results),
        "duplicates": sum(r.get("duplicate_count", 0) for r in results),
        "errors": [{"source": r["source_name"], "error": r["error"]} for r in results if r["error"]]
    }
