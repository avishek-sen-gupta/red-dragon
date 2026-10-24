# pyright: standard
"""The run's DD definitions as both halves of the run input: the `__hlasm_dd` builtin, and the file provider's path overrides that send each DDNAME to its data set."""

from collections.abc import Mapping
from types import MappingProxyType

from interpreter.cobol.run_inputs import RunInputs
from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.dd_builtins import dd_builtins
from interpreter.hlasm_run_inputs.dd_definition import DdDefinition
from interpreter.vm.builtin import Builtin


def dd_run_inputs(
    dds: Mapping[str, DdDefinition],
) -> tuple[Mapping[FuncName, Builtin], RunInputs]:
    paths = MappingProxyType({name: dd.path for name, dd in dds.items()})
    return dd_builtins(dds), RunInputs(path_overrides=paths)
