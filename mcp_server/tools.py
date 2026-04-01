"""Tool handler implementations for the RedDragon MCP server.

Each handle_* function is a pure function that returns a JSON-serializable dict.
The server module registers these as MCP tools.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any, get_type_hints

from interpreter.cfg import build_cfg
from interpreter.instructions import _TO_TYPED, InstructionBase
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.summaries import extract_sub_cfg
from interpreter.interprocedural.types import (
    FunctionEntry,
    InterproceduralResult,
    ReturnEndpoint,
    FieldEndpoint,
    VariableEndpoint,
)
from interpreter.registry import FunctionRegistry, build_registry
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


def _run_analysis(
    source: str, language: str
) -> tuple[CFG, FunctionRegistry, InterproceduralResult, list[InstructionBase]]:
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
    interprocedural: InterproceduralResult,
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
        "call_stack": [format_vm_state_frame(f) for f in vm_state.call_stack],  # type: ignore[union-attr]  # vm_state is non-None: load_session always populates initial_state
        "heap": {
            addr: {
                "type": str(obj.type_hint),
                "fields": {k: format_typed_value(v) for k, v in obj.fields.items()},
            }
            for addr, obj in vm_state.heap_items()  # type: ignore[union-attr]  # same as above
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

    from interpreter.project.compiler import compile_directory
    from interpreter.interprocedural.analyze import analyze_interprocedural

    try:
        lang = Language(language)
        entry_path = Path(entry_file)

        linked = compile_directory(entry_path.parent, lang)

        interprocedural = analyze_interprocedural(
            linked.merged_cfg, linked.merged_registry
        )

        # Store key data — note: for project mode we don't run execution,
        # so we skip trace/vm session storage and just return the analysis.

        return {
            "modules": len(linked.modules),
            "language": str(linked.language.value),
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


# ---------------------------------------------------------------------------
# Opcode catalogue
# ---------------------------------------------------------------------------


def _type_str(t: object) -> str:
    """Return a human-readable type name for MCP consumers."""
    if isinstance(t, type):
        return t.__name__
    # Strip module prefixes from generic alias strings (e.g. interpreter.ir.CodeLabel -> CodeLabel)
    return re.sub(r"[\w\.]*\.(\w+)", r"\1", str(t))


_OPCODE_CATEGORIES: dict[str, str] = {
    "CONST": "variables",
    "LOAD_VAR": "variables",
    "DECL_VAR": "variables",
    "STORE_VAR": "variables",
    "SYMBOLIC": "variables",
    "BINOP": "arithmetic",
    "UNOP": "arithmetic",
    "CALL_FUNCTION": "calls",
    "CALL_METHOD": "calls",
    "CALL_UNKNOWN": "calls",
    "CALL_CTOR": "calls",
    "LOAD_FIELD": "fields_and_indices",
    "STORE_FIELD": "fields_and_indices",
    "LOAD_FIELD_INDIRECT": "fields_and_indices",
    "LOAD_INDEX": "fields_and_indices",
    "STORE_INDEX": "fields_and_indices",
    "LABEL": "control_flow",
    "BRANCH": "control_flow",
    "BRANCH_IF": "control_flow",
    "RETURN": "control_flow",
    "THROW": "control_flow",
    "TRY_PUSH": "control_flow",
    "TRY_POP": "control_flow",
    "NEW_OBJECT": "heap",
    "NEW_ARRAY": "heap",
    "ALLOC_REGION": "memory",
    "LOAD_REGION": "memory",
    "WRITE_REGION": "memory",
    "ADDRESS_OF": "memory",
    "LOAD_INDIRECT": "memory",
    "STORE_INDIRECT": "memory",
    "SET_CONTINUATION": "continuations",
    "RESUME_CONTINUATION": "continuations",
}

_OPCODE_NOTES: dict[str, str] = {
    "CONST": (
        "value holds a Python literal: int, float, str, bool, None, or a list for "
        "array literals. result_reg receives the boxed value. Used for every literal "
        "expression in every frontend."
    ),
    "LOAD_VAR": (
        "Reads the variable named by name from the current frame's variable store. "
        "If the variable is absent from the current frame, the VM walks up the scope "
        "chain until it finds a frame that owns it. result_reg receives the value."
    ),
    "DECL_VAR": (
        "Declares name in the *current* frame and assigns value_reg to it. "
        "Deliberately shadows any outer-scope variable with the same name. "
        "result_reg is unused (NO_REGISTER). Use STORE_VAR for subsequent assignments."
    ),
    "STORE_VAR": (
        "Assigns value_reg to an already-declared variable named name. Unlike "
        "DECL_VAR, STORE_VAR walks up the scope chain to find the nearest frame that "
        "owns name and writes there. result_reg is unused."
    ),
    "SYMBOLIC": (
        "Placeholder instruction emitted for function parameters before VM execution. "
        "hint is a display name only and carries no runtime meaning. Any SYMBOLIC "
        "remaining at execution time indicates an unresolved parameter value. "
        "result_reg receives the symbolic register."
    ),
    "BINOP": (
        "Applies a binary operator to registers left and right; result lands in "
        "result_reg. operator is a BinopKind: ADD, SUB, MUL, DIV, MOD, EQ, NEQ, LT, "
        "LTE, GT, GTE, AND, OR, BITAND, BITOR, BITXOR, SHL, SHR. Integer and float "
        "operands are both accepted — the VM does not distinguish at the IR level. "
        "Comparison operators produce a boolean-valued register."
    ),
    "UNOP": (
        "Applies a unary operator to operand; result lands in result_reg. operator is "
        "a UnopKind: NEG (arithmetic negation), NOT (boolean negation), BITNOT "
        "(bitwise complement)."
    ),
    "CALL_FUNCTION": (
        "Calls the function named func_name with positional arguments in args. Each "
        "element of args is either a Register (normal argument) or a SpreadArguments "
        "wrapper (for *args splat). result_reg receives the return value; NO_REGISTER "
        "if the call is for side effects only. The callee must be resolvable in the "
        "function registry."
    ),
    "CALL_METHOD": (
        "Dispatches a method call dynamically. obj_reg holds the receiver object; "
        "method_name is the FieldName of the method. The VM looks up method_name on "
        "the object's class at runtime. result_reg receives the return value. Used for "
        "all object method calls across all languages."
    ),
    "CALL_UNKNOWN": (
        "Calls a first-class callable value stored in target_reg. Used for closures, "
        "higher-order functions, callbacks, and any call where the callee cannot be "
        "resolved at IR-lowering time. result_reg receives the return value."
    ),
    "CALL_CTOR": (
        "Allocates a new object of type type_hint and invokes its constructor. "
        "Distinct from CALL_FUNCTION because constructor semantics require the VM to "
        "initialise 'self' before dispatch. result_reg receives the newly constructed "
        "object. type_hint is the TypeExpr describing the class."
    ),
    "LOAD_FIELD": (
        "Reads field field_name from the object in obj_reg. result_reg receives the "
        "value. Raises a runtime error if the field does not exist on the object. "
        "Used for attribute access (obj.field) in all object-oriented frontends."
    ),
    "STORE_FIELD": (
        "Writes value_reg into field field_name on the object in obj_reg. Creates the "
        "field if it does not already exist (duck-typed object model). result_reg is "
        "unused. Used for attribute assignment (obj.field = value)."
    ),
    "LOAD_FIELD_INDIRECT": (
        "Like LOAD_FIELD but the field name is itself a runtime value in name_reg "
        "rather than a compile-time constant. Used for computed property access such "
        "as obj[expr] in property-bag patterns and dynamic dispatch tables."
    ),
    "LOAD_INDEX": (
        "Reads arr_reg[index_reg]. Supports lists, dicts, strings, and any object "
        "whose runtime type provides __getitem__ semantics in the VM's builtin layer. "
        "result_reg receives the element."
    ),
    "STORE_INDEX": (
        "Writes value_reg to arr_reg[index_reg]. Supports lists and dicts. "
        "result_reg is unused. Used for indexed assignment (arr[i] = v)."
    ),
    "LOAD_INDIRECT": (
        "Dereferences the Pointer value in ptr_reg and places the pointed-to value "
        "in result_reg. Used for C- and Pascal-style pointer semantics. The pointer "
        "must have been created by ADDRESS_OF."
    ),
    "STORE_INDIRECT": (
        "Writes value_reg to the memory address held in the Pointer in ptr_reg. "
        "result_reg is unused. Paired with ADDRESS_OF and LOAD_INDIRECT for pointer "
        "read-modify-write patterns."
    ),
    "ADDRESS_OF": (
        "Takes the address of the variable named var_name and stores a Pointer object "
        "in result_reg. The Pointer can later be passed to LOAD_INDIRECT or "
        "STORE_INDIRECT. Used to emulate pass-by-reference and C pointer semantics."
    ),
    "NEW_OBJECT": (
        "Allocates an empty heap object (HeapObject) tagged with type_hint. "
        "result_reg receives the object. Does NOT call a constructor — use CALL_CTOR "
        "for construction with initialisation. type_hint is a TypeExpr and may be "
        "UNKNOWN for dynamically-typed languages."
    ),
    "NEW_ARRAY": (
        "Allocates a new list of size_reg elements (initialised to None). type_hint "
        "is optional and may be UNKNOWN. result_reg receives the list. Used for "
        "fixed-size array allocation in statically-typed frontends; dynamically-typed "
        "frontends typically emit CONST with a list literal instead."
    ),
    "LABEL": (
        "Pseudo-instruction marking a basic block entry point. label holds the "
        "CodeLabel that other instructions branch to. Carries no runtime action — the "
        "VM uses LABEL instructions only during CFG construction. Every basic block "
        "begins with exactly one LABEL."
    ),
    "BRANCH": (
        "Unconditional jump to the target in label. Control never falls through to "
        "the next instruction in the flat IR list. Used to close a basic block that "
        "ends with a jump (loop back-edge, else/end-if merge)."
    ),
    "BRANCH_IF": (
        "Conditional branch on cond_reg. Jumps to branch_targets[0] if cond_reg is "
        "truthy, otherwise to branch_targets[1]. Exactly two branch targets are "
        "required. Used for if/else, while, and ternary expressions."
    ),
    "RETURN": (
        "Returns value_reg to the caller and pops the current stack frame. If "
        "value_reg is NO_REGISTER, the function returns None implicitly. Every "
        "function must have at least one RETURN on every exit path."
    ),
    "THROW": (
        "Raises value_reg as an exception and begins stack unwinding. The VM searches "
        "up the call stack for a matching TRY_PUSH handler. If none is found, the "
        "program terminates with an unhandled exception."
    ),
    "TRY_PUSH": (
        "Pushes an exception handler onto the VM's exception stack. catch_labels is "
        "a tuple of CodeLabel, one per catch clause in source order. finally_label "
        "is the finally block entry point (NO_LABEL if the try has no finally). "
        "end_label marks the end of the entire try/catch/finally construct. Must be "
        "paired with TRY_POP on the non-exception exit path."
    ),
    "TRY_POP": (
        "Pops the top exception handler from the VM's exception stack. Emitted at "
        "the end of a try block on the normal (non-exception) execution path. Every "
        "TRY_PUSH must have exactly one corresponding TRY_POP."
    ),
    "ALLOC_REGION": (
        "Allocates a raw memory region of size_reg bytes and returns an opaque region "
        "handle in result_reg. Used to emulate fixed-size structs (Pascal records, C "
        "structs). The region is accessed via LOAD_REGION and WRITE_REGION using byte "
        "offsets."
    ),
    "LOAD_REGION": (
        "Reads length bytes from the region in region_reg starting at byte offset "
        "offset_reg. result_reg receives the extracted value. length is an integer "
        "literal (not a register) representing the field width in bytes."
    ),
    "WRITE_REGION": (
        "Writes value_reg into region_reg at byte offset offset_reg for length bytes. "
        "length is an integer literal. result_reg is unused. Paired with ALLOC_REGION "
        "and LOAD_REGION for struct field access."
    ),
    "SET_CONTINUATION": (
        "Registers a named continuation re-entry point. name is a ContinuationName; "
        "target_label is the CodeLabel the VM will jump to when the continuation is "
        "resumed. Used to implement yield, coroutines, generators, and iterator "
        "protocols across multiple languages."
    ),
    "RESUME_CONTINUATION": (
        "Transfers control to the continuation registered under name. Paired with "
        "SET_CONTINUATION. Used to resume a suspended generator or coroutine from the "
        "point where SET_CONTINUATION was executed."
    ),
}


def handle_list_opcodes() -> dict[str, Any]:
    """Return all IR opcodes with descriptions, categories, fields, and notes."""
    entries = []
    for opcode, builder in _TO_TYPED.items():
        hints = get_type_hints(builder)
        cls = hints["return"]
        fields = [
            {"name": f.name, "type": _type_str(get_type_hints(cls).get(f.name, f.type))}
            for f in dataclasses.fields(cls)
            if f.name != "source_location"
        ]
        entries.append(
            {
                "name": opcode.value,
                "category": _OPCODE_CATEGORIES[opcode.value],
                "description": (cls.__doc__ or "").strip(),
                "fields": fields,
                "notes": _OPCODE_NOTES[opcode.value],
            }
        )
    return {"opcodes": sorted(entries, key=lambda e: e["name"])}
