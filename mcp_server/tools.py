"""Tool handler implementations for the RedDragon MCP server.

Each handle_* function is a pure function that returns a JSON-serializable dict.
The server module registers these as MCP tools.
"""

from __future__ import annotations

import logging
from typing import Any

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.summaries import extract_sub_cfg
from interpreter.interprocedural.types import (
    FunctionEntry,
    ReturnEndpoint,
    FieldEndpoint,
    VariableEndpoint,
)
from interpreter.registry import build_registry
from mcp_server.formatting import (
    format_chain_node,
    format_flow_endpoint,
    format_state_update,
    format_typed_value,
    format_vm_state_frame,
)
from mcp_server.session import Session, get_session, load_session, set_session
from viz.panels.dataflow_graph_panel import (
    ChainNode,
    build_call_chain,
    find_top_level_call_sites,
)
from viz.panels.dataflow_summary_panel import (
    build_function_callers,
    build_function_callees,
    merge_flows_for_function,
    render_endpoint,
)

logger = logging.getLogger(__name__)


def _run_analysis(source: str, language: str):
    """Run pipeline + interprocedural analysis. Returns (cfg, registry, interprocedural)."""
    lang = Language(language)
    frontend = get_frontend(lang)
    ir = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(ir)
    registry = build_registry(
        ir,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    interprocedural = analyze_interprocedural(cfg, registry)
    return cfg, registry, interprocedural, ir


def _find_function_entry(
    name: str,
    interprocedural,
) -> FunctionEntry:
    """Find a FunctionEntry by name or label. Raises ValueError if not found."""
    for f in interprocedural.call_graph.functions:
        if f.label == name:
            return f
    # Try name-based lookup: "add" → "func_add_0"
    for f in interprocedural.call_graph.functions:
        if f.label.starts_with("func_") and "_" in str(f.label)[5:]:
            func_name = f.label.extract_name("func_")
            if func_name == name:
                return f
    raise ValueError(f"Function not found: {name}")


# ---------------------------------------------------------------------------
# Analysis tools (stateless)
# ---------------------------------------------------------------------------


def handle_analyze_program(source: str, language: str) -> dict[str, Any]:
    """Run full pipeline + analysis, return program overview."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
    except Exception as e:
        return {"error": str(e)}

    call_graph = interprocedural.call_graph
    return {
        "functions": [
            {"label": str(f.label), "params": list(f.params)}
            for f in sorted(call_graph.functions, key=lambda f: str(f.label))
        ],
        "call_graph": [
            {"caller": s.caller.label, "callees": sorted(c.label for c in s.callees)}
            for s in call_graph.call_sites
        ],
        "summary_counts": {
            str(f.label): len(merge_flows_for_function(f, interprocedural.summaries))
            for f in call_graph.functions
        },
        "whole_program_edge_count": sum(
            len(dsts) for dsts in interprocedural.whole_program_graph.values()
        ),
        "ir_instruction_count": len(ir),
        "cfg_block_count": len(cfg.blocks),
    }


def handle_get_function_summary(
    source: str,
    language: str,
    function_name: str,
) -> dict[str, Any]:
    """Return param→return/field flows for a specific function."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
        func_entry = _find_function_entry(function_name, interprocedural)
    except Exception as e:
        return {"error": str(e)}

    call_graph = interprocedural.call_graph
    flows = merge_flows_for_function(func_entry, interprocedural.summaries)

    def _flow_type(src, dst) -> str:
        if isinstance(dst, ReturnEndpoint):
            return "param_to_return"
        if isinstance(dst, FieldEndpoint):
            return "param_to_field"
        return "other"

    return {
        "function": str(func_entry.label),
        "params": list(func_entry.params),
        "callers": sorted(build_function_callers(func_entry, call_graph)),
        "callees": sorted(build_function_callees(func_entry, call_graph)),
        "flows": [
            {
                "source": render_endpoint(src),
                "destination": render_endpoint(dst),
                "type": _flow_type(src, dst),
            }
            for src, dst in sorted(flows, key=lambda f: render_endpoint(f[0]))
        ],
    }


def handle_get_call_chain(
    source: str,
    language: str,
    function_name: str | None = None,
) -> dict[str, Any]:
    """Build call-chain tree from top-level calls or a specific function."""
    try:
        cfg, registry, interprocedural, ir = _run_analysis(source, language)
    except Exception as e:
        return {"error": str(e)}

    if function_name:
        try:
            func_entry = _find_function_entry(function_name, interprocedural)
        except ValueError as e:
            return {"error": str(e)}
        nodes = build_call_chain(
            func_entry,
            interprocedural.call_graph,
            interprocedural.summaries,
            cfg,
            set(),
        )
        return {
            "root": f"{func_entry.label}({', '.join(func_entry.params)})",
            "children": [format_chain_node(n) for n in nodes],
        }

    top_calls = find_top_level_call_sites(cfg, interprocedural.call_graph)
    chains = []
    func_by_label = {f.label: f for f in interprocedural.call_graph.functions}
    for call in top_calls:
        callee = func_by_label.get(call.callee_label)
        if not callee:
            callee = next(
                (
                    f
                    for f in interprocedural.call_graph.functions
                    if f.label.starts_with("func_")
                    and f.label.extract_name("func_") == call.callee_label
                ),
                None,
            )
        if callee:
            nodes = build_call_chain(
                callee,
                interprocedural.call_graph,
                interprocedural.summaries,
                cfg,
                set(),  # fresh visited per chain
            )
            chains.append(
                {
                    "root": f"{call.callee_label}({', '.join(call.arg_operands)}) → {call.result_var}",
                    "children": [format_chain_node(n) for n in nodes],
                }
            )

    return {"chains": chains}


# ---------------------------------------------------------------------------
# Execution tools (stateful)
# ---------------------------------------------------------------------------


def handle_load_program(
    source: str,
    language: str,
    max_steps: int = 300,
) -> dict[str, Any]:
    """Load, compile, execute, and analyze a program."""
    try:
        session = load_session(source, language, max_steps)
    except Exception as e:
        return {"error": str(e)}

    set_session(session)

    return {
        "functions": sorted(
            str(f.label) for f in session.interprocedural.call_graph.functions
        ),
        "ir_instruction_count": len(session.ir),
        "cfg_block_count": len(session.cfg.blocks),
        "entry_block": session.cfg.entry,
        "total_steps": len(session.trace.steps),
        "max_steps": max_steps,
    }


def handle_step(count: int = 1) -> dict[str, Any]:
    """Advance through the pre-recorded execution trace."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    trace = session.trace
    remaining = len(trace.steps) - session.step_index
    actual_count = min(count, remaining)

    steps_data = []
    for i in range(actual_count):
        step = trace.steps[session.step_index + i]
        steps_data.append(
            {
                "index": step.step_index,
                "block": step.block_label,
                "instruction": str(step.instruction),
                "deltas": format_state_update(step.update),
            }
        )

    session.step_index += actual_count
    done = session.step_index >= len(trace.steps)

    current_step = (
        trace.steps[session.step_index - 1] if session.step_index > 0 else None
    )
    return {
        "steps_executed": actual_count,
        "steps": steps_data,
        "current_block": current_step.block_label if current_step else "",
        "current_index": session.step_index,
        "done": done,
    }


def handle_run_to_end() -> dict[str, Any]:
    """Advance to the end of the pre-recorded trace."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    remaining = len(session.trace.steps) - session.step_index
    session.step_index = len(session.trace.steps)

    # Return final VM state
    frame = session.vm.current_frame
    return {
        "steps_executed": remaining,
        "variables": {
            str(k): format_typed_value(v) for k, v in frame.local_vars.items()
        },
        "heap": {
            addr: {
                "type": str(obj.type_hint),
                "fields": {k: format_typed_value(v) for k, v in obj.fields.items()},
            }
            for addr, obj in session.vm.heap_items()
        },
        "done": True,
    }


def handle_get_state() -> dict[str, Any]:
    """Return current VM state snapshot."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    # Get state from the trace at current step_index
    if session.step_index > 0:
        vm_state = session.trace.steps[session.step_index - 1].vm_state
    else:
        vm_state = session.trace.initial_state

    return {
        "step_index": session.step_index,
        "current_block": (
            session.trace.steps[session.step_index - 1].block_label
            if session.step_index > 0
            else session.cfg.entry
        ),
        "current_instruction_index": (
            session.trace.steps[session.step_index - 1].instruction_index
            if session.step_index > 0
            else 0
        ),
        "call_stack": [format_vm_state_frame(f) for f in vm_state.call_stack],
        "heap": {
            addr: {
                "type": str(obj.type_hint),
                "fields": {k: format_typed_value(v) for k, v in obj.fields.items()},
            }
            for addr, obj in vm_state.heap_items()
        },
    }


def handle_get_ir(function_name: str | None = None) -> dict[str, Any]:
    """Return IR instructions, optionally filtered to one function."""
    try:
        session = get_session()
    except RuntimeError as e:
        return {"error": str(e)}

    cfg = session.cfg

    if function_name:
        try:
            func_entry = _find_function_entry(function_name, session.interprocedural)
        except ValueError as e:
            return {"error": str(e)}
        sub_cfg = extract_sub_cfg(cfg, func_entry)
        cfg = sub_cfg

    return {
        "blocks": [
            {
                "label": label,
                "successors": list(block.successors),
                "instructions": [str(inst) for inst in block.instructions],
            }
            for label, block in cfg.blocks.items()
        ],
    }


def handle_load_project(
    entry_file: str,
    language: str,
) -> dict[str, Any]:
    """Load and analyze a multi-file project.

    Discovers imports from the entry file, resolves dependencies,
    compiles all modules, links them, and runs interprocedural analysis.

    Args:
        entry_file: Path to the entry point file (e.g. main.py).
        language: Source language (e.g. "python", "javascript").

    Returns:
        Summary of the loaded project: modules, import graph, functions, classes.
    """
    from pathlib import Path

    from interpreter.project.compiler import compile_project
    from interpreter.interprocedural.analyze import analyze_interprocedural

    try:
        lang = Language(language)
        entry_path = Path(entry_file)

        linked = compile_project(entry_path, lang)

        interprocedural = analyze_interprocedural(
            linked.merged_cfg, linked.merged_registry
        )

        # Store key data — note: for project mode we don't run execution,
        # so we skip trace/vm session storage and just return the analysis.

        return {
            "modules": len(linked.modules),
            "entry": str(linked.entry_module),
            "import_graph": {
                str(k): [str(v) for v in vs] for k, vs in linked.import_graph.items()
            },
            "unresolved_imports": len(linked.unresolved_imports),
            "cfg_blocks": len(linked.merged_cfg.blocks),
            "functions": sorted(
                str(f.label) for f in interprocedural.call_graph.functions
            ),
            "classes": sorted(str(k) for k in linked.merged_registry.classes.keys()),
        }
    except Exception as e:
        logger.exception("handle_load_project failed")
        return {"error": str(e)}
