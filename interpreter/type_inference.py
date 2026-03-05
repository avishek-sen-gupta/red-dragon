"""Static type inference pass — walks IR instructions and builds a TypeEnvironment."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter import constants
from interpreter.constants import TypeName
from interpreter.function_signature import FunctionSignature
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment import TypeEnvironment
from interpreter.type_resolver import TypeResolver

logger = logging.getLogger(__name__)

_FUNC_REF_PATTERN = re.compile(r"<function:")
_FUNC_REF_EXTRACT = re.compile(constants.FUNC_REF_PATTERN)
_CLASS_REF_PATTERN = re.compile(r"<class:")


@dataclass
class _InferenceContext:
    """Mutable bundle of all state accumulated during the inference walk."""

    register_types: dict[str, str] = field(default_factory=dict)
    var_types: dict[str, str] = field(default_factory=dict)
    func_return_types: dict[str, str] = field(default_factory=dict)
    func_param_types: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    current_func_label: str = ""


def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
) -> TypeEnvironment:
    """Walk *instructions* once and return an immutable TypeEnvironment.

    Pure function — no mutation of the input instructions.
    """
    ctx = _InferenceContext()

    for inst in instructions:
        _infer_instruction(inst, ctx, type_resolver)

    # Build func_signatures from the label→name mappings only (user-facing names)
    func_signatures = _build_func_signatures(ctx)

    logger.debug(
        "Type inference complete: %d register types, %d variable types, %d function signatures",
        len(ctx.register_types),
        len(ctx.var_types),
        len(func_signatures),
    )
    return TypeEnvironment(
        register_types=MappingProxyType(ctx.register_types),
        var_types=MappingProxyType(ctx.var_types),
        func_signatures=MappingProxyType(func_signatures),
    )


def _build_func_signatures(ctx: _InferenceContext) -> dict[str, FunctionSignature]:
    """Build signatures keyed only by user-facing function names.

    Internal labels (func_add_0) are excluded — only names that came
    through a <function:name@label> CONST mapping are included.
    """
    user_facing_names = {
        name
        for name in set(ctx.func_return_types) | set(ctx.func_param_types)
        if not name.startswith("func_")
    }

    return {
        name: FunctionSignature(
            params=tuple(ctx.func_param_types.get(name, [])),
            return_type=ctx.func_return_types.get(name, ""),
        )
        for name in user_facing_names
    }


def _infer_instruction(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    """Infer and record the output type for a single instruction."""
    handler = _DISPATCH.get(inst.opcode)
    if handler:
        handler(inst, ctx, type_resolver)


def _infer_label(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.label and inst.label.startswith("func_"):
        ctx.current_func_label = inst.label
        ctx.func_param_types.setdefault(inst.label, [])
        if inst.type_hint:
            ctx.func_return_types[inst.label] = inst.type_hint
    elif inst.label:
        # Leaving a function scope (e.g. end_add_0 or another non-func label)
        ctx.current_func_label = ""


def _infer_symbolic(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.type_hint and inst.result_reg:
        ctx.register_types[inst.result_reg] = inst.type_hint

    # Collect param types if inside a function
    if ctx.current_func_label and inst.operands:
        operand = str(inst.operands[0])
        if operand.startswith("param:"):
            param_name = operand[len("param:") :]
            param_type = inst.type_hint or ""
            ctx.func_param_types[ctx.current_func_label].append(
                (param_name, param_type)
            )


def _infer_const(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg:
        return
    raw = str(inst.operands[0]) if inst.operands else "None"
    # If this is a function reference, extract name→return-type and name→param-types mappings
    match = _FUNC_REF_EXTRACT.search(raw)
    if match:
        func_name, func_label = match.group(1), match.group(2)
        if func_label in ctx.func_return_types:
            ctx.func_return_types[func_name] = ctx.func_return_types[func_label]
        if func_label in ctx.func_param_types:
            ctx.func_param_types[func_name] = ctx.func_param_types[func_label]
        return
    inferred = _infer_const_type(raw)
    if inferred:
        ctx.register_types[inst.result_reg] = inferred


def _infer_load_var(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    name = inst.operands[0] if inst.operands else ""
    if inst.result_reg and name in ctx.var_types:
        ctx.register_types[inst.result_reg] = ctx.var_types[name]


def _infer_store_var(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    name = inst.operands[0] if inst.operands else ""
    if not name:
        return
    if inst.type_hint:
        ctx.var_types[name] = inst.type_hint
    elif len(inst.operands) >= 2:
        value_reg = str(inst.operands[1])
        if value_reg in ctx.register_types:
            ctx.var_types[name] = ctx.register_types[value_reg]


def _infer_binop(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 3:
        return
    operator = str(inst.operands[0])
    left_hint = ctx.register_types.get(str(inst.operands[1]), "")
    right_hint = ctx.register_types.get(str(inst.operands[2]), "")
    result = type_resolver.resolve_binop(operator, left_hint, right_hint)
    if result.result_type:
        ctx.register_types[inst.result_reg] = result.result_type


def _infer_unop(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    operand_hint = ctx.register_types.get(str(inst.operands[1]), "")
    if operand_hint:
        ctx.register_types[inst.result_reg] = operand_hint


def _infer_new_object(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg and inst.operands:
        class_name = str(inst.operands[0])
        if class_name:
            ctx.register_types[inst.result_reg] = class_name


def _infer_new_array(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = TypeName.ARRAY


def _infer_call_function(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg and inst.type_hint:
        ctx.register_types[inst.result_reg] = inst.type_hint
    elif inst.result_reg and inst.operands:
        func_name = str(inst.operands[0])
        if func_name in ctx.func_return_types:
            ctx.register_types[inst.result_reg] = ctx.func_return_types[func_name]


_DISPATCH: dict[Opcode, callable] = {
    Opcode.LABEL: _infer_label,
    Opcode.SYMBOLIC: _infer_symbolic,
    Opcode.CONST: _infer_const,
    Opcode.LOAD_VAR: _infer_load_var,
    Opcode.STORE_VAR: _infer_store_var,
    Opcode.BINOP: _infer_binop,
    Opcode.UNOP: _infer_unop,
    Opcode.NEW_OBJECT: _infer_new_object,
    Opcode.NEW_ARRAY: _infer_new_array,
    Opcode.CALL_FUNCTION: _infer_call_function,
}


def _infer_const_type(raw: str) -> str:
    """Infer a canonical type from a CONST literal string."""
    if raw in ("True", "False"):
        return TypeName.BOOL
    if raw == "None":
        return ""
    if _FUNC_REF_PATTERN.search(str(raw)):
        return ""
    if _CLASS_REF_PATTERN.search(str(raw)):
        return ""
    try:
        int(raw)
        return TypeName.INT
    except (ValueError, TypeError):
        pass
    try:
        float(raw)
        return TypeName.FLOAT
    except (ValueError, TypeError):
        pass
    if len(str(raw)) >= 2 and str(raw)[0] in ('"', "'") and str(raw)[-1] == str(raw)[0]:
        return TypeName.STRING
    return ""
