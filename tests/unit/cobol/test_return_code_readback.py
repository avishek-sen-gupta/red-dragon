"""read_return_code decodes the RETURN-CODE field of the run-unit region."""

import pytest

from interpreter.address import Address
from interpreter.cobol.return_code_readback import read_return_code
from interpreter.cobol.run_unit import RUN_UNIT_VAR
from interpreter.cobol.symbolic_return_code_error import SymbolicReturnCodeError
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import StackFrame, SymbolicRegionWrite, VMState
from tests.covers import NotLanguageFeature, covers


def _vm_with_run_unit(region: bytes) -> VMState:
    frame = StackFrame(
        function_name=FuncName("__main__"),
        local_vars={RUN_UNIT_VAR: typed_from_runtime(4096)},
    )
    vm = VMState(call_stack=[frame])
    vm.region_set(Address("4096"), bytearray(region))
    return vm


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_return_code_decodes_the_run_unit_field():
    assert read_return_code(_vm_with_run_unit(b"\x00\x0c\x00\x00\x00\x00")) == 12
    assert read_return_code(_vm_with_run_unit(b"\xff\xfe\x00\x00\x00\x00")) == -2
    assert read_return_code(_vm_with_run_unit(bytes(6))) == 0
    assert not hasattr(VMState(), "cobol_run_unit_return_code")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_symbolic_return_code_is_an_error_not_the_bytes_it_masks():
    """A RETURN-CODE whose bytes a symbolic write covers has no integer value:
    the readback names the symbol instead of decoding the stale bytes beneath."""
    vm = _vm_with_run_unit(b"\x00\x0c\x00\x00\x00\x00")
    base = vm.segment_of(Address("4096")).base
    symbol = vm.fresh_symbolic(hint="return_code")
    vm.write_symbolic(SymbolicRegionWrite(address=base, width=2, value=symbol))

    with pytest.raises(SymbolicReturnCodeError) as raised:
        read_return_code(vm)

    assert (raised.value.value, str(raised.value)) == (
        symbol,
        "RETURN-CODE holds the symbolic value sym_0, not an integer",
    )
