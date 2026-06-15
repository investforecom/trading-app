# Trading Insights System — Project Brief

> This file is the project's source of truth for context. Read it fully before acting.
> It captures decisions already made so they don't need re-explaining.

## Purpose

Build a personal, cloud-based **system** that turns trading data (1+ year of closed
trades, plus live open positions) into insights for reviewing performance, checking
discipline against the owner's own rules, and informing strategy.

This is a system built around a **clean data model**, not a one-off dashboard. The
dashboard is a *replaceable lens*; the data model is the *durable core*. Get the
schema right and any presentation layer (Metabase now, a custom app later) is just a
consumer of the same truth.

Eventually a small number of trusted friends may run their own portfolios in the same
tool. It is a personal / small-group tool, **not a commercial product**.

## Owner context

- Network engineer — comfortable with Linux, containers, networking, SSH, DNS.
- Based in Sydney, Australia; trades US markets, prefers longer-dated positions
  (timezone makes intraday US trading impractical).
- Runs multiple accounts: an aggressive IBKR options/LEAPS account, a long-term
  buy-and-hold IBKR account, and a separate ETF account.
- Owns all trading decisions. **No "not financial advice" disclaimers needed.**

## Current state

- **Host:** OVHcloud VPS in Sydney — 2 vCore / 4 GB RAM / 40 GB NVMe SSD,
  Ubuntu 26.04, public IP, prepaid 6 months, automated backups enabled. x86_64.
- **Data today:** existing routines (running as Claude Code jobs on a *separate* cloud
  instance) write trade / performance / position / macro data as **CSV files into a
  GitHub repo**.
- **Broker:** IBKR access available (an IBKR connector exists) for live
  positions and balances.

## Architecture (locked)

Data flow:

```
Ingestion (IBKR + routines)
   -> Raw layer (GitHub repo, versioned CSVs)   [append-only audit trail]
   -> Loader (idempotent)
   -> PostgreSQL (single source of truth)        [the durable core]
   -> Presentation (Metabase now / custom app later)
```

The loader, Postgres, and presentation run on the OVH box under **Docker Compose**,
behind a **Caddy** reverse proxy (automatic TLS) on a domain.

**Guiding principle:** Postgres + a well-designed schema *is* the system. Everything
else is a swappable consumer of it.

### Locked decisions

- **Docker Compose** for the whole stack — reproducible, portable, version-controlled.
  Nothing hand-installed on the host.
- **PostgreSQL** as the single source of truth. Schema changes via **versioned
  migrations** committed to the repo.
- **GitHub repo stays** as an append-only raw/audit layer upstream of the loader.
  Don't rip out what already works.
- **Idempotent loader** — re-running on the same raw data never duplicates or corrupts
  rows; history can be replayed safely.
- **Metabase** as the immediate presentation layer (fast value). A custom app
  (FastAPI + frontend, or Streamlit/Dash) can be added later against the same DB.
- **Caddy** reverse proxy for automatic HTTPS + domain.
- **Multi-tenancy from day one:** every domain table carries an `owner_id`
  (account-holder key), even though there is one user today. Adding friends later =
  new rows, not a schema rebuild.

### Deliberately excluded (for now)

- No Kubernetes, no microservices, no managed/cloud DB. Overkill on a 2-core box for a
  handful of users. Compose + one Postgres container scales well past current needs.

## Domain model (confirm against the real CSVs before finalizing the schema)

The repo's actual data is the source of truth. The below is context to interpret it,
not gospel — validate column names and meanings against the real files.

**Strategy taxonomy** (each trade is tagged with one):

| Tag | Meaning | Stop discipline |
|-----|---------|-----------------|
| LEAP | Single long call; let winners run while thesis holds | No price stop (size is the stop) |
| LDS | Long debit spread; harvest at >=70% gain or when forward R/R < ~1.5:1 | No stop |
| CDS | Swing debit spread (~3–10mo), technical, small size | HARD stop below support (only strategy with one); >10mo converts to LDS |
| 2x-ETF | Leveraged big-tech proxies (e.g. MSFU/METU/AMZU); DCA, covered calls, short-put wheel | n/a |
| Wheel | Cash-secured short puts / covered calls | n/a |
| Thematic | Small/mid-cap convexity, capped | n/a |
| Scalp | Rare | n/a |

**Accounts:** aggressive IBKR (options/LEAPS), long-term IBKR (buy & hold), ETF.
A position belongs to an account.

**Concepts the schema should support:**

- **Thesis + catalyst** per position. A trade may depend on a specific catalyst; if
  the catalyst breaks, the position should be exited. Track this so adherence can be
  measured.
- **Position sizing** vs a per-name cap (~4% of trading-account NAV / ~$3K cost basis
  on single-name LEAPS).
- **R-multiples**, realized/unrealized P&L, entry/exit dates, status (open/closed).

## Insights the system should eventually support

Build incrementally — not all at once.

- Per-strategy and per-account P&L, win rate, average R-multiple, holding period.
- Equity curve and drawdown over time; money-weighted return.
- Open positions with unrealized P&L and current size vs cap.
- Discipline checks: sizing vs the 4% cap; whether catalyst-dependent trades were cut
  when the thesis broke; a winner-trim flag (~7–8% of NAV) for positions drifting
  oversized.
- Macro / market-breadth context for deployment decisions (deployment keys off breadth
  *direction*, not level).

## Working agreement

- Build slowly and steadily. Prefer scalable, flexible choices that avoid future
  limits, while still delivering short-term value.
- Explain tradeoffs and confirm before large or destructive actions.
- Commit infra-as-code (Compose files, migrations, loader, Caddyfile) to the repo so
  the whole system is reproducible from scratch.
- Security matters — this is a public box holding financial data. Non-root user, SSH
  key auth only, firewall, secrets in `.env` files that are **never committed**.

## Suggested build order

1. Harden the box: non-root sudo user, SSH key auth, disable password login, UFW firewall.
2. Docker + Compose baseline: Postgres + Metabase, persistent volumes, `.env` for secrets.
3. Caddy reverse proxy + domain + automatic TLS; confirm browser access from anywhere.
4. Inspect the real CSVs, then design the Postgres schema (with `owner_id`) + migrations.
5. Idempotent loader: repo CSVs -> Postgres; backfill the 1+ year of history.
6. First Metabase dashboards: per-strategy P&L, open positions, equity curve.
7. Wire live IBKR open positions into the pipeline.
8. (Later) custom app against the same DB; add friends as additional owners.

## Immediate next steps

- Harden the box + stand up Compose (Postgres + Metabase). *Data-independent — start now.*
- Then design the schema from the actual repo CSVs (need: CSV headers + a few sample
  rows, and the shape of the open-positions export).
- Decide and register a domain for Caddy TLS.
