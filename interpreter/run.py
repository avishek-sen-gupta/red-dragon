"""Orchestrator — run() entry point."""

from __future__ import annotations

import copy
import functools
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, TypeIs

from interpreter import constants
from interpreter.cfg import CFG, build_cfg
from interpreter.cfg_types import BasicBlock
from interpreter.constants import FoundationTypeName, Language, LLMProvider
from interpreter.default_builtins import DEFAULT_BUILTINS
from interpreter.frontend import Frontend, get_frontend, make_cobol_parser
from interpreter.frontend_observer import FrontendObserver
from interpreter.frontends import get_hlasm_parser
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.run_input_builtins import (
    unsupplied_run_input_builtins,
)
from interpreter.instructions import (
    Data,
    Halt_,
    InstructionBase,
    Label_,
    Return_,
    Suspend,
    Throw_,
)
from interpreter.ir import NO_LABEL, CodeLabel
from interpreter.llm.backend import LLMBackend, get_backend
from interpreter.overload.ambiguity_handler import FallbackFirstWithWarning
from interpreter.overload.overload_resolver import (
    NullOverloadResolver,
    OverloadResolver,
)
from interpreter.overload.resolution_strategy import ArityThenTypeStrategy
from interpreter.project.cobol_compile import PROJECT_ROOT, compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.project.hlasm_compile import compile_hlasm
from interpreter.project.linker import module_prefix
from interpreter.project.program_entry import ProgramEntry
from interpreter.project.program_not_in_image import ProgramNotInImage
from interpreter.project.types import LinkedProgram
from interpreter.record_io.io_provider import NO_IO_PROVIDER, RecordIOProvider
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.register import NO_REGISTER, Register
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run_types import (
    ExecutionStats,
    PipelineStats,
    UnresolvedCallStrategy,
    VMConfig,
)
from interpreter.trace_types import ExecutionTrace, TraceStep
from interpreter.type_name import TypeName
from interpreter.types.coercion.binop_coercion import (
    BinopCoercionStrategy,
    DefaultBinopCoercion,
    JavaBinopCoercion,
)
from interpreter.types.coercion.conversion_rules import TypeConversionRules
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.types.coercion.type_compatibility import DefaultTypeCompatibility
from interpreter.types.coercion.unop_coercion import (
    DefaultUnopCoercion,
    UnopCoercionStrategy,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.types.type_graph import DEFAULT_TYPE_NODES, TypeGraph
from interpreter.types.type_inference import infer_types
from interpreter.types.type_node import TypeNode
from interpreter.types.type_resolver import TypeResolver
from interpreter.types.typed_value import TypedValue, typed, unwrap
from interpreter.var_name import VarName
from interpreter.vm.builtin import Builtin
from interpreter.vm.executor import HandlerContext, _try_execute_locally
from interpreter.vm.field_fallback import (
    FieldFallbackStrategy,
    ImplicitThisFieldFallback,
    NoFieldFallback,
)
from interpreter.vm.function_scoping import (
    FunctionScopingStrategy,
    GlobalLeakFunctionScopingStrategy,
    LocalFunctionScopingStrategy,
)
from interpreter.vm.null_access import NullAccess
from interpreter.vm.unknown_branch_target_error import UnknownBranchTargetError
from interpreter.vm.unresolved_call import (
    LLMPlausibleResolver,
    SymbolicResolver,
    UnresolvedCallResolver,
)
from interpreter.vm.vm import (
    StackFrame,
    StateUpdate,
    SymbolicValue,
    VMState,
    apply_update,
    coerce_local_update,
    materialize_raw_update,
)
from interpreter.vm.warn_and_ignore import WARN_AND_IGNORE

logger = logging.getLogger(__name__)

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)
_IDENTITY_RULES = IdentityConversionRules()
_DEFAULT_OVERLOAD_RESOLVER = NullOverloadResolver()


@dataclass(frozen=True)
class ExecutionStrategies:
    """Language-specific execution strategies bundled for execute_cfg."""

    type_env: TypeEnvironment = dataclass_field(default_factory=lambda: _EMPTY_TYPE_ENV)
    conversion_rules: TypeConversionRules = dataclass_field(
        default_factory=IdentityConversionRules
    )
    overload_resolver: OverloadResolver = dataclass_field(
        default_factory=NullOverloadResolver
    )
    binop_coercion: BinopCoercionStrategy = dataclass_field(
        default_factory=DefaultBinopCoercion
    )
    unop_coercion: UnopCoercionStrategy = dataclass_field(
        default_factory=DefaultUnopCoercion
    )
    func_symbol_table: dict[CodeLabel, FuncRef] = dataclass_field(default_factory=dict)
    class_symbol_table: dict[CodeLabel, ClassRef] = dataclass_field(
        default_factory=dict
    )
    field_fallback: FieldFallbackStrategy = dataclass_field(
        default_factory=NoFieldFallback
    )
    function_scoping: FunctionScopingStrategy = dataclass_field(
        default_factory=LocalFunctionScopingStrategy
    )
    symbol_table: SymbolTable = dataclass_field(default_factory=SymbolTable.empty)


_DEFAULT_VM_CONFIG = VMConfig()
_DEFAULT_STRATEGIES = ExecutionStrategies()
_TOP_LEVEL = EntryPoint.top_level()


def _create_resolver(config: VMConfig) -> UnresolvedCallResolver:
    """Create the appropriate call resolver based on config."""
    if config.unresolved_call_strategy == UnresolvedCallStrategy.LLM:
        from interpreter.llm.llm_client import get_llm_client

        llm_client = get_llm_client(provider=config.backend)
        return LLMPlausibleResolver(
            llm_client=llm_client,
            source_language=config.source_language,
        )
    return SymbolicResolver()


class _StopExecution:
    """Sentinel indicating the interpreter should halt."""

    pass


_Flow = tuple[CodeLabel, int] | _StopExecution


def _field_fallback_for_language(lang: Language) -> FieldFallbackStrategy:
    """Select FieldFallbackStrategy based on source language.

    Languages with implicit this (bare field names in method/constructor
    bodies resolve to this.field): Java, C#, Kotlin, Scala, C++.
    """
    _IMPLICIT_THIS_LANGS = frozenset(
        {Language.JAVA, Language.CSHARP, Language.KOTLIN, Language.SCALA, Language.CPP}
    )
    if lang in _IMPLICIT_THIS_LANGS:
        return ImplicitThisFieldFallback()
    return NoFieldFallback()


