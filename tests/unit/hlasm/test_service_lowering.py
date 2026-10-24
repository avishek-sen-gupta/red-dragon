# pyright: standard
"""GETMAIN/FREEMAIN, TIME and STORAGE lower to IR over existing builtins only: the table's membership test, the TOD clock and the byte conversions, with nothing left symbolic."""

from collections.abc import Callable

import pytest

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
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
