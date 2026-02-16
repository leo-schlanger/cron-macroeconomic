"""
Processador de notícias para blog.
- Reescreve notícias usando IA
- Traduz para PT-BR e EN
- Extrai imagens de capa
"""
import os
import re
import json
import requests
from typing import Optional, Tuple
from datetime import datetime

from database_blog import (
    get_pending_news, save_blog_post, update_queue_status,
    add_to_processing_queue, get_blog_stats
)
from database_supabase import get_connection, is_postgres
from deduplication import deduplicate_news_for_blog

# APIs disponíveis
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Configuração
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # openai ou anthropic


def extract_image_from_content(content: str, link: str) -> Optional[str]:
    """Extrai URL de imagem do conteúdo ou página."""
    # Tentar extrair de tags img no conteúdo
    img_pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
    matches = re.findall(img_pattern, content)
    if matches:
        return matches[0]

    # Tentar extrair og:image da página original
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(link, headers=headers, timeout=10)
        og_pattern = r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
        og_matches = re.findall(og_pattern, response.text)
        if og_matches:
            return og_matches[0]

        # Tentar twitter:image
        twitter_pattern = r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']'
        twitter_matches = re.findall(twitter_pattern, response.text)
        if twitter_matches:
            return twitter_matches[0]
    except:
        pass

    return None


def rewrite_with_openai(title: str, content: str, source_name: str) -> Tuple[dict, dict]:
    """Reescreve notícia usando OpenAI GPT-4."""
    if not OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY não configurada")

    prompt = f"""Você é um jornalista especializado em economia e criptomoedas.
Reescreva a notícia abaixo em um formato de artigo de blog profissional.

NOTÍCIA ORIGINAL:
Título: {title}
Fonte: {source_name}
Conteúdo: {content[:2000]}

INSTRUÇÕES:
1. Reescreva completamente com suas próprias palavras (não copie)
2. Mantenha os fatos e dados importantes
3. Use tom profissional mas acessível
4. Estruture com parágrafos claros
5. Crie um título atrativo
6. Gere um resumo de 2-3 frases

RESPONDA EM JSON:
{{
    "title_pt": "título em português",
    "content_pt": "conteúdo completo em português (3-5 parágrafos)",
    "summary_pt": "resumo em português",
    "title_en": "title in English",
    "content_en": "full content in English (3-5 paragraphs)",
    "summary_en": "summary in English",
    "tags": ["tag1", "tag2", "tag3"]
}}"""

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"}
        },
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

    result = response.json()
    content_json = json.loads(result["choices"][0]["message"]["content"])

    return content_json


