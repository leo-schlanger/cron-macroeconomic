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
from typing import Optional
from datetime import datetime

from database_blog import (
    get_pending_news, save_blog_post, update_queue_status,
    add_to_processing_queue, get_blog_stats
)
from database_supabase import get_connection, is_postgres
from deduplication import deduplicate_news_for_blog
from utils import retry, logger, RetryError
from html_parser import extract_image_from_content as extract_image_html

# APIs disponíveis
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Configuração
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # openai ou anthropic
MAX_API_RETRIES = 3


def extract_image_from_content(content: str, link: str) -> Optional[str]:
    """
    Extrai URL de imagem do conteúdo ou página.
    Usa BeautifulSoup para parsing robusto.
    """
    # Tentar buscar página original para og:image
    page_html = None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(link, headers=headers, timeout=10)
        page_html = response.text
    except (requests.RequestException, ValueError, AttributeError):
        pass

    # Usar parser robusto
    return extract_image_html(content, page_html)


@retry(
    max_attempts=MAX_API_RETRIES,
    delay=2.0,
    backoff=2.0,
    exceptions=(requests.exceptions.RequestException, requests.exceptions.Timeout)
)
def rewrite_with_openai(title: str, content: str, source_name: str) -> dict:
    """Reescreve notícia usando OpenAI GPT-4 com retry automático."""
    if not OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY não configurada")

    prompt = f"""Você é um jornalista econômico especializado em macroeconomia e mercados financeiros.
Com base nos FATOS da notícia abaixo, escreva um artigo ORIGINAL de blog com sua própria análise e estrutura.

FATOS DA NOTÍCIA (apenas como referência factual):
Título: {title}
Fonte: {source_name}
Conteúdo: {content[:2000]}

INSTRUÇÕES DE ORIGINALIDADE (CRÍTICO):
1. NÃO copie frases, estrutura ou parágrafos da notícia original
2. Crie uma estrutura e narrativa completamente novas
3. Use vocabulário e construções frasais diferentes do original
4. Adicione contexto macroeconômico relevante (ex: como isso se conecta a tendências globais)
5. Crie um título original que NÃO seja tradução ou paráfrase direta do original
6. O artigo deve funcionar de forma independente - um leitor não precisa ler a fonte original
7. Inclua ao final do conteúdo uma linha de atribuição: "Fonte original: {source_name}"

INSTRUÇÕES DE FORMATO:
1. Estruture com 3-5 parágrafos bem desenvolvidos
2. Use tom profissional, objetivo e factual
3. Gere um resumo de 2-3 frases
4. Crie 3-5 tags relevantes

DIRETRIZES DE IMPARCIALIDADE:
- Seja ESTRITAMENTE IMPARCIAL politicamente - não tome partido em conflitos
- Foque APENAS nos impactos econômicos e de mercado
- NÃO use linguagem emotiva ou sensacionalista
- NÃO faça julgamentos morais sobre países, governos ou grupos
- Apresente fatos de forma equilibrada, citando múltiplas perspectivas quando relevante
- Evite termos carregados como "terrorista", "regime", "colonizador" - use termos neutros
- Se a notícia envolver conflitos, foque APENAS nas consequências econômicas (preço do petróleo, mercados, sanções, comércio)

RESPONDA EM JSON:
{{
    "title_pt": "título original em português",
    "content_pt": "conteúdo original em português (3-5 parágrafos, com atribuição ao final)",
    "summary_pt": "resumo em português",
    "title_en": "original title in English",
    "content_en": "original content in English (3-5 paragraphs, with attribution at the end)",
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


@retry(
    max_attempts=MAX_API_RETRIES,
    delay=2.0,
    backoff=2.0,
    exceptions=(requests.exceptions.RequestException, requests.exceptions.Timeout)
)
def rewrite_with_anthropic(title: str, content: str, source_name: str) -> dict:
    """Reescreve notícia usando Claude com retry automático."""
    if not ANTHROPIC_API_KEY:
        raise Exception("ANTHROPIC_API_KEY não configurada")

    prompt = f"""Você é um jornalista econômico especializado em macroeconomia e mercados financeiros.
Com base nos FATOS da notícia abaixo, escreva um artigo ORIGINAL de blog com sua própria análise e estrutura.

FATOS DA NOTÍCIA (apenas como referência factual):
Título: {title}
Fonte: {source_name}
Conteúdo: {content[:2000]}

