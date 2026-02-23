"""
Script para remover posts do Oriente Médio APENAS da tabela blog_posts.
Mantém as fontes ativas para coleta, mas remove conteúdo não-macroeconômico já publicado.
"""
import os
import sys

# Adicionar path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_blog import (
    delete_posts_by_category,
    delete_posts_by_source_name_pattern,
    get_blog_stats,
    get_connection,
    is_postgres
)


def delete_posts_by_slug_pattern(pattern: str) -> int:
    """Deleta posts cujo slug contém o padrão."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        if is_postgres():
            cursor.execute("""
                DELETE FROM blog_posts
                WHERE slug_pt ILIKE %s OR slug_en ILIKE %s
                RETURNING id
            """, (f"%{pattern}%", f"%{pattern}%"))
            deleted = cursor.rowcount
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM blog_posts
                WHERE slug_pt LIKE ? OR slug_en LIKE ?
            """, (f"%{pattern}%", f"%{pattern}%"))
            deleted = cursor.fetchone()[0]
            cursor.execute("""
                DELETE FROM blog_posts
                WHERE slug_pt LIKE ? OR slug_en LIKE ?
            """, (f"%{pattern}%", f"%{pattern}%"))

        conn.commit()
        return deleted
    finally:
        conn.close()


def delete_posts_by_title_keywords(keywords: list) -> int:
    """Deleta posts cujo título contém palavras-chave de conflitos."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        total_deleted = 0

        for kw in keywords:
            if is_postgres():
                cursor.execute("""
                    DELETE FROM blog_posts
                    WHERE title_pt ILIKE %s OR title_en ILIKE %s
                    RETURNING id
                """, (f"%{kw}%", f"%{kw}%"))
                deleted = cursor.rowcount
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM blog_posts
                    WHERE title_pt LIKE ? OR title_en LIKE ?
                """, (f"%{kw}%", f"%{kw}%"))
                deleted = cursor.fetchone()[0]
                cursor.execute("""
                    DELETE FROM blog_posts
                    WHERE title_pt LIKE ? OR title_en LIKE ?
                """, (f"%{kw}%", f"%{kw}%"))

            if deleted > 0:
                print(f"    Deletados com '{kw}': {deleted}")
                total_deleted += deleted

        conn.commit()
        return total_deleted
    finally:
        conn.close()


def main():
    print("=" * 50)
    print("LIMPEZA DE POSTS DO BLOG - ORIENTE MÉDIO")
    print("(Apenas tabela blog_posts, fontes permanecem ativas)")
    print("=" * 50)

    # Estatísticas antes
    stats_before = get_blog_stats()
    print(f"\nAntes da limpeza:")
    print(f"  Total de posts no blog: {stats_before['total_posts']}")

    # Deletar por categoria
    deleted_category = delete_posts_by_category("middle_east")
    print(f"\nDeletados por categoria 'middle_east': {deleted_category}")

    # Deletar por fonte específica
    print("\nBuscando por fonte:")
    middle_east_sources = [
        "Al Jazeera",
        "Times of Israel",
        "Middle East Eye",
        "Khaleej Times"
    ]

    for source in middle_east_sources:
        deleted = delete_posts_by_source_name_pattern(source)
        if deleted > 0:
            print(f"  Deletados de '{source}': {deleted}")

    # Deletar por palavras-chave de conflitos no título
    print("\nBuscando por palavras-chave de conflitos:")
    conflict_keywords = [
        "colonos", "settlers", "palestin", "israel",
        "prisão", "prison", "prisioneiro", "prisoner",
        "safari", "ataque", "attack", "massacre",
        "gaza", "west bank", "cisjordânia",
        "hamas", "hezbollah", "idf"
    ]

    deleted_by_keywords = delete_posts_by_title_keywords(conflict_keywords)

    # Estatísticas depois
    stats_after = get_blog_stats()
    print(f"\nDepois da limpeza:")
    print(f"  Total de posts no blog: {stats_after['total_posts']}")
    print(f"\nTotal removido: {stats_before['total_posts'] - stats_after['total_posts']}")
    print("=" * 50)
    print("\nNota: As fontes de RSS permanecem ativas.")
    print("Os filtros no sources.json controlarão futuras publicações.")


if __name__ == "__main__":
    main()
