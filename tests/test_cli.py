"""End-to-end CLI tests (isolated temp working directory + temp db)."""
import pytest

from autohunt.cli import main


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(workdir, *argv):
    db = workdir / "test.db"
    return main(["--db", str(db), *argv])


def test_profiles_command(workdir, capsys):
    assert run(workdir, "profiles") == 0
    out = capsys.readouterr().out
    assert "mustang" in out and "family-suv" in out


def test_fetch_list_check_report_flow(workdir, capsys):
    assert run(workdir, "fetch", "--profile", "mustang") == 0
    assert "18 listings" in capsys.readouterr().out

    assert run(workdir, "list", "--profile", "mustang", "--min-score", "60") == 0
    out = capsys.readouterr().out
    assert "HOT DEAL" in out

    assert run(workdir, "check", "--profile", "mustang") == 0
    out = capsys.readouterr().out
    assert "NEW DEAL" in out

    # second check: nothing new
    assert run(workdir, "check", "--profile", "mustang") == 0
    assert "No new alerts" in capsys.readouterr().out

    out_path = workdir / "report.html"
    assert run(workdir, "report", "--profile", "mustang",
               "--output", str(out_path)) == 0
    assert out_path.exists()


def test_watch_flow_fires_target_alert(workdir, capsys):
    assert run(workdir, "fetch", "--profile", "mustang") == 0
    capsys.readouterr()
    assert run(workdir, "watch", "demo-mustang-09", "--target-price", "12000") == 0
    assert "Watching" in capsys.readouterr().out

    assert run(workdir, "watched") == 0
    assert "demo-mustang-09" in capsys.readouterr().out

    assert run(workdir, "check", "--profile", "mustang") == 0
    assert "WATCH TARGET HIT" in capsys.readouterr().out

    assert run(workdir, "unwatch", "demo-mustang-09") == 0


def test_watch_unknown_listing_fails(workdir):
    assert run(workdir, "watch", "no-such-id") == 2


def test_unknown_profile_fails(workdir):
    assert run(workdir, "fetch", "--profile", "nope") == 2


def test_source_fallback_to_demo(workdir, capsys):
    # Live sources are unavailable in this environment; the CLI must fall back.
    assert run(workdir, "fetch", "--profile", "mustang", "--source", "autotrader") == 0
    err = capsys.readouterr().err
    assert "falling back to bundled demo data" in err


def test_demo_runs_end_to_end(workdir, capsys):
    assert main(["demo"]) == 0  # uses default .autohunt dir under tmp cwd
    out = capsys.readouterr().out
    assert "Demo complete" in out
    assert (workdir / ".autohunt" / "reports" / "report-mustang.html").exists()
    assert (workdir / ".autohunt" / "reports" / "report-family-suv.html").exists()
