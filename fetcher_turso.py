"""
Fetcher de RSS - Versão compatível com Turso.
"""
import feedparser
import requests
from datetime import datetime
from typing import Optional
import time
import re
from dateutil import parser as date_parser

from database_turso import (
    get_active_sources, get_keywords, insert_news, update_source_fetch
)


# Configurações
REQUEST_TIMEOUT = 30
USER_AGENT = "MacroNewsCron/1.0 (News Aggregator)"


def calculate_priority(title: str, description: str, positive_keywords: list,
                       negative_keywords: list) -> tuple:
    """Calcula a prioridade de uma notícia baseado nas keywords."""
    text = f"{title} {description}".lower()

    # Verificar keywords negativas primeiro
    for kw in negative_keywords:
        if kw in text:
            return -1.0, []

    # Calcular score baseado em keywords positivas
    matched = []
    score = 0.0

    for kw in positive_keywords:
        if kw in text:
            matched.append(kw)
            if kw in title.lower():
                score += 2.0
            else:
                score += 1.0

    return score, matched


def parse_date(date_str: str) -> Optional[datetime]:
    """Tenta parsear uma data de várias formas."""
    if not date_str:
        return None
    try:
        return date_parser.parse(date_str)
    except:
        return None


def fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    """Faz o fetch de um feed RSS."""
    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            return None
        return feed
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request error: {str(e)}")
    except Exception as e:
        raise Exception(f"Parse error: {str(e)}")


def clean_html(text: str) -> str:
    """Remove tags HTML de um texto."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def process_feed(source: dict, positive_keywords: list, negative_keywords: list) -> dict:
    """Processa um feed RSS e salva as notícias no banco."""
    start_time = time.time()
    stats = {
        "source_id": source["id"],
        "source_name": source["name"],
        "success": False,
        "news_count": 0,
        "new_count": 0,
        "skipped_count": 0,
        "error": None
    }

    try:
        feed = fetch_feed(source["url"])
        if not feed:
            raise Exception("Feed vazio ou inválido")

        stats["news_count"] = len(feed.entries)

        for entry in feed.entries:
            title = clean_html(entry.get("title", ""))
            link = entry.get("link", "")

            if not title or not link:
                continue

            description = clean_html(
                entry.get("summary", "") or entry.get("description", "")
            )

            content = clean_html(
                entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
            )

            author = entry.get("author", "")

            published = parse_date(
                entry.get("published", "") or
                entry.get("pubDate", "") or
                entry.get("updated", "")
            )

            score, matched = calculate_priority(
                title, description, positive_keywords, negative_keywords
            )

            if score < 0:
                stats["skipped_count"] += 1
                continue

            news_id = insert_news(
                source_id=source["id"],
                title=title,
                link=link,
                description=description,
                content=content,
                author=author,
                published_at=published,
                priority_score=score,
                matched_keywords=matched
            )

            if news_id:
                stats["new_count"] += 1

        stats["success"] = True

    except Exception as e:
        stats["error"] = str(e)

    duration_ms = int((time.time() - start_time) * 1000)

    update_source_fetch(
        source_id=source["id"],
        success=stats["success"],
        news_count=stats["new_count"],
        error_message=stats["error"],
        duration_ms=duration_ms
    )

    return stats


def fetch_all_sources(category: str = None) -> list:
    """Processa todas as fontes ativas."""
    sources = get_active_sources()

    if category:
        sources = [s for s in sources if s["category"] == category]

    positive_kw, negative_kw = get_keywords()

    results = []
    total = len(sources)

    for i, source in enumerate(sources, 1):
        print(f"[{i}/{total}] {source['name']}...", end=" ")
        result = process_feed(source, positive_kw, negative_kw)

        if result["success"]:
            print(f"OK ({result['new_count']} novas)")
        else:
            print(f"ERRO: {result['error'][:40]}")

        results.append(result)

    return results


def get_fetch_summary(results: list) -> dict:
    """Gera um resumo dos resultados do fetch."""
    return {
        "total_sources": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "total_news": sum(r["news_count"] for r in results),
        "new_news": sum(r["new_count"] for r in results),
        "skipped": sum(r["skipped_count"] for r in results),
        "errors": [
            {"source": r["source_name"], "error": r["error"]}
            for r in results if r["error"]
        ]
    }


if __name__ == "__main__":
    print("Iniciando fetch de todas as fontes...")
    results = fetch_all_sources()
    summary = get_fetch_summary(results)

    print(f"\nResumo:")
    print(f"  Fontes: {summary['successful']}/{summary['total_sources']} OK")
    print(f"  Novas notícias: {summary['new_news']}")
