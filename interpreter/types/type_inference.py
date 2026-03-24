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
from dataclasses import dataclass, field
from types import MappingProxyType

from interpreter import constants
from interpreter.constants import CanonicalLiteral, TypeName
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.types.function_kind import FunctionKind
from interpreter.types.function_signature import FunctionSignature
from interpreter.ir import IRInstruction, Opcode, CodeLabel
from interpreter.instructions import (
    to_typed,
    Const,
    DeclVar,
    LoadVar,
    StoreVar,
    Symbolic,
    Binop,
    Unop,
    CallFunction,
    CallMethod,
    CallUnknown,
    LoadField,
    StoreField,
    LoadIndex,
    StoreIndex,
    NewObject,
    NewArray,
    Return_,
)
from interpreter.types.type_environment import TypeEnvironment
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.type_expr import (
    TypeExpr,
    ScalarType,
    ParameterizedType,
    FunctionType,
    UNBOUND,
    UNKNOWN,
    array_of,
    scalar,
    union_of,
    fn_type,
    tuple_of,
)
from interpreter.types.type_resolver import TypeResolver

logger = logging.getLogger(__name__)


def _try_parse_int(s: str) -> int:
    """Try to parse s as an integer, returning -1 on failure."""
    try:
        return int(s)
    except (ValueError, TypeError):
        return -1


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
    current_class_name: TypeExpr = UNKNOWN
    class_method_types: dict[TypeExpr, dict[str, TypeExpr]] = field(
        default_factory=dict
    )
    field_types: dict[TypeExpr, dict[str, TypeExpr]] = field(default_factory=dict)
    array_element_types: dict[str, TypeExpr] = field(default_factory=dict)
    var_array_element_types: dict[str, TypeExpr] = field(default_factory=dict)
    const_values: dict[str, str] = field(default_factory=dict)
    tuple_registers: set[str] = field(default_factory=set)
    tuple_element_types: dict[str, dict[int, TypeExpr]] = field(default_factory=dict)
    var_tuple_element_types: dict[str, dict[int, TypeExpr]] = field(
        default_factory=dict
    )
    register_source_var: dict[str, str] = field(default_factory=dict)
    interface_implementations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    class_method_signatures: dict[TypeExpr, dict[str, list[FunctionSignature]]] = field(
        default_factory=dict
    )
    func_symbol_table: dict[CodeLabel, FuncRef] = field(default_factory=dict)
    class_symbol_table: dict[CodeLabel, ClassRef] = field(default_factory=dict)
    _seeded_var_names: frozenset[str] = field(default_factory=frozenset)

    def store_var_type(self, name: str, type_expr: TypeExpr) -> None:
        """Store a variable type in the current function scope.

        Seeded types (from the builder) take precedence and are never widened.
        For inferred types, if the variable already has a different type in
        the current scope, the type is widened to a union.
        """
        if name in self._seeded_var_names:
            return
        scope = self.current_func_label
        scope_dict = self.scoped_var_types.setdefault(scope, {})
        existing = scope_dict.get(name, UNKNOWN)
        if not existing:
            scope_dict[name] = type_expr
        elif existing != type_expr:
            scope_dict[name] = union_of(existing, type_expr)

    def lookup_var_type(self, name: str) -> TypeExpr:
        """Look up a variable type: current scope first, then global."""
        scope = self.current_func_label
        scope_dict = self.scoped_var_types.get(scope, {})
        if name in scope_dict:
            return scope_dict[name]
        global_dict = self.scoped_var_types.get(_GLOBAL_SCOPE, {})
        return global_dict.get(name, UNKNOWN)

    def flat_var_types(self) -> dict[str, TypeExpr]:
        """Flatten all scoped var types into a single dict for TypeEnvironment.

        When the same variable name appears in multiple scopes with different
        types, the result is a union of those types rather than last-writer-wins.
        """
        result: dict[str, TypeExpr] = {}
        for scope_dict in self.scoped_var_types.values():
            for name, type_expr in scope_dict.items():
                existing = result.get(name, UNKNOWN)
                if not existing:
                    result[name] = type_expr
                elif existing != type_expr:
                    result[name] = union_of(existing, type_expr)
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


