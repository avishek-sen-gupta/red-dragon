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

import re
from pathlib import Path

from interpreter.cfg import build_cfg
from interpreter.ir import IRInstruction, Opcode
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


def max_register_number(ir: tuple[IRInstruction, ...] | list[IRInstruction]) -> int:
    """Find the highest register number used in an IR sequence. Returns -1 if none."""
    max_reg = -1
    for inst in ir:
        if inst.result_reg:
            m = _REGISTER_RE.match(inst.result_reg)
            if m:
                max_reg = max(max_reg, int(m.group(1)))
        for op in inst.operands:
            m = _REGISTER_RE.match(str(op))
            if m:
                max_reg = max(max_reg, int(m.group(1)))
    return max_reg


# ── IR transformation ───────────────────────────────────────────


def _namespace_branch_targets(label_str: str, prefix: str) -> str:
    """Namespace comma-separated branch targets."""
    parts = label_str.split(",")
    return ",".join(namespace_label(p.strip(), prefix) for p in parts)


def _rebase_operand(operand, offset: int):
    """Rebase a single operand if it's a register."""
    if isinstance(operand, str):
        return rebase_register(operand, offset)
    return operand


def _transform_instruction(
    inst: IRInstruction,
    prefix: str,
    reg_offset: int,
) -> IRInstruction:
    """Namespace labels, rebase registers, namespace CONST func/class refs."""
    # ── Label ──
    new_label = None
    if inst.label:
        if inst.opcode in (Opcode.BRANCH, Opcode.BRANCH_IF):
            new_label = _namespace_branch_targets(inst.label, prefix)
        elif inst.opcode == Opcode.TRY_PUSH:
            new_label = _namespace_branch_targets(inst.label, prefix)
        else:
            new_label = namespace_label(inst.label, prefix)

    # ── Result register ──
    new_result_reg = (
        rebase_register(inst.result_reg, reg_offset) if inst.result_reg else None
    )

    # ── Operands ──
    if inst.opcode == Opcode.TRY_PUSH:
        new_operands = [
            _namespace_branch_targets(op, prefix) if isinstance(op, str) and op else op
            for op in inst.operands
        ]
    else:
        new_operands = []
        for i, op in enumerate(inst.operands):
            rebased = _rebase_operand(op, reg_offset)
            # Namespace func/class label refs in CONST operands
            if (
                isinstance(rebased, str)
                and inst.opcode == Opcode.CONST
                and i == 0
                and (
                    rebased.startswith(constants.FUNC_LABEL_PREFIX)
                    or rebased.startswith(constants.CLASS_LABEL_PREFIX)
                )
            ):
                rebased = namespace_label(rebased, prefix)
            new_operands.append(rebased)

    return IRInstruction(
        opcode=inst.opcode,
        result_reg=new_result_reg,
        operands=new_operands,
        label=new_label,
        source_location=inst.source_location,
    )


def _is_import_call(inst: IRInstruction) -> bool:
    """Is this a CALL_FUNCTION 'import' ... instruction?"""
    return (
        inst.opcode == Opcode.CALL_FUNCTION
        and len(inst.operands) >= 1
        and str(inst.operands[0]) == "import"
    )


def _transform_module(
    module: ModuleUnit,
    prefix: str,
    reg_offset: int,
    resolved_imports: set[str],
) -> list[IRInstruction]:
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
    result: list[IRInstruction] = []
    skip_next_decl_for_reg: str | None = None

    for inst in module.ir:
        # Skip the per-module "entry:" label — we'll add a single one
        if inst.opcode == Opcode.LABEL and inst.label == "entry":
            continue

        # Drop import stubs for resolved names
        if _is_import_call(inst) and inst.result_reg:
            # Peek: the next DECL_VAR will tell us the name. We can't peek
            # here, so mark the register and decide at the DECL_VAR.
            skip_next_decl_for_reg = rebase_register(inst.result_reg, reg_offset)
            # Tentatively add the instruction — remove it if DECL_VAR matches
            result.append(_transform_instruction(inst, prefix, reg_offset))
            continue

        if (
            skip_next_decl_for_reg
            and inst.opcode == Opcode.DECL_VAR
            and len(inst.operands) >= 2
        ):
            var_name = str(inst.operands[0])
            reg = rebase_register(str(inst.operands[1]), reg_offset)
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
) -> tuple[dict[str, FuncRef], dict[str, ClassRef]]:
    """Merge and namespace all modules' export symbol tables.

    Labels are namespaced (unique in merged CFG).
    Names are kept bare (VM uses them for method dispatch).
    """
    merged_func: dict[str, FuncRef] = {}
    merged_class: dict[str, ClassRef] = {}

    for path, module in modules.items():
        prefix = prefixes[path]
        for name, label in module.exports.functions.items():
            ns_label = namespace_label(label, prefix)
            merged_func[ns_label] = FuncRef(name=name, label=ns_label)
        for name, label in module.exports.classes.items():
            ns_label = namespace_label(label, prefix)
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
    all_ir: list[IRInstruction] = [IRInstruction(opcode=Opcode.LABEL, label="entry")]
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
