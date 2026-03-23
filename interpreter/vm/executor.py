"""Local execution — opcode handlers and dispatch table."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from interpreter.ir import IRInstruction, Opcode, SpreadArguments, CodeLabel, NoCodeLabel, NO_LABEL
from interpreter.cfg import CFG
from interpreter.vm.vm import (
    VMState,
    SymbolicValue,
    HeapObject,
    ClosureEnvironment,
    ExceptionHandler,
    Pointer,
    StackFramePush,
    StateUpdate,
    HeapWrite,
    NewObject,
    RegionWrite,
    ExecutionResult,
    Operators,
    _resolve_reg,
    _is_symbolic,
    _heap_addr,
    _parse_const,
)
from interpreter.vm.vm_types import BuiltinResult, HeapWrite, StackFrame
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.vm.builtins import Builtins, _builtin_array_of
from interpreter.overload.overload_resolver import (
    NullOverloadResolver,
    OverloadResolver,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, TypeExpr, parse_type, pointer, scalar
from interpreter.vm.unresolved_call import UnresolvedCallResolver, SymbolicResolver
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.types.coercion.binop_coercion import (
    BinopCoercionStrategy,
    DefaultBinopCoercion,
)
from interpreter.types.coercion.unop_coercion import (
    UnopCoercionStrategy,
    DefaultUnopCoercion,
)
from interpreter.vm.field_fallback import (
    FieldFallbackStrategy,
    NoFieldFallback,
)
from interpreter.frontends.symbol_table import SymbolTable
from interpreter import constants

_DEFAULT_RESOLVER = SymbolicResolver()
_DEFAULT_OVERLOAD_RESOLVER = NullOverloadResolver()
_DEFAULT_BINOP_COERCION = DefaultBinopCoercion()
_DEFAULT_UNOP_COERCION = DefaultUnopCoercion()
_NO_FIELD_FALLBACK = NoFieldFallback()
_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandlerContext:
    """Typed execution context passed to all instruction handlers."""

    cfg: CFG
    registry: FunctionRegistry
    current_label: CodeLabel
    ip: int
    call_resolver: UnresolvedCallResolver
    overload_resolver: OverloadResolver
    type_env: TypeEnvironment
    binop_coercion: BinopCoercionStrategy
    unop_coercion: UnopCoercionStrategy
    func_symbol_table: dict[str, FuncRef]
    class_symbol_table: dict[str, ClassRef]
    field_fallback: FieldFallbackStrategy
    symbol_table: SymbolTable


def _default_handler_context() -> HandlerContext:
    """Create a HandlerContext with default values for all fields."""
    return HandlerContext(
        cfg=CFG(),
        registry=FunctionRegistry(),
        current_label=NO_LABEL,
        ip=0,
        call_resolver=_DEFAULT_RESOLVER,
        overload_resolver=_DEFAULT_OVERLOAD_RESOLVER,
        type_env=_EMPTY_TYPE_ENV,
        binop_coercion=_DEFAULT_BINOP_COERCION,
        unop_coercion=_DEFAULT_UNOP_COERCION,
        func_symbol_table={},
        class_symbol_table={},
        field_fallback=_NO_FIELD_FALLBACK,
        symbol_table=SymbolTable.empty(),
    )


# ── Handler imports ──────────────────────────────────────────────

from interpreter.handlers._common import (  # noqa: E402
    _resolve_call_args,
    _symbolic_name,
    _symbolic_type_hint,
    _write_var_to_frame,
)
from interpreter.handlers.variables import (  # noqa: E402
    _handle_const,
    _handle_load_var,
    _handle_decl_var,
    _handle_store_var,
    _handle_symbolic,
)
from interpreter.handlers.memory import (  # noqa: E402
    _handle_load_field,
    _handle_store_field,
    _handle_load_index,
    _handle_store_index,
    _handle_load_indirect,
    _handle_store_indirect,
    _handle_address_of,
    _handle_load_field_indirect,
    _find_method_missing,
    _resolve_method_delegation_target,
)
from interpreter.handlers.control_flow import (  # noqa: E402
    _handle_branch,
    _handle_branch_if,
    _handle_return,
    _handle_throw,
    _handle_try_push,
    _handle_try_pop,
    _handle_set_continuation,
    _handle_resume_continuation,
)
from interpreter.handlers.calls import (  # noqa: E402
    _handle_call_function,
    _handle_call_method,
    _handle_call_unknown,
    _try_builtin_call,
    _try_class_constructor_call,
    _try_user_function_call,
    _unwrap_builtin_result,
)
from interpreter.handlers.arithmetic import (  # noqa: E402
    _handle_binop,
    _handle_unop,
)
from interpreter.handlers.objects import (  # noqa: E402
    _handle_new_object,
    _handle_new_array,
)
from interpreter.handlers.regions import (  # noqa: E402
    _handle_alloc_region,
    _handle_write_region,
    _handle_load_region,
)

# ── Dispatch table and entry point ──────────────────────────────


class LocalExecutor:
    """Dispatches IR instructions to handler functions for local execution."""

    DISPATCH: dict[Opcode, Any] = {
        Opcode.CONST: _handle_const,
        Opcode.LOAD_VAR: _handle_load_var,
        Opcode.DECL_VAR: _handle_decl_var,
        Opcode.STORE_VAR: _handle_store_var,
        Opcode.BRANCH: _handle_branch,
        Opcode.SYMBOLIC: _handle_symbolic,
        Opcode.NEW_OBJECT: _handle_new_object,
        Opcode.NEW_ARRAY: _handle_new_array,
        Opcode.STORE_FIELD: _handle_store_field,
        Opcode.LOAD_FIELD: _handle_load_field,
        Opcode.STORE_INDEX: _handle_store_index,
        Opcode.LOAD_INDEX: _handle_load_index,
        Opcode.RETURN: _handle_return,
        Opcode.THROW: _handle_throw,
        Opcode.TRY_PUSH: _handle_try_push,
        Opcode.TRY_POP: _handle_try_pop,
        Opcode.BRANCH_IF: _handle_branch_if,
        Opcode.BINOP: _handle_binop,
        Opcode.UNOP: _handle_unop,
        Opcode.CALL_FUNCTION: _handle_call_function,
        Opcode.CALL_METHOD: _handle_call_method,
        Opcode.CALL_UNKNOWN: _handle_call_unknown,
        Opcode.SET_CONTINUATION: _handle_set_continuation,
        Opcode.RESUME_CONTINUATION: _handle_resume_continuation,
        Opcode.ALLOC_REGION: _handle_alloc_region,
        Opcode.WRITE_REGION: _handle_write_region,
        Opcode.LOAD_REGION: _handle_load_region,
        Opcode.ADDRESS_OF: _handle_address_of,
        Opcode.LOAD_INDIRECT: _handle_load_indirect,
        Opcode.LOAD_FIELD_INDIRECT: _handle_load_field_indirect,
        Opcode.STORE_INDIRECT: _handle_store_indirect,
    }

    @classmethod
    def execute(
        cls,
        inst: IRInstruction,
        vm: VMState,
        ctx: HandlerContext,
    ) -> ExecutionResult:
        handler = cls.DISPATCH.get(inst.opcode)
        if not handler:
            return ExecutionResult.not_handled()
        return handler(inst=inst, vm=vm, ctx=ctx)


def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    ctx: HandlerContext,
) -> ExecutionResult:
    """Try to execute an instruction without the LLM.

    Returns an ExecutionResult indicating whether the instruction was
    handled locally, and the StateUpdate if so.
    """
    return LocalExecutor.execute(inst, vm, ctx)
