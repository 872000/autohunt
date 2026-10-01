"""Command-line interface for AutoHunt."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import alerts as alert_rules
from . import config, fetchers, scoring
from .profiles import ProfileError, list_profiles, load_profile
from .report import generate_report
from .store import Store


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolve_profile(slug: str, profiles_dir: Path) -> dict:
    for ext in (".yaml", ".yml"):
        candidate = profiles_dir / f"{slug}{ext}"
        if candidate.exists():
            return load_profile(candidate)
    available = [p["slug"] for p in list_profiles(profiles_dir)]
    hint = f"Available profiles: {', '.join(available)}" if available else "No profiles found."
    raise ProfileError(f"unknown profile {slug!r}. {hint}")


def _score_all(profile: dict, store: Store) -> list[dict]:
    listings = store.all_listings()
    return [scoring.score_listing(profile, listing, pool=listings) for listing in listings]


def _fmt_flags(flags: list[dict]) -> str:
    return ",".join(f["code"] for f in flags) if flags else "-"


def _print_deals(results: list[dict], limit: int):
    matched = [r for r in results if r["is_match"]][:limit]
    print(f"{'SCORE':>5}  {'PRICE':>9}  {'MARKET':>9}  {'KM':>7}  {'YEAR':>4}  VERDICT     FLAGS  TITLE")
    print("-" * 110)
    for r in matched:
        listing = r["listing"]
        print(
            f"{r['score']:>5.0f}  ${listing['price']:>8,.0f}  ${r['market_value']:>8,.0f}  "
            f"{listing.get('mileage_km', 0):>7,}  {listing.get('year', ''):>4}  "
            f"{r['verdict']:<10}  {_fmt_flags(r['red_flags']):<14}  {listing['title']}"
        )
    skipped = len([r for r in results if not r["is_match"]])
    if skipped:
        print(f"\n({skipped} listing(s) filtered out by profile criteria)")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_profiles(args) -> int:
    profiles = list_profiles(args.profiles_dir)
    if not profiles:
        print(f"No profiles found in {args.profiles_dir}")
        return 1
    for p in profiles:
        profile = load_profile(p["path"])
        crit = profile["criteria"]
        print(f"- {p['slug']}: {p['name']}")
        print(f"    {profile.get('description', '')}")
        print(f"    budget <= ${crit['max_price']:,.0f}, {crit['min_year']}+, "
              f"<= {crit['max_mileage_km']:,} km, within {crit['max_distance_km']} km")
    return 0


def cmd_fetch(args) -> int:
    try:
        profile = _resolve_profile(args.profile, args.profiles_dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        listings = fetchers.fetch_listings(profile, source=args.source)
    except fetchers.SourceUnavailable as exc:
        print(f"warning: {exc}", file=sys.stderr)
        print("warning: falling back to bundled demo data", file=sys.stderr)
        listings = fetchers.fetch_listings(profile, source="demo")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    store = Store(args.db)
    new, updated = store.upsert_listings(listings)
    total = store.count()
    store.close()
    print(f"Fetched {len(listings)} listings from '{args.source}' "
          f"({new} new, {updated} updated). {total} in store.")
    return 0


def cmd_list(args) -> int:
    try:
        profile = _resolve_profile(args.profile, args.profiles_dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    store = Store(args.db)
    results = _score_all(profile, store)
    store.close()
    ranked = [r for r in results if r["is_match"] and r["score"] >= args.min_score]
    ranked.sort(key=lambda r: r["score"], reverse=True)
    if not ranked:
        print("No matching listings. Run `autohunt fetch` first.")
        return 0
    print(f"Top deals for profile '{args.profile}' (min score {args.min_score}):\n")
    _print_deals(ranked, args.limit)
    return 0


def cmd_check(args) -> int:
    try:
        profile = _resolve_profile(args.profile, args.profiles_dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    store = Store(args.db)
    results = _score_all(profile, store)
    fired = alert_rules.evaluate(store, profile, results)
    store.close()
    if not fired:
        print("No new alerts. The hunt continues. 🔭")
        return 0
    print(f"{len(fired)} alert(s) for profile '{args.profile}':\n")
    for alert in fired:
        print(f"  • {alert['message']}")
    return 0


def cmd_watch(args) -> int:
    store = Store(args.db)
    listing = store.get_listing(args.listing_id)
    if listing is None:
        print(f"error: no listing with id {args.listing_id!r} in the store", file=sys.stderr)
        store.close()
        return 2
    store.watch(args.listing_id, args.target_price)
    target = f" (target ${args.target_price:,.0f})" if args.target_price else ""
    print(f"Watching {listing['title']}{target}")
    store.close()
    return 0


def cmd_unwatch(args) -> int:
    store = Store(args.db)
    removed = store.unwatch(args.listing_id)
    store.close()
    print(f"Stopped watching {args.listing_id}" if removed else f"{args.listing_id} was not watched")
    return 0


def cmd_watched(args) -> int:
    store = Store(args.db)
    watched = store.watched()
    for w in watched:
        listing = store.get_listing(w["listing_id"])
        title = listing["title"] if listing else w["listing_id"]
        price = listing["price"] if listing else None
        target = f"target ${w['target_price']:,.0f}" if w["target_price"] else "no target"
        current = f", now ${price:,.0f}" if price else ""
        print(f"- {w['listing_id']}: {title} ({target}{current})")
    if not watched:
        print("Watchlist is empty. Use `autohunt watch <listing-id>` to add one.")
    store.close()
    return 0


def cmd_report(args) -> int:
    try:
        profile = _resolve_profile(args.profile, args.profiles_dir)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    store = Store(args.db)
    results = _score_all(profile, store)
    fired = store.recent_alerts(limit=20)
    store.close()
    output = Path(args.output) if args.output else (
        config.DEFAULT_DATA_DIR / "reports" / f"report-{args.profile}.html"
    )
    path = generate_report(profile, results, fired, output)
    matched = sum(1 for r in results if r["is_match"])
    print(f"Report for '{args.profile}': {matched} matching listings → {path}")
    return 0


def cmd_demo(args) -> int:
    """End-to-end demo on bundled data: fetch → score → check → report."""
    data_dir = config.DEFAULT_DATA_DIR
    if data_dir.exists():
        shutil.rmtree(data_dir)
    args.db.parent.mkdir(parents=True, exist_ok=True)

    slugs = [args.profile] if args.profile else [p["slug"] for p in list_profiles(args.profiles_dir)]
    if not slugs:
        print("error: no profiles found", file=sys.stderr)
        return 1

    print("🏁 AutoHunt demo — fetching bundled listings, scoring deals, checking alerts.\n")
    fetch_args = argparse.Namespace(profile=slugs[0], source="demo",
                                    db=args.db, profiles_dir=args.profiles_dir)
    rc = cmd_fetch(fetch_args)
    if rc != 0:
        return rc

    store = Store(args.db)
    for slug in slugs:
        profile = _resolve_profile(slug, args.profiles_dir)
        results = _score_all(profile, store)
        matched = [r for r in results if r["is_match"]]
        matched.sort(key=lambda r: r["score"], reverse=True)
        print(f"\n━━━ {profile.get('name', slug)} — top deals ━━━")
        _print_deals(matched, limit=5)

        fired = alert_rules.evaluate(store, profile, results)
        if fired:
            print(f"\n🔔 {len(fired)} alert(s):")
            for alert in fired:
                print(f"  • {alert['message']}")

        report_path = config.DEFAULT_REPORTS_DIR / f"report-{slug}.html"
        generate_report(profile, results, fired, report_path)
        print(f"\n📄 Report written to {report_path}")
    store.close()
    print("\n✅ Demo complete. Try `autohunt list --profile mustang` or "
          "`autohunt check --profile family-suv` next.")
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autohunt",
        description="Watch car listings, score deals and get alerted the moment a good one appears.",
    )
    parser.add_argument("--db", type=Path, default=config.DEFAULT_DB_PATH,
                        help="SQLite database path (default: .autohunt/autohunt.db)")
    parser.add_argument("--profiles-dir", type=Path, default=config.DEFAULT_PROFILES_DIR,
                        help="Directory of YAML search profiles")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("profiles", help="List available search profiles")

    p = sub.add_parser("fetch", help="Fetch listings into the local store")
    p.add_argument("--profile", required=True, help="Profile slug (e.g. mustang)")
    p.add_argument("--source", default="demo", choices=sorted(fetchers.FETCHERS),
                   help="Listing source (default: demo — bundled offline data)")

    p = sub.add_parser("list", help="Show ranked deals for a profile")
    p.add_argument("--profile", required=True)
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("check", help="Evaluate alert rules (new deals, price drops, watch targets)")
    p.add_argument("--profile", required=True)

    p = sub.add_parser("watch", help="Watch a listing for price drops")
    p.add_argument("listing_id")
    p.add_argument("--target-price", type=float, default=None)

    p = sub.add_parser("unwatch", help="Stop watching a listing")
    p.add_argument("listing_id")

    sub.add_parser("watched", help="Show the watchlist")

    p = sub.add_parser("report", help="Generate an HTML deal report")
    p.add_argument("--profile", required=True)
    p.add_argument("--output", default=None, help="Output HTML path")

    p = sub.add_parser("demo", help="Run the end-to-end demo on bundled data")
    p.add_argument("--profile", default=None, help="Only demo this profile")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "profiles": cmd_profiles,
        "fetch": cmd_fetch,
        "list": cmd_list,
        "check": cmd_check,
        "watch": cmd_watch,
        "unwatch": cmd_unwatch,
        "watched": cmd_watched,
        "report": cmd_report,
        "demo": cmd_demo,
    }
    try:
        return commands[args.command](args)
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
