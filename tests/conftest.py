import shutil
from pathlib import Path

import pytest

DATE = "20261103"
FIXTURES = Path(__file__).parent / "fixtures" / DATE


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A private copy of the fixture archives, safe to modify."""
    shutil.copytree(FIXTURES, tmp_path / "data")
    return tmp_path / "data"
