"""Curadoria: publica só as notícias de maior impacto para o mercado.

Fluxo de cada rodada (cron a cada 2h):
1. Candidatas: notícias das últimas CANDIDATE_HOURS horas que passaram no
   filtro de palavras-chave (priority_score) e ainda não foram avaliadas.
2. Triagem (Claude): nota de impacto de mercado 0-10 para cada uma, agrupando
   a mesma história de fontes diferentes e evitando repetir o que já saiu nas
   últimas 24h.
3. Publica no máximo PER_RUN por rodada e DAILY_MAX por dia, só com impacto
   >= MIN_IMPACT. Rodada calma não publica nada.
4. Artigo (Claude; Gemini grátis como reserva) em PT e EN, estruturado para
   decisão: o que aconteceu, por que importa, impacto por classe de ativo, o que
   acompanhar, cenários. Saída via tool use: o JSON sempre vem completo.
5. Checagem de qualidade: se falhar, o post vira rascunho em vez de publicar.

Todas as candidatas avaliadas entram em processing_queue (completed/skipped/
error), então nenhuma é reavaliada nem paga duas vezes.
"""

import json
import os
import re
import time

import requests

from utils import logger

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

MIN_IMPACT = int(os.getenv("CURATOR_MIN_IMPACT", "7"))
PER_RUN = int(os.getenv("CURATOR_PER_RUN", "2"))
DAILY_MAX = int(os.getenv("CURATOR_DAILY_MAX", "12"))
CANDIDATE_HOURS = int(os.getenv("CURATOR_CANDIDATE_HOURS", "6"))
CANDIDATE_MIN_SCORE = float(os.getenv("CURATOR_MIN_SCORE", "4.0"))
CANDIDATE_LIMIT = int(os.getenv("CURATOR_CANDIDATE_LIMIT", "60"))

MIN_CHARS_PT = 2500
MIN_CHARS_EN = 2000
MIN_SECTIONS = 3

# ─── LLM calls ───────────────────────────────────────────────


class LLMError(Exception):
    pass


def claude_tool(system: str, user: str, tool: dict, max_tokens: int) -> dict:
    """Call Claude forcing one tool: the tool input is the structured answer."""
    if not ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY não configurada")
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
    }
    last = None
    for attempt in range(3):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=120, headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
        except requests.RequestException as e:
            last = f"{type(e).__name__}"
        else:
            if r.status_code == 200:
                data = r.json()
                if data.get("stop_reason") == "max_tokens":
                    raise LLMError("resposta cortada (max_tokens)")
                for block in data.get("content", []):
                    if block.get("type") == "tool_use":
                        usage = data.get("usage", {})
                        logger.info(f"  [claude] tokens in={usage.get('input_tokens')} out={usage.get('output_tokens')}")
                        return block["input"]
                raise LLMError("resposta sem tool_use")
            last = f"HTTP {r.status_code}: {r.text[:150]}"
            if r.status_code not in (429, 500, 502, 503, 529):
                break
        time.sleep(5 * (attempt + 1))
    raise LLMError(f"Claude falhou: {last}")


def _gemini_schema(schema: dict) -> dict:
    """JSON Schema → subset accepted by Gemini responseSchema."""
    out = {k: v for k, v in schema.items() if k in ("type", "properties", "items", "required", "enum", "description")}
    if "properties" in out:
        out["properties"] = {k: _gemini_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _gemini_schema(out["items"])
    return out


def gemini_json(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY não configurada")
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens,
                                     "responseMimeType": "application/json",
                                     "responseSchema": _gemini_schema(schema)},
            },
            timeout=120,
        )
    except requests.RequestException as e:
        raise LLMError(f"Gemini: {type(e).__name__}")
    if r.status_code != 200:
        raise LLMError(f"Gemini HTTP {r.status_code}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Gemini resposta inválida: {type(e).__name__}")


def structured(system: str, user: str, tool: dict, max_tokens: int) -> tuple[dict, str]:
    """Claude first, Gemini (free) as backup. Returns (answer, provider)."""
    errors = []
    try:
        return claude_tool(system, user, tool, max_tokens), "claude"
    except LLMError as e:
        errors.append(str(e))
        logger.warning(f"  [claude] {str(e)[:120]}")
    try:
        return gemini_json(system, user, tool["input_schema"], max_tokens), "gemini"
    except LLMError as e:
        errors.append(str(e))
        logger.warning(f"  [gemini] {str(e)[:120]}")
    raise LLMError(" | ".join(errors))


