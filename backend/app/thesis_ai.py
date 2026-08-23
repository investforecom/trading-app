"""
Calls Claude to turn fundamentals + DCF output into a written thesis, top
risks, and a probability-weighted target price. Structured JSON output
(output_config.format) guarantees a parseable response — no free-text
scraping.
"""

import json
import os
import anthropic

MODEL = "claude-opus-5"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "thesis_text": {
            "type": "string",
            "description": "3-6 sentence investment thesis: why this name, why now, what has to be true.",
        },
        "top_risks": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short risk label, max 8 words"},
                    "detail": {"type": "string", "description": "1-2 sentence explanation"},
                },
                "required": ["title", "detail"],
                "additionalProperties": False,
            },
        },
        "scenario_commentary": {
            "type": "object",
            "properties": {
                "bear": {"type": "string", "description": "1-2 sentences: what has to happen for the bear case"},
                "base": {"type": "string", "description": "1-2 sentences: what has to happen for the base case"},
                "bull": {"type": "string", "description": "1-2 sentences: what has to happen for the bull case"},
            },
            "required": ["bear", "base", "bull"],
            "additionalProperties": False,
        },
        "target_price": {
            "type": "number",
            "description": "Probability-weighted 12-month target price, informed by the three DCF scenarios and analyst context — not a simple average.",
        },
    },
    "required": ["thesis_text", "top_risks", "scenario_commentary", "target_price"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are an equity research analyst building an investment thesis for a \
sophisticated individual investor who owns all trading decisions (no disclaimers needed). \
You are given fundamentals for a ticker and a 3-scenario DCF (bear/base/bull) already computed \
by the user's own model. Write a concise, opinionated thesis grounded in the numbers given — \
do not hedge with generic boilerplate. Flag the risks that would actually break this specific \
thesis, not generic market risk."""


def generate_thesis(ticker: str, fundamentals: dict, dcf_outputs: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    user_prompt = f"""Ticker: {ticker}

Fundamentals:
{json.dumps(fundamentals, indent=2, default=str)}

DCF output (bear/base/bull implied prices + assumptions, computed by the user's own model):
{json.dumps({k: v for k, v in dcf_outputs.items() if k != "sensitivity"}, indent=2, default=str)}

Current price: {fundamentals.get("current_price")}

Write the investment thesis."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
