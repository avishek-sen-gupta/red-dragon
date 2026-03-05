"""Static type inference pass — walks IR instructions and builds a TypeEnvironment."""

from __future__ import annotations

import logging
import re
from types import MappingProxyType

from interpreter.constants import TypeName
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment import TypeEnvironment
from interpreter.type_resolver import TypeResolver

logger = logging.getLogger(__name__)

_FUNC_REF_PATTERN = re.compile(r"<function:")
_CLASS_REF_PATTERN = re.compile(r"<class:")


def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
) -> TypeEnvironment:
    """Walk *instructions* once and return an immutable TypeEnvironment.

    Pure function — no mutation of the input instructions.
    """
    register_types: dict[str, str] = {}
    var_types: dict[str, str] = {}

    for inst in instructions:
        _infer_instruction(inst, register_types, var_types, type_resolver)

    logger.debug(
        "Type inference complete: %d register types, %d variable types",
        len(register_types),
        len(var_types),
    )
    return TypeEnvironment(
        register_types=MappingProxyType(register_types),
        var_types=MappingProxyType(var_types),
    )


def _infer_instruction(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    """Infer and record the output type for a single instruction."""
    handler = _DISPATCH.get(inst.opcode)
    if handler:
        handler(inst, register_types, var_types, type_resolver)


def _infer_symbolic(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if inst.type_hint and inst.result_reg:
        register_types[inst.result_reg] = inst.type_hint


def _infer_const(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        inferred = _infer_const_type(inst.operands[0] if inst.operands else "None")
        if inferred:
            register_types[inst.result_reg] = inferred


def _infer_load_var(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    name = inst.operands[0] if inst.operands else ""
    if inst.result_reg and name in var_types:
        register_types[inst.result_reg] = var_types[name]


def _infer_store_var(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    name = inst.operands[0] if inst.operands else ""
    if not name:
        return
    if inst.type_hint:
        var_types[name] = inst.type_hint
    elif len(inst.operands) >= 2:
        value_reg = str(inst.operands[1])
        if value_reg in register_types:
            var_types[name] = register_types[value_reg]


def _infer_binop(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 3:
        return
    operator = str(inst.operands[0])
    left_hint = register_types.get(str(inst.operands[1]), "")
    right_hint = register_types.get(str(inst.operands[2]), "")
    result = type_resolver.resolve_binop(operator, left_hint, right_hint)
    if result.result_type:
        register_types[inst.result_reg] = result.result_type


def _infer_unop(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg or len(inst.operands) < 2:
        return
    operand_hint = register_types.get(str(inst.operands[1]), "")
    if operand_hint:
        register_types[inst.result_reg] = operand_hint


def _infer_new_object(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg and inst.operands:
        class_name = str(inst.operands[0])
        if class_name:
            register_types[inst.result_reg] = class_name


def _infer_new_array(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg:
        register_types[inst.result_reg] = TypeName.ARRAY


def _infer_call_function(
    inst: IRInstruction,
    register_types: dict[str, str],
    var_types: dict[str, str],
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg and inst.type_hint:
        register_types[inst.result_reg] = inst.type_hint


_DISPATCH: dict[Opcode, callable] = {
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
