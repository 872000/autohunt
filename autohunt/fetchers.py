"""Listing fetchers.

Demo mode (bundled JSON) is the default and works fully offline — the whole
tool, including the test suite, runs without network access.

AutoTrader/Kijiji-style source classes are provided so real connectors can be
plugged in later. They are intentionally *not* bundled: live scraping needs
credentials/sessions that don't belong in a portfolio repo. When a live
source is requested but unavailable, ``SourceUnavailable`` is raised and the
CLI falls back to demo data with a clear warning.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config


class SourceUnavailable(Exception):
    """Raised when a live listing source cannot be reached or used."""


def _demo_listings_path() -> Path:
    return config.DEFAULT_DEMO_DATA_PATH


def _normalize_listing(raw: dict) -> dict:
    """Fill defaults and derive posted_at from posted_days_ago."""
    listing = dict(raw)
    raw_history = raw.get("history")
    if raw_history:
        listing["history"] = {
            "accidents": raw_history.get("accidents", 0),
            "owners": raw_history.get("owners"),
            "title_status": (raw_history.get("title_status") or "clean").lower(),
            "service_records": bool(raw_history.get("service_records", False)),
        }
    else:
        # No history supplied at all: keep it missing so scoring can flag it.
        listing["history"] = None
    days_ago = listing.pop("posted_days_ago", 0)
    posted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    listing["posted_at"] = posted_at.isoformat(timespec="seconds")
    listing.setdefault("source", "demo")
    listing.setdefault("seller_type", "unknown")
    listing.setdefault("body_style", "")
    listing.setdefault("distance_km", 0)
    return listing


def fetch_demo_listings(data_path: str | Path | None = None) -> list[dict]:
    """Load the bundled demo listings (works offline)."""
    path = Path(data_path) if data_path else _demo_listings_path()
    if not path.exists():
        raise SourceUnavailable(f"demo data not found at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [_normalize_listing(item) for item in raw]


class AutoTraderFetcher:
    """Placeholder for a real AutoTrader connector (not bundled)."""

    name = "autotrader"

    def fetch(self, profile: dict) -> list[dict]:  # noqa: ARG002
        raise SourceUnavailable(
            "AutoTrader live connector is not bundled with AutoHunt "
            "(it needs an API key / session). Using demo data instead — "
            "see fetchers.py to plug in your own connector."
        )


class KijijiFetcher:
    """Placeholder for a real Kijiji connector (not bundled)."""

    name = "kijiji"

    def fetch(self, profile: dict) -> list[dict]:  # noqa: ARG002
        raise SourceUnavailable(
            "Kijiji live connector is not bundled with AutoHunt "
            "(it needs a session / scraping setup). Using demo data instead — "
            "see fetchers.py to plug in your own connector."
        )


FETCHERS = {
    "demo": None,  # handled directly
    "autotrader": AutoTraderFetcher(),
    "kijiji": KijijiFetcher(),
}


def fetch_listings(profile: dict, source: str = "demo") -> list[dict]:
    """Fetch listings for a profile from the named source.

    Raises:
        SourceUnavailable: if the source cannot be used.
        ValueError: if the source name is unknown.
    """
    source = source.lower()
    if source == "demo":
        return fetch_demo_listings()
    fetcher = FETCHERS.get(source)
    if fetcher is None:
        raise ValueError(f"unknown source {source!r}; choose from: {', '.join(sorted(FETCHERS))}")
    return fetcher.fetch(profile)
