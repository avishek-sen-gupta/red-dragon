"""Built-in function implementations for the symbolic interpreter."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.address import Address
from interpreter.constants import ARR_ADDR_PREFIX, TypeName
from interpreter.field_name import FieldName, FieldKind
from interpreter.func_name import FuncName
from interpreter.vm.vm import VMState, Operators, _is_symbolic, _heap_addr
from interpreter.vm.vm_types import (
    HeapObject,
    BuiltinResult,
    NewObject,
    HeapWrite,
    Pointer,
)
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.types.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.types.type_expr import pointer, scalar

_UNCOMPUTABLE = Operators.UNCOMPUTABLE

logger = logging.getLogger(__name__)


def _builtin_len(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0].value
    addr = _heap_addr(val)
    if addr and vm.heap_contains(addr):
        fields = vm.heap_get(addr).fields
        if FieldName("length", FieldKind.SPECIAL) in fields:
            return BuiltinResult(
                value=fields[FieldName("length", FieldKind.SPECIAL)].value
            )
        return BuiltinResult(value=len(fields))
    if isinstance(val, (list, tuple, str)):
        return BuiltinResult(value=len(val))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_range(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    concrete = [a.value for a in args]
    if len(concrete) == 1:
        return BuiltinResult(value=list(range(int(concrete[0]))))
    if len(concrete) == 2:
        return BuiltinResult(value=list(range(int(concrete[0]), int(concrete[1]))))
    if len(concrete) == 3:
        return BuiltinResult(
            value=list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
        )
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_print(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    logger.info("[VM print] %s", " ".join(str(a.value) for a in args))
    return BuiltinResult(value=None)


def _builtin_int(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        try:
            return BuiltinResult(value=int(args[0].value))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_float(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        try:
            return BuiltinResult(value=float(args[0].value))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_str(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        return BuiltinResult(value=str(args[0].value))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_bool(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        return BuiltinResult(value=bool(args[0].value))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_abs(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        try:
            return BuiltinResult(value=abs(args[0].value))
        except TypeError:
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_max(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if all(not _is_symbolic(a.value) for a in args):
        try:
            return BuiltinResult(value=max(a.value for a in args))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_min(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if all(not _is_symbolic(a.value) for a in args):
        try:
            return BuiltinResult(value=min(a.value for a in args))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_keys(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Return a heap-allocated array of the object's field names.

    Excludes metadata fields like 'length' to match JS Object.keys() semantics.
    """
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0].value
    addr = _heap_addr(val)
    if not addr or not vm.heap_contains(addr):
        return BuiltinResult(value=_UNCOMPUTABLE)
    field_names = [
        str(k)
        for k in vm.heap_get(addr).fields
        if k != FieldName("length", FieldKind.SPECIAL)
    ]
    return _builtin_array_of(field_names, vm)


