"""End-to-end test: division → array index round-trip with type coercion.

Verifies that when a program computes an array index via division (which
produces a float in Python), the type-aware executor coerces it to int
so that STORE_INDEX and LOAD_INDEX use matching heap keys.
"""

from types import MappingProxyType

from interpreter.cfg import build_cfg
from interpreter.constants import TypeName
from interpreter.default_conversion_rules import DefaultTypeConversionRules
from interpreter.function_signature import FunctionSignature
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.type_environment import TypeEnvironment
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver
from interpreter.typed_value import unwrap


def _build_division_index_program() -> list[IRInstruction]:
    """Build IR for: arr[0] = 42; idx = 4 / 2; result = arr[idx]."""
    return [
        IRInstruction(opcode=Opcode.LABEL, label="entry"),
        # Create array
        IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%arr", operands=["int"]),
        # Store 42 at index 0
        IRInstruction(opcode=Opcode.CONST, result_reg="%zero", operands=["0"]),
        IRInstruction(opcode=Opcode.CONST, result_reg="%val", operands=["42"]),
        IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%zero", "%val"]),
        # Compute index: 4 / 2 = 2.0 (float in Python)
        IRInstruction(opcode=Opcode.CONST, result_reg="%four", operands=["4"]),
        IRInstruction(opcode=Opcode.CONST, result_reg="%two", operands=["2"]),
        IRInstruction(
            opcode=Opcode.BINOP, result_reg="%idx", operands=["/", "%four", "%two"]
        ),
        # Store 99 at computed index
        IRInstruction(opcode=Opcode.CONST, result_reg="%val2", operands=["99"]),
        IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%arr", "%idx", "%val2"]),
        # Load from int literal 2 — should find value 99
        IRInstruction(opcode=Opcode.CONST, result_reg="%two_i", operands=["2"]),
        IRInstruction(
            opcode=Opcode.LOAD_INDEX, result_reg="%result", operands=["%arr", "%two_i"]
        ),
        # Store result in variable for inspection
        IRInstruction(opcode=Opcode.STORE_VAR, operands=["result", "%result"]),
        IRInstruction(opcode=Opcode.RETURN, operands=["%result"]),
    ]


class TestTypeCoecionEndToEnd:
    def test_division_index_round_trip(self):
        """Division result (float) used as array index should match integer lookup."""
        instructions = _build_division_index_program()
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        conversion_rules = DefaultTypeConversionRules()
        type_resolver = TypeResolver(conversion_rules)
        type_env = infer_types(instructions, type_resolver)

        # Verify type inference assigned Int to %idx (Int / Int → Int via floor division)
        assert type_env.register_types.get("%idx") == TypeName.INT

        vm, stats = execute_cfg(
            cfg,
            "entry",
            registry,
            VMConfig(max_steps=50),
            type_env=type_env,
            conversion_rules=conversion_rules,
        )

        # The stored value should be retrievable via the integer key
        assert unwrap(vm.current_frame.local_vars.get("result")) == 99

    def test_division_index_without_type_env_mismatches(self):
        """Without type coercion, float division index produces key '2.0' not '2'."""
        instructions = _build_division_index_program()
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        # No type environment — executor uses identity rules (no coercion)
        vm, stats = execute_cfg(
            cfg,
            "entry",
            registry,
            VMConfig(max_steps=50),
        )

        # Without coercion, 4/2 = 2.0 (float), stored at key "2.0"
        # Load with int 2 looks for key "2" — won't find it, gets symbolic
        result = unwrap(vm.current_frame.local_vars.get("result"))
        assert result != 99, "Without type coercion, the round-trip should fail"
