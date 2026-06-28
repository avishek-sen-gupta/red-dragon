"""Tests for COBOL frontend — Data Division and Procedure Division lowering."""

from typing import Any, Sequence

from interpreter.cobol.asg_types import (
    CobolASG,
    CobolField,
    CobolParagraph,
    CobolSection,
)
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import make_cobol_parser
from interpreter.continuation_name import ContinuationName
from interpreter.instructions import InstructionBase, AllocRegion, Const
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
    DeleteStatement,
    DisplayStatement,
    EntryStatement,
    ExitStatement,
    GotoStatement,
    SimpleGoto,
    ProcedureRef,
    IfStatement,
    InitializeStatement,
    InspectStatement,
    MoveCorrespondingStatement,
    MoveStatement,
    OpenStatement,
    PerformStatement,
    PerformTimesSpec,
    PerformUntilSpec,
    PerformVaryingSpec,
    ReadStatement,
    Replacing,
    RewriteStatement,
    SearchStatement,
    SearchWhen,
    SetStatement,
    StartStatement,
    StopRunStatement,
    StringSending,
    StringStatement,
    TallyingFor,
    UnstringStatement,
    WriteStatement,
)
from interpreter.cobol.ref_mod import RefModOperand
from interpreter.cobol.cobol_expression import expr_from_dict
from interpreter.ir import Opcode
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _find_opcodes(
    instructions: list[InstructionBase], opcode: Opcode
) -> list[InstructionBase]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _ref(name: str) -> dict:
    """Structured field-reference dict, as the bridge serializes it."""
    return {"kind": "ref", "name": name}


def _lit(value: str) -> dict:
    """Structured numeric-literal dict, as the bridge serializes it."""
    return {"kind": "lit", "value": value}


def _binop(op: str, left: dict, right: dict) -> dict:
    """Structured binary-operation dict, as the bridge serializes it."""
    return {"kind": "binop", "op": op, "left": left, "right": right}


def _build_expr(expr_dict: dict):
    """Build an ExprNode from a structured expression dict (production bridge shape).

    Mirrors how production deserializes COMPUTE expressions via
    ``ComputeStatement.from_dict`` → ``expr_from_dict``.
    """
    return expr_from_dict(expr_dict)


