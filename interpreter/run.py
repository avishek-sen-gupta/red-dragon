"""Orchestrator — run() entry point."""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from .ir import Opcode
from .parser import Parser
from .frontend import get_frontend
from .cfg import CFG, build_cfg
from .registry import build_registry, _parse_class_ref, FunctionRegistry
from .executor import _try_execute_locally
from .unresolved_call import (
    SymbolicResolver,
    LLMPlausibleResolver,
    UnresolvedCallResolver,
)
from .vm import (
    VMState,
    SymbolicValue,
    StackFrame,
    StateUpdate,
    ExecutionResult,
    apply_update,
    _deserialize_value,
    _serialize_value,
)
from .run_types import (
    VMConfig,
    ExecutionStats,
    PipelineStats,
    UnresolvedCallStrategy,
)  # noqa: F401 — re-exported for backwards compatibility
from .trace_types import TraceStep, ExecutionTrace
from .backend import get_backend
from . import constants

logger = logging.getLogger(__name__)


def _create_resolver(config: VMConfig) -> UnresolvedCallResolver:
    """Create the appropriate call resolver based on config."""
    if config.unresolved_call_strategy == UnresolvedCallStrategy.LLM:
        from .llm_client import get_llm_client

        llm_client = get_llm_client(provider=config.backend)
        return LLMPlausibleResolver(
            llm_client=llm_client,
            source_language=config.source_language,
        )
    return SymbolicResolver()


class _StopExecution:
    """Sentinel indicating the interpreter should halt."""

    pass


def _find_entry_point(cfg: CFG, entry_point: str) -> str:
    """Resolve the entry point label in the CFG."""
    entry = entry_point or cfg.entry
    if entry in cfg.blocks:
        return entry
    # Try to find a function label matching the entry point
    for label in cfg.blocks:
        if entry in label:
            return label
    raise ValueError(
        f"Entry point '{entry}' not found in CFG. "
        f"Available: {list(cfg.blocks.keys())}"
    )


def _log_update(
    step: int,
    current_label: str,
    ip: int,
    instruction: Any,
    update: StateUpdate,
    used_llm: bool,
):
    """Print verbose step-by-step execution info."""
    tag = "LLM" if used_llm else "local"
    print(f"  [{tag}] {update.reasoning}")
    for reg, val in update.register_writes.items():
        print(f"    {reg} = {_format_val(val)}")
    for var, val in update.var_writes.items():
        print(f"    ${var} = {_format_val(val)}")
    for hw in update.heap_writes:
        print(f"    heap[{hw.obj_addr}].{hw.field} = {_format_val(hw.value)}")
    for obj in update.new_objects:
        print(f"    new {obj.type_hint} @ {obj.addr}")
    if update.next_label:
        print(f"    → {update.next_label}")
    if update.path_condition:
        print(f"    path: {update.path_condition}")
    print()


def _handle_call_dispatch_setup(
    vm: VMState,
    instruction: Any,
    update: StateUpdate,
    current_label: str,
    ip: int,
):
    """Set up the new call frame's return info after call_push + dispatch."""
    call_result_reg = instruction.result_reg
    call_return_label = current_label
    call_return_ip = ip + 1

    apply_update(vm, update)

    new_frame = vm.current_frame
    new_frame.return_label = call_return_label
    new_frame.return_ip = call_return_ip
    new_frame.result_reg = call_result_reg

    # For class constructors, the result_reg was already written
    # (the object address), so we mark it to not overwrite on return
    if instruction.opcode == Opcode.CALL_FUNCTION:
        func_val = vm.call_stack[-2].local_vars.get(instruction.operands[0])
        if func_val and _parse_class_ref(func_val).matched:
            new_frame.result_reg = None  # don't overwrite on return


def _handle_return_flow(
    vm: VMState,
    cfg: CFG,
    return_frame: StackFrame,
    update: StateUpdate,
    verbose: bool,
    step: int,
) -> tuple[str, int] | _StopExecution:
    """Handle RETURN/THROW control flow. Returns new (label, ip) or stop sentinel."""
    if len(vm.call_stack) < 1:
        if verbose:
            print(f"[step {step}] Top-level return/throw. Stopping.")
        return _StopExecution()

    if return_frame.function_name == constants.MAIN_FRAME_NAME:
        if verbose:
            print(f"[step {step}] Top-level return/throw. Stopping.")
        return _StopExecution()

    # Return to caller — write return value to caller's result register
    caller_frame = vm.current_frame
    if return_frame.result_reg and update.return_value is not None:
        caller_frame.registers[return_frame.result_reg] = _deserialize_value(
            update.return_value, vm
        )

    if return_frame.return_label and return_frame.return_label in cfg.blocks:
        new_ip = return_frame.return_ip if return_frame.return_ip is not None else 0
        return (return_frame.return_label, new_ip)

    if verbose:
        print(f"[step {step}] No return label. Stopping.")
    return _StopExecution()


