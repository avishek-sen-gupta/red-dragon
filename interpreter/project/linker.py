# pyright: standard
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
from typing import Any

from interpreter import constants
from interpreter.cfg import build_cfg
from interpreter.constants import (
    CLASS_LABEL_PREFIX,
    PRELUDE_CLASS_LABEL_PREFIX,
    Language,
)
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.instructions import (
    CallFunction,
    Const,
    DeclVar,
    ImportModule,
    InstructionBase,
    Label_,
)
from interpreter.ir import CodeLabel
from interpreter.path_name import NO_PATH_NAME
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.registry import build_registry
from interpreter.symbol_name import SymbolName
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.type_expr import UNKNOWN

# ── Public helpers (tested individually) ─────────────────────────

# Registers are "%" + an optional alpha prefix + a number. Tree-sitter frontends
# emit "%0", "%1", ...; the COBOL frontend emits "%r0", "%r1", .... Both must be
# recognized so per-module rebasing computes a correct offset (group 1 = prefix,
# group 2 = number).
_REGISTER_RE = re.compile(r"^%([A-Za-z]*)(\d+)$")


def module_prefix(file_path: Path, project_root: Path) -> str:
    """Compute the namespace prefix for a module.

    /project/src/utils.py  (root=/project/) → "src.utils"
    /project/main.py       (root=/project/) → "main"
    java/util/ArrayList.java (stdlib stub)  → "java.util.ArrayList"
    """
    if file_path.is_absolute():
        relative = file_path.relative_to(project_root)
    else:
        relative = file_path
    stem = str(relative.with_suffix(""))
    return stem.replace("/", ".").replace("\\", ".")


def namespace_label(label: str, prefix: str) -> str:
    """Prefix a label with a module namespace."""
    return f"{prefix}.{label}"


def rebase_register(operand: str, offset: int) -> str:
    """Shift a register's number by offset, preserving any alpha prefix.

    "%47" → "%147"; "%r5" → "%r105". Non-registers pass through unchanged.
    """
    m = _REGISTER_RE.match(str(operand))
    if m:
        return f"%{m.group(1)}{int(m.group(2)) + offset}"
    return operand


def max_register_number(ir: tuple[InstructionBase, ...] | list[InstructionBase]) -> int:
    """Find the highest register number used in an IR sequence. Returns -1 if none."""
    max_reg = -1
    for inst in ir:
        raw: Any = (
            inst  # InstructionBase subclasses have result_reg/operands; not in base  # see red-dragon-4ei7
        )
        if raw.result_reg.is_present():
            m = _REGISTER_RE.match(str(raw.result_reg))
            if m:
                max_reg = max(max_reg, int(m.group(2)))
        for op in raw.operands:
            m = _REGISTER_RE.match(str(op))
            if m:
                max_reg = max(max_reg, int(m.group(2)))
    return max_reg


# ── IR transformation ───────────────────────────────────────────


