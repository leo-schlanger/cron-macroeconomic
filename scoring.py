"""Market-impact pre-filter (keyword score) for fetched headlines.

This is only the first sieve: it decides which headlines are worth sending
to the LLM triage (curator.py), so it must favour RECALL of market-moving
news and cut obvious noise cheaply.

Design (fixes measured on 48h of real data, Oct/2026):
- Whole-word matching. Plain substring matching made "sec" match "section",
  "ban" match "bank", "fed" match "FedEx": 82% of approved headlines only
  passed because of such accidents.
- Weighted tiers: a central-bank decision or a CPI surprise is not worth the
  same as the word "legal".
- Coverage of what actually moves prices: yields, oil, FX, gold, equity
  indices, crypto majors, and Brazil (Selic, Copom, IPCA, Ibovespa...).
- Noise patterns (single-stock trivia, insider sales, crypto spam) subtract.
- Conflict/violence words no longer discard a headline: wars move oil and
  risk assets. Neutral writing is enforced in the article prompt instead.

Score = strongest term + ½ second + ¼ third (each ×2 when in the title),
minus noise penalties, × source weight. Diminishing returns on purpose: a
session wrap or an explainer mentions every market term but is not news.
"""

from __future__ import annotations

import re

TIERS: dict[float, list[str]] = {
    # Decisions and data that move several markets at once.
    3.0: [
        "fomc", "federal reserve", "fed", "powell", "rate decision", "rate hike", "rate hikes", "rate cut", "rate cuts",
        "hikes rates", "cuts rates", "holds rates", "raises rates", "lowers rates",
        "ecb", "lagarde", "bank of japan", "boj", "ueda", "bank of england", "boe", "pboc", "snb", "rba", "rbnz",
        "copom", "selic", "galípolo", "banco central do brasil", "bcb", "bce", "ezb",
        "cpi", "core inflation", "inflation", "inflação", "ipca", "pce", "ppi",
        "nonfarm", "non-farm", "payrolls", "payroll", "jobs report", "unemployment rate", "caged",
        "gdp", "pib", "recession", "recessão", "stagflation", "estagflação",
        "treasury yields", "treasuries", "títulos do tesouro", "tesouro dos eua", "tesouro americano",
        "treasury bonds", "gilts", "bunds", "jgb", "jgbs", "bond yields", "10-year yield", "yields", "yield", "bond rout",
        "bond selloff", "bond sell-off", "juros futuros", "curva de juros", "yield curve",
        "oil", "crude", "brent", "wti", "opec", "opep", "petróleo", "ölpreis",
        "default", "sovereign default", "banking crisis", "crise bancária", "bank run", "credit crunch",
        "debt ceiling", "teto da dívida", "downgrade", "rebaixamento",
        "tariff", "tariffs", "tarifa", "tarifas", "trade war", "guerra comercial", "sanctions", "sanções", "embargo",
        "strait of hormuz", "hormuz",
    ],
    # Prices and policy of a major asset class.
    2.0: [
        "dollar", "dólar", "dxy", "euro", "yen", "yuan", "renminbi", "real", "currency", "câmbio", "fx",
        "gold", "ouro", "silver", "copper", "natural gas", "lng", "gasolina", "diesel", "commodities",
        "ibovespa", "s&p 500", "nasdaq", "dow jones", "stocks", "equities", "wall street", "bolsa", "bolsas",
        "dax", "nikkei", "hang seng", "stoxx",
        "bitcoin", "btc", "ether", "ethereum", "spot etf", "etf flows", "etf inflows", "etf outflows", "stablecoin",
        "pmi", "ism", "retail sales", "vendas no varejo", "consumer confidence", "wage growth", "jobless claims",
        "fiscal", "deficit", "déficit", "arcabouço fiscal", "budget", "orçamento", "debt", "dívida pública",
        "credit spread", "spreads", "high yield", "junk bonds",
        "imf", "fmi", "world bank", "g7", "g20", "brics",
        "selloff", "sell-off", "rout", "crash", "plunge", "plunges", "tumble", "tumbles", "surge", "surges",
        "soars", "record high", "all-time high", "máxima histórica", "disparada", "derrete",
        "quantitative easing", "quantitative tightening", "qe", "qt", "balance sheet", "liquidity", "liquidez",
        "monetary policy", "política monetária", "forward guidance", "basis points", "pontos-base", "pontos base",
        "sec", "cftc", "regulation", "regulação", "capital controls", "capital flight",
        "supply shock", "supply chain", "cadeia de suprimentos", "shipping", "freight",
    ],
    # Context: relevant, smaller or slower effect.
    1.0: [
        "central bank", "banco central", "interest rate", "interest rates", "taxa de juros", "juros",
        "housing starts", "durable goods", "industrial production", "produção industrial", "trade deficit",
        "trade surplus", "current account", "conta corrente", "emerging markets", "emerging market",
        "mercados emergentes", "credit rating", "rating", "bankruptcy", "falência", "recuperação judicial",
        "ipo", "earnings", "guidance", "blackrock", "microstrategy", "strategy inc", "coinbase", "binance",
        "tether", "usdc", "cbdc", "halving", "institutional", "haddad", "eleição", "eleições", "election",
        "stimulus", "estímulo", "austerity", "austeridade", "vix", "volatility", "volatilidade",
        "de-dollarization", "petrodollar", "energy crisis", "crise energética", "opec+",
    ],
}

