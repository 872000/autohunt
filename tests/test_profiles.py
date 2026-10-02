"""Tests for profile loading, validation and the mini-YAML fallback parser."""
import pytest

from autohunt import profiles
from autohunt.profiles import (
    ProfileError,
    _mini_yaml_load,
    list_profiles,
    load_profile,
    validate_profile,
)


def test_shipped_profiles_load():
    mustang = load_profile("profiles/mustang.yaml")
    suv = load_profile("profiles/family-suv.yaml")
    assert mustang["slug"] == "mustang"
    assert suv["slug"] == "family-suv"
    assert mustang["criteria"]["min_year"] == 2015
    assert suv["criteria"]["max_mileage_km"] == 90000
    assert "Kia" in suv["preferences"]["excluded_makes"]
    assert "Hyundai Sonata" in suv["preferences"]["excluded_models"]


def test_list_profiles_finds_both():
    found = {p["slug"] for p in list_profiles("profiles")}
    assert found == {"mustang", "family-suv"}


def test_load_missing_profile_raises():
    with pytest.raises(ProfileError):
        load_profile("profiles/does-not-exist.yaml")


def test_validate_rejects_missing_criteria_key():
    with pytest.raises(ProfileError):
        validate_profile({"slug": "x", "criteria": {"min_year": 2015}})


def test_validate_rejects_bad_weights():
    with pytest.raises(ProfileError):
        validate_profile({
            "slug": "x",
            "criteria": {"min_year": 2015, "max_price": 1, "max_mileage_km": 1,
                         "max_distance_km": 1},
            "scoring": {"weights": {"price": 0.9, "mileage": 0.9}},
        })


def test_validate_rejects_future_min_year():
    with pytest.raises(ProfileError):
        validate_profile({
            "slug": "x",
            "criteria": {"min_year": 2040, "max_price": 1, "max_mileage_km": 1,
                         "max_distance_km": 1},
        })


def test_mini_yaml_subset():
    text = """
# a comment
slug: test
count: 3
price: 19.99
enabled: true
disabled: no
nothing: null
quoted: "hello: world"
home:
  city: Hamilton
  province: ON
makes:
  - Ford
  - Toyota
models: []
inline: [a, b, c]
"""
    data = _mini_yaml_load(text)
    assert data["slug"] == "test"
    assert data["count"] == 3
    assert data["price"] == 19.99
    assert data["enabled"] is True
    assert data["disabled"] is False
    assert data["nothing"] is None
    assert data["quoted"] == "hello: world"
    assert data["home"] == {"city": "Hamilton", "province": "ON"}
    assert data["makes"] == ["Ford", "Toyota"]
    assert data["models"] == []
    assert data["inline"] == ["a", "b", "c"]


def test_mini_yaml_rejects_tabs_and_garbage():
    with pytest.raises(ProfileError):
        _mini_yaml_load("slug: x\n\tbad: 1\n")
    with pytest.raises(ProfileError):
        _mini_yaml_load("slug: x\nnot a mapping line\n")


def test_profile_loads_without_pyyaml(monkeypatch):
    """The bundled parser must handle the real profiles when PyYAML is absent."""
    monkeypatch.setattr(profiles, "_pyyaml", None)
    profile = load_profile("profiles/mustang.yaml")
    assert profile["slug"] == "mustang"
    assert profile["criteria"]["makes"] == ["Ford"]


def test_validate_rejects_nonpositive_criteria():
    with pytest.raises(ProfileError):
        validate_profile({
            "slug": "x",
            "criteria": {"min_year": 2015, "max_price": -5000, "max_mileage_km": 1,
                         "max_distance_km": 1},
        })
