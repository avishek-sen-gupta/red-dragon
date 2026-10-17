"""No file primitive a COBOL program calls takes more than four parameters."""

from __future__ import annotations

import inspect

from interpreter.cobol.io_provider import CobolIOProvider, NullIOProvider
from interpreter.func_name import FuncName
from tests.covers import NotLanguageFeature, covers

_PRIMITIVES = (
    "__cobol_accept",
    "__cobol_declare_file",
    "__cobol_open_file",
    "__cobol_close_file",
    "__cobol_read_record",
    "__cobol_write_record",
    "__cobol_rewrite_record",
    "__cobol_start_file",
    "__cobol_delete_record",
    "__cobol_io_status",
    "__cobol_io_data",
    "__cobol_io_record_number",
    "__cobol_switch_status",
    "__cobol_set_switch",
    "__cobol_sort_using",
    "__cobol_sort_giving",
    "__cobol_sort_file",
)


def _arity(name: str) -> int:
    method_name = NullIOProvider().dispatch(FuncName(name))
    method = getattr(CobolIOProvider, str(method_name))
    return len(inspect.signature(method).parameters) - 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_no_provider_primitive_takes_more_than_four_parameters() -> None:
    assert {name: _arity(name) for name in _PRIMITIVES if _arity(name) > 4} == {}
