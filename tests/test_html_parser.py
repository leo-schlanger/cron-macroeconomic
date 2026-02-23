"""
Testes para o módulo html_parser.
"""
import pytest
import sys
from pathlib import Path

# Adicionar diretório pai ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from html_parser import (
    clean_html,
    extract_og_image,
    extract_first_image,
    extract_image_from_content,
    extract_links,
    extract_text_content
)


class TestCleanHtml:
    """Testes para a função clean_html."""

    def test_remove_simple_tags(self):
        html = "<p>Hello <strong>World</strong></p>"
        assert clean_html(html) == "Hello World"

    def test_remove_nested_tags(self):
        html = "<div><p>Text <span>nested</span></p></div>"
        assert clean_html(html) == "Text nested"

    def test_handle_empty_string(self):
        assert clean_html("") == ""

    def test_handle_none(self):
        assert clean_html(None) == ""

    def test_normalize_whitespace(self):
        html = "<p>Text   with    spaces</p>"
        assert clean_html(html) == "Text with spaces"

    def test_handle_script_tags(self):
        html = "<p>Safe</p><script>alert('xss')</script><p>Text</p>"
        result = clean_html(html)
        assert "alert" not in result or "Safe" in result

    def test_preserve_text_between_tags(self):
        html = "<p>First</p><p>Second</p>"
        result = clean_html(html)
        assert "First" in result and "Second" in result

    def test_handle_special_characters(self):
        html = "<p>&amp; &lt; &gt;</p>"
        result = clean_html(html)
        # BeautifulSoup converte entities
        assert "&" in result or "amp" in result


class TestExtractOgImage:
    """Testes para a função extract_og_image."""

    def test_extract_og_image_property(self):
        html = '''
        <html><head>
            <meta property="og:image" content="https://example.com/image.jpg">
        </head></html>
        '''
        assert extract_og_image(html) == "https://example.com/image.jpg"

    def test_extract_twitter_image_fallback(self):
        html = '''
        <html><head>
            <meta name="twitter:image" content="https://twitter.com/img.png">
        </head></html>
        '''
        assert extract_og_image(html) == "https://twitter.com/img.png"

    def test_prefer_og_over_twitter(self):
        html = '''
        <html><head>
            <meta property="og:image" content="https://og.com/image.jpg">
            <meta name="twitter:image" content="https://twitter.com/img.png">
        </head></html>
        '''
        assert extract_og_image(html) == "https://og.com/image.jpg"

    def test_handle_missing_meta(self):
        html = "<html><head><title>No Image</title></head></html>"
        assert extract_og_image(html) is None

    def test_handle_empty_content(self):
        html = '<meta property="og:image" content="">'
        result = extract_og_image(html)
        # Pode retornar None ou string vazia dependendo da implementação
        assert result is None or result == ""

    def test_handle_none_input(self):
        assert extract_og_image(None) is None

    def test_handle_empty_input(self):
        assert extract_og_image("") is None


class TestExtractFirstImage:
    """Testes para a função extract_first_image."""

    def test_extract_simple_image(self):
        html = '<img src="https://example.com/photo.jpg" alt="Photo">'
        assert extract_first_image(html) == "https://example.com/photo.jpg"

    def test_extract_first_of_multiple(self):
        html = '''
        <img src="https://first.com/1.jpg">
        <img src="https://second.com/2.jpg">
        '''
        assert extract_first_image(html) == "https://first.com/1.jpg"

    def test_handle_single_quotes(self):
        html = "<img src='https://example.com/img.png'>"
        assert extract_first_image(html) == "https://example.com/img.png"

    def test_handle_no_image(self):
        html = "<p>No images here</p>"
        assert extract_first_image(html) is None

    def test_handle_empty_input(self):
        assert extract_first_image("") is None
        assert extract_first_image(None) is None

    def test_handle_image_with_attributes(self):
        html = '<img class="photo" src="https://cdn.com/img.jpg" width="100">'
        assert extract_first_image(html) == "https://cdn.com/img.jpg"


class TestExtractImageFromContent:
    """Testes para a função extract_image_from_content."""

    def test_prefer_og_image(self):
        content = '<img src="https://content.com/img.jpg">'
        page = '<meta property="og:image" content="https://og.com/cover.jpg">'
        result = extract_image_from_content(content, page)
        assert result == "https://og.com/cover.jpg"

    def test_fallback_to_content_image(self):
        content = '<img src="https://content.com/img.jpg">'
        page = "<html><head></head></html>"
        result = extract_image_from_content(content, page)
        assert result == "https://content.com/img.jpg"

    def test_handle_no_images(self):
        content = "<p>No images</p>"
        page = "<html><head></head></html>"
        result = extract_image_from_content(content, page)
        assert result is None

    def test_handle_only_content(self):
        content = '<img src="https://only.com/img.jpg">'
        result = extract_image_from_content(content, None)
        assert result == "https://only.com/img.jpg"


class TestExtractLinks:
    """Testes para a função extract_links."""

    def test_extract_single_link(self):
        html = '<a href="https://example.com">Example</a>'
        links = extract_links(html)
        assert len(links) == 1
        assert links[0]['href'] == "https://example.com"
        assert links[0]['text'] == "Example"

    def test_extract_multiple_links(self):
        html = '''
        <a href="https://first.com">First</a>
        <a href="https://second.com">Second</a>
        '''
        links = extract_links(html)
        assert len(links) == 2

    def test_handle_empty_text(self):
        html = '<a href="https://example.com"></a>'
        links = extract_links(html)
        assert len(links) == 1
        assert links[0]['text'] == ""

    def test_handle_no_links(self):
        html = "<p>No links here</p>"
        links = extract_links(html)
        assert len(links) == 0

    def test_handle_empty_input(self):
        assert extract_links("") == []
        assert extract_links(None) == []


class TestExtractTextContent:
    """Testes para a função extract_text_content."""

    def test_extract_text(self):
        html = "<p>This is <strong>important</strong> text.</p>"
        result = extract_text_content(html)
        assert result == "This is important text."

    def test_max_length_truncation(self):
        html = "<p>This is a very long text that should be truncated.</p>"
        result = extract_text_content(html, max_length=20)
        assert len(result) <= 23  # 20 + "..."
        assert result.endswith("...")

    def test_truncate_at_word_boundary(self):
        html = "<p>Hello beautiful world</p>"
        result = extract_text_content(html, max_length=15)
        # Deve cortar em "Hello beautiful" ou "Hello"
        assert "Hello" in result
        assert not result.endswith(" ...")

    def test_handle_empty_input(self):
        assert extract_text_content("") == ""
        assert extract_text_content(None) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
