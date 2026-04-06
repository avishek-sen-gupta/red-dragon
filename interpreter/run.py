"""Orchestrator — run() entry point."""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field as dataclass_field, replace
from types import MappingProxyType
from typing import Any

from interpreter.constants import Language, TypeName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.types.coercion.conversion_rules import TypeConversionRules
from interpreter.types.coercion.default_conversion_rules import (
    DefaultTypeConversionRules,
)
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.ir import Opcode, CodeLabel, NO_LABEL
from interpreter.instructions import InstructionBase, Label_, Return_, Throw_
from interpreter.frontend import Frontend, get_frontend
from interpreter.frontend_observer import FrontendObserver
from interpreter.cfg import CFG, build_cfg
from interpreter.registry import build_registry, FunctionRegistry
from interpreter.refs.func_ref import FuncRef, BoundFuncRef
from interpreter.refs.class_ref import ClassRef
from interpreter.vm.executor import HandlerContext, _try_execute_locally
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.overload.overload_resolver import (
    NullOverloadResolver,
    OverloadResolver,
)
from interpreter.overload.resolution_strategy import ArityThenTypeStrategy
from interpreter.types.coercion.type_compatibility import DefaultTypeCompatibility
from interpreter.types.type_graph import TypeGraph, DEFAULT_TYPE_NODES
from interpreter.types.type_node import TypeNode
from interpreter.overload.ambiguity_handler import FallbackFirstWithWarning
from interpreter.types.coercion.binop_coercion import (
    BinopCoercionStrategy,
    DefaultBinopCoercion,
    JavaBinopCoercion,
)
from interpreter.types.coercion.unop_coercion import (
    UnopCoercionStrategy,
    DefaultUnopCoercion,
)
from interpreter.vm.field_fallback import (
    FieldFallbackStrategy,
    NoFieldFallback,
    ImplicitThisFieldFallback,
)
from interpreter.vm.function_scoping import (
    FunctionScopingStrategy,
    LocalFunctionScopingStrategy,
    GlobalLeakFunctionScopingStrategy,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_expr import scalar
from interpreter.types.typed_value import TypedValue
from interpreter.types.type_inference import infer_types
from interpreter.types.type_resolver import TypeResolver
from interpreter.vm.unresolved_call import (
    SymbolicResolver,
    LLMPlausibleResolver,
    UnresolvedCallResolver,
)
from interpreter.vm.vm import (
    VMState,
    SymbolicValue,
    StackFrame,
    StateUpdate,
    ExecutionResult,
    apply_update,
    coerce_local_update,
    materialize_raw_update,
)
from interpreter.run_types import (
    VMConfig,
    ExecutionStats,
    PipelineStats,
    UnresolvedCallStrategy,
)  # noqa: F401 — re-exported for backwards compatibility
from interpreter.trace_types import TraceStep, ExecutionTrace
from interpreter.llm.backend import get_backend
from interpreter import constants
from interpreter.constants import LLMProvider
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram

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
    # Try to find a function label matching the entry point
    for label in cfg.blocks:
        if label.contains(str(entry)):
            return label
    raise ValueError(
        f"Entry point '{entry}' not found in CFG. "
        f"Available: {list(cfg.blocks.keys())}"
    )


def _resolve_entry_function(vm: VMState, entry_point: str, cfg: CFG) -> CodeLabel:
    """Look up an entry_point function in the VM scope after module preamble.

    Checks vm.current_frame.local_vars for a FuncRef or BoundFuncRef matching
    the entry_point name. Falls back to _find_entry_point label matching.
    """
    key = VarName(entry_point)
    if key in vm.current_frame.local_vars:
        val = vm.current_frame.local_vars[key]
        raw = val.value if isinstance(val, TypedValue) else val
        if isinstance(raw, BoundFuncRef):
            return raw.func_ref.label
        if isinstance(raw, FuncRef):
            return raw.label
    return _find_entry_point(cfg, entry_point)


def _log_update(
    step: int,
    current_label: CodeLabel,
    ip: int,
    instruction: InstructionBase,
    update: StateUpdate,
    used_llm: bool,
):
    """Log verbose step-by-step execution info."""
    tag = "LLM" if used_llm else "local"
    logger.info("  [%s] %s", tag, update.reasoning)
    for reg, val in update.register_writes.items():
        logger.info("    %s = %s", reg, _format_val(val))
    for var, val in update.var_writes.items():
        logger.info("    $%s = %s", var, _format_val(val))
    for hw in update.heap_writes:
        logger.info(
            "    heap[%s].%s = %s", hw.obj_addr, hw.field, _format_val(hw.value)
        )
    for obj in update.new_objects:
        logger.info("    new %s @ %s", obj.type_hint, obj.addr)
    if update.next_label:
        logger.info("    → %s", update.next_label)
    if update.path_condition:
        logger.info("    path: %s", update.path_condition)
    logger.info("")


def _handle_call_dispatch_setup(
    vm: VMState,
    instruction: InstructionBase,
    update: StateUpdate,
    current_label: CodeLabel,
    ip: int,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
):
    """Set up the new call frame's return info after call_push + dispatch."""
    call_result_reg = instruction.result_reg
    call_return_label = current_label
    call_return_ip = ip + 1

    apply_update(vm, update, type_env=type_env, conversion_rules=conversion_rules)

    new_frame = vm.current_frame
    new_frame.return_label = call_return_label
    new_frame.return_ip = call_return_ip
    new_frame.result_reg = call_result_reg


def _handle_return_flow(
    vm: VMState,
    cfg: CFG,
    return_frame: StackFrame,
    update: StateUpdate,
    verbose: bool,
    step: int,
) -> tuple[CodeLabel, int] | _StopExecution:
    """Handle RETURN/THROW control flow. Returns new (label, ip) or stop sentinel."""
    if len(vm.call_stack) < 1:
        if verbose:
            logger.info("[step %d] Top-level return/throw. Stopping.", step)
        return _StopExecution()

    if return_frame.function_name == FuncName(constants.MAIN_FRAME_NAME):
        if verbose:
            logger.info("[step %d] Top-level return/throw. Stopping.", step)
        return _StopExecution()

    # Return to caller — write return value to caller's result register.
    # result_reg is None when the call site had no assignment (e.g. standalone
    # call_function with no %reg =), so there is no register to write to.
    # Skip Void returns (constructors, bare RETURN with no operands).
    caller_frame = vm.current_frame
    if return_frame.result_reg.is_present() and not (
        isinstance(update.return_value, TypedValue)
        and update.return_value.type == scalar(TypeName.VOID)
    ):
        caller_frame.registers[return_frame.result_reg] = update.return_value

    if return_frame.return_label and return_frame.return_label in cfg.blocks:
        new_ip = return_frame.return_ip if return_frame.return_ip is not None else 0
        return (return_frame.return_label, new_ip)

    if verbose:
        logger.info("[step %d] No return label. Stopping.", step)
    return _StopExecution()


def execute_cfg(
    cfg: CFG,
    entry_point: str | CodeLabel,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    strategies: ExecutionStrategies = ExecutionStrategies(),
    vm: VMState | None = None,
) -> tuple[VMState, ExecutionStats]:
    """Execute a pre-built CFG from the given entry point.

    Initializes a VM, runs the step loop (local execution + LLM fallback),
    and returns the final VM state plus execution metrics.

    Args:
        cfg: Pre-built control flow graph.
        entry_point: Label of the block to start execution from.
        registry: Pre-built function/class registry.
        config: Execution configuration (backend, max_steps, verbose).
        strategies: Language-specific execution strategies (type env, coercion, etc.).
        vm: Pre-built VM state to continue from. If None, a fresh VM is created.

    Returns:
        Tuple of (final VMState, ExecutionStats).
    """
    entry = _find_entry_point(cfg, entry_point)

    if vm is None:
        vm = VMState()
        vm.call_stack.append(
            StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME))
        )
        vm.io_provider = config.io_provider

    llm = None  # lazy — only created if local executor can't handle an instruction
    call_resolver = _create_resolver(config)
    current_label = entry
    ip = 0
    llm_calls = 0
    step = 0

    type_env = strategies.type_env
    conversion_rules = strategies.conversion_rules

    base_ctx = HandlerContext(
        cfg=cfg,
        registry=registry,
        current_label=NO_LABEL,
        ip=0,
        call_resolver=call_resolver,
        overload_resolver=strategies.overload_resolver,
        type_env=type_env,
        binop_coercion=strategies.binop_coercion,
        unop_coercion=strategies.unop_coercion,
        func_symbol_table=strategies.func_symbol_table,
        class_symbol_table=strategies.class_symbol_table,
        field_fallback=strategies.field_fallback,
        function_scoping=strategies.function_scoping,
        symbol_table=strategies.symbol_table,
    )

    for step in range(config.max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            if config.verbose:
                logger.info(
                    "[step %d] End of '%s', no successors. Stopping.",
                    step,
                    current_label,
                )
            break

        instruction = block.instructions[ip]

        if config.verbose:
            logger.info("[step %d] %s:%d  %s", step, current_label, ip, instruction)

        if isinstance(instruction, Label_):
            ip += 1
            continue

        step_ctx = replace(base_ctx, current_label=current_label, ip=ip)
        result = _try_execute_locally(instruction, vm, step_ctx)
        used_llm = False
        if result.handled:
            update = coerce_local_update(result.update, type_env, conversion_rules)
        else:
            if llm is None:
                llm = get_backend(config.backend)
            raw_update = llm.interpret_instruction(instruction, vm)
            update = materialize_raw_update(raw_update, vm, type_env, conversion_rules)
            used_llm = True
            llm_calls += 1

        if config.verbose:
            _log_update(step, current_label, ip, instruction, update, used_llm)

        is_return = isinstance(instruction, Return_)
        is_throw = isinstance(instruction, Throw_)
        is_caught_throw = is_throw and update.next_label is not None
        return_frame = (
            vm.current_frame
            if (is_return or (is_throw and not is_caught_throw))
            else None
        )

        is_call_dispatch = (
            update.call_push is not None and update.next_label is not None
        )
        if is_call_dispatch:
            _handle_call_dispatch_setup(
                vm,
                instruction,
                update,
                current_label,
                ip,
                type_env=type_env,
                conversion_rules=conversion_rules,
            )
        else:
            apply_update(
                vm, update, type_env=type_env, conversion_rules=conversion_rules
            )

        if is_return or (is_throw and not is_caught_throw):
            flow = _handle_return_flow(
                vm, cfg, return_frame, update, config.verbose, step
            )
            if isinstance(flow, _StopExecution):
                break
            current_label, ip = flow

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1

    stats = ExecutionStats(
        steps=step + 1,
        llm_calls=llm_calls + call_resolver.llm_call_count,
        final_heap_objects=vm.heap_count(),
        final_symbolic_count=vm.symbolic_counter,
        closures_captured=len(vm.closures),
    )

    if config.verbose:
        logger.info("(%d steps, %d LLM calls)", stats.steps, stats.llm_calls)

    return (vm, stats)


def execute_cfg_traced(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    strategies: ExecutionStrategies = ExecutionStrategies(),
    vm: VMState | None = None,
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
        vm: Optional pre-built VMState to reuse; a fresh one is created if None.

    Returns:
        Tuple of (final VMState, ExecutionTrace with per-step snapshots).
    """
    entry = _find_entry_point(cfg, entry_point)

    if vm is None:
        vm = VMState()
        vm.call_stack.append(
            StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME))
        )
        vm.io_provider = config.io_provider
    initial_state = copy.deepcopy(vm)

    llm = None  # lazy — only created if local executor can't handle an instruction
    call_resolver = _create_resolver(config)
    current_label = entry
    ip = 0
    llm_calls = 0
    step = 0
    trace_steps: list[TraceStep] = []

    type_env = strategies.type_env
    conversion_rules = strategies.conversion_rules

    base_ctx = HandlerContext(
        cfg=cfg,
        registry=registry,
        current_label=NO_LABEL,
        ip=0,
        call_resolver=call_resolver,
        overload_resolver=strategies.overload_resolver,
        type_env=type_env,
        binop_coercion=strategies.binop_coercion,
        unop_coercion=strategies.unop_coercion,
        func_symbol_table=strategies.func_symbol_table,
        class_symbol_table=strategies.class_symbol_table,
        field_fallback=strategies.field_fallback,
        function_scoping=strategies.function_scoping,
        symbol_table=strategies.symbol_table,
    )

    for step in range(config.max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            if config.verbose:
                logger.info(
                    "[step %d] End of '%s', no successors. Stopping.",
                    step,
                    current_label,
                )
            break

        instruction = block.instructions[ip]

        if config.verbose:
            logger.info("[step %d] %s:%d  %s", step, current_label, ip, instruction)

        if isinstance(instruction, Label_):
            ip += 1
            continue

        step_ctx = replace(base_ctx, current_label=current_label, ip=ip)
        result = _try_execute_locally(instruction, vm, step_ctx)
        used_llm = False
        if result.handled:
            update = coerce_local_update(result.update, type_env, conversion_rules)
        else:
            if llm is None:
                llm = get_backend(config.backend)
            raw_update = llm.interpret_instruction(instruction, vm)
            update = materialize_raw_update(raw_update, vm, type_env, conversion_rules)
            used_llm = True
            llm_calls += 1

        if config.verbose:
            _log_update(step, current_label, ip, instruction, update, used_llm)

        is_return = isinstance(instruction, Return_)
        is_throw = isinstance(instruction, Throw_)
        return_frame = vm.current_frame if (is_return or is_throw) else None

        is_call_dispatch = (
            update.call_push is not None and update.next_label is not None
        )
        if is_call_dispatch:
            _handle_call_dispatch_setup(
                vm,
                instruction,
                update,
                current_label,
                ip,
                type_env=type_env,
                conversion_rules=conversion_rules,
            )
        else:
            apply_update(
                vm, update, type_env=type_env, conversion_rules=conversion_rules
            )

        # Snapshot the VM state after update
        trace_steps.append(
            TraceStep(
                step_index=len(trace_steps),
                block_label=current_label,
                instruction_index=ip,
                instruction=instruction,
                update=update,
                vm_state=copy.deepcopy(vm),
                used_llm=used_llm,
            )
        )

        if is_return or is_throw:
            flow = _handle_return_flow(
                vm, cfg, return_frame, update, config.verbose, step
            )
            if isinstance(flow, _StopExecution):
                break
            current_label, ip = flow

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1

    stats = ExecutionStats(
        steps=step + 1,
        llm_calls=llm_calls + call_resolver.llm_call_count,
        final_heap_objects=vm.heap_count(),
        final_symbolic_count=vm.symbolic_counter,
        closures_captured=len(vm.closures),
    )

    if config.verbose:
        logger.info("(%d steps, %d LLM calls)", stats.steps, stats.llm_calls)

    trace = ExecutionTrace(
        steps=trace_steps,
        stats=stats,
        initial_state=initial_state,
    )

    return (vm, trace)


def build_execution_strategies(
    frontend: Frontend,
    instructions: list[InstructionBase],
    registry: FunctionRegistry,
    lang: Language,
) -> ExecutionStrategies:
    """Build ExecutionStrategies with type inference, overload resolution, and symbol tables.

    Shared by run() and the TUI pipeline to ensure identical execution behaviour.
    """
    conversion_rules = DefaultTypeConversionRules()
    type_resolver = TypeResolver(conversion_rules)
    type_env = infer_types(
        instructions,
        type_resolver,
        type_env_builder=frontend.type_env_builder,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    class_nodes = tuple(
        TypeNode(name=str(cls), parents=tuple(str(p) for p in parents))
        for cls, parents in registry.class_parents.items()
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
        binop_coercion=_binop_coercion_for_language(lang),
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
        field_fallback=_field_fallback_for_language(lang),
        function_scoping=_function_scoping_for_language(lang),
        symbol_table=frontend.symbol_table,
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
        TypeNode(name=str(cls), parents=tuple(str(p) for p in parents))
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


def run_linked(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
    """Execute a LinkedProgram with the given entry point.

    Args:
        linked: Pre-compiled program (single-module or multi-module).
        entry_point: How to enter — EntryPoint.top_level() or EntryPoint.function(pred).
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        backend: LLM backend for interpreter fallback.
        unresolved_call_strategy: Resolution strategy for unknown calls.
    """
    strategies = _build_strategies_from_linked(linked)

    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
    )

    if entry_point.is_top_level:
        vm, exec_stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )
    else:
        # Phase 1: preamble
        module_entry = linked.merged_cfg.entry
        vm, preamble_stats = execute_cfg(
            linked.merged_cfg,
            module_entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )

        # Resolve entry point function via predicate
        func_ref = entry_point.resolve(list(linked.func_symbol_table.values()))
        func_label = _resolve_entry_function(vm, str(func_ref.name), linked.merged_cfg)

        # Phase 2: dispatch into target function
        remaining = max_steps - preamble_stats.steps
        phase2_config = replace(vm_config, max_steps=max(remaining, 0))
        vm, phase2_stats = execute_cfg(
            linked.merged_cfg,
            func_label,
            linked.merged_registry,
            phase2_config,
            strategies,
            vm=vm,
        )

    vm.data_layout = linked.data_layout
    return vm


def run_linked_traced(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> tuple[VMState, ExecutionTrace]:
    """Execute a LinkedProgram and return a trace of execution steps.

    Mirrors run_linked() but uses execute_cfg_traced() instead of execute_cfg()
    and returns both the final VMState and a complete ExecutionTrace.

    For function entry points, performs two-phase execution (preamble + dispatch)
    and concatenates the traces.

    Args:
        linked: Pre-compiled program (single-module or multi-module).
        entry_point: How to enter — EntryPoint.top_level() or EntryPoint.function(pred).
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
    )

    if entry_point.is_top_level:
        vm, trace = execute_cfg_traced(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )
    else:
        # Phase 1: preamble
        module_entry = linked.merged_cfg.entry
        vm, preamble_trace = execute_cfg_traced(
            linked.merged_cfg,
            module_entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )

        # Resolve entry point function via predicate
        func_ref = entry_point.resolve(list(linked.func_symbol_table.values()))
        func_label = _resolve_entry_function(vm, str(func_ref.name), linked.merged_cfg)

        # Phase 2: dispatch into target function
        remaining = max_steps - preamble_trace.stats.steps
        phase2_config = replace(vm_config, max_steps=max(remaining, 0))
        vm, dispatch_trace = execute_cfg_traced(
            linked.merged_cfg,
            func_label,
            linked.merged_registry,
            phase2_config,
            strategies,
            vm=vm,
        )

        # Concatenate traces: renumber dispatch steps with offset, combine stats
        preamble_step_count = len(preamble_trace.steps)
        renumbered_dispatch_steps = [
            replace(step, step_index=step.step_index + preamble_step_count)
            for step in dispatch_trace.steps
        ]

        # Combine stats
        combined_stats = ExecutionStats(
            steps=preamble_trace.stats.steps + dispatch_trace.stats.steps,
            llm_calls=preamble_trace.stats.llm_calls + dispatch_trace.stats.llm_calls,
            final_heap_objects=dispatch_trace.stats.final_heap_objects,
            final_symbolic_count=dispatch_trace.stats.final_symbolic_count,
            closures_captured=preamble_trace.stats.closures_captured
            + dispatch_trace.stats.closures_captured,
        )

        # Build concatenated trace with preamble's initial state
        trace = ExecutionTrace(
            steps=preamble_trace.steps + renumbered_dispatch_steps,
            stats=combined_stats,
            initial_state=preamble_trace.initial_state,
        )

    vm.data_layout = linked.data_layout
    return vm, trace


def run(
    source: str,
    language: str | Language = Language.PYTHON,
    entry_point: EntryPoint = EntryPoint.top_level(),
    backend: str = LLMProvider.CLAUDE,
    max_steps: int = 100,
    verbose: bool = False,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_client: Any = None,  # Any: Optional LLM client injection — see red-dragon-c7y2
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
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
    """
    lang = Language(language)
    pipeline_start = time.perf_counter()
    stats = PipelineStats(
        source_bytes=len(source.encode("utf-8")),
        source_lines=source.count("\n")
        + (1 if source and not source.endswith("\n") else 0),
        language=lang,
        frontend_type=frontend_type,
    )

    # 1. Parse + Lower
    class _StatsObserver:
        """Populates PipelineStats timing fields from frontend callbacks."""

        def __init__(self, target: PipelineStats):
            self._target = target

        def on_parse(self, duration: float) -> None:
            self._target.parse_time = duration

        def on_lower(self, duration: float) -> None:
            self._target.lower_time = duration

    resolved_frontend_type = (
        constants.FRONTEND_COBOL if lang == Language.COBOL else frontend_type
    )
    observer: FrontendObserver = _StatsObserver(stats)
    frontend = get_frontend(
        lang,
        frontend_type=resolved_frontend_type,
        llm_provider=backend,
        llm_client=llm_client,
        observer=observer,
    )
    instructions = frontend.lower(source.encode("utf-8"))

    stats.ir_instruction_count = len(instructions)
    logger.info(
        "Frontend produced %d IR instructions in %.1fms",
        stats.ir_instruction_count,
        (stats.parse_time + stats.lower_time) * 1000,
    )

    if verbose:
        logger.info("═══ IR ═══")
        for inst in instructions:
            logger.info("  %s", inst)
        logger.info("")

    # 2. Build CFG
    t0 = time.perf_counter()
    cfg = build_cfg(instructions)
    stats.cfg_time = time.perf_counter() - t0
    stats.cfg_block_count = len(cfg.blocks)

    if verbose:
        logger.info("═══ CFG ═══")
        logger.info("%s", cfg)

    # 3. Build function registry
    t0 = time.perf_counter()
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    stats.registry_time = time.perf_counter() - t0
    stats.registry_functions = len(registry.func_params)
    stats.registry_classes = len(registry.classes)

    # 4. Build single-module LinkedProgram
    linked = LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=lang,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        data_layout=frontend.data_layout,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )

    # 5. Execute via run_linked
    exec_start = time.perf_counter()
    vm = run_linked(
        linked,
        entry_point=entry_point,
        max_steps=max_steps,
        verbose=verbose,
        backend=backend,
        unresolved_call_strategy=unresolved_call_strategy,
    )
    stats.execution_time = time.perf_counter() - exec_start
    stats.total_time = time.perf_counter() - pipeline_start

    if verbose:
        logger.info("")
        logger.info("%s", stats.report())

    return vm


def _format_val(
    v: Any,
) -> str:  # Any: display boundary — formats all runtime value types
    """Format a value for verbose display."""
    if isinstance(v, TypedValue):
        return _format_val(v.value)
    if isinstance(v, SymbolicValue):
        if v.constraints:
            return f"{v.name} [{', '.join(v.constraints)}]"
        return f"{v.name}" + (f" ({v.type_hint})" if v.type_hint else "")
    if isinstance(v, dict) and v.get("__symbolic__"):
        name = v.get("name", "?")
        constraints = v.get("constraints", [])
        if constraints:
            return f"{name} [{', '.join(str(c) for c in constraints)}]"
        hint = v.get("type_hint", "")
        return f"{name}" + (f" ({hint})" if hint else "")
    if isinstance(v, BoundFuncRef):
        if v.closure_id:
            return f"<function:{v.func_ref.name}@{v.func_ref.label}#{v.closure_id}>"
        return f"<function:{v.func_ref.name}@{v.func_ref.label}>"
    if isinstance(v, ClassRef):
        if v.parents:
            return f"<class:{v.name}@{v.label}:{','.join(str(p) for p in v.parents)}>"
        return f"<class:{v.name}@{v.label}>"
    return repr(v)
