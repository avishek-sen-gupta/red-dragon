"""Tests for OCCURS support in the COBOL frontend — subscript parsing and resolution."""

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_expression import LiteralNode
from interpreter.cobol.cobol_frontend import (
    CobolFrontend,
)
from interpreter.cobol.data_layout import DataLayout, build_data_layout
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

    def test_literal_subscript_resolve(self):
        """A structured literal subscript emits correct offset arithmetic.

        The legacy ``"NAME(SUB)"`` string path is retired (red-dragon-6ddr); the
        subscript is now passed structurally via ``subscripts=``.
        """
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        frontend._reg_counter = 0
        frontend._label_counter = 0
        frontend._instructions = []

        materialised = _materialise(layout)
        ref, _ = frontend._resolve_field_ref(
            "WS-TBL", materialised, subscripts=(LiteralNode("3"),)
        )
        assert ref.fl.name == "WS-TBL"
        # Element size should be 4 (single element), not 20 (total)
        assert ref.fl.byte_length == 4
        # Should have emitted CONST, BINOP (sub), CONST (elem_size), BINOP (mul),
        # CONST (base), BINOP (add)
        binop_insts = [i for i in frontend._instructions if i.opcode == Opcode.BINOP]
        assert len(binop_insts) == 3
        # Verify the three operations: (idx-1), *(elem_size), +(base)
        assert [i.operands[0] for i in binop_insts] == ["-", "*", "+"]

    def test_has_field_with_subscript(self):
        """_has_field identifies base field names (subscripts are structural now).

        Post red-dragon-6ddr, ``has_field`` takes a BARE name; the subscript is
        carried separately and handled by ``resolve_field_ref``.
        """
        frontend = self._make_frontend()
        layout = self._make_layout_with_occurs()
        materialised = _materialise(layout)
        assert frontend._has_field("WS-TBL", materialised)
        assert frontend._has_field("WS-IDX", materialised)
        assert not frontend._has_field("WS-NONEXISTENT", materialised)