def execute_cfg(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
) -> tuple[VMState, ExecutionStats]:
    """Execute a pre-built CFG from the given entry point.

    Initializes a VM, runs the step loop (local execution + LLM fallback),
    and returns the final VM state plus execution metrics.

    Args:
        cfg: Pre-built control flow graph.
        entry_point: Label of the block to start execution from.
        registry: Pre-built function/class registry.
        config: Execution configuration (backend, max_steps, verbose).

    Returns:
        Tuple of (final VMState, ExecutionStats).
    """
    entry = _find_entry_point(cfg, entry_point)

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=constants.MAIN_FRAME_NAME))

    llm = get_backend(config.backend)
    call_resolver = _create_resolver(config)
    current_label = entry
    ip = 0
    llm_calls = 0
    step = 0

    for step in range(config.max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            if config.verbose:
                print(
                    f"[step {step}] End of '{current_label}', "
                    "no successors. Stopping."
                )
            break

        instruction = block.instructions[ip]

        if config.verbose:
            print(f"[step {step}] {current_label}:{ip}  {instruction}")

        if instruction.opcode == Opcode.LABEL:
            ip += 1
            continue

        result = _try_execute_locally(
            instruction,
            vm,
            cfg=cfg,
            registry=registry,
            current_label=current_label,
            ip=ip,
            call_resolver=call_resolver,
        )
        used_llm = False
        if result.handled:
            update = result.update
        else:
            update = llm.interpret_instruction(instruction, vm)
            used_llm = True
            llm_calls += 1

        if config.verbose:
            _log_update(step, current_label, ip, instruction, update, used_llm)

        is_return = instruction.opcode == Opcode.RETURN
        is_throw = instruction.opcode == Opcode.THROW
        return_frame = vm.current_frame if (is_return or is_throw) else None

        is_call_dispatch = (
            update.call_push is not None and update.next_label is not None
        )
        if is_call_dispatch:
            _handle_call_dispatch_setup(vm, instruction, update, current_label, ip)
        else:
            apply_update(vm, update)

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
        llm_calls=llm_calls,
        final_heap_objects=len(vm.heap),
        final_symbolic_count=vm.symbolic_counter,
        closures_captured=len(vm.closures),
    )

    if config.verbose:
        print(f"\n({stats.steps} steps, {stats.llm_calls} LLM calls)")

    return (vm, stats)


def execute_cfg_traced(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
) -> tuple[VMState, ExecutionTrace]:
    """Execute a pre-built CFG and record a trace of every step.

    Identical to execute_cfg() but deep-copies the VMState after each
    instruction so callers can replay the execution step by step.

    Args:
        cfg: Pre-built control flow graph.
        entry_point: Label of the block to start execution from.
        registry: Pre-built function/class registry.
        config: Execution configuration (backend, max_steps, verbose).

    Returns:
        Tuple of (final VMState, ExecutionTrace with per-step snapshots).
    """
    entry = _find_entry_point(cfg, entry_point)

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=constants.MAIN_FRAME_NAME))
    initial_state = copy.deepcopy(vm)

    llm = get_backend(config.backend)
    call_resolver = _create_resolver(config)
    current_label = entry
    ip = 0
    llm_calls = 0
    step = 0
    trace_steps: list[TraceStep] = []

    for step in range(config.max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            if config.verbose:
                print(
                    f"[step {step}] End of '{current_label}', "
                    "no successors. Stopping."
                )
            break

        instruction = block.instructions[ip]

        if config.verbose:
            print(f"[step {step}] {current_label}:{ip}  {instruction}")

        if instruction.opcode == Opcode.LABEL:
            ip += 1
            continue

        result = _try_execute_locally(
            instruction,
            vm,
            cfg=cfg,
            registry=registry,
            current_label=current_label,
            ip=ip,
            call_resolver=call_resolver,
        )
        used_llm = False
        if result.handled:
            update = result.update
        else:
            update = llm.interpret_instruction(instruction, vm)
            used_llm = True
            llm_calls += 1

        if config.verbose:
            _log_update(step, current_label, ip, instruction, update, used_llm)

        is_return = instruction.opcode == Opcode.RETURN
        is_throw = instruction.opcode == Opcode.THROW
        return_frame = vm.current_frame if (is_return or is_throw) else None

        is_call_dispatch = (
            update.call_push is not None and update.next_label is not None
        )
        if is_call_dispatch:
            _handle_call_dispatch_setup(vm, instruction, update, current_label, ip)
        else:
            apply_update(vm, update)

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
        llm_calls=llm_calls,
        final_heap_objects=len(vm.heap),
        final_symbolic_count=vm.symbolic_counter,
        closures_captured=len(vm.closures),
    )

    if config.verbose:
        print(f"\n({stats.steps} steps, {stats.llm_calls} LLM calls)")

    trace = ExecutionTrace(
        steps=trace_steps,
        stats=stats,
        initial_state=initial_state,
    )

    return (vm, trace)