# ─── triage ──────────────────────────────────────────────────

TRIAGE_SYSTEM = """Você é o editor-chefe de uma mesa de análise macro para investidores.
Sua tarefa: dar a cada manchete uma nota de IMPACTO DE MERCADO de 0 a 10.

Escala:
- 9-10: move vários mercados globais agora (decisão/sinalização clara de banco central relevante,
  surpresa grande em CPI/payroll/PIB dos EUA, choque de petróleo, crise de crédito/bancária,
  default soberano, sanção ou guerra com efeito direto em commodities).
- 7-8: relevante para preços de uma classe de ativo importante (juros, dólar, bolsas,
  commodities, cripto, Brasil) ou muda expectativas de política monetária.
- 4-6: contexto útil, efeito pequeno ou local.
- 0-3: rotina, agenda, resumos de sessão, circulares administrativas, opinião sem fato novo.

Regras:
- Valorize FATO NOVO e SURPRESA vs o esperado; previews e "o que observar hoje" valem pouco.
- Agrupe a mesma história de fontes diferentes com o MESMO valor em "story" (chave curta em inglês,
  ex.: "fed-logan-hikes"); avalie a melhor versão e dê nota baixa às demais.
- Se a história já foi publicada nas últimas 24h (lista abaixo), só dê nota alta se houver fato novo relevante.
- Devolva apenas itens com nota >= 5."""

TRIAGE_TOOL = {
    "name": "rank_news",
    "description": "Notas de impacto de mercado das manchetes candidatas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "impact": {"type": "integer", "description": "0-10"},
                        "story": {"type": "string", "description": "chave curta da história"},
                        "assets": {"type": "array", "items": {"type": "string"}},
                        "why": {"type": "string", "description": "uma frase"},
                    },
                    "required": ["id", "impact", "story", "why"],
                },
            }
        },
        "required": ["items"],
    },
}


def build_triage_prompt(candidates: list[dict], recent_titles: list[str]) -> str:
    lines = ["MANCHETES CANDIDATAS (id | fonte | título | resumo):"]
    for c in candidates:
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c.get("description") or "")).strip()[:200]
        lines.append(f"{c['id']} | {c['source_name']} | {c['title']} | {desc}")
    lines.append("")
    lines.append("JÁ PUBLICADO NAS ÚLTIMAS 24H:")
    lines += [f"- {t}" for t in recent_titles] or ["- (nada)"]
    return "\n".join(lines)


def select_for_publication(ranked: list[dict], valid_ids: set, slots: int,
                           min_impact: int = MIN_IMPACT) -> list[dict]:
    """Highest impact first, one per story, only ids we sent, at most ``slots``."""
    out, seen = [], set()
    for item in sorted(ranked, key=lambda x: -int(x.get("impact", 0))):
        if len(out) >= slots:
            break
        story = (item.get("story") or "").strip().lower()
        if item.get("id") not in valid_ids or int(item.get("impact", 0)) < min_impact or story in seen:
            continue
        seen.add(story)
        out.append(item)
    return out


# ─── article ─────────────────────────────────────────────────

ARTICLE_SYSTEM = """Você é analista macro sênior escrevendo para investidores brasileiros que tomam
decisões com base no texto. Escreva em português do Brasil impecável e, separadamente, em inglês.

PRECISÃO (crítico):
- Use SOMENTE fatos presentes na notícia de referência. Não invente números, datas, citações ou nomes.
- Se um detalhe não está na fonte, não o afirme; contextualize de forma geral e sinalize a incerteza.
- Impactos de mercado são análise: explique o MECANISMO (por que o ativo tende a reagir assim)
  e use linguagem condicional ("tende a", "pode").

ESTRUTURA do content_pt em Markdown (títulos com ##, 450-700 palavras):
## O que aconteceu
## Por que importa
## Impacto nos mercados
   (lista com as classes RELEVANTES apenas: **Juros/Treasuries**, **Dólar e câmbio**, **Bolsas**,
   **Commodities**, **Cripto**, **Brasil**: direção provável e o porquê)
## O que acompanhar
   (próximos dados, decisões ou eventos que confirmam ou invalidam a leitura)
## Cenários
   (cenário base e cenário de risco, em poucas linhas)
Última linha: "*Fonte original: {fonte}. Conteúdo informativo, não é recomendação de investimento.*"

content_en: o mesmo artigo em inglês natural (mesma estrutura, títulos em inglês: What happened,
Why it matters, Market impact, What to watch, Scenarios), última linha
"*Original source: {fonte}. For information only, not investment advice.*"

ESTILO: título original e específico (não traduza o título da fonte), sem sensacionalismo,
politicamente imparcial (foco só em consequências econômicas; termos neutros), não copie frases da fonte.
summary_pt/summary_en: 2 frases com a conclusão para o investidor. tags: 3-6, em português."""

