"""Tests for IRInstruction type_hint field."""

from interpreter.ir import IRInstruction, Opcode, NO_SOURCE_LOCATION


class TestIRInstructionTypeHint:
    """Verify the optional type_hint field on IRInstruction."""

    def test_default_type_hint_is_empty_string(self):
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="t0", operands=[42])
        assert inst.type_hint == ""

    def test_type_hint_can_be_specified(self):
        inst = IRInstruction(
            opcode=Opcode.CONST, result_reg="t0", operands=[42], type_hint="int"
        )
        assert inst.type_hint == "int"

    def test_type_hint_preserved_across_opcodes(self):
        instructions = [
            IRInstruction(
                opcode=Opcode.CONST, result_reg="t0", operands=[3.14], type_hint="float"
            ),
            IRInstruction(
                opcode=Opcode.LOAD_VAR, result_reg="t1", operands=["x"], type_hint="str"
            ),
            IRInstruction(
                opcode=Opcode.BINOP,
                result_reg="t2",
                operands=["+", "t0", "t1"],
                type_hint="int",
            ),
            IRInstruction(
                opcode=Opcode.STORE_VAR, operands=["y", "t2"], type_hint="int"
            ),
        ]
        assert [i.type_hint for i in instructions] == ["float", "str", "int", "int"]

    def test_existing_fields_unaffected_by_type_hint(self):
        inst = IRInstruction(
            opcode=Opcode.CONST,
            result_reg="t0",
            operands=[99],
            label="my_label",
            type_hint="int",
        )
        assert inst.opcode == Opcode.CONST
        assert inst.result_reg == "t0"
        assert inst.operands == [99]
        assert inst.label == "my_label"
        assert inst.source_location == NO_SOURCE_LOCATION

    def test_str_representation_includes_type_hint(self):
        without = IRInstruction(opcode=Opcode.CONST, result_reg="t0", operands=[42])
        with_hint = IRInstruction(
            opcode=Opcode.CONST, result_reg="t0", operands=[42], type_hint="int"
        )
        assert str(without) == "t0 = const 42"
        assert str(with_hint) == "t0 = const 42  :: int"

    def test_type_hint_in_serialization(self):
        inst = IRInstruction(
            opcode=Opcode.CONST, result_reg="t0", operands=[42], type_hint="int"
        )
        data = inst.model_dump()
        assert data["type_hint"] == "int"

    def test_type_hint_roundtrips_through_json(self):
        inst = IRInstruction(
            opcode=Opcode.CONST, result_reg="t0", operands=[42], type_hint="float"
        )
        json_str = inst.model_dump_json()
        restored = IRInstruction.model_validate_json(json_str)
        assert restored.type_hint == "float"

    def test_default_type_hint_roundtrips_through_json(self):
        inst = IRInstruction(opcode=Opcode.CONST, result_reg="t0", operands=[42])
        json_str = inst.model_dump_json()
        restored = IRInstruction.model_validate_json(json_str)
        assert restored.type_hint == ""
