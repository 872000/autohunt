"""Tests for the SQLite store."""
import pytest

from autohunt.store import Store
from tests.conftest import make_listing


@pytest.fixture()
def store(tmp_path):
    db = Store(tmp_path / "test.db")
    yield db
    db.close()


def test_upsert_new_and_updated(store):
    new, updated = store.upsert_listings([make_listing(), make_listing(id="test-02")])
    assert (new, updated) == (2, 0)
    assert store.count() == 2

    changed = make_listing(price=16000)
    new, updated = store.upsert_listings([changed])
    assert (new, updated) == (0, 1)
    assert store.get_listing("test-01")["price"] == 16000


def test_price_history_only_on_change(store):
    store.upsert_listings([make_listing(price=17000)])
    store.upsert_listings([make_listing(price=17000)])  # same price: no new row
    assert store.previous_price("test-01") is None
    store.upsert_listings([make_listing(price=16000)])
    assert store.previous_price("test-01") == 17000
    assert store.latest_price("test-01") == 16000


def test_seen_state_is_per_profile(store):
    assert not store.is_seen("test-01", "mustang")
    store.mark_seen("test-01", "mustang")
    assert store.is_seen("test-01", "mustang")
    assert not store.is_seen("test-01", "family-suv")  # other profile unaffected


def test_watchlist(store):
    store.watch("test-01", target_price=15000)
    watched = store.watched()
    assert len(watched) == 1
    assert watched[0]["target_price"] == 15000
    assert store.unwatch("test-01") is True
    assert store.watched() == []
    assert store.unwatch("test-01") is False


def test_alert_log(store):
    store.log_alert("test-01", "new_deal", "a great deal")
    recent = store.recent_alerts()
    assert len(recent) == 1
    assert recent[0]["rule"] == "new_deal"


def test_missing_history_round_trip(store):
    store.upsert_listings([make_listing(history=None)])
    assert store.get_listing("test-01")["history"] is None


def test_history_round_trip(store):
    store.upsert_listings([make_listing()])
    history = store.get_listing("test-01")["history"]
    assert history["accidents"] == 0
    assert history["owners"] == 1
    assert history["service_records"] is True
