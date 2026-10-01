"""Tests for the HTML report generator."""
import pytest

from autohunt.report import generate_report
from autohunt.scoring import rank


def test_report_is_self_contained_html(tmp_path, mustang_profile, demo_listings):
    ranked = rank(mustang_profile, demo_listings)
    out = tmp_path / "report.html"
    path = generate_report(mustang_profile, ranked, [], out)
    assert path.exists()
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "AutoHunt" in html
    assert "2017 Ford Mustang Convertible" in html  # top deal present
    assert "HOT DEAL" in html
    # inline styles only — no external assets
    assert 'rel="stylesheet"' not in html
    assert "<script" not in html


def test_report_with_no_matches(tmp_path, mustang_profile):
    out = tmp_path / "empty.html"
    generate_report(mustang_profile, [], [], out)
    assert "No matching listings" in out.read_text(encoding="utf-8")


def test_report_chart_embedded_when_matplotlib_present(tmp_path, mustang_profile, demo_listings):
    pytest.importorskip("matplotlib")
    ranked = rank(mustang_profile, demo_listings)
    out = tmp_path / "chart.html"
    generate_report(mustang_profile, ranked, [], out)
    assert "data:image/png;base64" in out.read_text(encoding="utf-8")
