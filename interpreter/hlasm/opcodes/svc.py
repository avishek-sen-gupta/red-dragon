# pyright: standard
"""SVC: the supervisor calls lowered in IR (WTO, ABEND, GETMAIN/FREEMAIN, TIME, STORAGE, LINK, LOAD, DELETE, OPEN, CLOSE, GET, PUT), by number, the number written or set by EX; any other number abends S0C1."""

import logging
from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.abend_completion import emit_abend_completion
from interpreter.hlasm.byte_one_layouts import NUMBER_BYTE
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_set_services import (
    emit_close,
    emit_get,
    emit_open,
    emit_put,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_constants import (
    ABEND_SVC,
    CLOSE_SVC,
    DELETE_SVC,
    GET_SVC,
    GETMAIN_FREEMAIN_SVC,
    LINK_SVC,
    LOAD_SVC,
    OPEN_SVC,
    OPERATION_EXCEPTION_ABEND,
    PUT_SVC,
    STORAGE_SVC,
    TIME_SVC,
    WTO_SVC,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.program_services import emit_delete, emit_link, emit_load
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.storage_services import emit_getmain_freemain, emit_storage
from interpreter.hlasm.time_service import emit_time
from interpreter.hlasm.write_to_operator import emit_write_to_operator

logger = logging.getLogger(__name__)

_SERVICES: Mapping[int, Callable[[HlasmEmitter], None]] = {
    WTO_SVC: emit_write_to_operator,
    ABEND_SVC: emit_abend_completion,
    GETMAIN_FREEMAIN_SVC: emit_getmain_freemain,
    TIME_SVC: emit_time,
    STORAGE_SVC: emit_storage,
    LINK_SVC: emit_link,
    LOAD_SVC: emit_load,
    DELETE_SVC: emit_delete,
    OPEN_SVC: emit_open,
    CLOSE_SVC: emit_close,
    GET_SVC: emit_get,
    PUT_SVC: emit_put,
}


def _no_service(emitter: HlasmEmitter, number: str) -> None:
    logger.warning(
        "SVC %s has no lowering; it abends %s", number, OPERATION_EXCEPTION_ABEND
    )
    emit_abend(emitter, OPERATION_EXCEPTION_ABEND)


def lower_svc(
    emitter: HlasmEmitter, statement: MachineStatement, number: DataField
) -> None:
    number.select(emitter, _SERVICES, _no_service)


SVC_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "SVC": FieldLowering(NUMBER_BYTE, lower_svc)
}
SVC_LOWERINGS: Mapping[str, StatementLowering] = written_lowerings(SVC_FIELD_LOWERINGS)
