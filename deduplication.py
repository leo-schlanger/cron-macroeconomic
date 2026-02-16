"""
Módulo de deduplicação de notícias sem IA.
Usa normalização de texto e hashing para detectar duplicatas.
"""
import re
import hashlib
from typing import Optional, List, Set
from datetime import datetime, timedelta

# Stopwords comuns em inglês e português (para normalização)
STOPWORDS = {
    # English
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
    'she', 'we', 'they', 'what', 'which', 'who', 'whom', 'when', 'where',
    'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'not', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there',
    'says', 'said', 'report', 'reports', 'according', 'new', 'news',
    # Portuguese
    'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'de', 'da', 'do',
    'das', 'dos', 'em', 'na', 'no', 'nas', 'nos', 'por', 'para', 'com',
    'sem', 'sob', 'sobre', 'entre', 'e', 'ou', 'mas', 'se', 'que',
    'qual', 'quais', 'como', 'quando', 'onde', 'porque', 'isso', 'isto',
    'esse', 'essa', 'este', 'esta', 'aquele', 'aquela', 'ser', 'estar',
    'ter', 'haver', 'fazer', 'dizer', 'disse', 'diz', 'vai', 'vão',
    'pode', 'podem', 'deve', 'devem', 'segundo', 'ainda', 'mais', 'menos',
    'muito', 'pouco', 'bem', 'mal', 'já', 'ainda', 'sempre', 'nunca',
    'notícia', 'notícias', 'novo', 'nova', 'novos', 'novas'
}


def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparação.
    - Converte para minúsculas
    - Remove pontuação
    - Remove stopwords
    - Remove espaços extras
    """
    if not text:
        return ""

    # Minúsculas
    text = text.lower()

    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)

    # Remove pontuação e caracteres especiais
    text = re.sub(r'[^\w\s]', ' ', text)

    # Remove números isolados (mantém números em palavras como "covid19")
    text = re.sub(r'\b\d+\b', '', text)

    # Split em palavras
    words = text.split()

    # Remove stopwords e palavras muito curtas
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]

    # Ordena palavras (para que ordem não importe)
    words.sort()

    return ' '.join(words)


def generate_title_hash(title: str) -> str:
    """
    Gera hash MD5 do título normalizado.
    Usado para detectar títulos duplicados/similares.
    """
    normalized = normalize_text(title)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]


def generate_content_fingerprint(title: str, description: str) -> str:
    """
    Gera fingerprint combinando título e descrição.
    Mais preciso que apenas o título.
    """
    combined = f"{title} {description}"
    normalized = normalize_text(combined)

    # Pega as 10 palavras mais significativas
    words = normalized.split()[:10]

    return hashlib.md5(' '.join(words).encode('utf-8')).hexdigest()[:16]


def extract_key_entities(text: str) -> Set[str]:
    """
    Extrai entidades-chave do texto (números, nomes próprios, siglas).
    Útil para comparar se notícias são sobre o mesmo assunto.
    """
    entities = set()

    # Números com contexto (ex: "5%", "$100", "2024")
    numbers = re.findall(r'\$?\d+(?:\.\d+)?%?', text)
    entities.update(numbers)

    # Siglas (2-5 letras maiúsculas)
    acronyms = re.findall(r'\b[A-Z]{2,5}\b', text)
    entities.update(acronyms)

    # Palavras capitalizadas (possíveis nomes próprios)
    # Ignora início de frase
    proper_nouns = re.findall(r'(?<!^)(?<!\. )[A-Z][a-z]+', text)
    entities.update(proper_nouns)

    return entities


def calculate_similarity_score(title1: str, title2: str,
                               desc1: str = "", desc2: str = "") -> float:
    """
    Calcula score de similaridade entre duas notícias (0.0 a 1.0).
    Sem usar IA - baseado em palavras em comum.
    """
    # Normalizar textos
    words1 = set(normalize_text(f"{title1} {desc1}").split())
    words2 = set(normalize_text(f"{title2} {desc2}").split())

    if not words1 or not words2:
        return 0.0

    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)

    jaccard = intersection / union if union > 0 else 0.0

    # Boost se entidades-chave coincidem
    entities1 = extract_key_entities(f"{title1} {desc1}")
    entities2 = extract_key_entities(f"{title2} {desc2}")

    if entities1 and entities2:
        entity_overlap = len(entities1 & entities2) / max(len(entities1), len(entities2))
        # Entidades têm peso maior
        return (jaccard * 0.4) + (entity_overlap * 0.6)

    return jaccard


def is_duplicate(new_title: str, new_desc: str,
                 existing_titles: List[dict],
                 threshold: float = 0.6) -> Optional[int]:
    """
    Verifica se uma notícia é duplicata de alguma existente.

    Args:
        new_title: Título da nova notícia
        new_desc: Descrição da nova notícia
        existing_titles: Lista de dicts com 'id', 'title', 'description'
        threshold: Limiar de similaridade (0.6 = 60% similar)

    Returns:
        ID da notícia duplicada ou None se não for duplicata
    """
    new_hash = generate_title_hash(new_title)

    for existing in existing_titles:
        # Primeiro check: hash exato
        existing_hash = generate_title_hash(existing['title'])
        if new_hash == existing_hash:
            return existing['id']

        # Segundo check: similaridade
        similarity = calculate_similarity_score(
            new_title, existing['title'],
            new_desc, existing.get('description', '')
        )

        if similarity >= threshold:
            return existing['id']

    return None


def get_recent_titles_for_dedup(conn, hours: int = 48) -> List[dict]:
    """
    Busca títulos recentes para verificação de duplicatas.
    """
    from database_supabase import is_postgres

    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            SELECT id, title, description
            FROM news
            WHERE fetched_at > NOW() - INTERVAL '%s hours'
            ORDER BY fetched_at DESC
            LIMIT 1000
        """, (hours,))
    else:
        cursor.execute("""
            SELECT id, title, description
            FROM news
            WHERE fetched_at > datetime('now', ?)
            ORDER BY fetched_at DESC
            LIMIT 1000
        """, (f'-{hours} hours',))

    rows = cursor.fetchall()

    # Converter para lista de dicts
    if rows:
        columns = ['id', 'title', 'description']
        return [dict(zip(columns, row)) for row in rows]

    return []


