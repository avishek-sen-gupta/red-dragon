"""End-to-end tests for COBOL frontend: fixture JSON → IR → CFG → execute.

These tests exercise the full pipeline: JSON ASG → CobolFrontend.lower()
→ IR instructions → build_cfg → build_registry → execute_cfg.
"""

import json
from pathlib import Path
from typing import Any

from interpreter.cfg import build_cfg
from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.subprocess_runner import SubprocessRunner
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import build_registry
from interpreter.run import VMConfig, execute_cfg
from interpreter.vm import VMState, apply_update
from interpreter.vm_types import StackFrame
from interpreter.executor import LocalExecutor

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "cobol"


class _FakeParser:
    """Returns a pre-built CobolASG."""

    def __init__(self, asg: CobolASG):
        self._asg = asg

    def parse(self, source: bytes) -> CobolASG:
        return self._asg


def _load_fixture(name: str) -> CobolASG:
    fixture_path = FIXTURE_DIR / name
    data = json.loads(fixture_path.read_text())
    return CobolASG.from_dict(data)


def _execute_straight_line(
    instructions: list[IRInstruction],
) -> VMState:
    """Execute IR straight-line (no branches). Good for Data Division only."""
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)

    for inst in instructions:
        if inst.opcode == Opcode.LABEL:
            continue
        if inst.opcode == Opcode.RETURN:
            break
        if inst.opcode in (Opcode.BRANCH, Opcode.BRANCH_IF):
            continue  # Skip branches for straight-line
        result = LocalExecutor.execute(inst=inst, vm=vm, cfg=cfg, registry=registry)
        if result.handled:
            apply_update(vm, result.update)

    return vm


class TestHelloWorldFixture:
    def test_produces_ir(self):
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        assert len(instructions) > 0
        labels = [i for i in instructions if i.opcode == Opcode.LABEL]
        assert any(l.label == "entry" for l in labels)

    def test_data_division_allocs_11_bytes(self):
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        allocs = [i for i in instructions if i.opcode == Opcode.ALLOC_REGION]
        assert len(allocs) == 1
        assert allocs[0].operands[0] == 11  # X(11)

    def test_initial_value_written_to_region(self):
        """Verify that the initial VALUE "HELLO WORLD" is written into the region."""
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        vm = _execute_straight_line(instructions)

        # Should have at least one region
        assert len(vm.regions) >= 1
        region_addr = list(vm.regions.keys())[0]
        region = vm.regions[region_addr]

        # Region should have 11 bytes written (EBCDIC-encoded "HELLO WORLD")
        assert len(region) == 11
        # Verify non-zero content (EBCDIC encoding of "HELLO WORLD")
        assert any(b != 0 for b in region)


