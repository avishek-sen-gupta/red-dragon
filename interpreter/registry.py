"""Function & Class Registry — scanning IR/CFG to catalogue functions and classes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ir import IRInstruction, Opcode
from .cfg import CFG
from . import constants

# ── Parse helpers ────────────────────────────────────────────────


@dataclass
class RefParseResult:
    """Result of parsing a function or class reference string."""

    matched: bool
    name: str = ""
    label: str = ""
    closure_id: str = ""


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
    """Parse '<class:name@label>' → RefParseResult."""
    if not isinstance(val, str):
        return RefParseResult(matched=False)
    m = RefPatterns.CLASS_RE.search(val)
    if not m:
        return RefParseResult(matched=False)
    return RefParseResult(matched=True, name=m.group(1), label=m.group(2))


# ── Registry ─────────────────────────────────────────────────────


@dataclass
class FunctionRegistry:
    # func_label → ordered list of parameter names
    func_params: dict[str, list[str]] = field(default_factory=dict)
    # class_name → {method_name → func_label}
    class_methods: dict[str, dict[str, str]] = field(default_factory=dict)
    # class_name → class_body_label
    classes: dict[str, str] = field(default_factory=dict)


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
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Scan IR to find classes and their methods.

    Returns (classes, class_methods) where:
    - classes: class_name → class_body_label
    - class_methods: class_name → {method_name → func_label}
    """
    classes: dict[str, str] = {}
    class_methods: dict[str, dict[str, str]] = {}

    # First pass: find class constants
    for inst in instructions:
        if inst.opcode != Opcode.CONST or not inst.operands:
            continue
        cr = _parse_class_ref(str(inst.operands[0]))
        if cr.matched:
            classes[cr.name] = cr.label

    # Second pass: identify class scopes and their methods
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
                in_class = ""

        if in_class and inst.opcode == Opcode.CONST and inst.operands:
            fr = _parse_func_ref(str(inst.operands[0]))
            if fr.matched:
                class_methods[in_class][fr.name] = fr.label

    return classes, class_methods


def build_registry(instructions: list[IRInstruction], cfg: CFG) -> FunctionRegistry:
    """Scan IR and CFG to build a function/class registry."""
    reg = FunctionRegistry()
    reg.func_params = _scan_func_params(cfg)
    reg.classes, reg.class_methods = _scan_classes(instructions)
    return reg
