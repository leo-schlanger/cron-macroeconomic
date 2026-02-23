"""
Script para remover posts do Oriente Médio APENAS da tabela blog_posts.
Mantém as fontes ativas para coleta, mas remove conteúdo não-macroeconômico já publicado.
"""
import os
import sys

# Adicionar path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_blog import delete_posts_by_category, delete_posts_by_source_name_pattern, get_blog_stats


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

    # Deletar por fonte específica (caso a categoria não esteja setada)
    middle_east_sources = [
        "Al Jazeera",
        "Times of Israel",
        "Middle East Eye",
        "Khaleej Times"
    ]

    total_deleted_by_source = 0
    for source in middle_east_sources:
        deleted = delete_posts_by_source_name_pattern(source)
        if deleted > 0:
            print(f"  Deletados de '{source}': {deleted}")
            total_deleted_by_source += deleted

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