# Subtract: noise that keyword lists catch but no macro reader needs.
NOISE: list[tuple[str, float]] = [
    (r"52-week (low|high)", 6.0),
    (r"price target", 4.0),
    (r"\b(sells|buys|sold|bought) \$[\d,.]+ (in|of) .{0,40}stock", 6.0),
    (r"options flow", 4.0),
    (r"stocks? to watch", 3.0),
    (r"trader'?s guide|how to trade|what is (a|an) ", 4.0),
    (r"technical analysis|análise técnica|price prediction|previsão de preço", 4.0),
    (r"\b(meme ?coins?|shitcoin|airdrop|giveaway|1000x|nft drop|pepe|shiba)\b", 8.0),
    (r"^(interesting stocks|what are the main events|agenda do dia|reminder:)", 6.0),
    (r"\b(webinar|podcast|sponsored|patrocinado)\b", 4.0),
    # Recaps and evergreen explainers: everything in them already happened or is not news.
    (r"\b(news wrap|session wrap|market wrap|market news:|weekly recap|resumo do dia|fechamento:)", 4.0),
    (r"\bexplained\b|\bwhy .{0,40}\bmatters?\b|\bhow .{0,40}\bworks?\b|\bguide\b|\bentenda\b", 5.0),
    # Administrative circulars from central banks/regulators.
    (r"directions? under section|master direction|\(amendment\)|notification no|circular no|press release:? .{0,20}auction", 8.0),
]

_COMPILED = {w: [(t, re.compile(r"(?<![\w&])" + re.escape(t) + r"(?![\w&])", re.I)) for t in terms]
             for w, terms in TIERS.items()}
_NOISE = [(re.compile(p, re.I), w) for p, w in NOISE]

# Words that are also common outside finance: count only when another
# market term is present (avoid "real" in "real estate news", "rating" in reviews).
_NEEDS_COMPANY = {"real", "euro", "rating", "debt", "budget", "fiscal", "fx", "qe", "qt", "sec", "fed",
                  "bolsa", "yield", "guidance", "juros"}


def score_headline(title: str, description: str = "", source_weight: float = 1.0) -> tuple[float, list[str]]:
    """Return (score, matched terms). Higher = more likely to move markets."""
    title = title or ""
    text = f"{title} {description or ''}"
    matched: dict[str, float] = {}
    for weight, terms in _COMPILED.items():
        for term, rx in terms:
            if term in matched:
                continue
            if rx.search(title):
                matched[term] = weight * 2
            elif rx.search(text):
                matched[term] = weight
    strong = [t for t in matched if t not in _NEEDS_COMPANY]
    if not strong:
        matched = {}
    top = sorted(matched.values(), reverse=True)[:3]
    score = sum(w * f for w, f in zip(top, (1.0, 0.5, 0.25)))
    for rx, penalty in _NOISE:
        if rx.search(title) or rx.search(text[:300]):
            score -= penalty
    return round(max(score, 0.0) * source_weight, 2), sorted(matched)
