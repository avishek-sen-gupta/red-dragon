"""Integration test: type hints propagate through full pipeline (source -> frontend -> IR -> builder)."""

from __future__ import annotations

from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.go import GoFrontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.parser import TreeSitterParserFactory


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _find_symbolic_params(instructions: list[IRInstruction]) -> list[IRInstruction]:
    return [
        inst
        for inst in instructions
        if inst.opcode == Opcode.SYMBOLIC
        and any("param:" in str(op) for op in inst.operands)
    ]


class TestJavaTypeHintPropagation:
    def test_full_java_class_with_typed_members(self):
        source = """
        class Calculator {
            int result;

            int add(int a, int b) {
                int sum = a + b;
                return sum;
            }

            double divide(double x, double y) {
                return x / y;
            }
        }
        """
        frontend = JavaFrontend(TreeSitterParserFactory(), "java")
        instructions = frontend.lower(source.encode())
        builder = frontend.type_env_builder

        # Parameters should carry type hints via builder register_types
        params = _find_symbolic_params(instructions)
        int_params = [
            p for p in params if builder.register_types.get(p.result_reg) == "Int"
        ]
        float_params = [
            p for p in params if builder.register_types.get(p.result_reg) == "Float"
        ]

        # 'a' and 'b' should have Int type hints
        assert len(int_params) == 2, f"Expected 2 Int params, got {len(int_params)}"
        # 'x' and 'y' should have Float type hints
        assert (
            len(float_params) == 2
        ), f"Expected 2 Float params, got {len(float_params)}"

        # Local variable 'sum' should have Int type hint via builder var_types
        assert builder.var_types.get("sum") == "Int"


class TestGoTypeHintPropagation:
    def test_full_go_program_with_typed_vars(self):
        source = """
        package main

        func add(a int, b int) int {
            return a + b
        }

        var counter int = 0
        """
        frontend = GoFrontend(TreeSitterParserFactory(), "go")
        instructions = frontend.lower(source.encode())
        builder = frontend.type_env_builder

        # Parameters should carry type hints via builder register_types
        params = _find_symbolic_params(instructions)
        int_params = [
            p for p in params if builder.register_types.get(p.result_reg) == "Int"
        ]

        # 'a' and 'b' should have Int type hints
        assert len(int_params) == 2, f"Expected 2 Int params, got {len(int_params)}"

        # 'counter' should have Int type hint via builder var_types
        assert builder.var_types.get("counter") == "Int"
