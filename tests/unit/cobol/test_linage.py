"""LINAGE: the clause and WRITE's ADVANCING and END-OF-PAGE phrases as the ASG reader
takes them, the LINAGE-COUNTER each such file declares, and the page state its WRITE
keeps."""

from __future__ import annotations

from cobol_asg.advancing_lines import AdvancingLines
from cobol_asg.advancing_page import AdvancingPage
from cobol_asg.advancing_position import AdvancingPosition
from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_expression import FieldRefNode, LiteralNode
from cobol_asg.cobol_statements import (
    DisplayStatement,
    FileControlEntry,
    FileDescription,
    NoRecordClause,
    WriteStatement,
)
from cobol_asg.file_enums import RecordingMode
from cobol_asg.linage_clause import LinageClause
from cobol_asg.no_footing import NO_FOOTING
from cobol_asg.no_linage import NO_LINAGE
from cobol_asg.storage_layout import section_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.file_state import file_state_of
from interpreter.cobol.linage_counters import (
    LINAGE_COUNTER_NAME,
    special_registers_layout,
)
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.lower_io import lower_write
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import StoreVar
from tests.covers import covers

_ZERO = LiteralNode("0", numeric=True)


@covers(CobolFeature.WRITE)
def test_linage_clause_and_write_phrases_are_read_from_bridge_json() -> None:
    fd = FileDescription.from_dict(
        {
            "fd_name": "P",
            "recording_mode": "",
            "record_clause": {"kind": "none"},
            "linage": {
                "lines": {"kind": "lit", "value": "50"},
                "footing": {"kind": "ref", "name": "F"},
                "bottom": {"kind": "lit", "value": "6"},
            },
        }
    )
    bare = FileDescription.from_dict(
        {"fd_name": "Q", "recording_mode": "", "record_clause": {"kind": "none"}}
    )
    write = WriteStatement.from_dict(
        {
            "type": "WRITE",
            "record_name": "P-REC",
            "advancing": {
                "position": "BEFORE",
                "kind": "LINES",
                "lines": {"kind": "ref", "name": "N"},
            },
            "at_end_of_page": [{"type": "DISPLAY", "operands": []}],
            "not_at_end_of_page": [],
        }
    )
    page = WriteStatement.from_dict(
        {
            "type": "WRITE",
            "record_name": "P-REC",
            "advancing": {"position": "AFTER", "kind": "PAGE"},
        }
    )
    plain = WriteStatement.from_dict({"type": "WRITE", "record_name": "P-REC"})
    assert fd.linage == LinageClause(
        lines=LiteralNode("50"),
        footing=FieldRefNode("F"),
        top=_ZERO,
        bottom=LiteralNode("6"),
    )
    assert FileDescription.from_dict(fd.to_dict()) == fd
    assert bare.linage == NO_LINAGE
    assert write.advancing == AdvancingLines(
        AdvancingPosition.BEFORE, FieldRefNode("N")
    )
    assert write.at_end_of_page == [DisplayStatement(operands=())]
    assert write.not_at_end_of_page == []
    assert page.advancing == AdvancingPage(AdvancingPosition.AFTER)
    assert plain.advancing == AdvancingLines(
        AdvancingPosition.AFTER, LiteralNode("1", numeric=True)
    )
    assert WriteStatement.from_dict(write.to_dict()) == write


def _description(name: str, linage: LinageClause) -> FileDescription:
    return FileDescription(
        name, RecordingMode.NOT_CODED, NoRecordClause(), linage=linage
    )


def _asg() -> CobolASG:
    return CobolASG(
        data_fields=section_layout(
            [CobolField(name="L", level=77, pic="999", usage="DISPLAY", offset=0)]
        ),
        file_control=[FileControlEntry(file_name="P"), FileControlEntry(file_name="R")],
        file_fields=section_layout(
            [
                CobolField(
                    name="P-REC", level=1, pic="X(4)", usage="DISPLAY", offset=0
                ),
                CobolField(
                    name="R-REC", level=1, pic="X(4)", usage="DISPLAY", offset=4
                ),
            ]
        ),
        file_record_to_select={"P-REC": "P", "R-REC": "R"},
        file_descriptions=[
            _description("P", LinageClause(lines=LiteralNode("50"))),
            _description(
                "Q", LinageClause(lines=FieldRefNode("L"), footing=NO_FOOTING)
            ),
            FileDescription("R", RecordingMode.NOT_CODED, NoRecordClause()),
        ],
    )


@covers(CobolFeature.WRITE)
def test_each_linage_file_declares_its_own_counter_after_return_code() -> None:
    """IBM Enterprise COBOL LR, LINAGE-COUNTER: one is generated for each FD with a
    LINAGE clause; for an integer it is a binary item of that integer's digits, for a
    data-name it has that data-name's PICTURE and USAGE."""
    layout = special_registers_layout(_asg())
    counters = {
        file: [
            (
                m.storage.offset,
                m.storage.byte_length,
                m.storage.type_descriptor.category.value,
                m.storage.type_descriptor.pic_string,
            )
            for m in layout.qualified_matches(LINAGE_COUNTER_NAME, (file,))
        ]
        for file in ("P", "Q", "R")
    }
    return_code = layout.lookup_or_raise("RETURN-CODE")
    assert (return_code.offset, return_code.byte_length) == (0, 2)
    assert counters == {
        "P": [(2, 2, "BINARY", "9(2)")],
        "Q": [(4, 3, "ZONED_DECIMAL", "999")],
        "R": [],
    }


def _stored_page_state(record: str) -> tuple[bool, bool]:
    asg = _asg()
    ctx = EmitContext(dispatch_fn=dispatch_statement, asg=asg)
    materialised = lower_sectioned_data_division(
        ctx, build_sectioned_layout(asg), "LIN"
    )
    lower_write(ctx, WriteStatement(record_name=record), materialised)
    state = file_state_of(asg, record.removesuffix("-REC"))
    stored = {i.name for i in ctx.instructions if isinstance(i, StoreVar)}
    return state.page_body in stored, state.page_footing in stored


@covers(CobolFeature.WRITE)
def test_only_a_linage_files_write_begins_new_pages() -> None:
    """A WRITE on a LINAGE file that overflows the page body begins the next page from
    the clause; a WRITE on any other file keeps no page."""
    assert _stored_page_state("P-REC") == (True, False)
    assert _stored_page_state("R-REC") == (False, False)
