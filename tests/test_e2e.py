import pytest
from conftest import DATE

from rpkispool.main import main


@pytest.fixture
def run(capsys, data_dir):
    """Run the CLI through main() on the fixture and return stdout; main exits with status 1 on failure."""

    def _run(*args):
        main(["--output-dir", str(data_dir), "--date", DATE, *args])
        return capsys.readouterr().out

    return _run


def test_verify(run):
    out = run("verify")
    assert out.count("OK  ") == 3
    assert "FAIL" not in out


def test_coverage_vantage_points(run):
    out = run("coverage", "vantage-points")
    assert "Vantage point" in out
    assert "Total unique repos   : 6" in out


def test_coverage_repositories(run):
    out = run("coverage", "repositories")
    assert "Repository" in out
    assert "ok" in out
    assert "--" in out  # a repository missing at some vantage point


def test_coverage_missing(run):
    lines = run("coverage", "missing").splitlines()
    assert lines
    assert all(len(line.split("\t")) == 2 for line in lines)
