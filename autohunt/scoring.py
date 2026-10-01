"""Deal scoring.

Every listing that matches a profile's hard criteria gets a 0–100 score:

* **price** (45%) — how the asking price compares to an estimated market
  value. Market value comes from comparable listings (same make/model,
  model-year within ±2) when at least three exist, otherwise from a
  depreciation heuristic.
* **mileage** (20%) — lower odometer readings score higher, scaled to the
  profile's ``max_mileage_km``.
* **year** (15%) — newer model years score higher.
* **history** (20%) — clean, one-owner history scores best; accidents,
  rebuilt titles and missing records drag it down and raise red flags.

Red flags never silently vanish: they are reported on every result, and the
nastiest ones (rebuilt title, scam-bait pricing) cap the total score.
"""
from __future__ import annotations

from statistics import median

from . import config

DEFAULT_WEIGHTS = {"price": 0.45, "mileage": 0.20, "year": 0.15, "history": 0.20}

# Tuning knobs for the price component.
OVERPRICED_RATIO = 1.25      # price > 125% of market -> red flag
SUSPICIOUS_RATIO = 0.55      # price < 55% of market -> likely scam-bait
MIN_COMPARABLES = 3          # need this many to use the market median

VERDICTS = (
    (80, "HOT DEAL"),
    (65, "Good deal"),
    (50, "Fair"),
    (0, "Skip"),
)


def _norm(value) -> str:
    return str(value or "").strip().lower()


def is_match(profile: dict, listing: dict) -> tuple[bool, str]:
    """Check a listing against a profile's hard criteria.

    Returns (matched, reason). ``reason`` explains the first failing check,
    which makes "why was this skipped?" easy to answer.
    """
    criteria = profile.get("criteria", {})
    prefs = profile.get("preferences", {}) or {}

    def check(ok: bool, reason: str):
        return ok, ("" if ok else reason)

    makes = {_norm(m) for m in criteria.get("makes", []) or []}
    if makes:
        ok, reason = check(_norm(listing.get("make")) in makes,
                           f"make {listing.get('make')!r} not wanted")
        if not ok:
            return False, reason

    models = {_norm(m) for m in criteria.get("models", []) or []}
    if models:
        ok, reason = check(_norm(listing.get("model")) in models,
                           f"model {listing.get('model')!r} not wanted")
        if not ok:
            return False, reason

    bodies = {_norm(b) for b in criteria.get("body_styles", []) or []}
    if bodies:
        ok, reason = check(_norm(listing.get("body_style")) in bodies,
                           f"body style {listing.get('body_style')!r} not wanted")
        if not ok:
            return False, reason

    if listing.get("year", 0) < criteria.get("min_year", 0):
        return False, f"year {listing.get('year')} older than {criteria['min_year']}"
    if listing.get("price", 0) > criteria.get("max_price", float("inf")):
        return False, f"price ${listing.get('price'):,.0f} over budget"
    if listing.get("mileage_km", 0) > criteria.get("max_mileage_km", float("inf")):
        return False, "mileage over limit"
    if listing.get("distance_km", 0) > criteria.get("max_distance_km", float("inf")):
        return False, "too far away"

    excluded_makes = {_norm(m) for m in prefs.get("excluded_makes", []) or []}
    if _norm(listing.get("make")) in excluded_makes:
        return False, f"excluded make {listing.get('make')!r}"

    excluded_models = {_norm(m) for m in prefs.get("excluded_models", []) or []}
    full_name = _norm(f"{listing.get('make')} {listing.get('model')}")
    if full_name in excluded_models or _norm(listing.get("model")) in excluded_models:
        return False, f"excluded model {listing.get('model')!r}"

    return True, ""


def comparable_listings(listing: dict, pool: list[dict]) -> list[dict]:
    """Other listings of the same make/model/body with model-year within ±2."""
    out = []
    for other in pool:
        if other.get("id") == listing.get("id"):
            continue
        if _norm(other.get("make")) != _norm(listing.get("make")):
            continue
        if _norm(other.get("model")) != _norm(listing.get("model")):
            continue
        if _norm(other.get("body_style")) != _norm(listing.get("body_style")):
            continue
        if abs(other.get("year", 0) - listing.get("year", 0)) <= 2:
            out.append(other)
    return out


def estimate_market_value(listing: dict, comparables: list[dict]) -> tuple[float, str]:
    """Estimate market value; returns (value, method)."""
    prices = sorted(c["price"] for c in comparables if c.get("price"))
    if len(prices) >= MIN_COMPARABLES:
        return float(median(prices)), f"median of {len(prices)} comparables"

    base = config.BASE_PRICES.get(
        (_norm(listing.get("make")), _norm(listing.get("model"))),
        config.DEFAULT_BASE_PRICE,
    )
    age = max(0, config.CURRENT_YEAR - listing.get("year", config.CURRENT_YEAR))
    mileage_factor = max(0.50, 1.0 - listing.get("mileage_km", 0) / 500_000)
    value = base * (0.93 ** age) * mileage_factor
    return round(value, 2), "depreciation estimate"