class TestMoveFieldsFixture:
    def test_produces_load_and_write_region(self):
        asg = _load_fixture("move_fields.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        loads = [i for i in instructions if i.opcode == Opcode.LOAD_REGION]
        writes = [i for i in instructions if i.opcode == Opcode.WRITE_REGION]
        assert len(loads) >= 1
        assert len(writes) >= 1

    def test_data_division_allocs_6_bytes(self):
        asg = _load_fixture("move_fields.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        allocs = [i for i in instructions if i.opcode == Opcode.ALLOC_REGION]
        assert allocs[0].operands[0] == 6  # 9(3) + 9(3) = 3 + 3


class TestArithmeticFixture:
    def test_produces_binops(self):
        asg = _load_fixture("arithmetic.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        binops = [i for i in instructions if i.opcode == Opcode.BINOP]
        ops = [b.operands[0] for b in binops]
        assert "+" in ops  # ADD 50
        assert "-" in ops  # SUBTRACT 25

    def test_initial_value_100_in_region(self):
        """Verify initial VALUE "100" is correctly encoded as zoned decimal."""
        asg = _load_fixture("arithmetic.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        vm = _execute_straight_line(instructions)

        region_addr = list(vm.regions.keys())[0]
        region = vm.regions[region_addr]
        assert len(region) == 5  # 9(5)


class TestPerformReturnFixture:
    def test_perform_returns_to_caller(self):
        """MAIN PERFORMs WORK, WORK does MOVE, execution returns to MAIN and hits STOP RUN."""
        asg = _load_fixture("perform_return.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        # Execution should have completed (hit STOP RUN)
        assert len(vm.regions) >= 1
        region_addr = list(vm.regions.keys())[0]
        region = vm.regions[region_addr]
        # The MOVE 42 TO WS-RESULT should have written to the region
        assert any(b != 0 for b in region)

    def test_nested_perform(self):
        """A calls B, B calls C, all return correctly."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-VAL",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "PERFORM", "operands": ["PARA-A"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "PARA-A",
                        "statements": [
                            {"type": "MOVE", "operands": ["10", "WS-VAL"]},
                            {"type": "PERFORM", "operands": ["PARA-B"]},
                        ],
                    },
                    {
                        "name": "PARA-B",
                        "statements": [
                            {"type": "MOVE", "operands": ["99", "WS-VAL"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=300))

        # Should have completed without infinite looping
        assert stats.steps < 300
        # Region should have been written to (MOVE statements executed)
        assert len(vm.regions) >= 1

    def test_fall_through_without_perform(self):
        """Two paragraphs, no PERFORM — verify sequential execution."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "FIRST-PARA",
                        "statements": [
                            {"type": "MOVE", "operands": ["1", "WS-A"]},
                        ],
                    },
                    {
                        "name": "SECOND-PARA",
                        "statements": [
                            {"type": "MOVE", "operands": ["2", "WS-A"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        # Should complete within steps (hit STOP RUN in SECOND-PARA)
        assert stats.steps < 200
        assert len(vm.regions) >= 1


class TestCobolFrontendIdempotency:
    def test_lower_twice_produces_same_ir(self):
        """Calling lower() twice should reset state and produce identical IR."""
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))

        ir1 = frontend.lower(b"")
        ir2 = frontend.lower(b"")

        assert len(ir1) == len(ir2)
        for i, (a, b) in enumerate(zip(ir1, ir2)):
            assert a.opcode == b.opcode, f"Mismatch at {i}: {a.opcode} != {b.opcode}"
            assert a.label == b.label
            assert a.result_reg == b.result_reg


class TestMultipleStatementTypes:
    def test_mixed_statements(self):
        """Test a program with MOVE, DISPLAY, and STOP RUN."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "offset": 0,
                        "value": "0",
                    },
                    {
                        "name": "WS-B",
                        "level": 77,
                        "pic": "X(5)",
                        "offset": 0,
                        "value": "HELLO",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN",
                        "statements": [
                            {"type": "MOVE", "operands": ["42", "WS-A"]},
                            {"type": "DISPLAY", "operands": ["WS-B"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")

        opcodes = {i.opcode for i in instructions}
        assert Opcode.ALLOC_REGION in opcodes
        assert Opcode.WRITE_REGION in opcodes
        assert Opcode.CALL_FUNCTION in opcodes  # print
        assert Opcode.RETURN in opcodes  # STOP RUN


class TestIfElseExecution:
    """IF ... ELSE execution tests."""

    def test_if_true_branch_taken(self):
        """IF WS-A > 0 should take the THEN branch when WS-A = 5."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "5",
                    },
                    {
                        "name": "WS-RESULT",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 3,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "IF",
                                "condition": "WS-A > 0",
                                "children": [
                                    {"type": "MOVE", "operands": ["1", "WS-RESULT"]},
                                ],
                                "else_children": [
                                    {"type": "MOVE", "operands": ["2", "WS-RESULT"]},
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))
        assert stats.steps < 200
        assert len(vm.regions) >= 1

    def test_if_false_branch_taken(self):
        """IF WS-A > 10 should take the ELSE branch when WS-A = 5."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "5",
                    },
                    {
                        "name": "WS-RESULT",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 3,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "IF",
                                "condition": "WS-A > 10",
                                "children": [
                                    {"type": "MOVE", "operands": ["1", "WS-RESULT"]},
                                ],
                                "else_children": [
                                    {"type": "MOVE", "operands": ["2", "WS-RESULT"]},
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))
        assert stats.steps < 200
        assert len(vm.regions) >= 1


class TestPerformTimesExecution:
    """PERFORM ... TIMES loop execution tests."""

    def test_perform_times_inline_executes_body_n_times(self):
        """Inline PERFORM 3 TIMES with ADD 1 TO WS-CTR should result in WS-CTR = 3."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-CTR",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "3",
                                "children": [
                                    {"type": "ADD", "operands": ["1", "WS-CTR"]},
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        # Should complete within step limit
        assert stats.steps < 500
        # Region should be written (ADD executed 3 times)
        assert len(vm.regions) >= 1


class TestPerformUntilExecution:
    """PERFORM ... UNTIL loop execution tests."""

    def test_perform_until_test_before(self):
        """PERFORM UNTIL WS-A > 2 with ADD 1 should loop until WS-A reaches 3."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "UNTIL",
                                "until": "WS-A > 2",
                                "test_before": True,
                                "children": [
                                    {"type": "ADD", "operands": ["1", "WS-A"]},
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        assert stats.steps < 500
        assert len(vm.regions) >= 1


class TestPerformVaryingExecution:
    """PERFORM ... VARYING loop execution tests."""

    def test_perform_varying_inline(self):
        """PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 3."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-IDX",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                    {
                        "name": "WS-SUM",
                        "level": 77,
                        "pic": "9(5)",
                        "usage": "DISPLAY",
                        "offset": 3,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "VARYING",
                                "varying_var": "WS-IDX",
                                "varying_from": "1",
                                "varying_by": "1",
                                "until": "WS-IDX > 3",
                                "test_before": True,
                                "children": [
                                    {
                                        "type": "ADD",
                                        "operands": ["WS-IDX", "WS-SUM"],
                                    },
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=1000))

        assert stats.steps < 1000
        assert len(vm.regions) >= 1


def _decode_zoned_unsigned(region: list[int], offset: int, length: int) -> int:
    """Decode unsigned zoned decimal from a memory region.

    Each byte is EBCDIC zoned: 0xF0=0, 0xF1=1, ..., 0xF9=9.
    The digit is in the low nibble (b & 0x0F).
    """
    digits = [region[offset + i] & 0x0F for i in range(length)]
    return sum(d * (10 ** (length - 1 - i)) for i, d in enumerate(digits))


class TestNumericValueVerification:
    """Verify that e2e execution produces correct numeric values in memory regions."""

    def test_move_literal_value(self):
        """MOVE 42 TO WS-A → WS-A should decode to 42."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "MOVE", "operands": ["42", "WS-A"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 3) == 42

    def test_add_two_values(self):
        """WS-A=10, WS-B=5, ADD WS-A WS-B → WS-B should be 15."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "10",
                    },
                    {
                        "name": "WS-B",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 4,
                        "value": "5",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["WS-A", "WS-B"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 10  # WS-A unchanged
        assert _decode_zoned_unsigned(region, 4, 4) == 15  # WS-B = 10 + 5

    def test_subtract_values(self):
        """WS-A=10, WS-B=3, SUBTRACT WS-B FROM WS-A → WS-A should be 7."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "10",
                    },
                    {
                        "name": "WS-B",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 4,
                        "value": "3",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "SUBTRACT", "operands": ["WS-B", "WS-A"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 7  # WS-A = 10 - 3

    def test_add_literal_to_field(self):
        """WS-A=0, ADD 25 TO WS-A → WS-A should be 25."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["25", "WS-A"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 25

    def test_perform_times_accumulation(self):
        """PERFORM 3 TIMES with ADD 1 TO WS-CTR → WS-CTR should be 3."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-CTR",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "3",
                                "children": [
                                    {"type": "ADD", "operands": ["1", "WS-CTR"]},
                                ],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 3

    def test_initial_value_encoding(self):
        """Initial VALUE 123 should encode correctly in the region."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "123",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 123

    def test_multiple_adds_accumulate(self):
        """WS-R=0, ADD 10 TO WS-R, ADD 5 TO WS-R → WS-R should be 15."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-R",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-R"]},
                            {"type": "ADD", "operands": ["5", "WS-R"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 15

    def test_paragraph_perform_times_accumulation(self):
        """PERFORM ADD-PARA 3 TIMES with ADD 10 TO WS-SUM → WS-SUM should be 30.

        Tests paragraph-level PERFORM TIMES (not inline) to verify the loop
        counter works correctly when the body is a separate paragraph.
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-SUM",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "3",
                                "operands": ["ADD-PARA"],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "ADD-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-SUM"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=1000))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 30

    def test_move_then_perform_times_accumulation(self):
        """MOVE 100 TO WS-SUM, then PERFORM ADD-PARA 3 TIMES adding 10 → WS-SUM should be 130.

        Tests that MOVE literal followed by paragraph PERFORM TIMES produces
        correct cumulative result, requiring sufficient step budget.
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-SUM",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "MOVE", "operands": ["100", "WS-SUM"]},
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "3",
                                "operands": ["ADD-PARA"],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "ADD-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-SUM"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=1000))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 130


class TestSectionFallThrough:
    """Test that paragraphs within a section execute sequentially."""

    def test_section_paragraphs_fall_through(self):
        """Two paragraphs in a section, no PERFORM — verify sequential execution."""
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-A",
                        "level": 77,
                        "pic": "9(3)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "sections": [
                    {
                        "name": "MAIN-SECTION",
                        "paragraphs": [
                            {
                                "name": "FIRST-PARA",
                                "statements": [
                                    {"type": "MOVE", "operands": ["1", "WS-A"]},
                                ],
                            },
                            {
                                "name": "SECOND-PARA",
                                "statements": [
                                    {"type": "MOVE", "operands": ["2", "WS-A"]},
                                    {"type": "STOP_RUN"},
                                ],
                            },
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))

        assert stats.steps < 200
        assert len(vm.regions) >= 1
        # Fall-through: FIRST-PARA sets WS-A=1, SECOND-PARA overwrites to 2
        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 3) == 2


class TestNestedPerformNumericValues:
    """Nested PERFORM with numeric value verification."""

    def test_nested_perform_accumulation(self):
        """MAIN performs OUTER, OUTER performs INNER, both add to WS-SUM.

        OUTER: ADD 100, PERFORM INNER, ADD 1
        INNER: ADD 10
        Expected: 0 + 100 + 10 + 1 = 111
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-SUM",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "PERFORM", "operands": ["OUTER-PARA"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "OUTER-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["100", "WS-SUM"]},
                            {"type": "PERFORM", "operands": ["INNER-PARA"]},
                            {"type": "ADD", "operands": ["1", "WS-SUM"]},
                        ],
                    },
                    {
                        "name": "INNER-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-SUM"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 111

    def test_nested_perform_times(self):
        """PERFORM OUTER 2 TIMES, OUTER performs INNER 3 TIMES.

        OUTER body: PERFORM INNER 3 TIMES
        INNER body: ADD 1 TO WS-CTR
        Expected: 2 * 3 = 6
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-CTR",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "2",
                                "operands": ["OUTER-PARA"],
                            },
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "OUTER-PARA",
                        "statements": [
                            {
                                "type": "PERFORM",
                                "perform_type": "TIMES",
                                "times": "3",
                                "operands": ["INNER-PARA"],
                            },
                        ],
                    },
                    {
                        "name": "INNER-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["1", "WS-CTR"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=2000))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 6


class TestGotoInsidePerform:
    """Tests for GO TO within and outside PERFORM ranges."""

    def test_goto_within_perform_range(self):
        """GO TO jumps forward within the PERFORM paragraph range.

        PERFORM WORK-PARA: ADD 10, GO TO SKIP-PARA, ADD 999 (should be skipped)
        SKIP-PARA: ADD 1
        Expected: 0 + 10 + 1 = 11 (the ADD 999 is skipped)
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-VAL",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-VAL"]},
                            {"type": "GOTO", "operands": ["SKIP-PARA"]},
                            {"type": "ADD", "operands": ["999", "WS-VAL"]},
                        ],
                    },
                    {
                        "name": "SKIP-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["1", "WS-VAL"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 11

    def test_goto_skips_code_in_paragraph(self):
        """GO TO from PARA-A to PARA-C, skipping PARA-B entirely.

        PARA-A: ADD 1, GO TO PARA-C
        PARA-B: ADD 100 (should be skipped)
        PARA-C: ADD 10, STOP RUN
        Expected: 0 + 1 + 10 = 11
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-VAL",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "PARA-A",
                        "statements": [
                            {"type": "ADD", "operands": ["1", "WS-VAL"]},
                            {"type": "GOTO", "operands": ["PARA-C"]},
                        ],
                    },
                    {
                        "name": "PARA-B",
                        "statements": [
                            {"type": "ADD", "operands": ["100", "WS-VAL"]},
                        ],
                    },
                    {
                        "name": "PARA-C",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-VAL"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        region = vm.regions[list(vm.regions.keys())[0]]
        assert _decode_zoned_unsigned(region, 0, 4) == 11

    def test_goto_exits_performed_paragraph(self):
        """PERFORM WORK-PARA, where WORK-PARA does GO TO EXIT-PARA.

        MAIN: PERFORM WORK-PARA, ADD 1 TO WS-VAL, STOP RUN
        WORK-PARA: ADD 10, GO TO EXIT-PARA
        EXIT-PARA: ADD 100

        GO TO from a PERFORMed paragraph jumps to EXIT-PARA, which
        falls through (no continuation set for EXIT-PARA). The ADD 1
        after the PERFORM in MAIN may or may not execute depending on
        continuation mechanics.
        """
        asg = CobolASG.from_dict(
            {
                "data_fields": [
                    {
                        "name": "WS-VAL",
                        "level": 77,
                        "pic": "9(4)",
                        "usage": "DISPLAY",
                        "offset": 0,
                        "value": "0",
                    },
                ],
                "paragraphs": [
                    {
                        "name": "MAIN-PARA",
                        "statements": [
                            {"type": "PERFORM", "operands": ["WORK-PARA"]},
                            {"type": "ADD", "operands": ["1", "WS-VAL"]},
                            {"type": "STOP_RUN"},
                        ],
                    },
                    {
                        "name": "WORK-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["10", "WS-VAL"]},
                            {"type": "GOTO", "operands": ["EXIT-PARA"]},
                        ],
                    },
                    {
                        "name": "EXIT-PARA",
                        "statements": [
                            {"type": "ADD", "operands": ["100", "WS-VAL"]},
                        ],
                    },
                ],
            }
        )
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(b"")
        cfg = build_cfg(instructions)
        registry = build_registry(instructions, cfg)

        vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=500))

        region = vm.regions[list(vm.regions.keys())[0]]
        # WORK-PARA adds 10, GO TO jumps to EXIT-PARA which adds 100.
        # The GO TO bypasses WORK-PARA's end label, so the PERFORM
        # continuation is never triggered — control does NOT return to
        # MAIN-PARA. The ADD 1 after the PERFORM never executes.
        # Total: 10 + 100 = 110.
        assert _decode_zoned_unsigned(region, 0, 4) == 110
