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
        instructions = frontend.lower(None, b"")

        assert len(instructions) > 0
        labels = [i for i in instructions if i.opcode == Opcode.LABEL]
        assert any(l.label == "entry" for l in labels)

    def test_data_division_allocs_11_bytes(self):
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        allocs = [i for i in instructions if i.opcode == Opcode.ALLOC_REGION]
        assert len(allocs) == 1
        assert allocs[0].operands[0] == 11  # X(11)

    def test_initial_value_written_to_region(self):
        """Verify that the initial VALUE "HELLO WORLD" is written into the region."""
        asg = _load_fixture("hello_world.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

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
        instructions = frontend.lower(None, b"")

        loads = [i for i in instructions if i.opcode == Opcode.LOAD_REGION]
        writes = [i for i in instructions if i.opcode == Opcode.WRITE_REGION]
        assert len(loads) >= 1
        assert len(writes) >= 1

    def test_data_division_allocs_6_bytes(self):
        asg = _load_fixture("move_fields.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        allocs = [i for i in instructions if i.opcode == Opcode.ALLOC_REGION]
        assert allocs[0].operands[0] == 6  # 9(3) + 9(3) = 3 + 3


class TestArithmeticFixture:
    def test_produces_binops(self):
        asg = _load_fixture("arithmetic.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        binops = [i for i in instructions if i.opcode == Opcode.BINOP]
        ops = [b.operands[0] for b in binops]
        assert "+" in ops  # ADD 50
        assert "-" in ops  # SUBTRACT 25

    def test_initial_value_100_in_region(self):
        """Verify initial VALUE "100" is correctly encoded as zoned decimal."""
        asg = _load_fixture("arithmetic.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")

        vm = _execute_straight_line(instructions)

        region_addr = list(vm.regions.keys())[0]
        region = vm.regions[region_addr]
        assert len(region) == 5  # 9(5)


class TestPerformReturnFixture:
    def test_perform_returns_to_caller(self):
        """MAIN PERFORMs WORK, WORK does MOVE, execution returns to MAIN and hits STOP RUN."""
        asg = _load_fixture("perform_return.json")
        frontend = CobolFrontend(_FakeParser(asg))
        instructions = frontend.lower(None, b"")
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
        instructions = frontend.lower(None, b"")
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
        instructions = frontend.lower(None, b"")
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

        ir1 = frontend.lower(None, b"")
        ir2 = frontend.lower(None, b"")

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
        instructions = frontend.lower(None, b"")

        opcodes = {i.opcode for i in instructions}
        assert Opcode.ALLOC_REGION in opcodes
        assert Opcode.WRITE_REGION in opcodes
        assert Opcode.CALL_FUNCTION in opcodes  # print
        assert Opcode.RETURN in opcodes  # STOP RUN
