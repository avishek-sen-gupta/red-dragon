# pyright: standard
"""GETMAIN/FREEMAIN, TIME, STORAGE, LINK, LOAD, DELETE, OPEN, CLOSE, GET and PUT lower to IR over existing builtins only: the table's membership test, the TOD clock, the byte, list and string conversions, LINK's call of the far branch, and the file provider with the DD lookup and OPEN's file declaration, with nothing left symbolic."""

from collections.abc import Callable

import pytest

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.program_object import ENTRY_PREFIX
from interpreter.hlasm.data_set_services import (
    emit_close,
    emit_get,
    emit_open,
    emit_put,
)
from interpreter.hlasm.hlasm_constants import (
    PROGRAM_ENTRY_PREFIX,
    PROVIDER_END_OF_FILE,
    PROVIDER_OK,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.program_services import emit_delete, emit_link, emit_load
from interpreter.hlasm.storage_services import (
    TABLE_HOLDS,
    emit_getmain_freemain,
    emit_storage,
)
from interpreter.hlasm.time_service import emit_time
from interpreter.instructions import CallFunction, Symbolic
from tests.covers import NotLanguageFeature, covers

REGISTER_IMAGES = {"__binary_bytes_to_int", "__int_to_binary_bytes"}
TABLE_LOOKUP = {str(TABLE_HOLDS), *REGISTER_IMAGES}
DDNAME = {
    *REGISTER_IMAGES,
    "__bytes_to_string",
    "__string_concat_pair",
    "__string_find",
    "__string_slice",
}
RECORD_WRITE = {*DDNAME, "__list_concat", "__make_list", "__cobol_write_record"}

SERVICES: dict[str, tuple[Callable[[HlasmEmitter], None], set[str]]] = {
    "svc_10": (emit_getmain_freemain, TABLE_LOOKUP),
    "svc_11": (emit_time, {"__hlasm_tod_clock", *REGISTER_IMAGES}),
    "svc_120": (emit_storage, TABLE_LOOKUP),
    "svc_6": (
        emit_link,
        {
            *TABLE_LOOKUP,
            "__hlasm_far_branch",
            "str_upper",
            "__bytes_to_string",
            "__string_concat_pair",
            "__string_find",
            "__string_slice",
        },
    ),
    "svc_8": (emit_load, TABLE_LOOKUP),
    "svc_9": (emit_delete, TABLE_LOOKUP),
    "svc_19": (
        emit_open,
        {
            *DDNAME,
            "__hlasm_dd",
            "__list_get",
            "__hlasm_declare_file",
            "__cobol_open_file",
            "__cobol_io_outcome",
        },
    ),
    "svc_20": (emit_close, {*RECORD_WRITE, "__cobol_close_file"}),
    "svc_200": (
        emit_get,
        {
            *DDNAME,
            "__cobol_read_record",
            "__cobol_io_outcome",
            "__cobol_io_data",
            "__string_to_bytes",
            "__list_concat",
            "__list_len",
            "__list_slice",
        },
    ),
    "svc_201": (emit_put, RECORD_WRITE),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("service", list(SERVICES))
def test_a_service_calls_only_existing_builtins(service: str):
    emit, builtins = SERVICES[service]
    emitter = HlasmEmitter()
    emit(emitter)
    instructions = emitter.instructions()

    assert (
        {str(i.func_name) for i in instructions if isinstance(i, CallFunction)},
        [i for i in instructions if isinstance(i, Symbolic)],
    ) == (builtins, [])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_provider_outcomes_the_lowering_compares_are_the_access_condition_positions():
    positions = (AccessCondition.OK.position(), AccessCondition.END_OF_FILE.position())

    assert positions == (PROVIDER_OK, PROVIDER_END_OF_FILE)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_program_entry_prefix_is_cobols():
    assert PROGRAM_ENTRY_PREFIX == ENTRY_PREFIX
