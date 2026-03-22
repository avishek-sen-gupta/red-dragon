"""Unit tests — verify executor dispatches __cobol_* calls to io_provider."""

from interpreter.cfg import build_cfg
from interpreter.cobol.io_provider import NullIOProvider, StubIOProvider
from interpreter.vm.vm_types import SymbolicValue
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import unwrap


def _build_call_function_ir(func_name: str, *arg_literals) -> list[IRInstruction]:
    """Build a minimal IR sequence: LABEL entry, CONST args, CALL_FUNCTION, RETURN."""
    instructions: list[IRInstruction] = []
    instructions.append(IRInstruction(opcode=Opcode.LABEL, label="entry"))

    arg_regs = []
    for i, lit in enumerate(arg_literals):
        reg = f"%a{i}"
        instructions.append(
            IRInstruction(opcode=Opcode.CONST, result_reg=reg, operands=[lit])
        )
        arg_regs.append(reg)

    instructions.append(
        IRInstruction(
            opcode=Opcode.CALL_FUNCTION,
            result_reg="%result",
            operands=[func_name, *arg_regs],
        )
    )

    zero = "%zero"
    instructions.append(
        IRInstruction(opcode=Opcode.CONST, result_reg=zero, operands=[0])
    )
    instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=[zero]))
    return instructions


def _execute_with_provider(instructions, provider):
    """Execute IR with a given io_provider and return the VM."""
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)
    config = VMConfig(max_steps=50, io_provider=provider)
    vm, stats = execute_cfg(cfg, "entry", registry, config)
    return vm


class TestExecutorIOProviderDispatch:
    def test_stub_accept_returns_concrete_value(self):
        ir = _build_call_function_ir("__cobol_accept", "CONSOLE")
        provider = StubIOProvider(accept_values=["HELLO"])
        vm = _execute_with_provider(ir, provider)

        result = unwrap(vm.current_frame.registers.get("%result"))
        assert result == "HELLO"

    def test_stub_accept_empty_returns_symbolic(self):
        ir = _build_call_function_ir("__cobol_accept", "CONSOLE")
        provider = StubIOProvider(accept_values=[])
        vm = _execute_with_provider(ir, provider)

        result = unwrap(vm.current_frame.registers.get("%result"))
        assert isinstance(
            result, SymbolicValue
        ), f"expected SymbolicValue, got {type(result).__name__}: {result}"

    def test_null_provider_returns_symbolic(self):
        ir = _build_call_function_ir("__cobol_accept", "CONSOLE")
        provider = NullIOProvider()
        vm = _execute_with_provider(ir, provider)

        result = unwrap(vm.current_frame.registers.get("%result"))
        assert isinstance(
            result, SymbolicValue
        ), f"expected SymbolicValue, got {type(result).__name__}: {result}"

    def test_stub_read_returns_record(self):
        ir = _build_call_function_ir("__cobol_read_record", "CUST-FILE")
        provider = StubIOProvider(files={"CUST-FILE": {"records": ["RECORD-DATA"]}})
        vm = _execute_with_provider(ir, provider)

        result = unwrap(vm.current_frame.registers.get("%result"))
        assert result == "RECORD-DATA"

    def test_stub_write_captures_data(self):
        ir = _build_call_function_ir("__cobol_write_record", "OUT-FILE", "DATA1")
        provider = StubIOProvider()
        _execute_with_provider(ir, provider)

        assert provider.get_file("OUT-FILE").written == ["DATA1"]

    def test_stub_open_close_lifecycle(self):
        # Build IR: OPEN, then CLOSE
        instructions = [IRInstruction(opcode=Opcode.LABEL, label="entry")]

        instructions.append(
            IRInstruction(opcode=Opcode.CONST, result_reg="%f", operands=["MY-FILE"])
        )
        instructions.append(
            IRInstruction(opcode=Opcode.CONST, result_reg="%m", operands=["INPUT"])
        )
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%r1",
                operands=["__cobol_open_file", "%f", "%m"],
            )
        )
        instructions.append(
            IRInstruction(
                opcode=Opcode.CALL_FUNCTION,
                result_reg="%r2",
                operands=["__cobol_close_file", "%f"],
            )
        )

        instructions.append(
            IRInstruction(opcode=Opcode.CONST, result_reg="%z", operands=[0])
        )
        instructions.append(IRInstruction(opcode=Opcode.RETURN, operands=["%z"]))

        provider = StubIOProvider()
        _execute_with_provider(instructions, provider)

        assert provider.get_file("MY-FILE").is_open is False

    def test_no_provider_falls_through_to_builtins(self):
        """Without io_provider, __cobol_* builtins (prepare_digits etc.) still work."""
        ir = _build_call_function_ir("__cobol_prepare_digits", "123", 5, 2, True)
        # No provider — should fall through to builtins
        vm = _execute_with_provider(ir, None)
        result = unwrap(vm.current_frame.registers.get("%result"))
        # Should get a concrete list of digit ints from the builtin, not symbolic
        assert isinstance(
            result, list
        ), f"Expected concrete list, got {type(result)}: {result}"

    def test_non_cobol_call_handled_by_builtin(self):
        """Non __cobol_* calls are handled by builtins, not the IO provider."""
        ir = _build_call_function_ir("print", "hello")
        provider = StubIOProvider()
        vm = _execute_with_provider(ir, provider)
        # print returns None (the builtin handles it, not the provider)
        result = unwrap(vm.current_frame.registers.get("%result"))
        assert result is None
