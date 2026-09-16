"""SourceSpan parses from and serialises to the bridge's flat JSON keys."""

from cobol_asg.asg_types import CobolField, CobolParagraph, CobolSection
from cobol_asg.cobol_parser import make_cobol_parser
from cobol_asg.cobol_statements import (
    AlteredGoto,
    ComputedGoto,
    GotoStatement,
    IfStatement,
    ProcedureRef,
    SimpleGoto,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.source_spans import to_source_location
from interpreter.instructions import Const
from interpreter.ir import NO_SOURCE_LOCATION, SourceLocation
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


def _zoned_td(total_digits: int) -> CobolTypeDescriptor:
    return CobolTypeDescriptor(
        category=CobolDataCategory.ZONED_DECIMAL, total_digits=total_digits
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_reads_the_four_flat_keys():
    span = SourceSpan.from_dict(
        {"line_start": 7, "col_start": 11, "line_end": 7, "col_end": 21}
    )
    assert span == SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_returns_none_when_position_is_absent():
    """A bridge object with no ctx emits no position keys at all."""
    assert SourceSpan.from_dict({"type": "MOVE"}) is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_ignores_unrelated_keys():
    span = SourceSpan.from_dict(
        {"type": "MOVE", "line_start": 1, "col_start": 2, "line_end": 3, "col_end": 4}
    )
    assert span == SourceSpan(line_start=1, col_start=2, line_end=3, col_end=4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_into_round_trips_through_from_dict():
    original = SourceSpan(line_start=7, col_start=11, line_end=9, col_end=4)
    result: dict = {}
    original.write_into(result)
    assert result == {"line_start": 7, "col_start": 11, "line_end": 9, "col_end": 4}
    assert SourceSpan.from_dict(result) == original


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_carries_a_span():
    para = CobolParagraph.from_dict(
        {
            "name": "MAIN-PARA",
            "line_start": 12,
            "col_start": 7,
            "line_end": 18,
            "col_end": 11,
        }
    )
    assert para.span == SourceSpan(line_start=12, col_start=7, line_end=18, col_end=11)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_without_position_has_no_span():
    assert CobolParagraph.from_dict({"name": "MAIN-PARA"}).span is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_to_dict_keeps_the_flat_wire_format():
    """The JSON contract with the Java bridge must not change."""
    para = CobolParagraph.from_dict(
        {
            "name": "MAIN-PARA",
            "line_start": 12,
            "col_start": 7,
            "line_end": 18,
            "col_end": 11,
        }
    )
    assert para.to_dict() == {
        "name": "MAIN-PARA",
        "line_start": 12,
        "col_start": 7,
        "line_end": 18,
        "col_end": 11,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_to_dict_round_trips_the_span():
    """A field's span must survive to_dict/from_dict, same as a paragraph's."""
    field_obj = CobolField.from_dict(
        {
            "name": "WS-B",
            "level": 1,
            "pic": "9(4)",
            "usage": "DISPLAY",
            "offset": 0,
            "line_start": 5,
            "col_start": 7,
            "line_end": 5,
            "col_end": 32,
        }
    )
    result = field_obj.to_dict()
    assert result["line_start"] == 5
    assert result["col_start"] == 7
    assert result["line_end"] == 5
    assert result["col_end"] == 32
    assert CobolField.from_dict(result).span == field_obj.span


PROBE_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_data_division_field():
    """01 WS-B is declared on line 5 of PROBE_SOURCE."""
    asg = make_cobol_parser().parse(PROBE_SOURCE)
    (field,) = [f for f in asg.data_fields if f.name == "WS-B"]
    assert field.span is not None
    assert field.span.line_start == 5


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_layout_carries_the_declaring_line():
    """WS-B's FieldLayout knows it was declared on line 5."""
    asg = make_cobol_parser().parse(PROBE_SOURCE)
    layout = build_data_layout(asg.data_fields)
    fl = layout.fields["WS-B"]
    assert fl.span is not None
    assert fl.span.line_start == 5


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_index_items_are_deliberately_spanless():
    """Compiler-allocated index items correspond to no source text.

    OCCURS ... INDEXED BY IX is the only declaration IX ever gets, so the
    layout must actually contain an index item for this to assert anything.
    """
    from interpreter.cobol.data_layout import build_index_layout

    indexed_source = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IDXPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TABLE.
          05 WS-ROW PIC X(4) OCCURS 3 TIMES INDEXED BY IX.
       PROCEDURE DIVISION.
           STOP RUN.
"""
    asg = make_cobol_parser().parse(indexed_source)
    index_layout = build_index_layout(asg.data_fields)
    assert index_layout.fields, "expected an index item for IX"
    assert all(fl.span is None for fl in index_layout.fields.values())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_maps_transposed_field_names():
    """SourceSpan says line_start; SourceLocation says start_line."""
    loc = to_source_location(
        SourceSpan(line_start=7, col_start=11, line_end=9, col_end=4)
    )
    assert loc == SourceLocation(start_line=7, start_col=11, end_line=9, end_col=4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_of_none_is_the_unknown_location():
    assert to_source_location(None) == NO_SOURCE_LOCATION
    assert to_source_location(None).is_unknown()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_emit_inst_stamps_the_span(cobol_emit_context):
    ctx = cobol_emit_context
    ctx.emit_inst(
        Const.int_(Register("%r0"), 1),
        span=SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21),
    )
    assert ctx.instructions[-1].source_location == SourceLocation(
        start_line=7, start_col=11, end_line=7, end_col=21
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_emit_inst_without_a_span_is_unknown(cobol_emit_context):
    ctx = cobol_emit_context
    ctx.emit_inst(Const.int_(Register("%r0"), 1))
    assert ctx.instructions[-1].source_location.is_unknown()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_explicit_location_on_the_instruction_wins(cobol_emit_context):
    """Matches frontends/context.py:219-222 — explicit beats resolved."""
    ctx = cobol_emit_context
    explicit = SourceLocation(start_line=1, start_col=2, end_line=3, end_col=4)
    ctx.emit_inst(
        Const.int_(Register("%r0"), 1, source_location=explicit),
        span=SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21),
    )
    assert ctx.instructions[-1].source_location == explicit


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_const_to_reg_stamps_the_span(cobol_emit_context):
    ctx = cobol_emit_context
    span = SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21)
    ctx.const_to_reg("42", span=span)
    assert ctx.instructions[-1].source_location.start_line == 7


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inline_ir_stamps_every_instruction_it_inlines(cobol_emit_context):
    """The ir_encoders builders emit into detached lists with no span of
    their own; inline_ir is where they acquire one."""
    ctx = cobol_emit_context
    span = SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21)
    before = len(ctx.instructions)
    ctx.emit_encode_numeric("WS_B", "42", _zoned_td(4), span=span)
    emitted = ctx.instructions[before:]
    assert len(emitted) > 5, "expected an inlined encoder body"
    assert all(i.source_location.start_line == 7 for i in emitted)


SECTION_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SECTPGM.
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_section():
    """MAIN-SECTION SECTION is declared on line 4 of SECTION_SOURCE."""
    asg = make_cobol_parser().parse(SECTION_SOURCE)
    (section,) = [s for s in asg.sections if s.name == "MAIN-SECTION"]
    assert isinstance(section, CobolSection)
    assert section.span is not None
    assert section.span.line_start == 4


IF_BRANCH_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IFBRANCH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           IF WS-A > 0
               MOVE 7 TO WS-B
           ELSE
               MOVE 9 TO WS-B
           END-IF.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_if_branch_statements_carry_their_own_spans():
    """THEN-branch MOVE is on line 9, ELSE-branch MOVE on line 11."""
    asg = make_cobol_parser().parse(IF_BRANCH_SOURCE)
    if_stmt = asg.statements[0]
    assert isinstance(if_stmt, IfStatement)
    assert if_stmt.span is not None and if_stmt.span.line_start == 8
    (then_move,) = if_stmt.children
    (else_move,) = if_stmt.else_children
    assert then_move.span is not None and then_move.span.line_start == 9
    assert else_move.span is not None and else_move.span.line_start == 11


GOTO_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GOTOPGM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-I PIC 9 VALUE 1.
       PROCEDURE DIVISION.
       PARA-A.
           GO TO PARA-B.
       PARA-B.
           GO TO PARA-C PARA-D DEPENDING ON WS-I.
       PARA-C.
           STOP RUN.
       PARA-D.
           STOP RUN.
"""


def _goto_in(paragraph_name: str) -> GotoStatement:
    asg = make_cobol_parser().parse(GOTO_SOURCE)
    (para,) = [p for p in asg.paragraphs if p.name == paragraph_name]
    (stmt,) = para.statements
    assert isinstance(stmt, GotoStatement)
    return stmt


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_simple_goto():
    """GO TO PARA-B is on line 8 of GOTO_SOURCE."""
    stmt = _goto_in("PARA-A")
    assert isinstance(stmt.form, SimpleGoto)
    assert stmt.span is not None
    assert stmt.span.line_start == 8


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_computed_goto():
    """GO TO ... DEPENDING ON is on line 10 of GOTO_SOURCE."""
    stmt = _goto_in("PARA-B")
    assert isinstance(stmt.form, ComputedGoto)
    assert stmt.span is not None
    assert stmt.span.line_start == 10


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_altered_goto_from_dict_reads_the_span():
    """The bridge cannot be made to emit the altered form from real source:
    ProLeap drops a bare ``GO TO.`` entirely and parses ``GO TO MORE-LABELS``
    as a DEPENDING ON statement with no targets. So this reads the bridge's
    wire shape for the altered form directly."""
    stmt = GotoStatement.from_dict(
        {
            "type": "GOTO",
            "form": "altered",
            "line_start": 14,
            "col_start": 11,
            "line_end": 14,
            "col_end": 15,
        }
    )
    assert isinstance(stmt.form, AlteredGoto)
    assert stmt.span == SourceSpan(line_start=14, col_start=11, line_end=14, col_end=15)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_goto_to_dict_round_trips_the_span_for_every_form():
    span = SourceSpan(line_start=8, col_start=11, line_end=8, col_end=17)
    target = ProcedureRef(paragraph="PARA-B", section="")
    forms = (
        SimpleGoto(target=target),
        ComputedGoto(targets=(target,), index=RefModOperand(name="WS-I")),
        AlteredGoto(),
    )
    lost = [
        type(form).__name__
        for form in forms
        if GotoStatement.from_dict(GotoStatement(form=form, span=span).to_dict())
        != GotoStatement(form=form, span=span)
    ]
    assert lost == [], f"GO TO forms that lost their span on round-trip: {lost}"


DECLARATIVES_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DECLPGM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO 'IN.DAT'
               ORGANIZATION IS SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD IN-FILE.
       01 IN-REC PIC X(10).
       PROCEDURE DIVISION.
       DECLARATIVES.
       IO-ERR SECTION.
           USE AFTER ERROR PROCEDURE ON IN-FILE.
       IO-ERR-PARA.
           DISPLAY 'ERR'.
       END DECLARATIVES.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_declarative_section():
    """IO-ERR SECTION is declared on line 14 of DECLARATIVES_SOURCE, inside
    the DECLARATIVES block."""
    asg = make_cobol_parser().parse(DECLARATIVES_SOURCE)
    (section,) = [s for s in asg.declaratives if s.name == "IO-ERR"]
    assert section.use is not None, "expected the USE AFTER ERROR clause"
    assert section.span is not None
    assert section.span.line_start == 14
