"""Deserialize RedDragon IR + VM state from a JSON export file.

Usage:
    poetry run python experiments/legacy_ir_export/deserialize_ir.py <json_file>

Reconstructs:
    - Typed IR instructions via the IRInstruction() factory
    - CFG from reconstructed instructions
    - Function registry
    - VM state (if execution succeeded during export)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.instructions import InstructionBase
from interpreter.ir import (
    CodeLabel,
    IRInstruction,
    NO_LABEL,
    NO_REGISTER,
    NO_SOURCE_LOCATION,
    Opcode,
    SourceLocation,
)
from interpreter.register import Register
from interpreter.vm.vm_types import (
    ClosureEnvironment,
    HeapObject,
    StackFrame,
    SymbolicValue,
    VMState,
)
from interpreter.address import Address
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.types.type_expr import UNKNOWN, scalar
from interpreter.constants import TypeName
from interpreter.types.typed_value import typed

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Instruction deserialization ────────────────────────────────────


def _deserialize_source_location(loc_dict: dict | None) -> SourceLocation:
    """Reconstruct a SourceLocation from its dict form."""
    if loc_dict is None:
        return NO_SOURCE_LOCATION
    return SourceLocation(
        start_line=loc_dict["start_line"],
        start_col=loc_dict["start_col"],
        end_line=loc_dict["end_line"],
        end_col=loc_dict["end_col"],
    )


def _deserialize_operand(val: Any) -> Any:
    """Reconstruct an operand from its JSON form."""
    if isinstance(val, dict):
        typ = val.get("__type__")
        if typ == "Register":
            return Register(val["value"])
        if typ == "SpreadArguments":
            from interpreter.ir import SpreadArguments

            return SpreadArguments(register=Register(val["register"]))
        if typ == "CodeLabel":
            return CodeLabel(val["value"])
        if typ == "list":
            return [_deserialize_operand(item) for item in val["items"]]
    return val


def deserialize_instruction(d: dict) -> InstructionBase:
    """Reconstruct a typed instruction from its flat JSON form.

    Uses the IRInstruction() factory which handles the opcode → typed class dispatch.
    """
    opcode = Opcode(d["opcode"])
    result_reg = Register(d["result_reg"]) if d.get("result_reg") else NO_REGISTER
    operands = [_deserialize_operand(op) for op in d.get("operands", [])]
    label = CodeLabel(d["label"]) if d.get("label") else NO_LABEL
    branch_targets = [CodeLabel(t) for t in d.get("branch_targets", [])]
    source_location = _deserialize_source_location(d.get("source_location"))

    return IRInstruction(
        opcode=opcode,
        result_reg=result_reg,
        operands=operands,
        label=label,
        branch_targets=branch_targets,
        source_location=source_location,
    )


def deserialize_instructions(data: list[dict]) -> list[InstructionBase]:
    """Reconstruct all instructions from a JSON list."""
    return [deserialize_instruction(d) for d in data]


# ── VM state deserialization ────────────────────────────────────────


def _deserialize_value(val: Any) -> Any:
    """Reconstruct typed values from their JSON form."""
    if isinstance(val, dict):
        if val.get("__symbolic__"):
            return SymbolicValue(
                name=val.get("name", ""),
                type_hint=val.get("type_hint"),
            )
        if val.get("__pointer__"):
            from interpreter.vm.vm import Pointer

            return Pointer(base=Address(val["base"]), offset=val.get("offset", 0))
    return val


def _deserialize_heap_object(d: dict) -> HeapObject:
    """Reconstruct a HeapObject."""
    type_hint_str = d.get("type_hint", "unknown")
    type_hint = (
        scalar(TypeName(type_hint_str)) if type_hint_str != "unknown" else UNKNOWN
    )
    fields = {
        FieldName(k): _deserialize_value(v) for k, v in d.get("fields", {}).items()
    }
    return HeapObject(type_hint=type_hint, fields=fields)


def _deserialize_stack_frame(d: dict) -> StackFrame:
    """Reconstruct a StackFrame."""
    return StackFrame(
        function_name=FuncName(d.get("function_name", "")),
        registers={
            Register(k): _deserialize_value(v)
            for k, v in d.get("registers", {}).items()
        },
        local_vars={
            VarName(k): _deserialize_value(v)
            for k, v in d.get("local_vars", {}).items()
        },
        return_label=(
            CodeLabel(d["return_label"]) if d.get("return_label") else NO_LABEL
        ),
        closure_env_id=(
            ClosureId(d["closure_env_id"]) if d.get("closure_env_id") else NO_CLOSURE_ID
        ),
    )


def deserialize_vm_state(d: dict | None) -> VMState | None:
    """Reconstruct VMState from its dict form."""
    if d is None:
        return None

    heap = {
        Address(k): _deserialize_heap_object(v) for k, v in d.get("heap", {}).items()
    }
    call_stack = [_deserialize_stack_frame(f) for f in d.get("call_stack", [])]

    vm = VMState()
    for addr, obj in heap.items():
        vm.heap_set(addr, obj)
    vm.call_stack = call_stack
    vm.path_conditions = d.get("path_conditions", [])
    vm.symbolic_counter = d.get("symbolic_counter", 0)

    for label_str, env_dict in d.get("closures", {}).items():
        closure_id = ClosureId(label_str)
        bindings = {
            VarName(k): _deserialize_value(v)
            for k, v in env_dict.get("bindings", {}).items()
        }
        vm.closures[closure_id] = ClosureEnvironment(bindings=bindings)

    for addr_str, data in d.get("regions", {}).items():
        vm.region_alloc(Address(addr_str), len(data))
        for i, byte_val in enumerate(data):
            vm.region_write(Address(addr_str), i, [byte_val])

    for k, v in d.get("continuations", {}).items():
        from interpreter.continuation_name import ContinuationName

        vm.continuations[ContinuationName(k)] = CodeLabel(v)

    if d.get("data_layout"):
        vm.data_layout = d["data_layout"]

    return vm


# ── Full deserialization ────────────────────────────────────────────


def deserialize_export(json_path: Path) -> dict:
    """Deserialize a full IR export file back to live Python objects.

    Returns a dict with:
        - "meta": dict of export metadata
        - "instructions": list[InstructionBase] (typed IR instructions)
        - "cfg": CFG built from the instructions
        - "registry": FunctionRegistry
        - "vm_state": VMState | None
        - "execution": dict of execution stats
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))

    meta = data["_meta"]
    logger.info("Deserializing export from %s", meta["source_file"])
    logger.info(
        "  Format version: %d, %d instructions",
        meta["format_version"],
        meta["instruction_count"],
    )

    # Reconstruct instructions
    instructions = deserialize_instructions(data["instructions"])
    logger.info("  Reconstructed %d typed instructions", len(instructions))

    # Verify round-trip fidelity
    original_types = [d["_type"] for d in data["instructions"]]
    reconstructed_types = [type(inst).__name__ for inst in instructions]
    mismatches = [
        (i, orig, recon)
        for i, (orig, recon) in enumerate(zip(original_types, reconstructed_types))
        if orig != recon
    ]
    if mismatches:
        logger.warning("  Type mismatches at indices: %s", mismatches[:5])
    else:
        logger.info("  All instruction types match (round-trip verified)")

    # Rebuild CFG
    cfg = build_cfg(instructions)
    logger.info(
        "  Rebuilt CFG: %d blocks (original: %d)",
        len(cfg.blocks),
        meta["cfg_block_count"],
    )

    # Rebuild registry
    registry = build_registry(instructions, cfg)
    logger.info(
        "  Rebuilt registry: %d functions, %d classes",
        len(registry.func_params),
        len(registry.classes),
    )

    # Reconstruct VM state
    vm_state = deserialize_vm_state(data.get("vm_state"))
    if vm_state:
        logger.info(
            "  Restored VM state: %d heap objects, %d stack frames",
            vm_state.heap_count(),
            len(vm_state.call_stack),
        )
    else:
        logger.info("  No VM state to restore (execution failed during export)")

    return {
        "meta": meta,
        "instructions": instructions,
        "cfg": cfg,
        "registry": registry,
        "vm_state": vm_state,
        "execution": data.get("execution", {}),
    }