def _builtin_array_of(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {
        FieldName(str(i), FieldKind.INDEX): (
            val if isinstance(val, TypedValue) else typed_from_runtime(val)
        )
        for i, val in enumerate(args)
    }
    fields[FieldName("length", FieldKind.SPECIAL)] = typed(
        len(args), scalar(TypeName.INT)
    )
    return BuiltinResult(
        value=typed(Pointer(base=Address(addr), offset=0), pointer(scalar("Array"))),
        new_objects=[NewObject(addr=Address(addr), type_hint=scalar("Array"))],
        heap_writes=[
            HeapWrite(obj_addr=Address(addr), field=k, value=v)
            for k, v in fields.items()
        ],
    )


def _builtin_slice(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """slice(collection, start[, stop[, step]]) — return a sub-sequence.

    Supports native lists/tuples, strings, and heap-backed arrays.
    Missing stop/step represented as 'None' string (from IR CONST).
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    collection = args[0].value
    raw_start, raw_stop, raw_step = (
        args[1].value,
        _arg_or_none_value(args, 2),
        _arg_or_none_value(args, 3),
    )
    start = _parse_slice_int(raw_start)
    stop = _parse_slice_int(raw_stop)
    step = _parse_slice_int(raw_step)
    py_slice = slice(start, stop, step)
    # Native list/tuple
    if isinstance(collection, (list, tuple)):
        return _builtin_array_of(list(collection[py_slice]), vm)
    # Heap-backed array (check before string — heap addresses are strings too)
    addr = _heap_addr(collection)
    if addr and vm.heap_contains(addr):
        return _slice_heap_array(vm.heap_get(addr), py_slice, vm)
    # Native string
    if isinstance(collection, str):
        return BuiltinResult(value=collection[py_slice])
    return BuiltinResult(value=_UNCOMPUTABLE)


def _arg_or_none_value(args: list[TypedValue], index: int) -> Any:
    """Return args[index].value if it exists, else None."""
    return args[index].value if index < len(args) else None


def _parse_slice_int(value: Any) -> int | None:
    """Convert a slice argument to int or None ('None' string → None)."""
    if value is None or value == "None":
        return None
    return int(value)


def _slice_heap_array(
    heap_obj: HeapObject, py_slice: slice, vm: VMState
) -> BuiltinResult:
    """Apply a Python slice to a heap-backed array and return a new heap array."""
    length_raw = heap_obj.fields.get(
        FieldName("length", FieldKind.SPECIAL), len(heap_obj.fields)
    )
    length = length_raw.value if isinstance(length_raw, TypedValue) else length_raw
    if not isinstance(length, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    indices = range(length)[py_slice]
    elements = [
        heap_obj.fields.get(FieldName(str(i), FieldKind.INDEX)) for i in indices
    ]
    return _builtin_array_of(elements, vm)


def _builtin_clone(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """clone(obj) — shallow-copy a heap object (PHP clone keyword)."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    addr = _heap_addr(args[0].value)
    if not addr or not vm.heap_contains(addr):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source = vm.heap_get(addr)
    clone_addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    hint = source.type_hint if source.type_hint else scalar("Object")
    return BuiltinResult(
        value=typed(
            Pointer(base=Address(clone_addr), offset=0),
            pointer(hint),
        ),
        new_objects=[NewObject(addr=Address(clone_addr), type_hint=hint)],
        heap_writes=[
            HeapWrite(obj_addr=Address(clone_addr), field=k, value=v)
            for k, v in source.fields.items()
        ],
    )


def _builtin_object_rest(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """object_rest(obj, key1, key2, ...) — return new object without excluded keys."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    obj_val = args[0].value
    excluded_keys = {FieldName(str(a.value)) for a in args[1:]}
    addr = _heap_addr(obj_val)
    if not addr or not vm.heap_contains(addr):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source_fields = vm.heap_get(addr).fields
    rest_fields = {
        k: v
        for k, v in source_fields.items()
        if k not in excluded_keys and k != FieldName("length", FieldKind.SPECIAL)
    }
    rest_addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return BuiltinResult(
        value=typed(
            Pointer(base=Address(rest_addr), offset=0), pointer(scalar("Object"))
        ),
        new_objects=[NewObject(addr=Address(rest_addr), type_hint=scalar("Object"))],
        heap_writes=[
            HeapWrite(obj_addr=Address(rest_addr), field=k, value=v)
            for k, v in rest_fields.items()
        ],
    )


def _method_slice(
    obj: TypedValue, args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Method builtin: obj.subList(start, stop) / obj.substring(start, stop) → slice."""
    return _builtin_slice([obj, *args], vm)


def _method_to_string(
    obj: TypedValue, args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Method builtin: obj.to_string() / obj.toString() → str(obj)."""
    return BuiltinResult(value=str(obj.value))


def _method_length(
    obj: TypedValue, args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Method builtin: obj.length() / obj.size() / obj.Length → len(obj).

    Handles Java .length(), Kotlin .length/.size, C# .Length, JS .length,
    Ruby .size/.length on strings and collections.
    """
    return _builtin_len([obj], vm)


_PRIMITIVE_TYPE_MAP: dict[str, type] = {
    "int": int,
    "Int": int,
    "Integer": int,
    "string": str,
    "String": str,
    "float": float,
    "Float": float,
    "Double": float,
    "bool": bool,
    "Boolean": bool,
}


def _builtin_isinstance(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """isinstance(obj, class_name) — check type against class name.

    Works for both heap objects (checks type_hint) and native primitives
    (checks Python type against _PRIMITIVE_TYPE_MAP).
    """
    obj_val = args[0].value
    class_name = str(args[1].value)
    # Try heap object first
    addr = _heap_addr(obj_val)
    if addr and vm.heap_contains(addr):
        from interpreter.types.type_expr import ScalarType

        type_hint = vm.heap_get(addr).type_hint
        matches = isinstance(type_hint, ScalarType) and type_hint.name == class_name
        return BuiltinResult(value=typed(matches, scalar("Boolean")))
    # Fall back to primitive type check
    py_type = _PRIMITIVE_TYPE_MAP.get(class_name)
    if py_type is not None:
        matches = isinstance(obj_val, py_type)
        return BuiltinResult(value=typed(matches, scalar("Boolean")))
    return BuiltinResult(value=typed(False, scalar("Boolean")))


class Builtins:
    """Table of built-in function implementations."""

    TABLE: dict[FuncName, Any] = {
        FuncName("len"): _builtin_len,
        FuncName("strlen"): _builtin_len,
        FuncName("range"): _builtin_range,
        FuncName("print"): _builtin_print,
        FuncName("int"): _builtin_int,
        FuncName("float"): _builtin_float,
        FuncName("str"): _builtin_str,
        FuncName("bool"): _builtin_bool,
        FuncName("abs"): _builtin_abs,
        FuncName("max"): _builtin_max,
        FuncName("min"): _builtin_min,
        FuncName("keys"): _builtin_keys,
        FuncName("arrayOf"): _builtin_array_of,
        FuncName("intArrayOf"): _builtin_array_of,
        FuncName("listOf"): _builtin_array_of,
        FuncName("mutableListOf"): _builtin_array_of,
        FuncName("Array"): _builtin_array_of,
        FuncName("slice"): _builtin_slice,
        FuncName("clone"): _builtin_clone,
        FuncName("isinstance"): _builtin_isinstance,
        FuncName("object_rest"): _builtin_object_rest,
        **BYTE_BUILTINS,
    }

    @classmethod
    def lookup_builtin(cls, name: FuncName) -> Any | None:
        return cls.TABLE.get(name)

    @classmethod
    def lookup_method_builtin(cls, name: FuncName) -> Any | None:
        return cls.METHOD_TABLE.get(name)

    # Method builtins: obj.method(args) → builtin(obj, *args)
    # Signature: (obj, args: list, vm) -> Any
    METHOD_TABLE: dict[FuncName, Any] = {
        FuncName("subList"): _method_slice,
        FuncName("substring"): _method_slice,
        FuncName("slice"): _method_slice,
        FuncName("to_string"): _method_to_string,
        FuncName("toString"): _method_to_string,
        FuncName("length"): _method_length,
        FuncName("size"): _method_length,
        FuncName("Length"): _method_length,
    }