ARTICLE_TOOL = {
    "name": "publish_article",
    "description": "Artigo final em PT e EN.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title_pt": {"type": "string"},
            "summary_pt": {"type": "string"},
            "content_pt": {"type": "string"},
            "title_en": {"type": "string"},
            "summary_en": {"type": "string"},
            "content_en": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title_pt", "summary_pt", "content_pt", "title_en", "summary_en", "content_en", "tags"],
    },
}


def build_article_prompt(news: dict, triage: dict) -> str:
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", f"{news.get('description') or ''} {news.get('content') or ''}")).strip()
    return (
        f"NOTÍCIA DE REFERÊNCIA\nFonte: {news['source_name']}\nTítulo: {news['title']}\n"
        f"Publicada: {news.get('published_at') or 'n/d'}\nConteúdo: {body[:4000]}\n\n"
        f"Leitura do editor: impacto {triage.get('impact')}/10, ativos: "
        f"{', '.join(triage.get('assets') or []) or 'n/d'}. {triage.get('why', '')}\n\n"
        f"Escreva o artigo. Fonte para a linha final: {news['source_name']}."
    )


_PT_MARKERS = re.compile(r"\b(que|não|para|com|uma|são|também|está|mercado|juros|dólar)\b", re.I)
_FOREIGN_IN_PT = re.compile(r"\b(the|and|of|los|las|del|inversores|partnership|however)\b", re.I)


def quality_problems(a: dict) -> list[str]:
    """Reasons to hold an article as draft (empty list = publish)."""
    problems = []
    for k in ARTICLE_TOOL["input_schema"]["required"]:
        if not a.get(k):
            problems.append(f"campo vazio: {k}")
    pt, en = a.get("content_pt") or "", a.get("content_en") or ""
    if len(pt) < MIN_CHARS_PT:
        problems.append(f"content_pt curto ({len(pt)})")
    if len(en) < MIN_CHARS_EN:
        problems.append(f"content_en curto ({len(en)})")
    if len(re.findall(r"^## ", pt, re.M)) < MIN_SECTIONS:
        problems.append("content_pt sem a estrutura de seções")
    words = max(len(pt.split()), 1)
    if len(_PT_MARKERS.findall(pt)) / words < 0.04:
        problems.append("content_pt não parece português")
    if len(_FOREIGN_IN_PT.findall(pt)) / words > 0.01:
        problems.append("content_pt com palavras em outro idioma")
    if a.get("title_pt") and _FOREIGN_IN_PT.search(a["title_pt"]):
        problems.append("título PT com palavra em outro idioma")
    return problems


# ─── DB ──────────────────────────────────────────────────────

def _rows(sql: str, params=()) -> list[dict]:
    from psycopg2.extras import RealDictCursor
    from database_supabase import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_candidates() -> list[dict]:
    return _rows("""
        SELECT n.id, n.title, n.description, n.content, n.link, n.published_at, n.priority_score,
               s.name AS source_name, s.category
        FROM news n
        JOIN sources s ON s.id = n.source_id
        LEFT JOIN processing_queue pq ON pq.news_id = n.id
        WHERE n.fetched_at > NOW() - make_interval(hours => %s)
          AND n.priority_score >= %s
          AND pq.id IS NULL
        ORDER BY n.priority_score DESC, n.published_at DESC NULLS LAST
        LIMIT %s
    """, (CANDIDATE_HOURS, CANDIDATE_MIN_SCORE, CANDIDATE_LIMIT))


def recent_titles(hours: int = 24) -> list[str]:
    return [r["title_pt"] for r in _rows(
        "SELECT title_pt FROM blog_posts WHERE created_at > NOW() - make_interval(hours => %s) "
        "ORDER BY created_at DESC LIMIT 40", (hours,))]


