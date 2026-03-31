"""Unit tests for C struct pointer support.

Covers:
  1. Address-of (&) on a heap object (struct) returns the heap reference
     unchanged, enabling pointer-based access.
  2. Arrow operator (->) on a struct pointer reads/writes fields correctly
     (lowered as LOAD_FIELD/STORE_FIELD, same as dot access).
"""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.frontends.c import CFrontend
from interpreter.ir import Opcode
from interpreter.project.entry_point import EntryPoint
from interpreter.parser import TreeSitterParserFactory
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _parse_and_lower(source: str):
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [inst for inst in instructions if inst.opcode == opcode]


def _run_c(source: str, max_steps: int = 300) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(
        source,
        language=Language.C,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


# ── Frontend: arrow operator lowers to LOAD_FIELD/STORE_FIELD ────


class TestArrowOperatorLowering:
    def test_arrow_read_lowers_to_load_field(self):
        """p->x should lower to LOAD_FIELD, same as p.x."""
        source = (
            "struct S { int x; };\n"
            "void f() { struct S s; struct S *p = &s; int v = p->x; }"
        )
        ir = _parse_and_lower(source)
        loads = _find_all(ir, Opcode.LOAD_FIELD)
        field_loads = [l for l in loads if "x" in l.operands]
        assert len(field_loads) == 1

    def test_arrow_write_lowers_to_store_field(self):
        """p->x = 5 should lower to STORE_FIELD with value 5."""
        source = (
            "struct S { int x; };\n"
            "void f() { struct S s; struct S *p = &s; p->x = 5; }"
        )
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_FIELD)
        field_stores = [s for s in stores if "x" in s.operands]
        assert len(field_stores) == 2
        # Verify the arrow write stores the value 5 (not the struct field init)
        consts = {
            str(inst.result_reg): inst.operands[0]
            for inst in ir
            if inst.opcode == Opcode.CONST
        }
        arrow_store = field_stores[-1]  # arrow write is the second STORE_FIELD
        assert consts.get(arrow_store.operands[2]) == "5"


# ── Executor: address-of on heap objects ─────────────────────────


class TestAddressOfHeapObject:
    def test_address_of_struct_returns_pointer(self):
        """&struct_var should return a Pointer wrapping the heap address."""
        source = (
            "struct Point { int x; int y; };\n"
            "struct Point pt;\n"
            "pt.x = 42;\n"
            "struct Point *p = &pt;\n"
            "int val = p->x;"
        )
        vars_ = _run_c(source)
        assert vars_[VarName("val")] == 42
        from interpreter.vm.vm_types import Pointer

        assert isinstance(vars_[VarName("p")], Pointer)
        assert vars_[VarName("p")].offset == 0


# ── Executor: reading through struct pointer ─────────────────────


class TestStructPointerRead:
    def test_read_field_via_arrow(self):
        """p->x and p->y should read the struct's fields."""
        source = (
            "struct Point { int x; int y; };\n"
            "struct Point pt;\n"
            "pt.x = 10;\n"
            "pt.y = 20;\n"
            "struct Point *p = &pt;\n"
            "int a = p->x;\n"
            "int b = p->y;\n"
            "int sum = a + b;"
        )
        vars_ = _run_c(source)
        assert vars_[VarName("a")] == 10
        assert vars_[VarName("b")] == 20
        assert vars_[VarName("sum")] == 30


# ── Executor: writing through struct pointer ─────────────────────


class TestStructPointerWrite:
    def test_write_field_via_arrow(self):
        """p->x = val should mutate the underlying struct."""
        source = (
            "struct Point { int x; int y; };\n"
            "struct Point pt;\n"
            "pt.x = 1;\n"
            "pt.y = 2;\n"
            "struct Point *p = &pt;\n"
            "p->x = 100;\n"
            "p->y = 200;\n"
            "int a = pt.x;\n"
            "int b = pt.y;"
        )
        vars_ = _run_c(source)
        assert vars_[VarName("a")] == 100
        assert vars_[VarName("b")] == 200
