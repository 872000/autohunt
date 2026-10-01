"""Tests for alert rules."""
import pytest

from autohunt import alerts
from autohunt.scoring import score_listing
from autohunt.store import Store
from tests.conftest import make_listing


@pytest.fixture()
def store(tmp_path):
    db = Store(tmp_path / "test.db")
    yield db
    db.close()


def _scored(profile, listings):
    return [score_listing(profile, listing, pool=listings) for listing in listings]


def test_new_deal_alert_fires_once(store, mustang_profile, demo_listings):
    store.upsert_listings(demo_listings)
    scored = _scored(mustang_profile, store.all_listings())

    first = alerts.evaluate(store, mustang_profile, scored)
    assert any(a["rule"] == "new_deal" for a in first)
    assert all(a["score"] >= 70 for a in first if a["rule"] == "new_deal")

    second = alerts.evaluate(store, mustang_profile, scored)
    assert not [a for a in second if a["rule"] == "new_deal"]


def test_low_score_new_listing_does_not_alert(store, mustang_profile):
    bad = make_listing(id="junk", price=19999, mileage_km=119000, year=2015,
                       history={"accidents": 3, "owners": 4,
                                "title_status": "clean", "service_records": False})
    store.upsert_listings([bad])
    fired = alerts.evaluate(store, mustang_profile, _scored(mustang_profile, [bad]))
    assert fired == []


def test_price_drop_alert(store, mustang_profile):
    listing = make_listing(id="dropper", price=18000)
    store.upsert_listings([listing])
    store.upsert_listings([make_listing(id="dropper", price=16000)])  # −11%
    store.mark_seen("dropper", "mustang")  # not a first sighting anymore
    scored = _scored(mustang_profile, store.all_listings())
    fired = alerts.evaluate(store, mustang_profile, scored)
    drops = [a for a in fired if a["rule"] == "price_drop"]
    assert len(drops) == 1
    assert "18,000" in drops[0]["message"] and "16,000" in drops[0]["message"]


def test_small_price_change_does_not_alert(store, mustang_profile):
    listing = make_listing(id="steady", price=18000)
    store.upsert_listings([listing])
    store.upsert_listings([make_listing(id="steady", price=17800)])  # −1.1%
    store.mark_seen("steady", "mustang")
    scored = _scored(mustang_profile, store.all_listings())
    fired = alerts.evaluate(store, mustang_profile, scored)
    assert not [a for a in fired if a["rule"] == "price_drop"]


def test_watch_target_alert(store, mustang_profile):
    listing = make_listing(id="watched-01", price=15000)
    store.upsert_listings([listing])
    store.watch("watched-01", target_price=16000)
    scored = _scored(mustang_profile, store.all_listings())
    fired = alerts.evaluate(store, mustang_profile, scored)
    targets = [a for a in fired if a["rule"] == "watch_target"]
    assert len(targets) == 1
    assert "16,000" in targets[0]["message"]


def test_alerts_are_logged(store, mustang_profile, demo_listings):
    store.upsert_listings(demo_listings)
    alerts.evaluate(store, mustang_profile, _scored(mustang_profile, store.all_listings()))
    assert store.recent_alerts()
