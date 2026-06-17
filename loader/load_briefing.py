"""
Parse a daily briefing markdown file → daily_briefings + daily_decisions + daily_flags.

Briefing format (as written by Routine A):
  # Briefing — YYYY-MM-DD (Day)
  **Header:** NAV $X · Deployed Y% (band A–B%) · Eff Lev Z.ZZx
  **Wheel cover:** ...
  > one-liner commentary
  ## MARKET
  ## PORTFOLIO (flagged only)
  ## WHEEL (≤5 trading days)
  ## NEW
  ## DETECTED CLOSED
  ## TODAY'S DECISIONS (ranked)
  Watchlist: ...
"""
import re
from datetime import date
from pathlib import Path

from db import transaction, fetch_one


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_header(line: str) -> dict:
    """
    Extract nav, deployed_pct, eff_lev, band_lo, band_hi from Header line.
    Handles three historical formats:
      Jun 8:   **NAV: $71,908** | **Deployed: 52.8%** | **Leverage: 1.42x**
      Jun 9-11: **Account:** NAV $X · Deployed Y% · Leverage Z
      Jun 12+:  **Header:** NAV $X · Deployed Y% (band A–B%) · Eff Lev Z.ZZx
    """
    result = {}
    m = re.search(r"NAV:?\s*\$([0-9,]+\.?[0-9]*)", line)
    if m:
        result["nav"] = float(m.group(1).replace(",", ""))
    m = re.search(r"Deployed:?\s*([0-9.]+)%", line)
    if m:
        result["deployed_pct"] = float(m.group(1))
    m = re.search(r"band ([0-9.]+)[–\-]([0-9.]+)%", line)
    if m:
        result["band_lo"] = float(m.group(1))
        result["band_hi"] = float(m.group(2))
    # Eff Lev (standardized) or Leverage (old format)
    m = re.search(r"Eff Lev ([0-9.]+)x?", line)
    if not m:
        m = re.search(r"Leverage:?\s*([0-9.]+)x?", line)
    if m:
        result["eff_lev"] = float(m.group(1))
    return result


def _parse_flags(portfolio_block: str) -> list[dict]:
    """
    Extract flagged positions from the PORTFOLIO section.
    Lines look like: - **HARVEST · CRWV 98P** note...
    """
    flags = []
    known_types = {"HARVEST", "UNDERWATER", "TRIM", "THESIS-CHECK", "EXPIRES", "NEW"}
    for line in portfolio_block.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        # Extract bold token: **TYPE · SYMBOL** or **TYPE · SYMBOL TEXT**
        m = re.search(r"\*\*([A-Z\-]+)\s*[·•]\s*([^\*]+?)\*\*\s*(.*)", line)
        if not m:
            # Fallback: **TYPE:** symbol text
            m = re.search(r"\*\*([A-Z\-]+)[:\s]+([^\*]+?)\*\*\s*(.*)", line)
        if m:
            flag_type = m.group(1).strip().upper()
            symbol_raw = m.group(2).strip()
            note = m.group(3).strip(" —-")
            # Normalise flag type
            if flag_type not in known_types:
                flag_type = "OTHER"
            # Symbol is first token of symbol_raw
            symbol = symbol_raw.split()[0].rstrip(".,")
            flags.append({"flag_type": flag_type, "symbol": symbol, "note": note or symbol_raw})
    return flags


def _parse_decisions(decisions_block: str) -> list[dict]:
    """
    Extract ranked decisions.
    Lines look like: 1. **ACTION** — note text.
    """
    decisions = []
    for line in decisions_block.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m:
            rank = int(m.group(1))
            text = m.group(2).strip()
            # Strip markdown bold markers for plain storage
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
            decisions.append({"rank": rank, "decision_text": text})
    return decisions


def _section(md: str, heading: str) -> str:
    """Return text of a ## section (up to the next ## or end of file)."""
    pattern = rf"##\s+{re.escape(heading)}[^\n]*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, md, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Public load function
# ---------------------------------------------------------------------------

