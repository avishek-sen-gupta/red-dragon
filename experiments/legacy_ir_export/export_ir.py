"""Export RedDragon IR + VM state to a JSON file that can be deserialized back.

Usage:
    poetry run python experiments/legacy_ir_export/export_ir.py <java_file> [<output_json>]

Exports:
    - IR instructions in flat (opcode, result_reg, operands, label, branch_targets, source_location) form
    - VM state after execution (via VMState.to_dict())
    - Function registry metadata (params, classes)
    - Pipeline stats
"""

import dataclasses
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from interpreter.frontend import get_frontend
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.ir import (
    CodeLabel,
    NO_LABEL,
    NO_SOURCE_LOCATION,
    Opcode,
    SourceLocation,
    SpreadArguments,
)
from interpreter.instructions import InstructionBase
from interpreter.constants import Language
from interpreter.register import NO_REGISTER, Register
from interpreter.run import build_execution_strategies, execute_cfg
from interpreter.run_types import VMConfig, UnresolvedCallStrategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Serialization helpers ─────────────────────────────────────────


def _serialize_source_location(loc: SourceLocation) -> dict | None:
    """Serialize a SourceLocation to a dict, or None if unknown."""
    if loc.is_unknown():
        return None
    return {
        "start_line": loc.start_line,
        "start_col": loc.start_col,
        "end_line": loc.end_line,
        "end_col": loc.end_col,
    }


def _serialize_operand(val: Any) -> Any:
    """Convert an operand value to a JSON-safe representation."""
    if isinstance(val, list):
        return {"__type__": "list", "items": [_serialize_operand(item) for item in val]}
    if isinstance(val, Register):
        return {"__type__": "Register", "value": str(val)}
    if isinstance(val, SpreadArguments):
        return {"__type__": "SpreadArguments", "register": str(val.register)}
    if isinstance(val, CodeLabel):
        return (
            {"__type__": "CodeLabel", "value": str(val)} if val.is_present() else None
        )
    if isinstance(val, (int, float, bool)):
        return val
    if val is None:
        return None
    # Enums, domain types — convert to string
    return str(val)


def serialize_instruction(inst: InstructionBase) -> dict:
    """Serialize one typed instruction to its flat JSON form.

    This mirrors the fields accepted by the IRInstruction() factory,
    so deserialization can reconstruct the typed instruction.
    """
    return {
        "opcode": inst.opcode.value,
        "result_reg": str(inst.result_reg) if inst.result_reg.is_present() else None,
        "operands": [_serialize_operand(op) for op in inst.operands],
        "label": (
            str(inst.label)
            if hasattr(inst, "label") and inst.label.is_present()
            else None
        ),
        "branch_targets": (
            [str(t) for t in inst.branch_targets]
            if hasattr(inst, "branch_targets") and inst.branch_targets
            else []
        ),
        "source_location": _serialize_source_location(inst.source_location),
        # Extra metadata not needed for reconstruction, but useful for analysis
        "_type": type(inst).__name__,
        "_str": str(inst),
    }


def serialize_registry(registry: Any) -> dict:
    """Serialize function registry metadata."""
    return {
        "func_params": {
            str(k): [str(p) for p in v] for k, v in registry.func_params.items()
        },
        "classes": {
            str(k): {
                "fields": (
                    [str(f) for f in cls.fields] if hasattr(cls, "fields") else []
                ),
                "methods": (
                    [str(m) for m in cls.methods] if hasattr(cls, "methods") else []
                ),
                "parent": (
                    str(cls.parent) if hasattr(cls, "parent") and cls.parent else None
                ),
            }
            for k, cls in registry.classes.items()
        },
    }


# ── Main export logic ─────────────────────────────────────────────


def export_ir(java_file: Path, output_path: Path) -> dict:
    """Lower a Java file to IR, execute, and export everything to JSON."""
    source = java_file.read_text(encoding="utf-8")
    lang = Language.JAVA

    logger.info("Lowering %s (%d lines)...", java_file.name, source.count("\n") + 1)
    t0 = time.perf_counter()

    # 1. Lower to IR
    frontend = get_frontend(lang)
    instructions = frontend.lower(source.encode("utf-8"))
    lower_time = time.perf_counter() - t0
    logger.info(
        "  Produced %d IR instructions in %.1fms", len(instructions), lower_time * 1000
    )

    # 2. Build CFG
    cfg = build_cfg(instructions)
    logger.info("  CFG: %d blocks", len(cfg.blocks))

    # 3. Build registry
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    logger.info(
        "  Registry: %d functions, %d classes",
        len(registry.func_params),
        len(registry.classes),
    )

    # 4. Execute
    strategies = build_execution_strategies(frontend, instructions, registry, lang)
    entry_label = CodeLabel(cfg.entry) if isinstance(cfg.entry, str) else cfg.entry
    vm_config = VMConfig(
        max_steps=500,
        source_language=lang,
        unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
    )

    try:
        vm, exec_stats = execute_cfg(cfg, entry_label, registry, vm_config, strategies)
        vm.data_layout = frontend.data_layout
        vm_state_dict = vm.to_dict()
        execution_info = {
            "steps": exec_stats.steps,
            "llm_calls": exec_stats.llm_calls,
            "final_heap_objects": exec_stats.final_heap_objects,
            "final_symbolic_count": exec_stats.final_symbolic_count,
        }
    except Exception as e:
        logger.warning("  Execution failed (expected for partial programs): %s", e)
        vm_state_dict = None
        execution_info = {"error": str(e)}

    # 5. Build export payload
    payload = {
        "_meta": {
            "format_version": 1,
            "source_file": str(java_file),
            "language": lang.value,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "instruction_count": len(instructions),
            "cfg_block_count": len(cfg.blocks),
        },
        "instructions": [serialize_instruction(inst) for inst in instructions],
        "cfg_entry_label": str(entry_label),
        "registry": serialize_registry(registry),
        "vm_state": vm_state_dict,
        "execution": execution_info,
    }

    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info(
        "  Wrote %s (%.1f KB)", output_path.name, output_path.stat().st_size / 1024
    )
    return payload


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: poetry run python experiments/legacy_ir_export/export_ir.py <java_file> [<output_json>]"
        )
        sys.exit(1)

    java_file = Path(sys.argv[1])
    if not java_file.exists():
        print(f"File not found: {java_file}")
        sys.exit(1)

    output = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(f"experiments/legacy_ir_export/output/{java_file.stem}_ir.json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    export_ir(java_file, output)
