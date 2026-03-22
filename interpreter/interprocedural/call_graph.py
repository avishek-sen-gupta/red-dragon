"""Call graph construction with Class Hierarchy Analysis (CHA) for method dispatch."""

from __future__ import annotations

import logging

from interpreter.cfg_types import CFG
from interpreter.ir import Opcode
from interpreter.registry import FunctionRegistry
from interpreter import constants
from interpreter.interprocedural.types import (
    CallGraph,
    CallSite,
    FunctionEntry,
    InstructionLocation,
)

logger = logging.getLogger(__name__)

CALL_OPCODES = frozenset(
    {Opcode.CALL_FUNCTION, Opcode.CALL_METHOD, Opcode.CALL_UNKNOWN}
)


def build_function_entries(
    cfg: CFG, registry: FunctionRegistry
) -> dict[str, FunctionEntry]:
    """Create one FunctionEntry per registered function."""
    return {
        label: FunctionEntry(label=label, params=tuple(params))
        for label, params in registry.func_params.items()
    }


def _build_block_to_function(
    cfg: CFG, function_entries: dict[str, FunctionEntry]
) -> dict[str, FunctionEntry]:
    """Map each block label to the FunctionEntry that owns it.

    Strategy: walk blocks in order. When we hit a block whose label is a known
    function entry, set current_function. All subsequent blocks belong to that
    function until we hit the next function entry.
    """
    block_to_func: dict[str, FunctionEntry] = {}
    current_func: FunctionEntry | None = None

    for label in cfg.blocks:
        if label in function_entries:
            current_func = function_entries[label]
        if current_func is not None:
            block_to_func[label] = current_func

    return block_to_func


def _resolve_call_function_callees(
    target_label: str, function_entries: dict[str, FunctionEntry]
) -> frozenset[FunctionEntry]:
    """Resolve a CALL_FUNCTION target to its callee set (0 or 1)."""
    entry = function_entries.get(target_label)
    if entry is not None:
        return frozenset({entry})
    return frozenset()


def _resolve_call_method_callees_cha(
    method_name: str,
    registry: FunctionRegistry,
    function_entries: dict[str, FunctionEntry],
) -> frozenset[FunctionEntry]:
    """CHA: collect all classes that define this method, return their FunctionEntries."""
    callees: list[FunctionEntry] = []
    for _class_name, methods in registry.class_methods.items():
        labels = methods.get(method_name, [])
        callees.extend(
            function_entries[lbl] for lbl in labels if lbl in function_entries
        )
    return frozenset(callees)


def build_call_graph(cfg: CFG, registry: FunctionRegistry) -> CallGraph:
    """Scan CFG for CALL_* instructions and build the call graph."""
    function_entries = build_function_entries(cfg, registry)
    block_to_func = _build_block_to_function(cfg, function_entries)
    functions = frozenset(function_entries.values())

    call_sites: list[CallSite] = []

    for label, block in cfg.blocks.items():
        caller = block_to_func.get(label)
        if caller is None:
            continue

        for idx, inst in enumerate(block.instructions):
            if inst.opcode not in CALL_OPCODES:
                continue

            location = InstructionLocation(block_label=label, instruction_index=idx)

            if inst.opcode == Opcode.CALL_FUNCTION:
                target_label = str(inst.operands[0])
                callees = _resolve_call_function_callees(target_label, function_entries)
                arg_operands = tuple(str(op) for op in inst.operands[1:])

            elif inst.opcode == Opcode.CALL_METHOD:
                # operands: [object_reg, method_name, arg1, arg2, ...]
                method_name = str(inst.operands[1])
                callees = _resolve_call_method_callees_cha(
                    method_name, registry, function_entries
                )
                arg_operands = tuple(str(op) for op in inst.operands[2:])

            else:  # CALL_UNKNOWN
                callees = frozenset()
                arg_operands = tuple(str(op) for op in inst.operands)

            site = CallSite(
                caller=caller,
                location=location,
                callees=callees,
                arg_operands=arg_operands,
            )
            call_sites.append(site)
            logger.debug(
                "CallSite: %s calls %s at %s",
                caller.label,
                [c.label for c in callees],
                location,
            )

    return CallGraph(functions=functions, call_sites=frozenset(call_sites))
