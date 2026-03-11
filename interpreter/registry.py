"""Function & Class Registry — scanning IR/CFG to catalogue functions and classes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from interpreter.ir import IRInstruction, Opcode
from interpreter.cfg import CFG
from interpreter import constants

# ── Parse helpers ────────────────────────────────────────────────


@dataclass
class RefParseResult:
    """Result of parsing a function or class reference string."""

    matched: bool
    name: str = ""
    label: str = ""
    closure_id: str = ""
    parents: list[str] = field(default_factory=list)


class RefPatterns:
    """Compiled regex patterns for function/class references."""

    FUNC_RE = re.compile(constants.FUNC_REF_PATTERN)
    CLASS_RE = re.compile(constants.CLASS_REF_PATTERN)


def _parse_func_ref(val: Any) -> RefParseResult:
    """Parse '<function:name@label>' or '<function:name@label#closure_id>'."""
    if not isinstance(val, str):
        return RefParseResult(matched=False)
    m = RefPatterns.FUNC_RE.search(val)
    if not m:
        return RefParseResult(matched=False)
    return RefParseResult(
        matched=True,
        name=m.group(1),
        label=m.group(2),
        closure_id=m.group(3) or "",
    )


def _parse_class_ref(val: Any) -> RefParseResult:
    """Parse '<class:name@label>' or '<class:name@label:Parent1,Parent2>'."""
    if not isinstance(val, str):
        return RefParseResult(matched=False)
    m = RefPatterns.CLASS_RE.search(val)
    if not m:
        return RefParseResult(matched=False)
    parents_str = m.group(3) or ""
    parents = [p for p in parents_str.split(",") if p]
    return RefParseResult(
        matched=True, name=m.group(1), label=m.group(2), parents=parents
    )


# ── Registry ─────────────────────────────────────────────────────


@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[str, list[str]] = field(default_factory=dict)
    # class_name → {method_name → func_label}
    class_methods: dict[str, dict[str, str]] = field(default_factory=dict)
    # class_name → class_body_label
    classes: dict[str, str] = field(default_factory=dict)
    # class_name → linearized parent chain (MRO, excluding self)
    class_parents: dict[str, list[str]] = field(default_factory=dict)


def _scan_func_params(cfg: CFG) -> dict[str, list[str]]:
    """Extract parameter names from function blocks in the CFG."""
    result: dict[str, list[str]] = {}
    for label, block in cfg.blocks.items():
        if not label.startswith(constants.FUNC_LABEL_PREFIX):
            continue
        params = [
            str(inst.operands[0])[len(constants.PARAM_PREFIX) :]
            for inst in block.instructions
            if inst.opcode == Opcode.SYMBOLIC
            and inst.operands
            and str(inst.operands[0]).startswith(constants.PARAM_PREFIX)
        ]
        result[label] = params
    return result


def _scan_classes(
    instructions: list[IRInstruction],
) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, list[str]]]:
    """Scan IR to find classes, their methods, and parent chains.

    Returns (classes, class_methods, class_parents) where:
    - classes: class_name → class_body_label
    - class_methods: class_name → {method_name → func_label}
    - class_parents: class_name → linearized parent chain (MRO, excluding self)
    """
    classes: dict[str, str] = {}
    class_methods: dict[str, dict[str, str]] = {}
    class_parents: dict[str, list[str]] = {}

    # First pass: find class constants and aliases.
    # Track which register holds which class ref so that a subsequent
    # STORE_VAR with a different name can register an alias
    # (e.g. `const Foo = class { ... }` → class ref is __anon_class_0,
    # variable is Foo).
    reg_to_class: dict[str, str] = {}
    for inst in instructions:
        if inst.opcode == Opcode.CONST and inst.operands:
            cr = _parse_class_ref(str(inst.operands[0]))
            if cr.matched:
                classes[cr.name] = cr.label
                if cr.parents:
                    class_parents[cr.name] = cr.parents
                if inst.result_reg:
                    reg_to_class[inst.result_reg] = cr.name
        elif inst.opcode == Opcode.STORE_VAR and len(inst.operands) >= 2:
            var_name = inst.operands[0]
            reg = inst.operands[1]
            class_name = reg_to_class.get(reg, "")
            if class_name and var_name != class_name:
                classes[var_name] = classes[class_name]
                if class_name in class_parents:
                    class_parents[var_name] = class_parents[class_name]

    # Second pass: identify class scopes and their methods.
    # Python emits methods inside the class scope (class_X ... end_class_X).
    # Java/C#/Scala hoist methods after end_class_X (so they execute at top
    # level for field initializers and static blocks). To handle both layouts,
    # we keep in_class set after end_class — the next class_X label for a
    # *different* class will reset it.
    in_class: str = ""
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.startswith(
                constants.CLASS_LABEL_PREFIX
            ) and not inst.label.startswith(constants.END_CLASS_LABEL_PREFIX):
                for cname, clabel in classes.items():
                    if inst.label == clabel:
                        in_class = cname
                        if cname not in class_methods:
                            class_methods[cname] = {}
                        break
            elif inst.label.startswith(constants.END_CLASS_LABEL_PREFIX):
                # Keep in_class set — hoisted methods may follow end_class
                pass

        if in_class and inst.opcode == Opcode.CONST and inst.operands:
            fr = _parse_func_ref(str(inst.operands[0]))
            if fr.matched:
                class_methods[in_class][fr.name] = fr.label

    # Propagate methods to aliases: if multiple class names share a label,
    # ensure all of them have the same methods dict.
    label_to_methods: dict[str, dict[str, str]] = {}
    for cname, clabel in classes.items():
        if cname in class_methods:
            label_to_methods[clabel] = class_methods[cname]
    for cname, clabel in classes.items():
        if cname not in class_methods and clabel in label_to_methods:
            class_methods[cname] = label_to_methods[clabel]

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


def build_registry(instructions: list[IRInstruction], cfg: CFG) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()
    reg.func_params = _scan_func_params(cfg)
    reg.classes, reg.class_methods, direct_parents = _scan_classes(instructions)
    reg.class_parents = _expand_parent_chains(direct_parents)
    return reg
