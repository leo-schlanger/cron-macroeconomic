"""
Script principal do Cron de Notícias Macroeconômicas.
Pode ser executado diretamente ou agendado via cron/task scheduler.
"""
import argparse
import schedule
import time
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

from database import init_db, load_sources_from_json, load_keywords_from_json, get_news_stats
from fetcher import fetch_all_sources, get_fetch_summary

console = Console()


def run_fetch(category: str = None, verbose: bool = True):
    """Executa o fetch de todas as fontes."""
    start_time = datetime.now()

    if verbose:
        console.print(f"\n[bold blue]{'='*60}[/bold blue]")
        console.print(f"[bold]Fetch iniciado em: {start_time.strftime('%Y-%m-%d %H:%M:%S')}[/bold]")
        if category:
            console.print(f"Categoria: [cyan]{category}[/cyan]")
        console.print(f"[bold blue]{'='*60}[/bold blue]\n")

    results = fetch_all_sources(category=category)
    summary = get_fetch_summary(results)

    if verbose:
        # Resultados resumidos
        console.print(f"\n[bold]Resultados:[/bold]")
        console.print(f"  Fontes: {summary['successful']}/{summary['total_sources']} OK")
        console.print(f"  Notícias encontradas: {summary['total_news']}")
        console.print(f"  [green]Novas salvas: {summary['new_news']}[/green]")
        console.print(f"  Filtradas: {summary['skipped']}")

        if summary['failed'] > 0:
            console.print(f"\n[red]Falhas ({summary['failed']}):[/red]")
            for err in summary['errors'][:5]:
                console.print(f"  - {err['source']}: {err['error'][:50]}")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        console.print(f"\n[dim]Duração: {duration:.1f}s[/dim]")

    return summary


def show_stats():
    """Mostra estatísticas do banco de dados."""
    stats = get_news_stats()

    panel_content = f"""
[bold]Fontes:[/bold]
  Total: {stats['total_sources']}
  Ativas: {stats['active_sources']}

[bold]Notícias:[/bold]
  Total: {stats['total_news']}
  Não processadas: {stats['unprocessed_news']}
  Publicadas no blog: {stats['published_blog']}

[bold]Por categoria:[/bold]
"""
    for cat, count in sorted(stats['sources_by_category'].items()):
        panel_content += f"  {cat}: {count}\n"

    console.print(Panel(panel_content, title="Estatísticas", border_style="blue"))


def run_scheduler(interval_minutes: int = 30):
    """Executa o scheduler para rodar periodicamente."""
    console.print(f"\n[bold green]Scheduler iniciado[/bold green]")
    console.print(f"Intervalo: {interval_minutes} minutos")
    console.print("Pressione Ctrl+C para parar\n")

    # Executar imediatamente na primeira vez
    run_fetch()

    # Agendar execuções
    schedule.every(interval_minutes).minutes.do(run_fetch)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler interrompido.[/yellow]")


def setup():
    """Configura o banco de dados inicial."""
    console.print("[bold]Configurando banco de dados...[/bold]\n")

    init_db()
    load_sources_from_json()
    load_keywords_from_json()

    console.print("\n[green]Configuração concluída![/green]")
    show_stats()


def main():
    parser = argparse.ArgumentParser(
        description="Cron de Notícias Macroeconômicas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py setup              # Configura o banco de dados
  python main.py fetch              # Executa fetch uma vez
  python main.py fetch --category crypto  # Fetch apenas crypto
  python main.py stats              # Mostra estatísticas
  python main.py scheduler          # Roda continuamente
  python main.py scheduler --interval 60  # Roda a cada 60 min
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # Setup
    subparsers.add_parser("setup", help="Configura o banco de dados")

    # Fetch
    fetch_parser = subparsers.add_parser("fetch", help="Executa fetch das fontes")
    fetch_parser.add_argument("--category", "-c", help="Filtrar por categoria")
    fetch_parser.add_argument("--quiet", "-q", action="store_true", help="Modo silencioso")

    # Stats
    subparsers.add_parser("stats", help="Mostra estatísticas")

    # Scheduler
    sched_parser = subparsers.add_parser("scheduler", help="Executa scheduler contínuo")
    sched_parser.add_argument("--interval", "-i", type=int, default=30,
                              help="Intervalo em minutos (default: 30)")

    args = parser.parse_args()

    if args.command == "setup":
        setup()
    elif args.command == "fetch":
        run_fetch(category=args.category, verbose=not args.quiet)
    elif args.command == "stats":
        show_stats()
    elif args.command == "scheduler":
        run_scheduler(interval_minutes=args.interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
