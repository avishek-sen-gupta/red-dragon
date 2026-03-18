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
    def test_box_new_emits_call_function_box(self):
        """Box::new(x) should emit CALL_FUNCTION with 'Box'."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        box_calls = [
            c
            for c in calls
            if isinstance(c.operands[0], str) and c.operands[0] == "Box"
        ]
        assert (
            len(box_calls) == 1
        ), f"Expected exactly one CALL_FUNCTION 'Box', got {[c.operands for c in calls]}"

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


class TestStringFromLowering:
    def test_string_from_is_pass_through(self):
        """String::from(x) should be pass-through — no CALL_FUNCTION for String."""
        instructions = _parse_rust("""\
let s = String::from("hello");
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        string_calls = [
            c
            for c in calls
            if isinstance(c.operands[0], str) and "String" in c.operands[0]
        ]
        assert (
            len(string_calls) == 0
        ), f"String::from should be pass-through (no CALL_FUNCTION String), got {string_calls}"


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


class TestDerefLowering:
    def test_deref_emits_load_field_boxed(self):
        """*box_val should emit LOAD_FIELD with '__boxed__' field name."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
let inner = *b;
""")
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        boxed_fields = [f for f in fields if "__boxed__" in f.operands]
        assert (
            len(boxed_fields) >= 1
        ), f"Expected LOAD_FIELD with '__boxed__', got {[f.operands for f in fields]}"

    def test_deref_does_not_emit_load_indirect(self):
        """*expr should NOT produce LOAD_INDIRECT — Rust deref is Box unwrap."""
        instructions = _parse_rust("""\
let b = Box::new(42);
let inner = *b;
""")
        indirects = _find_all(instructions, Opcode.LOAD_INDIRECT)
        assert (
            len(indirects) == 0
        ), f"Rust deref should not produce LOAD_INDIRECT: {indirects}"
