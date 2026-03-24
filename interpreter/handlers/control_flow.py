"""Control flow opcode handlers: BRANCH, BRANCH_IF, RETURN, THROW, TRY_PUSH, TRY_POP,
SET_CONTINUATION, RESUME_CONTINUATION."""

from __future__ import annotations

from typing import Any

from interpreter.instructions import (
    InstructionBase,
    Branch,
    BranchIf,
    Return_,
    Throw_,
    TryPush,
    TryPop,
    SetContinuation,
    ResumeContinuation,
)
from interpreter.ir import CodeLabel
from interpreter.vm.vm import (
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


def _handle_branch(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Branch)
    return ExecutionResult.success(
        StateUpdate(
            next_label=t.label,
            reasoning=f"branch → {t.label}",
        )
    )


def _handle_branch_if(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, BranchIf)
    cond_val = _resolve_reg(vm, t.cond_reg).value
    true_label = t.branch_targets[0]
    false_label = t.branch_targets[1] if len(t.branch_targets) > 1 else None

    if _is_symbolic(cond_val):
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
            path_condition=f"{t.cond_reg} is {taken}",
            reasoning=f"branch_if {cond_val!r} → {chosen}",
        )
    )


def _handle_return(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Return_)
    if vm.current_frame.is_ctor:
        tv = typed(None, scalar(constants.TypeName.VOID))
    elif t.value_reg is not None:
        tv = _resolve_reg(vm, t.value_reg)
    else:
        tv = typed(None, scalar(constants.TypeName.VOID))
    return ExecutionResult.success(
        StateUpdate(
            return_value=tv,
            call_pop=True,
            reasoning=f"return {tv.value!r}",
        )
    )


def _handle_throw(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, Throw_)
    val = _resolve_reg(vm, t.value_reg).value if t.value_reg is not None else None
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


def _handle_try_push(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, TryPush)
    catch_labels: tuple[CodeLabel, ...] = t.catch_labels
    finally_label: CodeLabel = t.finally_label
    end_label: CodeLabel = t.end_label
    vm.exception_stack.append(
        ExceptionHandler(
            catch_labels=list(catch_labels),
            finally_label=finally_label if finally_label.is_present() else None,
            end_label=end_label if end_label.is_present() else None,
        )
    )
    return ExecutionResult.success(
        StateUpdate(reasoning=f"push exception handler → catch={catch_labels}")
    )


def _handle_try_pop(inst: InstructionBase, vm: VMState, ctx: Any) -> ExecutionResult:
    t = inst
    assert isinstance(t, TryPop)
    vm.exception_stack.pop()
    return ExecutionResult.success(StateUpdate(reasoning="pop exception handler"))


def _handle_set_continuation(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    """SET_CONTINUATION: operands = [name, label]. Write name → label into continuation table."""
    t = inst
    assert isinstance(t, SetContinuation)
    name = t.name
    label = t.target_label
    return ExecutionResult.success(
        StateUpdate(
            continuation_writes={name: label},
            reasoning=f"set_continuation {name} → {label}",
        )
    )


def _handle_resume_continuation(
    inst: InstructionBase, vm: VMState, ctx: Any
) -> ExecutionResult:
    """RESUME_CONTINUATION: operands = [name]. Branch to label if set, else fall through."""
    t = inst
    assert isinstance(t, ResumeContinuation)
    name = t.name
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
