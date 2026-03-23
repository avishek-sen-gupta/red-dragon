"""Linker — namespace, rebase, rewrite, and merge multi-module IR.

link_modules(): list[ModuleUnit] + import graph → LinkedProgram
"""

from __future__ import annotations

import re
from pathlib import Path

from interpreter.cfg import build_cfg
from interpreter.constants import Language
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


# ── Internal helpers ─────────────────────────────────────────────


def _is_label_operand(opcode: Opcode) -> bool:
    """Does this opcode's label field contain branch target(s)?"""
    return opcode in (Opcode.BRANCH, Opcode.BRANCH_IF, Opcode.LABEL)


def _namespace_branch_targets(label_str: str, prefix: str) -> str:
    """Namespace comma-separated branch targets."""
    parts = label_str.split(",")
    return ",".join(namespace_label(p.strip(), prefix) for p in parts)


def _rebase_operand(operand, offset: int) -> object:
    """Rebase a single operand if it's a register."""
    if isinstance(operand, str):
        return rebase_register(operand, offset)
    return operand


def _chain_module_entries(
    ir: list[IRInstruction],
    processing_order: list[Path],
    prefixes: dict[Path, str],
) -> None:
    """Insert BRANCH instructions to chain module entry points.

    After concatenation, each module's top-level code is isolated — no
    instruction branches from one module to the next. This function finds
    the last top-level block of each module (excluding the final entry
    module) and appends a BRANCH to the next module's entry label.

    This ensures dependency modules' top-level code (variable assignments,
    function declarations) runs before the entry module's code.
    """
    if len(processing_order) < 2:
        return

    # For each module except the last, find the last instruction that belongs
    # to it and insert a BRANCH to the next module's entry after it.
    module_boundaries: list[tuple[int, str]] = []  # (last_ir_index, next_entry_label)

    current_module_idx = 0
    for i, inst in enumerate(ir):
        if inst.opcode == Opcode.LABEL and inst.label:
            # Check if this label belongs to a later module
            for j in range(current_module_idx + 1, len(processing_order)):
                next_prefix = prefixes[processing_order[j]]
                if inst.label == namespace_label("entry", next_prefix):
                    # Found the start of the next module
                    next_label = inst.label
                    module_boundaries.append((i, next_label))
                    current_module_idx = j
                    break

    # Insert BRANCH instructions before each module boundary (in reverse order
    # to preserve indices)
    for insert_before, next_label in reversed(module_boundaries):
        ir.insert(insert_before, IRInstruction(
            opcode=Opcode.BRANCH,
            label=next_label,
        ))


def _namespace_and_rebase_instruction(
    inst: IRInstruction,
    prefix: str,
    reg_offset: int,
    import_table: dict[str, str],
) -> IRInstruction:
    """Namespace labels, rebase registers, and rewrite imported references."""
    new_label = None
    if inst.label:
        if inst.opcode == Opcode.LABEL:
            new_label = namespace_label(inst.label, prefix)
        elif inst.opcode in (Opcode.BRANCH, Opcode.BRANCH_IF):
            new_label = _namespace_branch_targets(inst.label, prefix)
        elif inst.opcode == Opcode.TRY_PUSH:
            # TRY_PUSH has comma-separated labels in .label, but also in operands
            new_label = _namespace_branch_targets(inst.label, prefix) if inst.label else None
        else:
            new_label = namespace_label(inst.label, prefix)

    new_result_reg = None
    if inst.result_reg:
        new_result_reg = rebase_register(inst.result_reg, reg_offset)

    new_operands = []
    for i, op in enumerate(inst.operands):
        rebased = _rebase_operand(op, reg_offset)
        # Do NOT rewrite CALL_FUNCTION/LOAD_VAR operands — the VM resolves
        # function names via local_vars scope lookup. We fix imports by
        # replacing the import CALL_FUNCTION+DECL_VAR pair instead.
        # Namespace func/class label references in CONST operands
        # (e.g. CONST "func_helper_0" → CONST "utils.func_helper_0")
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

    # Rewrite TRY_PUSH operands (they contain label strings)
    if inst.opcode == Opcode.TRY_PUSH:
        new_operands = []
        for op in inst.operands:
            if isinstance(op, str) and op:
                # Could be comma-separated labels
                new_operands.append(_namespace_branch_targets(op, prefix))
            else:
                new_operands.append(op)

    return IRInstruction(
        opcode=inst.opcode,
        result_reg=new_result_reg,
        operands=new_operands,
        label=new_label,
        source_location=inst.source_location,
    )