_IMAGE_LANGUAGES: frozenset[Language] = frozenset({Language.COBOL, Language.HLASM})

_ImageLanguage = Literal[Language.COBOL, Language.HLASM]


def _is_image_language(lang: Language) -> TypeIs[_ImageLanguage]:
    return lang in _IMAGE_LANGUAGES


_LEAKY_SCOPING_LANGS: frozenset[Language] = frozenset(
    {Language.RUBY, Language.PHP, Language.LUA}
)


def _function_scoping_for_language(lang: Language) -> FunctionScopingStrategy:
    """Select FunctionScopingStrategy based on source language.

    Ruby, PHP, and Lua leak inner function definitions to global scope.
    All other languages use lexical (local) scoping for inner functions.
    """
    if lang in _LEAKY_SCOPING_LANGS:
        return GlobalLeakFunctionScopingStrategy()
    return LocalFunctionScopingStrategy()


def _binop_coercion_for_language(lang: Language) -> BinopCoercionStrategy:
    """Select BinopCoercionStrategy based on source language."""
    _JAVA_LIKE = frozenset({Language.JAVA})
    if lang in _JAVA_LIKE:
        return JavaBinopCoercion()
    return DefaultBinopCoercion()


def _find_entry_point(cfg: CFG, entry_point: str | CodeLabel) -> CodeLabel:
    """Resolve the entry point label in the CFG."""
    entry: str | CodeLabel = entry_point or cfg.entry
    if entry in cfg.blocks:
        return entry if isinstance(entry, CodeLabel) else CodeLabel(entry)
    matches = [label for label in cfg.blocks if label.contains(str(entry))]
    if not matches:
        raise ValueError(
            f"Entry point '{entry}' not found in CFG. "
            f"Available: {list(cfg.blocks.keys())}"
        )
    return matches[0]


def _resolve_entry_function(vm: VMState, entry_point: str, cfg: CFG) -> CodeLabel:
    """Look up an entry_point function in the VM scope after module preamble.

    Checks vm.current_frame.local_vars for a FuncRef or BoundFuncRef matching
    the entry_point name. Falls back to _find_entry_point label matching.
    """
    match unwrap(vm.current_frame.local_vars.get(VarName(entry_point))):
        case BoundFuncRef(func_ref=func_ref):
            return func_ref.label
        case FuncRef(label=label):
            return label
        case _:
            return _find_entry_point(cfg, entry_point)


def _trace(verbose: bool, message: str) -> None:
    if verbose:
        logger.info("%s", message)


def _log_step(
    verbose: bool, step: int, label: CodeLabel, ip: int, instruction: InstructionBase
) -> None:
    if verbose:
        logger.info("[step %d] %s:%d  %s", step, label, ip, instruction)


def _update_lines(update: StateUpdate) -> list[str]:
    return [
        *(
            f"    {reg} = {_format_val(val)}"
            for reg, val in update.register_writes.items()
        ),
        *(f"    ${var} = {_format_val(val)}" for var, val in update.var_writes.items()),
        *(
            f"    heap[{hw.obj_addr}].{hw.field} = {_format_val(hw.value)}"
            for hw in update.heap_writes
        ),
        *(f"    new {obj.type_hint} @ {obj.addr}" for obj in update.new_objects),
        *([f"    → {update.next_label}"] if update.next_label else []),
        *([f"    path: {update.path_condition}"] if update.path_condition else []),
        "",
    ]


def _log_update(
    step: int,
    current_label: CodeLabel,
    ip: int,
    instruction: InstructionBase,
    update: StateUpdate,
    used_llm: bool,
) -> None:
    """Log verbose step-by-step execution info."""
    tag = "LLM" if used_llm else "local"
    logger.info("  [%s] %s", tag, update.reasoning)
    for line in _update_lines(update):
        logger.info("%s", line)


def _is_void(value: Any) -> bool:
    return isinstance(value, TypedValue) and value.type == scalar(
        FoundationTypeName.VOID
    )


def _deliver_return_value(
    caller: StackFrame, returning: StackFrame, update: StateUpdate
) -> None:
    if not returning.result_reg.is_present() or _is_void(update.return_value):
        return
    caller.registers[returning.result_reg] = update.return_value


def _handle_return_flow(
    vm: VMState,
    cfg: CFG,
    return_frame: StackFrame,
    update: StateUpdate,
    verbose: bool,
    step: int,
) -> _Flow:
    """Handle RETURN/THROW control flow. Returns new (label, ip) or stop sentinel."""
    if len(vm.call_stack) < 1 or return_frame.function_name == FuncName(
        constants.MAIN_FRAME_NAME
    ):
        _trace(verbose, f"[step {step}] Top-level return/throw. Stopping.")
        return _StopExecution()
    _deliver_return_value(vm.current_frame, return_frame, update)
    if return_frame.return_label and return_frame.return_label in cfg.blocks:
        return (return_frame.return_label, return_frame.return_ip or 0)
    _trace(verbose, f"[step {step}] No return label. Stopping.")
    return _StopExecution()


@dataclass(frozen=True)
class _LoopResult:
    """Internal outcome of one slice of the step loop."""

    suspended: bool
    exhausted: bool = False
    steps: int = 0
    llm_calls: int = 0
    susp_label: CodeLabel = NO_LABEL
    susp_ip: int = 0
    susp_reg: Register = NO_REGISTER
    susp_value: Any = None


def _make_base_ctx(
    cfg: CFG,
    registry: FunctionRegistry,
    call_resolver: UnresolvedCallResolver,
    strategies: ExecutionStrategies,
    config: VMConfig,
) -> HandlerContext:
    """Build the per-run HandlerContext shared by every step in a loop slice."""
    return HandlerContext(
        cfg=cfg,
        registry=registry,
        current_label=NO_LABEL,
        ip=0,
        call_resolver=call_resolver,
        overload_resolver=strategies.overload_resolver,
        type_env=strategies.type_env,
        binop_coercion=strategies.binop_coercion,
        unop_coercion=strategies.unop_coercion,
        func_symbol_table=strategies.func_symbol_table,
        class_symbol_table=strategies.class_symbol_table,
        field_fallback=strategies.field_fallback,
        function_scoping=strategies.function_scoping,
        symbol_table=strategies.symbol_table,
        permit_unresolved_call_targets=config.permit_unresolved_call_targets,
        builtins=config.builtins,
    )


def _lazy_backend(config: VMConfig) -> Callable[[], LLMBackend]:
    return functools.cache(functools.partial(get_backend, config.backend))


