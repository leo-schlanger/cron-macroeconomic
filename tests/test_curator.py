"""Curadoria: triagem, seleção, qualidade e chamadas estruturadas (sem rede)."""

import pytest

import curator


def item(i, impact, story):
    return {"id": i, "impact": impact, "story": story, "why": "x"}


# ─── seleção ─────────────────────────────────────────────────

def test_selects_highest_impact_one_per_story_within_slots():
    ranked = [item(1, 7, "fed-logan"), item(2, 9, "payrolls"), item(3, 8, "fed-logan"),
              item(4, 6, "oil"), item(5, 10, "payrolls")]
    got = curator.select_for_publication(ranked, {1, 2, 3, 4, 5}, slots=2, min_impact=7)
    assert [g["id"] for g in got] == [5, 3]          # best of each story, highest first


def test_ties_go_to_the_stronger_prefilter_score():
    ranked = [item(1, 7, "hedge-funds"), item(2, 7, "oil-supply"), item(3, 7, "france-bonds")]
    got = curator.select_for_publication(ranked, {1, 2, 3}, slots=2, min_impact=7,
                                         prefilter={1: 6.0, 2: 14.6, 3: 15.0})
    assert [g["id"] for g in got] == [3, 2]


def test_quiet_run_publishes_nothing_and_ignores_unknown_ids():
    assert curator.select_for_publication([item(1, 6, "a")], {1}, slots=2, min_impact=7) == []
    assert curator.select_for_publication([item(99, 10, "a")], {1}, slots=2, min_impact=7) == []
    assert curator.select_for_publication([item(1, 9, "a")], {1}, slots=0, min_impact=7) == []


# ─── qualidade ───────────────────────────────────────────────

PT = ("## O que aconteceu\n" + "O Fed sinalizou que os juros podem subir mais, e o mercado reagiu com alta do dólar. " * 12 +
      "\n## Por que importa\n" + "Isso muda as expectativas para a política monetária e para a curva de juros. " * 12 +
      "\n## Impacto nos mercados\n" + "- **Dólar e câmbio**: tende a se fortalecer com juros mais altos nos EUA. " * 8 +
      "\n## O que acompanhar\n- Payroll e CPI.\n## Cenários\nBase e risco.\n"
      "*Fonte original: X. Conteúdo informativo, não é recomendação de investimento.*")
EN = ("## What happened\n" + "The Fed signalled that rates may rise further and the dollar rallied. " * 30 +
      "\n## Why it matters\n## Market impact\n## What to watch\n## Scenarios\n")
GOOD = {"title_pt": "Fed indica mais altas de juros e dólar sobe", "summary_pt": "s", "content_pt": PT,
        "title_en": "Fed signals more hikes", "summary_en": "s", "content_en": EN, "tags": ["fed"]}


def test_good_article_passes():
    assert curator.quality_problems(GOOD) == []


def test_short_unstructured_or_mixed_language_becomes_draft():
    assert any("curto" in p for p in curator.quality_problems(dict(GOOD, content_pt="## a\ncurto")))
    flat = PT.replace("## ", "")
    assert "content_pt sem a estrutura de seções" in curator.quality_problems(dict(GOOD, content_pt=flat))
    mixed = PT + " the market and the investors of the world los inversores del mercado" * 3
    assert "content_pt com palavras em outro idioma" in curator.quality_problems(dict(GOOD, content_pt=mixed))
    # the exact defects seen in production titles
    assert curator.quality_problems(dict(GOOD, title_pt="Influxo de Inversores Institucionais"))
    assert curator.quality_problems(dict(GOOD, title_pt="Partnership para Crescimento Privado"))
    # false positives found in the audit of real posts
    for ok in ("Juros podem subir após autoridades europeias afirmarem que a guerra pode forçá-los a agir",
               "Investigação sobre plano em Punta del Este preocupa mercados argentinos",
               "Bank of Japan eleva juros pela primeira vez em décadas"):
        assert not any("título" in p for p in curator.quality_problems(dict(GOOD, title_pt=ok))), ok
    assert "campo vazio: summary_en" in curator.quality_problems(dict(GOOD, summary_en=""))


