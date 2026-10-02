"""Pre-filter regressions from a 48h audit of real headlines (Oct/2026)."""

import pytest

from scoring import score_headline

PASS = 6.0  # curator CANDIDATE_MIN_SCORE


@pytest.mark.parametrize("title", [
    "US 10-year yield jumps to 5.34% as global bond rout pushes borrowing costs higher",
    "Why Bond Yields Are Climbing All Over the World",
    "Ibovespa, real e juros futuros pioram com disparada do petróleo",
    "Dax aktuell: Dax dreht ins Minus – Ölpreis über 100 Dollar",
    "Crude oil exports from strait of Hormuz largely return to pre-war levels",
    "Bond selloff could mean outsized portfolio changes at quarter’s end",
    "Copom eleva a Selic para 15,25% e sinaliza novas altas",
    "IPCA de setembro sobe 0,6% e supera projeções",
    "Fed’s Logan says more rate hikes needed to curb sticky inflation",
    "Tokyo core inflation jumps in September, bolsters case for more BOJ hikes",
    "Bitcoin cai com juros dos títulos do Tesouro dos EUA na máxima desde 2002",
    "Produção de petróleo do Brasil bate recorde pelo 3º mês consecutivo em agosto",
])
def test_market_moving_headlines_reach_triage(title):
    score, _ = score_headline(title)
    assert score >= PASS, (score, title)


@pytest.mark.parametrize("title", [
    "Directions under Section 35A read with Section 56 of the Banking Regulation Act, 1949",
    "Interesting stocks today as October month starts",
    "What are the main events for today?",
    "Joby Aviation stock hits 52-week low at $5.93",
    "Susquehanna raises Accenture stock price target on strong bookings",
    "KFC CEO Scott Mezvinsky sells $65,869 in Yum Brands stock",
    "Which inflation report matters most to markets? CPI vs PCE vs PPI explained",
    "Top 5 meme coins to buy before the next 1000x pump",
    "Real estate agents share home staging tips",
])
def test_noise_stays_out(title):
    score, _ = score_headline(title)
    assert score < PASS, (score, title)


def test_whole_words_only():
    assert score_headline("CMA CGM finalizes acquisition of FedEx unit")[1] == []
    assert "sec" not in score_headline("Second-quarter sector review of securities")[1]
    assert "ban" not in score_headline("Bank holiday in Bangladesh")[1]


def test_conflict_news_with_market_impact_is_not_discarded():
    score, matched = score_headline("Strike on tanker kills crew, oil jumps 6% as Hormuz risk rises")
    assert score >= PASS and "oil" in matched


def test_source_weight_and_title_bonus():
    a, _ = score_headline("Markets wait", "Fed signals a pause in rate hikes")
    b, _ = score_headline("Fed signals a pause in rate hikes")
    assert b > a
    assert score_headline("Fed signals a pause", source_weight=2.0)[0] == 2 * score_headline("Fed signals a pause")[0]