def _report_progress(config: VMConfig, step: int, label: CodeLabel) -> None:
    if config.step_callback and step and step % config.step_callback_interval == 0:
        config.step_callback(step, str(label))


def _fall_through(
    block: BasicBlock, label: CodeLabel, step: int, verbose: bool
) -> _Flow:
    if block.successors:
        return (block.successors[0], 0)
    _trace(verbose, f"[step {step}] End of '{label}', no successors. Stopping.")
    return _StopExecution()


def _interpret(
    instruction: InstructionBase,
    vm: VMState,
    ctx: HandlerContext,
    llm: Callable[[], LLMBackend],
    conversion_rules: TypeConversionRules,
) -> tuple[StateUpdate, bool]:
    result = _try_execute_locally(instruction, vm, ctx)
    if result.handled:
        return coerce_local_update(result.update, ctx.type_env, conversion_rules), False
    raw_update = llm().interpret_instruction(instruction, vm)
    return materialize_raw_update(raw_update, vm, ctx.type_env, conversion_rules), True


def _proceed(ctx: HandlerContext, update: StateUpdate) -> _Flow:
    target = _branch_target(ctx.cfg, ctx.current_label, update)
    if target.is_present():
        return (target, 0)
    return (ctx.current_label, ctx.ip + 1)


def _flow(
    vm: VMState,
    ctx: HandlerContext,
    instruction: InstructionBase,
    update: StateUpdate,
    returning: Sequence[StackFrame],
    step: int,
    verbose: bool,
) -> _Flow:
    if isinstance(instruction, Halt_):
        _trace(verbose, f"[step {step}] STOP RUN — halting entire run unit.")
        return _StopExecution()
    if returning:
        return _handle_return_flow(vm, ctx.cfg, returning[0], update, verbose, step)
    return _proceed(ctx, update)


def _unwinds(instruction: InstructionBase, update: StateUpdate) -> bool:
    return isinstance(instruction, Return_) or (
        isinstance(instruction, Throw_) and update.next_label is None
    )


def _execute(
    vm: VMState,
    instruction: InstructionBase,
    ctx: HandlerContext,
    step: int,
    *,
    llm: Callable[[], LLMBackend],
    conversion_rules: TypeConversionRules,
    verbose: bool,
) -> tuple[_Flow, bool]:
    update, used_llm = _interpret(instruction, vm, ctx, llm, conversion_rules)
    if verbose:
        _log_update(step, ctx.current_label, ctx.ip, instruction, update, used_llm)
    returning = (vm.current_frame,) if _unwinds(instruction, update) else ()
    apply_update(vm, update, type_env=ctx.type_env, conversion_rules=conversion_rules)
    return _flow(vm, ctx, instruction, update, returning, step, verbose), used_llm


def _step(
    vm: VMState,
    base_ctx: HandlerContext,
    label: CodeLabel,
    ip: int,
    step: int,
    *,
    llm: Callable[[], LLMBackend],
    conversion_rules: TypeConversionRules,
    verbose: bool,
) -> tuple[_Flow | Suspend, bool]:
    block = base_ctx.cfg.blocks[label]
    if ip >= len(block.instructions):
        return _fall_through(block, label, step, verbose), False
    instruction = block.instructions[ip]
    _log_step(verbose, step, label, ip, instruction)
    if isinstance(instruction, (Label_, Data, Suspend)):
        return _skipped(instruction, label, ip), False
    ctx = replace(base_ctx, current_label=label, ip=ip)
    return _execute(
        vm,
        instruction,
        ctx,
        step,
        llm=llm,
        conversion_rules=conversion_rules,
        verbose=verbose,
    )


def _skipped(
    instruction: Label_ | Data | Suspend, label: CodeLabel, ip: int
) -> _Flow | Suspend:
    if isinstance(instruction, Suspend):
        return instruction
    return (label, ip + 1)


def _suspended_value(vm: VMState, instruction: Suspend) -> Any:
    if not instruction.operand_reg.is_present():
        return None
    return unwrap(vm.current_frame.registers.get(instruction.operand_reg))


def _suspension(
    vm: VMState,
    instruction: Suspend,
    label: CodeLabel,
    ip: int,
    steps: int,
    llm_calls: int,
) -> _LoopResult:
    return _LoopResult(
        suspended=True,
        steps=steps,
        llm_calls=llm_calls,
        susp_label=label,
        susp_ip=ip + 1,
        susp_reg=instruction.result_reg,
        susp_value=_suspended_value(vm, instruction),
    )


def _run_loop(
    cfg: CFG,
    vm: VMState,
    current_label: CodeLabel,
    ip: int,
    *,
    config: VMConfig,
    base_ctx: HandlerContext,
    conversion_rules: TypeConversionRules,
) -> _LoopResult:
    """The core fetch-decode-execute loop, shared by ``execute_cfg`` and the
    resumable ``run_resumable``/``resume`` entry points.

    Starts at ``(current_label, ip)`` and runs until the program terminates OR a
    ``Suspend`` instruction is reached, in which case it returns immediately with
    the suspension cursor. The cursor + ``vm`` together form a resumable
    continuation; nothing else (no Python stack) needs preserving because the
    call stack lives in ``vm.call_stack``.
    """
    advance = functools.partial(
        _step,
        vm,
        base_ctx,
        llm=_lazy_backend(config),
        conversion_rules=conversion_rules,
        verbose=config.verbose,
    )
    llm_calls = 0
    for step in range(config.max_steps):
        _report_progress(config, step, current_label)
        flow, used_llm = advance(current_label, ip, step)
        llm_calls += used_llm
        if isinstance(flow, Suspend):
            return _suspension(vm, flow, current_label, ip, step + 1, llm_calls)
        if isinstance(flow, _StopExecution):
            return _LoopResult(suspended=False, steps=step + 1, llm_calls=llm_calls)
        current_label, ip = flow
    _warn_step_budget_exhausted(config.max_steps, current_label, ip)
    return _LoopResult(
        suspended=False,
        exhausted=True,
        steps=config.max_steps,
        llm_calls=llm_calls,
    )


def _branch_target(cfg: CFG, source: CodeLabel, update: StateUpdate) -> CodeLabel:
    target = update.next_label or NO_LABEL
    if target.is_present() and target not in cfg.blocks:
        raise UnknownBranchTargetError(source, target)
    return target


