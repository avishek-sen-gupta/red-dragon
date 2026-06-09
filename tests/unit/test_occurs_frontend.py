"""Tests for OCCURS support in the COBOL frontend — subscript parsing and resolution."""

import pytest

from interpreter.cobol.cobol_frontend import (
    ResolvedFieldRef,
    CobolFrontend,
)
from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.pic_parser import parse_pic
from interpreter.cobol.cobol_expression import tokenize_expression, parse_expression
from interpreter.cobol.cobol_expression import FieldRefNode
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.ir import Opcode
from interpreter.register import Register


def _materialise(layout: DataLayout) -> MaterialisedSectionedLayout:
    """Wrap a DataLayout in a MaterialisedSectionedLayout with a dummy region register."""
    empty = DataLayout()
    dummy_reg = Register("%r_region")
    return MaterialisedSectionedLayout(
        working_storage=(layout, dummy_reg),
        linkage=(empty, Register("__no_reg__")),
        local_storage=(empty, Register("__no_reg__")),
    )


class TestExpressionTokenizerWithSubscripts:
    def test_subscripted_field_is_single_token(self):
        """WS-TABLE(IDX) is captured as a single token."""
        tokens = tokenize_expression("WS-TABLE(IDX) + 1")
        assert tokens == ["WS-TABLE(IDX)", "+", "1"]

    def test_subscripted_field_with_literal(self):
        """WS-TABLE(3) is captured as a single token."""
        tokens = tokenize_expression("WS-TABLE(3) * 2")
        assert tokens == ["WS-TABLE(3)", "*", "2"]

    def test_plain_expression_unchanged(self):
        """Regular expressions still tokenize correctly."""
        tokens = tokenize_expression("WS-A + WS-B * 2")
        assert tokens == ["WS-A", "+", "WS-B", "*", "2"]

    def test_subscripted_in_expression_parses_as_field_ref(self):
        """Subscripted field parses to FieldRefNode."""
        tree = parse_expression("WS-TABLE(3) + 1")
        # The left side of the addition should be a FieldRefNode
        assert hasattr(tree, "left")
        assert isinstance(tree.left, FieldRefNode)
        assert tree.left.name == "WS-TABLE(3)"


class TestResolveFieldRef:
    """Tests for _resolve_field_ref via the frontend's public interface."""

    def _make_frontend(self):
        """Create a CobolFrontend with a dummy parser."""

        class DummyParser:
            def parse(self, source):
                pass

        return CobolFrontend(cobol_parser=DummyParser())

    def _make_layout_with_occurs(self):
        """Create a layout with an OCCURS field."""
        fields = [
            CobolField(
                name="WS-TBL",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                occurs=5,
                element_size=4,
            ),
            CobolField(
                name="WS-IDX",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=20,
            ),
        ]
        return build_data_layout(fields)

    def test_bare_name_resolve(self):
        """Bare name resolves to FieldLayout with CONST offset."""
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        # Initialize frontend state
        frontend._reg_counter = 0
        frontend._label_counter = 0
        frontend._instructions = []

        materialised = _materialise(layout)
        ref, _ = frontend._resolve_field_ref("WS-IDX", materialised)
        assert ref.fl.name == "WS-IDX"
        assert ref.fl.byte_length == 4
        # Should have emitted a CONST for offset
        const_insts = [i for i in frontend._instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == [20]

    @pytest.mark.xfail(
        reason="COMPUTE-string subscript structuring pending red-dragon-ovzi",
        strict=True,
    )
    def test_literal_subscript_resolve(self):
        """Literal subscript emits correct offset arithmetic."""
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        frontend._reg_counter = 0
        frontend._label_counter = 0
        frontend._instructions = []

        materialised = _materialise(layout)
        ref, _ = frontend._resolve_field_ref("WS-TBL(3)", materialised)
        assert ref.fl.name == "WS-TBL"
        # Element size should be 4 (single element), not 20 (total)
        assert ref.fl.byte_length == 4
        # Should have emitted CONST, BINOP (sub), CONST (elem_size), BINOP (mul),
        # CONST (base), BINOP (add)
        binop_insts = [i for i in frontend._instructions if i.opcode == Opcode.BINOP]
        assert len(binop_insts) == 3
        # Verify the three operations: (idx-1), *(elem_size), +(base)
        assert [i.operands[0] for i in binop_insts] == ["-", "*", "+"]

    @pytest.mark.xfail(
        reason="COMPUTE-string subscript structuring pending red-dragon-ovzi",
        strict=True,
    )
    def test_has_field_with_subscript(self):
        """_has_field correctly identifies subscripted field references."""
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        materialised = _materialise(layout)
        assert frontend._has_field("WS-TBL(3)", materialised)
        assert frontend._has_field("WS-TBL", materialised)
        assert frontend._has_field("WS-IDX", materialised)
        assert not frontend._has_field("WS-NONEXISTENT", materialised)
        assert not frontend._has_field("WS-NONEXISTENT(1)", materialised)
