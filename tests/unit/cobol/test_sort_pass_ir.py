"""SORT's passes over its work file are IR on the file primitives; one builtin of two
arguments orders the records."""

from __future__ import annotations

from collections.abc import Callable

from cobol_asg.sort_key_direction import SortKeyDirection
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.sort_builtins import SORT_BUILTINS
from interpreter.cobol.sort_field import SortField
from interpreter.cobol.sort_key_encoding import SortKeyEncoding
from interpreter.cobol.sort_ordering import SortOrdering
from interpreter.cobol.sort_pass_ir import SortPassIr
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators, VMState
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers

_KEY = SortField(
    offset=1,
    length=1,
    encoding=SortKeyEncoding.ALPHANUMERIC,
    direction=SortKeyDirection.DESCENDING,
)
_ORDERING = SortOrdering((_KEY,), tuple(range(256)))


def _copy(passes: SortPassIr) -> None:
    passes.copy("IN-F", "SRT")


def _order(passes: SortPassIr) -> None:
    passes.order("SRT", _ORDERING)


def _calls(emit: Callable[[SortPassIr], None]) -> list[tuple[str, int]]:
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    e = IrEmitter(ctx=ctx, span=None)
    emit(SortPassIr(e, e.text("PGM")))
    return [
        (str(i.func_name), len(i.args))
        for i in ctx.instructions
        if isinstance(i, CallFunction)
    ]


@covers(CobolFeature.SORT)
def test_sort_passes_call_only_file_primitives_and_the_ordering_builtin() -> None:
    read = [
        ("__cobol_read_record", 3),
        ("__cobol_io_outcome", 2),
        ("__cobol_io_data", 2),
    ]
    assert (_calls(_copy), _calls(_order)) == (
        [*read, ("__cobol_write_record", 4)],
        [
            ("__cobol_close_file", 2),
            ("__cobol_open_file", 3),
            *read,
            ("__list_set", 3),
            ("__list_concat", 2),
            ("__cobol_close_file", 2),
            ("__cobol_open_file", 3),
            (BuiltinName.SORT_RECORDS, 2),
            ("__list_len", 1),
            ("__list_get", 2),
            ("__cobol_write_record", 4),
            ("__cobol_close_file", 2),
        ],
    )


@covers(CobolFeature.SORT)
def test_the_ordering_builtin_orders_records_and_leaves_symbolic_ones_unordered() -> (
    None
):
    sort = SORT_BUILTINS[FuncName(BuiltinName.SORT_RECORDS)]
    ordering = typed_from_runtime(_ORDERING.data())
    records = typed_from_runtime(["1A", "2C", "3B", "4C"])
    unknown = typed_from_runtime(SymbolicValue(name="sym_records"))
    assert (
        sort([records, ordering], VMState()).value,
        sort([unknown, ordering], VMState()).value,
    ) == (["2C", "4C", "3B", "1A"], Operators.UNCOMPUTABLE)