def _warn_step_budget_exhausted(max_steps: int, label: CodeLabel, ip: int) -> None:
    """Report that execution stopped on the step budget, not on program termination."""
    logger.warning(
        "VM ran out of step budget (%d steps) before the program ended; "
        "stopped at %s:%d",
        max_steps,
        label,
        ip,
    )


def initial_vm_state(
    io_provider: RecordIOProvider = NO_IO_PROVIDER,
    null_access: NullAccess = WARN_AND_IGNORE,
) -> VMState:
    """Build a fresh VMState seeded with the ``<main>`` call frame.

    ``execute_cfg``/``run_resumable``/``execute_cfg_traced``/``run_linked``/
    ``run_linked_resumable`` all require a caller-supplied ``vm``/``initial_vm``
    now (no ``None``-defaulted fallback). This is the equivalent of what those
    functions used to build internally when the argument was omitted — callers
    that don't need to continue an existing VM should call this to get one.
    """
    return VMState(
        null_access=null_access,
        call_stack=[StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME))],
        io_provider=io_provider,
    )


def _execution_stats(steps: int, llm_calls: int, vm: VMState) -> ExecutionStats:
    return ExecutionStats(
        steps=steps,
        llm_calls=llm_calls,
        final_heap_objects=vm.heap_count(),
        final_symbolic_count=vm.symbolic_counter,
        closures_captured=len(vm.closures),
    )


def _log_execution_done(stats: ExecutionStats, verbose: bool) -> None:
    logger.debug(
        "execute_cfg done: %d steps, %d LLM calls", stats.steps, stats.llm_calls
    )
    _trace(verbose, f"({stats.steps} steps, {stats.llm_calls} LLM calls)")


def execute_cfg(
    cfg: CFG,
    entry_point: str | CodeLabel,
    registry: FunctionRegistry,
    config: VMConfig = _DEFAULT_VM_CONFIG,
    strategies: ExecutionStrategies = _DEFAULT_STRATEGIES,
    *,
    vm: VMState,
) -> tuple[VMState, ExecutionStats]:
    """Execute a pre-built CFG from the given entry point.

    Runs the step loop (local execution + LLM fallback) against ``vm``, and
    returns the final VM state plus execution metrics.

    Args:
        cfg: Pre-built control flow graph.
        entry_point: Label of the block to start execution from.
        registry: Pre-built function/class registry.
        config: Execution configuration (backend, max_steps, verbose).
        strategies: Language-specific execution strategies (type env, coercion, etc.).
        vm: VM state to execute against (continues from it in place). Use
            ``initial_vm_state()`` to get a fresh one.

    Returns:
        Tuple of (final VMState, ExecutionStats).
    """
    entry = _find_entry_point(cfg, entry_point)
    logger.debug("execute_cfg: entry=%s max_steps=%d", entry, config.max_steps)

    call_resolver = _create_resolver(config)
    base_ctx = _make_base_ctx(cfg, registry, call_resolver, strategies, config)

    loop = _run_loop(
        cfg,
        vm,
        entry,
        0,
        config=config,
        base_ctx=base_ctx,
        conversion_rules=strategies.conversion_rules,
    )
    if loop.suspended:
        raise RuntimeError(
            "SUSPEND reached under execute_cfg(); use run_resumable()/resume() "
            "for suspendable execution"
        )

    stats = _execution_stats(
        loop.steps, loop.llm_calls + call_resolver.llm_call_count, vm
    )
    _log_execution_done(stats, config.verbose)
    return (vm, stats)


@dataclass(frozen=True)
class ExecutionState:
    """A resumable, serializable continuation.

    Holds only the DYNAMIC state — the ``vm`` (working storage, call stack, heap,
    regions, continuations) plus the cursor ``(current_label, ip)`` and the
    register a resumed value lands in. It does NOT hold the static program: the
    CFG/registry are rebuilt and passed to ``resume()``. So the continuation is
    plain, picklable data — it can be serialized, the whole process torn down,
    and execution resumed against a freshly rebuilt pipeline.
    """

    vm: VMState
    current_label: CodeLabel
    ip: int
    resume_reg: Register
    entered: CodeLabel


@dataclass(frozen=True)
class Suspended:
    """Outcome: execution paused at a ``Suspend`` instruction."""

    state: ExecutionState
    value: Any


@dataclass(frozen=True)
class Completed:
    """Outcome: execution ran to termination."""

    vm: VMState
    stats: ExecutionStats


@dataclass(frozen=True)
class BudgetExhausted:
    """Outcome: execution stopped on the step budget before the program ended."""

    vm: VMState
    stats: ExecutionStats


RunOutcome = Suspended | Completed | BudgetExhausted


def _wrap_outcome(
    loop: _LoopResult,
    vm: VMState,
    call_resolver: UnresolvedCallResolver,
    entered: CodeLabel,
) -> RunOutcome:
    if loop.suspended:
        return Suspended(
            state=ExecutionState(
                vm=vm,
                current_label=loop.susp_label,
                ip=loop.susp_ip,
                resume_reg=loop.susp_reg,
                entered=entered,
            ),
            value=loop.susp_value,
        )
    stats = _execution_stats(
        loop.steps, loop.llm_calls + call_resolver.llm_call_count, vm
    )
    terminal = BudgetExhausted if loop.exhausted else Completed
    return terminal(vm=vm, stats=stats)


def run_resumable(
    cfg: CFG,
    entry_point: str | CodeLabel,
    registry: FunctionRegistry,
    config: VMConfig = _DEFAULT_VM_CONFIG,
    strategies: ExecutionStrategies = _DEFAULT_STRATEGIES,
    *,
    vm: VMState,
) -> RunOutcome:
    """Execute a CFG, returning ``Suspended`` if it hits a ``Suspend`` (instead of
    raising as ``execute_cfg`` does), or ``Completed`` when it terminates."""
    entry = _find_entry_point(cfg, entry_point)
    call_resolver = _create_resolver(config)
    base_ctx = _make_base_ctx(cfg, registry, call_resolver, strategies, config)
    loop = _run_loop(
        cfg,
        vm,
        entry,
        0,
        config=config,
        base_ctx=base_ctx,
        conversion_rules=strategies.conversion_rules,
    )
    return _wrap_outcome(loop, vm, call_resolver, NO_LABEL)