def _transform_instruction(
    inst: InstructionBase,
    prefix: str,
    reg_offset: int,
) -> InstructionBase:
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
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    module_path: Path,
    prefixes: dict[Path, str],
) -> list[InstructionBase]:
    """Transform a module's IR: namespace, rebase, drop resolved import stubs.

    Handles two types of import stubs:

    1. Old-style (Python): CALL_FUNCTION "import" + DECL_VAR. These are dropped
       for names already resolved (present in resolved_imports).

    2. New-style (IMPORT_MODULE): IMPORT_MODULE instructions with resolved_path
       pointing to a local file. These are replaced with CONST instructions that
       reference the actual function/class labels from dependency modules, since
       the linker concatenates modules in dependency order.

    NOTE: The stub dropper assumes CALL_FUNCTION "import" is immediately
    followed by DECL_VAR (no intervening instructions). This holds for all
    current frontends — only Python emits CALL_FUNCTION "import", and its
    lower_import / lower_import_from always emit the pair adjacently. If a
    future frontend breaks this adjacency, the skip_next_decl_for_reg flag
    could match a later unrelated DECL_VAR. See red-dragon-lzae.
    """
    from interpreter.instructions import LoadField

    result: list[InstructionBase] = []
    skip_next_decl_for_reg: str | None = None
    skip_import_module_pattern: tuple[str, list[tuple[str, str]]] | None = None

    # Build a map of imported names to their source modules (for IMPORT_MODULE replacement)
    # Value is either (src_module, label_string) for functions/classes, or (src_module, "VAR") for variables
    import_name_sources: dict[SymbolName, tuple[Path, str]] = (
        {}
    )  # name -> (src_module, src_label or "VAR")
    for dep_path in import_graph.get(module_path, []):
        if dep_path in modules:
            dep = modules[dep_path]
            dep_prefix = prefixes[dep_path]
            # Map function names to their namespaced labels
            for fname, label in dep.exports.functions.items():
                import_name_sources[SymbolName(str(fname))] = (
                    dep_path,
                    str(label.namespace(dep_prefix)),
                )
            # Map class names to their namespaced labels
            for cname, label in dep.exports.classes.items():
                import_name_sources[SymbolName(str(cname))] = (
                    dep_path,
                    str(label.namespace(dep_prefix)),
                )
            # Mark variables as importable (value is "VAR" since we skip the pattern)
            for vname in dep.exports.variables.keys():
                import_name_sources[SymbolName(str(vname))] = (dep_path, "VAR")

    i = 0
    ir_list = list(module.ir)
    while i < len(ir_list):
        inst = ir_list[i]
        typed = inst

        # Skip the per-module "entry:" label — we'll add a single one
        if isinstance(typed, Label_) and typed.label.is_entry():
            i += 1
            continue

        # Handle IMPORT_MODULE patterns: IMPORT_MODULE + LOAD_FIELD + DECL_VAR
        if isinstance(typed, ImportModule) and typed.resolved_path != NO_PATH_NAME:
            # This is a resolved local import. Look ahead to see if we have
            # LOAD_FIELD + DECL_VAR pattern that we can replace.
            import_reg = (
                str(typed.result_reg) if typed.result_reg.is_present() else None
            )
            # DEBUG: Check import_name_sources
            # print(f"DEBUG: IMPORT_MODULE {typed.module_path} with resolved_path {typed.resolved_path}")
            # print(f"DEBUG: import_name_sources = {import_name_sources}")
            # print(f"DEBUG: dependencies from import_graph[{module_path}] = {import_graph.get(module_path, [])}")

            # Scan forward for LOAD_FIELD instructions that depend on this register
            loads_and_decls = []
            j = i + 1
            while j < len(ir_list):
                next_inst = ir_list[j]
                if isinstance(next_inst, LoadField):
                    # Check if this LOAD_FIELD uses the import register
                    if str(next_inst.obj_reg) == import_reg:
                        # Look for the following DECL_VAR
                        if j + 1 < len(ir_list) and isinstance(ir_list[j + 1], DeclVar):
                            decl = ir_list[j + 1]
                            loads_and_decls.append((next_inst, decl))
                            j += 2
                        else:
                            break
                    else:
                        break
                else:
                    break

            # If we found LOAD_FIELD + DECL_VAR pairs, handle them
            if loads_and_decls:
                for load_field, decl in loads_and_decls:
                    field_name = load_field.field_name  # It's a FieldName object
                    symbol_key = SymbolName(str(field_name))
                    if symbol_key in import_name_sources:
                        _, import_source = import_name_sources[symbol_key]
                    else:
                        import_source = None

                    if import_source is not None:
                        if import_source == "VAR":
                            # For variables: skip the entire LOAD_FIELD + DECL_VAR pattern.
                            # The dependency module's top-level STORE_VAR already set the
                            # variable in scope, so we don't need to redeclare it.
                            pass  # Skip both LOAD_FIELD and DECL_VAR
                        else:
                            # For functions/classes: emit a typed CONST ref with the
                            # actual label, then DECL_VAR. Class labels -> class_ref
                            # (metatype), everything else -> func_ref (FunctionType),
                            # so the VM resolves the symbol-table entry by type.
                            actual_label = import_source
                            # Cross-module labels carry a "<module>." prefix
                            # (e.g. "geometry.class_Circle_0"), so test the bare
                            # label segment, not the fully-qualified string.
                            bare_label = actual_label.rsplit(".", 1)[-1]
                            if bare_label.startswith(
                                CLASS_LABEL_PREFIX
                            ) or bare_label.startswith(PRELUDE_CLASS_LABEL_PREFIX):
                                const_inst = Const.class_ref(
                                    load_field.result_reg, actual_label, UNKNOWN
                                )
                            else:
                                const_inst = Const.func_ref(
                                    load_field.result_reg, actual_label
                                )
                            result.append(
                                _transform_instruction(const_inst, prefix, reg_offset)
                            )
                            # Keep the DECL_VAR (but transform it)
                            result.append(
                                _transform_instruction(decl, prefix, reg_offset)
                            )
                    else:
                        # Name not found in imports — keep original LOAD_FIELD + DECL_VAR
                        result.append(
                            _transform_instruction(load_field, prefix, reg_offset)
                        )
                        result.append(_transform_instruction(decl, prefix, reg_offset))

                # Skip all the instructions we just processed
                i = j
                continue

            # If no LOAD_FIELD pattern found, just drop the IMPORT_MODULE
            i += 1
            continue

        # External/unresolved IMPORT_MODULE — keep it
        if isinstance(typed, ImportModule):
            result.append(_transform_instruction(inst, prefix, reg_offset))
            i += 1
            continue

        # Drop old-style import stubs for resolved names
        raw_inst: Any = (
            inst  # InstructionBase subclasses have result_reg; not in base  # see red-dragon-4ei7
        )
        if _is_import_call(inst) and raw_inst.result_reg.is_present():
            # Peek: the next DECL_VAR will tell us the name. We can't peek
            # here, so mark the register and decide at the DECL_VAR.
            skip_next_decl_for_reg = rebase_register(raw_inst.result_reg, reg_offset)
            # Tentatively add the instruction — remove it if DECL_VAR matches
            result.append(_transform_instruction(inst, prefix, reg_offset))
            i += 1
            continue

        if skip_next_decl_for_reg and isinstance(typed, DeclVar):
            var_name = str(typed.name)
            reg = rebase_register(str(typed.value_reg), reg_offset)
            if reg == skip_next_decl_for_reg and var_name in resolved_imports:
                # Drop both the import CALL and this DECL_VAR
                result.pop()  # remove the tentatively-added CALL_FUNCTION
                skip_next_decl_for_reg = None
                i += 1
                continue
            skip_next_decl_for_reg = None

        result.append(_transform_instruction(inst, prefix, reg_offset))
        i += 1

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
            merged_func[ns_label] = FuncRef(name=name, label=ns_label)
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


