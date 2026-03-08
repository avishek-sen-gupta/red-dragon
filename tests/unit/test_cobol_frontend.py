"""Tests for COBOL frontend — Data Division and Procedure Division lowering."""

from typing import Any

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolField,
    CobolParagraph,
    CobolSection,
)
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_statements import (
    AcceptStatement,
    AlterStatement,
    AlterProceedTo,
    ArithmeticStatement,
    CallStatement,
    CallUsingParam,
    CancelStatement,
    CloseStatement,
    CobolStatementType,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EntryStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveStatement,
    OpenStatement,
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    ReadStatement,
    Replacing,
    SearchStatement,
    SearchWhen,
    SetStatement,
    StopRunStatement,
    StringSending,
    StringStatement,
    TallyingFor,
    UnstringStatement,
    WriteStatement,
    RewriteStatement,
    StartStatement,
    DeleteStatement,
)
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
        instructions = frontend.lower(b"")

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
        instructions = frontend.lower(b"")

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 1  # Exactly one WRITE_REGION for initial value
        # Verify the write contains encoded bytes for "123"
        write_bytes = [w.operands for w in writes]
        assert any(
            isinstance(ops, list) and len(ops) >= 2 for ops in write_bytes
        ), f"WRITE_REGION should have region + data operands, got {write_bytes}"

    def test_entry_label_emitted(self):
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

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
        instructions = frontend.lower(b"")

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
        instructions = frontend.lower(b"")

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 2  # One for each field with a VALUE


