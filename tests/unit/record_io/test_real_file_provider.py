# pyright: standard
"""The record provider opens a file only at the path the run gives its name."""

from pathlib import Path
from types import MappingProxyType

from cobol_asg.file_enums import FileOrganization, OpenMode
from interpreter.func_name import FuncName
from interpreter.record_io.access_result import AccessCondition
from interpreter.record_io.file_frame import FileFrame
from interpreter.record_io.prime_key import PrimeKey
from interpreter.record_io.real_file_provider import RealFileProvider
from interpreter.record_io.run_inputs import RunInputs
from interpreter.types.typed_value import typed
from tests.covers import NotLanguageFeature, covers

DECLARE = FuncName("__cobol_declare_file")
OPEN = FuncName("__cobol_open_file")


def _opened(provider: RealFileProvider, name: str) -> AccessCondition:
    frame = FileFrame(name, FileOrganization.SEQUENTIAL, PrimeKey(), False, 80)
    provider.handle_call(DECLARE, [typed(frame.data()), typed("")])
    return provider.handle_call(
        OPEN, [typed(name), typed(OpenMode.OUTPUT.value), typed("")]
    ).condition


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_output_open_succeeds_at_its_given_path_and_fails_for_a_name_without_one(
    tmp_path: Path,
):
    given = tmp_path / "out.dat"
    provider = RealFileProvider(
        RunInputs(path_overrides=MappingProxyType({"OUTDD": given}))
    )

    assert (
        _opened(provider, "OUTDD"),
        given.exists(),
        _opened(provider, "NODD"),
        sorted(p.name for p in tmp_path.iterdir()),
    ) == (AccessCondition.OK, True, AccessCondition.FILE_NOT_FOUND, ["out.dat"])
