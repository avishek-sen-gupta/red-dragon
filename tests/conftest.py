"""Every compile a test makes without a work directory lands in this session's own temp directory."""

import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _compiles_stay_in_the_session_temp_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    tempfile.tempdir = str(tmp_path_factory.mktemp("compile"))
    yield
    tempfile.tempdir = None
