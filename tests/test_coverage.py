import pytest
from conftest import DATE

from rpkispool.main import main


def run(capsys, data_dir, *args):
    main(["--output-dir", str(data_dir), "--date", DATE, "coverage", *args])
    return capsys.readouterr().out


def test_missing_lists_the_gap(capsys, data_dir):
    lines = run(capsys, data_dir, "missing").splitlines()
    assert lines  # the first repositories are not at every vantage point
    assert all(len(line.split("\t")) == 2 for line in lines)


def test_missing_fail_exits_with_status_1(data_dir):
    with pytest.raises(SystemExit) as e:
        main(["--output-dir", str(data_dir), "--date", DATE, "coverage", "missing", "--fail"])
    assert e.value.code == 1


def test_vantage_points_short_and_full(capsys, data_dir):
    short = run(capsys, data_dir, "vantage-points")
    assert "Total unique repos   : 6" in short
    assert "1: " in short  # count of missing repos, then names

    full = run(capsys, data_dir, "vantage-points", "--full")
    assert "Total unique repos   : 6" in full
    assert "..." not in full


def test_repositories_matrix(capsys, data_dir):
    out = run(capsys, data_dir, "repositories")
    assert "--" in out  # the gap
    assert "ok" in out
