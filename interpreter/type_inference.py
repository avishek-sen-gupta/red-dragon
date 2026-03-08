"""Static type inference pass — walks IR instructions and builds a TypeEnvironment.

**Type representation:** The entire type pipeline operates on ``TypeExpr``
objects end-to-end.  Frontends call ``parse_type()`` at the seeding
boundary (``TreeSitterEmitContext.seed_*``), so ``TypeEnvironmentBuilder``
already stores ``TypeExpr``.  This module copies those values directly —
no string parsing or serialization anywhere in the pipeline.

The ``UNKNOWN`` sentinel (an ``UnknownType`` instance) replaces empty
strings as the "type not yet known" marker.  It is falsy, so existing
``if type_expr:`` checks continue to work.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter import constants
from interpreter.constants import CanonicalLiteral, TypeName
from interpreter.function_signature import FunctionSignature
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment import TypeEnvironment
from interpreter.type_environment_builder import TypeEnvironmentBuilder
from interpreter.type_expr import (
    TypeExpr,
    ScalarType,
    UNKNOWN,
    array_of,
    scalar,
)
from interpreter.type_resolver import TypeResolver

logger = logging.getLogger(__name__)

_BUILTIN_RETURN_TYPES: dict[str, TypeExpr] = {
    "len": scalar(TypeName.INT),
    "int": scalar(TypeName.INT),
    "float": scalar(TypeName.FLOAT),
    "str": scalar(TypeName.STRING),
    "bool": scalar(TypeName.BOOL),
    "range": scalar(TypeName.ARRAY),
    "abs": scalar(TypeName.NUMBER),
    "max": scalar(TypeName.NUMBER),
    "min": scalar(TypeName.NUMBER),
    "arrayOf": scalar(TypeName.ARRAY),
    "intArrayOf": scalar(TypeName.ARRAY),
    "Array": scalar(TypeName.ARRAY),
}

_BUILTIN_METHOD_RETURN_TYPES: dict[str, TypeExpr] = {
    # String → String
    "upper": scalar(TypeName.STRING),
    "lower": scalar(TypeName.STRING),
    "strip": scalar(TypeName.STRING),
    "lstrip": scalar(TypeName.STRING),
    "rstrip": scalar(TypeName.STRING),
    "replace": scalar(TypeName.STRING),
    "format": scalar(TypeName.STRING),
    "join": scalar(TypeName.STRING),
    "capitalize": scalar(TypeName.STRING),
    "title": scalar(TypeName.STRING),
    "swapcase": scalar(TypeName.STRING),
    "trim": scalar(TypeName.STRING),
    "toLowerCase": scalar(TypeName.STRING),
    "toUpperCase": scalar(TypeName.STRING),
    "substring": scalar(TypeName.STRING),
    "charAt": scalar(TypeName.STRING),
    "toString": scalar(TypeName.STRING),
    "concat": scalar(TypeName.STRING),
    "downcase": scalar(TypeName.STRING),
    "upcase": scalar(TypeName.STRING),
    "chomp": scalar(TypeName.STRING),
    "chop": scalar(TypeName.STRING),
    "gsub": scalar(TypeName.STRING),
    "sub": scalar(TypeName.STRING),
    "encode": scalar(TypeName.STRING),
    "decode": scalar(TypeName.STRING),
    # → Int
    "find": scalar(TypeName.INT),
    "index": scalar(TypeName.INT),
    "rfind": scalar(TypeName.INT),
    "rindex": scalar(TypeName.INT),
    "count": scalar(TypeName.INT),
    "indexOf": scalar(TypeName.INT),
    "lastIndexOf": scalar(TypeName.INT),
    "size": scalar(TypeName.INT),
    "length": scalar(TypeName.INT),
    # → Bool
    "startswith": scalar(TypeName.BOOL),
    "endswith": scalar(TypeName.BOOL),
    "isdigit": scalar(TypeName.BOOL),
    "isalpha": scalar(TypeName.BOOL),
    "isalnum": scalar(TypeName.BOOL),
    "isupper": scalar(TypeName.BOOL),
    "islower": scalar(TypeName.BOOL),
    "isspace": scalar(TypeName.BOOL),
    "startsWith": scalar(TypeName.BOOL),
    "endsWith": scalar(TypeName.BOOL),
    "includes": scalar(TypeName.BOOL),
    "contains": scalar(TypeName.BOOL),
    "isEmpty": scalar(TypeName.BOOL),
    "has": scalar(TypeName.BOOL),
    # → Array
    "split": scalar(TypeName.ARRAY),
    "splitlines": scalar(TypeName.ARRAY),
    "rsplit": scalar(TypeName.ARRAY),
    "keys": scalar(TypeName.ARRAY),
    "values": scalar(TypeName.ARRAY),
    "items": scalar(TypeName.ARRAY),
    "entries": scalar(TypeName.ARRAY),
    "toArray": scalar(TypeName.ARRAY),
    "toList": scalar(TypeName.ARRAY),
}

_SELF_PARAM_NAMES = constants.SELF_PARAM_NAMES

_FUNC_REF_PATTERN = re.compile(r"<function:")
_FUNC_REF_EXTRACT = re.compile(constants.FUNC_REF_PATTERN)
_CLASS_REF_PATTERN = re.compile(r"<class:")


_GLOBAL_SCOPE = ""


@dataclass
class _InferenceContext:
    """Mutable bundle of all state accumulated during the inference walk."""

    register_types: dict[str, TypeExpr] = field(default_factory=dict)
    scoped_var_types: dict[str, dict[str, TypeExpr]] = field(default_factory=dict)
    func_return_types: dict[str, TypeExpr] = field(default_factory=dict)
    func_param_types: dict[str, list[tuple[str, TypeExpr]]] = field(
        default_factory=dict
    )
    current_func_label: str = ""
    current_class_name: str = ""
    class_method_types: dict[str, dict[str, TypeExpr]] = field(default_factory=dict)
    field_types: dict[str, dict[str, TypeExpr]] = field(default_factory=dict)
    array_element_types: dict[str, TypeExpr] = field(default_factory=dict)
    var_array_element_types: dict[str, TypeExpr] = field(default_factory=dict)
    register_source_var: dict[str, str] = field(default_factory=dict)

    def store_var_type(self, name: str, type_expr: TypeExpr) -> None:
        """Store a variable type in the current function scope.

        Does not overwrite if the variable already has a type in any scope
        (seeded types in _GLOBAL_SCOPE take precedence over inferred types).
        """
        if self.lookup_var_type(name):
            return
        scope = self.current_func_label
        scope_dict = self.scoped_var_types.setdefault(scope, {})
        scope_dict[name] = type_expr

    def lookup_var_type(self, name: str) -> TypeExpr:
        """Look up a variable type: current scope first, then global."""
        scope = self.current_func_label
        scope_dict = self.scoped_var_types.get(scope, {})
        if name in scope_dict:
            return scope_dict[name]
        global_dict = self.scoped_var_types.get(_GLOBAL_SCOPE, {})
        return global_dict.get(name, UNKNOWN)

    def flat_var_types(self) -> dict[str, TypeExpr]:
        """Flatten all scoped var types into a single dict for TypeEnvironment."""
        result: dict[str, TypeExpr] = {}
        for scope_dict in self.scoped_var_types.values():
            result.update(scope_dict)
        return result


def _promote_array_element_types(ctx: _InferenceContext) -> None:
    """Promote Array variables with known element types to Array[ElementType].

    After inference converges, variables typed as ``Array`` (or untyped) that
    have known element types are promoted to ``Array[ElementType]``.  Register
    types for array registers are also promoted.
    """
    for var_name, elem_type in ctx.var_array_element_types.items():
        for scope_dict in ctx.scoped_var_types.values():
            if var_name in scope_dict:
                current = scope_dict[var_name]
                if current == TypeName.ARRAY:
                    scope_dict[var_name] = array_of(elem_type)
                    logger.debug("Promoted %s: Array → Array[%s]", var_name, elem_type)

    for reg, elem_type in ctx.array_element_types.items():
        if ctx.register_types.get(reg, UNKNOWN) == TypeName.ARRAY:
            ctx.register_types[reg] = array_of(elem_type)


def _build_func_signatures(
    func_return_types: dict[str, TypeExpr],
    func_param_types: dict[str, list[tuple[str, TypeExpr]]],
) -> dict[str, FunctionSignature]:
    """Build signatures keyed only by user-facing function names.

    Internal labels (func_add_0) are excluded — only names that came
    through a <function:name@label> CONST mapping are included.
    """
    user_facing_names = {
        name
        for name in set(func_return_types) | set(func_param_types)
        if not name.startswith("func_")
    }

    return {
        name: FunctionSignature(
            params=tuple(func_param_types.get(name, [])),
            return_type=func_return_types.get(name, UNKNOWN),
        )
        for name in user_facing_names
    }


def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
) -> TypeEnvironment:
    """Walk *instructions* to fixpoint and return an immutable TypeEnvironment.

    Pre-seeded type info from ``type_env_builder`` (populated by the
    frontend during lowering) is merged first; the inference walk then
    adds inferred types on top.  The walk repeats until no new types are
    discovered, resolving forward references (e.g. function A calls
    function B which is defined later in the IR).

    Pure function — no mutation of the input instructions.
    """
    ctx = _InferenceContext(
        register_types=dict(type_env_builder.register_types),
        scoped_var_types={_GLOBAL_SCOPE: dict(type_env_builder.var_types)},
        func_return_types=dict(type_env_builder.func_return_types),
        func_param_types={
            k: list(v) for k, v in type_env_builder.func_param_types.items()
        },
    )

    prev_size = -1
    current_size = 0
    passes = 0
    while current_size > prev_size:
        prev_size = current_size
        for inst in instructions:
            _infer_instruction(inst, ctx, type_resolver)
        current_size = len(ctx.register_types) + len(ctx.func_return_types)
        passes += 1

    logger.debug("Type inference converged after %d pass(es)", passes)

    # Promote Array variables with known element types to Array[ElementType]
    _promote_array_element_types(ctx)

    # Build TypeEnvironment directly — no roundtrip through builder
    flat_vars = ctx.flat_var_types()
    func_signatures = _build_func_signatures(
        ctx.func_return_types, ctx.func_param_types
    )

    logger.debug(
        "Type inference complete: %d register types, %d variable types",
        len(ctx.register_types),
        len(flat_vars),
    )
    return TypeEnvironment(
        register_types=MappingProxyType(ctx.register_types),
        var_types=MappingProxyType(flat_vars),
        func_signatures=MappingProxyType(func_signatures),
    )


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
                param_type = ctx.register_types.get(inst.result_reg, UNKNOWN)
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
                ctx.register_types[inst.result_reg] = scalar(ctx.current_class_name)


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
            ret_type = ctx.func_return_types.get(func_label, UNKNOWN)
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
    var_type = ctx.lookup_var_type(str(name)) if name else UNKNOWN
    if inst.result_reg and var_type:
        ctx.register_types[inst.result_reg] = var_type
    # Propagate array element types from variable to register
    if inst.result_reg and str(name) in ctx.var_array_element_types:
        ctx.array_element_types[inst.result_reg] = ctx.var_array_element_types[
            str(name)
        ]


def _infer_store_var(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    name = inst.operands[0] if inst.operands else ""
    if not name:
        return
    if len(inst.operands) >= 2:
        value_reg = str(inst.operands[1])
        if value_reg in ctx.register_types:
            ctx.store_var_type(str(name), ctx.register_types[value_reg])
        # Track array element types at the variable level
        if value_reg in ctx.array_element_types:
            ctx.var_array_element_types[str(name)] = ctx.array_element_types[value_reg]


def _infer_binop(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 3:
        return
    operator = str(inst.operands[0])
    left_hint = ctx.register_types.get(str(inst.operands[1]), UNKNOWN)
    right_hint = ctx.register_types.get(str(inst.operands[2]), UNKNOWN)
    result = type_resolver.resolve_binop(operator, left_hint, right_hint)
    if result.result_type:
        ctx.register_types[inst.result_reg] = result.result_type


_UNOP_FIXED_TYPES: dict[str, TypeExpr] = {
    "not": scalar(TypeName.BOOL),
    "!": scalar(TypeName.BOOL),
    "#": scalar(TypeName.INT),
    "~": scalar(TypeName.INT),
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
    operand_hint = ctx.register_types.get(str(inst.operands[1]), UNKNOWN)
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
            ctx.register_types[inst.result_reg] = scalar(class_name)


def _infer_new_array(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = scalar(TypeName.ARRAY)


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
        ctx.register_types[inst.result_reg] = scalar("Region")


def _infer_load_region(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = scalar(TypeName.ARRAY)


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
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    value_type = ctx.register_types.get(value_reg, UNKNOWN)
    if class_name and value_type:
        ctx.field_types.setdefault(str(class_name), {})[field_name] = value_type


def _infer_load_field(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    obj_reg = str(inst.operands[0])
    field_name = str(inst.operands[1])
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    if class_name and str(class_name) in ctx.field_types:
        field_type = ctx.field_types[str(class_name)].get(field_name, UNKNOWN)
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
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    if class_name and str(class_name) in ctx.class_method_types:
        ret_type = ctx.class_method_types[str(class_name)].get(method_name, UNKNOWN)
        if ret_type:
            ctx.register_types[inst.result_reg] = ret_type
            return
    # Fallback: try func_return_types for unique method names
    if method_name in ctx.func_return_types:
        ctx.register_types[inst.result_reg] = ctx.func_return_types[method_name]
        return
    # Final fallback: builtin method return types (e.g. .upper()→String, .split()→Array)
    builtin_type = _BUILTIN_METHOD_RETURN_TYPES.get(method_name, UNKNOWN)
    if builtin_type:
        ctx.register_types[inst.result_reg] = builtin_type


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
    value_type = ctx.register_types.get(value_reg, UNKNOWN)
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
    element_type = ctx.array_element_types.get(arr_reg, UNKNOWN)
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
    ret_type = ctx.register_types.get(value_reg, UNKNOWN)
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


def _infer_const_type(raw: str) -> TypeExpr:
    """Infer a canonical type from a CONST literal string."""
    if raw in (CanonicalLiteral.TRUE, CanonicalLiteral.FALSE):
        return scalar(TypeName.BOOL)
    if raw == CanonicalLiteral.NONE:
        return UNKNOWN
    if _FUNC_REF_PATTERN.search(str(raw)):
        return UNKNOWN
    if _CLASS_REF_PATTERN.search(str(raw)):
        return UNKNOWN
    try:
        int(raw)
        return scalar(TypeName.INT)
    except (ValueError, TypeError):
        pass
    try:
        float(raw)
        return scalar(TypeName.FLOAT)
    except (ValueError, TypeError):
        pass
    if len(str(raw)) >= 2 and str(raw)[0] in ('"', "'") and str(raw)[-1] == str(raw)[0]:
        return scalar(TypeName.STRING)
    return UNKNOWN
