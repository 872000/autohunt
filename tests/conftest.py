"""Shared fixtures for the AutoHunt test suite."""
from __future__ import annotations

import pytest

from autohunt import fetchers
from autohunt.profiles import load_profile


@pytest.fixture()
def mustang_profile():
    return load_profile("profiles/mustang.yaml")


@pytest.fixture()
def suv_profile():
    return load_profile("profiles/family-suv.yaml")


@pytest.fixture()
def demo_listings():
    return fetchers.fetch_demo_listings()


def make_listing(**overrides):
    listing = {
        "id": "test-01",
        "source": "demo",
        "title": "2019 Ford Mustang Convertible",
        "make": "Ford",
        "model": "Mustang",
        "year": 2019,
        "body_style": "convertible",
        "price": 17000,
        "mileage_km": 50000,
        "city": "Hamilton",
        "distance_km": 10,
        "url": "https://example.com/test-01",
        "posted_at": "2026-09-01T00:00:00+00:00",
        "seller_type": "dealer",
        "history": {"accidents": 0, "owners": 1, "title_status": "clean",
                    "service_records": True},
    }
    listing.update(overrides)
    return listing
