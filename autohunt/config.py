"""Shared constants and path helpers for AutoHunt."""
from __future__ import annotations

from pathlib import Path

APP_NAME = "autohunt"
VERSION = "0.1.0"
CURRENT_YEAR = 2026

# Package-root-relative locations, so the tool works no matter where it is
# installed or invoked from.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILES_DIR = PACKAGE_ROOT / "profiles"
DEFAULT_DEMO_DATA_PATH = PACKAGE_ROOT / "demo_data" / "listings.json"

# Runtime state lives in the current working directory (gitignored).
DEFAULT_DATA_DIR = Path(".autohunt")
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "autohunt.db"
DEFAULT_REPORTS_DIR = DEFAULT_DATA_DIR / "reports"

# Approximate new MSRP (CAD). Only used as a fallback when fewer than three
# comparable listings exist to estimate market value from.
BASE_PRICES = {
    ("ford", "mustang"): 46000,
    ("honda", "civic"): 29000,
    ("honda", "cr-v"): 37000,
    ("honda", "accord"): 36000,
    ("toyota", "corolla"): 27000,
    ("toyota", "rav4"): 38000,
    ("toyota", "camry"): 35000,
    ("mazda", "mazda3"): 28000,
    ("mazda", "cx-5"): 36000,
}
DEFAULT_BASE_PRICE = 30000
