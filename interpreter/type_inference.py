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
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.type_resolver import TypeResolver

logger = logging.getLogger(__name__)

_BUILTIN_RETURN_TYPES: dict[str, str] = {
    "len": TypeName.INT,
    "int": TypeName.INT,
    "float": TypeName.FLOAT,
    "str": TypeName.STRING,
    "bool": TypeName.BOOL,
    "range": TypeName.ARRAY,
    "abs": TypeName.NUMBER,
    "max": TypeName.NUMBER,
    "min": TypeName.NUMBER,
    "arrayOf": TypeName.ARRAY,
    "intArrayOf": TypeName.ARRAY,
    "Array": TypeName.ARRAY,
}

_SELF_PARAM_NAMES = frozenset({"self", "this", "$this"})

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
    current_class_name: str = ""
    class_method_types: dict[str, dict[str, str]] = field(default_factory=dict)
    field_types: dict[str, dict[str, str]] = field(default_factory=dict)
    array_element_types: dict[str, str] = field(default_factory=dict)
    register_source_var: dict[str, str] = field(default_factory=dict)


def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
) -> TypeEnvironment:
    """Walk *instructions* once and return an immutable TypeEnvironment.

    Pre-seeded type info from ``type_env_builder`` (populated by the
    frontend during lowering) is merged first; the inference walk then
    adds inferred types on top.

    Pure function — no mutation of the input instructions.
    """
    ctx = _InferenceContext(
        register_types=dict(type_env_builder.register_types),
        var_types=dict(type_env_builder.var_types),
        func_return_types=dict(type_env_builder.func_return_types),
        func_param_types={
            k: list(v) for k, v in type_env_builder.func_param_types.items()
        },
    )

    for inst in instructions:
        _infer_instruction(inst, ctx, type_resolver)

    # Use builder for final assembly
    final_builder = TypeEnvironmentBuilder(
        register_types=ctx.register_types,
        var_types=ctx.var_types,
        func_return_types=ctx.func_return_types,
        func_param_types=ctx.func_param_types,
    )

    logger.debug(
        "Type inference complete: %d register types, %d variable types",
        len(ctx.register_types),
        len(ctx.var_types),
    )
    return final_builder.build()


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
    if not inst.label:
        return
    if inst.label.startswith(constants.FUNC_LABEL_PREFIX):
        ctx.current_func_label = inst.label
        ctx.func_param_types.setdefault(inst.label, [])
        # func_return_types are pre-seeded by the builder; no inst.type_hint read
    elif inst.label.startswith(
        constants.CLASS_LABEL_PREFIX
    ) and not inst.label.startswith(constants.END_CLASS_LABEL_PREFIX):
        ctx.current_class_name = inst.label.removeprefix(
            constants.CLASS_LABEL_PREFIX
        ).rsplit("_", 1)[0]
        ctx.class_method_types.setdefault(ctx.current_class_name, {})
        ctx.current_func_label = ""
    else:
        ctx.current_func_label = ""


