"""Linker — namespace, rebase, and merge multi-module IR.

The linker's job is simple: produce a single IR stream that looks exactly
like what the single-file pipeline would produce if all source files were
concatenated in dependency order.

Design:
  1. Namespace labels and rebase registers (avoid collisions)
  2. Strip per-module `entry:` labels (there's only one entry point)
  3. Concatenate in dependency order (deps first, entry module last)
  4. Prepend a single `entry:` label
  5. Replace import stubs with the declarations the dep modules provide

That's it. No chaining, no import tables, no special variable handling.
The dependency modules' top-level code (STORE_VAR, CONST+DECL_VAR for
functions/classes) runs first, so by the time the entry module's code
executes, all imported names are already in scope — exactly like single-file.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from interpreter.cfg import build_cfg
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.instructions import (
    InstructionBase,
    Instruction,
    CallFunction,
    DeclVar,
    Const,
    Label_,
)
from interpreter.project.types import ExportTable, LinkedProgram, ModuleUnit
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.registry import build_registry
from interpreter import constants

# ── Public helpers (tested individually) ─────────────────────────

_REGISTER_RE = re.compile(r"^%(\d+)$")


def module_prefix(file_path: Path, project_root: Path) -> str:
    """Compute the namespace prefix for a module.

    /project/src/utils.py  (root=/project/) → "src.utils"
    /project/main.py       (root=/project/) → "main"
    """
    relative = file_path.relative_to(project_root)
    stem = str(relative.with_suffix(""))
    return stem.replace("/", ".").replace("\\", ".")


def namespace_label(label: str, prefix: str) -> str:
    """Prefix a label with a module namespace."""
    return f"{prefix}.{label}"


def rebase_register(operand: str, offset: int) -> str:
    """Shift a register %N by offset. Non-registers pass through unchanged."""
    m = _REGISTER_RE.match(str(operand))
    if m:
        return f"%{int(m.group(1)) + offset}"
    return operand


def max_register_number(ir: tuple[...] | list[InstructionBase]) -> int:
    """Find the highest register number used in an IR sequence. Returns -1 if none."""
    max_reg = -1
    for inst in ir:
        if inst.result_reg.is_present():
            m = _REGISTER_RE.match(str(inst.result_reg))
            if m:
                max_reg = max(max_reg, int(m.group(1)))
        for op in inst.operands:
            m = _REGISTER_RE.match(str(op))
            if m:
                max_reg = max(max_reg, int(m.group(1)))
    return max_reg


# ── IR transformation ───────────────────────────────────────────


def _transform_instruction(
    inst: InstructionBase,
    prefix: str,
    reg_offset: int,
) -> Instruction:
    """Namespace labels, rebase registers, namespace CONST func/class refs."""
    typed = inst

    # map_labels handles all CodeLabel fields (label, branch_targets, catch_labels, etc.)
    transformed = typed.map_labels(lambda l: l.namespace(prefix))

    # map_registers handles all Register fields (result_reg, operand regs, etc.)
    transformed = transformed.map_registers(lambda r: r.rebase(reg_offset))

    # Special case: CONST with func/class label refs stored as string values
    if (
        isinstance(transformed, Const)
        and isinstance(transformed.value, str)
        and transformed.value
        and (
            transformed.value.startswith(constants.FUNC_LABEL_PREFIX)
            or transformed.value.startswith(constants.CLASS_LABEL_PREFIX)
        )
    ):
        transformed = dataclasses.replace(
            transformed, value=namespace_label(transformed.value, prefix)
        )

    return transformed


def _is_import_call(inst: InstructionBase) -> bool:
    """Is this a CALL_FUNCTION 'import' ... instruction?"""
    t = inst
    if not isinstance(t, CallFunction):
        return False
    return str(t.func_name) == "import"


def _transform_module(
    module: ModuleUnit,
    prefix: str,
    reg_offset: int,
    resolved_imports: set[str],
) -> list[InstructionBase]:
    """Transform a module's IR: namespace, rebase, drop resolved import stubs.

    Import stubs (CALL_FUNCTION "import" + DECL_VAR) are dropped for names
    that are already resolved (present in resolved_imports). These names
    will be set by the dependency module's top-level code which runs first.

    NOTE: The stub dropper assumes CALL_FUNCTION "import" is immediately
    followed by DECL_VAR (no intervening instructions). This holds for all
    current frontends — only Python emits CALL_FUNCTION "import", and its
    lower_import / lower_import_from always emit the pair adjacently. If a
    future frontend breaks this adjacency, the skip_next_decl_for_reg flag
    could match a later unrelated DECL_VAR. See red-dragon-lzae.
    """
    result: list[InstructionBase] = []
    skip_next_decl_for_reg: str | None = None

    for inst in module.ir:
        # Skip the per-module "entry:" label — we'll add a single one
        typed = inst
        if isinstance(typed, Label_) and typed.label.is_entry():
            continue

        # Drop import stubs for resolved names
        if _is_import_call(inst) and inst.result_reg.is_present():
            # Peek: the next DECL_VAR will tell us the name. We can't peek
            # here, so mark the register and decide at the DECL_VAR.
            skip_next_decl_for_reg = rebase_register(inst.result_reg, reg_offset)
            # Tentatively add the instruction — remove it if DECL_VAR matches
            result.append(_transform_instruction(inst, prefix, reg_offset))
            continue

        if skip_next_decl_for_reg and isinstance(typed, DeclVar):
            var_name = str(typed.name)
            reg = rebase_register(str(typed.value_reg), reg_offset)
            if reg == skip_next_decl_for_reg and var_name in resolved_imports:
                # Drop both the import CALL and this DECL_VAR
                result.pop()  # remove the tentatively-added CALL_FUNCTION
                skip_next_decl_for_reg = None
                continue
            skip_next_decl_for_reg = None

        result.append(_transform_instruction(inst, prefix, reg_offset))

    return result


# ── Symbol table merging ─────────────────────────────────────────


def _merge_symbol_tables(
    modules: dict[Path, ModuleUnit],
    prefixes: dict[Path, str],
) -> tuple[dict[CodeLabel, FuncRef], dict[CodeLabel, ClassRef]]:
    """Merge and namespace all modules' export symbol tables.

    Labels are namespaced (unique in merged CFG).
    Names are kept bare (VM uses them for method dispatch).
    """
    merged_func: dict[CodeLabel, FuncRef] = {}
    merged_class: dict[CodeLabel, ClassRef] = {}

    for path, module in modules.items():
        prefix = prefixes[path]
        for name, label in module.exports.functions.items():
            ns_label = label.namespace(prefix)
            merged_func[ns_label] = FuncRef(name=FuncName(name), label=ns_label)
        for name, label in module.exports.classes.items():
            ns_label = label.namespace(prefix)
            merged_class[ns_label] = ClassRef(name=name, label=ns_label, parents=())

    return merged_func, merged_class


def _collect_resolved_imports(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
) -> dict[Path, set[str]]:
    """For each module, collect names that are resolved by dependency modules.

    A name is 'resolved' if it appears in a dependency module's exports
    (function, class, or variable). These names don't need import stubs
    because the dependency module's top-level code will set them in scope.
    """
    resolved: dict[Path, set[str]] = {}
    for path, module in modules.items():
        names: set[str] = set()
        for dep_path in import_graph.get(path, []):
            if dep_path in modules:
                dep = modules[dep_path]
                names |= dep.exports.all_names()
        resolved[path] = names
    return resolved


# ── Main linker ──────────────────────────────────────────────────


def link_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    entry_module: Path,
    project_root: Path,
    topo_order: list[Path],
) -> LinkedProgram:
    """Link compiled modules into a single program.

    Produces IR that looks like a single-file compilation:
      entry:
        [dep1 top-level code]    ← sets variables, declares functions/classes
        [dep2 top-level code]
        [entry module code]       ← uses imported names (already in scope)
        [dep1 function bodies]   ← jumped over by BRANCH-end patterns
        [dep2 function bodies]
        [entry function bodies]
    """
    prefixes = {path: module_prefix(path, project_root) for path in modules}
    resolved = _collect_resolved_imports(modules, import_graph)

    # Processing order: dependencies first (topo order), entry module last
    processing_order = [p for p in topo_order if p != entry_module and p in modules] + [
        entry_module
    ]

    # Build merged IR with a single entry label
    all_ir: list[InstructionBase] = [Label_(label=CodeLabel("entry"))]
    reg_offset = 0

    for file_path in processing_order:
        module = modules[file_path]
        prefix = prefixes[file_path]
        module_resolved = resolved.get(file_path, set())

        transformed = _transform_module(module, prefix, reg_offset, module_resolved)
        all_ir.extend(transformed)
        reg_offset += max_register_number(module.ir) + 1

    # Build merged symbol tables, CFG, and registry
    merged_func_symbols, merged_class_symbols = _merge_symbol_tables(modules, prefixes)
    merged_cfg = build_cfg(all_ir)
    merged_registry = build_registry(
        all_ir,
        merged_cfg,
        func_symbol_table=merged_func_symbols,
        class_symbol_table=merged_class_symbols,
    )

    return LinkedProgram(
        modules=modules,
        merged_ir=all_ir,
        merged_cfg=merged_cfg,
        merged_registry=merged_registry,
        entry_module=entry_module,
        import_graph=import_graph,
        func_symbol_table=merged_func_symbols,
        class_symbol_table=merged_class_symbols,
    )
