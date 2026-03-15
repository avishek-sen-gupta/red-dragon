"""Tests for C function pointer support.

Covers:
  1. extract_declarator_name correctly handles parenthesized_declarator
     (e.g. ``int (*fp)(int, int)`` → variable name ``fp``, not ``(*fp)``).
  2. UNOP '&' on a FUNC_REF returns the FUNC_REF unchanged (address-of
     function is identity in C).
  3. LOAD_FIELD with field '*' on a FUNC_REF returns the FUNC_REF unchanged
     (dereferencing a function pointer is identity in C).
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.func_ref import BoundFuncRef
from interpreter.frontends.c import CFrontend
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _parse_and_lower(source: str):
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [inst for inst in instructions if inst.opcode == opcode]


def _run_c(source: str, max_steps: int = 300) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


# ── Frontend: declarator name extraction ─────────────────────────


class TestFunctionPointerDeclaratorName:
    def test_function_pointer_declaration_stores_to_fp(self):
        """int (*fp)(int, int) = &add; should store to 'fp', not '(*fp)'."""
        source = (
            "int add(int a, int b) { return a + b; }\n" "int (*fp)(int, int) = &add;"
        )
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        store_names = [s.operands[0] for s in stores]
        assert "fp" in store_names
        assert "(*fp)" not in store_names

    def test_function_pointer_emits_address_of(self):
        """int (*fp)(int, int) = &add; should emit ADDRESS_OF for address-of."""
        source = (
            "int add(int a, int b) { return a + b; }\n" "int (*fp)(int, int) = &add;"
        )
        ir = _parse_and_lower(source)
        addr_of_ops = _find_all(ir, Opcode.ADDRESS_OF)
        assert len(addr_of_ops) == 1
        assert addr_of_ops[0].operands[0] == "add"


# ── Executor: address-of function reference ──────────────────────


class TestAddressOfFuncRef:
    def test_address_of_function_returns_func_ref(self):
        """&add should resolve to the FUNC_REF, not a symbolic value."""
        source = (
            "int add(int a, int b) { return a + b; }\n" "int (*fp)(int, int) = &add;"
        )
        vars_ = _run_c(source)
        assert vars_["fp"] == vars_["add"]
        assert isinstance(vars_["fp"], BoundFuncRef)

    def test_assign_function_without_address_of(self):
        """fp = add (without &) should also store the FUNC_REF directly."""
        source = (
            "int add(int a, int b) { return a + b; }\n" "int (*fp)(int, int) = add;"
        )
        vars_ = _run_c(source)
        assert vars_["fp"] == vars_["add"]


# ── Executor: dereference of function pointer ────────────────────


class TestDereferenceFuncRef:
    def test_deref_function_pointer_call(self):
        """(*fp)(3, 5) should dispatch to the underlying function."""
        source = (
            "int add(int a, int b) { return a + b; }\n"
            "int (*fp)(int, int) = &add;\n"
            "int result = (*fp)(3, 5);"
        )
        vars_ = _run_c(source)
        assert vars_["result"] == 8

    def test_direct_function_pointer_call(self):
        """fp(3, 5) (without explicit dereference) should also work."""
        source = (
            "int add(int a, int b) { return a + b; }\n"
            "int (*fp)(int, int) = add;\n"
            "int result = fp(3, 5);"
        )
        vars_ = _run_c(source)
        assert vars_["result"] == 8

    def test_reassign_function_pointer(self):
        """Reassigning a function pointer to a different function should work."""
        source = (
            "int add(int a, int b) { return a + b; }\n"
            "int mul(int a, int b) { return a * b; }\n"
            "int (*fp)(int, int) = &add;\n"
            "int r1 = (*fp)(3, 5);\n"
            "fp = &mul;\n"
            "int r2 = (*fp)(4, 6);"
        )
        vars_ = _run_c(source, max_steps=500)
        assert vars_["r1"] == 8
        assert vars_["r2"] == 24