class TestProcedureDivisionLowering:
    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_move_literal_to_field(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [MoveStatement(source="123", target="WS-A")]
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
        stmts = [MoveStatement(source="WS-A", target="WS-B")]
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
        stmts = [ArithmeticStatement(op="ADD", source="5", target="WS-A")]
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
        stmts = [ArithmeticStatement(op="SUBTRACT", source="3", target="WS-A")]
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
            IfStatement(
                condition="WS-A > 0",
                children=[
                    DisplayStatement(operand="POSITIVE"),
                ],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branches = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 1

    def test_if_else_produces_two_branches(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            IfStatement(
                condition="WS-A > 0",
                children=[DisplayStatement(operand="POSITIVE")],
                else_children=[DisplayStatement(operand="NOT-POSITIVE")],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have BRANCH_IF
        branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 1

        # Should have two print calls (one for THEN, one for ELSE)
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) == 2

        # Should have three labels: if_true, if_false, if_end
        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert any("if_true" in l for l in label_names)
        assert any("if_false" in l for l in label_names)
        assert any("if_end" in l for l in label_names)

    def test_if_without_else_has_empty_false_branch(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            IfStatement(
                condition="WS-A > 0",
                children=[DisplayStatement(operand="ONLY-THEN")],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Only one print call (THEN branch only)
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) == 1

    def test_display_literal(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [DisplayStatement(operand="HELLO WORLD")]
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
        stmts = [DisplayStatement(operand="WS-A")]
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
        stmts = [StopRunStatement()]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        returns = _find_opcodes(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    def test_goto_produces_branch(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [GotoStatement(target="OTHER-PARA")]
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
        stmts = [PerformStatement(target="WORK-PARA")]
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
        stmts = [StopRunStatement()]

        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        resume_conts = _find_opcodes(instructions, Opcode.RESUME_CONTINUATION)
        assert len(resume_conts) >= 1
        resume_names = [inst.operands[0] for inst in resume_conts]
        assert "para_MAIN_end" in resume_names

    def test_perform_thru_sets_continuation_at_thru_endpoint(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [PerformStatement(target="FIRST-PARA", thru="LAST-PARA")]
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
        stmts = [StopRunStatement()]

        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert "para_MAIN" in label_names


class TestComputeLowering:
    """Tests for COMPUTE statement IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_compute_simple_addition(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
            CobolField(
                name="WS-B", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="5"
            ),
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=6,
                value="0",
            ),
        ]
        stmts = [ComputeStatement(expression="WS-A + WS-B", targets=["WS-RESULT"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        add_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(add_ops) >= 1

        # Should decode both fields
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        assert len(loads) >= 2  # WS-A and WS-B

        # Should write to WS-RESULT
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    def test_compute_with_precedence(self):
        """COMPUTE WS-RESULT = WS-A + WS-B * 2 → WS-A + (WS-B * 2)."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
            CobolField(
                name="WS-B", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="5"
            ),
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=6,
                value="0",
            ),
        ]
        stmts = [ComputeStatement(expression="WS-A + WS-B * 2", targets=["WS-RESULT"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # The WRITE_REGION for the target comes after expr evaluation.
        # The expression BINOPs (the last 2 before the str conversion) should be * then +.
        # Extract the last 2 BINOPs with arithmetic operators before the final CALL_FUNCTION "str".
        all_binops = _find_opcodes(instructions, Opcode.BINOP)
        arith_ops = [
            b.operands[0] for b in all_binops if b.operands[0] in ("+", "-", "*", "/")
        ]
        # Last two arithmetic BINOPs are from the expression: * (higher prec) then +
        assert arith_ops[-2:] == ["*", "+"]

    def test_compute_with_parentheses(self):
        """COMPUTE WS-RESULT = (WS-A + WS-B) * 3 → + before *."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
            CobolField(
                name="WS-B", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="5"
            ),
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=6,
                value="0",
            ),
        ]
        stmts = [
            ComputeStatement(expression="(WS-A + WS-B) * 3", targets=["WS-RESULT"])
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # The expression BINOPs should be + then * (parentheses override precedence)
        all_binops = _find_opcodes(instructions, Opcode.BINOP)
        arith_ops = [
            b.operands[0] for b in all_binops if b.operands[0] in ("+", "-", "*", "/")
        ]
        # Last two arithmetic BINOPs: + (inside parens, evaluated first) then *
        assert arith_ops[-2:] == ["+", "*"]

    def test_compute_multiple_targets(self):
        """COMPUTE writes result to all target fields."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
            CobolField(
                name="WS-C", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="0"
            ),
            CobolField(
                name="WS-D", level=77, pic="9(3)", usage="DISPLAY", offset=6, value="0"
            ),
        ]
        stmts = [ComputeStatement(expression="WS-A * 5", targets=["WS-C", "WS-D"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have WRITE_REGION for initial values (3 fields) + 2 COMPUTE targets
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert (
            len(writes) >= 4
        )  # 3 initial values (WS-A="100", WS-C="0", WS-D="0") + 2 COMPUTE targets

    def test_compute_literal_expression(self):
        """COMPUTE with only literals (no field references)."""
        fields = [
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="0",
            ),
        ]
        stmts = [ComputeStatement(expression="10 + 5", targets=["WS-RESULT"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        add_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(add_ops) >= 1


class TestPerformLoopLowering:
    """Tests for PERFORM TIMES / UNTIL / VARYING IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
        paragraphs: list[CobolParagraph] = [],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)] + paragraphs,
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_perform_times_inline_emits_counter_loop(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operand="IN-LOOP")],
                spec=PerformTimesSpec(times="3"),
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit STORE_VAR (counter init), LOAD_VAR, BINOP >=, BRANCH_IF
        store_vars = _find_opcodes(instructions, Opcode.STORE_VAR)
        assert len(store_vars) >= 1  # counter init

        load_vars = _find_opcodes(instructions, Opcode.LOAD_VAR)
        assert len(load_vars) >= 1  # counter check

        binops = _find_opcodes(instructions, Opcode.BINOP)
        ge_ops = [b for b in binops if b.operands[0] == ">="]
        assert len(ge_ops) >= 1  # counter >= times

        branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 1

    def test_perform_times_procedure_emits_set_continuation_in_loop(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            PerformStatement(
                target="WORK-PARA",
                spec=PerformTimesSpec(times="2"),
            ),
        ]
        paragraphs = [
            CobolParagraph(
                name="WORK-PARA",
                statements=[DisplayStatement(operand="WORKING")],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts, paragraphs)

        # Should have SET_CONTINUATION inside the loop
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1

        # Should have counter logic
        store_vars = _find_opcodes(instructions, Opcode.STORE_VAR)
        assert len(store_vars) >= 1

    def test_perform_until_test_before_condition_first(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operand="LOOPING")],
                spec=PerformUntilSpec(condition="WS-A > 10", test_before=True),
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have BRANCH_IF for condition check
        branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) >= 1

        # Should have comparison BINOP
        binops = _find_opcodes(instructions, Opcode.BINOP)
        gt_ops = [b for b in binops if b.operands[0] == ">"]
        assert len(gt_ops) >= 1

        # TEST BEFORE: condition (BRANCH_IF) must appear before body (print call)
        branch_if_indices = [
            i for i, inst in enumerate(instructions) if inst.opcode == Opcode.BRANCH_IF
        ]
        print_indices = [
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and inst.operands[0] == "print"
        ]
        assert (
            branch_if_indices and print_indices
        ), "expected both BRANCH_IF and print calls"
        assert branch_if_indices[0] < print_indices[0], (
            f"TEST BEFORE: first condition (idx {branch_if_indices[0]}) "
            f"must precede first body (idx {print_indices[0]})"
        )

    def test_perform_until_test_after_body_first(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operand="LOOPING")],
                spec=PerformUntilSpec(condition="WS-A > 10", test_before=False),
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # For TEST AFTER, body comes before condition check
        # Find the print call (body) and the BRANCH_IF (condition)
        all_ops = [(i, inst.opcode) for i, inst in enumerate(instructions)]
        print_indices = [
            i
            for i, inst in enumerate(instructions)
            if inst.opcode == Opcode.CALL_FUNCTION
            and inst.operands
            and inst.operands[0] == "print"
        ]
        branch_if_indices = [
            i for i, inst in enumerate(instructions) if inst.opcode == Opcode.BRANCH_IF
        ]
        # At least one of the print calls should come before the BRANCH_IF
        assert (
            print_indices and branch_if_indices
        ), "expected both print calls and BRANCH_IF"
        assert print_indices[0] < branch_if_indices[0], (
            f"TEST AFTER: first body (idx {print_indices[0]}) "
            f"must precede first condition (idx {branch_if_indices[0]})"
        )

    def test_perform_varying_inline_emits_init_and_increment(self):
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="0",
            ),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operand="VARYING-LOOP")],
                spec=PerformVaryingSpec(
                    varying_var="WS-IDX",
                    varying_from="1",
                    varying_by="1",
                    condition="WS-IDX > 5",
                    test_before=True,
                ),
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have WRITE_REGION for init (FROM value) and for increment
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        # At least: initial field value + FROM init + increment encode back
        assert len(writes) >= 2

        # Should have BINOP + for increment
        binops = _find_opcodes(instructions, Opcode.BINOP)
        plus_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(plus_ops) >= 1


class TestSectionPerform:
    """Tests for section-level PERFORM."""

    def test_perform_section_branches_to_section_label(self):
        from interpreter.cobol.asg_types import CobolSection

        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[
                CobolParagraph(
                    name="MAIN",
                    statements=[
                        PerformStatement(target="WORK-SECTION"),
                        StopRunStatement(),
                    ],
                ),
            ],
            sections=[
                CobolSection(
                    name="WORK-SECTION",
                    paragraphs=[
                        CobolParagraph(
                            name="WORK-PARA",
                            statements=[DisplayStatement(operand="IN-SECTION")],
                        ),
                    ],
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        # Should branch to section_WORK-SECTION
        branches = _find_opcodes(instructions, Opcode.BRANCH)
        section_branches = [
            b for b in branches if b.label and "section_WORK-SECTION" == b.label
        ]
        assert len(section_branches) >= 1

        # Should set continuation at section end
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        section_conts = [
            s for s in set_conts if s.operands[0] == "section_WORK-SECTION_end"
        ]
        assert len(section_conts) >= 1

    def test_section_emits_end_resume_continuation(self):
        from interpreter.cobol.asg_types import CobolSection

        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        asg = CobolASG(
            data_fields=fields,
            sections=[
                CobolSection(
                    name="MY-SECTION",
                    paragraphs=[
                        CobolParagraph(
                            name="PARA-A",
                            statements=[StopRunStatement()],
                        ),
                    ],
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        resume_conts = _find_opcodes(instructions, Opcode.RESUME_CONTINUATION)
        resume_names = [inst.operands[0] for inst in resume_conts]
        assert "section_MY-SECTION_end" in resume_names


class TestTier1Lowering:
    """Tests for CONTINUE, EXIT, INITIALIZE, SET IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_continue_emits_nothing(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [ContinueStatement()]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Only infrastructure instructions (LABEL, ALLOC_REGION, RESUME_CONTINUATION)
        # No CALL_FUNCTION, no WRITE_REGION for CONTINUE itself
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 0

    def test_exit_emits_nothing(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [ExitStatement()]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 0

    def test_initialize_numeric_field(self):
        fields = [
            CobolField(
                name="WS-A",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="123",
            ),
        ]
        stmts = [InitializeStatement(operands=["WS-A"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce WRITE_REGION: initial value + INITIALIZE reset
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial VALUE + INITIALIZE

    def test_initialize_alphanumeric_field(self):
        fields = [
            CobolField(
                name="WS-NAME",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=0,
                value="HELLO",
            ),
        ]
        stmts = [InitializeStatement(operands=["WS-NAME"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial VALUE + INITIALIZE

    def test_initialize_multiple_fields(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="1"
            ),
            CobolField(
                name="WS-B",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=3,
                value="ABC",
            ),
        ]
        stmts = [InitializeStatement(operands=["WS-A", "WS-B"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 4  # 2 initial values + 2 INITIALIZE resets

    def test_set_to_produces_write(self):
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="0",
            ),
        ]
        stmts = [SetStatement(set_type="TO", targets=["WS-IDX"], values=["5"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial VALUE + SET TO

    def test_set_by_up_produces_binop_plus(self):
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="5",
            ),
        ]
        stmts = [
            SetStatement(set_type="BY", targets=["WS-IDX"], values=["1"], by_type="UP")
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        plus_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(plus_ops) >= 1

    def test_set_by_down_produces_binop_minus(self):
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="5",
            ),
        ]
        stmts = [
            SetStatement(
                set_type="BY", targets=["WS-IDX"], values=["1"], by_type="DOWN"
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        minus_ops = [b for b in binops if b.operands[0] == "-"]
        assert len(minus_ops) >= 1


class TestTier2Lowering:
    """Tests for STRING, UNSTRING, INSPECT IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_string_produces_write_to_target(self):
        fields = [
            CobolField(
                name="WS-FIRST",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=0,
                value="JOHN",
            ),
            CobolField(
                name="WS-LAST",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=5,
                value="DOE",
            ),
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=10,
            ),
        ]
        stmts = [
            StringStatement(
                sendings=[
                    StringSending(value="WS-FIRST", delimited_by="SIZE"),
                    StringSending(value="WS-LAST", delimited_by="SIZE"),
                ],
                into="WS-RESULT",
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce WRITE_REGION for the STRING result
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        # 2 initial VALUE writes (WS-FIRST, WS-LAST) + at least 1 from STRING into WS-RESULT
        assert (
            len(writes) >= 3
        ), f"expected >= 3 WRITE_REGION (2 init + STRING), got {len(writes)}"

    def test_string_with_delimiter_calls_split(self):
        fields = [
            CobolField(
                name="WS-SRC",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=0,
                value="HELLO",
            ),
            CobolField(
                name="WS-OUT",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=10,
            ),
        ]
        stmts = [
            StringStatement(
                sendings=[
                    StringSending(value="WS-SRC", delimited_by=" "),
                ],
                into="WS-OUT",
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should use __string_split for delimiter handling
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        split_calls = [
            c for c in calls if c.operands and c.operands[0] == "__string_split"
        ]
        assert len(split_calls) >= 1

    def test_unstring_produces_split_and_writes(self):
        fields = [
            CobolField(
                name="WS-FULL",
                level=77,
                pic="X(20)",
                usage="DISPLAY",
                offset=0,
                value="JOHN DOE",
            ),
            CobolField(
                name="WS-FIRST",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=20,
            ),
            CobolField(
                name="WS-LAST",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=30,
            ),
        ]
        stmts = [
            UnstringStatement(
                source="WS-FULL",
                delimited_by=" ",
                into=["WS-FIRST", "WS-LAST"],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce __string_split call
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        split_calls = [
            c for c in calls if c.operands and c.operands[0] == "__string_split"
        ]
        assert len(split_calls) >= 1

        # Should produce WRITE_REGION for each INTO target
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial + 2 UNSTRING targets (initial has no value)

    def test_inspect_tallying_produces_count_and_write(self):
        fields = [
            CobolField(
                name="WS-DATA",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=0,
                value="ABCABC",
            ),
            CobolField(
                name="WS-COUNT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=10,
                value="0",
            ),
        ]
        stmts = [
            InspectStatement(
                inspect_type="TALLYING",
                source="WS-DATA",
                tallying_target="WS-COUNT",
                tallying_for=[TallyingFor(mode="ALL", pattern="A")],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should use __string_count
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        count_calls = [
            c for c in calls if c.operands and c.operands[0] == "__string_count"
        ]
        assert len(count_calls) >= 1

        # Should produce WRITE_REGION for tally target
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    def test_inspect_replacing_produces_replace_and_write(self):
        fields = [
            CobolField(
                name="WS-DATA",
                level=77,
                pic="X(10)",
                usage="DISPLAY",
                offset=0,
                value="AABAA",
            ),
        ]
        stmts = [
            InspectStatement(
                inspect_type="REPLACING",
                source="WS-DATA",
                replacings=[Replacing(mode="ALL", from_pattern="A", to_pattern="B")],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should use __string_replace
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        replace_calls = [
            c for c in calls if c.operands and c.operands[0] == "__string_replace"
        ]
        assert len(replace_calls) >= 1

        # Should write back to source field
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial VALUE + REPLACING write-back


class TestSearchLowering:
    """Tests for SEARCH IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_search_emits_loop_structure(self):
        """SEARCH should emit BRANCH_IF for bound check and WHEN conditions."""
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="1",
            ),
            CobolField(
                name="WS-VAL",
                level=77,
                pic="X(5)",
                usage="DISPLAY",
                offset=3,
                value="HELLO",
            ),
        ]
        stmts = [
            SearchStatement(
                table="WS-TABLE",
                varying="WS-IDX",
                whens=[
                    SearchWhen(
                        condition="WS-IDX = 5",
                        children=[DisplayStatement(operand="FOUND")],
                    )
                ],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit BRANCH_IF for the bound check + WHEN condition
        branches = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 2  # bound check + at least one WHEN

        # Should emit BRANCH for loop-back and exit
        jumps = _find_opcodes(instructions, Opcode.BRANCH)
        assert len(jumps) >= 1

        # Should emit labels for loop structure
        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [inst.label for inst in labels]
        assert any("search_loop" in name for name in label_names)
        assert any("search_end" in name for name in label_names)

    def test_search_with_varying_increments_index(self):
        """SEARCH VARYING should emit decode/increment/encode for the index."""
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="1",
            ),
        ]
        stmts = [
            SearchStatement(
                table="WS-TABLE",
                varying="WS-IDX",
                whens=[SearchWhen(condition="WS-IDX = 5")],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should write back the incremented index
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # initial VALUE + index increment write

    def test_search_at_end_emits_statements(self):
        """AT END clause should emit its child statements."""
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="1",
            ),
        ]
        stmts = [
            SearchStatement(
                table="WS-TABLE",
                whens=[SearchWhen(condition="WS-IDX = 5")],
                at_end=[DisplayStatement(operand="NOT FOUND")],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # AT END should produce CALL_FUNCTION for DISPLAY (uses "print")
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    def test_search_multiple_whens(self):
        """Multiple WHEN clauses should each get a BRANCH_IF."""
        fields = [
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="1",
            ),
        ]
        stmts = [
            SearchStatement(
                table="WS-TABLE",
                varying="WS-IDX",
                whens=[
                    SearchWhen(condition="WS-IDX = 3"),
                    SearchWhen(condition="WS-IDX = 7"),
                ],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit BRANCH_IF for bound check + 2 WHEN conditions
        branches = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 3


class TestCallAlterEntryCancelLowering:
    """Tests for CALL, ALTER, ENTRY, CANCEL IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: list[CobolStatementType],
    ) -> list[IRInstruction]:
        asg = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        return frontend.lower(b"")

    def test_call_emits_call_function(self):
        """CALL should emit CALL_FUNCTION with program name."""
        fields = [
            CobolField(
                name="WS-A",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="123",
            ),
        ]
        stmts = [
            CallStatement(
                program="SUBPROG",
                using=[CallUsingParam(name="WS-A", param_type="REFERENCE")],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        subprog_calls = [c for c in calls if c.operands and c.operands[0] == "SUBPROG"]
        assert len(subprog_calls) >= 1

    def test_call_with_giving_writes_result(self):
        """CALL with GIVING should write result to the giving field."""
        fields = [
            CobolField(
                name="WS-A",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=0,
                value="1",
            ),
            CobolField(
                name="WS-RESULT",
                level=77,
                pic="9(3)",
                usage="DISPLAY",
                offset=3,
                value="0",
            ),
        ]
        stmts = [
            CallStatement(
                program="CALC",
                using=[CallUsingParam(name="WS-A")],
                giving="WS-RESULT",
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should write back to WS-RESULT
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 3  # 2 initial VALUES + GIVING write-back

    def test_alter_emits_store_var(self):
        """ALTER should emit STORE_VAR for the altered paragraph target."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            AlterStatement(
                proceed_tos=[AlterProceedTo(source="PARA-1", target="PARA-2")]
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        stores = _find_opcodes(instructions, Opcode.STORE_VAR)
        alter_stores = [
            s for s in stores if s.operands and "__alter_PARA-1" in str(s.operands[0])
        ]
        assert len(alter_stores) >= 1

    def test_entry_emits_label(self):
        """ENTRY should emit a LABEL for the alternate entry point."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [EntryStatement(entry_name="ALT-ENTRY")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        labels = _find_opcodes(instructions, Opcode.LABEL)
        entry_labels = [l for l in labels if l.label and "entry_ALT-ENTRY" in l.label]
        assert len(entry_labels) >= 1

    def test_cancel_emits_nothing(self):
        """CANCEL should not emit any data-affecting instructions."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [CancelStatement(programs=["SUBPROG"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # No CALL_FUNCTION, no WRITE_REGION (beyond initial allocation)
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        assert len(writes) == 0
        assert len(calls) == 0

    # ── I/O Statement Tests ──────────────────────────────────────────

    def test_accept_emits_cobol_accept_call(self):
        """ACCEPT should emit CALL_FUNCTION __cobol_accept."""
        fields = [
            CobolField(
                name="WS-INPUT", level=77, pic="X(10)", usage="DISPLAY", offset=0
            ),
        ]
        stmts = [AcceptStatement(target="WS-INPUT", from_device="CONSOLE")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        accept_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_accept"
        ]
        assert len(accept_calls) == 1

    def test_accept_writes_to_target_field(self):
        """ACCEPT with a target field should emit WRITE_REGION."""
        fields = [
            CobolField(
                name="WS-INPUT", level=77, pic="X(10)", usage="DISPLAY", offset=0
            ),
        ]
        stmts = [AcceptStatement(target="WS-INPUT")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    def test_open_emits_cobol_open_for_each_file(self):
        """OPEN should emit CALL_FUNCTION __cobol_open_file for each file."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [OpenStatement(mode="INPUT", files=["FILE-A", "FILE-B"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        open_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_open_file"
        ]
        assert len(open_calls) == 2

    def test_close_emits_cobol_close_for_each_file(self):
        """CLOSE should emit CALL_FUNCTION __cobol_close_file for each file."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [CloseStatement(files=["FILE-A", "FILE-B"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        close_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_close_file"
        ]
        assert len(close_calls) == 2

    def test_read_emits_cobol_read_record(self):
        """READ should emit CALL_FUNCTION __cobol_read_record."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [ReadStatement(file_name="CUST-FILE")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        read_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_read_record"
        ]
        assert len(read_calls) == 1

    def test_read_with_into_writes_to_field(self):
        """READ INTO should write result to target field."""
        fields = [
            CobolField(
                name="WS-RECORD", level=77, pic="X(10)", usage="DISPLAY", offset=0
            ),
        ]
        stmts = [ReadStatement(file_name="CUST-FILE", into="WS-RECORD")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    def test_write_emits_cobol_write_record(self):
        """WRITE should emit CALL_FUNCTION __cobol_write_record."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [WriteStatement(record_name="CUST-REC")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        write_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_write_record"
        ]
        assert len(write_calls) == 1

    def test_write_from_field_decodes_source(self):
        """WRITE FROM field should decode the source field."""
        fields = [
            CobolField(
                name="WS-OUTPUT", level=77, pic="X(10)", usage="DISPLAY", offset=0
            ),
        ]
        stmts = [WriteStatement(record_name="CUST-REC", from_field="WS-OUTPUT")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have LOAD_REGION for decoding the source field
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        assert len(loads) >= 1
        # And a CALL_FUNCTION for __cobol_write_record
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        write_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_write_record"
        ]
        assert len(write_calls) == 1

    def test_rewrite_emits_cobol_rewrite_record(self):
        """REWRITE should emit CALL_FUNCTION __cobol_rewrite_record."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [RewriteStatement(record_name="CUST-REC")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        rewrite_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_rewrite_record"
        ]
        assert len(rewrite_calls) == 1

    def test_start_emits_cobol_start_file(self):
        """START should emit CALL_FUNCTION __cobol_start_file."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [StartStatement(file_name="CUST-FILE", key="CUST-ID")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        start_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_start_file"
        ]
        assert len(start_calls) == 1

    def test_delete_emits_cobol_delete_record(self):
        """DELETE should emit CALL_FUNCTION __cobol_delete_record."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [DeleteStatement(file_name="CUST-FILE")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        delete_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_delete_record"
        ]
        assert len(delete_calls) == 1


class TestBareStatements:
    """Tests for bare statements at division and section level."""

    def test_bare_division_statements_lower_to_ir(self):
        """Division-level bare statements (no paragraph) should produce IR."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        asg = CobolASG(
            data_fields=fields,
            statements=[
                ComputeStatement(targets=["WS-A"], expression="WS-A + 50"),
                DisplayStatement(operand="WS-A"),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        # COMPUTE produces a BINOP + WRITE_REGION
        binops = _find_opcodes(instructions, Opcode.BINOP)
        assert len(binops) >= 1, "COMPUTE should emit at least one BINOP"

        # DISPLAY produces a CALL_FUNCTION for print
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1, "DISPLAY should emit a print CALL_FUNCTION"

    def test_bare_section_statements_lower_to_ir(self):
        """Section-level bare statements should produce IR with section LABEL."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        asg = CobolASG(
            data_fields=fields,
            sections=[
                CobolSection(
                    name="MAIN-SECTION",
                    statements=[DisplayStatement(operand="WS-A")],
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        # Should have a section LABEL
        labels = _find_opcodes(instructions, Opcode.LABEL)
        section_labels = [
            inst for inst in labels if inst.label == "section_MAIN-SECTION"
        ]
        assert len(section_labels) == 1, "Should emit section LABEL"

        # DISPLAY should emit print
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1, "DISPLAY should emit a print CALL_FUNCTION"

    def test_mixed_bare_and_paragraph_ordering(self):
        """Division-level bare statements should come before paragraph statements in IR."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        asg = CobolASG(
            data_fields=fields,
            statements=[DisplayStatement(operand="WS-A")],
            paragraphs=[
                CobolParagraph(
                    name="MAIN-PARA",
                    statements=[StopRunStatement()],
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        # Find indices of first print (from bare DISPLAY) and first paragraph LABEL
        print_idx = next(
            (
                i
                for i, inst in enumerate(instructions)
                if inst.opcode == Opcode.CALL_FUNCTION
                and inst.operands
                and inst.operands[0] == "print"
            ),
            -1,
        )
        para_label_idx = next(
            (
                i
                for i, inst in enumerate(instructions)
                if inst.opcode == Opcode.LABEL and inst.label == "para_MAIN-PARA"
            ),
            -1,
        )
        assert print_idx != -1, "Should find a print CALL_FUNCTION"
        assert para_label_idx != -1, "Should find para_MAIN-PARA LABEL"
        assert (
            print_idx < para_label_idx
        ), "Bare statement (DISPLAY) should come before paragraph LABEL"


class TestDataLayout:
    def test_data_layout_empty_before_lower(self):
        """data_layout returns empty dict before lower() is called."""
        asg = CobolASG(data_fields=[])
        frontend = CobolFrontend(_FakeParser(asg))
        assert frontend.data_layout == {}

    def test_data_layout_after_lower(self):
        """data_layout exposes correct field metadata after lower()."""
        asg = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
                CobolField(
                    name="WS-B",
                    level=77,
                    pic="X(5)",
                    usage="DISPLAY",
                    offset=3,
                ),
            ],
        )
        frontend = CobolFrontend(_FakeParser(asg))
        frontend.lower(b"")

        layout = frontend.data_layout
        assert "WS-A" in layout
        assert layout["WS-A"]["offset"] == 0
        assert layout["WS-A"]["length"] == 3
        assert layout["WS-A"]["category"] == "ZONED_DECIMAL"
        assert layout["WS-A"]["total_digits"] == 3
        assert layout["WS-A"]["decimal_digits"] == 0
        assert layout["WS-A"]["signed"] is False

        assert "WS-B" in layout
        assert layout["WS-B"]["offset"] == 3
        assert layout["WS-B"]["length"] == 5
        assert layout["WS-B"]["category"] == "ALPHANUMERIC"