def resume(
    cfg: CFG,
    registry: FunctionRegistry,
    state: ExecutionState,
    value: Any = None,
    config: VMConfig = _DEFAULT_VM_CONFIG,
    strategies: ExecutionStrategies = _DEFAULT_STRATEGIES,
) -> RunOutcome:
    """Resume a suspended ``ExecutionState``, injecting ``value`` as the result of
    the ``Suspend`` (written into its result register), and run to the next
    suspension or to termination.

    ``cfg``/``registry`` are the (re)built static program — they need not be the
    same Python objects used originally, enabling resume after a full pipeline
    rebuild. The ``state`` is mutated in place (its ``vm`` advances); deep-copy it
    first for multi-shot resumption.
    """
    vm = state.vm
    if state.resume_reg.is_present():
        vm.current_frame.registers[state.resume_reg] = typed(value, UNKNOWN)
    call_resolver = _create_resolver(config)
    base_ctx = _make_base_ctx(cfg, registry, call_resolver, strategies, config)
    loop = _run_loop(
        cfg,
        vm,
        state.current_label,
        state.ip,
        config=config,
        base_ctx=base_ctx,
        conversion_rules=strategies.conversion_rules,
    )
    return _wrap_outcome(loop, vm, call_resolver, state.entered)


def _traced_execute(
    vm: VMState,
    instruction: InstructionBase,
    ctx: HandlerContext,
    step: int,
    index: int,
    *,
    llm: Callable[[], LLMBackend],
    conversion_rules: TypeConversionRules,
    verbose: bool,
) -> tuple[_Flow, tuple[TraceStep, ...]]:
    update, used_llm = _interpret(instruction, vm, ctx, llm, conversion_rules)
    if verbose:
        _log_update(step, ctx.current_label, ctx.ip, instruction, update, used_llm)
    unwinds = isinstance(instruction, (Return_, Throw_))
    returning = (vm.current_frame,) if unwinds else ()
    apply_update(vm, update, type_env=ctx.type_env, conversion_rules=conversion_rules)
    recorded = TraceStep(
        step_index=index,
        block_label=ctx.current_label,
        instruction_index=ctx.ip,
        instruction=instruction,
        update=update,
        vm_state=copy.deepcopy(vm),
        used_llm=used_llm,
    )
    return _flow(vm, ctx, instruction, update, returning, step, verbose), (recorded,)


def _traced_step(
    vm: VMState,
    base_ctx: HandlerContext,
    label: CodeLabel,
    ip: int,
    step: int,
    index: int,
    *,
    llm: Callable[[], LLMBackend],
    conversion_rules: TypeConversionRules,
    verbose: bool,
) -> tuple[_Flow, tuple[TraceStep, ...]]:
    block = base_ctx.cfg.blocks[label]
    if ip >= len(block.instructions):
        return _fall_through(block, label, step, verbose), ()
    instruction = block.instructions[ip]
    _log_step(verbose, step, label, ip, instruction)
    if isinstance(instruction, (Label_, Data)):
        return (label, ip + 1), ()
    return _traced_execute(
        vm,
        instruction,
        replace(base_ctx, current_label=label, ip=ip),
        step,
        index,
        llm=llm,
        conversion_rules=conversion_rules,
        verbose=verbose,
    )


def execute_cfg_traced(
    cfg: CFG,
    entry_point: CodeLabel,
    registry: FunctionRegistry,
    config: VMConfig = _DEFAULT_VM_CONFIG,
    strategies: ExecutionStrategies = _DEFAULT_STRATEGIES,
    *,
    vm: VMState,
) -> tuple[VMState, ExecutionTrace]:
    """Execute a pre-built CFG and record a trace of every step.

    Identical to execute_cfg() but deep-copies the VMState after each
    instruction so callers can replay the execution step by step.

    Args:
        cfg: Pre-built control flow graph.
        entry_point: Label of the block to start execution from.
        registry: Pre-built function/class registry.
        config: Execution configuration (backend, max_steps, verbose).
        strategies: Language-specific execution strategies (type env, coercion, etc.).
        vm: VMState to execute against. Use ``initial_vm_state()`` for a fresh one.

    Returns:
        Tuple of (final VMState, ExecutionTrace with per-step snapshots).
    """
    entry = _find_entry_point(cfg, entry_point)
    initial_state = copy.deepcopy(vm)
    call_resolver = _create_resolver(config)
    advance = functools.partial(
        _traced_step,
        vm,
        _make_base_ctx(cfg, registry, call_resolver, strategies, config),
        llm=_lazy_backend(config),
        conversion_rules=strategies.conversion_rules,
        verbose=config.verbose,
    )
    current_label, ip, step = entry, 0, 0
    trace_steps: list[TraceStep] = []

    for step in range(config.max_steps):
        flow, recorded = advance(current_label, ip, step, len(trace_steps))
        trace_steps.extend(recorded)
        if isinstance(flow, _StopExecution):
            break
        current_label, ip = flow
    else:
        _warn_step_budget_exhausted(config.max_steps, current_label, ip)

    llm_calls = sum(1 for traced in trace_steps if traced.used_llm)
    stats = _execution_stats(step + 1, llm_calls + call_resolver.llm_call_count, vm)
    _trace(config.verbose, f"({stats.steps} steps, {stats.llm_calls} LLM calls)")
    return (
        vm,
        ExecutionTrace(steps=trace_steps, stats=stats, initial_state=initial_state),
    )


def _build_strategies_from_linked(linked: LinkedProgram) -> ExecutionStrategies:
    """Build ExecutionStrategies from a LinkedProgram's data."""
    conversion_rules = DefaultTypeConversionRules()
    type_resolver = TypeResolver(conversion_rules)
    type_env = infer_types(
        linked.merged_ir,
        type_resolver,
        type_env_builder=linked.type_env_builder,
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
    )
    class_nodes = tuple(
        TypeNode(
            name=TypeName(str(cls)), parents=tuple(TypeName(str(p)) for p in parents)
        )
        for cls, parents in linked.merged_registry.class_parents.items()
    )
    type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
    overload_resolver = OverloadResolver(
        ArityThenTypeStrategy(DefaultTypeCompatibility(type_graph)),
        FallbackFirstWithWarning(),
    )
    return ExecutionStrategies(
        type_env=type_env,
        conversion_rules=conversion_rules,
        overload_resolver=overload_resolver,
        binop_coercion=_binop_coercion_for_language(linked.language),
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
        field_fallback=_field_fallback_for_language(linked.language),
        function_scoping=_function_scoping_for_language(linked.language),
        symbol_table=linked.symbol_table,
    )