class TestDataDivisionLowering:
    @covers(
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.DATA_LAYOUT_ENGINE,
    )
    def test_alloc_region_size(self):
        data = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        # WS region + the always-present special-registers region. red-dragon-o8uq.
        allocs = [i for i in instructions if isinstance(i, AllocRegion)]
        assert len(allocs) == 2
        alloc_sizes = {
            const.value
            for alloc in allocs
            for const in instructions
            if isinstance(const, Const) and const.result_reg == alloc.size_reg
        }
        assert 5 in alloc_sizes  # 5 bytes for 9(5)

    @covers(
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.DATA_LAYOUT_ENGINE,
    )
    def test_initial_value_encoding(self):
        data = CobolASG(
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
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 1  # Exactly one WRITE_REGION for initial value
        # Verify the write contains encoded bytes for "123"
        write_bytes = [w.operands for w in writes]
        assert any(
            isinstance(ops, list) and len(ops) >= 2 for ops in write_bytes
        ), f"WRITE_REGION should have region + data operands, got {write_bytes}"

    @covers(
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.FRONTEND_IDEMPOTENCY,
    )
    def test_entry_label_emitted(self):
        data = CobolASG(
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [str(inst.label) for inst in labels]
        assert "entry" in label_names

    @covers(
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.DATA_LAYOUT_ENGINE,
    )
    def test_group_field_total_bytes(self):
        data = CobolASG(
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
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        allocs = [i for i in instructions if isinstance(i, AllocRegion)]
        size_const = [
            i
            for i in instructions
            if isinstance(i, Const) and i.result_reg == allocs[0].size_reg
        ]
        assert size_const[0].value == 8  # 5 + 3

    @covers(
        CobolFeature.PIC_CLAUSE, CobolFeature.VALUE_CLAUSE, CobolFeature.USAGE_DISPLAY
    )
    def test_multiple_fields_with_values(self):
        data = CobolASG(
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
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 2  # One for each field with a VALUE


class TestProcedureDivisionLowering:
    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(CobolFeature.MOVE, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_move_literal_to_field(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            MoveStatement(
                source=RefModOperand(name="123"), targets=[RefModOperand(name="WS-A")]
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce WRITE_REGION for the MOVE
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1

    @covers(
        CobolFeature.MOVE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
        stmts = [
            MoveStatement(
                source=RefModOperand(name="WS-A"), targets=[RefModOperand(name="WS-B")]
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should produce LOAD_REGION (decode WS-A) + WRITE_REGION (encode to WS-B)
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(loads) >= 1
        assert len(writes) >= 1

    @covers(
        CobolFeature.ADD,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_add_produces_binop(self):
        """ADD statement produces BINOP + and stores result to target field."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
        ]
        stmts = [
            ArithmeticStatement(
                op="ADD",
                source=RefModOperand(name="5"),
                target=RefModOperand(name="WS-A"),
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        add_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(add_ops) >= 1, "Expected at least one ADD BINOP"

        # Verify result is stored via WRITE_REGION (COBOL's field storage)
        stores = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(stores) >= 1, "Expected WRITE_REGION to store ADD result"

    @covers(
        CobolFeature.SUBTRACT,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_subtract_produces_binop(self):
        """SUBTRACT statement produces BINOP - and stores result to target field."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="10"
            ),
        ]
        stmts = [
            ArithmeticStatement(
                op="SUBTRACT",
                source=RefModOperand(name="3"),
                target=RefModOperand(name="WS-A"),
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        binops = _find_opcodes(instructions, Opcode.BINOP)
        sub_ops = [b for b in binops if b.operands[0] == "-"]
        assert len(sub_ops) >= 1, "Expected at least one SUBTRACT BINOP"

        # Verify result is stored via WRITE_REGION (COBOL's field storage)
        stores = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(stores) >= 1, "Expected WRITE_REGION to store SUBTRACT result"

    @covers(
        CobolFeature.IF_ELSE,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_if_produces_branch_if(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            IfStatement(
                condition={
                    "not": False,
                    "relation": {
                        "left": {"kind": "ref", "name": "WS-A"},
                        "op": ">",
                        "right": {"kind": "lit", "value": "0"},
                    },
                },
                children=[
                    DisplayStatement(operands=(RefModOperand(name="POSITIVE"),)),
                ],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branches = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branches) >= 1

    @covers(
        CobolFeature.IF_ELSE,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_if_else_produces_two_branches(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            IfStatement(
                condition={
                    "not": False,
                    "relation": {
                        "left": {"kind": "ref", "name": "WS-A"},
                        "op": ">",
                        "right": {"kind": "lit", "value": "0"},
                    },
                },
                children=[DisplayStatement(operands=(RefModOperand(name="POSITIVE"),))],
                else_children=[
                    DisplayStatement(operands=(RefModOperand(name="NOT-POSITIVE"),))
                ],
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
        label_names = [str(inst.label) for inst in labels]
        assert any("if_true" in l for l in label_names)
        assert any("if_false" in l for l in label_names)
        assert any("if_end" in l for l in label_names)

    @covers(
        CobolFeature.IF_ELSE,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_if_without_else_has_empty_false_branch(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            IfStatement(
                condition={
                    "not": False,
                    "relation": {
                        "left": {"kind": "ref", "name": "WS-A"},
                        "op": ">",
                        "right": {"kind": "lit", "value": "0"},
                    },
                },
                children=[
                    DisplayStatement(operands=(RefModOperand(name="ONLY-THEN"),))
                ],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Only one print call (THEN branch only)
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) == 1

    @covers(CobolFeature.DISPLAY, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_display_literal(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [DisplayStatement(operands=(RefModOperand(name="HELLO WORLD"),))]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    @covers(
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_display_field(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="42"
            ),
        ]
        stmts = [DisplayStatement(operands=(RefModOperand(name="WS-A"),))]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should LOAD_REGION to decode the field, then call print
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        assert len(loads) >= 1
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    @covers(CobolFeature.STOP_RUN, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_stop_run_produces_return(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [StopRunStatement()]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        returns = _find_opcodes(instructions, Opcode.RETURN)
        assert len(returns) >= 1

    @covers(CobolFeature.GO_TO, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_goto_produces_branch(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            GotoStatement(form=SimpleGoto(target=ProcedureRef(paragraph="OTHER-PARA")))
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        goto_branches = [
            b
            for b in branches
            if b.label.is_present() and b.label.contains("para_OTHER-PARA")
        ]
        assert len(goto_branches) >= 1

    @covers(CobolFeature.PERFORM, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_perform_produces_set_continuation_and_branch(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [PerformStatement(target="WORK-PARA")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit SET_CONTINUATION before the BRANCH
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1
        assert set_conts[0].operands[0] == ContinuationName("para_WORK-PARA_end")

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        perform_branches = [
            b
            for b in branches
            if b.label.is_present() and b.label.contains("para_WORK-PARA")
        ]
        assert len(perform_branches) >= 1

    @covers(CobolFeature.STOP_RUN, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_paragraph_boundary_emits_resume_continuation(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [StopRunStatement()]

        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        resume_conts = _find_opcodes(instructions, Opcode.RESUME_CONTINUATION)
        assert len(resume_conts) >= 1
        resume_names = [inst.operands[0] for inst in resume_conts]
        assert ContinuationName("para_MAIN_end") in resume_names

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_THRU,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_perform_thru_sets_continuation_at_thru_endpoint(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [PerformStatement(target="FIRST-PARA", thru="LAST-PARA")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1
        # Continuation should be keyed to the THRU paragraph's end, not the start
        assert set_conts[0].operands[0] == ContinuationName("para_LAST-PARA_end")

        branches = _find_opcodes(instructions, Opcode.BRANCH)
        perform_branches = [
            b
            for b in branches
            if b.label.is_present() and b.label.contains("para_FIRST-PARA")
        ]
        assert len(perform_branches) >= 1

    @covers(CobolFeature.STOP_RUN, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_paragraph_label_emitted(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [StopRunStatement()]

        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        labels = _find_opcodes(instructions, Opcode.LABEL)
        label_names = [str(inst.label) for inst in labels]
        assert "para_MAIN" in label_names


class TestComputeLowering:
    """Tests for COMPUTE statement IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.GIVING_CLAUSE,
    )
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
        stmts = [
            ComputeStatement(
                expression=_build_expr(_binop("+", _ref("WS-A"), _ref("WS-B"))),
                targets=["WS-RESULT"],
            )
        ]
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

    @covers(
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.GIVING_CLAUSE,
    )
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
        stmts = [
            ComputeStatement(
                expression=_build_expr(
                    _binop("+", _ref("WS-A"), _binop("*", _ref("WS-B"), _lit("2")))
                ),
                targets=["WS-RESULT"],
            )
        ]
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

    @covers(
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PARENTHESIZED_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.GIVING_CLAUSE,
    )
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
            ComputeStatement(
                expression=_build_expr(
                    _binop("*", _binop("+", _ref("WS-A"), _ref("WS-B")), _lit("3"))
                ),
                targets=["WS-RESULT"],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # The expression BINOPs should be + then * (parentheses override precedence)
        all_binops = _find_opcodes(instructions, Opcode.BINOP)
        arith_ops = [
            b.operands[0] for b in all_binops if b.operands[0] in ("+", "-", "*", "/")
        ]
        # Last two arithmetic BINOPs: + (inside parens, evaluated first) then *
        assert arith_ops[-2:] == ["+", "*"]

    @covers(
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.GIVING_CLAUSE,
    )
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
        stmts = [
            ComputeStatement(
                expression=_build_expr(_binop("*", _ref("WS-A"), _lit("5"))),
                targets=["WS-C", "WS-D"],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should have WRITE_REGION for initial values (3 fields) + 2 COMPUTE targets
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 4
        # Verify both target fields (WS-C at offset 3, WS-D at offset 6) are written
        const_map = {
            str(i.result_reg): i.operands[0]
            for i in instructions
            if i.opcode == Opcode.CONST
        }
        write_offsets = [const_map.get(str(w.operands[1])) for w in writes]
        assert (
            3 in write_offsets
        ), f"Expected write at offset 3 (WS-C), got offsets: {write_offsets}"
        assert (
            6 in write_offsets
        ), f"Expected write at offset 6 (WS-D), got offsets: {write_offsets}"

    @covers(
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
        CobolFeature.GIVING_CLAUSE,
    )
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
        stmts = [
            ComputeStatement(
                expression=_build_expr(_binop("+", _lit("10"), _lit("5"))),
                targets=["WS-RESULT"],
            )
        ]
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
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=stmts)] + paragraphs,
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_TIMES,
        CobolFeature.PERFORM_INLINE,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_perform_times_inline_emits_counter_loop(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operands=(RefModOperand(name="IN-LOOP"),))],
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

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_TIMES,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                statements=[
                    DisplayStatement(operands=(RefModOperand(name="WORKING"),))
                ],
            ),
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts, paragraphs)

        # Should have SET_CONTINUATION inside the loop
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        assert len(set_conts) >= 1

        # Should have counter logic
        store_vars = _find_opcodes(instructions, Opcode.STORE_VAR)
        assert len(store_vars) >= 1

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_UNTIL,
        CobolFeature.PERFORM_TEST_BEFORE,
        CobolFeature.PERFORM_INLINE,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_perform_until_test_before_condition_first(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operands=(RefModOperand(name="LOOPING"),))],
                spec=PerformUntilSpec(
                    condition={
                        "not": False,
                        "relation": {
                            "left": {"kind": "ref", "name": "WS-A"},
                            "op": ">",
                            "right": {"kind": "lit", "value": "10"},
                        },
                    },
                    test_before=True,
                ),
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

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_UNTIL,
        CobolFeature.PERFORM_TEST_AFTER,
        CobolFeature.PERFORM_INLINE,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_perform_until_test_after_body_first(self):
        fields = [
            CobolField(
                name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="5"
            ),
        ]
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operands=(RefModOperand(name="LOOPING"),))],
                spec=PerformUntilSpec(
                    condition={
                        "not": False,
                        "relation": {
                            "left": {"kind": "ref", "name": "WS-A"},
                            "op": ">",
                            "right": {"kind": "lit", "value": "10"},
                        },
                    },
                    test_before=False,
                ),
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

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.PERFORM_VARYING,
        CobolFeature.PERFORM_INLINE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.COMPARISON_OPERATORS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
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
                children=[
                    DisplayStatement(operands=(RefModOperand(name="VARYING-LOOP"),))
                ],
                spec=PerformVaryingSpec(
                    varying_var="WS-IDX",
                    varying_from="1",
                    varying_by="1",
                    condition={
                        "not": False,
                        "relation": {
                            "left": {"kind": "ref", "name": "WS-IDX"},
                            "op": ">",
                            "right": {"kind": "lit", "value": "5"},
                        },
                    },
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

    @covers(CobolFeature.PERFORM_VARYING_AFTER)
    def test_perform_varying_after_test_before_emits_nested_loops(self):
        """PERFORM VARYING I AFTER J (TEST BEFORE) emits two BRANCH_IF with nested structure.

        The outer BranchIf's true-target must be the overall exit label.
        The inner BranchIf's true-target must be the outer increment label (not exit).
        Both WRITE_REGIONs for FROM init appear before their respective loop tops.
        """
        fields = [
            CobolField(
                name="WS-I", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="0"
            ),
            CobolField(
                name="WS-J", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="0"
            ),
        ]
        until_i = {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-I"},
                "op": ">",
                "right": {"kind": "lit", "value": "2"},
            },
        }
        until_j = {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-J"},
                "op": ">",
                "right": {"kind": "lit", "value": "3"},
            },
        }
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operands=(RefModOperand(name="BODY"),))],
                spec=PerformVaryingSpec(
                    varying_var="WS-I",
                    varying_from="1",
                    varying_by="1",
                    condition=until_i,
                    test_before=True,
                    after_specs=(
                        PerformVaryingSpec(
                            varying_var="WS-J",
                            varying_from="1",
                            varying_by="1",
                            condition=until_j,
                        ),
                    ),
                ),
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
        # Two BRANCH_IF instructions: outer (I) and inner (J)
        assert len(branch_ifs) == 2

        # Two BRANCH (unconditional) instructions: inner loop-back and outer loop-back
        branches = _find_opcodes(instructions, Opcode.BRANCH)
        assert len(branches) >= 2

        # Two BINOP (+) for the two increment operations (may be more from encode/decode)
        binops = _find_opcodes(instructions, Opcode.BINOP)
        plus_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(plus_ops) >= 2

        # Inner BRANCH_IF's true-target must NOT equal outer BRANCH_IF's true-target
        # (inner exits to outer's incr, not the same exit as outer)
        outer_true = branch_ifs[0].branch_targets[0]
        inner_true = branch_ifs[1].branch_targets[0]
        assert outer_true != inner_true

    @covers(CobolFeature.PERFORM_VARYING_AFTER, CobolFeature.PERFORM_TEST_AFTER)
    def test_perform_varying_after_test_after_emits_cascade(self):
        """PERFORM VARYING I AFTER J TEST AFTER emits body-first cascade structure.

        Expects:
        - Two BRANCH_IF: innermost (J) first in IR, then outer (I)
        - Two BINOP (+) for the two increments
        - The two BRANCH_IF true-targets are different (innermost → outer incr, outer → exit)
        """
        fields = [
            CobolField(
                name="WS-I", level=77, pic="9(3)", usage="DISPLAY", offset=0, value="0"
            ),
            CobolField(
                name="WS-J", level=77, pic="9(3)", usage="DISPLAY", offset=3, value="0"
            ),
        ]
        until_i = {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-I"},
                "op": ">",
                "right": {"kind": "lit", "value": "2"},
            },
        }
        until_j = {
            "not": False,
            "relation": {
                "left": {"kind": "ref", "name": "WS-J"},
                "op": ">",
                "right": {"kind": "lit", "value": "3"},
            },
        }
        stmts = [
            PerformStatement(
                children=[DisplayStatement(operands=(RefModOperand(name="BODY"),))],
                spec=PerformVaryingSpec(
                    varying_var="WS-I",
                    varying_from="1",
                    varying_by="1",
                    condition=until_i,
                    test_before=False,
                    after_specs=(
                        PerformVaryingSpec(
                            varying_var="WS-J",
                            varying_from="1",
                            varying_by="1",
                            condition=until_j,
                        ),
                    ),
                ),
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        branch_ifs = _find_opcodes(instructions, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 2

        # Two BINOP (+): one for J increment, one for I increment (plus encode/decode overhead)
        binops = _find_opcodes(instructions, Opcode.BINOP)
        plus_ops = [b for b in binops if b.operands[0] == "+"]
        assert len(plus_ops) >= 2

        # The two BRANCH_IF true-targets are different (innermost → outer incr, outer → exit)
        assert branch_ifs[0].branch_targets[0] != branch_ifs[1].branch_targets[0]


class TestSectionPerform:
    """Tests for section-level PERFORM."""

    @covers(
        CobolFeature.PERFORM,
        CobolFeature.DISPLAY,
        CobolFeature.STOP_RUN,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_perform_section_branches_to_section_label(self):
        from interpreter.cobol.asg_types import CobolSection

        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        data = CobolASG(
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
                            statements=[
                                DisplayStatement(
                                    operands=(RefModOperand(name="IN-SECTION"),)
                                )
                            ],
                        ),
                    ],
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        # Should branch to section_WORK-SECTION
        branches = _find_opcodes(instructions, Opcode.BRANCH)
        section_branches = [
            b for b in branches if b.label and "section_WORK-SECTION" == b.label
        ]
        assert len(section_branches) >= 1

        # Should set continuation at section end
        set_conts = _find_opcodes(instructions, Opcode.SET_CONTINUATION)
        section_conts = [
            s
            for s in set_conts
            if s.operands[0] == ContinuationName("section_WORK-SECTION_end")
        ]
        assert len(section_conts) >= 1

    @covers(CobolFeature.STOP_RUN, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_section_emits_end_resume_continuation(self):
        from interpreter.cobol.asg_types import CobolSection

        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        data = CobolASG(
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
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        resume_conts = _find_opcodes(instructions, Opcode.RESUME_CONTINUATION)
        resume_names = [inst.operands[0] for inst in resume_conts]
        assert ContinuationName("section_MY-SECTION_end") in resume_names


class TestTier1Lowering:
    """Tests for CONTINUE, EXIT, INITIALIZE, SET IR lowering."""

    def _lower_with_field_and_stmts(
        self,
        fields: list[CobolField],
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(CobolFeature.CONTINUE, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
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

    @covers(CobolFeature.EXIT, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_exit_emits_nothing(self):
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        stmts = [ExitStatement()]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) == 0

    @covers(
        CobolFeature.INITIALIZE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.INITIALIZE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.INITIALIZE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.INITIALIZE,
        CobolFeature.GROUP_ITEM,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_initialize_group_item_emits_write_per_child(self):
        """INITIALIZE on a group item emits one WRITE_REGION per leaf child."""
        fields = [
            CobolField(
                name="WS-GROUP",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="9(3)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-B", level=5, pic="X(3)", usage="DISPLAY", offset=3
                    ),
                ],
            ),
        ]
        stmts = [InitializeStatement(operands=["WS-GROUP"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        # One WRITE_REGION per child (no initial VALUE clauses here)
        assert len(writes) >= 2

    @covers(
        CobolFeature.SET_TO,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.SET_UP_BY,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.SET_DOWN_BY,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.STRING_DELIMITED_BY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                    StringSending(
                        value=RefModOperand(name="WS-FIRST"), delimited_by="SIZE"
                    ),
                    StringSending(
                        value=RefModOperand(name="WS-LAST"), delimited_by="SIZE"
                    ),
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

    @covers(
        CobolFeature.STRING_VERB,
        CobolFeature.STRING_DELIMITED_BY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                    StringSending(value=RefModOperand(name="WS-SRC"), delimited_by=" "),
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

    @covers(
        CobolFeature.UNSTRING_VERB,
        CobolFeature.UNSTRING_DELIMITED_BY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                source=RefModOperand(name="WS-FULL"),
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

    @covers(
        CobolFeature.INSPECT_TALLYING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                source=RefModOperand(name="WS-DATA"),
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

    @covers(
        CobolFeature.INSPECT_REPLACING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                source=RefModOperand(name="WS-DATA"),
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
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
        CobolFeature.SEARCH_VARYING,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                        children=[
                            DisplayStatement(operands=(RefModOperand(name="FOUND"),))
                        ],
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
        label_names = [str(inst.label) for inst in labels]
        assert any("search_loop" in name for name in label_names)
        assert any("search_end" in name for name in label_names)

    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
        CobolFeature.SEARCH_VARYING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
        CobolFeature.SEARCH_AT_END,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
                at_end=[DisplayStatement(operands=(RefModOperand(name="NOT FOUND"),))],
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # AT END should produce CALL_FUNCTION for DISPLAY (uses "print")
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1

    @covers(
        CobolFeature.SEARCH_LINEAR,
        CobolFeature.SEARCH_WHEN_CONDITIONS,
        CobolFeature.SEARCH_VARYING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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
        stmts: Sequence[CobolStatementType],
    ) -> list[InstructionBase]:
        data = CobolASG(
            data_fields=fields,
            paragraphs=[CobolParagraph(name="MAIN", statements=list(stmts))],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.CALL,
        CobolFeature.CALL_USING,
        CobolFeature.USING_BY_REFERENCE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_call_emits_call_with_memory(self):
        """CALL should emit CALL_WITH_MEMORY with program name."""
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

        calls = _find_opcodes(instructions, Opcode.CALL_WITH_MEMORY)
        subprog_calls = [c for c in calls if c.operands and c.operands[0] == "SUBPROG"]
        assert len(subprog_calls) >= 1

    @covers(
        CobolFeature.CALL,
        CobolFeature.CALL_USING,
        CobolFeature.CALL_GIVING,
        CobolFeature.USING_BY_REFERENCE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.VALUE_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(CobolFeature.ALTER, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
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

    @covers(CobolFeature.ENTRY, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
    def test_entry_emits_label(self):
        """ENTRY should emit a LABEL for the alternate entry point."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        stmts = [EntryStatement(entry_name="ALT-ENTRY")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        labels = _find_opcodes(instructions, Opcode.LABEL)
        entry_labels = [
            l
            for l in labels
            if l.label.is_present() and l.label.contains("entry_ALT-ENTRY")
        ]
        assert len(entry_labels) >= 1

    @covers(CobolFeature.CANCEL, CobolFeature.PIC_CLAUSE, CobolFeature.USAGE_DISPLAY)
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

    @covers(
        CobolFeature.ACCEPT,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.ACCEPT,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.OPEN,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_open_emits_cobol_open_for_each_file(self):
        """OPEN should emit CALL_FUNCTION __cobol_open_file for each file."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(1)", usage="DISPLAY", offset=0),
        ]
        from interpreter.cobol.file_enums import OpenMode

        stmts = [OpenStatement(mode_groups=[(OpenMode.INPUT, ["FILE-A", "FILE-B"])])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        open_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_open_file"
        ]
        assert len(open_calls) == 2

    @covers(
        CobolFeature.CLOSE,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.READ,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.READ,
        CobolFeature.READ_INTO,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.WRITE,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.WRITE,
        CobolFeature.WRITE_FROM,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_write_from_field_decodes_source(self):
        """WRITE rec FROM field == MOVE field TO rec; WRITE rec (red-dragon-zwzg).

        The source field is loaded by the synthetic MOVE into the record area,
        and the record area is then read raw (byte-faithful) for the write — so
        both the receiving record and the source field must exist.
        """
        fields = [
            CobolField(
                name="WS-OUTPUT", level=77, pic="X(10)", usage="DISPLAY", offset=0
            ),
            CobolField(
                name="CUST-REC", level=1, pic="X(10)", usage="DISPLAY", offset=10
            ),
        ]
        stmts = [WriteStatement(record_name="CUST-REC", from_field="WS-OUTPUT")]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # The source field is loaded by the MOVE into the record area.
        loads = _find_opcodes(instructions, Opcode.LOAD_REGION)
        assert len(loads) >= 1
        # And a CALL_FUNCTION for __cobol_write_record
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        write_calls = [
            c for c in calls if c.operands and c.operands[0] == "__cobol_write_record"
        ]
        assert len(write_calls) == 1

    @covers(
        CobolFeature.REWRITE,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.START,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.DELETE_RECORD,
        CobolFeature.IO_PROVIDER,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
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

    @covers(
        CobolFeature.BARE_STATEMENTS,
        CobolFeature.COMPUTE,
        CobolFeature.ARITHMETIC_EXPRESSION,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_bare_division_statements_lower_to_ir(self):
        """Division-level bare statements (no paragraph) should produce IR."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        data = CobolASG(
            data_fields=fields,
            statements=[
                ComputeStatement(
                    targets=["WS-A"],
                    expression=_build_expr(_binop("+", _ref("WS-A"), _lit("50"))),
                ),
                DisplayStatement(operands=(RefModOperand(name="WS-A"),)),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        # COMPUTE produces a BINOP + WRITE_REGION
        binops = _find_opcodes(instructions, Opcode.BINOP)
        assert len(binops) >= 1, "COMPUTE should emit at least one BINOP"

        # DISPLAY produces a CALL_FUNCTION for print
        calls = _find_opcodes(instructions, Opcode.CALL_FUNCTION)
        print_calls = [c for c in calls if c.operands and c.operands[0] == "print"]
        assert len(print_calls) >= 1, "DISPLAY should emit a print CALL_FUNCTION"

    @covers(
        CobolFeature.BARE_STATEMENTS,
        CobolFeature.DISPLAY,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_bare_section_statements_lower_to_ir(self):
        """Section-level bare statements should produce IR with section LABEL."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        data = CobolASG(
            data_fields=fields,
            sections=[
                CobolSection(
                    name="MAIN-SECTION",
                    statements=[
                        DisplayStatement(operands=(RefModOperand(name="WS-A"),))
                    ],
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

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

    @covers(
        CobolFeature.BARE_STATEMENTS,
        CobolFeature.DISPLAY,
        CobolFeature.STOP_RUN,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_mixed_bare_and_paragraph_ordering(self):
        """Division-level bare statements should come before paragraph statements in IR."""
        fields = [
            CobolField(name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0),
        ]
        data = CobolASG(
            data_fields=fields,
            statements=[DisplayStatement(operands=(RefModOperand(name="WS-A"),))],
            paragraphs=[
                CobolParagraph(
                    name="MAIN-PARA",
                    statements=[StopRunStatement()],
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

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
    @covers(CobolFeature.DATA_LAYOUT_ENGINE)
    def test_data_layout_empty_before_lower(self):
        """data_layout returns empty dict before lower() is called."""
        frontend = CobolFrontend(make_cobol_parser())
        assert frontend.data_layout == {}

    @covers(
        CobolFeature.DATA_LAYOUT_ENGINE,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_data_layout_after_lower(self):
        """data_layout exposes correct field metadata after lower()."""
        data = CobolASG(
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
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        frontend.lower_from_ast_dict(data)

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


class TestMoveCorrespondingLowering:
    """Tests for MOVE CORRESPONDING statement lowering."""

    def _lower_with_field_and_stmts(
        self, fields: list[CobolField], stmts: list[CobolStatementType]
    ) -> list[InstructionBase]:
        """Helper to lower a COBOL program with given fields and statements."""
        paragraphs = [CobolParagraph(name="MAIN-PARA", statements=stmts)]
        section = CobolSection(name="PROC", paragraphs=paragraphs)
        data = CobolASG(data_fields=fields, sections=[section]).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        return frontend.lower_from_ast_dict(data)

    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_move_corresponding_simple(self):
        """MOVE CORRESPONDING source TO target with matching field names."""
        fields = [
            CobolField(
                name="WS-SOURCE",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="SRC-A", level=5, pic="9(3)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="SRC-B", level=5, pic="X(2)", usage="DISPLAY", offset=3
                    ),
                ],
            ),
            CobolField(
                name="WS-TARGET",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=5,
                children=[
                    CobolField(
                        name="SRC-A", level=5, pic="9(3)", usage="DISPLAY", offset=5
                    ),
                    CobolField(
                        name="SRC-B", level=5, pic="X(2)", usage="DISPLAY", offset=8
                    ),
                ],
            ),
        ]
        stmts = [MoveCorrespondingStatement(source="WS-SOURCE", targets=["WS-TARGET"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit WRITE_REGION instructions for moved fields
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # At least 2 fields (SRC-A, SRC-B)

    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_move_corresponding_multiple_targets(self):
        """MOVE CORRESPONDING source TO target1 TO target2."""
        fields = [
            CobolField(
                name="WS-SOURCE",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="FIELD-A", level=5, pic="9(1)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
            CobolField(
                name="WS-TARGET1",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=1,
                children=[
                    CobolField(
                        name="FIELD-A", level=5, pic="9(1)", usage="DISPLAY", offset=1
                    ),
                ],
            ),
            CobolField(
                name="WS-TARGET2",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=2,
                children=[
                    CobolField(
                        name="FIELD-A", level=5, pic="9(1)", usage="DISPLAY", offset=2
                    ),
                ],
            ),
        ]
        stmts = [
            MoveCorrespondingStatement(
                source="WS-SOURCE", targets=["WS-TARGET1", "WS-TARGET2"]
            )
        ]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit WRITE_REGION for both targets
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 2  # At least one for each target

    @covers(
        CobolFeature.MOVE_CORRESPONDING,
        CobolFeature.PIC_CLAUSE,
        CobolFeature.USAGE_DISPLAY,
    )
    def test_move_corresponding_partial_match(self):
        """MOVE CORRESPONDING only moves matching field names."""
        fields = [
            CobolField(
                name="WS-SOURCE",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="FIELD-X", level=5, pic="9(1)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="FIELD-Y", level=5, pic="9(1)", usage="DISPLAY", offset=1
                    ),
                ],
            ),
            CobolField(
                name="WS-TARGET",
                level=1,
                pic=None,
                usage="DISPLAY",
                offset=2,
                children=[
                    CobolField(
                        name="FIELD-X", level=5, pic="9(1)", usage="DISPLAY", offset=2
                    ),
                    CobolField(
                        name="FIELD-Z", level=5, pic="9(1)", usage="DISPLAY", offset=3
                    ),
                ],
            ),
        ]
        stmts = [MoveCorrespondingStatement(source="WS-SOURCE", targets=["WS-TARGET"])]
        instructions = self._lower_with_field_and_stmts(fields, stmts)

        # Should emit WRITE_REGION for matching field (FIELD-X) but not non-matching ones
        writes = _find_opcodes(instructions, Opcode.WRITE_REGION)
        assert len(writes) >= 1  # At least FIELD-X match


class TestSectionedLayout:
    @covers(CobolFeature.SECTION_LOCAL_STORAGE)
    def test_frontend_lower_produces_alloc_regions_for_ws_ls_and_special_registers(
        self,
    ):
        """CobolFrontend.lower() emits an ALLOC_REGION for WS, LS, and the
        always-present special-registers region (RETURN-CODE). red-dragon-o8uq."""
        data = CobolASG(
            data_fields=[
                CobolField(name="WS-X", level=1, pic="X(5)", usage="DISPLAY", offset=0)
            ],
            local_storage_fields=[
                CobolField(name="LS-Y", level=1, pic="X(3)", usage="DISPLAY", offset=0)
            ],
        ).to_dict()
        frontend = CobolFrontend(cobol_parser=make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        alloc_count = sum(1 for i in instructions if i.opcode == Opcode.ALLOC_REGION)
        assert (
            alloc_count == 3
        ), f"Expected 3 ALLOC_REGION (WS + LS + special registers), got {alloc_count}"


class TestSingletonInit:
    """Tests for Task 5: singleton init block and func_PROGRAMID_0 label."""

    @covers(CobolFeature.SECTION_WORKING_STORAGE)
    def test_frontend_lower_emits_func_proc_label(self):
        """lower() must wrap the procedure division in func_<pid>_0 label."""
        data = CobolASG(
            program_id="TEST-INIT",
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        instructions = frontend.lower_from_ast_dict(data)

        labels = [
            str(inst.label) for inst in instructions if inst.opcode == Opcode.LABEL
        ]
        assert any(
            l.startswith("func_") and l.endswith("_0") for l in labels
        ), f"Expected a func_*_0 label, got labels: {labels}"

    @covers(CobolFeature.SECTION_WORKING_STORAGE)
    def test_frontend_exposes_program_id(self):
        """frontend.program_id must return the PROGRAM-ID after lower()."""
        data = CobolASG(
            program_id="TEST-INIT",
            data_fields=[
                CobolField(
                    name="WS-A", level=77, pic="9(3)", usage="DISPLAY", offset=0
                ),
            ],
        ).to_dict()
        frontend = CobolFrontend(make_cobol_parser())
        frontend.lower_from_ast_dict(data)
        assert frontend.program_id == "TEST-INIT"
