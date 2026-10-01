"""Alert rules evaluated by ``autohunt check``.

Rules:
* ``new_deal``      — a listing seen for the first time scoring at or above
  the profile's ``alerts.min_score``.
* ``price_drop``    — a tracked listing whose price fell by at least
  ``alerts.watch_price_drop_pct`` since the previous observation.
* ``watch_target``  — a watchlisted listing at or below its target price.

Every fired alert is appended to the store's alert log.
"""
from __future__ import annotations


def evaluate(store, profile: dict, scored: list[dict]) -> list[dict]:
    """Evaluate alert rules; returns the alerts fired (and logs them)."""
    alerts_cfg = profile.get("alerts") or {}
    min_score = alerts_cfg.get("min_score", 70)
    drop_pct = alerts_cfg.get("watch_price_drop_pct", 5.0)
    slug = profile.get("slug", "")

    fired: list[dict] = []
    by_id = {r["listing"]["id"]: r for r in scored}

    for result in scored:
        listing = result["listing"]
        lid = listing["id"]
        first_time = not store.is_seen(lid, slug)

        if first_time and result["is_match"] and result["score"] >= min_score:
            fired.append({
                "rule": "new_deal",
                "listing_id": lid,
                "title": listing["title"],
                "score": result["score"],
                "message": (
                    f"NEW DEAL — {listing['title']} scores {result['score']:.0f}/100 "
                    f"({result['verdict']}) at ${listing['price']:,.0f}."
                ),
            })

        if not first_time:
            prev = store.previous_price(lid)
            current = listing.get("price", 0)
            if prev and current and current < prev * (1 - drop_pct / 100):
                pct = 100.0 * (prev - current) / prev
                fired.append({
                    "rule": "price_drop",
                    "listing_id": lid,
                    "title": listing["title"],
                    "score": result["score"],
                    "message": (
                        f"PRICE DROP — {listing['title']}: "
                        f"${prev:,.0f} → ${current:,.0f} (−{pct:.1f}%)."
                    ),
                })

        store.mark_seen(lid, slug)

    for watch in store.watched():
        lid = watch["listing_id"]
        target = watch.get("target_price")
        result = by_id.get(lid)
        listing = result["listing"] if result else store.get_listing(lid)
        if listing is None or target is None:
            continue
        if listing.get("price", float("inf")) <= target:
            fired.append({
                "rule": "watch_target",
                "listing_id": lid,
                "title": listing["title"],
                "score": result["score"] if result else 0,
                "message": (
                    f"WATCH TARGET HIT — {listing['title']} is ${listing['price']:,.0f} "
                    f"(target was ${target:,.0f})."
                ),
            })

    for alert in fired:
        store.log_alert(alert["listing_id"], alert["rule"], alert["message"])
    return fired
