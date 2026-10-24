# pyright: standard
"""The run's DD definitions as a builtin: per DDNAME whether it is supplied, then its RECFM byte, LRECL and BLKSIZE (0 where not given); irreducible, since it reads outside the program."""

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.dd_definition import DdDefinition
from interpreter.hlasm_run_inputs.run_input_names import DD_BUILTIN
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult

NO_DDS: Mapping[str, DdDefinition] = MappingProxyType({})
UNSUPPLIED = (0, 0, 0, 0)


def dd_builtins(dds: Mapping[str, DdDefinition]) -> Mapping[FuncName, Builtin]:
    def dd(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
        name = str(args[0].value)
        facts = dds[name].facts() if name in dds else UNSUPPLIED
        return BuiltinResult(value=list(facts))

    return {DD_BUILTIN: dd}