def _price_score(ratio: float) -> float:
    """Map price/market ratio to 0–100. Cheaper is better."""
    if ratio <= 0.70:
        return 100.0
    if ratio >= 1.35:
        return 0.0
    return 100.0 * (1.35 - ratio) / (1.35 - 0.70)


def _history_score(history: dict | None) -> tuple[float, list[dict]]:
    """Score vehicle history; returns (score, red_flags)."""
    flags: list[dict] = []
    if not history:
        flags.append({
            "code": "missing_history",
            "detail": "No vehicle history available — verify with a Carfax before visiting.",
            "severity": "medium",
        })
        return 55.0, flags

    score = 100.0
    accidents = int(history.get("accidents") or 0)
    if accidents > 0:
        score -= min(60.0, 20.0 * accidents)
        flags.append({
            "code": "accident_history",
            "detail": f"{accidents} reported accident(s) on record.",
            "severity": "high" if accidents > 1 else "medium",
        })

    title = _norm(history.get("title_status"))
    if title in ("rebuilt", "salvage"):
        score = 0.0
        flags.append({
            "code": "rebuilt_title",
            "detail": f"Title status is '{title}' — resale value and insurance are affected.",
            "severity": "high",
        })

    owners = history.get("owners")
    if owners is not None:
        try:
            owners = int(owners)
        except (TypeError, ValueError):
            owners = None
    if owners is not None and owners >= 3:
        score -= 15.0
        flags.append({
            "code": "many_owners",
            "detail": f"{owners} previous owners.",
            "severity": "low",
        })

    if not history.get("service_records"):
        score -= 5.0

    return max(0.0, score), flags


def score_listing(profile: dict, listing: dict, pool: list[dict] | None = None) -> dict:
    """Score a listing against a profile.

    Returns a result dict with the score, component breakdown, red flags,
    verdict, market value estimate and the match decision.
    """
    pool = pool or []
    matched, reason = is_match(profile, listing)
    criteria = profile.get("criteria", {})
    prefs = profile.get("preferences", {}) or {}
    weights = (profile.get("scoring") or {}).get("weights") or DEFAULT_WEIGHTS

    comparables = comparable_listings(listing, pool)
    market_value, method = estimate_market_value(listing, comparables)
    price = listing.get("price", 0) or 0
    ratio = (price / market_value) if market_value > 0 else 1.0

    flags: list[dict] = []
    if ratio > OVERPRICED_RATIO:
        flags.append({
            "code": "overpriced",
            "detail": f"Asking ${price:,.0f} is {ratio:.0%} of the ~${market_value:,.0f} market value.",
            "severity": "medium",
        })
    suspicious = ratio < SUSPICIOUS_RATIO
    if suspicious:
        flags.append({
            "code": "suspiciously_low_price",
            "detail": f"Asking ${price:,.0f} is far below the ~${market_value:,.0f} market value — "
                      "common scam-bait pattern. Verify the seller and VIN in person.",
            "severity": "high",
        })

    price_score = _price_score(ratio)

    max_km = criteria.get("max_mileage_km", 1) or 1
    mileage_score = 100.0 * max(0.0, 1.0 - listing.get("mileage_km", 0) / max_km)

    min_year = criteria.get("min_year", config.CURRENT_YEAR)
    span = max(1, config.CURRENT_YEAR - min_year + 1)
    year_score = 100.0 * (listing.get("year", min_year) - min_year + 1) / span
    year_score = max(0.0, min(100.0, year_score))

    history_score, history_flags = _history_score(listing.get("history"))
    flags.extend(history_flags)

    total = (
        weights.get("price", 0) * price_score
        + weights.get("mileage", 0) * mileage_score
        + weights.get("year", 0) * year_score
        + weights.get("history", 0) * history_score
    )

    preferred = {_norm(m) for m in prefs.get("preferred_makes", []) or []}
    if _norm(listing.get("make")) in preferred:
        total += 5.0

    # Hard caps for the nastiest red flags.
    codes = {f["code"] for f in flags}
    if "rebuilt_title" in codes:
        total = min(total, 25.0)
    if suspicious:
        total = min(total, 65.0)

    total = round(max(0.0, min(100.0, total)), 1)
    verdict = next(label for threshold, label in VERDICTS if total >= threshold)

    return {
        "listing": listing,
        "is_match": matched,
        "skip_reason": reason,
        "score": total,
        "verdict": verdict,
        "market_value": round(market_value, 2),
        "market_method": method,
        "price_ratio": round(ratio, 3),
        "red_flags": flags,
        "breakdown": {
            "price": round(price_score, 1),
            "mileage": round(mileage_score, 1),
            "year": round(year_score, 1),
            "history": round(history_score, 1),
        },
    }


def rank(profile: dict, listings: list[dict], min_score: float = 0.0) -> list[dict]:
    """Score every listing and return matches sorted by score (best first)."""
    results = [score_listing(profile, listing, pool=listings) for listing in listings]
    matched = [r for r in results if r["is_match"] and r["score"] >= min_score]
    matched.sort(key=lambda r: r["score"], reverse=True)
    return matched