def _after_preamble(
    linked: LinkedProgram,
    dispatch: EntryPoint,
    vm_config: VMConfig,
    strategies: ExecutionStrategies,
    initial_vm: VMState,
) -> tuple[VMState, CodeLabel, VMConfig]:
    vm, preamble_stats = execute_cfg(
        linked.merged_cfg,
        linked.merged_cfg.entry,
        linked.merged_registry,
        vm_config,
        strategies,
        vm=initial_vm,
    )
    func_ref = dispatch.resolve(list(linked.func_symbol_table.values()))
    func_label = _resolve_entry_function(vm, str(func_ref.name), linked.merged_cfg)
    remaining = max(vm_config.max_steps - preamble_stats.steps, 0)
    return vm, func_label, replace(vm_config, max_steps=remaining)


def _run_dispatched(
    linked: LinkedProgram,
    dispatch: EntryPoint,
    vm_config: VMConfig,
    strategies: ExecutionStrategies,
    initial_vm: VMState,
) -> VMState:
    if dispatch.is_top_level:
        return execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
            vm=initial_vm,
        )[0]
    vm, func_label, phase2_config = _after_preamble(
        linked, dispatch, vm_config, strategies, initial_vm
    )
    return execute_cfg(
        linked.merged_cfg,
        func_label,
        linked.merged_registry,
        phase2_config,
        strategies,
        vm=vm,
    )[0]


def run_linked(
    linked: LinkedProgram,
    entry_point: EntryPoint | ProgramEntry,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: RecordIOProvider = NO_IO_PROVIDER,
    *,
    builtins: Mapping[FuncName, Builtin],
    initial_vm: VMState,
    permit_unresolved_call_targets: bool = True,
    step_callback: Callable[[int, str], None] | None = None,
    step_callback_interval: int = 1_000_000,
) -> VMState:
    """Execute a LinkedProgram with the given entry point.

    Args:
        linked: Pre-compiled program (single-module or multi-module).
        entry_point: How to enter — EntryPoint.top_level(), EntryPoint.function(pred),
            or ProgramEntry(name), the image's program of that name.
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        backend: LLM backend for interpreter fallback.
        unresolved_call_strategy: Resolution strategy for unknown calls.
        io_provider: The file provider record I/O calls reach (e.g. StubIOProvider for
            testing); ``NO_IO_PROVIDER``, the default, serves none.
        builtins: The builtins table this run resolves builtin calls through.
        initial_vm: VM state to execute against. Use ``initial_vm_state()`` for a
            fresh one.
        permit_unresolved_call_targets: When False, a CALL_WITH_MEMORY to a
            literal location that resolves to nothing raises
            UnresolvedProgramError instead of going to the call resolver.
        step_callback: Optional callable(step, label) invoked every
            step_callback_interval steps for progress reporting.
        step_callback_interval: How often to invoke step_callback (default 1M steps).
    """
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
        permit_unresolved_call_targets=permit_unresolved_call_targets,
        builtins=builtins,
        io_provider=io_provider,
        step_callback=step_callback,
        step_callback_interval=step_callback_interval,
    )
    dispatch, entered = _entering(linked, entry_point)
    initial_vm.declarations = _declarations_at(linked, entered)
    return _run_dispatched(
        linked, dispatch, vm_config, _build_strategies_from_linked(linked), initial_vm
    )


def _entering(
    linked: LinkedProgram, entry_point: EntryPoint | ProgramEntry
) -> tuple[EntryPoint, CodeLabel]:
    match entry_point:
        case ProgramEntry(name=name):
            label = _program_label(linked, name)
            return EntryPoint.function(lambda ref: ref.label == label), label
        case EntryPoint():
            return entry_point, linked.entry_func_label


def _program_label(linked: LinkedProgram, program: str) -> CodeLabel:
    if program not in linked.programs:
        raise ProgramNotInImage(program)
    return linked.programs[program]


def declarations_of(linked: LinkedProgram, program: str) -> tuple[Data, ...]:
    return _declarations_at(linked, _program_label(linked, program))


def _declarations_at(linked: LinkedProgram, entered: CodeLabel) -> tuple[Data, ...]:
    return next(
        (
            tuple(i for i in unit.ir if isinstance(i, Data))
            for unit in linked.modules.values()
            if unit.entry_label.namespace(module_prefix(unit.path, PROJECT_ROOT))
            == entered
        ),
        (),
    )


def _carrying(outcome: RunOutcome, entered: CodeLabel) -> RunOutcome:
    match outcome:
        case Suspended(state=state):
            return replace(outcome, state=replace(state, entered=entered))
        case _:
            return outcome


def _resumable_dispatched(
    linked: LinkedProgram,
    dispatch: EntryPoint,
    vm_config: VMConfig,
    strategies: ExecutionStrategies,
    initial_vm: VMState,
) -> RunOutcome:
    if dispatch.is_top_level:
        return run_resumable(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
            vm=initial_vm,
        )
    vm, func_label, phase2_config = _after_preamble(
        linked, dispatch, vm_config, strategies, initial_vm
    )
    return run_resumable(
        linked.merged_cfg,
        func_label,
        linked.merged_registry,
        phase2_config,
        strategies,
        vm=vm,
    )


def run_linked_resumable(
    linked: LinkedProgram,
    entry_point: EntryPoint | ProgramEntry,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: RecordIOProvider = NO_IO_PROVIDER,
    *,
    builtins: Mapping[FuncName, Builtin],
    initial_vm: VMState,
    permit_unresolved_call_targets: bool = True,
) -> RunOutcome:
    """Like ``run_linked`` but suspendable: returns ``Suspended`` if execution
    reaches a ``SUSPEND`` instruction, else ``Completed``.

    The preamble (module init / function registration) runs to completion via the
    non-resumable path — it never suspends — and only the program body (phase 2)
    is run resumably. Continue with ``resume_linked``.
    """
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
        permit_unresolved_call_targets=permit_unresolved_call_targets,
        builtins=builtins,
        io_provider=io_provider,
    )
    dispatch, entered = _entering(linked, entry_point)
    initial_vm.declarations = _declarations_at(linked, entered)
    outcome = _resumable_dispatched(
        linked, dispatch, vm_config, _build_strategies_from_linked(linked), initial_vm
    )
    return _carrying(outcome, entered)