# ── Verification ────────────────────────────────────────────────


def verify_round_trip(json_path: Path) -> bool:
    """Verify that serialize → deserialize produces identical IR text."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    result = deserialize_export(json_path)

    original_strs = [d["_str"] for d in data["instructions"]]
    reconstructed_strs = [str(inst) for inst in result["instructions"]]

    matches = 0
    mismatches = 0
    for i, (orig, recon) in enumerate(zip(original_strs, reconstructed_strs)):
        if orig == recon:
            matches += 1
        else:
            mismatches += 1
            if mismatches <= 5:
                logger.warning("  Mismatch at %d:", i)
                logger.warning("    original:      %s", orig)
                logger.warning("    reconstructed:  %s", recon)

    total = len(original_strs)
    logger.info(
        "Round-trip fidelity: %d/%d instructions match (%.1f%%)",
        matches,
        total,
        matches / total * 100 if total else 0,
    )
    return mismatches == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: poetry run python experiments/legacy_ir_export/deserialize_ir.py <json_file>"
        )
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}")
        sys.exit(1)

    result = deserialize_export(json_path)

    print("\n═══ Reconstructed IR ═══")
    for inst in result["instructions"]:
        print(f"  {inst}")

    print(f"\n═══ CFG ═══")
    print(f"  {len(result['cfg'].blocks)} blocks, entry: {result['cfg'].entry}")

    print(f"\n═══ Registry ═══")
    print(f"  Functions: {list(result['registry'].func_params.keys())[:10]}")
    print(f"  Classes: {list(result['registry'].classes.keys())[:10]}")

    if result["vm_state"]:
        print(f"\n═══ VM State ═══")
        print(f"  Heap objects: {result['vm_state'].heap_count()}")
        print(f"  Stack frames: {len(result['vm_state'].call_stack)}")

    print("\n═══ Round-trip Verification ═══")
    verify_round_trip(json_path)
