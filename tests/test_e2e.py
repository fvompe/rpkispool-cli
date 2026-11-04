from conftest import DATE

from rpkispool.main import main


def test_verify_and_coverage_end_to_end(capsys, data_dir):
    def run(*args):
        main(["--output-dir", str(data_dir), "--date", DATE, *args])  # exits with status 1 on failure
        return capsys.readouterr().out

    out = run("verify")
    assert out.count("OK  ") == 3
    assert "FAIL" not in out

    assert "Total unique repos   : 6" in run("coverage", "vantage-points")
    assert "ok" in run("coverage", "repositories")
    assert run("coverage", "missing").strip()
