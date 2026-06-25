#!/usr/bin/env python3
"""
Generate daily briefing markdown from DB + local JSON files — no LLM required.

Replaces the `claude -p` briefing step in daily_routine.sh.
Reads: account_state.json, ibkr_positions.json, trading_system.md
Queries: account_snapshots, position_snapshots, positions, pending_closes, position_notes
Writes: briefing_log/YYYY-MM-DD.md
Posts:  Discord webhook (from routine_instructions.md)
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras

ROUTINE_DIR = Path.home() / "workspace" / "trading-routine"
APP_DIR = Path(os.environ.get("TRADING_APP_DIR", Path.home() / "workspace" / "trading-app"))

PRIORITY_ORDER = [
    "EXPIRES_5D", "EXPIRES_4D", "EXPIRES_3D",
    "WHEEL-AT-RISK", "WHEEL-STUCK",
    "HARVEST", "TRIM",
    "UNDERWATER", "THESIS_CHECK",
    "NEW",
]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_env():
    env = {}
    env_path = APP_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.split("#")[0].strip()
    return env


def connect():
    env = _load_env()
    return psycopg2.connect(
        host=os.environ.get("PGHOST", env.get("PGHOST", "127.0.0.1")),
        port=int(os.environ.get("PGPORT", env.get("PGPORT", "5432"))),
        dbname=os.environ.get("PGDATABASE", env.get("PGDATABASE", "trading")),
        user=os.environ.get("PGUSER", env.get("PGUSER", env.get("POSTGRES_USER", "trading"))),
        password=os.environ.get("PGPASSWORD", env.get("PGPASSWORD", env.get("POSTGRES_PASSWORD", ""))),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_account_state():
    p = ROUTINE_DIR / "account_state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_ibkr_stock_prices():
    """Return {ticker: market_price} for all STK positions from ibkr_positions.json."""
    p = ROUTINE_DIR / "ibkr_positions.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    positions = data.get("positions", data) if isinstance(data, dict) else data
    prices = {}
    for pos in positions:
        if pos.get("asset_class") == "STK":
            ticker = pos.get("contract_description", "").split()[0]
            prices[ticker] = pos.get("market_price", 0)
    return prices


def load_band():
    """Extract deployment band from trading_system.md (last occurrence of 'trim-to-XX–YY%')."""
    p = ROUTINE_DIR / "trading_system.md"
    if not p.exists():
        return "40–60%"
    text = p.read_text()
    # Look for the regime line: "trim-to-40–60%" or "band 40–60%" or "40-60%"
    m = re.search(r"trim-to-(\d+)[–\-](\d+)%", text)
    if m:
        return f"{m.group(1)}–{m.group(2)}%"
    m = re.search(r"target.*?(\d+)[–\-](\d+)%", text)
    if m:
        return f"{m.group(1)}–{m.group(2)}%"
    return "40–60%"


def load_discord_webhook():
    p = ROUTINE_DIR / "routine_instructions.md"
    if not p.exists():
        return None
    m = re.search(r"https://discord\.com/api/webhooks/[\w/\-]+", p.read_text())
    return m.group(0) if m else None


def load_positions(cur, snap_date):
    cur.execute("""
        SELECT p.symbol, p.strategy, p.underlying, p.assignment_price,
               ps.qty, ps.cost_basis, ps.current_value, ps.gain_pct,
               ps.pct_nav, ps.forward_rr, ps.flags, ps.notes
        FROM position_snapshots ps
        JOIN positions p ON p.id = ps.position_id
        WHERE ps.snapshot_date = %s
          AND p.closed_date IS NULL
        ORDER BY p.strategy, p.symbol
    """, (snap_date,))
    return cur.fetchall()


def load_suppressed(cur):
    """Return {underlying: [flag, ...]} for active suppressions."""
    cur.execute("""
        SELECT underlying, suppress_flags, note
        FROM position_notes
        WHERE account_id = 1 AND active = true
          AND (snooze_until IS NULL OR snooze_until >= CURRENT_DATE)
    """)
    result = {}
    for row in cur.fetchall():
        result[row["underlying"]] = {
            "suppress": row["suppress_flags"] or [],
            "note": row["note"],
        }
    return result


def load_recent_closes(cur, snap_date, days=3):
    since = (datetime.strptime(str(snap_date), "%Y-%m-%d").date() - timedelta(days=days)).isoformat()
    cur.execute("""
        SELECT detected_date, symbol, strategy, est_realized_pnl, likely_reason
        FROM pending_closes
        WHERE detected_date >= %s
        ORDER BY detected_date DESC
    """, (since,))
    return cur.fetchall()


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_usd(n, decimals=0):
    if n is None:
        return "—"
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.{decimals}f}"


def fmt_pct(n, decimals=1):
    if n is None:
        return "—"
    return f"{n:+.{decimals}f}%"


def flag_priority(flags):
    if not flags:
        return 99
    for i, f in enumerate(PRIORITY_ORDER):
        if f in flags:
            return i
    return 99


def parse_expiry_days(symbol, snap_date):
    """Parse expiry date from symbol like NVDL_JUN26_87P. Returns days to expiry or None."""
    MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
              "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    # Match patterns like JUN26 (no year) or JUN18'26 (with year)
    m = re.search(r"_([A-Z]{3})(\d{2})(?:'(\d{2}))?_", symbol.upper())
    if not m:
        return None
    mon_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
    mon = MONTHS.get(mon_str)
    if not mon:
        return None
    snap = datetime.strptime(str(snap_date), "%Y-%m-%d").date()
    if year_str:
        # Format: JUN18'26 → day=18, year=2026
        exp = date(2000 + int(year_str), mon, int(day_str))
    else:
        # Format: JUN26 → month=JUN, day=26 of current/next year
        day = int(day_str)
        year = snap.year
        try:
            exp = date(year, mon, day)
        except ValueError:
            return None
        if exp < snap:
            exp = date(year + 1, mon, day)
    return (exp - snap).days


# ── Briefing sections ─────────────────────────────────────────────────────────

def section_header(state, band):
    nav = state.get("nav", 0)
    deployed_pct = state.get("deployed_pct", 0)
    eff_lev = state.get("leverage", 0)
    snap_date = state.get("date", date.today().isoformat())
    daily_pnl = state.get("daily_pnl")

    d = datetime.strptime(snap_date, "%Y-%m-%d")
    weekday = d.strftime("%A")

    lev_warn = " *** MARGIN RISK ***" if eff_lev >= 1.0 else ""
    header = (
        f"# Briefing {snap_date} [{weekday}]\n\n"
        f"**NAV {fmt_usd(nav)} · Deployed {deployed_pct:.1f}% (band {band}) · "
        f"Eff Lev {eff_lev:.2f}x{lev_warn}**"
    )
    if daily_pnl is not None:
        change_pct = state.get("daily_pnl_pct", 0)
        header += f"\n\nDaily P&L: {fmt_usd(daily_pnl)} ({change_pct:+.2f}%)"
    return header


def section_wheel_cover(state, positions):
    cash = state.get("cash", 0)
    sgov = state.get("sgov", 0)
    cover = cash + sgov

    # Compute short-put notional from WheelSP positions
    notional = 0.0
    sp_items = []
    for p in positions:
        if p["strategy"] != "WheelSP":
            continue
        qty = p["qty"] or 0
        if qty >= 0:
            continue
        # Parse strike from symbol  (e.g. NVDL_JUN26_87P → 87)
        m = re.search(r"_([\d.]+)[PC]$", p["symbol"].upper())
        if not m:
            continue
        strike = float(m.group(1))
        n = strike * 100 * abs(qty)
        notional += n
        sp_items.append(f"{p['underlying']} ${strike:.0f}k" if n >= 1000 else f"{p['underlying']} ${n:.0f}")

    if notional == 0:
        return None

    ratio = cover / notional if notional > 0 else 0
    status = "fully secured" if ratio >= 1.0 else "partially secured"
    sp_str = " + ".join(sp_items[:6])
    line = (
        f"Wheel cover: {fmt_usd(cover)} (cash {fmt_usd(cash)} + SGOV {fmt_usd(sgov)}) "
        f"vs {fmt_usd(notional)} short-put-notional ({sp_str}) → **{status} ({ratio:.2f}x)**"
    )
    return line


def section_portfolio_flags(positions, suppressed, stock_prices):
    flags_out = []
    for p in positions:
        flags = list(p["flags"] or [])
        if not flags:
            continue
        und = p["underlying"]
        sym = p["symbol"]
        gain = float(p["gain_pct"] or 0)
        pnav = float(p["pct_nav"] or 0)
        fwd_rr = p["forward_rr"]
        notes = p["notes"] or ""

        sup = suppressed.get(und, {})
        sup_flags = sup.get("suppress", [])
        sup_note = sup.get("note", "")

        # Skip purely expiry/NEW flags (go in other sections)
        display_flags = [f for f in flags if f not in ("EXPIRES_5D", "EXPIRES_4D", "EXPIRES_3D", "NEW")]
        if not display_flags:
            continue

        active = [f for f in display_flags if f not in sup_flags]
        suppressed_here = [f for f in display_flags if f in sup_flags]

        if suppressed_here and not active:
            flags_out.append(f"- ~~**{'+'.join(suppressed_here)} · {sym}**~~ suppressed ({sup_note})")
            continue

        # Combine all active flags into one line per position
        top = active[0] if active else None
        flag_label = "+".join(active)

        if top == "HARVEST":
            fwd_str = f" fwd R/R {fwd_rr}" if fwd_rr else ""
            desc = notes.split(".")[0] if notes else ""
            flags_out.append(f"- **{flag_label} · {sym}**{fwd_str}. {desc}".rstrip("."))
        elif top == "TRIM":
            desc = notes.split(".")[0] if notes else ""
            flags_out.append(f"- **{flag_label} · {sym}** {pnav:.1f}% NAV — reduce size. {desc}".rstrip("."))
        elif top in ("UNDERWATER", "THESIS_CHECK"):
            flags_out.append(f"- **{flag_label} · {sym}** {gain:+.1f}%. {notes}")
        elif top == "WHEEL-AT-RISK":
            stock_price = stock_prices.get(und)
            m = re.search(r"_([\d.]+)[PC]$", sym.upper())
            strike_str = f"strike ${float(m.group(1)):.2f}" if m else ""
            price_str = f"stock ${stock_price:.2f}" if stock_price else "stock price unknown"
            flags_out.append(f"- **{flag_label} · {sym}** {strike_str} — {price_str}. {notes}")
        elif top == "WHEEL-STUCK":
            ap = p.get("assignment_price")
            stock_price = stock_prices.get(und)
            if ap and stock_price:
                diff = (float(stock_price) - float(ap)) / float(ap) * 100
                flags_out.append(
                    f"- **WHEEL-STUCK · {und}** Assigned @${float(ap):.2f} — "
                    f"stock ${stock_price:.2f} ({diff:+.1f}%)"
                )
            else:
                flags_out.append(f"- **WHEEL-STUCK · {und}** {notes}")
        else:
            flags_out.append(f"- **{flag_label} · {sym}** {notes}")

        if suppressed_here:
            flags_out[-1] += f" *(also {'+'.join(suppressed_here)}: suppressed — {sup_note})*"

    return "\n".join(flags_out) if flags_out else "No flags today."


def section_wheel(positions, snap_date, stock_prices):
    rows = []
    for p in positions:
        if p["strategy"] not in ("WheelSP", "WheelSC"):
            continue
        if (p["qty"] or 0) == 0:
            continue  # expired / closed — skip
        flags = list(p["flags"] or [])
        has_expiry = any(f.startswith("EXPIRES") for f in flags) or "WHEEL-AT-RISK" in flags
        if not has_expiry:
            continue

        sym = p["symbol"]
        und = p["underlying"]
        notes = p["notes"] or ""
        gain = float(p["gain_pct"] or 0)

        m = re.search(r"_([\d.]+)([PC])$", sym.upper())
        strike = f"${float(m.group(1)):.2f}" if m else "—"
        cp = "Put" if m and m.group(2) == "P" else "Call"

        stock_price = stock_prices.get(und)
        if stock_price and m:
            s = float(m.group(1))
            if m.group(2) == "P":
                diff = (stock_price - s) / s * 100
                itm_str = f"**ITM** ${stock_price:.2f}" if stock_price < s else f"OTM {diff:+.1f}% (${stock_price:.2f})"
            else:
                diff = (stock_price - s) / s * 100
                itm_str = f"**ITM** ${stock_price:.2f}" if stock_price > s else f"OTM {diff:+.1f}% (${stock_price:.2f})"
        else:
            itm_str = "—"

        # Determine action from flags + notes
        if "WHEEL-AT-RISK" in flags:
            action = "**Close — at-risk**"
        elif gain > 70:
            action = "Let expire"
        elif gain > 30:
            action = "Monitor"
        else:
            action = "Review"

        days = parse_expiry_days(sym, snap_date)
        exp_str = f"{days}d" if days is not None else "—"

        rows.append(f"| {sym} {cp} {strike} | {itm_str} | {exp_str} | {action} |")

    if not rows:
        return "Nothing expiring ≤5 trading days."
    header = "| Symbol | Status | Exp | Action |\n|--------|--------|-----|--------|"
    return header + "\n" + "\n".join(rows)


def section_new(positions):
    items = []
    for p in positions:
        flags = list(p["flags"] or [])
        if "NEW" not in flags:
            continue
        strat = p["strategy"]
        sym = p["symbol"]
        notes = p["notes"] or ""
        gain = float(p["gain_pct"] or 0)
        items.append(f"- **{sym} {strat}** {gain:+.1f}%. {notes}")
    return "\n".join(items) if items else "None."


def section_closes(closes):
    if not closes:
        return "None detected."
    lines = []
    for c in closes:
        pnl = c["est_realized_pnl"]
        pnl_str = fmt_usd(pnl) if pnl else "—"
        lines.append(
            f"- **{c['symbol']} {c['strategy']}** {c['detected_date']} — "
            f"est. P&L {pnl_str}. {c['likely_reason'] or ''}"
        )
    return "\n".join(lines)


def section_decisions(positions, suppressed, stock_prices, snap_date):
    """Rank top ≤4 decisions by priority heuristic."""
    items = []
    seen_und = set()

    # Sort positions by flag priority
    def sort_key(p):
        flags = list(p["flags"] or [])
        return min((flag_priority([f]) for f in flags), default=99)

    for p in sorted(positions, key=sort_key):
        flags = list(p["flags"] or [])
        und = p["underlying"]
        sym = p["symbol"]
        strat = p["strategy"]
        gain = float(p["gain_pct"] or 0)
        fwd_rr = p["forward_rr"]
        notes = p["notes"] or ""
        sup = suppressed.get(und, {}).get("suppress", [])
        stock_price = stock_prices.get(und)

        display_flags = [f for f in flags if f not in ("EXPIRES_5D", "EXPIRES_4D", "EXPIRES_3D", "NEW")]
        active_flags = [f for f in display_flags if f not in sup]
        if not active_flags:
            continue

        # Deduplicate per underlying for same-priority flags
        key = (und, active_flags[0])
        if key in seen_und:
            continue
        seen_und.add(key)

        top = active_flags[0]
        if top in ("EXPIRES_5D", "EXPIRES_4D", "EXPIRES_3D") or top == "WHEEL-AT-RISK":
            m = re.search(r"_([\d.]+)([PC])$", sym.upper())
            strike = f"${float(m.group(1)):.2f}" if m else "?"
            days = parse_expiry_days(sym, snap_date)
            day_str = f", exp {days}d" if days is not None else ""
            price_str = f" stock ${stock_price:.2f}" if stock_price else ""
            items.append(f"**{sym}** — {top}: {strike}{price_str}{day_str} → close/roll before assignment")
        elif top == "WHEEL-STUCK":
            ap = p.get("assignment_price")
            price_str = f" stock ${stock_price:.2f}" if stock_price else ""
            ap_str = f" (assigned @${float(ap):.2f})" if ap else ""
            items.append(f"**{und}** — WHEEL-STUCK{ap_str}{price_str}: review CC roll")
        elif top == "HARVEST":
            fwd_str = f", R/R {fwd_rr}" if fwd_rr else ""
            items.append(f"**{sym}** — HARVEST {gain:+.1f}%{fwd_str}: close or scale out")
        elif top == "TRIM":
            pnav = float(p["pct_nav"] or 0)
            items.append(f"**{sym}** — TRIM: {pnav:.1f}% NAV, reduce to cap")
        elif top == "UNDERWATER":
            items.append(f"**{sym}** — UNDERWATER {gain:+.1f}%: thesis check, cut if broken")
        elif top == "THESIS_CHECK":
            items.append(f"**{sym}** — THESIS_CHECK {gain:+.1f}%: confirm thesis before adding")
        else:
            items.append(f"**{sym}** — {top}: {notes.split('.')[0] if notes else ''}")

        if len(items) >= 4:
            break

    if not items:
        return "Nothing urgent today."
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))


# ── Discord ───────────────────────────────────────────────────────────────────

def post_discord(webhook_url, message):
    import urllib.request

    if len(message) > 1800:
        # Truncate to header + decisions
        lines = message.split("\n")
        short = []
        in_decisions = False
        for line in lines:
            if "TODAY'S DECISIONS" in line:
                in_decisions = True
            if in_decisions or len(short) < 6:
                short.append(line)
            if len("\n".join(short)) > 1800:
                break
        message = "\n".join(short)

    payload = json.dumps({"content": message}).encode()
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (trading-system, 1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 204
    except Exception as e:
        print(f"Discord error: {e}", file=sys.stderr)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def generate(briefing_date=None):
    state = load_account_state()
    snap_date = briefing_date or state.get("date") or date.today().isoformat()
    stock_prices = load_ibkr_stock_prices()
    band = load_band()
    discord_url = load_discord_webhook()

    conn = connect()
    cur = conn.cursor()

    try:
        positions = load_positions(cur, snap_date)
        suppressed = load_suppressed(cur)
        closes = load_recent_closes(cur, snap_date, days=3)
    finally:
        conn.close()

    if not positions:
        print(f"ERROR: no position_snapshots for {snap_date}", file=sys.stderr)
        return False

    # Build each section
    header = section_header(state, band)
    wheel_cover = section_wheel_cover(state, positions)
    port_flags = section_portfolio_flags(positions, suppressed, stock_prices)
    wheel = section_wheel(positions, snap_date, stock_prices)
    new_pos = section_new(positions)
    detected = section_closes(closes)
    decisions = section_decisions(positions, suppressed, stock_prices, snap_date)

    md_parts = [header]
    if wheel_cover:
        md_parts.append(f"\n{wheel_cover}")
    md_parts += [
        "\n---",
        "\n## MARKET",
        "\n*Market data not pre-fetched — check index futures / VIX / catalysts.*",
        "\n---",
        "\n## PORTFOLIO FLAGS",
        f"\n{port_flags}",
        "\n---",
        f"\n## WHEEL (expiring ≤5 trading days)",
        f"\n{wheel}",
        "\n---",
        "\n## NEW",
        f"\n{new_pos}",
        "\n---",
        "\n## DETECTED CLOSED",
        f"\n{detected}",
        "\n---",
        "\n## TODAY'S DECISIONS",
        f"\n{decisions}",
    ]
    md = "\n".join(md_parts)

    # Write to file
    log_dir = ROUTINE_DIR / "briefing_log"
    log_dir.mkdir(exist_ok=True)
    out_path = log_dir / f"{snap_date}.md"
    out_path.write_text(md)
    print(f"OK  briefing_log/{snap_date}.md written ({len(md)} chars)")

    # Discord
    if discord_url:
        d = datetime.strptime(snap_date, "%Y-%m-%d")
        deployed_pct = state.get("deployed_pct", 0)
        eff_lev = state.get("leverage", 0)
        nav = state.get("nav", 0)
        daily_pnl = state.get("daily_pnl")
        pnl_str = fmt_usd(daily_pnl) if daily_pnl else ""

        msg_lines = [
            f"**{snap_date} [{d.strftime('%A')}]** · NAV {fmt_usd(nav)} · Deployed {deployed_pct:.1f}% (band {band}) · Eff Lev {eff_lev:.2f}x",
        ]
        if wheel_cover:
            msg_lines.append(wheel_cover[:200])
        if pnl_str:
            msg_lines.append(f"Daily P&L: {pnl_str}")
        msg_lines.append("")
        msg_lines.append("**TODAY'S DECISIONS**")
        msg_lines.append(decisions)

        msg = "\n".join(msg_lines)
        ok = post_discord(discord_url, msg)
        print(f"{'OK' if ok else 'WARN'} Discord {'sent' if ok else 'failed'}")
    else:
        print("WARN Discord webhook not found — skipped")

    return True


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    success = generate(date_arg)
    sys.exit(0 if success else 1)
