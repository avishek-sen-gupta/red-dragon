"""Which USE declaratives an I-O condition on a file can select, in order of precedence
(red-dragon-ljku.4): the program's own, a file-named one before those for an open
mode; then each containing program's USE GLOBAL ones, the nearest first, a file-named
one only when it names the same file connector."""

from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.use_selection import UseProcedure, use_procedures
from tests.covers import covers


def _use(name: str, target: str, is_global: bool, files: tuple[str, ...] = ()) -> dict:
    return {
        "name": name,
        "use": {"global": is_global, "target": target, "files": list(files)},
    }


def _fd(name: str, is_global: bool) -> dict:
    return {
        "fd_name": name,
        "recording_mode": "",
        "record_clause": {"kind": "none"},
        "global": is_global,
    }


_OUTER = {
    "program_id": "OUTER",
    "file_control": [{"file_name": "F"}],
    "file_descriptions": [_fd("F", True)],
    "declaratives": [
        _use("OUTER-ON-F", "FILE", True, ("F",)),
        _use("OUTER-INPUT", "INPUT", True),
        _use("OUTER-LOCAL", "OUTPUT", False),
    ],
}
_MIDDLE = {
    "program_id": "MIDDLE",
    "declaratives": [
        _use("MIDDLE-ON-F", "FILE", False, ("F",)),
        _use("MIDDLE-OUTPUT", "OUTPUT", True),
    ],
}


def _inner(**own: Sequence[dict]) -> CobolASG:
    return CobolASG.from_dict(
        {"program_id": "INNER", "enclosing": [_MIDDLE, _OUTER]}
        | {section: list(items) for section, items in own.items()}
    )


@covers(CobolFeature.USE_GLOBAL, CobolFeature.DECLARATIVES)
def test_use_declaratives_are_ranked_own_first_then_containing_global_ones():
    own_mode = _inner(declaratives=[_use("INNER-IO", "I-O", False)])
    own_file = _inner(
        file_control=[{"file_name": "F"}],
        declaratives=[_use("INNER-ON-F", "FILE", False, ("F",))],
    )
    own_connector = _inner(file_control=[{"file_name": "F"}])

    assert (
        use_procedures(own_mode, "F"),
        use_procedures(own_file, "F"),
        use_procedures(own_connector, "F"),
    ) == (
        (
            UseProcedure("INNER", "INNER-IO", "I-O"),
            UseProcedure("MIDDLE", "MIDDLE-OUTPUT", "OUTPUT"),
            UseProcedure("OUTER", "OUTER-ON-F", ""),
        ),
        (UseProcedure("INNER", "INNER-ON-F", ""),),
        (
            UseProcedure("MIDDLE", "MIDDLE-OUTPUT", "OUTPUT"),
            UseProcedure("OUTER", "OUTER-INPUT", "INPUT"),
        ),
    )
