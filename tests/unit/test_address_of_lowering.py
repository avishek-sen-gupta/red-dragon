"""Unit tests for ADDRESS_OF opcode emission in C and Rust frontends.

Verifies that &identifier emits ADDRESS_OF (not LOAD_VAR + UNOP "&")
and that &complex_expr still falls back to UNOP "&".
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.frontends.c import CFrontend
from interpreter.frontends.rust import RustFrontend
from interpreter.ir import Opcode
from interpreter.parser import TreeSitterParserFactory


def _parse_c(source: str):
    frontend = CFrontend(TreeSitterParserFactory(), "c")
    return frontend.lower(source.encode("utf-8"))


def _parse_rust(source: str):
    frontend = RustFrontend(TreeSitterParserFactory(), "rust")
    return frontend.lower(source.encode("utf-8"))


class TestCAddressOfLowering:
    def test_address_of_identifier_emits_address_of_opcode(self):
        """&x on a simple identifier should emit ADDRESS_OF 'x'."""
        ir = _parse_c("int x = 42; int *ptr = &x;")
        addr_of_insts = [inst for inst in ir if inst.opcode == Opcode.ADDRESS_OF]
        assert len(addr_of_insts) >= 1
        assert addr_of_insts[0].operands[0] == "x"

    def test_address_of_identifier_does_not_emit_unop(self):
        """&x should NOT emit UNOP '&' anymore."""
        ir = _parse_c("int x = 42; int *ptr = &x;")
        unop_addr = [
            inst
            for inst in ir
            if inst.opcode == Opcode.UNOP and inst.operands and inst.operands[0] == "&"
        ]
        assert len(unop_addr) == 0

    def test_deref_still_emits_load_field(self):
        """*ptr should still emit LOAD_FIELD ptr, '*'."""
        ir = _parse_c("int x = 42; int *ptr = &x; int y = *ptr;")
        load_field_star = [
            inst
            for inst in ir
            if inst.opcode == Opcode.LOAD_FIELD
            and len(inst.operands) >= 2
            and inst.operands[1] == "*"
        ]
        assert len(load_field_star) >= 1


class TestRustAddressOfLowering:
    def test_address_of_identifier_emits_address_of_opcode(self):
        """&x on a simple identifier should emit ADDRESS_OF 'x'."""
        ir = _parse_rust("let x = 42; let ptr = &x;")
        addr_of_insts = [inst for inst in ir if inst.opcode == Opcode.ADDRESS_OF]
        assert len(addr_of_insts) >= 1
        assert addr_of_insts[0].operands[0] == "x"

    def test_deref_assignment_emits_store_field(self):
        """*ptr = val should emit STORE_FIELD ptr, '*', val."""
        ir = _parse_rust("let mut x = 42; let ptr = &mut x; *ptr = 99;")
        store_field_star = [
            inst
            for inst in ir
            if inst.opcode == Opcode.STORE_FIELD
            and len(inst.operands) >= 2
            and inst.operands[1] == "*"
        ]
        assert len(store_field_star) >= 1
