"""No file primitive a COBOL program calls, and no driver open, takes more than four
parameters."""

from __future__ import annotations

import inspect
from collections.abc import Callable

from infrastructure.zos.access_methods.alternate_index_driver import (
    AlternateIndexDriver,
    open_alternate_index_driver,
)
from infrastructure.zos.access_methods.file_drivers import (
    FileOrganizationDriver,
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
    open_driver,
)
from infrastructure.zos.access_methods.variable_sequential_driver import (
    VariableSequentialDriver,
)
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
    "__cobol_io_outcome",
    "__cobol_io_data",
    "__cobol_io_record_number",
    "__cobol_switch_status",
    "__cobol_set_switch",
)


def _arity(name: str) -> int:
    method_name = NullIOProvider().dispatch(FuncName(name))
    method = getattr(CobolIOProvider, str(method_name))
    return len(inspect.signature(method).parameters) - 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_no_provider_primitive_takes_more_than_four_parameters() -> None:
    assert {name: _arity(name) for name in _PRIMITIVES if _arity(name) > 4} == {}


def _parameters(
    function: Callable[..., None] | Callable[..., FileOrganizationDriver],
) -> int:
    names = inspect.signature(function).parameters
    return len([n for n in names if n != "self"])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_no_driver_open_takes_more_than_four_parameters() -> None:
    opens = {
        "FileOrganizationDriver.open": FileOrganizationDriver.open,
        "SequentialDriver.open": SequentialDriver.open,
        "IndexedDriver.open": IndexedDriver.open,
        "RelativeDriver.open": RelativeDriver.open,
        "VariableSequentialDriver.open": VariableSequentialDriver.open,
        "AlternateIndexDriver.open": AlternateIndexDriver.open,
        "open_driver": open_driver,
        "open_alternate_index_driver": open_alternate_index_driver,
    }
    assert {
        name: _parameters(f) for name, f in opens.items() if _parameters(f) > 4
    } == {}
