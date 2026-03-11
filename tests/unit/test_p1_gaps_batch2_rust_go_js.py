"""Unit tests for P1 lowering gaps: Rust (4), Go (1), JS (1), TS (1)."""

from __future__ import annotations

from interpreter.frontends.rust import RustFrontend
from interpreter.frontends.go import GoFrontend
from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


# ── Rust: foreign_mod_item ───────────────────────────────────────


class TestRustForeignModItem:
    def test_foreign_mod_no_symbolic(self):
        """extern { fn foo(); } should not produce SYMBOLIC fallthrough."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b'extern "C" { fn foo(); }')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("foreign_mod_item" in str(inst.operands) for inst in symbolics)

    def test_foreign_mod_body_lowered(self):
        """Declarations inside extern block should be lowered."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b'extern "C" { fn foo(); }')
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("foo" in inst.operands for inst in stores)


# ── Rust: union_item ─────────────────────────────────────────────


class TestRustUnionItem:
    def test_union_no_symbolic(self):
        """union Foo { x: i32, y: f64 } should not produce SYMBOLIC."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"union Foo { x: i32, y: f64 }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("union_item" in str(inst.operands) for inst in symbolics)

    def test_union_stores_name(self):
        """union Foo should produce a STORE_VAR for Foo."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"union Foo { x: i32, y: f64 }")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Foo" in inst.operands for inst in stores)


# ── Rust: macro_definition ───────────────────────────────────────


class TestRustMacroDefinition:
    def test_macro_definition_no_symbolic(self):
        """macro_rules! should not produce SYMBOLIC fallthrough."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"macro_rules! my_macro { () => {} }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("macro_definition" in str(inst.operands) for inst in symbolics)

    def test_macro_definition_does_not_block(self):
        """Code after macro_rules! should still be lowered."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"macro_rules! my_macro { () => {} }\nlet x = 42;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


# ── Rust: mut_pattern ────────────────────────────────────────────


class TestRustMutPattern:
    def test_mut_pattern_no_symbolic(self):
        """mut x in let should not produce SYMBOLIC fallthrough."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"let mut x = 42;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("mut_pattern" in str(inst.operands) for inst in symbolics)

    def test_mut_pattern_stores_var(self):
        """let mut x = 42 should produce STORE_VAR for x."""
        frontend = RustFrontend(TreeSitterParserFactory(), "rust")
        ir = frontend.lower(b"let mut x = 42;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


# ── Go: variadic_argument ───────────────────────────────────────


class TestGoVariadicArgument:
    def test_variadic_argument_no_symbolic(self):
        """args... in function call should not produce SYMBOLIC."""
        frontend = GoFrontend(TreeSitterParserFactory(), "go")
        ir = frontend.lower(b"func main() { fmt.Println(args...) }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("variadic_argument" in str(inst.operands) for inst in symbolics)


# ── JS: meta_property ───────────────────────────────────────────


class TestJSMetaProperty:
    def test_meta_property_no_symbolic(self):
        """new.target should not produce SYMBOLIC fallthrough."""
        frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
        ir = frontend.lower(b"let x = new.target;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("meta_property" in str(inst.operands) for inst in symbolics)

    def test_meta_property_stores_value(self):
        """new.target should be stored as a const."""
        frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
        ir = frontend.lower(b"let x = new.target;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)


# ── TS: type_assertion ───────────────────────────────────────────


class TestTSTypeAssertion:
    def test_type_assertion_no_symbolic(self):
        """<string>x should not produce SYMBOLIC fallthrough."""
        frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
        ir = frontend.lower(b"let y = <string>x;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("type_assertion" in str(inst.operands) for inst in symbolics)

    def test_type_assertion_lowers_inner_expr(self):
        """<string>x should produce a LOAD_VAR for x."""
        frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
        ir = frontend.lower(b"let y = <string>x;")
        loads = _find_all(ir, Opcode.LOAD_VAR)
        assert any("x" in inst.operands for inst in loads)
