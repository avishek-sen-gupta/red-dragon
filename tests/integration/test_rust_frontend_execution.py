"""Integration tests for Rust frontend: raw_string_literal, negative_literal, foreign_mod_item, union_item, macro_definition, mut_pattern."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_rust(source: str, max_steps: int = 200):
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestRustRawStringLiteralExecution:
    def test_raw_string_assigned(self):
        """let x = r\"hello\"; should execute without errors."""
        _, local_vars = _run_rust('let x = r"hello";')
        assert "x" in local_vars

    def test_raw_string_in_comparison(self):
        """Raw string should be usable in comparison without crashing."""
        _, local_vars = _run_rust("""\
let x = r"hello";
let y = r"hello";
let same = x == y;
""")
        assert local_vars["same"] is True

    def test_raw_string_with_hashes(self):
        """r#\"has quotes\"# should execute without errors."""
        _, local_vars = _run_rust("""\
let x = r#"has quotes"#;
let y = 42;
""")
        assert local_vars["y"] == 42


class TestRustNegativeLiteralExecution:
    def test_negative_literal_value(self):
        """let x: i32 = -1; should store -1."""
        _, local_vars = _run_rust("let x: i32 = -1;")
        assert local_vars["x"] == -1

    def test_negative_literal_in_arithmetic(self):
        """Negative literal should be usable in arithmetic."""
        _, local_vars = _run_rust("""\
let x: i32 = -5;
let y = x + 10;
""")
        assert local_vars["y"] == 5

    def test_negative_float_literal(self):
        """let x = -3.0; should store a negative float."""
        _, local_vars = _run_rust("let x: f64 = -3.0;")
        assert local_vars["x"] == -3.0

    def test_negative_literal_in_match_pattern(self):
        """match arm with -1 pattern should execute without errors."""
        _, local_vars = _run_rust(
            """\
let x = 5;
let r = match x {
    -1 => 10,
    5 => 50,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["r"] == 50

    def test_negative_literal_match_hits_negative(self):
        """match arm with -1 pattern should match when value is -1."""
        _, local_vars = _run_rust(
            """\
let x: i32 = -1;
let r = match x {
    -1 => 10,
    5 => 50,
    _ => 0,
};
""",
            max_steps=300,
        )
        assert local_vars["r"] == 10


class TestRustForeignModItemExecution:
    def test_code_after_extern_block_executes(self):
        """Code after extern block should execute normally."""
        _, locals_ = _run_rust('extern "C" { fn foo(); }\nlet x = 10;')
        assert locals_["x"] == 10


class TestRustUnionItemExecution:
    def test_code_after_union_executes(self):
        """Code after union definition should execute normally."""
        _, locals_ = _run_rust("union Foo { x: i32, y: f64 }\nlet a = 5;")
        assert locals_["a"] == 5


class TestRustMacroDefinitionExecution:
    def test_code_after_macro_def_executes(self):
        """Code after macro_rules! should execute normally."""
        _, locals_ = _run_rust("macro_rules! my_macro { () => {} }\nlet y = 99;")
        assert locals_["y"] == 99


class TestRustMutPatternExecution:
    def test_let_mut_stores_value(self):
        """let mut x = 42 should store 42 in x."""
        _, locals_ = _run_rust("let mut x = 42;")
        assert locals_["x"] == 42

    def test_let_mut_reassignment(self):
        """let mut x should allow reassignment."""
        _, locals_ = _run_rust("let mut x = 1;\nx = 2;")
        assert locals_["x"] == 2


class TestRustBoxExecution:
    def test_box_new_creates_box_object(self):
        """Box::new(x) creates a Box wrapping x via __boxed__."""
        vm, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""",
            max_steps=300,
        )
        # Box::new creates a Box heap object containing the Node via __boxed__
        b_ptr = local_vars["b"]
        assert b_ptr.base in vm.heap
        box_obj = vm.heap[b_ptr.base]
        from interpreter.type_expr import ScalarType

        assert box_obj.type_hint == ScalarType("Box")
        assert "__boxed__" in box_obj.fields
        from interpreter.typed_value import TypedValue

        inner = box_obj.fields["__boxed__"]
        inner_val = inner.value if isinstance(inner, TypedValue) else inner
        assert inner_val == local_vars["n"]


class TestRustOptionExecution:
    def test_some_creates_option_with_value(self):
        """Some(42) should create an Option object with value field = 42."""
        vm, local_vars = _run_rust("let opt = Some(42);", max_steps=300)
        opt_ptr = local_vars.get("opt")
        assert opt_ptr is not None
        assert opt_ptr.base in vm.heap
        assert "value" in vm.heap[opt_ptr.base].fields
        from interpreter.typed_value import TypedValue

        tv = vm.heap[opt_ptr.base].fields["value"]
        assert isinstance(tv, TypedValue)
        assert tv.value == 42

    def test_option_unwrap_returns_inner(self):
        """Some(42).unwrap() should return 42."""
        _, local_vars = _run_rust(
            """\
let opt = Some(42);
let val = opt.unwrap();
""",
            max_steps=300,
        )
        assert local_vars["val"] == 42

    def test_option_as_ref_identity(self):
        """opt.as_ref() should return the same object."""
        _, local_vars = _run_rust(
            """\
let opt = Some(42);
let ref_opt = opt.as_ref();
let val = ref_opt.unwrap();
""",
            max_steps=400,
        )
        assert local_vars["val"] == 42

    def test_nested_box_in_option(self):
        """Some(Box::new(42)) — unwrap returns the Box object."""
        vm, local_vars = _run_rust(
            """\
let opt = Some(Box::new(42));
let inner = opt.unwrap();
""",
            max_steps=400,
        )
        # unwrap returns the Box object; auto-deref to 42 is a separate concern
        inner_ptr = local_vars["inner"]
        assert inner_ptr.base in vm.heap
        from interpreter.type_expr import ScalarType

        assert vm.heap[inner_ptr.base].type_hint == ScalarType("Box")

    def test_as_ref_unwrap_chain(self):
        """opt.as_ref().unwrap() — the actual Rosetta pattern."""
        _, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 42 };
let opt = Some(Box::new(n));
let inner = opt.as_ref().unwrap();
""",
            max_steps=500,
        )
        assert local_vars.get("inner") is not None
