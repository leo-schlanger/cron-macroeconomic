"""
Script para testar quais feeds RSS estão funcionando.
Gera um relatório detalhado do status de cada fonte.
"""
import json
import requests
import feedparser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

TIMEOUT = 15
USER_AGENT = "MacroNewsCron/1.0 (Feed Tester)"


def test_feed(name: str, url: str, category: str) -> dict:
    """Testa um único feed RSS."""
    result = {
        "name": name,
        "url": url,
        "category": category,
        "status": "unknown",
        "http_code": None,
        "entries_count": 0,
        "error": None
    }

    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        result["http_code"] = response.status_code

        if response.status_code != 200:
            result["status"] = "http_error"
            result["error"] = f"HTTP {response.status_code}"
            return result

        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            result["status"] = "parse_error"
            result["error"] = str(feed.bozo_exception)[:50] if feed.bozo_exception else "Parse error"
            return result

        result["entries_count"] = len(feed.entries)

        if result["entries_count"] == 0:
            result["status"] = "empty"
            result["error"] = "Feed vazio"
        else:
            result["status"] = "ok"

    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = f"Timeout ({TIMEOUT}s)"
    except requests.exceptions.SSLError as e:
        result["status"] = "ssl_error"
        result["error"] = "Erro SSL"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "connection_error"
        result["error"] = "Conexão recusada"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:50]

    return result


def load_feeds_from_json() -> list:
    """Carrega todos os feeds do arquivo JSON."""
    sources_path = Path(__file__).parent / "sources.json"

    with open(sources_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    feeds = []
    for category, cat_data in data.items():
        if category == "keywords":
            continue
        if "feeds" not in cat_data:
            continue
        for feed in cat_data["feeds"]:
            feeds.append({
                "name": feed["name"],
                "url": feed["url"],
                "category": category
            })

    return feeds


def run_tests(max_workers: int = 10) -> list:
    """Executa os testes em paralelo."""
    feeds = load_feeds_from_json()
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"[cyan]Testando {len(feeds)} feeds...", total=len(feeds))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(test_feed, f["name"], f["url"], f["category"]): f
                for f in feeds
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                progress.advance(task)

    return results


def print_results(results: list):
    """Imprime os resultados formatados."""
    # Ordenar por status
    status_order = {"ok": 0, "empty": 1, "timeout": 2, "http_error": 3,
                    "ssl_error": 4, "connection_error": 5, "parse_error": 6, "error": 7}
    results.sort(key=lambda x: (status_order.get(x["status"], 99), x["category"], x["name"]))

    # Tabela de resultados
    table = Table(title="\nResultados do Teste de Feeds RSS")
    table.add_column("Categoria", style="cyan", width=15)
    table.add_column("Fonte", style="white", width=35)
    table.add_column("Status", width=12)
    table.add_column("Entries", justify="right", width=8)
    table.add_column("Erro", style="dim", width=30)

    for r in results:
        if r["status"] == "ok":
            status = "[green]OK[/green]"
        elif r["status"] == "empty":
            status = "[yellow]VAZIO[/yellow]"
        elif r["status"] == "timeout":
            status = "[red]TIMEOUT[/red]"
        else:
            status = f"[red]{r['status'].upper()}[/red]"

        table.add_row(
            r["category"],
            r["name"][:35],
            status,
            str(r["entries_count"]) if r["entries_count"] > 0 else "-",
            (r["error"] or "")[:30]
        )

    console.print(table)

    # Resumo por status
    console.print("\n[bold]Resumo:[/bold]")
    status_counts = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    total = len(results)
    ok_count = status_counts.get("ok", 0)

    console.print(f"  Total de feeds: {total}")
    console.print(f"  [green]Funcionando: {ok_count} ({ok_count*100//total}%)[/green]")

    for status, count in sorted(status_counts.items()):
        if status != "ok":
            console.print(f"  {status}: {count}")

    # Resumo por categoria
    console.print("\n[bold]Por categoria:[/bold]")
    cat_stats = {}
    for r in results:
        cat = r["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"total": 0, "ok": 0}
        cat_stats[cat]["total"] += 1
        if r["status"] == "ok":
            cat_stats[cat]["ok"] += 1

    for cat, stats in sorted(cat_stats.items()):
        pct = stats["ok"] * 100 // stats["total"] if stats["total"] > 0 else 0
        color = "green" if pct >= 70 else "yellow" if pct >= 40 else "red"
        console.print(f"  {cat}: [{color}]{stats['ok']}/{stats['total']} ({pct}%)[/{color}]")

    return results


def save_working_feeds(results: list):
    """Salva apenas os feeds funcionando em um arquivo separado."""
    working = [r for r in results if r["status"] == "ok"]

    output_path = Path(__file__).parent / "working_feeds.json"

    output = {}
    for r in working:
        cat = r["category"]
        if cat not in output:
            output[cat] = []
        output[cat].append({
            "name": r["name"],
            "url": r["url"],
            "entries_count": r["entries_count"]
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    console.print(f"\n[green]Feeds funcionando salvos em: {output_path}[/green]")


def update_sources_status(results: list):
    """Atualiza o status das fontes no banco de dados."""
    try:
        from database import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        for r in results:
            is_active = 1 if r["status"] == "ok" else 0
            cursor.execute("""
                UPDATE sources SET is_active = ? WHERE url = ?
            """, (is_active, r["url"]))

        conn.commit()
        conn.close()
        console.print("[green]Status das fontes atualizado no banco de dados.[/green]")
    except Exception as e:
        console.print(f"[yellow]Aviso: Não foi possível atualizar o banco: {e}[/yellow]")


if __name__ == "__main__":
    console.print("\n[bold blue]Testando feeds RSS...[/bold blue]\n")

    results = run_tests(max_workers=15)
    print_results(results)
    save_working_feeds(results)
    update_sources_status(results)
