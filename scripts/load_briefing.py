#!/usr/bin/env python3
"""
Load a daily briefing markdown file into the daily_briefings DB table.

Usage:
  python3 load_briefing.py            # loads today's briefing file
  python3 load_briefing.py 2026-06-23 # loads a specific date
  python3 load_briefing.py --backfill # loads all unloaded files in briefing_log/
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import psycopg2

ROUTINE_DIR = Path.home() / "workspace" / "trading-routine"
APP_DIR     = Path.home() / "workspace" / "trading-app"
ACCOUNT_ID  = 1


def _connect():
    env: dict = {}
    env_path = APP_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.split("#")[0].strip()
    return psycopg2.connect(
        host     = os.environ.get("PGHOST",     env.get("PGHOST",     "127.0.0.1")),
        port     = int(os.environ.get("PGPORT", env.get("PGPORT",     "5432"))),
        dbname   = os.environ.get("PGDATABASE", env.get("PGDATABASE", "trading")),
        user     = os.environ.get("PGUSER",     env.get("PGUSER",     env.get("POSTGRES_USER", "trading"))),
        password = os.environ.get("PGPASSWORD", env.get("PGPASSWORD", env.get("POSTGRES_PASSWORD", ""))),
    )


def _section(text: str, *patterns: str) -> str | None:
    """Extract content between the first matching ## heading and the next ## heading."""
    for pat in patterns:
        m = re.search(rf"^##\s+{pat}", text, re.MULTILINE | re.IGNORECASE)
        if m:
            start = m.end()
            # skip to end of matched line first
            eol = text.find("\n", start)
            start = eol + 1 if eol != -1 else start
            nxt   = re.search(r"^##\s+", text[start:], re.MULTILINE)
            end   = start + nxt.start() if nxt else len(text)
            chunk = text[start:end].strip()
            return chunk or None
    return None


def parse(text: str) -> dict:
    nav_m        = re.search(r"NAV\s+\$([0-9,]+)",  text)
    dep_m        = re.search(r"Deployed\s+([\d.]+)%", text)
    lev_m        = re.search(r"Eff\s+Lev\s+([\d.]+)x", text)
    band_m       = re.search(r"band\s+(\d+)[–\-](\d+)%", text)
    wc_lines     = [l.strip().lstrip("*").strip()
                    for l in text.splitlines() if "Wheel cover:" in l]

    return {
        "nav":          float(nav_m.group(1).replace(",", "")) if nav_m  else None,
        "deployed_pct": float(dep_m.group(1))                  if dep_m  else None,
        "eff_lev":      float(lev_m.group(1))                  if lev_m  else None,
        "band_lo":      int(band_m.group(1))                   if band_m else None,
        "band_hi":      int(band_m.group(2))                   if band_m else None,
        "wheel_cover":  wc_lines[0]                            if wc_lines else None,
        "market_summary": _section(text, "MARKET"),
        "commentary":     _section(text, r"PORTFOLIO(?:\s+FLAGS)?"),
        "wheel_section":  _section(text, "WHEEL"),
        "watchlist":      _section(text, r"TODAY'S DECISIONS", "DECISIONS"),
        "briefing_md":    text,
    }


def load_one(briefing_date: str) -> bool:
    md_path = ROUTINE_DIR / "briefing_log" / f"{briefing_date}.md"
    if not md_path.exists():
        print(f"  SKIP {briefing_date}: no file at {md_path}", file=sys.stderr)
        return False

    fields = parse(md_path.read_text())

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO daily_briefings
                    (account_id, date, nav, deployed_pct, eff_lev, band_lo, band_hi,
                     wheel_cover, commentary, market_summary, wheel_section, watchlist,
                     briefing_md)
                VALUES
                    (%(account_id)s, %(date)s, %(nav)s, %(deployed_pct)s, %(eff_lev)s,
                     %(band_lo)s,    %(band_hi)s, %(wheel_cover)s, %(commentary)s,
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
            """, {**fields, "account_id": ACCOUNT_ID, "date": briefing_date})
        nav_str = f"${fields['nav']:,.0f}" if fields["nav"] else "NAV=?"
        print(f"  Loaded {briefing_date} → DB  ({nav_str}  deployed={fields['deployed_pct']}%)")
        return True
    except Exception as e:
        print(f"  ERROR loading {briefing_date}: {e}", file=sys.stderr)
        return False
    finally:
        conn.close()


def backfill():
    """Load every file in briefing_log/ that has no DB row yet."""
    conn = _connect()
    cur  = conn.cursor()
    cur.execute("SELECT date::text FROM daily_briefings WHERE account_id = %s", (ACCOUNT_ID,))
    in_db = {r[0] for r in cur.fetchall()}
    conn.close()

    files = sorted(ROUTINE_DIR.glob("briefing_log/*.md"))
    loaded = 0
    for f in files:
        d = f.stem  # YYYY-MM-DD
        if d in in_db:
            print(f"  SKIP {d}: already in DB")
            continue
        if load_one(d):
            loaded += 1
    print(f"  Backfill done: {loaded} loaded, {len(files) - loaded} skipped")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--backfill" in args:
        backfill()
    elif args:
        ok = load_one(args[0])
        sys.exit(0 if ok else 1)
    else:
        # Default: use date from account_state.json if available, else today
        state_path = ROUTINE_DIR / "account_state.json"
        if state_path.exists():
            import json
            d = json.loads(state_path.read_text()).get("date") or date.today().isoformat()
        else:
            d = date.today().isoformat()
        ok = load_one(d)
        sys.exit(0 if ok else 1)