def resume_linked(
    linked: LinkedProgram,
    state: ExecutionState,
    value: Any = None,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: RecordIOProvider = NO_IO_PROVIDER,
    permit_unresolved_call_targets: bool = True,
    *,
    builtins: Mapping[FuncName, Builtin],
) -> RunOutcome:
    """Resume a ``run_linked_resumable`` continuation, injecting ``value`` at the
    suspension point, and run to the next suspension or to termination."""
    strategies = _build_strategies_from_linked(linked)
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
        permit_unresolved_call_targets=permit_unresolved_call_targets,
        builtins=builtins,
        io_provider=io_provider,
    )
    if io_provider is not NO_IO_PROVIDER:
        state.vm.io_provider = io_provider
    state.vm.declarations = _declarations_at(linked, state.entered)
    return resume(
        linked.merged_cfg,
        linked.merged_registry,
        state,
        value,
        vm_config,
        strategies,
    )


def _concatenated(
    preamble_trace: ExecutionTrace, dispatch_trace: ExecutionTrace
) -> ExecutionTrace:
    preamble_step_count = len(preamble_trace.steps)
    renumbered_dispatch_steps = [
        replace(step, step_index=step.step_index + preamble_step_count)
        for step in dispatch_trace.steps
    ]
    combined_stats = ExecutionStats(
        steps=preamble_trace.stats.steps + dispatch_trace.stats.steps,
        llm_calls=preamble_trace.stats.llm_calls + dispatch_trace.stats.llm_calls,
        final_heap_objects=dispatch_trace.stats.final_heap_objects,
        final_symbolic_count=dispatch_trace.stats.final_symbolic_count,
        closures_captured=preamble_trace.stats.closures_captured
        + dispatch_trace.stats.closures_captured,
    )
    return ExecutionTrace(
        steps=preamble_trace.steps + renumbered_dispatch_steps,
        stats=combined_stats,
        initial_state=preamble_trace.initial_state,
    )


def _traced_function_entry(
    linked: LinkedProgram,
    dispatch: EntryPoint,
    vm_config: VMConfig,
    strategies: ExecutionStrategies,
    initial_vm: VMState,
) -> tuple[VMState, ExecutionTrace]:
    preambled, preamble_trace = execute_cfg_traced(
        linked.merged_cfg,
        linked.merged_cfg.entry,
        linked.merged_registry,
        vm_config,
        strategies,
        vm=initial_vm,
    )
    func_ref = dispatch.resolve(list(linked.func_symbol_table.values()))
    func_label = _resolve_entry_function(
        preambled, str(func_ref.name), linked.merged_cfg
    )
    remaining = max(vm_config.max_steps - preamble_trace.stats.steps, 0)
    vm, dispatch_trace = execute_cfg_traced(
        linked.merged_cfg,
        func_label,
        linked.merged_registry,
        replace(vm_config, max_steps=remaining),
        strategies,
        vm=preambled,
    )
    return vm, _concatenated(preamble_trace, dispatch_trace)


def run_linked_traced(
    linked: LinkedProgram,
    entry_point: EntryPoint | ProgramEntry,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    permit_unresolved_call_targets: bool = True,
    *,
    builtins: Mapping[FuncName, Builtin],
) -> tuple[VMState, ExecutionTrace]:
    """Execute a LinkedProgram and return a trace of execution steps.

    Mirrors run_linked() but uses execute_cfg_traced() instead of execute_cfg()
    and returns both the final VMState and a complete ExecutionTrace.

    For function entry points, performs two-phase execution (preamble + dispatch)
    and concatenates the traces.

    Args:
        linked: Pre-compiled program (single-module or multi-module).
        entry_point: How to enter — EntryPoint.top_level(), EntryPoint.function(pred),
            or ProgramEntry(name), the image's program of that name.
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        backend: LLM backend for interpreter fallback.
        unresolved_call_strategy: Resolution strategy for unknown calls.

    Returns:
        Tuple of (final VMState, ExecutionTrace with per-step snapshots).
    """
    strategies = _build_strategies_from_linked(linked)
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
        permit_unresolved_call_targets=permit_unresolved_call_targets,
        builtins=builtins,
    )
    initial_vm = initial_vm_state()
    dispatch, entered = _entering(linked, entry_point)
    initial_vm.declarations = _declarations_at(linked, entered)
    if dispatch.is_top_level:
        return execute_cfg_traced(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
            vm=initial_vm,
        )
    return _traced_function_entry(linked, dispatch, vm_config, strategies, initial_vm)


class _StatsObserver:
    """Populates PipelineStats timing fields from frontend callbacks."""

    def __init__(self, target: PipelineStats):
        self._target = target

    def on_parse(self, duration: float) -> None:
        self._target.parse_time = duration

    def on_lower(self, duration: float) -> None:
        self._target.lower_time = duration


def _pipeline_stats(source: str, lang: Language, frontend_type: str) -> PipelineStats:
    return PipelineStats(
        source_bytes=len(source.encode("utf-8")),
        source_lines=source.count("\n")
        + (1 if source and not source.endswith("\n") else 0),
        language=lang,
        frontend_type=frontend_type,
    )


def _image_program(
    lang: _ImageLanguage,
    source: str,
    copybook_dirs: Sequence[Path],
    observer: FrontendObserver,
    tolerant: bool,
    stats: PipelineStats,
) -> LinkedProgram:
    linked = _compiled_image(
        lang, source.encode("utf-8"), copybook_dirs, observer, tolerant
    )
    stats.ir_instruction_count = len(linked.merged_ir)
    stats.cfg_block_count = len(linked.merged_cfg.blocks)
    stats.registry_functions = len(linked.merged_registry.func_params)
    stats.registry_classes = len(linked.merged_registry.classes)
    return linked


def _log_ir(verbose: bool, instructions: Sequence[InstructionBase]) -> None:
    if not verbose:
        return
    logger.info("═══ IR ═══")
    for inst in instructions:
        logger.info("  %s", inst)
    logger.info("")


def _timed_cfg(
    instructions: list[InstructionBase], verbose: bool, stats: PipelineStats
) -> CFG:
    started = time.perf_counter()
    cfg = build_cfg(instructions)
    stats.cfg_time = time.perf_counter() - started
    stats.cfg_block_count = len(cfg.blocks)
    if verbose:
        logger.info("═══ CFG ═══")
        logger.info("%s", cfg)
    return cfg


def _timed_registry(
    instructions: list[InstructionBase],
    cfg: CFG,
    frontend: Frontend,
    stats: PipelineStats,
) -> FunctionRegistry:
    started = time.perf_counter()
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    stats.registry_time = time.perf_counter() - started
    stats.registry_functions = len(registry.func_params)
    stats.registry_classes = len(registry.classes)
    return registry


