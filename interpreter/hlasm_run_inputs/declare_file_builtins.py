# pyright: standard
"""OPEN's file declaration as a builtin: the provider's sequential frame for a DDNAME, built from the record format and length the DCB holds at run time; irreducible, since the frame is a provider value no IR can build."""

from collections.abc import Mapping, Sequence

from cobol_asg.file_enums import FileOrganization
from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.run_input_names import DECLARE_FILE_BUILTIN
from interpreter.record_io.file_frame import FileFrame
from interpreter.record_io.prime_key import PrimeKey
from interpreter.types.typed_value import TypedValue, typed
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult

PROVIDER_DECLARATION = FuncName("__cobol_declare_file")
PROVIDER_OUTCOME = FuncName("__cobol_io_outcome")
NO_PROGRAM = ""


def declare_file_builtins() -> Mapping[FuncName, Builtin]:
    def declare_file(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        name, variable, record_length = (a.value for a in args)
        frame = FileFrame(
            str(name),
            FileOrganization.SEQUENTIAL,
            PrimeKey(),
            bool(variable),
            int(record_length),
        )
        declared = vm.io_provider.handle_call(
            PROVIDER_DECLARATION, [typed(frame.data()), typed(NO_PROGRAM)]
        )
        outcome = vm.io_provider.handle_call(
            PROVIDER_OUTCOME, [typed(declared), typed(NO_PROGRAM)]
        )
        return BuiltinResult(value=outcome)

    return {DECLARE_FILE_BUILTIN: declare_file}
