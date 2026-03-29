"""Function & Class Registry — scanning IR/CFG to catalogue functions and classes."""

from __future__ import annotations

from dataclasses import dataclass, field

from interpreter.ir import CodeLabel
from interpreter.instructions import Const, InstructionBase, Label_, Symbolic
from interpreter.cfg import CFG
from interpreter.func_name import FuncName
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter import constants

# ── Registry ─────────────────────────────────────────────────────


@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[CodeLabel, list[str]] = field(default_factory=dict)
    # class_name → {method_name → [func_label, ...]}  (supports overloads)
    class_methods: dict[str, dict[FuncName, list[CodeLabel]]] = field(
        default_factory=dict
    )
    # class_name → class_body_label
    classes: dict[str, CodeLabel] = field(default_factory=dict)
    # class_name → linearized parent chain (MRO, excluding self)
    class_parents: dict[str, list[str]] = field(default_factory=dict)
    # function_name → FuncRef (name→label mapping for call resolution)
    func_refs: dict[FuncName, FuncRef] = field(default_factory=dict)

    def lookup_func(self, name: FuncName) -> FuncRef | None:
        return self.func_refs.get(name)

    def lookup_methods(self, class_name: str, name: FuncName) -> list[CodeLabel]:
        return self.class_methods.get(class_name, {}).get(name, [])

    def register_func(self, name: FuncName, ref: FuncRef) -> None:
        self.func_refs[name] = ref

    def register_method(
        self, class_name: str, name: FuncName, label: CodeLabel
    ) -> None:
        self.class_methods.setdefault(class_name, {}).setdefault(name, []).append(label)


def _is_func_label(label: str | CodeLabel) -> bool:
    """Check if a label is a function entry label, possibly namespaced.

    Matches: ``func_foo_0``, ``utils.func_foo_0``, ``src.utils.func_foo_0``.
    """
    s = str(label)
    return (
        s.startswith(constants.FUNC_LABEL_PREFIX)
        or f".{constants.FUNC_LABEL_PREFIX}" in s
    )


def _is_class_label(label: str | CodeLabel) -> bool:
    """Check if a label is a class entry label, possibly namespaced."""
    s = str(label)
    return (
        (
            s.startswith(constants.CLASS_LABEL_PREFIX)
            or f".{constants.CLASS_LABEL_PREFIX}" in s
        )
        or (
            s.startswith(constants.PRELUDE_CLASS_LABEL_PREFIX)
            or f".{constants.PRELUDE_CLASS_LABEL_PREFIX}" in s
        )
    ) and not _is_end_class_label(label)


def _is_end_class_label(label: str | CodeLabel) -> bool:
    """Check if a label is an end-class label, possibly namespaced."""
    s = str(label)
    return (
        s.startswith(constants.END_CLASS_LABEL_PREFIX)
        or f".{constants.END_CLASS_LABEL_PREFIX}" in s
        or s.startswith(constants.PRELUDE_END_CLASS_LABEL_PREFIX)
        or f".{constants.PRELUDE_END_CLASS_LABEL_PREFIX}" in s
    )


def _scan_func_params(cfg: CFG) -> dict[CodeLabel, list[str]]:
    """Extract parameter names from function blocks in the CFG."""
    result: dict[CodeLabel, list[str]] = {}
    for label, block in cfg.blocks.items():
        if not _is_func_label(label):
            continue
        params = [
            str(t.hint)[len(constants.PARAM_PREFIX) :]
            for inst in block.instructions
            if inst.operands
            and isinstance((t := inst), Symbolic)
            and str(t.hint).startswith(constants.PARAM_PREFIX)
        ]
        result[label] = params
    return result


def _scan_classes(
    instructions: list[InstructionBase],
    func_symbol_table: dict[CodeLabel, FuncRef] = {},
    class_symbol_table: dict[CodeLabel, ClassRef] = {},
) -> tuple[
    dict[str, CodeLabel],
    dict[str, dict[FuncName, list[CodeLabel]]],
    dict[str, list[str]],
]:
    """Scan IR to find classes, their methods, and parent chains.

    Returns (classes, class_methods, class_parents) where:
    - classes: class_name → class_body_label
    - class_methods: class_name → {method_name → [func_label, ...]}
    - class_parents: class_name → linearized parent chain (MRO, excluding self)
    """
    classes: dict[str, CodeLabel] = {}
    class_methods: dict[str, dict[FuncName, list[CodeLabel]]] = {}
    class_parents: dict[str, list[str]] = {}

    # First pass: populate from class_symbol_table (new path).
    for label, cref in class_symbol_table.items():
        classes[cref.name] = cref.label
        if cref.parents:
            class_parents[cref.name] = list(cref.parents)

    # Second pass: identify class scopes and their methods.
    # Python emits methods inside the class scope (class_X ... end_class_X).
    # Java/C#/Scala hoist methods after end_class_X (so they execute at top
    # level for field initializers and static blocks). To handle both layouts,
    # we keep in_class set after end_class — the next class_X label for a
    # *different* class will reset it.
    in_class: str = ""
    for inst in instructions:
        if isinstance(inst, Label_) and inst.label.is_present():
            is_class_start = inst.label.is_class()
            is_class_end = inst.label.is_end_class()
            if is_class_start:
                for cname, clabel in classes.items():
                    if inst.label == clabel:
                        in_class = cname
                        if cname not in class_methods:
                            class_methods[cname] = {}
                        break
            elif is_class_end:
                # Keep in_class set — hoisted methods may follow end_class
                pass

        if in_class and inst.operands and isinstance((t := inst), Const):
            operand = str(t.value)
            if operand in func_symbol_table:
                ref = func_symbol_table[operand]
                class_methods[in_class].setdefault(FuncName(ref.name), []).append(
                    ref.label
                )

    return classes, class_methods, class_parents


def _expand_parent_chains(
    class_parents: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Expand direct parent lists into full linearized MRO chains.

    For single inheritance, if Dog -> Animal -> Object, then
    class_parents["Dog"] should be ["Animal", "Object"], not just ["Animal"].
    """
    expanded: dict[str, list[str]] = {}
    for cls in class_parents:
        chain: list[str] = []
        seen: set[str] = set()
        queue = list(class_parents.get(cls, []))
        while queue:
            parent = queue.pop(0)
            if parent in seen:
                continue
            seen.add(parent)
            chain.append(parent)
            queue.extend(class_parents.get(parent, []))
        expanded[cls] = chain
    return expanded


def build_registry(
    instructions: list[InstructionBase],
    cfg: CFG,
    func_symbol_table: dict[CodeLabel, FuncRef] = {},
    class_symbol_table: dict[CodeLabel, ClassRef] = {},
) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()
    reg.func_params = _scan_func_params(cfg)
    reg.classes, reg.class_methods, direct_parents = _scan_classes(
        instructions, func_symbol_table, class_symbol_table
    )
    reg.class_parents = _expand_parent_chains(direct_parents)
    reg.func_refs = {FuncName(ref.name): ref for ref in func_symbol_table.values()}
    return reg
