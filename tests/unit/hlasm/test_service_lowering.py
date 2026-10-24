# pyright: standard
"""GETMAIN/FREEMAIN, TIME, STORAGE, LINK, LOAD and DELETE lower to IR over existing builtins only: the table's membership test, the TOD clock, the byte and string conversions, and LINK's call of the far branch, with nothing left symbolic."""

from collections.abc import Callable

import pytest

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

SERVICES: dict[str, tuple[Callable[[HlasmEmitter], None], set[str]]] = {
    "svc_10": (emit_getmain_freemain, TABLE_LOOKUP),
    "svc_11": (emit_time, {"__hlasm_tod_clock", *REGISTER_IMAGES}),
    "svc_120": (emit_storage, TABLE_LOOKUP),
    "svc_6": (
        emit_link,
        {
            *TABLE_LOOKUP,
            "__hlasm_far_branch",
            "__bytes_to_string",
            "__string_concat_pair",
            "__string_find",
            "__string_slice",
        },
    ),
    "svc_8": (emit_load, TABLE_LOOKUP),
    "svc_9": (emit_delete, {"__int_to_binary_bytes"}),
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
