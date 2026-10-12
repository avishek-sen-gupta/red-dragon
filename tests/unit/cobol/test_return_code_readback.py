"""read_return_code decodes the RETURN-CODE field of the run-unit region."""

from interpreter.address import Address
from interpreter.cobol.return_code_readback import read_return_code
from interpreter.cobol.run_unit import RUN_UNIT_VAR
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import StackFrame, VMState
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
