"""
Script para testar feeds RSS - Versão Turso.
"""
import json
import requests
import feedparser
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        result["status"] = "ok" if result["entries_count"] > 0 else "empty"

    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = f"Timeout ({TIMEOUT}s)"
    except requests.exceptions.SSLError:
        result["status"] = "ssl_error"
        result["error"] = "Erro SSL"
    except requests.exceptions.ConnectionError:
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
        if category == "keywords" or "feeds" not in cat_data:
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

    print(f"Testando {len(feeds)} feeds...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(test_feed, f["name"], f["url"], f["category"]): f
            for f in feeds
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "OK" if result["status"] == "ok" else result["status"].upper()
            print(f"  [{status}] {result['name']}")

    return results


def print_summary(results: list):
    """Imprime resumo dos testes."""
    total = len(results)
    ok_count = sum(1 for r in results if r["status"] == "ok")

    print(f"\n{'='*50}")
    print("RESUMO")
    print(f"{'='*50}")
    print(f"Total de feeds: {total}")
    print(f"Funcionando: {ok_count} ({ok_count*100//total}%)")

    status_counts = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    for status, count in sorted(status_counts.items()):
        if status != "ok":
            print(f"  {status}: {count}")

    # Por categoria
    print(f"\nPor categoria:")
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
        print(f"  {cat}: {stats['ok']}/{stats['total']} ({pct}%)")


def update_database_status(results: list):
    """Atualiza status no banco de dados."""
    try:
        from database_turso import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        for r in results:
            is_active = 1 if r["status"] == "ok" else 0
            cursor.execute("UPDATE sources SET is_active = ? WHERE url = ?",
                          (is_active, r["url"]))

        conn.commit()
        conn.close()
        print("\nStatus atualizado no banco de dados.")
    except Exception as e:
        print(f"\nAviso: Não foi possível atualizar o banco: {e}")


if __name__ == "__main__":
    print("\nTestando feeds RSS...\n")
    results = run_tests(max_workers=15)
    print_summary(results)
    update_database_status(results)
