"""
Calls the host-side Thesis bridge (claude -p, the user's Claude Code
subscription — not the billed API) to turn fundamentals + DCF output into a
written thesis, top risks, and a probability-weighted target price.
"""

from app.claude_bridge import call_bridge


def generate_thesis(ticker: str, fundamentals: dict, dcf_outputs: dict) -> dict:
    return call_bridge("dcf_thesis", ticker=ticker, fundamentals=fundamentals, dcf_outputs=dcf_outputs)
