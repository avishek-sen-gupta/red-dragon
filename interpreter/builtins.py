"""Built-in function implementations for the symbolic interpreter."""

from __future__ import annotations

from typing import Any

from .vm import VMState, Operators, _is_symbolic, _heap_addr

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        return len(vm.heap[addr].fields)
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
    return None  # print returns None (the actual Python value)


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
    }
