"""Convert internal RedDragon types to JSON-serializable dicts for MCP tool responses."""

from __future__ import annotations

from typing import Any

from interpreter.interprocedural.types import (
    FieldEndpoint,
    FlowEndpoint,
    ReturnEndpoint,
    VariableEndpoint,
)
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import StateUpdate


def format_typed_value(tv: Any) -> Any:
    """Convert a TypedValue to a JSON-friendly representation."""
    if isinstance(tv, (int, float, str, bool)):
        return tv
    if not isinstance(tv, TypedValue):
        return str(tv)
    if isinstance(tv.value, (int, float, str, bool)):
        return tv.value
    return {"value": str(tv.value), "type": str(tv.type)}


def format_flow_endpoint(ep: FlowEndpoint) -> dict[str, str]:
    """Convert a FlowEndpoint to a JSON dict."""
    if isinstance(ep, VariableEndpoint):
        return {"name": ep.name, "type": "variable"}
    if isinstance(ep, ReturnEndpoint):
        return {"function": ep.function.label, "type": "return"}
    if isinstance(ep, FieldEndpoint):
        return {"base": ep.base.name, "field": ep.field, "type": "field"}
    return {"value": str(ep), "type": "unknown"}


def format_chain_node(node) -> dict:
    """Convert a ChainNode tree to nested JSON."""
    return {
        "label": node.label,
        "children": [format_chain_node(c) for c in node.children],
    }


def format_state_update(update: StateUpdate) -> dict[str, Any]:
    """Convert a StateUpdate to a dict with only non-empty fields."""
    result: dict[str, Any] = {}
    if update.register_writes:
        result["registers"] = {
            k: format_typed_value(v) for k, v in update.register_writes.items()
        }
    if update.var_writes:
        result["variables"] = {
            k: format_typed_value(v) for k, v in update.var_writes.items()
        }
    if update.heap_writes:
        result["heap_writes"] = [
            {
                "address": hw.obj_addr,
                "field": hw.field,
                "value": format_typed_value(hw.value),
            }
            for hw in update.heap_writes
        ]
    if update.new_objects:
        result["new_objects"] = [
            {"address": no.addr, "type_hint": str(no.type_hint)}
            for no in update.new_objects
        ]
    if update.next_label:
        result["next_block"] = str(update.next_label)
    if update.call_push:
        result["call_push"] = update.call_push.function_name
    if update.call_pop:
        result["call_pop"] = True
    if update.reasoning:
        result["reasoning"] = update.reasoning
    return result


def format_vm_state_frame(frame) -> dict[str, Any]:
    """Convert a StackFrame to a JSON dict."""
    return {
        "function": frame.function_name,
        "variables": {k: format_typed_value(v) for k, v in frame.local_vars.items()},
        "registers": {k: format_typed_value(v) for k, v in frame.registers.items()},
    }
