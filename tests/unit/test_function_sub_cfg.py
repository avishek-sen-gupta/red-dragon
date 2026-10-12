"""Tests: function_sub_cfg extracts one function's blocks from a whole-program CFG."""

from interpreter.cfg import build_cfg, function_sub_cfg
from interpreter.ir import CodeLabel, IRInstruction, Opcode
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_follows_branches_and_stops_at_other_functions():
    full_cfg = build_cfg(
        [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(opcode=Opcode.BRANCH, label=CodeLabel("end_foo_1")),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("func_foo_0")),
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg=Register("%0"),
                operands=["param:n"],
            ),
            IRInstruction(opcode=Opcode.DECL_VAR, operands=["n", "%0"]),
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg=Register("%1"), operands=["n"]
            ),
            IRInstruction(
                opcode=Opcode.BRANCH_IF,
                operands=["%1"],
                branch_targets=[CodeLabel("if_true_2"), CodeLabel("if_end_3")],
            ),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("if_true_2")),
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%2"), operands=["1"]
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%2"]),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("if_end_3")),
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg=Register("%3"), operands=["n"]
            ),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("func_bar_4")),
            IRInstruction(
                opcode=Opcode.SYMBOLIC,
                result_reg=Register("%5"),
                operands=["param:m"],
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%5"]),
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("end_foo_1")),
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%4"), operands=["5"]
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%4"]),
        ]
    )

    sub = function_sub_cfg(full_cfg, CodeLabel("func_foo_0"))

    assert sub.entry == CodeLabel("func_foo_0")
    assert {str(label) for label in sub.blocks} == {
        "func_foo_0",
        "if_true_2",
        "if_end_3",
    }
    assert sorted(map(str, sub.blocks[CodeLabel("func_foo_0")].successors)) == [
        "if_end_3",
        "if_true_2",
    ]
    assert sub.blocks[CodeLabel("func_foo_0")].predecessors == []
    assert sub.blocks[CodeLabel("if_end_3")].successors == []