# ─── prompts ─────────────────────────────────────────────────

def test_triage_prompt_strips_html_and_lists_recent():
    p = curator.build_triage_prompt(
        [{"id": 7, "source_name": "FT", "title": "Fed holds", "description": "<p>Rates <b>unchanged</b></p>"}],
        ["Fed mantém juros"])
    assert "7 | FT | Fed holds | Rates unchanged" in p and "- Fed mantém juros" in p


def test_article_prompt_carries_editor_read_and_source():
    p = curator.build_article_prompt({"source_name": "Bloomberg", "title": "T", "description": "d", "content": "<i>c</i>"},
                                     {"impact": 9, "assets": ["juros", "dólar"], "why": "surpresa"})
    assert "impacto 9/10" in p and "juros, dólar" in p and "Fonte para a linha final: Bloomberg" in p
    assert "<i>" not in p


# ─── chamadas estruturadas ───────────────────────────────────

class Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        return self._data


def test_claude_tool_returns_tool_input_and_retries_overload(monkeypatch):
    monkeypatch.setattr(curator, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(curator.time, "sleep", lambda s: None)
    calls = []
    answers = [Resp(529, text="overloaded"),
               Resp(200, {"stop_reason": "tool_use", "usage": {},
                          "content": [{"type": "tool_use", "input": {"items": []}}]})]
    monkeypatch.setattr(curator.requests, "post", lambda *a, **k: calls.append(k) or answers.pop(0))
    assert curator.claude_tool("s", "u", curator.TRIAGE_TOOL, 100) == {"items": []}
    assert len(calls) == 2 and calls[0]["json"]["tool_choice"]["name"] == "rank_news"


def test_claude_truncated_answer_is_an_error(monkeypatch):
    monkeypatch.setattr(curator, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(curator.requests, "post", lambda *a, **k: Resp(200, {"stop_reason": "max_tokens", "content": []}))
    with pytest.raises(curator.LLMError, match="cortada"):
        curator.claude_tool("s", "u", curator.ARTICLE_TOOL, 100)


def test_free_chain_routes_triage_to_lite_and_articles_to_flash(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.setattr(curator, k, None)
    monkeypatch.setattr(curator, "GEMINI_API_KEY", "g")
    assert [n for n, _ in curator.provider_chain("triage")] == ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    assert [n for n, _ in curator.provider_chain("article")] == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    monkeypatch.setattr(curator, "GROQ_API_KEY", "q")
    monkeypatch.setattr(curator, "OPENROUTER_API_KEY", "o")
    names = [n for n, _ in curator.provider_chain("article")]
    assert names[0].startswith("openrouter:") and names[-1].startswith("groq:")


def test_openai_compatible_tool_call(monkeypatch):
    seen = {}

    def post(url, **k):
        seen.update(url=url, body=k["json"], auth=k["headers"]["Authorization"])
        return Resp(200, {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
            {"function": {"name": "rank_news", "arguments": '{"items": []}'}}]}}]})
    monkeypatch.setattr(curator.requests, "post", post)
    out = curator.openai_compat_tool("https://api.groq.com/openai/v1", "q", "llama", "s", "u", curator.TRIAGE_TOOL, 100)
    assert out == {"items": []} and seen["url"].endswith("/chat/completions") and seen["auth"] == "Bearer q"
    assert seen["body"]["tool_choice"]["function"]["name"] == "rank_news"
    monkeypatch.setattr(curator.requests, "post", lambda *a, **k: Resp(200, {"choices": [{"finish_reason": "length", "message": {}}]}))
    with pytest.raises(curator.LLMError, match="cortada"):
        curator.openai_compat_tool("u", "q", "m", "s", "u", curator.TRIAGE_TOOL, 10)