def _promote_tuple_element_types(ctx: _InferenceContext) -> None:
    """Promote Tuple variables with known per-index types to Tuple[T1, T2, ...].

    After inference converges, variables typed as ``Tuple`` that have known
    per-index element types are promoted to ``Tuple[T1, T2, ...]``.  Register
    types for tuple registers are also promoted.
    """
    for var_name, idx_types in ctx.var_tuple_element_types.items():
        for scope_dict in ctx.scoped_var_types.values():
            if var_name in scope_dict and scope_dict[var_name] == TypeName.TUPLE:
                ordered = tuple(idx_types[i] for i in sorted(idx_types.keys()))
                scope_dict[var_name] = tuple_of(*ordered)
                logger.debug("Promoted %s: Tuple → Tuple[%s]", var_name, ordered)

    for reg, idx_types in ctx.tuple_element_types.items():
        if ctx.register_types.get(reg, UNKNOWN) == TypeName.TUPLE:
            ordered = tuple(idx_types[i] for i in sorted(idx_types.keys()))
            ctx.register_types[reg] = tuple_of(*ordered)


def _build_func_signatures(
    func_return_types: dict[str, TypeExpr],
    func_param_types: dict[str, list[tuple[str, TypeExpr]]],
) -> dict[str, list[FunctionSignature]]:
    """Build signatures keyed only by user-facing function names.

    Internal labels (func_add_0) are excluded — only names that came
    through a <function:name@label> CONST mapping are included.

    Each name maps to a list of signatures to support overloads.
    Currently the upstream dicts are name-keyed (last-write-wins),
    so each list has at most one entry until class-scoped accumulation
    is added.
    """
    user_facing_names = {
        name
        for name in set(func_return_types) | set(func_param_types)
        if not name.startswith("func_")
    }

    return {
        name: [
            FunctionSignature(
                params=tuple(func_param_types.get(name, [])),
                return_type=func_return_types.get(name, UNKNOWN),
            )
        ]
        for name in user_facing_names
    }


def _resolve_alias(
    t: TypeExpr, aliases: dict[str, TypeExpr], depth: int = 0
) -> TypeExpr:
    """Resolve a TypeExpr through the alias registry, expanding transitively.

    ScalarType names that appear as alias keys are expanded. Parameterized
    types have their arguments resolved recursively. A depth limit prevents
    infinite loops from circular aliases.
    """
    if depth > 20:
        return t
    if isinstance(t, ScalarType) and t.name in aliases:
        return _resolve_alias(aliases[t.name], aliases, depth + 1)
    if isinstance(t, ParameterizedType):
        resolved_args = tuple(
            _resolve_alias(a, aliases, depth + 1) for a in t.arguments
        )
        return ParameterizedType(t.constructor, resolved_args)
    return t


def _resolve_aliases_in_dict(
    d: dict[str, TypeExpr], aliases: dict[str, TypeExpr]
) -> dict[str, TypeExpr]:
    """Resolve all values in a dict through the alias registry."""
    return {k: _resolve_alias(v, aliases) for k, v in d.items()}


