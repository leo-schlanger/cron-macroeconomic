"""
Script para visualizar notícias coletadas.
"""
import argparse
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from database import get_connection

console = Console()


def get_top_news(limit: int = 20, category: str = None, hours: int = 24) -> list:
    """Retorna as notícias de maior prioridade."""
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = datetime.now() - timedelta(hours=hours)

    query = """
        SELECT n.*, s.name as source_name, s.category
        FROM news n
        JOIN sources s ON n.source_id = s.id
        WHERE n.priority_score > 0
        AND n.fetched_at > ?
    """
    params = [cutoff.isoformat()]

    if category:
        query += " AND s.category = ?"
        params.append(category)

    query += " ORDER BY n.priority_score DESC, n.published_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    news = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return news


def get_news_by_keyword(keyword: str, limit: int = 20) -> list:
    """Busca notícias por palavra-chave."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT n.*, s.name as source_name, s.category
        FROM news n
        JOIN sources s ON n.source_id = s.id
        WHERE (n.title LIKE ? OR n.description LIKE ?)
        ORDER BY n.published_at DESC
        LIMIT ?
    """, (f"%{keyword}%", f"%{keyword}%", limit))

    news = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return news


def get_recent_news(limit: int = 50, category: str = None) -> list:
    """Retorna as notícias mais recentes."""
    conn = get_connection()
    cursor = conn.cursor()

    if category:
        cursor.execute("""
            SELECT n.*, s.name as source_name, s.category
            FROM news n
            JOIN sources s ON n.source_id = s.id
            WHERE s.category = ?
            ORDER BY n.published_at DESC
            LIMIT ?
        """, (category, limit))
    else:
        cursor.execute("""
            SELECT n.*, s.name as source_name, s.category
            FROM news n
            JOIN sources s ON n.source_id = s.id
            ORDER BY n.published_at DESC
            LIMIT ?
        """, (limit,))

    news = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return news


def display_news(news_list: list, title: str = "Notícias"):
    """Exibe notícias formatadas."""
    if not news_list:
        console.print("[yellow]Nenhuma notícia encontrada.[/yellow]")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("Score", justify="right", style="yellow", width=6)
    table.add_column("Categoria", style="cyan", width=12)
    table.add_column("Fonte", style="blue", width=20)
    table.add_column("Título", style="white", width=60)
    table.add_column("Keywords", style="green", width=20)

    for n in news_list:
        score = f"{n['priority_score']:.1f}" if n['priority_score'] else "-"
        keywords = n.get('matched_keywords', '')
        if keywords and keywords != 'null':
            import json
            try:
                kw_list = json.loads(keywords)
                keywords = ", ".join(kw_list[:3])
            except:
                keywords = ""
        else:
            keywords = ""

        table.add_row(
            score,
            n['category'],
            n['source_name'][:20],
            n['title'][:60],
            keywords[:20]
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Visualizador de Notícias")
    subparsers = parser.add_subparsers(dest="command")

    # Top news
    top_parser = subparsers.add_parser("top", help="Notícias de alta prioridade")
    top_parser.add_argument("--limit", "-l", type=int, default=20)
    top_parser.add_argument("--category", "-c", help="Filtrar por categoria")
    top_parser.add_argument("--hours", "-H", type=int, default=24)

    # Recent news
    recent_parser = subparsers.add_parser("recent", help="Notícias mais recentes")
    recent_parser.add_argument("--limit", "-l", type=int, default=30)
    recent_parser.add_argument("--category", "-c", help="Filtrar por categoria")

    # Search
    search_parser = subparsers.add_parser("search", help="Buscar por palavra-chave")
    search_parser.add_argument("keyword", help="Palavra-chave para buscar")
    search_parser.add_argument("--limit", "-l", type=int, default=20)

    args = parser.parse_args()

    if args.command == "top":
        news = get_top_news(limit=args.limit, category=args.category, hours=args.hours)
        display_news(news, f"Top {len(news)} Notícias de Alta Prioridade")

    elif args.command == "recent":
        news = get_recent_news(limit=args.limit, category=args.category)
        display_news(news, f"Últimas {len(news)} Notícias")

    elif args.command == "search":
        news = get_news_by_keyword(args.keyword, limit=args.limit)
        display_news(news, f"Busca: '{args.keyword}'")

    else:
        # Default: mostrar top notícias
        news = get_top_news(limit=15)
        display_news(news, "Top 15 Notícias de Alta Prioridade")


if __name__ == "__main__":
    main()
