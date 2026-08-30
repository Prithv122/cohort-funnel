from __future__ import annotations

import pytest

from cohortfunnel import __version__, cli


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("wh") / "cohorts.duckdb"
    assert cli.main(["--database", str(path), "build"]) == 0
    return str(path)


def test_version_is_set():
    assert __version__


def test_build_reports_row_count(database, capsys):
    assert "events" in capsys.readouterr().out or True  # build ran in the fixture
    assert cli.main(["--database", database, "build"]) == 0
    assert "events" in capsys.readouterr().out


def test_retention_command(database, capsys):
    assert cli.main(["--database", database, "retention", "--max-periods", "4"]) == 0
    out = capsys.readouterr().out
    assert "Blended curve" in out
    assert "cohort" in out


def test_funnel_command_with_filters(database, capsys):
    code = cli.main(
        ["--database", database, "funnel", "--channel", "referral", "--window-hours", "72"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "signup" in out
    assert "72.0h from entry" in out


def test_compare_command(database, capsys):
    assert cli.main(["--database", database, "compare"]) == 0
    assert "overcount" in capsys.readouterr().out


def test_missing_warehouse_is_a_clean_error(tmp_path, capsys):
    code = cli.main(["--database", str(tmp_path / "nope.duckdb"), "funnel"])
    assert code == 2
    assert "Build it first" in capsys.readouterr().err


def test_bad_filter_column_is_a_clean_error(database, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_filters", lambda args: {"user_id": ["u1"]})
    assert cli.main(["--database", database, "funnel"]) == 2
    assert "Not a filterable column" in capsys.readouterr().err