def load(briefing_path: Path, account_id: int, _owner_id: int) -> None:
    md = briefing_path.read_text(encoding="utf-8")

    # Date from filename YYYY-MM-DD.md
    try:
        briefing_date = date.fromisoformat(briefing_path.stem)
    except ValueError:
        print(f"  Briefing filename not a date: {briefing_path.name}, skipping")
        return

    # --- Header metrics ---
    # Handles: **Header:** (current), **Account:** (Jun 9-11), **NAV:** (Jun 8)
    header_data: dict = {}
    for line in md.splitlines():
        if any(line.startswith(p) for p in ("**Header:**", "**Account:**", "**NAV:")):
            header_data = _parse_header(line)
            if header_data.get("nav"):
                break

    # --- Wheel cover ---
    wheel_cover = ""
    for line in md.splitlines():
        if line.startswith("**Wheel cover:**"):
            wheel_cover = line.replace("**Wheel cover:**", "").strip()
            break

    # --- Commentary (blockquote) ---
    commentary = ""
    for line in md.splitlines():
        if line.startswith(">"):
            commentary = line.lstrip(">").strip()
            break

    # --- Sections ---
    market_summary  = _section(md, "MARKET")
    portfolio_block = _section(md, "PORTFOLIO")
    wheel_section   = _section(md, "WHEEL")
    decisions_block = _section(md, "TODAY'S DECISIONS")

    # --- Watchlist (last line of file if it starts with "Watchlist:") ---
    watchlist = ""
    for line in reversed(md.splitlines()):
        if line.startswith("Watchlist:"):
            watchlist = line
            break

    flags     = _parse_flags(portfolio_block)
    decisions = _parse_decisions(decisions_block)

    with transaction() as cur:
        # Upsert briefing row
        cur.execute(
            """
            INSERT INTO daily_briefings
                (account_id, date, nav, deployed_pct, eff_lev,
                 band_lo, band_hi, wheel_cover, commentary,
                 market_summary, wheel_section, watchlist, briefing_md)
            VALUES
                (%(account_id)s, %(date)s, %(nav)s, %(deployed_pct)s, %(eff_lev)s,
                 %(band_lo)s, %(band_hi)s, %(wheel_cover)s, %(commentary)s,
                 %(market_summary)s, %(wheel_section)s, %(watchlist)s, %(briefing_md)s)
            ON CONFLICT (account_id, date) DO UPDATE SET
                nav            = EXCLUDED.nav,
                deployed_pct   = EXCLUDED.deployed_pct,
                eff_lev        = EXCLUDED.eff_lev,
                band_lo        = EXCLUDED.band_lo,
                band_hi        = EXCLUDED.band_hi,
                wheel_cover    = EXCLUDED.wheel_cover,
                commentary     = EXCLUDED.commentary,
                market_summary = EXCLUDED.market_summary,
                wheel_section  = EXCLUDED.wheel_section,
                watchlist      = EXCLUDED.watchlist,
                briefing_md    = EXCLUDED.briefing_md
            RETURNING id
            """,
            {
                "account_id":     account_id,
                "date":           briefing_date,
                "nav":            header_data.get("nav"),
                "deployed_pct":   header_data.get("deployed_pct"),
                "eff_lev":        header_data.get("eff_lev"),
                "band_lo":        header_data.get("band_lo"),
                "band_hi":        header_data.get("band_hi"),
                "wheel_cover":    wheel_cover or None,
                "commentary":     commentary or None,
                "market_summary": market_summary or None,
                "wheel_section":  wheel_section or None,
                "watchlist":      watchlist or None,
                "briefing_md":    md,
            },
        )
        briefing_id = cur.fetchone()["id"]

        # Replace decisions and flags (re-insert on each load for idempotency)
        cur.execute("DELETE FROM daily_decisions WHERE briefing_id = %s", (briefing_id,))
        for d in decisions:
            cur.execute(
                "INSERT INTO daily_decisions (briefing_id, rank, decision_text) VALUES (%s, %s, %s)",
                (briefing_id, d["rank"], d["decision_text"]),
            )

        cur.execute("DELETE FROM daily_flags WHERE briefing_id = %s", (briefing_id,))
        for f in flags:
            cur.execute(
                "INSERT INTO daily_flags (briefing_id, flag_type, symbol, note) VALUES (%s, %s, %s, %s)",
                (briefing_id, f["flag_type"], f["symbol"], f["note"]),
            )

    print(
        f"  briefing {briefing_date}: nav={header_data.get('nav')}, "
        f"{len(decisions)} decisions, {len(flags)} flags"
    )