# ============================================================
# Funções para deduplicação no processamento de blog
# ============================================================

def group_similar_news(news_list: List[dict], threshold: float = 0.5) -> List[List[dict]]:
    """
    Agrupa notícias similares.
    Retorna lista de grupos, onde cada grupo são notícias sobre o mesmo assunto.
    """
    if not news_list:
        return []

    groups = []
    used = set()

    for i, news1 in enumerate(news_list):
        if i in used:
            continue

        group = [news1]
        used.add(i)

        for j, news2 in enumerate(news_list[i+1:], start=i+1):
            if j in used:
                continue

            similarity = calculate_similarity_score(
                news1['title'], news2['title'],
                news1.get('description', ''), news2.get('description', '')
            )

            if similarity >= threshold:
                group.append(news2)
                used.add(j)

        groups.append(group)

    return groups


def select_best_from_group(group: List[dict]) -> dict:
    """
    Seleciona a melhor notícia de um grupo de similares.
    Critérios: maior priority_score, depois maior conteúdo.
    """
    if len(group) == 1:
        return group[0]

    # Ordenar por priority_score (desc), depois por tamanho do conteúdo (desc)
    sorted_group = sorted(
        group,
        key=lambda x: (
            x.get('priority_score', 0),
            len(x.get('content', '') or ''),
            len(x.get('description', '') or '')
        ),
        reverse=True
    )

    return sorted_group[0]


def deduplicate_news_for_blog(news_list: List[dict]) -> List[dict]:
    """
    Remove duplicatas de uma lista de notícias para processamento de blog.
    Mantém apenas a melhor versão de cada notícia similar.
    """
    if not news_list:
        return []

    # Agrupar similares
    groups = group_similar_news(news_list, threshold=0.5)

    # Selecionar melhor de cada grupo
    deduplicated = [select_best_from_group(group) for group in groups]

    print(f"[Dedup] {len(news_list)} notícias → {len(deduplicated)} únicas ({len(news_list) - len(deduplicated)} duplicatas removidas)")

    return deduplicated


# ============================================================
# Testes
# ============================================================

if __name__ == "__main__":
    # Teste de normalização
    print("=== Teste de Normalização ===")
    t1 = "Fed Raises Interest Rates by 0.25%"
    t2 = "Federal Reserve increases interest rates by 0.25 percent"

    print(f"Título 1: {t1}")
    print(f"Normalizado: {normalize_text(t1)}")
    print(f"Hash: {generate_title_hash(t1)}")
    print()
    print(f"Título 2: {t2}")
    print(f"Normalizado: {normalize_text(t2)}")
    print(f"Hash: {generate_title_hash(t2)}")
    print()

    # Teste de similaridade
    print("=== Teste de Similaridade ===")
    similarity = calculate_similarity_score(t1, t2)
    print(f"Similaridade: {similarity:.2%}")
    print()

    # Teste com notícias diferentes
    t3 = "Bitcoin drops 10% amid market uncertainty"
    print(f"Título 3: {t3}")
    sim_1_3 = calculate_similarity_score(t1, t3)
    print(f"Similaridade T1-T3: {sim_1_3:.2%}")