def rewrite_with_anthropic(title: str, content: str, source_name: str) -> dict:
    """Reescreve notícia usando Claude."""
    if not ANTHROPIC_API_KEY:
        raise Exception("ANTHROPIC_API_KEY não configurada")

    prompt = f"""Você é um jornalista especializado em economia e criptomoedas.
Reescreva a notícia abaixo em um formato de artigo de blog profissional.

NOTÍCIA ORIGINAL:
Título: {title}
Fonte: {source_name}
Conteúdo: {content[:2000]}

INSTRUÇÕES:
1. Reescreva completamente com suas próprias palavras (não copie)
2. Mantenha os fatos e dados importantes
3. Use tom profissional mas acessível
4. Estruture com parágrafos claros
5. Crie um título atrativo
6. Gere um resumo de 2-3 frases

RESPONDA APENAS EM JSON (sem markdown):
{{
    "title_pt": "título em português",
    "content_pt": "conteúdo completo em português (3-5 parágrafos)",
    "summary_pt": "resumo em português",
    "title_en": "title in English",
    "content_en": "full content in English (3-5 paragraphs)",
    "summary_en": "summary in English",
    "tags": ["tag1", "tag2", "tag3"]
}}"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        json={
            "model": "claude-3-haiku-20240307",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")

    result = response.json()
    text = result["content"][0]["text"]

    # Extrair JSON da resposta
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json.loads(json_match.group())
    else:
        raise Exception("Não foi possível extrair JSON da resposta")


def rewrite_news(title: str, content: str, source_name: str) -> dict:
    """Reescreve notícia usando o provedor de IA configurado."""
    if AI_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return rewrite_with_anthropic(title, content, source_name)
    elif OPENAI_API_KEY:
        return rewrite_with_openai(title, content, source_name)
    else:
        raise Exception("Nenhuma API de IA configurada. Configure OPENAI_API_KEY ou ANTHROPIC_API_KEY")


def process_single_news(news: dict) -> bool:
    """Processa uma única notícia."""
    try:
        print(f"  Processando: {news['title'][:50]}...")

        # Combinar título e descrição para contexto
        full_content = f"{news.get('description', '')} {news.get('content', '')}"

        # Reescrever com IA
        rewritten = rewrite_news(
            title=news["title"],
            content=full_content,
            source_name=news["source_name"]
        )

        # Extrair imagem
        image_url = extract_image_from_content(
            news.get("content", ""),
            news["link"]
        )

        # Salvar post do blog
        post_id = save_blog_post(
            news_id=news["id"],
            title_pt=rewritten["title_pt"],
            content_pt=rewritten["content_pt"],
            title_en=rewritten["title_en"],
            content_en=rewritten["content_en"],
            summary_pt=rewritten["summary_pt"],
            summary_en=rewritten["summary_en"],
            image_url=image_url,
            source_url=news["link"],
            source_name=news["source_name"],
            category=news["category"],
            tags=rewritten.get("tags", []),
            priority_score=news.get("priority_score", 0)
        )

        # Atualizar fila
        update_queue_status(news["queue_id"], "completed")
        print(f"    ✓ Post #{post_id} criado")
        return True

    except Exception as e:
        print(f"    ✗ Erro: {str(e)[:50]}")
        update_queue_status(news["queue_id"], "error", str(e))
        return False


def queue_high_priority_news(min_score: float = 4.0, limit: int = 20):
    """Adiciona notícias de alta prioridade à fila de processamento."""
    conn = get_connection()

    if is_postgres():
        from psycopg2.extras import RealDictCursor
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT n.id
            FROM news n
            LEFT JOIN processing_queue pq ON n.id = pq.news_id
            WHERE n.priority_score >= %s
            AND pq.id IS NULL
            AND n.is_processed = FALSE
            ORDER BY n.priority_score DESC
            LIMIT %s
        """, (min_score, limit))
    else:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.id
            FROM news n
            LEFT JOIN processing_queue pq ON n.id = pq.news_id
            WHERE n.priority_score >= ?
            AND pq.id IS NULL
            AND n.is_processed = 0
            ORDER BY n.priority_score DESC
            LIMIT ?
        """, (min_score, limit))

    rows = cursor.fetchall()
    conn.close()

    count = 0
    for row in rows:
        news_id = row[0] if isinstance(row, tuple) else row["id"]
        if add_to_processing_queue(news_id):
            count += 1

    print(f"[Queue] {count} notícias adicionadas à fila")
    return count


def process_queue(limit: int = 10):
    """Processa notícias da fila."""
    print(f"\n{'='*50}")
    print("PROCESSAMENTO DE NOTÍCIAS PARA BLOG")
    print(f"{'='*50}\n")

    # Verificar API
    if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        print("ERRO: Configure OPENAI_API_KEY ou ANTHROPIC_API_KEY")
        return

    provider = "Anthropic" if AI_PROVIDER == "anthropic" else "OpenAI"
    print(f"Usando: {provider}")

    # Pegar notícias pendentes
    pending = get_pending_news(limit * 2)  # Pegar mais para compensar duplicatas
    print(f"Notícias na fila: {len(pending)}")

    # Deduplicar antes de processar
    pending = deduplicate_news_for_blog(pending)
    pending = pending[:limit]  # Limitar após deduplicação
    print(f"Após deduplicação: {len(pending)}\n")

    success = 0
    errors = 0

    for news in pending:
        if process_single_news(news):
            success += 1
        else:
            errors += 1

    print(f"\n{'='*50}")
    print(f"Concluído: {success} sucesso, {errors} erros")
    print(f"{'='*50}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Processador de notícias para blog")
    subparsers = parser.add_subparsers(dest="command")

    # Queue
    queue_parser = subparsers.add_parser("queue", help="Adiciona notícias à fila")
    queue_parser.add_argument("--min-score", "-s", type=float, default=2.0)
    queue_parser.add_argument("--limit", "-l", type=int, default=20)

    # Process
    process_parser = subparsers.add_parser("process", help="Processa fila")
    process_parser.add_argument("--limit", "-l", type=int, default=10)

    # Stats
    subparsers.add_parser("stats", help="Estatísticas")

    # Init
    subparsers.add_parser("init", help="Inicializa tabelas de blog")

    args = parser.parse_args()

    if args.command == "init":
        from database_blog import init_blog_tables
        init_blog_tables()

    elif args.command == "queue":
        queue_high_priority_news(args.min_score, args.limit)

    elif args.command == "process":
        process_queue(args.limit)

    elif args.command == "stats":
        stats = get_blog_stats()
        print("\nEstatísticas do Blog:")
        print(f"  Total de posts: {stats['total_posts']}")
        print(f"  Rascunhos: {stats['drafts']}")
        print(f"  Publicados: {stats['published']}")
        print(f"  Pendentes: {stats['pending_processing']}")
        print(f"  Processados: {stats['processed']}")
        print(f"  Erros: {stats['errors']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
