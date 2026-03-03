"""Tests for OCCURS support in the COBOL frontend — subscript parsing and resolution."""

from interpreter.cobol.cobol_frontend import (
    _parse_subscript_notation,
    ResolvedFieldRef,
    CobolFrontend,
)
from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.pic_parser import parse_pic
from interpreter.cobol.cobol_expression import tokenize_expression, parse_expression
from interpreter.cobol.cobol_expression import FieldRefNode
from interpreter.ir import Opcode


class TestParseSubscriptNotation:
    def test_bare_name(self):
        """Bare name returns empty subscript."""
        base, sub = _parse_subscript_notation("WS-FIELD")
        assert base == "WS-FIELD"
        assert sub == ""

    def test_literal_subscript(self):
        """Numeric subscript parsed correctly."""
        base, sub = _parse_subscript_notation("WS-TABLE(3)")
        assert base == "WS-TABLE"
        assert sub == "3"

    def test_field_subscript(self):
        """Field reference as subscript parsed correctly."""
        base, sub = _parse_subscript_notation("WS-TABLE(WS-IDX)")
        assert base == "WS-TABLE"
        assert sub == "WS-IDX"

    def test_hyphenated_names(self):
        """Hyphenated field and subscript names work."""
        base, sub = _parse_subscript_notation("MY-TABLE-1(MY-IDX-2)")
        assert base == "MY-TABLE-1"
        assert sub == "MY-IDX-2"

    def test_no_parens_in_name(self):
        """Name without parens returns empty subscript."""
        base, sub = _parse_subscript_notation("SIMPLE")
        assert base == "SIMPLE"
        assert sub == ""


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

        ref = frontend._resolve_field_ref("WS-IDX", layout, "%r_region")
        assert ref.fl.name == "WS-IDX"
        assert ref.fl.byte_length == 4
        # Should have emitted a CONST for offset
        const_insts = [i for i in frontend._instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == [20]

    def test_literal_subscript_resolve(self):
        """Literal subscript emits correct offset arithmetic."""
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        frontend._reg_counter = 0
        frontend._label_counter = 0
        frontend._instructions = []

        ref = frontend._resolve_field_ref("WS-TBL(3)", layout, "%r_region")
        assert ref.fl.name == "WS-TBL"
        # Element size should be 4 (single element), not 20 (total)
        assert ref.fl.byte_length == 4
        # Should have emitted CONST, BINOP (sub), CONST (elem_size), BINOP (mul),
        # CONST (base), BINOP (add)
        binop_insts = [i for i in frontend._instructions if i.opcode == Opcode.BINOP]
        assert len(binop_insts) == 3  # idx-1, *(elem_size), +(base)

    def test_has_field_with_subscript(self):
        """_has_field correctly identifies subscripted field references."""
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        assert frontend._has_field("WS-TBL(3)", layout)
        assert frontend._has_field("WS-TBL", layout)
        assert frontend._has_field("WS-IDX", layout)
        assert not frontend._has_field("WS-NONEXISTENT", layout)
        assert not frontend._has_field("WS-NONEXISTENT(1)", layout)