def _lowered_program(
    source: str,
    lang: Language,
    frontend: Frontend,
    verbose: bool,
    stats: PipelineStats,
) -> LinkedProgram:
    instructions = frontend.lower(source.encode("utf-8"))
    stats.ir_instruction_count = len(instructions)
    logger.debug(
        "Frontend produced %d IR instructions in %.1fms",
        stats.ir_instruction_count,
        (stats.parse_time + stats.lower_time) * 1000,
    )
    _log_ir(verbose, instructions)
    cfg = _timed_cfg(instructions, verbose, stats)
    return LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=_timed_registry(instructions, cfg, frontend, stats),
        language=lang,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )


def _effective_entry(
    lang: Language, entry_point: EntryPoint, linked: LinkedProgram
) -> EntryPoint:
    if not (_is_image_language(lang) and entry_point.is_top_level):
        return entry_point
    label = linked.entry_func_label
    return EntryPoint.function(lambda ref: ref.label == label)


def _record_run_times(
    stats: PipelineStats, pipeline_start: float, exec_start: float
) -> None:
    finished = time.perf_counter()
    stats.execution_time = finished - exec_start
    stats.total_time = finished - pipeline_start


def _log_report(verbose: bool, stats: PipelineStats) -> None:
    if verbose:
        logger.info("")
        logger.info("%s", stats.report())


def run(
    source: str,
    language: str | Language = Language.PYTHON,
    entry_point: EntryPoint = _TOP_LEVEL,
    backend: str = LLMProvider.CLAUDE,
    max_steps: int = 100,
    verbose: bool = False,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_client: Any = None,  # Any: Optional LLM client injection — see red-dragon-c7y2
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: RecordIOProvider = NO_IO_PROVIDER,
    copybook_dirs: list[Path] = [],
    tolerant: bool = False,
    null_access: NullAccess = WARN_AND_IGNORE,
    *,
    builtins: Mapping[FuncName, Builtin] = DEFAULT_BUILTINS,
) -> VMState:
    """End-to-end: parse → lower → build LinkedProgram → run_linked.

    Convenience wrapper that compiles a single source string into a
    LinkedProgram and delegates execution to run_linked().

    Args:
        source: Raw source code string.
        language: Source language name.
        entry_point: How to enter the program (default: top-level execution).
        backend: LLM backend for interpreter fallback ("claude" or "openai").
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        frontend_type: "deterministic" (tree-sitter) or "llm".
        llm_client: Pre-built LLMClient for DI/testing (used by LLM frontend).
        unresolved_call_strategy: Resolution strategy for unknown calls.
        tolerant: Skip (with a WARNING) COBOL statements whose lowering
            raises, instead of failing compilation. Default off. COBOL only.
        builtins: The builtins table this run resolves builtin calls through
            (default: ``DEFAULT_BUILTINS``, the core table). An HLASM run adds
            the HLASM run inputs it is not given: the host clock, an empty
            PARM and no DD definitions. Callers add the floating-point
            builtins and an HLASM program's files: ``declare_file_builtins()``,
            the DD builtin and ``RunInputs`` from ``dd_run_inputs(dds)``, and a
            ``RealFileProvider`` over those inputs as ``io_provider``. Each part
            exists here; red-dragon-forge composes them into a run-time stack.
    """
    lang = Language(language)
    pipeline_start = time.perf_counter()
    stats = _pipeline_stats(source, lang, frontend_type)
    observer = _StatsObserver(stats)
    linked = (
        _image_program(lang, source, copybook_dirs, observer, tolerant, stats)
        if _is_image_language(lang)
        else _lowered_program(
            source,
            lang,
            get_frontend(
                lang,
                frontend_type=frontend_type,
                llm_provider=backend,
                llm_client=llm_client,
                observer=observer,
            ),
            verbose,
            stats,
        )
    )
    exec_start = time.perf_counter()
    vm = run_linked(
        linked,
        entry_point=_effective_entry(lang, entry_point, linked),
        max_steps=max_steps,
        verbose=verbose,
        backend=backend,
        unresolved_call_strategy=unresolved_call_strategy,
        io_provider=io_provider,
        builtins=_language_builtins(lang, builtins),
        initial_vm=initial_vm_state(io_provider=io_provider, null_access=null_access),
    )
    _record_run_times(stats, pipeline_start, exec_start)
    _log_report(verbose, stats)
    return vm


def _language_builtins(
    lang: Language, given: Mapping[FuncName, Builtin]
) -> Mapping[FuncName, Builtin]:
    match lang:
        case Language.HLASM:
            return MappingProxyType({**unsupplied_run_input_builtins(), **given})
        case _:
            return given


def _compiled_image(
    lang: _ImageLanguage,
    source: bytes,
    copybook_dirs: Sequence[Path],
    observer: FrontendObserver,
    tolerant: bool,
) -> LinkedProgram:
    match lang:
        case Language.HLASM:
            return compile_hlasm(source, parser=get_hlasm_parser(copybook_dirs))
        case Language.COBOL:
            return compile_cobol(
                source,
                parser=make_cobol_parser(copybook_dirs=copybook_dirs),
                copybook_dirs=copybook_dirs,
                observer=observer,
                tolerant=tolerant,
            )


def _format_symbolic(name: str, constraints: Sequence[str], hint: str) -> str:
    if constraints:
        return f"{name} [{', '.join(constraints)}]"
    return f"{name}" + (f" ({hint})" if hint else "")


def _format_dict_symbolic(v: Mapping[str, Any]) -> str:
    return _format_symbolic(
        v.get("name", "?"),
        [str(c) for c in v.get("constraints", [])],
        v.get("type_hint", ""),
    )


def _format_bound_func(v: BoundFuncRef) -> str:
    suffix = f"#{v.closure_id}" if v.closure_id else ""
    return f"<function:{v.func_ref.name}@{v.func_ref.label}{suffix}>"


def _format_class(v: ClassRef) -> str:
    parents = f":{','.join(str(p) for p in v.parents)}" if v.parents else ""
    return f"<class:{v.name}@{v.label}{parents}>"


def _format_val(
    v: Any,
) -> str:  # Any: display boundary — formats all runtime value types
    """Format a value for verbose display."""
    match v:
        case TypedValue():
            return _format_val(v.value)
        case SymbolicValue():
            return _format_symbolic(v.name, v.constraints, v.type_hint or "")
        case dict() if v.get("__symbolic__"):
            return _format_dict_symbolic(v)
        case BoundFuncRef():
            return _format_bound_func(v)
        case ClassRef():
            return _format_class(v)
        case _:
            return repr(v)
