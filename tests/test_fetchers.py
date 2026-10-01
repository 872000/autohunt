"""Tests for listing fetchers."""
import pytest

from autohunt import fetchers
from autohunt.fetchers import SourceUnavailable, fetch_demo_listings, fetch_listings


def test_demo_fetch_returns_bundled_listings():
    listings = fetch_demo_listings()
    assert len(listings) == 18
    required = {"id", "title", "make", "model", "year", "price", "mileage_km",
                "city", "distance_km", "url", "posted_at", "history"}
    for listing in listings:
        assert required <= set(listing)
        assert listing["history"] is None or isinstance(listing["history"], dict)


def test_demo_fetch_is_default_and_offline(mustang_profile):
    listings = fetch_listings(mustang_profile, source="demo")
    assert len(listings) == 18


def test_live_sources_raise_source_unavailable(mustang_profile):
    for source in ("autotrader", "kijiji"):
        with pytest.raises(SourceUnavailable):
            fetch_listings(mustang_profile, source=source)


def test_unknown_source_raises_value_error(mustang_profile):
    with pytest.raises(ValueError):
        fetch_listings(mustang_profile, source="craigslist")


def test_missing_history_stays_missing():
    raw = {"id": "x", "title": "t", "make": "Ford", "model": "Mustang",
           "year": 2018, "price": 15000, "mileage_km": 50000}
    listing = fetchers._normalize_listing(raw)
    assert listing["history"] is None
    assert listing["posted_at"]  # derived timestamp present