def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
    func_symbol_table: dict[CodeLabel, FuncRef] = {},
    class_symbol_table: dict[CodeLabel, ClassRef] = {},
) -> TypeEnvironment:
    """Walk *instructions* to fixpoint and return an immutable TypeEnvironment.

    Pre-seeded type info from ``type_env_builder`` (populated by the
    frontend during lowering) is merged first; the inference walk then
    adds inferred types on top.  The walk repeats until no new types are
    discovered, resolving forward references (e.g. function A calls
    function B which is defined later in the IR).

    Pure function — no mutation of the input instructions.
    """
    aliases = type_env_builder.type_aliases
    ctx = _InferenceContext(
        register_types=_resolve_aliases_in_dict(
            type_env_builder.register_types, aliases
        ),
        scoped_var_types={
            _GLOBAL_SCOPE: _resolve_aliases_in_dict(type_env_builder.var_types, aliases)
        },
        func_return_types=_resolve_aliases_in_dict(
            type_env_builder.func_return_types, aliases
        ),
        func_param_types={
            k: [(pn, _resolve_alias(pt, aliases)) for pn, pt in v]
            for k, v in type_env_builder.func_param_types.items()
        },
        interface_implementations={
            k: tuple(v) for k, v in type_env_builder.interface_implementations.items()
        },
        func_symbol_table=func_symbol_table,
        class_symbol_table=class_symbol_table,
        _seeded_var_names=frozenset(type_env_builder.var_types.keys()),
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

    # Promote Array/Tuple variables with known element types
    _promote_array_element_types(ctx)
    _promote_tuple_element_types(ctx)

    # Build TypeEnvironment directly — no roundtrip through builder
    flat_vars = ctx.flat_var_types()
    standalone_sigs = _build_func_signatures(
        ctx.func_return_types, ctx.func_param_types
    )

    logger.debug(
        "Type inference complete: %d register types, %d variable types",
        len(ctx.register_types),
        len(flat_vars),
    )
    frozen_scoped = MappingProxyType(
        {
            scope: MappingProxyType(dict(var_dict))
            for scope, var_dict in ctx.scoped_var_types.items()
        }
    )
    # Unify standalone and class-scoped signatures under one container
    unified_sigs: dict[TypeExpr, MappingProxyType[str, list[FunctionSignature]]] = {
        class_type: MappingProxyType(dict(methods))
        for class_type, methods in ctx.class_method_signatures.items()
    }
    if standalone_sigs:
        unified_sigs[UNBOUND] = MappingProxyType(standalone_sigs)
    return TypeEnvironment(
        register_types=MappingProxyType(ctx.register_types),
        var_types=MappingProxyType(flat_vars),
        method_signatures=MappingProxyType(unified_sigs),
        type_aliases=MappingProxyType(dict(aliases)),
        interface_implementations=MappingProxyType(
            {k: tuple(v) for k, v in type_env_builder.interface_implementations.items()}
        ),
        scoped_var_types=frozen_scoped,
        var_scope_metadata=MappingProxyType(dict(type_env_builder.var_scope_metadata)),
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
    if not inst.label.is_present():
        return
    if inst.label.is_function():
        ctx.current_func_label = str(inst.label)
        ctx.func_param_types.setdefault(str(inst.label), [])
        # func_return_types are pre-seeded by the builder; no inst.type_hint read
    elif (
        inst.label.starts_with(constants.CLASS_LABEL_PREFIX)
        and not inst.label.is_end_class()
    ):
        ctx.current_class_name = scalar(
            inst.label.extract_name(constants.CLASS_LABEL_PREFIX)
        )
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
    t = to_typed(inst)
    assert isinstance(t, Symbolic)

    # Collect param types if inside a function (only if not already seeded)
    if ctx.current_func_label and t.hint:
        operand = str(t.hint)
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
        and t.hint
    ):
        operand = str(t.hint)
        if operand.startswith("param:"):
            param_name = operand[len("param:") :]
            if param_name in _SELF_PARAM_NAMES:
                ctx.register_types[inst.result_reg] = ctx.current_class_name


def _infer_const(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present():
        return
    t = to_typed(inst)
    assert isinstance(t, Const)
    raw = str(t.value) if t.value != "" else "None"
    # If this is a function reference, extract name→return-type and name→param-types mappings
    # Symbol table lookup: plain label operands → FuncRef
    func_name, func_label = "", ""
    if raw in ctx.func_symbol_table:
        ref = ctx.func_symbol_table[raw]
        func_name, func_label = ref.name, ref.label
    if func_name and func_label:
        # Only populate flat (name-keyed) dicts for standalone functions.
        # Class methods go into class_method_signatures instead.
        if not ctx.current_class_name:
            if func_label in ctx.func_return_types:
                ctx.func_return_types[func_name] = ctx.func_return_types[func_label]
            if func_label in ctx.func_param_types:
                ctx.func_param_types[func_name] = ctx.func_param_types[func_label]
        if ctx.current_class_name:
            ret_type = ctx.func_return_types.get(func_label, UNKNOWN)
            ctx.class_method_types.setdefault(ctx.current_class_name, {})[
                func_name
            ] = ret_type
            # Build class-scoped method signature (supports overloads)
            param_pairs = ctx.func_param_types.get(func_label, [])
            has_this = any(n in ("this", "$this") for n, _ in param_pairs)
            method_kind = FunctionKind.INSTANCE if has_this else FunctionKind.STATIC
            sig = FunctionSignature(
                params=tuple(param_pairs),
                return_type=ret_type,
                kind=method_kind,
            )
            method_sigs = ctx.class_method_signatures.setdefault(
                ctx.current_class_name, {}
            ).setdefault(func_name, [])
            if sig not in method_sigs:
                method_sigs.append(sig)
        # Infer FunctionType for the register holding the function reference
        ret_type = ctx.func_return_types.get(func_label, UNKNOWN)
        if ret_type:
            param_pairs = ctx.func_param_types.get(func_label, [])
            param_types = tuple(pt for _, pt in param_pairs)
            ctx.register_types[inst.result_reg] = FunctionType(
                params=param_types, return_type=ret_type
            )
        return
    ctx.const_values[inst.result_reg] = raw
    inferred = _infer_const_type(
        raw,
        func_symbol_table=ctx.func_symbol_table,
        class_symbol_table=ctx.class_symbol_table,
    )
    if inferred:
        ctx.register_types[inst.result_reg] = inferred


def _infer_load_var(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    t = to_typed(inst)
    assert isinstance(t, LoadVar)
    name = t.name if t.name else ""
    if inst.result_reg.is_present() and name:
        ctx.register_source_var[inst.result_reg] = str(name)
    var_type = ctx.lookup_var_type(str(name)) if name else UNKNOWN
    if inst.result_reg.is_present() and var_type:
        ctx.register_types[inst.result_reg] = var_type
    # Propagate array element types from variable to register
    if inst.result_reg.is_present() and str(name) in ctx.var_array_element_types:
        ctx.array_element_types[inst.result_reg] = ctx.var_array_element_types[
            str(name)
        ]
    # Propagate tuple element types from variable to register
    if inst.result_reg.is_present() and str(name) in ctx.var_tuple_element_types:
        ctx.tuple_element_types[inst.result_reg] = ctx.var_tuple_element_types[
            str(name)
        ]
        ctx.tuple_registers.add(inst.result_reg)


def _infer_store_var(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    # Dispatched for both STORE_VAR and DECL_VAR
    t = to_typed(inst)
    assert isinstance(t, (StoreVar, DeclVar))
    name = t.name if t.name else ""
    if not name:
        return
    value_reg = str(t.value_reg)
    if value_reg:
        if value_reg in ctx.register_types:
            ctx.store_var_type(str(name), ctx.register_types[value_reg])
        # Track array element types at the variable level
        if value_reg in ctx.array_element_types:
            ctx.var_array_element_types[str(name)] = ctx.array_element_types[value_reg]
        # Track tuple element types at the variable level
        if value_reg in ctx.tuple_element_types:
            ctx.var_tuple_element_types[str(name)] = ctx.tuple_element_types[value_reg]


def _infer_binop(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present() or len(inst.operands) < 3:
        return
    t = to_typed(inst)
    assert isinstance(t, Binop)
    operator = str(t.operator)
    left_hint = ctx.register_types.get(str(t.left), UNKNOWN)
    right_hint = ctx.register_types.get(str(t.right), UNKNOWN)
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
    if not inst.result_reg.is_present() or len(inst.operands) < 2:
        return
    t = to_typed(inst)
    assert isinstance(t, Unop)
    operator = str(t.operator)
    fixed = _UNOP_FIXED_TYPES.get(operator)
    if fixed:
        ctx.register_types[inst.result_reg] = fixed
        return
    operand_hint = ctx.register_types.get(str(t.operand), UNKNOWN)
    if operand_hint:
        ctx.register_types[inst.result_reg] = operand_hint


def _infer_new_object(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg.is_present() and inst.operands:
        t = to_typed(inst)
        assert isinstance(t, NewObject)
        class_name = str(t.type_hint)
        if class_name:
            ctx.register_types[inst.result_reg] = scalar(class_name)


def _infer_new_array(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present():
        return
    t = to_typed(inst)
    assert isinstance(t, NewArray)
    is_tuple = str(t.type_hint) == "tuple"
    if is_tuple:
        ctx.register_types[inst.result_reg] = scalar(TypeName.TUPLE)
        ctx.tuple_registers.add(inst.result_reg)
    else:
        ctx.register_types[inst.result_reg] = scalar(TypeName.ARRAY)


def _infer_call_function(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present():
        return
    # register_types may be pre-seeded by the builder (e.g., constructor type_hint)
    if inst.result_reg in ctx.register_types:
        return
    if inst.operands:
        t = to_typed(inst)
        assert isinstance(t, CallFunction)
        func_name = str(t.func_name)
        if func_name in ctx.func_return_types:
            ctx.register_types[inst.result_reg] = ctx.func_return_types[func_name]
        else:
            # Search class-scoped method types for static methods called by name
            matching = [
                methods[func_name]
                for methods in ctx.class_method_types.values()
                if func_name in methods
            ]
            if len(matching) == 1:
                ctx.register_types[inst.result_reg] = matching[0]
            elif func_name in _BUILTIN_RETURN_TYPES:
                ctx.register_types[inst.result_reg] = _BUILTIN_RETURN_TYPES[func_name]


def _infer_alloc_region(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg.is_present():
        ctx.register_types[inst.result_reg] = scalar("Region")


def _infer_load_region(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if inst.result_reg.is_present():
        ctx.register_types[inst.result_reg] = scalar(TypeName.ARRAY)


def _infer_store_field(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if len(inst.operands) < 3:
        return
    t = to_typed(inst)
    assert isinstance(t, StoreField)
    obj_reg = str(t.obj_reg)
    field_name = str(t.field_name)
    value_reg = str(t.value_reg)
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    value_type = ctx.register_types.get(value_reg, UNKNOWN)
    if class_name and value_type:
        ctx.field_types.setdefault(class_name, {})[field_name] = value_type


def _infer_load_field(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present() or len(inst.operands) < 2:
        return
    t = to_typed(inst)
    assert isinstance(t, LoadField)
    obj_reg = str(t.obj_reg)
    field_name = str(t.field_name)
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    if class_name and class_name in ctx.field_types:
        field_type = ctx.field_types[class_name].get(field_name, UNKNOWN)
        if field_type:
            ctx.register_types[inst.result_reg] = field_type


def _infer_call_method(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present() or len(inst.operands) < 2:
        return
    t = to_typed(inst)
    assert isinstance(t, CallMethod)
    obj_reg = str(t.obj_reg)
    method_name = str(t.method_name)
    class_name = ctx.register_types.get(obj_reg, UNKNOWN)
    if class_name and class_name in ctx.class_method_types:
        ret_type = ctx.class_method_types[class_name].get(method_name, UNKNOWN)
        if ret_type:
            ctx.register_types[inst.result_reg] = ret_type
            return
    # Interface chain walk: if class implements interfaces, check their method types
    class_name_str = str(class_name) if class_name else ""
    if class_name_str in ctx.interface_implementations:
        for iface in ctx.interface_implementations[class_name_str]:
            iface_type = scalar(iface)
            if iface_type in ctx.class_method_types:
                ret = ctx.class_method_types[iface_type].get(method_name, UNKNOWN)
                if ret:
                    ctx.register_types[inst.result_reg] = ret
                    return
    # Fallback: search class method types across all classes, then flat func_return_types
    matching_types = [
        methods[method_name]
        for methods in ctx.class_method_types.values()
        if method_name in methods
    ]
    if len(matching_types) == 1:
        ctx.register_types[inst.result_reg] = matching_types[0]
        return
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
    if not inst.result_reg.is_present() or not inst.operands:
        return
    t = to_typed(inst)
    assert isinstance(t, CallUnknown)
    target_reg = str(t.target_reg)
    # Check if the target register has a FunctionType directly
    target_type = ctx.register_types.get(target_reg, UNKNOWN)
    if isinstance(target_type, FunctionType) and target_type.return_type:
        ctx.register_types[inst.result_reg] = target_type.return_type
        return
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
    t = to_typed(inst)
    assert isinstance(t, StoreIndex)
    arr_reg = str(t.arr_reg)
    index_reg = str(t.index_reg)
    value_reg = str(t.value_reg)
    value_type = ctx.register_types.get(value_reg, UNKNOWN)
    if not value_type:
        return
    if arr_reg in ctx.tuple_registers:
        # Track per-index element types for tuples
        idx = _try_parse_int(ctx.const_values.get(index_reg, ""))
        if idx >= 0:
            ctx.tuple_element_types.setdefault(arr_reg, {})[idx] = value_type
    else:
        ctx.array_element_types[arr_reg] = value_type


def _infer_load_index(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    if not inst.result_reg.is_present() or len(inst.operands) < 2:
        return
    t = to_typed(inst)
    assert isinstance(t, LoadIndex)
    arr_reg = str(t.arr_reg)
    # Tuple: resolve per-index element type
    if arr_reg in ctx.tuple_registers and len(inst.operands) >= 2:
        index_reg = str(t.index_reg)
        idx = _try_parse_int(ctx.const_values.get(index_reg, ""))
        idx_types = ctx.tuple_element_types.get(arr_reg, {})
        if idx >= 0 and idx in idx_types:
            ctx.register_types[inst.result_reg] = idx_types[idx]
            return
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
    t = to_typed(inst)
    assert isinstance(t, Return_)
    value_reg = str(t.value_reg)
    ret_type = ctx.register_types.get(value_reg, UNKNOWN)
    if ret_type:
        ctx.func_return_types[ctx.current_func_label] = ret_type


def _infer_load_indirect(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    """LOAD_INDIRECT produces UNKNOWN — no field-type lookup for dereferences."""
    if inst.result_reg.is_present():
        ctx.register_types[inst.result_reg] = UNKNOWN


def _infer_store_indirect(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    """STORE_INDIRECT — no type inference side effects."""
    pass


_DISPATCH: dict[Opcode, callable] = {
    Opcode.LABEL: _infer_label,
    Opcode.SYMBOLIC: _infer_symbolic,
    Opcode.CONST: _infer_const,
    Opcode.LOAD_VAR: _infer_load_var,
    Opcode.STORE_VAR: _infer_store_var,
    Opcode.DECL_VAR: _infer_store_var,
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
    Opcode.LOAD_INDIRECT: _infer_load_indirect,
    Opcode.STORE_INDIRECT: _infer_store_indirect,
}


def _infer_const_type(
    raw: str,
    func_symbol_table: dict[CodeLabel, FuncRef] = {},
    class_symbol_table: dict[CodeLabel, ClassRef] = {},
) -> TypeExpr:
    """Infer a canonical type from a CONST literal string."""
    if raw in (CanonicalLiteral.TRUE, CanonicalLiteral.FALSE):
        return scalar(TypeName.BOOL)
    if raw == CanonicalLiteral.NONE:
        return UNKNOWN
    if str(raw) in func_symbol_table:
        return UNKNOWN
    if str(raw) in class_symbol_table:
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
