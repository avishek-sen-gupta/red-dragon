"""Arithmetic opcode handlers: BINOP, UNOP."""

from __future__ import annotations

from typing import Any

from interpreter.instructions import InstructionBase, Binop, Unop
from interpreter.vm.vm import (
    VMState,
    Pointer,
    ExecutionResult,
    StateUpdate,
    Operators,
    _resolve_reg,
    _heap_addr,
    _is_symbolic,
)
from interpreter.refs.func_ref import BoundFuncRef
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.typed_value import typed, typed_from_runtime
from interpreter import constants
from interpreter.handlers._common import _symbolic_name


def _handle_binop(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Binop)
    binop_coercion = ctx.binop_coercion
    oper = t.operator
    lhs_typed = _resolve_reg(vm, inst.operands[1])
    rhs_typed = _resolve_reg(vm, inst.operands[2])

    # Unwrap for special-case checks
    lhs = lhs_typed.value
    rhs = rhs_typed.value

    # Pointer arithmetic: Pointer +/- int or int + Pointer
    lhs_ptr = lhs if isinstance(lhs, Pointer) else None
    rhs_ptr = rhs if isinstance(rhs, Pointer) else None
    if lhs_ptr and rhs_ptr:
        if oper == "-" and lhs_ptr.base == rhs_ptr.base:
            diff = lhs_ptr.offset - rhs_ptr.offset
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={
                        t.result_reg: typed(diff, scalar(constants.TypeName.INT))
                    },
                    reasoning=f"pointer diff {lhs!r} - {rhs!r} = {diff}",
                )
            )
        if oper in ("<", ">", "<=", ">=", "==", "!=") and lhs_ptr.base == rhs_ptr.base:
            result = Operators.eval_binop(oper, lhs_ptr.offset, rhs_ptr.offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={
                        t.result_reg: typed(result, scalar(constants.TypeName.BOOL))
                    },
                    reasoning=f"pointer cmp {lhs!r} {oper} {rhs!r} = {result!r}",
                )
            )
    if oper in ("+", "-") and (lhs_ptr or rhs_ptr):
        ptr = lhs_ptr or rhs_ptr
        offset_val = rhs if lhs_ptr else lhs
        if isinstance(offset_val, (int, float)):
            new_offset = (
                ptr.offset + int(offset_val)
                if oper == "+" or not lhs_ptr
                else ptr.offset - int(offset_val)
            )
            result_ptr = Pointer(base=ptr.base, offset=new_offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={
                        t.result_reg: typed(
                            result_ptr, scalar(constants.TypeName.POINTER)
                        )
                    },
                    reasoning=f"pointer arith {lhs!r} {oper} {rhs!r} = {result_ptr!r}",
                )
            )

    # Symbolic short-circuit — before coercion
    if _is_symbolic(lhs) or _is_symbolic(rhs):
        lhs_desc = _symbolic_name(lhs)
        rhs_desc = _symbolic_name(rhs)
        sym = vm.fresh_symbolic(hint=f"{lhs_desc} {oper} {rhs_desc}")
        sym.constraints = [f"{lhs_desc} {oper} {rhs_desc}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"binop {lhs_desc} {oper} {rhs_desc} → symbolic {sym.name}",
            )
        )

    # Coerce and compute
    lhs_coerced, rhs_coerced = binop_coercion.coerce(oper, lhs_typed, rhs_typed)
    lhs_raw, rhs_raw = lhs_coerced.value, rhs_coerced.value
    result = Operators.eval_binop(oper, lhs_raw, rhs_raw)

    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{lhs_raw!r} {oper} {rhs_raw!r}")
        sym.constraints = [f"{lhs_raw!r} {oper} {rhs_raw!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} → uncomputable, symbolic {sym.name}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={
                t.result_reg: typed(
                    result, binop_coercion.result_type(oper, lhs_typed, rhs_typed)
                )
            },
            reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} = {result!r}",
        )
    )


def _handle_unop(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Unop)
    unop_coercion = ctx.unop_coercion
    oper = t.operator
    operand_typed = _resolve_reg(vm, inst.operands[1])
    operand = operand_typed.value
    # Address-of (&) on a value that is already a reference (function ref or
    # heap object) returns the reference unchanged — our model already uses
    # references rather than inline values for these.
    if oper == "&":
        addr = _heap_addr(operand)
        if isinstance(operand, BoundFuncRef) or (addr and vm.heap_contains(addr)):
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={t.result_reg: typed_from_runtime(operand)},
                    reasoning=f"unop &{operand} → {operand} (address-of reference is identity)",
                )
            )
    # Symbolic short-circuit — before coercion
    if _is_symbolic(operand):
        op_desc = _symbolic_name(operand)
        sym = vm.fresh_symbolic(hint=f"{oper}{op_desc}")
        sym.constraints = [f"{oper}{op_desc}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"unop {oper}{op_desc} → symbolic {sym.name}",
            )
        )

    # Coerce and compute
    coerced = unop_coercion.coerce(oper, operand_typed)
    raw = coerced.value
    result = Operators.eval_unop(oper, raw)
    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{oper}{raw!r}")
        sym.constraints = [f"{oper}{raw!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={t.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"unop {oper}{raw!r} → uncomputable, symbolic {sym.name}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={
                t.result_reg: typed(
                    result, unop_coercion.result_type(oper, operand_typed)
                )
            },
            reasoning=f"unop {oper}{raw!r} = {result!r}",
        )
    )
