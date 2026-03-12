"""Built-in function implementations for the symbolic interpreter."""

from __future__ import annotations

import logging
from typing import Any

from interpreter.constants import ARR_ADDR_PREFIX
from interpreter.vm import VMState, Operators, _is_symbolic, _heap_addr
from interpreter.vm_types import HeapObject
from interpreter.cobol.byte_builtins import BYTE_BUILTINS

_UNCOMPUTABLE = Operators.UNCOMPUTABLE

logger = logging.getLogger(__name__)


def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        fields = vm.heap[addr].fields
        if "length" in fields:
            return fields["length"]
        return len(fields)
    if isinstance(val, (list, tuple, str)):
        return len(val)
    return _UNCOMPUTABLE


def _builtin_range(args: list[Any], vm: VMState) -> Any:
    if any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    concrete = list(args)
    if len(concrete) == 1:
        return list(range(int(concrete[0])))
    if len(concrete) == 2:
        return list(range(int(concrete[0]), int(concrete[1])))
    if len(concrete) == 3:
        return list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
    return _UNCOMPUTABLE


def _builtin_print(args: list[Any], vm: VMState) -> Any:
    logger.info("[VM print] %s", " ".join(str(a) for a in args))
    return None


def _builtin_int(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return int(args[0])
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_float(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return float(args[0])
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_str(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return str(args[0])
    return _UNCOMPUTABLE


def _builtin_bool(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        return bool(args[0])
    return _UNCOMPUTABLE


def _builtin_abs(args: list[Any], vm: VMState) -> Any:
    if args and not _is_symbolic(args[0]):
        try:
            return abs(args[0])
        except TypeError:
            pass
    return _UNCOMPUTABLE


def _builtin_max(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return max(args)
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


def _builtin_min(args: list[Any], vm: VMState) -> Any:
    if all(not _is_symbolic(a) for a in args):
        try:
            return min(args)
        except (ValueError, TypeError):
            pass
    return _UNCOMPUTABLE


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


def _builtin_array_of(args: list[Any], vm: VMState) -> Any:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {str(i): val for i, val in enumerate(args)}
    fields["length"] = len(args)
    vm.heap[addr] = HeapObject(type_hint="array", fields=fields)
    return addr


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
    length = heap_obj.fields.get("length", len(heap_obj.fields))
    if not isinstance(length, int):
        return _UNCOMPUTABLE
    indices = range(length)[py_slice]
    elements = [heap_obj.fields.get(str(i)) for i in indices]
    return _builtin_array_of(elements, vm)


def _builtin_object_rest(args: list[Any], vm: VMState) -> Any:
    """object_rest(obj, key1, key2, ...) — return new object without excluded keys.

    Creates a new heap object with all fields from obj except the listed keys.
    """
    if not args:
        return _UNCOMPUTABLE
    obj_val = args[0]
    excluded_keys = set(args[1:])
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return _UNCOMPUTABLE
    source_fields = vm.heap[addr].fields
    rest_fields = {
        k: v
        for k, v in source_fields.items()
        if k not in excluded_keys and k != "length"
    }
    rest_addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    vm.heap[rest_addr] = HeapObject(type_hint="object", fields=rest_fields)
    return rest_addr


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
        "Array": _builtin_array_of,
        "slice": _builtin_slice,
        "object_rest": _builtin_object_rest,
        **BYTE_BUILTINS,
    }