def _infer_symbolic(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    # register_types are pre-seeded by the builder; no inst.type_hint read

    # Collect param types if inside a function (only if not already seeded)
    if ctx.current_func_label and inst.operands:
        operand = str(inst.operands[0])
        if operand.startswith("param:"):
            param_name = operand[len("param:") :]
            # Skip param append when func already seeded in func_param_types
            already_seeded = any(
                p[0] == param_name
                for p in ctx.func_param_types.get(ctx.current_func_label, [])
            )
            if not already_seeded:
                param_type = ctx.register_types.get(inst.result_reg, "")
                ctx.func_param_types[ctx.current_func_label].append(
                    (param_name, param_type)
                )

    # self/this typing: assign class name when inside a class scope
    if (
        inst.result_reg
        and inst.result_reg not in ctx.register_types
        and ctx.current_class_name
        and inst.operands
    ):
        operand = str(inst.operands[0])
        if operand.startswith("param:"):
            param_name = operand[len("param:") :]
            if param_name in _SELF_PARAM_NAMES:
                ctx.register_types[inst.result_reg] = ctx.current_class_name


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
        if ctx.current_class_name:
            ret_type = ctx.func_return_types.get(func_label, "")
            ctx.class_method_types.setdefault(ctx.current_class_name, {})[
                func_name
            ] = ret_type
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
    if inst.result_reg and name:
        ctx.register_source_var[inst.result_reg] = str(name)
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
    # var_types may be pre-seeded by the builder; skip if already known
    if name in ctx.var_types:
        return
    if len(inst.operands) >= 2:
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


_UNOP_FIXED_TYPES: dict[str, str] = {
    "not": TypeName.BOOL,
    "!": TypeName.BOOL,
    "#": TypeName.INT,
}


def _infer_unop(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    operator = str(inst.operands[0])
    fixed = _UNOP_FIXED_TYPES.get(operator)
    if fixed:
        ctx.register_types[inst.result_reg] = fixed
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
    if not inst.result_reg:
        return
    # register_types may be pre-seeded by the builder (e.g., constructor type_hint)
    if inst.result_reg in ctx.register_types:
        return
    if inst.operands:
        func_name = str(inst.operands[0])
        if func_name in ctx.func_return_types:
            ctx.register_types[inst.result_reg] = ctx.func_return_types[func_name]
        elif func_name in _BUILTIN_RETURN_TYPES:
            ctx.register_types[inst.result_reg] = _BUILTIN_RETURN_TYPES[func_name]


def _infer_alloc_region(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = "Region"


def _infer_load_region(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = TypeName.ARRAY


def _infer_store_field(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if len(inst.operands) < 3:
        return
    obj_reg = str(inst.operands[0])
    field_name = str(inst.operands[1])
    value_reg = str(inst.operands[2])
    class_name = ctx.register_types.get(obj_reg, "")
    value_type = ctx.register_types.get(value_reg, "")
    if class_name and value_type:
        ctx.field_types.setdefault(class_name, {})[field_name] = value_type


def _infer_load_field(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    obj_reg = str(inst.operands[0])
    field_name = str(inst.operands[1])
    class_name = ctx.register_types.get(obj_reg, "")
    if class_name and class_name in ctx.field_types:
        field_type = ctx.field_types[class_name].get(field_name, "")
        if field_type:
            ctx.register_types[inst.result_reg] = field_type


def _infer_call_method(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    obj_reg = str(inst.operands[0])
    method_name = str(inst.operands[1])
    class_name = ctx.register_types.get(obj_reg, "")
    if class_name and class_name in ctx.class_method_types:
        ret_type = ctx.class_method_types[class_name].get(method_name, "")
        if ret_type:
            ctx.register_types[inst.result_reg] = ret_type
            return
    # Fallback: try func_return_types for unique method names
    if method_name in ctx.func_return_types:
        ctx.register_types[inst.result_reg] = ctx.func_return_types[method_name]


def _infer_call_unknown(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or not inst.operands:
        return
    target_reg = str(inst.operands[0])
    func_name = ctx.register_source_var.get(target_reg, "")
    if not func_name:
        return
    if func_name in ctx.func_return_types:
        ctx.register_types[inst.result_reg] = ctx.func_return_types[func_name]
    elif func_name in _BUILTIN_RETURN_TYPES:
        ctx.register_types[inst.result_reg] = _BUILTIN_RETURN_TYPES[func_name]


def _infer_store_index(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if len(inst.operands) < 3:
        return
    arr_reg = str(inst.operands[0])
    value_reg = str(inst.operands[2])
    value_type = ctx.register_types.get(value_reg, "")
    if value_type:
        ctx.array_element_types[arr_reg] = value_type


def _infer_load_index(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    arr_reg = str(inst.operands[0])
    element_type = ctx.array_element_types.get(arr_reg, "")
    if element_type:
        ctx.register_types[inst.result_reg] = element_type


def _infer_return(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not ctx.current_func_label:
        return
    if ctx.current_func_label in ctx.func_return_types:
        return
    if not inst.operands:
        return
    value_reg = str(inst.operands[0])
    ret_type = ctx.register_types.get(value_reg, "")
    if ret_type:
        ctx.func_return_types[ctx.current_func_label] = ret_type


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
    Opcode.CALL_METHOD: _infer_call_method,
    Opcode.STORE_FIELD: _infer_store_field,
    Opcode.LOAD_FIELD: _infer_load_field,
    Opcode.ALLOC_REGION: _infer_alloc_region,
    Opcode.LOAD_REGION: _infer_load_region,
    Opcode.RETURN: _infer_return,
    Opcode.CALL_UNKNOWN: _infer_call_unknown,
    Opcode.STORE_INDEX: _infer_store_index,
    Opcode.LOAD_INDEX: _infer_load_index,
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
