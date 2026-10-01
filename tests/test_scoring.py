"""Tests for matching, market value estimation and deal scoring."""
from autohunt import scoring
from autohunt.scoring import is_match, rank, score_listing
from tests.conftest import make_listing


def test_match_accepts_good_listing(mustang_profile):
    matched, reason = is_match(mustang_profile, make_listing())
    assert matched, reason


def test_match_rejects_each_hard_criterion(mustang_profile):
    cases = [
        ({"price": 99999}, "budget"),
        ({"year": 2010}, "year"),
        ({"mileage_km": 999999}, "mileage"),
        ({"distance_km": 999}, "distance"),
        ({"body_style": "coupe"}, "body"),
        ({"make": "Honda"}, "make"),
        ({"model": "Civic"}, "model"),
    ]
    for overrides, _ in cases:
        matched, reason = is_match(mustang_profile, make_listing(**overrides))
        assert not matched, f"should reject {overrides}"
        assert reason


def test_match_respects_exclusions(suv_profile):
    kia = make_listing(make="Kia", model="Sportage", body_style="suv", year=2018,
                       price=15000, mileage_km=70000)
    assert not is_match(suv_profile, kia)[0]
    sonata = make_listing(make="Hyundai", model="Sonata", body_style="sedan",
                          year=2018, price=13000, mileage_km=70000)
    assert not is_match(suv_profile, sonata)[0]
    civic = make_listing(make="Honda", model="Civic", body_style="sedan",
                         year=2018, price=15000, mileage_km=70000)
    assert is_match(suv_profile, civic)[0]


def test_market_value_uses_comparable_median():
    target = make_listing(price=15000)
    pool = [make_listing(id=f"c{i}", price=p, year=2018 + (i % 3) - 1)
            for i, p in enumerate([14000, 16000, 18000, 20000])]
    value, method = scoring.estimate_market_value(
        target, scoring.comparable_listings(target, pool))
    assert value == 17000  # median of [14000, 16000, 18000, 20000]
    assert "comparables" in method


def test_market_value_falls_back_to_heuristic():
    target = make_listing(price=15000)
    value, method = scoring.estimate_market_value(target, [])
    assert value > 0
    assert "depreciation" in method


def test_comparables_require_same_body_style():
    target = make_listing()
    coupe = make_listing(id="coupe", body_style="coupe")
    assert scoring.comparable_listings(target, [coupe]) == []


def test_red_flag_accident(mustang_profile):
    result = score_listing(mustang_profile,
                           make_listing(history={"accidents": 2, "owners": 2,
                                                 "title_status": "clean",
                                                 "service_records": True}),
                           pool=[])
    codes = {f["code"] for f in result["red_flags"]}
    assert "accident_history" in codes
    assert result["breakdown"]["history"] < 100


def test_red_flag_rebuilt_title_caps_score(mustang_profile):
    result = score_listing(mustang_profile,
                           make_listing(price=5000,
                                        history={"accidents": 0, "owners": 1,
                                                 "title_status": "rebuilt",
                                                 "service_records": True}),
                           pool=[])
    assert "rebuilt_title" in {f["code"] for f in result["red_flags"]}
    assert result["score"] <= 25


def test_red_flag_suspicious_price_capped(mustang_profile):
    # Far below any plausible market value for a 2019 Mustang.
    result = score_listing(mustang_profile, make_listing(price=3000), pool=[])
    codes = {f["code"] for f in result["red_flags"]}
    assert "suspiciously_low_price" in codes
    assert result["score"] <= 65


def test_red_flag_overpriced(mustang_profile):
    result = score_listing(mustang_profile, make_listing(price=60000), pool=[])
    assert "overpriced" in {f["code"] for f in result["red_flags"]}


def test_red_flag_missing_history(mustang_profile):
    result = score_listing(mustang_profile, make_listing(history=None), pool=[])
    assert "missing_history" in {f["code"] for f in result["red_flags"]}


def test_scores_bounded_and_ranked(mustang_profile, demo_listings):
    ranked = rank(mustang_profile, demo_listings)
    assert ranked, "expected some mustang matches in demo data"
    scores = [r["score"] for r in ranked]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert all(r["is_match"] for r in ranked)


def test_demo_top_mustang_is_hot_deal(mustang_profile, demo_listings):
    ranked = rank(mustang_profile, demo_listings)
    assert ranked[0]["verdict"] == "HOT DEAL"
    assert ranked[0]["listing"]["id"] == "demo-mustang-09"


def test_demo_red_flags_show_up(mustang_profile, demo_listings):
    ranked = rank(mustang_profile, demo_listings)
    by_id = {r["listing"]["id"]: r for r in ranked}
    assert "suspiciously_low_price" in {f["code"] for f in by_id["demo-mustang-04"]["red_flags"]}
    assert "accident_history" in {f["code"] for f in by_id["demo-mustang-02"]["red_flags"]}
    assert "missing_history" in {f["code"] for f in by_id["demo-mustang-08"]["red_flags"]}


def test_rebuilt_mustang_scores_low(mustang_profile, demo_listings):
    ranked = rank(mustang_profile, demo_listings)
    by_id = {r["listing"]["id"]: r for r in ranked}
    rebuilt = by_id["demo-mustang-06"]
    assert rebuilt["score"] <= 25
    assert "rebuilt_title" in {f["code"] for f in rebuilt["red_flags"]}


def test_preferred_make_bonus(suv_profile):
    base = dict(suv_profile)
    listing = make_listing(make="Honda", model="Civic", body_style="sedan",
                           year=2018, price=15000, mileage_km=60000,
                           history={"accidents": 0, "owners": 1,
                                    "title_status": "clean", "service_records": True})
    with_bonus = score_listing(base, listing, pool=[])["score"]
    no_prefs = dict(base, preferences={})
    without_bonus = score_listing(no_prefs, listing, pool=[])["score"]
    assert with_bonus == without_bonus + 5