def test_falls_back_to_gemini_with_key_in_header(monkeypatch):
    monkeypatch.setattr(curator, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(curator, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(curator, "GROQ_API_KEY", None)
    monkeypatch.setattr(curator, "GEMINI_API_KEY", "g")
    seen = {}

    def post(url, **k):
        seen.update(url=url, headers=k["headers"], schema=k["json"]["generationConfig"]["responseSchema"])
        return Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"items": []}'}]}}]})
    monkeypatch.setattr(curator.requests, "post", post)
    out, provider = curator.structured("s", "u", curator.TRIAGE_TOOL, 100)
    assert out == {"items": []} and provider == "gemini-2.5-flash"
    assert "key=" not in seen["url"] and seen["headers"]["x-goog-api-key"] == "g"
    assert "description" not in str(seen["schema"].get("properties", {}).get("items", {}).get("description", ""))


def test_no_provider_raises(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.setattr(curator, k, None)
    with pytest.raises(curator.LLMError):
        curator.structured("s", "u", curator.TRIAGE_TOOL, 100)


# ─── rodada ──────────────────────────────────────────────────

def test_run_respects_daily_cap_and_marks_everything(monkeypatch):
    marks, saved = [], []
    monkeypatch.setattr(curator, "published_today", lambda: 11)          # 1 slot left of 12
    monkeypatch.setattr(curator, "get_candidates", lambda: [
        {"id": 1, "title": "Payrolls surprise", "source_name": "FT", "category": "macro_global", "link": "l1"},
        {"id": 2, "title": "Fed speaker", "source_name": "FT", "category": "central_banks", "link": "l2"},
        {"id": 3, "title": "Agenda do dia", "source_name": "Valor", "category": "brazil", "link": "l3"}])
    monkeypatch.setattr(curator, "recent_titles", lambda: [])
    monkeypatch.setattr(curator, "mark", lambda ids, status, msg=None: marks.append((sorted(ids), status)))

    monkeypatch.setattr(curator, "structured",
                        lambda *a, **k: ({"items": [item(1, 9, "nfp"), item(2, 8, "fed")]}, "gemini-2.5-flash-lite"))
    monkeypatch.setattr(curator, "provider_chain", lambda task: [("gemini-2.5-flash", lambda *a: GOOD)])
    monkeypatch.setattr("database_blog.save_blog_post", lambda **k: saved.append(k) or 101)
    monkeypatch.setattr("processor.extract_image_from_content", lambda c, l: None)
    stats = curator.run()
    assert stats["published"] == 1 and saved[0]["news_id"] == 1 and saved[0]["status"] == "published"
    assert saved[0]["priority_score"] == 9.0
    assert ([2, 3], "skipped") in marks and ([1], "completed") in marks


def test_quality_failure_tries_next_provider_then_keeps_best_draft(monkeypatch):
    english_title = dict(GOOD, title_pt="Eurozone inflation hits three-year high",
                         title_en="Eurozone inflation hits three-year high")
    calls = []

    def chain(task):
        return [("gemini-2.5-flash", lambda *a: calls.append("flash") or english_title),
                ("groq:gpt-oss", lambda *a: calls.append("groq") or GOOD)]
    monkeypatch.setattr(curator, "provider_chain", chain)
    art, provider, problems = curator.write_article({"source_name": "FT", "title": "t"}, item(1, 8, "x"))
    assert calls == ["flash", "groq"] and provider == "groq:gpt-oss" and problems == []

    short = dict(GOOD, content_pt="## a\ncurto")
    one_problem = dict(GOOD, title_pt="Eurozone inflation three-year high", title_en="Eurozone inflation three-year high")
    assert len(curator.quality_problems(one_problem)) == 1
    monkeypatch.setattr(curator, "provider_chain", lambda task: [("a", lambda *a: short), ("b", lambda *a: one_problem)])
    art, provider, problems = curator.write_article({"source_name": "FT", "title": "t"}, item(1, 8, "x"))
    assert provider == "b" and len(problems) == 1          # fewest problems kept for the draft


def test_run_with_full_day_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(curator, "published_today", lambda: 12)
    monkeypatch.setattr(curator, "structured", lambda *a: pytest.fail("LLM chamado sem vaga"))
    assert curator.run()["published"] == 0