INSTRUÇÕES DE ORIGINALIDADE (CRÍTICO):
1. NÃO copie frases, estrutura ou parágrafos da notícia original
2. Crie uma estrutura e narrativa completamente novas
3. Use vocabulário e construções frasais diferentes do original
4. Adicione contexto macroeconômico relevante (ex: como isso se conecta a tendências globais)
5. Crie um título original que NÃO seja tradução ou paráfrase direta do original
6. O artigo deve funcionar de forma independente - um leitor não precisa ler a fonte original
7. Inclua ao final do conteúdo uma linha de atribuição: "Fonte original: {source_name}"

INSTRUÇÕES DE FORMATO:
1. Estruture com 3-5 parágrafos bem desenvolvidos
2. Use tom profissional, objetivo e factual
3. Gere um resumo de 2-3 frases
4. Crie 3-5 tags relevantes

DIRETRIZES DE IMPARCIALIDADE:
- Seja ESTRITAMENTE IMPARCIAL politicamente - não tome partido em conflitos
- Foque APENAS nos impactos econômicos e de mercado
- NÃO use linguagem emotiva ou sensacionalista
- NÃO faça julgamentos morais sobre países, governos ou grupos
- Apresente fatos de forma equilibrada, citando múltiplas perspectivas quando relevante
- Evite termos carregados como "terrorista", "regime", "colonizador" - use termos neutros
- Se a notícia envolver conflitos, foque APENAS nas consequências econômicas (preço do petróleo, mercados, sanções, comércio)

RESPONDA APENAS EM JSON (sem markdown):
{{
    "title_pt": "título original em português",
    "content_pt": "conteúdo original em português (3-5 parágrafos, com atribuição ao final)",
    "summary_pt": "resumo em português",
    "title_en": "original title in English",
    "content_en": "original content in English (3-5 paragraphs, with attribution at the end)",
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
        json_str = json_match.group()
        # Remover caracteres de controle inválidos em JSON (exceto \n \r \t que são comuns)
        # Substituir por espaço para não perder separação de palavras
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: tentar normalizar quebras de linha dentro de strings JSON
            # Substitui newlines literais por \n escapado dentro de valores string
            def fix_string_newlines(m):
                s = m.group(0)
                s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                return s
            json_str = re.sub(r'"[^"]*"', fix_string_newlines, json_str)
            return json.loads(json_str)
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
        logger.info(f"Processando: {news['title'][:50]}...")

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
        logger.info(f"  Post #{post_id} criado com sucesso")
        return True

    except RetryError as e:
        error_msg = f"Falhou após {MAX_API_RETRIES} tentativas: {e.last_exception}"
        logger.error(f"  Erro: {error_msg[:80]}")
        update_queue_status(news["queue_id"], "error", error_msg)
        return False
    except Exception as e:
        logger.error(f"  Erro: {str(e)[:80]}")
        update_queue_status(news["queue_id"], "error", str(e))
        return False


def queue_high_priority_news(min_score: float = 4.0, limit: int = 20):
    """Adiciona notícias de alta prioridade à fila de processamento."""
    conn = get_connection()
    try:
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
    finally:
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
    logger.info("=" * 50)
    logger.info("PROCESSAMENTO DE NOTÍCIAS PARA BLOG")
    logger.info("=" * 50)

    # Verificar API
    if not OPENAI_API_KEY and not ANTHROPIC_API_KEY:
        logger.error("ERRO: Configure OPENAI_API_KEY ou ANTHROPIC_API_KEY")
        return

    provider = "Anthropic" if AI_PROVIDER == "anthropic" else "OpenAI"
    logger.info(f"Usando: {provider}")

    # Pegar notícias pendentes
    pending = get_pending_news(limit * 2)  # Pegar mais para compensar duplicatas
    logger.info(f"Notícias na fila: {len(pending)}")

    # Deduplicar antes de processar
    pending = deduplicate_news_for_blog(pending)
    pending = pending[:limit]  # Limitar após deduplicação
    logger.info(f"Após deduplicação: {len(pending)}")

    success = 0
    errors = 0

    for news in pending:
        if process_single_news(news):
            success += 1
        else:
            errors += 1

    logger.info("=" * 50)
    logger.info(f"Concluído: {success} sucesso, {errors} erros")
    logger.info("=" * 50)


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
