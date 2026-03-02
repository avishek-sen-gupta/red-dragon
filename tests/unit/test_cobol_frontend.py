"""Tests for COBOL frontend — Data Division and Procedure Division lowering."""

from typing import Any

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolField,
    CobolParagraph,
    CobolStatement,
)
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.ir import IRInstruction, Opcode


class _FakeParser:
    """Fake parser that returns a pre-built CobolASG."""

    def __init__(self, asg: CobolASG):
        self._asg = asg

    def parse(self, source: bytes) -> CobolASG:
        return self._asg


def _find_opcodes(
    instructions: list[IRInstruction], opcode: Opcode
) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestDataDivisionLowering:
    def test_alloc_region_size(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        allocs = _find_opcodes(instructions, Opcode.ALLOC_REGION)
        assert len(allocs) == 1
        assert allocs[0].operands[0] == 5  # 5 bytes for 9(5)

    def test_initial_value_encoding(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A",
                    level=77,
                    pic="9(3)",
                    usage="DISPLAY",
                    offset=0,
                    value="123",
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1  # At least one WRITE_REGION for initial value

    def test_entry_label_emitted(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert "entry" in label_names

    def test_group_field_total_bytes(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-REC",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-A", level=5, pic="9(5)", usage="DISPLAY", offset=0
                        ),
                        CobolField(
                            name="WS-B", level=5, pic="X(3)", usage="DISPLAY", offset=5
                        ),
                    ],
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        allocs = _find_opcodes(instructions, Opcode.ALLOC_REGION)
        assert allocs[0].operands[0] == 8  # 5 + 3

    def test_multiple_fields_with_values(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A",
                    level=77,
                    pic="9(3)",
                    usage="DISPLAY",
                    offset=0,
                    value="1",
                ),
                CobolField(
                    name="WS-B",
                    level=77,
                    pic="X(5)",
                    usage="DISPLAY",
                    offset=0,
                    value="HELLO",
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # One for each field with a VALUE


class TestProcedureDivisionLowering:
    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatement],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(None, b"")

    def test_move_literal_to_field(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="MOVE", operands=["123", "WS-A"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce WRITE_REGION for the MOVE
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    def test_move_field_to_field(self):
        fields = [
            CobolField(
                name="WS-A",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="123",
            ),
            CobolField(name="WS-B", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="MOVE", operands=["WS-A", "WS-B"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce LOAD_REGION (decode WS-A) + WRITE_REGION (encode to WS-B)
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(loads) >= 1
        assert len(writes) >= 1

    def test_add_produces_binop(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
        ]
        stmts = [CobolStatement(type="ADD", operands=["5", "WS-A"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        add_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(add_ops) >= 1

    def test_subtract_produces_binop(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
        ]
        stmts = [CobolStatement(type="SUBTRACT", operands=["3", "WS-A"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        sub_ops = [b for b in binops if b.operands[0] == "-"]
        assert len(sub_ops) >= 1

    def test_if_produces_branch_if(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            CobolStatement(
                type="IF",
                condition="WS-A > 0",
                children=[
                    CobolStatement(type="DISPLAY", operands=["POSITIVE"]),
                ],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branches = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 1

    def test_display_literal(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="DISPLAY", operands=["HELLO WORLD"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    def test_display_field(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="42"
            ),
        ]
        stmts = [CobolStatement(type="DISPLAY", operands=["WS-A"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should LOAD_REGION to decode the field, then call print
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        assert len(loads) >= 1
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    def test_stop_run_produces_return(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="STOP_RUN")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        returns = _find_opcodes(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_goto_produces_branch(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="GOTO", operands=["OTHER-PARA"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        goto_branches = [
            b for b in branches if b.label and "para_OTHER-PARA" in b.label
        ]
        assert len(goto_branches) >= 1

    def test_perform_produces_set_continuation_and_branch(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="PERFORM", operands=["WORK-PARA"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit SET_CONTINUATION before the BRANCH
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1
        assert set_conts[0].operands[0] == "para_WORK-PARA_end"

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        perform_branches = [
            b for b in branches if b.label and "para_WORK-PARA" in b.label
        ]
        assert len(perform_branches) >= 1

    def test_paragraph_boundary_emits_resume_continuation(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="STOP_RUN")]

        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        resume_conts = _find_opcodes(instructions, Opcode.RESUME_CONTINUATION)
        assert len(resume_conts) >= 1
        resume_names = [inst.operands[0] for inst in resume_conts]
        assert "para_MAIN_end" in resume_names

    def test_perform_thru_sets_continuation_at_thru_endpoint(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            CobolStatement(type="PERFORM", operands=["FIRST-PARA"], thru="LAST-PARA")
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1
        # Continuation should be keyed to the THRU paragraph's end, not the start
        assert set_conts[0].operands[0] == "para_LAST-PARA_end"

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        perform_branches = [
            b for b in branches if b.label and "para_FIRST-PARA" in b.label
        ]
        assert len(perform_branches) >= 1

    def test_paragraph_label_emitted(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [CobolStatement(type="STOP_RUN")]

        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert "para_MAIN" in label_names