def published_today() -> int:
    return _rows("SELECT COUNT(*) AS n FROM blog_posts WHERE created_at >= date_trunc('day', NOW()) "
                 "AND status = 'published'")[0]["n"]


def mark(news_ids: list[int], status: str, message: str | None = None) -> None:
    from database_supabase import get_connection
    if not news_ids:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        for nid in news_ids:
            # Candidates never have a queue row yet (see get_candidates), and each
            # one is marked exactly once per run.
            cur.execute("""INSERT INTO processing_queue (news_id, status, error_message, processed_at)
                           VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""", (nid, status, message))
        conn.commit()
    finally:
        conn.close()


# ─── run ─────────────────────────────────────────────────────

def run(dry_run: bool = False) -> dict:
    stats = {"candidates": 0, "ranked": 0, "published": 0, "drafts": 0, "errors": 0}
    slots = min(PER_RUN, DAILY_MAX - published_today())
    logger.info(f"[curator] vagas nesta rodada: {slots} (máx {PER_RUN}/rodada, {DAILY_MAX}/dia)")
    if slots <= 0:
        return stats
    candidates = get_candidates()
    stats["candidates"] = len(candidates)
    if not candidates:
        logger.info("[curator] nenhuma candidata nova")
        return stats

    try:
        ranked, provider = structured(TRIAGE_SYSTEM, build_triage_prompt(candidates, recent_titles()),
                                      TRIAGE_TOOL, 2000)
    except LLMError as e:
        logger.error(f"[curator] triagem falhou: {e}")
        stats["errors"] += 1
        return stats  # candidates stay unmarked: next run retries them
    items = ranked.get("items") or []
    stats["ranked"] = len(items)
    by_id = {c["id"]: c for c in candidates}
    chosen = select_for_publication(items, set(by_id), slots)
    for it in sorted(items, key=lambda x: -int(x.get("impact", 0)))[:8]:
        logger.info(f"  {it.get('impact'):>2} [{it.get('story')}] {by_id.get(it.get('id'), {}).get('title', '?')[:80]}")
    logger.info(f"[curator] triagem via {provider}: {len(items)} com nota >= 5, {len(chosen)} escolhidas")
    if dry_run:
        return stats

    chosen_ids = {c["id"] for c in chosen}
    impact = {int(i["id"]): int(i.get("impact", 0)) for i in items if isinstance(i.get("id"), int)}
    mark([c["id"] for c in candidates if c["id"] not in chosen_ids], "skipped", None)

    from database_blog import save_blog_post
    from processor import extract_image_from_content
    for item in chosen:
        news = by_id[item["id"]]
        logger.info(f"[curator] escrevendo ({item['impact']}/10): {news['title'][:80]}")
        try:
            art, provider = structured(ARTICLE_SYSTEM, build_article_prompt(news, item), ARTICLE_TOOL, 6000)
        except LLMError as e:
            logger.error(f"  artigo falhou: {str(e)[:150]}")
            mark([news["id"]], "error", str(e)[:500])
            stats["errors"] += 1
            continue
        problems = quality_problems(art)
        status = "draft" if problems else "published"
        post_id = save_blog_post(
            news_id=news["id"], title_pt=art["title_pt"], content_pt=art["content_pt"],
            title_en=art["title_en"], content_en=art["content_en"],
            summary_pt=art["summary_pt"], summary_en=art["summary_en"],
            image_url=extract_image_from_content(news.get("content") or "", news["link"]),
            source_url=news["link"], source_name=news["source_name"], category=news["category"],
            tags=art.get("tags") or [], priority_score=float(impact.get(news["id"], item["impact"])),
            status=status,
        )
        mark([news["id"]], "completed", "; ".join(problems) or None)
        if problems:
            stats["drafts"] += 1
            logger.warning(f"  post #{post_id} salvo como RASCUNHO ({provider}): {'; '.join(problems)}")
        else:
            stats["published"] += 1
            logger.info(f"  post #{post_id} publicado ({provider})")
    logger.info(f"[curator] fim: {stats}")
    return stats


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Curadoria de notícias de alto impacto para o blog")
    p.add_argument("command", choices=["run", "dry-run"])
    args = p.parse_args()
    run(dry_run=args.command == "dry-run")
