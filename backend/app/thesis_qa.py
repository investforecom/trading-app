"""
Thesis stage — answers a short set of business questions and produces a
2-sentence growth thesis. Grounded 80-90% in the Quality Screen fundamentals
already fetched; a bounded web search fills gaps the numbers alone can't
answer (recent 10-Q/10-K disclosures, a specific competitive development).
"""

import json
import os
import re

import anthropic

MODEL = "claude-opus-5"

TOOLS = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]

SYSTEM_PROMPT = """You are an equity analyst building a short growth thesis for a \
sophisticated individual investor who owns all trading decisions (no disclaimers needed).

You are given the company's Quality Screen fundamentals (reliability, profitability, \
debt, dilution, valuation) already computed by the user's own tool. Base 80-90% of your \
answer directly on these numbers — cite the specific figures that justify each claim. Use \
the web_search tool sparingly (at most a few searches) only to fill gaps the fundamentals \
can't answer — e.g. a recent 10-Q/10-K disclosure, a specific competitive development, or a \
demand driver not visible in the financials. Every answer must be justified: reference the \
number or source behind it, not just an assertion.

Classify the company into exactly one stage:
- Growth: revenue still compounding at a high rate, market still being won
- Stabilization: growth decelerating, margins/moat maturing, competitive position settling
- Mature: low growth, capital return focus, moat largely established or eroding

Respond with ONLY a single fenced json code block (```json ... ```) matching this schema — \
no text before or after the fence:
{
  "demand": "1-2 sentences: what is the demand for this business's products/services, grounded in revenue growth and market context",
  "moat": "1-2 sentences: what is the moat (pricing power, switching costs, network effects, scale, IP)",
  "moat_trend": "Widening | Narrowing | Stable",
  "moat_trend_reason": "1 sentence justifying the trend, citing margin/market-share evidence",
  "numbers_support_story": true,
  "numbers_support_reason": "1-2 sentences: do growth/margins/dilution/debt actually back up the narrative, or is there a mismatch",
  "stage": "Growth | Stabilization | Mature",
  "stage_reason": "1 sentence justifying the stage classification",
  "growth_basis": "FCF | Earnings | Sales",
  "growth_rate_pct": 25,
  "growth_years": 5,
  "normalized_growth_pct": 6,
  "thesis_text": "Exactly 2 sentences: (1) 'The business is in the <Stage> stage and should compound <growth_basis> at roughly <growth_rate_pct>% annually for the next <growth_years> years before normalizing to <normalized_growth_pct>%.' (2) One sentence on the core justification.",
  "sources_used": ["short label per web search source actually used, e.g. 'Q2 FY26 10-Q' — empty array if none used"]
}
"""


def generate_thesis_qa(ticker: str, fundamentals: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_prompt = f"""Ticker: {ticker} ({fundamentals.get("long_name")})
Sector: {fundamentals.get("sector")} / {fundamentals.get("industry")}

Quality Screen fundamentals:
{json.dumps(fundamentals, indent=2, default=str)}

Answer the business questions and produce the growth thesis."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=TOOLS,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError("Claude did not return a parseable thesis JSON block")
    return json.loads(match.group(1))
