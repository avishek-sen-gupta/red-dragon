"""The one SORT builtin: it puts a work file's records in key order. Ordering stays a
builtin because an IR comparison sort would decode both keys on every comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.sort_order import ordered
from interpreter.cobol.sort_ordering import ordering_of
from interpreter.data_value import DataRecord
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.builtin import Builtin
from interpreter.vm.vm import Operators, VMState
from interpreter.vm.vm_types import BuiltinResult


def _sorted_records(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
    match [a.value for a in args]:
        case [list() as records, DataRecord() as ordering] if all(
            isinstance(r, str) for r in records
        ):
            order = ordering_of(ordering)
            return BuiltinResult(
                value=[
                    record.decode("latin-1")
                    for record in ordered(
                        [r.encode("latin-1") for r in records],
                        order.fields,
                        order.weights,
                    )
                ]
            )
        case _:
            return BuiltinResult(value=Operators.UNCOMPUTABLE)


SORT_BUILTINS: Mapping[FuncName, Builtin] = MappingProxyType(
    {FuncName(BuiltinName.SORT_RECORDS): _sorted_records}
)
