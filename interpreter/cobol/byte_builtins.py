"""Primitive byte-manipulation builtins for the symbolic interpreter.

These are the atoms from which all COBOL encoding/decoding is built in IR.
Language-agnostic — no COBOL-specific logic here.
"""

from __future__ import annotations

from typing import Any

from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.vm import Operators, _is_symbolic

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_nibble_get(args: list[Any], vm: Any) -> Any:
    """Extract high or low nibble from a byte value.

    Args: [byte_val: int, position: str ("high" or "low")]
    Returns: int (0-15)
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    byte_val, position = args[0], args[1]
    if not isinstance(byte_val, int) or not isinstance(position, str):
        return _UNCOMPUTABLE
    if position == "high":
        return (byte_val >> 4) & 0x0F
    if position == "low":
        return byte_val & 0x0F
    return _UNCOMPUTABLE


def _builtin_nibble_set(args: list[Any], vm: Any) -> Any:
    """Set high or low nibble of a byte value.

    Args: [byte_val: int, position: str ("high" or "low"), nibble: int]
    Returns: int (0-255)
    """
    if len(args) < 3 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    byte_val, position, nibble = args[0], args[1], args[2]
    if (
        not isinstance(byte_val, int)
        or not isinstance(position, str)
        or not isinstance(nibble, int)
    ):
        return _UNCOMPUTABLE
    if position == "high":
        return (nibble << 4) | (byte_val & 0x0F)
    if position == "low":
        return (byte_val & 0xF0) | (nibble & 0x0F)
    return _UNCOMPUTABLE


def _builtin_byte_from_int(args: list[Any], vm: Any) -> Any:
    """Clamp/mask integer to 0-255.

    Args: [value: int]
    Returns: int (0-255)
    """
    if len(args) < 1 or _is_symbolic(args[0]):
        return _UNCOMPUTABLE
    if not isinstance(args[0], int):
        return _UNCOMPUTABLE
    return args[0] & 0xFF


def _builtin_int_from_byte(args: list[Any], vm: Any) -> Any:
    """Identity — for semantic clarity in IR.

    Args: [byte_val: int]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0]):
        return _UNCOMPUTABLE
    if not isinstance(args[0], int):
        return _UNCOMPUTABLE
    return args[0]


def _builtin_bytes_to_string(args: list[Any], vm: Any) -> Any:
    """Decode byte list to string.

    Args: [byte_list: list[int], encoding: str ("ascii" or "ebcdic")]
    Returns: str
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    byte_list, encoding = args[0], args[1]
    if not isinstance(byte_list, list) or not isinstance(encoding, str):
        return _UNCOMPUTABLE
    raw = bytes(byte_list)
    if encoding == "ebcdic":
        ascii_bytes = EbcdicTable.ebcdic_to_ascii(raw)
        return ascii_bytes.decode("ascii", errors="replace")
    if encoding == "ascii":
        return raw.decode("ascii", errors="replace")
    return _UNCOMPUTABLE


def _builtin_string_to_bytes(args: list[Any], vm: Any) -> Any:
    """Encode string to byte list.

    Args: [string: str, encoding: str ("ascii" or "ebcdic")]
    Returns: list[int]
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    string, encoding = args[0], args[1]
    if not isinstance(string, str) or not isinstance(encoding, str):
        return _UNCOMPUTABLE
    if encoding == "ebcdic":
        ascii_bytes = string.encode("ascii", errors="replace")
        ebcdic_bytes = EbcdicTable.ascii_to_ebcdic(ascii_bytes)
        return list(ebcdic_bytes)
    if encoding == "ascii":
        return list(string.encode("ascii", errors="replace"))
    return _UNCOMPUTABLE


def _builtin_list_get(args: list[Any], vm: Any) -> Any:
    """Get element at index from a list.

    Args: [lst: list, index: int]
    Returns: Any
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    lst, index = args[0], args[1]
    if not isinstance(lst, list) or not isinstance(index, int):
        return _UNCOMPUTABLE
    if 0 <= index < len(lst):
        return lst[index]
    return _UNCOMPUTABLE


def _builtin_list_set(args: list[Any], vm: Any) -> Any:
    """Return new list with element replaced at index.

    Args: [lst: list, index: int, value: Any]
    Returns: list
    """
    if len(args) < 3 or _is_symbolic(args[0]) or _is_symbolic(args[1]):
        return _UNCOMPUTABLE
    lst, index, value = args[0], args[1], args[2]
    if not isinstance(lst, list) or not isinstance(index, int):
        return _UNCOMPUTABLE
    if 0 <= index < len(lst):
        new_lst = list(lst)
        new_lst[index] = value
        return new_lst
    return _UNCOMPUTABLE


def _builtin_list_len(args: list[Any], vm: Any) -> Any:
    """Return list length.

    Args: [lst: list]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0]):
        return _UNCOMPUTABLE
    if not isinstance(args[0], list):
        return _UNCOMPUTABLE
    return len(args[0])


def _builtin_list_slice(args: list[Any], vm: Any) -> Any:
    """Return sublist [start:end].

    Args: [lst: list, start: int, end: int]
    Returns: list
    """
    if len(args) < 3 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    lst, start, end = args[0], args[1], args[2]
    if (
        not isinstance(lst, list)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        return _UNCOMPUTABLE
    return lst[start:end]


def _builtin_list_concat(args: list[Any], vm: Any) -> Any:
    """Concatenate two lists.

    Args: [lst1: list, lst2: list]
    Returns: list
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    lst1, lst2 = args[0], args[1]
    if not isinstance(lst1, list) or not isinstance(lst2, list):
        return _UNCOMPUTABLE
    return lst1 + lst2


def _builtin_make_list(args: list[Any], vm: Any) -> Any:
    """Create list of `size` elements, all set to `fill`.

    Args: [size: int, fill: int]
    Returns: list[int]
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    size, fill = args[0], args[1]
    if not isinstance(size, int) or not isinstance(fill, int):
        return _UNCOMPUTABLE
    return [fill] * size


BYTE_BUILTINS: dict[str, Any] = {
    "__nibble_get": _builtin_nibble_get,
    "__nibble_set": _builtin_nibble_set,
    "__byte_from_int": _builtin_byte_from_int,
    "__int_from_byte": _builtin_int_from_byte,
    "__bytes_to_string": _builtin_bytes_to_string,
    "__string_to_bytes": _builtin_string_to_bytes,
    "__list_get": _builtin_list_get,
    "__list_set": _builtin_list_set,
    "__list_len": _builtin_list_len,
    "__list_slice": _builtin_list_slice,
    "__list_concat": _builtin_list_concat,
    "__make_list": _builtin_make_list,
}
