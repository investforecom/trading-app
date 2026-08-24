"""
Thesis stage — answers a short set of business questions and produces a
2-sentence growth thesis, via the host-side Thesis bridge (claude -p, the
user's Claude Code subscription — not the billed API).
"""

from app.claude_bridge import call_bridge


def generate_thesis_qa(ticker: str, fundamentals: dict) -> dict:
    return call_bridge("thesis_qa", ticker=ticker, fundamentals=fundamentals)
