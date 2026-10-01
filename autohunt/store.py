"""SQLite store: listings, price history, seen state, watchlist, alert log."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    make         TEXT NOT NULL,
    model        TEXT NOT NULL,
    year         INTEGER NOT NULL,
    body_style   TEXT NOT NULL DEFAULT '',
    price        REAL NOT NULL,
    mileage_km   INTEGER NOT NULL,
    city         TEXT NOT NULL DEFAULT '',
    distance_km  REAL NOT NULL DEFAULT 0,
    url          TEXT NOT NULL DEFAULT '',
    posted_at    TEXT NOT NULL DEFAULT '',
    accidents    INTEGER NOT NULL DEFAULT 0,
    owners       INTEGER,
    title_status TEXT NOT NULL DEFAULT 'clean',
    service_records INTEGER,
    seller_type  TEXT NOT NULL DEFAULT 'unknown',
    fetched_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    price      REAL NOT NULL,
    seen_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id, id);
CREATE TABLE IF NOT EXISTS seen (
    listing_id    TEXT NOT NULL,
    profile       TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    PRIMARY KEY (listing_id, profile)
);
CREATE TABLE IF NOT EXISTS watched (
    listing_id   TEXT PRIMARY KEY,
    target_price REAL,
    added_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    rule       TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_listing(row: sqlite3.Row) -> dict:
    listing = dict(row)
    accidents = listing.pop("accidents", 0) or 0
    owners = listing.pop("owners", None)
    title_status = listing.pop("title_status", "clean") or "clean"
    service_records = listing.pop("service_records", None)
    if service_records is None and owners is None and not accidents and title_status == "clean":
        # No history was ever supplied for this listing.
        listing["history"] = None
    else:
        listing["history"] = {
            "accidents": accidents,
            "owners": owners,
            "title_status": title_status,
            "service_records": bool(service_records),
        }
    listing.pop("fetched_at", None)
    return listing


class Store:
    """Thin sqlite3 wrapper for AutoHunt's persistent state."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -- listings ------------------------------------------------------
    def upsert_listings(self, listings: list[dict]) -> tuple[int, int]:
        """Insert or update listings; record price history on first sight or change.

        Returns (new_count, updated_count).
        """
        new, updated = 0, 0
        now = _now()
        for item in listings:
            history = item.get("history") or {}
            service_records = history.get("service_records")
            if service_records is not None:
                service_records = int(bool(service_records))
            existing = self.conn.execute(
                "SELECT price FROM listings WHERE id = ?", (item["id"],)
            ).fetchone()
            if existing is None:
                self.conn.execute(
                    """INSERT INTO listings
                       (id, source, title, make, model, year, body_style, price,
                        mileage_km, city, distance_km, url, posted_at,
                        accidents, owners, title_status, service_records,
                        seller_type, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item["id"], item.get("source", ""), item.get("title", ""),
                        item.get("make", ""), item.get("model", ""), item.get("year", 0),
                        item.get("body_style", ""), item.get("price", 0),
                        item.get("mileage_km", 0), item.get("city", ""),
                        item.get("distance_km", 0), item.get("url", ""),
                        item.get("posted_at", ""), history.get("accidents", 0),
                        history.get("owners"), history.get("title_status", "clean"),
                        service_records,
                        item.get("seller_type", "unknown"), now,
                    ),
                )
                self.conn.execute(
                    "INSERT INTO price_history (listing_id, price, seen_at) VALUES (?,?,?)",
                    (item["id"], item.get("price", 0), now),
                )
                new += 1
            else:
                old_price = existing["price"]
                new_price = item.get("price", 0)
                self.conn.execute(
                    """UPDATE listings SET source=?, title=?, make=?, model=?, year=?,
                       body_style=?, price=?, mileage_km=?, city=?, distance_km=?,
                       url=?, posted_at=?, accidents=?, owners=?, title_status=?,
                       service_records=?, seller_type=?, fetched_at=? WHERE id=?""",
                    (
                        item.get("source", ""), item.get("title", ""),
                        item.get("make", ""), item.get("model", ""), item.get("year", 0),
                        item.get("body_style", ""), new_price,
                        item.get("mileage_km", 0), item.get("city", ""),
                        item.get("distance_km", 0), item.get("url", ""),
                        item.get("posted_at", ""), history.get("accidents", 0),
                        history.get("owners"), history.get("title_status", "clean"),
                        service_records,
                        item.get("seller_type", "unknown"), now, item["id"],
                    ),
                )
                if new_price != old_price:
                    self.conn.execute(
                        "INSERT INTO price_history (listing_id, price, seen_at) VALUES (?,?,?)",
                        (item["id"], new_price, now),
                    )
                updated += 1
        self.conn.commit()
        return new, updated

    def get_listing(self, listing_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return _row_to_listing(row) if row else None

    def all_listings(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM listings ORDER BY fetched_at DESC").fetchall()
        return [_row_to_listing(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS n FROM listings").fetchone()["n"]

    # -- price history --------------------------------------------------
    def latest_price(self, listing_id: str) -> float | None:
        row = self.conn.execute(
            "SELECT price FROM price_history WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
            (listing_id,),
        ).fetchone()
        return row["price"] if row else None

    def previous_price(self, listing_id: str) -> float | None:
        """The price before the most recent observation (None if only one)."""
        rows = self.conn.execute(
            "SELECT price FROM price_history WHERE listing_id = ? ORDER BY id DESC LIMIT 2",
            (listing_id,),
        ).fetchall()
        return rows[1]["price"] if len(rows) == 2 else None

    # -- seen state ------------------------------------------------------
    def is_seen(self, listing_id: str, profile: str = "") -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM seen WHERE listing_id = ? AND profile = ?",
                (listing_id, profile),
            ).fetchone()
            is not None
        )

    def mark_seen(self, listing_id: str, profile: str = ""):
        now = _now()
        self.conn.execute(
            """INSERT INTO seen (listing_id, profile, first_seen_at, last_seen_at)
               VALUES (?,?,?,?)
               ON CONFLICT(listing_id, profile)
               DO UPDATE SET last_seen_at=excluded.last_seen_at""",
            (listing_id, profile, now, now),
        )
        self.conn.commit()

    # -- watchlist --------------------------------------------------------
    def watch(self, listing_id: str, target_price: float | None = None):
        self.conn.execute(
            """INSERT INTO watched (listing_id, target_price, added_at)
               VALUES (?,?,?)
               ON CONFLICT(listing_id) DO UPDATE SET target_price=excluded.target_price""",
            (listing_id, target_price, _now()),
        )
        self.conn.commit()

    def unwatch(self, listing_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM watched WHERE listing_id = ?", (listing_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def watched(self) -> list[dict]:
        rows = self.conn.execute("SELECT listing_id, target_price, added_at FROM watched").fetchall()
        return [dict(r) for r in rows]

    # -- alert log ---------------------------------------------------------
    def log_alert(self, listing_id: str, rule: str, message: str):
        self.conn.execute(
            "INSERT INTO alerts (listing_id, rule, message, created_at) VALUES (?,?,?,?)",
            (listing_id, rule, message, _now()),
        )
        self.conn.commit()

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
