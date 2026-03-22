"""Control flow opcode handlers: BRANCH, BRANCH_IF, RETURN, THROW, TRY_PUSH, TRY_POP,
SET_CONTINUATION, RESUME_CONTINUATION."""

from __future__ import annotations

from typing import Any

from interpreter.ir import IRInstruction
from interpreter.vm import (
    VMState,
    ExceptionHandler,
    ExecutionResult,
    StateUpdate,
    _resolve_reg,
    _is_symbolic,
)
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import typed
from interpreter import constants
from interpreter.handlers._common import _symbolic_name


def _handle_branch(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    return ExecutionResult.success(
        StateUpdate(
            next_label=inst.label,
            reasoning=f"branch → {inst.label}",
        )
    )


def _handle_branch_if(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    cond_val = _resolve_reg(vm, inst.operands[0]).value
    targets = inst.label.split(",")
    true_label = targets[0].strip()
    false_label = targets[1].strip() if len(targets) > 1 else None

    if _is_symbolic(cond_val):
        # Symbolic condition — deterministically take the true branch
        # and record the assumption as a path condition
        sym_desc = _symbolic_name(cond_val)
        return ExecutionResult.success(
            StateUpdate(
                next_label=true_label,
                path_condition=f"assuming {sym_desc} is True",
                reasoning=f"branch_if {sym_desc} (symbolic) → {true_label} (assumed true)",
            )
        )

    taken = bool(cond_val)
    chosen = true_label if taken else false_label
    return ExecutionResult.success(
        StateUpdate(
            next_label=chosen,
            path_condition=f"{inst.operands[0]} is {taken}",
            reasoning=f"branch_if {cond_val!r} → {chosen}",
        )
    )


def _handle_return(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    if vm.current_frame.is_ctor:
        tv = typed(None, scalar(constants.TypeName.VOID))
    elif inst.operands:
        tv = _resolve_reg(vm, inst.operands[0])
    else:
        tv = typed(None, scalar(constants.TypeName.VOID))
    return ExecutionResult.success(
        StateUpdate(
            return_value=tv,
            call_pop=True,
            reasoning=f"return {tv.value!r}",
        )
    )


def _handle_throw(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    val = _resolve_reg(vm, inst.operands[0]).value if inst.operands else None
    if vm.exception_stack:
        handler = vm.exception_stack.pop()
        # Redirect to the first catch label (or finally if no catch)
        target = (
            handler.catch_labels[0]
            if handler.catch_labels
            else handler.finally_label or handler.end_label
        )
        return ExecutionResult.success(
            StateUpdate(
                next_label=target, reasoning=f"throw {val!r} → caught by {target}"
            )
        )
    return ExecutionResult.success(StateUpdate(reasoning=f"throw {val!r} (uncaught)"))


def _handle_try_push(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    catch_labels_str, finally_label, end_label = (
        inst.operands[0],
        inst.operands[1],
        inst.operands[2],
    )
    catch_labels = [lbl.strip() for lbl in catch_labels_str.split(",") if lbl.strip()]
    vm.exception_stack.append(
        ExceptionHandler(
            catch_labels=catch_labels,
            finally_label=finally_label,
            end_label=end_label,
        )
    )
    return ExecutionResult.success(
        StateUpdate(reasoning=f"push exception handler → catch={catch_labels}")
    )


def _handle_try_pop(inst: IRInstruction, vm: VMState, ctx: Any) -> ExecutionResult:
    vm.exception_stack.pop()
    return ExecutionResult.success(StateUpdate(reasoning="pop exception handler"))


def _handle_set_continuation(
    inst: IRInstruction, vm: VMState, ctx: Any
) -> ExecutionResult:
    """SET_CONTINUATION: operands = [name, label]. Write name → label into continuation table."""
    name = inst.operands[0]
    label = inst.operands[1]
    return ExecutionResult.success(
        StateUpdate(
            continuation_writes={name: label},
            reasoning=f"set_continuation {name} → {label}",
        )
    )


def _handle_resume_continuation(
    inst: IRInstruction, vm: VMState, ctx: Any
) -> ExecutionResult:
    """RESUME_CONTINUATION: operands = [name]. Branch to label if set, else fall through."""
    name = inst.operands[0]
    target = vm.continuations.get(name)
    if target:
        return ExecutionResult.success(
            StateUpdate(
                next_label=target,
                continuation_clear=name,
                reasoning=f"resume_continuation {name} → {target}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            continuation_clear=name,
            reasoning=f"resume_continuation {name} (not set, fall through)",
        )
    )