def _build_import_table(
    module: ModuleUnit,
    all_modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    prefixes: dict[Path, str],
) -> dict[str, str]:
    """Build a name → namespaced-label mapping for a module's imports.

    For each ImportRef with specific names (from X import Y), maps the local
    name to the target module's namespaced export label.
    """
    table: dict[str, str] = {}
    target_paths = import_graph.get(module.path, [])

    for ref in module.imports:
        if ref.is_system or not ref.names:
            continue

        # Find which target file this ref points to
        target_path = _match_ref_to_target(ref, target_paths, all_modules)
        if target_path is None:
            continue

        target_module = all_modules[target_path]
        target_prefix = prefixes[target_path]

        for name in ref.names:
            if name == "*":
                # Wildcard: import all exports — only functions and classes
                for export_name in target_module.exports.all_names():
                    # Skip variable exports — they're resolved by running the dep module
                    if export_name in target_module.exports.variables:
                        continue
                    export_label = target_module.exports.lookup(export_name)
                    if export_label:
                        namespaced = namespace_label(export_label, target_prefix)
                        table[export_name] = namespaced
            else:
                # Skip variable exports
                if name in target_module.exports.variables and \
                   name not in target_module.exports.functions and \
                   name not in target_module.exports.classes:
                    continue
                export_label = target_module.exports.lookup(name)
                if export_label:
                    actual_name = ref.alias if ref.alias and len(ref.names) == 1 else name
                    namespaced = namespace_label(export_label, target_prefix)
                    table[actual_name] = namespaced

    return table


def _match_ref_to_target(
    ref: ImportRef,
    target_paths: list[Path],
    all_modules: dict[Path, ModuleUnit],
) -> Path | None:
    """Match an ImportRef to one of the resolved target paths."""
    # Simple heuristic: check if the module_path or any name appears in the
    # target file's path or exports
    for target in target_paths:
        if target not in all_modules:
            continue
        target_stem = target.stem
        # Match by filename stem
        module_parts = ref.module_path.split(".") if ref.module_path else []
        if module_parts and module_parts[-1] == target_stem:
            return target
        if not module_parts and ref.names:
            # from . import X → match X to a filename
            for name in ref.names:
                if name.lower() == target_stem.lower():
                    return target
    # Fallback: if only one target, use it
    if len(target_paths) == 1 and target_paths[0] in all_modules:
        return target_paths[0]
    return None


def _merge_symbol_tables(
    modules: dict[Path, ModuleUnit],
    prefixes: dict[Path, str],
) -> tuple[dict[str, FuncRef], dict[str, ClassRef]]:
    """Merge and namespace all modules' export symbol tables.

    Labels are namespaced (to avoid collisions in the merged CFG).
    Names are kept bare (the VM uses them for method dispatch lookups).
    """
    merged_func: dict[str, FuncRef] = {}
    merged_class: dict[str, ClassRef] = {}

    for path, module in modules.items():
        prefix = prefixes[path]
        for name, label in module.exports.functions.items():
            ns_label = namespace_label(label, prefix)
            # Keep bare name — VM method dispatch looks up by bare name
            merged_func[ns_label] = FuncRef(name=name, label=ns_label)
        for name, label in module.exports.classes.items():
            ns_label = namespace_label(label, prefix)
            # Keep bare name — VM constructor dispatch uses it for heap type_hint
            # and class_methods lookup
            merged_class[ns_label] = ClassRef(name=name, label=ns_label, parents=())

    return merged_func, merged_class


def _build_all_import_bindings(
    import_tables: dict[Path, dict[str, str]],
) -> dict[str, str]:
    """Flatten all import tables into a single name → label mapping."""
    bindings: dict[str, str] = {}
    for table in import_tables.values():
        bindings.update(table)
    return bindings


