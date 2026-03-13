"""Built-in function implementations for the symbolic interpreter."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.constants import ARR_ADDR_PREFIX, TypeName
from interpreter.vm import VMState, Operators, _is_symbolic, _heap_addr
from interpreter.vm_types import HeapObject, BuiltinResult, NewObject, HeapWrite
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.type_expr import scalar

_UNCOMPUTABLE = Operators.UNCOMPUTABLE

logger = logging.getLogger(__name__)


def _builtin_len(args: list[Any], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        fields = vm.heap[addr].fields
        if "length" in fields:
            return BuiltinResult(value=fields["length"].value)
        return BuiltinResult(value=len(fields))
    if isinstance(val, (list, tuple, str)):
        return BuiltinResult(value=len(val))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_range(args: list[Any], vm: VMState) -> BuiltinResult:
    if any(_is_symbolic(a) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    concrete = list(args)
    if len(concrete) == 1:
        return BuiltinResult(value=list(range(int(concrete[0]))))
    if len(concrete) == 2:
        return BuiltinResult(value=list(range(int(concrete[0]), int(concrete[1]))))
    if len(concrete) == 3:
        return BuiltinResult(value=list(range(int(concrete[0]), int(concrete[1]), int(concrete[2]))))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_print(args: list[Any], vm: VMState) -> BuiltinResult:
    logger.info("[VM print] %s", " ".join(str(a) for a in args))
    return BuiltinResult(value=None)


def _builtin_int(args: list[Any], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0]):
        try:
            return BuiltinResult(value=int(args[0]))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_float(args: list[Any], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0]):
        try:
            return BuiltinResult(value=float(args[0]))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_str(args: list[Any], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0]):
        return BuiltinResult(value=str(args[0]))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_bool(args: list[Any], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0]):
        return BuiltinResult(value=bool(args[0]))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_abs(args: list[Any], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0]):
        try:
            return BuiltinResult(value=abs(args[0]))
        except TypeError:
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_max(args: list[Any], vm: VMState) -> BuiltinResult:
    if all(not _is_symbolic(a) for a in args):
        try:
            return BuiltinResult(value=max(args))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_min(args: list[Any], vm: VMState) -> BuiltinResult:
    if all(not _is_symbolic(a) for a in args):
        try:
            return BuiltinResult(value=min(args))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_keys(args: list[Any], vm: VMState) -> Any:
    """Return a heap-allocated array of the object's field names.

    Excludes metadata fields like 'length' to match JS Object.keys() semantics.
    """
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if not addr or addr not in vm.heap:
        return _UNCOMPUTABLE
    field_names = [k for k in vm.heap[addr].fields if k != "length"]
    return _builtin_array_of(field_names, vm)


def _builtin_array_of(args: list[Any], vm: VMState) -> BuiltinResult:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {
        str(i): val if isinstance(val, TypedValue) else typed_from_runtime(val)
        for i, val in enumerate(args)
    }
    fields["length"] = typed(len(args), scalar(TypeName.INT))
    return BuiltinResult(
        value=addr,
        new_objects=[NewObject(addr=addr, type_hint="array")],
        heap_writes=[
            HeapWrite(obj_addr=addr, field=k, value=v) for k, v in fields.items()
        ],
    )


def _builtin_slice(args: list[Any], vm: VMState) -> Any:
    """slice(collection, start[, stop[, step]]) — return a sub-sequence.

    Supports native lists/tuples, strings, and heap-backed arrays.
    Missing stop/step represented as 'None' string (from IR CONST).
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    collection = args[0]
    raw_start, raw_stop, raw_step = (
        args[1],
        _arg_or_none(args, 2),
        _arg_or_none(args, 3),
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
    if addr and addr in vm.heap:
        return _slice_heap_array(vm.heap[addr], py_slice, vm)
    # Native string
    if isinstance(collection, str):
        return collection[py_slice]
    return _UNCOMPUTABLE


def _arg_or_none(args: list[Any], index: int) -> Any:
    """Return args[index] if it exists, else None."""
    return args[index] if index < len(args) else None


def _parse_slice_int(value: Any) -> int | None:
    """Convert a slice argument to int or None ('None' string → None)."""
    if value is None or value == "None":
        return None
    return int(value)


def _slice_heap_array(heap_obj: HeapObject, py_slice: slice, vm: VMState) -> Any:
    """Apply a Python slice to a heap-backed array and return a new heap array."""
    length_raw = heap_obj.fields.get("length", len(heap_obj.fields))
    length = length_raw.value if isinstance(length_raw, TypedValue) else length_raw
    if not isinstance(length, int):
        return _UNCOMPUTABLE
    indices = range(length)[py_slice]
    elements = [heap_obj.fields.get(str(i)) for i in indices]
    return _builtin_array_of(elements, vm)


def _builtin_object_rest(args: list[Any], vm: VMState) -> BuiltinResult:
    """object_rest(obj, key1, key2, ...) — return new object without excluded keys."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    obj_val = args[0]
    excluded_keys = set(args[1:])
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return BuiltinResult(value=_UNCOMPUTABLE)
    source_fields = vm.heap[addr].fields
    rest_fields = {
        k: v
        for k, v in source_fields.items()
        if k not in excluded_keys and k != "length"
    }
    rest_addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return BuiltinResult(
        value=rest_addr,
        new_objects=[NewObject(addr=rest_addr, type_hint="object")],
        heap_writes=[
            HeapWrite(obj_addr=rest_addr, field=k, value=v)
            for k, v in rest_fields.items()
        ],
    )


def _method_slice(obj: Any, args: list[Any], vm: VMState) -> Any:
    """Method builtin: obj.subList(start, stop) / obj.substring(start, stop) → slice."""
    return _builtin_slice([obj, *args], vm)


class Builtins:
    """Table of built-in function implementations."""

    TABLE: dict[str, Any] = {
        "len": _builtin_len,
        "range": _builtin_range,
        "print": _builtin_print,
        "int": _builtin_int,
        "float": _builtin_float,
        "str": _builtin_str,
        "bool": _builtin_bool,
        "abs": _builtin_abs,
        "max": _builtin_max,
        "min": _builtin_min,
        "keys": _builtin_keys,
        "arrayOf": _builtin_array_of,
        "intArrayOf": _builtin_array_of,
        "listOf": _builtin_array_of,
        "mutableListOf": _builtin_array_of,
        "Array": _builtin_array_of,
        "slice": _builtin_slice,
        "object_rest": _builtin_object_rest,
        **BYTE_BUILTINS,
    }

    # Method builtins: obj.method(args) → builtin(obj, *args)
    # Signature: (obj, args: list, vm) -> Any
    METHOD_TABLE: dict[str, Any] = {
        "subList": _method_slice,
        "substring": _method_slice,
        "slice": _method_slice,
    }