# ── Demand-driven filtering ──────────────────────────────────────


def _filter_reachable_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    entry_path: Path,
) -> tuple[dict[Path, ModuleUnit], dict[Path, list[Path]]]:
    """Filter modules to only those reachable from the entry point.

    Performs a reachability walk starting from entry_path through the import_graph,
    including only modules that are transitively reachable. Returns filtered
    modules dict and import_graph (both with unreachable nodes removed).

    Args:
        modules: All compiled modules.
        import_graph: Import graph for all modules.
        entry_path: The entry point module (typically the last in topo_order).

    Returns:
        A tuple of (filtered_modules, filtered_import_graph) containing only
        reachable modules and their dependencies.
    """
    if entry_path not in modules:
        # Entry not in modules — return everything (shouldn't happen)
        return modules, import_graph

    reachable: set[Path] = set()
    queue = [entry_path]

    while queue:
        path = queue.pop(0)
        if path in reachable:
            continue
        reachable.add(path)
        for dep in import_graph.get(path, []):
            if dep not in reachable:
                queue.append(dep)

    # Filter both dicts
    filtered_modules = {p: m for p, m in modules.items() if p in reachable}
    filtered_graph = {
        p: [d for d in deps if d in reachable]
        for p, deps in import_graph.items()
        if p in reachable
    }

    return filtered_modules, filtered_graph


# ── Main linker ──────────────────────────────────────────────────


def link_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    project_root: Path,
    topo_order: list[Path],
    language: Language,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
    symbol_table: SymbolTable | None = None,
    data_layout: dict[str, dict] = {},
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
    if symbol_table is None:
        symbol_table = SymbolTable.empty()

    prefixes = {path: module_prefix(path, project_root) for path in modules}
    resolved = _collect_resolved_imports(modules, import_graph)

    # Processing order: topo_order already has deps first, entry last
    processing_order = [p for p in topo_order if p in modules]

    # Demand-driven filtering: keep only modules reachable from entry point
    if processing_order:
        entry_path = processing_order[-1]
        modules, import_graph = _filter_reachable_modules(
            modules, import_graph, entry_path
        )
        # Recompute prefixes and resolved for the filtered modules
        prefixes = {path: module_prefix(path, project_root) for path in modules}
        resolved = _collect_resolved_imports(modules, import_graph)
        processing_order = [p for p in processing_order if p in modules]

    # Build merged IR with a single entry label
    all_ir: list[InstructionBase] = [Label_(label=CodeLabel("entry"))]
    reg_offset = 0

    for file_path in processing_order:
        module = modules[file_path]
        prefix = prefixes[file_path]
        module_resolved = resolved.get(file_path, set())

        transformed = _transform_module(
            module,
            prefix,
            reg_offset,
            module_resolved,
            modules,
            import_graph,
            file_path,
            prefixes,
        )
        all_ir.extend(transformed)
        reg_offset += max_register_number(module.ir) + 1

    # Build merged symbol tables, CFG, and registry
    merged_func_symbols, merged_class_symbols = _merge_symbol_tables(modules, prefixes)
    for module in modules.values():
        symbol_table.classes.update(module.symbol_table.classes)
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
        language=language,
        import_graph=import_graph,
        type_env_builder=type_env_builder,
        symbol_table=symbol_table,
        data_layout=data_layout,
        func_symbol_table=merged_func_symbols,
        class_symbol_table=merged_class_symbols,
    )
