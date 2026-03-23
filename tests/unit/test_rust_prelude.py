"""Tests for Rust frontend prelude class emission (Box, Option)."""

from interpreter.frontends.rust.frontend import RustFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import Opcode


def _parse_rust(source: str):
    frontend = RustFrontend(TreeSitterParserFactory(), "rust")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [i for i in instructions if i.opcode == opcode]


def _labels(instructions):
    return [str(i.label) for i in instructions if i.opcode == Opcode.LABEL]


class TestRustPrelude:
    def test_box_class_label_emitted(self):
        """Even an empty Rust program should emit Box class definition."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l.startswith("prelude_class_Box") for l in labels if l)

    def test_option_class_label_emitted(self):
        """Even an empty Rust program should emit Option class definition."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l.startswith("prelude_class_Option") for l in labels if l)

    def test_box_has_init_method(self):
        """Box prelude should define __init__ with a value parameter."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            l and "Box" in l and "__init__" in l for l in labels
        ), f"No Box.__init__ label found in {labels}"

    def test_option_has_init_method(self):
        """Option prelude should define __init__ with a value parameter."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l and "Option" in l and "__init__" in l for l in labels)

    def test_option_has_unwrap_method(self):
        """Option prelude should define unwrap method."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l and "Option" in l and "unwrap" in l for l in labels)

    def test_option_has_as_ref_method(self):
        """Option prelude should define as_ref method."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l and "Option" in l and "as_ref" in l for l in labels)

    def test_box_store_var_emitted(self):
        """Box class ref should be stored in a variable."""
        instructions = _parse_rust("let x: i32 = 1;")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Box" in inst.operands for inst in stores)

    def test_box_has_method_missing(self):
        """Box prelude class must define __method_missing__."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            "Box" in lbl and "__method_missing__" in lbl for lbl in labels if lbl
        ), f"No __method_missing__ label found for Box in: {labels}"

    def test_option_store_var_emitted(self):
        """Option class ref should be stored in a variable."""
        instructions = _parse_rust("let x: i32 = 1;")
        stores = _find_all(instructions, Opcode.DECL_VAR)
        assert any("Option" in inst.operands for inst in stores)