def _rewrite_import_stubs(
    ir: list[IRInstruction],
    import_tables: dict[Path, dict[str, str]],
    modules: dict[Path, ModuleUnit],
    prefixes: dict[Path, str],
) -> list[IRInstruction]:
    """Replace import CALL_FUNCTION + DECL_VAR pairs with direct label bindings.

    The Python frontend (and others) emits import statements as:
        %0 = CALL_FUNCTION "import" "from X import Y"
        DECL_VAR Y %0

    After linking, we know Y maps to a namespaced label. Replace the pair:
        %0 = CONST "target_module.func_Y_0"
        DECL_VAR Y %0

    This way the VM finds the correct function/class label in local_vars
    when dispatching calls.
    """
    # Build a combined name → namespaced-label mapping from all import tables
    all_bindings: dict[str, str] = {}
    for table in import_tables.values():
        all_bindings.update(table)

    if not all_bindings:
        return ir

    # Scan for CALL_FUNCTION "import" instructions and record which registers
    # they write to, so we can replace the following DECL_VAR.
    import_regs: dict[str, None] = {}  # registers produced by import calls
    result: list[IRInstruction] = []

    # Pre-compute which names are variable-only imports (no function/class binding)
    # These should be dropped entirely — the dep module already sets them.
    var_only_names: set[str] = set()
    for table in import_tables.values():
        pass  # all_bindings only has func/class bindings (var skipped above)
    # Gather variable names from all modules' exports
    all_var_exports: set[str] = set()
    for mod in modules.values():
        all_var_exports.update(mod.exports.variables.keys())

    for inst in ir:
        # Detect: %N = CALL_FUNCTION "import" "from X import Y"
        if (
            inst.opcode == Opcode.CALL_FUNCTION
            and len(inst.operands) >= 1
            and str(inst.operands[0]) == "import"
            and inst.result_reg
        ):
            import_regs[inst.result_reg] = None
            # Don't emit this instruction yet — check if next DECL_VAR uses it
            # Actually, we need to replace this CALL with a CONST for the right label.
            # But we don't know the name yet — that comes from the DECL_VAR.
            # So keep the instruction but mark it for replacement.
            result.append(inst)
            continue

        # Detect: DECL_VAR Y %N where %N is an import register
        if (
            inst.opcode == Opcode.DECL_VAR
            and len(inst.operands) >= 2
            and str(inst.operands[1]) in import_regs
        ):
            var_name = str(inst.operands[0])
            reg = str(inst.operands[1])

            if var_name in all_bindings:
                target_label = all_bindings[var_name]
                # Replace the preceding CALL_FUNCTION "import" with CONST
                # Find and replace it in result
                for j in range(len(result) - 1, -1, -1):
                    if result[j].result_reg == reg and result[j].opcode == Opcode.CALL_FUNCTION:
                        result[j] = IRInstruction(
                            opcode=Opcode.CONST,
                            result_reg=reg,
                            operands=[target_label],
                            source_location=result[j].source_location,
                        )
                        break
                # Emit the DECL_VAR unchanged — it now binds to the CONST label
                result.append(inst)
                # Clean up the import_regs entry
                del import_regs[reg]
            elif var_name in all_var_exports:
                # Variable-only import — the dependency module already set this
                # variable in the global scope. Drop the import stub + DECL_VAR
                # pair to avoid overwriting the concrete value with a symbolic one.
                for j in range(len(result) - 1, -1, -1):
                    if result[j].result_reg == reg and result[j].opcode == Opcode.CALL_FUNCTION:
                        result.pop(j)
                        break
                if reg in import_regs:
                    del import_regs[reg]
                # Don't emit the DECL_VAR — skip it
            else:
                # Import name not in our bindings (e.g., system import) — keep as-is
                result.append(inst)
            continue

        result.append(inst)

    return result


# ── Main linker ──────────────────────────────────────────────────


def link_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    entry_module: Path,
    project_root: Path,
    topo_order: list[Path],
) -> LinkedProgram:
    """Link compiled modules into a single program.

    1. Compute namespace prefixes for each module
    2. Build import tables for cross-module reference rewriting
    3. Namespace labels, rebase registers, rewrite imports in each module's IR
    4. Concatenate into merged IR (entry module first)
    5. Build CFG + registry on the merged IR
    """
    prefixes = {path: module_prefix(path, project_root) for path in modules}

    # Build import tables
    import_tables: dict[Path, dict[str, str]] = {}
    for path, module in modules.items():
        import_tables[path] = _build_import_table(
            module, modules, import_graph, prefixes
        )

    # Namespace + rebase + merge
    all_ir: list[IRInstruction] = []
    reg_offset = 0

    # Dependency modules first (their function/class declarations must be
    # available before the entry module's top-level code uses them).
    # Then entry module last — its entry label is still the program entry
    # because build_cfg sets cfg.entry to the first label it sees, and we
    # fix that below.
    processing_order = [
        p for p in topo_order if p != entry_module and p in modules
    ] + [entry_module]

    for file_path in processing_order:
        module = modules[file_path]
        prefix = prefixes[file_path]
        import_table = import_tables.get(file_path, {})

        for inst in module.ir:
            namespaced = _namespace_and_rebase_instruction(
                inst, prefix, reg_offset, import_table
            )
            all_ir.append(namespaced)

        reg_offset += max_register_number(module.ir) + 1

    # Chain module entries: add BRANCH from the end of each module's
    # top-level code to the next module's entry label. This ensures all
    # dependency modules' code runs before the entry module.
    _chain_module_entries(all_ir, processing_order, prefixes)

    # Build merged CFG + registry
    merged_func_symbols, merged_class_symbols = _merge_symbol_tables(modules, prefixes)

    # Replace import stubs with direct label bindings
    all_ir = _rewrite_import_stubs(all_ir, import_tables, modules, prefixes)

    merged_cfg = build_cfg(all_ir)
    # Set entry to the first module in processing order (first dependency).
    # The chain of BRANCH instructions will flow through all deps to the
    # entry module's code.
    first_prefix = prefixes[processing_order[0]]
    merged_cfg.entry = namespace_label("entry", first_prefix)
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
