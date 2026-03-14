"""Tests for Rust frontend Box::new and Some call lowering."""

from interpreter.frontends.rust.frontend import RustFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import Opcode


def _parse_rust(source: str):
    frontend = RustFrontend(TreeSitterParserFactory(), "rust")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [i for i in instructions if i.opcode == opcode]


class TestBoxNewLowering:
    def test_box_new_emits_call_function(self):
        """Box::new(x) should emit CALL_FUNCTION, not CALL_UNKNOWN."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        box_calls = [
            c
            for c in calls
            if isinstance(c.operands[0], str) and "Box" in c.operands[0]
        ]
        assert (
            len(box_calls) >= 1
        ), f"Expected CALL_FUNCTION with Box, got {[c.operands for c in calls]}"

    def test_box_new_operand_is_not_call_unknown(self):
        """Box::new should NOT produce CALL_UNKNOWN."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""")
        unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        box_unknowns = [
            c for c in unknowns if any("Box" in str(op) for op in c.operands)
        ]
        assert (
            len(box_unknowns) == 0
        ), f"Box::new should not produce CALL_UNKNOWN: {box_unknowns}"


class TestSomeLowering:
    def test_some_emits_call_function_option(self):
        """Some(x) should emit CALL_FUNCTION with Option."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let opt = Some(n);
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        option_calls = [
            c
            for c in calls
            if isinstance(c.operands[0], str) and "Option" in c.operands[0]
        ]
        assert (
            len(option_calls) >= 1
        ), f"Expected CALL_FUNCTION with Option, got {[c.operands for c in calls]}"
