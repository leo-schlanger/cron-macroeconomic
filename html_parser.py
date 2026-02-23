"""
Módulo de parsing HTML robusto usando BeautifulSoup.
Substitui parsing baseado em regex por soluções mais confiáveis.
"""
from typing import Optional, List
import re

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def clean_html(text: str) -> str:
    """
    Remove tags HTML de um texto de forma segura.

    Args:
        text: Texto com possíveis tags HTML

    Returns:
        Texto limpo sem HTML
    """
    if not text:
        return ""

    if HAS_BS4:
        # Usar BeautifulSoup para parsing robusto
        soup = BeautifulSoup(text, 'html.parser')
        # Extrair texto, preservando espaços entre elementos
        clean = soup.get_text(separator=' ')
    else:
        # Fallback para regex (menos confiável)
        clean = re.sub(r'<[^>]+>', ' ', text)

    # Normalizar espaços
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def extract_og_image(html: str) -> Optional[str]:
    """
    Extrai URL da imagem Open Graph de uma página HTML.

    Args:
        html: Conteúdo HTML da página

    Returns:
        URL da imagem ou None
    """
    if not html:
        return None

    if HAS_BS4:
        soup = BeautifulSoup(html, 'html.parser')

        # Tentar og:image primeiro
        og_tag = soup.find('meta', property='og:image')
        if og_tag and og_tag.get('content'):
            return og_tag['content']

        # Fallback para twitter:image
        twitter_tag = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_tag and twitter_tag.get('content'):
            return twitter_tag['content']

        # Tentar variações (alguns sites usam name em vez de property)
        og_tag_alt = soup.find('meta', attrs={'name': 'og:image'})
        if og_tag_alt and og_tag_alt.get('content'):
            return og_tag_alt['content']
    else:
        # Fallback regex
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)

    return None


def extract_first_image(html: str) -> Optional[str]:
    """
    Extrai URL da primeira imagem encontrada no HTML.

    Args:
        html: Conteúdo HTML

    Returns:
        URL da imagem ou None
    """
    if not html:
        return None

    if HAS_BS4:
        soup = BeautifulSoup(html, 'html.parser')
        img_tag = soup.find('img', src=True)
        if img_tag:
            return img_tag['src']
    else:
        # Fallback regex
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_image_from_content(content: str, page_html: str = None) -> Optional[str]:
    """
    Extrai a melhor imagem disponível do conteúdo ou página.

    Ordem de prioridade:
    1. og:image da página
    2. twitter:image da página
    3. Primeira imagem no conteúdo

    Args:
        content: Conteúdo do artigo (pode conter HTML)
        page_html: HTML completo da página (opcional)

    Returns:
        URL da melhor imagem encontrada ou None
    """
    # Tentar extrair de meta tags primeiro (maior qualidade)
    if page_html:
        og_image = extract_og_image(page_html)
        if og_image:
            return og_image

    # Fallback para imagem no conteúdo
    if content:
        return extract_first_image(content)

    return None


def extract_text_content(html: str, max_length: int = None) -> str:
    """
    Extrai conteúdo textual principal de HTML.

    Args:
        html: Conteúdo HTML
        max_length: Tamanho máximo do texto (opcional)

    Returns:
        Texto extraído
    """
    text = clean_html(html)

    if max_length and len(text) > max_length:
        # Cortar no último espaço antes do limite
        text = text[:max_length].rsplit(' ', 1)[0] + '...'

    return text


def extract_links(html: str) -> List[dict]:
    """
    Extrai todos os links de um HTML.

    Args:
        html: Conteúdo HTML

    Returns:
        Lista de dicts com 'href' e 'text'
    """
    links = []

    if not html:
        return links

    if HAS_BS4:
        soup = BeautifulSoup(html, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            links.append({
                'href': a_tag['href'],
                'text': a_tag.get_text(strip=True)
            })
    else:
        # Fallback regex (básico)
        pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
        for match in re.finditer(pattern, html, re.IGNORECASE):
            links.append({
                'href': match.group(1),
                'text': match.group(2).strip()
            })

    return links


# ============================================================
# TESTES
# ============================================================

if __name__ == "__main__":
    print(f"BeautifulSoup disponível: {HAS_BS4}\n")

    # Teste clean_html
    html_test = """
    <div class="article">
        <h1>Título do Artigo</h1>
        <p>Este é um <strong>parágrafo</strong> com <a href="#">link</a>.</p>
        <script>alert('malicious');</script>
    </div>
    """
    print("=== Teste clean_html ===")
    print(f"Input: {html_test[:50]}...")
    print(f"Output: {clean_html(html_test)}")
    print()

    # Teste extract_og_image
    page_html = """
    <html>
    <head>
        <meta property="og:image" content="https://example.com/image.jpg">
        <meta name="twitter:image" content="https://example.com/twitter.jpg">
    </head>
    </html>
    """
    print("=== Teste extract_og_image ===")
    print(f"og:image: {extract_og_image(page_html)}")
    print()

    # Teste extract_first_image
    content = '<p>Texto <img src="https://cdn.example.com/photo.png" alt="foto"> mais texto</p>'
    print("=== Teste extract_first_image ===")
    print(f"Imagem: {extract_first_image(content)}")
    print()

    # Teste extract_links
    links_html = '<a href="https://google.com">Google</a> e <a href="https://github.com">GitHub</a>'
    print("=== Teste extract_links ===")
    print(f"Links: {extract_links(links_html)}")
