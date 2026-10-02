"""YAML search profiles.

Profiles describe *what* to hunt for: hard criteria (year, price, mileage,
distance), brand preferences/exclusions, scoring weights and alert rules.

PyYAML is used when it is installed; otherwise a small built-in parser
handles the documented subset (nested mappings, scalar lists, inline lists,
comments). Either way the tool runs with zero required dependencies.
"""
from __future__ import annotations

from pathlib import Path

try:  # optional, graceful fallback below
    import yaml as _pyyaml
except Exception:  # pragma: no cover - exercised when PyYAML missing
    _pyyaml = None

from . import config


class ProfileError(Exception):
    """Raised when a search profile is missing or invalid."""


# ---------------------------------------------------------------------------
# Minimal YAML subset parser (fallback when PyYAML is unavailable)
# ---------------------------------------------------------------------------

def _split_top_level(text: str) -> list[str]:
    """Split on commas, ignoring commas inside single/double quotes."""
    parts, current, quote = [], [], None
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _parse_scalar(value: str):
    value = value.strip()
    if value in ("", "~", "null", "Null", "NULL"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(p) for p in _split_top_level(inner)]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _mini_yaml_load(text: str) -> dict:
    """Parse the small YAML subset used by search profiles."""
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # strip trailing comments ("key: value  # comment")
        content = _strip_inline_comment(raw).strip()
        if not content:
            continue
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise ProfileError(f"line {lineno}: tabs are not allowed for indentation")
        indent = len(leading)
        lines.append((indent, content, lineno))
    if not lines:
        return {}

    pos = 0

    def peek():
        return lines[pos] if pos < len(lines) else None

    def parse_block() -> object:
        nxt = peek()
        if nxt is None:
            return {}
        _, content, _ = nxt
        if content.startswith("- ") or content == "-":
            return parse_list(nxt[0])
        return parse_map(nxt[0])

    def parse_map(indent: int) -> dict:
        nonlocal pos
        result: dict = {}
        while True:
            nxt = peek()
            if nxt is None:
                break
            ind, content, lineno = nxt
            if ind != indent or content.startswith("- ") or content == "-":
                break
            if ":" not in content:
                raise ProfileError(f"line {lineno}: expected 'key: value', got {content!r}")
            key, _, val = content.partition(":")
            key, val = key.strip(), val.strip()
            if not key:
                raise ProfileError(f"line {lineno}: empty key")
            pos += 1
            if val == "":
                child = peek()
                if child is not None and child[0] > indent:
                    result[key] = parse_block()
                else:
                    result[key] = None
            else:
                result[key] = _parse_scalar(val)
        return result

    def parse_list(indent: int) -> list:
        nonlocal pos
        result: list = []
        while True:
            nxt = peek()
            if nxt is None:
                break
            ind, content, lineno = nxt
            if ind != indent or not (content.startswith("- ") or content == "-"):
                break
            item = content[1:].strip()
            pos += 1
            if item == "":
                child = peek()
                if child is not None and child[0] > indent:
                    result.append(parse_block())
                else:
                    result.append(None)
            elif ":" in item and not _looks_quoted(item):
                raise ProfileError(
                    f"line {lineno}: mapping items are not supported inside lists "
                    f"(got {item!r}); use nested blocks instead"
                )
            else:
                result.append(_parse_scalar(item))
        return result

    if lines[0][0] != 0:
        raise ProfileError("profile must start with a top-level mapping at indent 0")
    data = parse_block()
    if not isinstance(data, dict):
        raise ProfileError("profile must be a mapping at the top level")
    return data


def _strip_inline_comment(line: str) -> str:
    """Remove a ' # comment' suffix, respecting quotes."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and i > 0 and line[i - 1] in (" ", "\t"):
            return line[:i]
    return line


def _looks_quoted(value: str) -> bool:
    value = value.strip()
    return len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

REQUIRED_CRITERIA = ("min_year", "max_price", "max_mileage_km", "max_distance_km")


def _load_yaml_text(text: str) -> dict:
    if _pyyaml is not None:
        data = _pyyaml.safe_load(text)
        return {} if data is None else data
    return _mini_yaml_load(text)


def load_profile(path: str | Path) -> dict:
    """Load and validate a search profile from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ProfileError(f"profile not found: {path}")
    try:
        data = _load_yaml_text(path.read_text(encoding="utf-8"))
    except ProfileError:
        raise
    except Exception as exc:  # malformed YAML
        raise ProfileError(f"could not parse {path}: {exc}") from exc
    validate_profile(data, source=str(path))
    data["_path"] = str(path)
    return data


def list_profiles(profiles_dir: str | Path | None = None) -> list[dict]:
    """Return {'slug', 'name', 'path'} for every profile in the directory."""
    directory = Path(profiles_dir) if profiles_dir else config.DEFAULT_PROFILES_DIR
    found = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
            try:
                profile = load_profile(path)
            except ProfileError:
                continue
            found.append(
                {"slug": profile["slug"], "name": profile.get("name", profile["slug"]), "path": str(path)}
            )
    return found


def validate_profile(data: dict, source: str = "<profile>") -> None:
    """Raise ProfileError if the profile dict is structurally invalid."""
    if not isinstance(data, dict):
        raise ProfileError(f"{source}: profile must be a mapping")
    for key in ("slug", "criteria"):
        if key not in data:
            raise ProfileError(f"{source}: missing required key {key!r}")
    criteria = data["criteria"]
    if not isinstance(criteria, dict):
        raise ProfileError(f"{source}: 'criteria' must be a mapping")
    for key in REQUIRED_CRITERIA:
        if key not in criteria:
            raise ProfileError(f"{source}: criteria missing required key {key!r}")
        if not isinstance(criteria[key], (int, float)):
            raise ProfileError(f"{source}: criteria.{key} must be a number")
    if criteria["min_year"] > config.CURRENT_YEAR + 1:
        raise ProfileError(f"{source}: criteria.min_year is in the future")
    for key in ("max_price", "max_mileage_km", "max_distance_km"):
        if criteria[key] <= 0:
            raise ProfileError(f"{source}: criteria.{key} must be positive")

    scoring = data.get("scoring", {})
    weights = scoring.get("weights", {}) if isinstance(scoring, dict) else {}
    if weights:
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ProfileError(f"{source}: scoring.weights must sum to 1.0 (got {total:.2f})")
        for name, weight in weights.items():
            if not 0 <= weight <= 1:
                raise ProfileError(f"{source}: scoring.weights.{name} must be between 0 and 1")

    alerts = data.get("alerts", {})
    if isinstance(alerts, dict) and "min_score" in alerts:
        if not 0 <= alerts["min_score"] <= 100:
            raise ProfileError(f"{source}: alerts.min_score must be between 0 and 100")
