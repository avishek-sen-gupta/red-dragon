"""Tests for BinopKind and UnopKind enums."""

import pytest

from interpreter.operator_kind import BinopKind, UnopKind


class TestBinopKind:
    def test_value_returns_symbol(self):
        assert BinopKind.ADD.value == "+"
        assert BinopKind.EQ.value == "=="
        assert BinopKind.AND.value == "and"

    def test_equality_with_string(self):
        assert BinopKind.ADD == "+"
        assert BinopKind.POWER == "**"

    def test_all_vm_operators_covered(self):
        """Every operator in the VM's BINOP_TABLE must have a BinopKind."""
        from interpreter.vm.vm import Operators

        binop_values = {k.value for k in BinopKind}
        for op in Operators.BINOP_TABLE:
            assert op in binop_values, f"Missing BinopKind for '{op}'"

    def test_resolve_binop(self):
        from interpreter.operator_kind import resolve_binop

        assert resolve_binop("+") == BinopKind.ADD
        assert resolve_binop("==") == BinopKind.EQ

    def test_resolve_binop_rejects_unknown(self):
        from interpreter.operator_kind import resolve_binop

        with pytest.raises(ValueError, match="Unknown binary operator"):
            resolve_binop("unknown_op")


class TestUnopKind:
    def test_value_returns_symbol(self):
        assert UnopKind.NEG.value == "-"
        assert UnopKind.NOT.value == "not"
        assert UnopKind.BANG.value == "!"

    def test_all_vm_operators_covered(self):
        """Every unary operator the VM handles must have an UnopKind."""
        expected = {"-", "+", "not", "~", "#", "!", "!!", "&"}
        unop_values = {k.value for k in UnopKind}
        for op in expected:
            assert op in unop_values, f"Missing UnopKind for '{op}'"

    def test_resolve_unop(self):
        from interpreter.operator_kind import resolve_unop

        assert resolve_unop("-") == UnopKind.NEG
        assert resolve_unop("not") == UnopKind.NOT

    def test_resolve_unop_rejects_unknown(self):
        from interpreter.operator_kind import resolve_unop

        with pytest.raises(ValueError, match="Unknown unary operator"):
            resolve_unop("unknown_op")