def run(
    source: str,
    language: str = "python",
    entry_point: str = "",
    backend: str = "claude",
    max_steps: int = 100,
    verbose: bool = False,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_client: Any = None,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
    """End-to-end: parse → lower → CFG → LLM interpret.

    Args:
        source: Raw source code string.
        language: Source language name.
        entry_point: Entry point label or function name.
        backend: LLM backend for interpreter fallback ("claude" or "openai").
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        frontend_type: "deterministic" (tree-sitter) or "llm".
        llm_client: Pre-built LLMClient for DI/testing (used by LLM frontend).
        unresolved_call_strategy: Resolution strategy for unknown calls.
    """
    pipeline_start = time.perf_counter()
    stats = PipelineStats(
        source_bytes=len(source.encode("utf-8")),
        source_lines=source.count("\n")
        + (1 if source and not source.endswith("\n") else 0),
        language=language,
        frontend_type=frontend_type,
    )

    # 1. Parse + Lower
    t0 = time.perf_counter()
    if frontend_type in (constants.FRONTEND_LLM, constants.FRONTEND_CHUNKED_LLM):
        # LLM frontend: skip tree-sitter, send source directly
        frontend = get_frontend(
            language,
            frontend_type=frontend_type,
            llm_provider=backend,
            llm_client=llm_client,
        )
        t1 = time.perf_counter()
        stats.parse_time = t1 - t0  # no parse step for LLM frontend
        instructions = frontend.lower(None, source.encode("utf-8"))
        stats.lower_time = time.perf_counter() - t1
    else:
        # Deterministic frontend: parse with tree-sitter first
        from .parser import TreeSitterParserFactory

        tree = Parser(TreeSitterParserFactory()).parse(source, language)
        t1 = time.perf_counter()
        stats.parse_time = t1 - t0
        frontend = get_frontend(language, frontend_type=frontend_type)
        instructions = frontend.lower(tree, source.encode("utf-8"))
        stats.lower_time = time.perf_counter() - t1

    stats.ir_instruction_count = len(instructions)
    logger.info(
        "Frontend produced %d IR instructions in %.1fms",
        stats.ir_instruction_count,
        (stats.parse_time + stats.lower_time) * 1000,
    )

    if verbose:
        print("═══ IR ═══")
        for inst in instructions:
            print(f"  {inst}")
        print()

    # 3. Build CFG
    t0 = time.perf_counter()
    cfg = build_cfg(instructions)
    stats.cfg_time = time.perf_counter() - t0
    stats.cfg_block_count = len(cfg.blocks)

    if verbose:
        print("═══ CFG ═══")
        print(cfg)

    # 4. Pick entry
    entry = _find_entry_point(cfg, entry_point)

    # 4b. Build function registry
    t0 = time.perf_counter()
    registry = build_registry(instructions, cfg)
    stats.registry_time = time.perf_counter() - t0
    stats.registry_functions = len(registry.func_params)
    stats.registry_classes = len(registry.classes)

    # 5. Execute via extract
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=language,
        unresolved_call_strategy=unresolved_call_strategy,
    )
    exec_start = time.perf_counter()
    vm, exec_stats = execute_cfg(cfg, entry, registry, vm_config)
    stats.execution_time = time.perf_counter() - exec_start

    stats.execution_steps = exec_stats.steps
    stats.llm_calls = exec_stats.llm_calls
    stats.final_heap_objects = exec_stats.final_heap_objects
    stats.final_symbolic_count = exec_stats.final_symbolic_count
    stats.closures_captured = exec_stats.closures_captured
    stats.total_time = time.perf_counter() - pipeline_start

    if verbose:
        print()
        print(stats.report())

    return vm


def _format_val(v: Any) -> str:
    """Format a value for verbose display."""
    if isinstance(v, dict) and v.get("__symbolic__"):
        name = v.get("name", "?")
        constraints = v.get("constraints", [])
        if constraints:
            return f"{name} [{', '.join(str(c) for c in constraints)}]"
        hint = v.get("type_hint", "")
        return f"{name}" + (f" ({hint})" if hint else "")
    if isinstance(v, SymbolicValue):
        if v.constraints:
            return f"{v.name} [{', '.join(v.constraints)}]"
        return f"{v.name}" + (f" ({v.type_hint})" if v.type_hint else "")
    return repr(v)
