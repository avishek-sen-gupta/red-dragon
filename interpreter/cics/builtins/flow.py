"""CICS flow control builtins — RETURN TRANSID, XCTL context setters."""

from __future__ import annotations

import logging

from interpreter.cics.types import DispatchKind, DispatchResult
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import BuiltinResult, VMState

logger = logging.getLogger(__name__)


def make_set_return_context_builtin(result_holder: list) -> object:
    """Return __cics_set_return_context builtin.

    With no args → plain RETURN. With args[0]=transid, args[1]=commarea → RETURN_TRANSID.
    """

    def __cics_set_return_context(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        if not args:
            result_holder[0] = DispatchResult(kind=DispatchKind.RETURN)
        else:
            transid = str(args[0].value).strip()
            commarea = bytes(args[1].value) if len(args) > 1 else b""
            result_holder[0] = DispatchResult(
                kind=DispatchKind.RETURN_TRANSID,
                transid=transid,
                commarea=commarea,
            )
        return BuiltinResult(value=None)

    return __cics_set_return_context


def make_set_xctl_context_builtin(result_holder: list) -> object:
    """Return __cics_set_xctl_context builtin.

    args[0]=program name, args[1]=commarea bytes.
    """

    def __cics_set_xctl_context(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        program = str(args[0].value).strip() if args else ""
        commarea = bytes(args[1].value) if len(args) > 1 else b""
        result_holder[0] = DispatchResult(
            kind=DispatchKind.XCTL,
            program=program,
            commarea=commarea,
        )
        return BuiltinResult(value=None)

    return __cics_set_xctl_context
