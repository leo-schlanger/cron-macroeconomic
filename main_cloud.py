"""
Script principal - Versão Cloud (Supabase/PostgreSQL).
"""
import argparse
from datetime import datetime

from database_supabase import (
    init_db, load_sources_from_json, load_keywords_from_json,
    get_news_stats, get_active_sources, get_keywords,
    insert_news, update_source_fetch, cleanup_old_news
)
from fetcher_cloud import fetch_all_sources, get_fetch_summary


def run_fetch(category: str = None, verbose: bool = True):
    """Executa o fetch de todas as fontes."""
    start_time = datetime.now()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Fetch iniciado em: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if category:
            print(f"Categoria: {category}")
        print(f"{'='*60}\n")

    results = fetch_all_sources(category=category)
    summary = get_fetch_summary(results)

    if verbose:
        print(f"\nResultados:")
        print(f"  Fontes: {summary['successful']}/{summary['total_sources']} OK")
        print(f"  Notícias encontradas: {summary['total_news']}")
        print(f"  Novas salvas: {summary['new_news']}")
        print(f"  Duplicatas ignoradas: {summary.get('duplicates', 0)}")
        print(f"  Filtradas (keywords): {summary['skipped']}")

        if summary['failed'] > 0:
            print(f"\nFalhas ({summary['failed']}):")
            for err in summary['errors'][:5]:
                print(f"  - {err['source']}: {err['error'][:50]}")

        duration = (datetime.now() - start_time).total_seconds()
        print(f"\nDuração: {duration:.1f}s")

    return summary


def show_stats():
    """Mostra estatísticas do banco de dados."""
    stats = get_news_stats()

    print("\n" + "="*50)
    print("ESTATÍSTICAS")
    print("="*50)
    print(f"\nFontes:")
    print(f"  Total: {stats['total_sources']}")
    print(f"  Ativas: {stats['active_sources']}")
    print(f"\nNotícias:")
    print(f"  Total: {stats['total_news']}")
    print(f"  Não processadas: {stats['unprocessed_news']}")
    print(f"  Publicadas: {stats['published_blog']}")
    print(f"\nPor categoria:")
    for cat, count in sorted(stats['sources_by_category'].items()):
        print(f"  {cat}: {count}")
    print("="*50)


def setup():
    """Configura o banco de dados inicial."""
    print("Configurando banco de dados...\n")
    init_db()
    load_sources_from_json()
    load_keywords_from_json()
    print("\nConfiguração concluída!")
    show_stats()


def cleanup(days: int = 30):
    """Remove notícias antigas."""
    print(f"Removendo notícias com mais de {days} dias...")
    deleted = cleanup_old_news(days)
    print(f"Removidas: {deleted} notícias")


def main():
    parser = argparse.ArgumentParser(description="Cron Macroeconômico (Cloud)")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Configura o banco")

    fetch_parser = subparsers.add_parser("fetch", help="Busca notícias")
    fetch_parser.add_argument("--category", "-c")
    fetch_parser.add_argument("--quiet", "-q", action="store_true")

    subparsers.add_parser("stats", help="Estatísticas")

    cleanup_parser = subparsers.add_parser("cleanup", help="Limpa notícias antigas")
    cleanup_parser.add_argument("--days", "-d", type=int, default=30)

    args = parser.parse_args()

    if args.command == "setup":
        setup()
    elif args.command == "fetch":
        run_fetch(category=args.category, verbose=not args.quiet)
    elif args.command == "stats":
        show_stats()
    elif args.command == "cleanup":
        cleanup(days=args.days)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
