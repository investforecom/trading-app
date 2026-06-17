"""Shared parsing helpers used across all loaders."""
import re
from datetime import date, datetime
from typing import Optional


STRATEGY_VALUES = {
    "LEAP", "LDS", "SWING", "2x-ETF", "Thematic",
    "WheelSP", "WheelSC", "PCS", "cash",
}

THEME_VALUES = {
    "AI-DC", "AI-Semis", "AI-Storage", "Neo-Cloud", "Large-Cap-Tech",
    "Fintech", "Financials", "Software-Recovery", "Nuclear-Power",
    "Solar-Energy", "Nat-Gas", "Battery-Storage", "Drones-Defense",
    "Gold-Macro", "Crit-Minerals", "Consumer", "Edge-HPC", "Quantum",
    "Photonics", "Autonomous-SW", "Space", "Crypto-Bitcoin",
    "Healthcare", "Cybersecurity", "Income", "Cash",
}


def parse_decimal(val: str) -> Optional[float]:
    """Return float or None for blank / N/A values."""
    if not val or val.strip().upper() in ("N/A", "NA", ""):
        return None
    # Strip leading + sign that appears in some CSV fields
    return float(val.strip().lstrip("+"))


def parse_int(val: str) -> Optional[int]:
    if not val or val.strip() == "":
        return None
    return int(float(val.strip()))


def parse_date_csv(val: str) -> Optional[date]:
    """Parse YYYY-MM-DD or 'unknown'."""
    val = val.strip()
    if not val or val.lower() == "unknown":
        return None
    return datetime.strptime(val, "%Y-%m-%d").date()


def parse_date_flex(val: str) -> Optional[date]:
    """Parse IBKR Flex date YYYYMMDD or datetime YYYYMMDD;HHMMSS."""
    val = val.strip()
    if not val:
        return None
    val = val.split(";")[0]  # drop time component
    return datetime.strptime(val, "%Y%m%d").date()


def parse_flags(val: str) -> Optional[list]:
    """Convert 'HARVEST|EXPIRES_4D' → ['HARVEST', 'EXPIRES_4D'], or None."""
    val = val.strip()
    if not val:
        return None
    parts = [p.strip() for p in val.split("|") if p.strip()]
    return parts if parts else None


def derive_underlying(symbol: str) -> str:
    """
    Heuristic: extract underlying ticker from a routine-format symbol.
    ORCL_DEC27_170C270C → ORCL
    SOFI_STK            → SOFI
    SGOV                → SGOV
    Falls back to the full symbol if no underscore.
    """
    if "_" not in symbol:
        return symbol
    root = symbol.split("_")[0]
    return root


def safe_strategy(val: str) -> str:
    val = val.strip()
    return val if val in STRATEGY_VALUES else "cash"


def safe_theme(val: str) -> Optional[str]:
    val = val.strip()
    return val if val in THEME_VALUES else None


def parse_hold_days(val: str) -> Optional[int]:
    val = val.strip()
    if not val or val.lower() == "unknown":
        return None
    return int(float(val))
