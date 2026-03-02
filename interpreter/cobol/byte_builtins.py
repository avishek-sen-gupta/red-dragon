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


def _builtin_cobol_prepare_digits(args: list[Any], vm: Any) -> Any:
    """Prepare digit list from a string value for COBOL numeric encoding.

    Args: [value_str: str, total_digits: int, decimal_digits: int, signed: bool]
    Returns: list[int] of digit values (0-9)
    """
    if len(args) < 4 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    value_str, total_digits, decimal_digits, signed = (
        args[0],
        args[1],
        args[2],
        args[3],
    )
    if not isinstance(total_digits, int):
        return _UNCOMPUTABLE
    if isinstance(value_str, (int, float)):
        value_str = str(value_str)
    if not isinstance(value_str, str):
        return _UNCOMPUTABLE

    from interpreter.cobol.data_filters import align_decimal, left_adjust

    clean = value_str.lstrip("+-")
    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        integer_part = clean.split(".")[0] if "." in clean else clean
        digit_str = left_adjust(integer_part, total_digits)

    return [int(ch) if ch.isdigit() else 0 for ch in digit_str]


def _builtin_cobol_prepare_sign(args: list[Any], vm: Any) -> Any:
    """Compute sign nibble from a string value for COBOL numeric encoding.

    Args: [value_str: str, signed: bool]
    Returns: int (sign nibble: 0x0F unsigned, 0x0C positive, 0x0D negative)
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    value_str, signed = args[0], args[1]
    if isinstance(value_str, (int, float)):
        value_str = str(value_str)
    if not isinstance(value_str, str):
        return _UNCOMPUTABLE
    if not signed:
        return 0x0F
    negative = value_str.startswith("-")
    clean = value_str.lstrip("+-").replace(".", "")
    has_nonzero = any(ch != "0" for ch in clean if ch.isdigit())
    if negative and has_nonzero:
        return 0x0D
    return 0x0C


def _builtin_string_find(args: list[Any], vm: Any) -> Any:
    """Find first occurrence of needle in source string.

    Args: [source: str, needle: str]
    Returns: int index (-1 if not found)
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    source, needle = args[0], args[1]
    if not isinstance(source, str) or not isinstance(needle, str):
        return _UNCOMPUTABLE
    return source.find(needle)


def _builtin_string_split(args: list[Any], vm: Any) -> Any:
    """Split source string by delimiter.

    Args: [source: str, delimiter: str]
    Returns: list[str]
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    source, delimiter = args[0], args[1]
    if not isinstance(source, str) or not isinstance(delimiter, str):
        return _UNCOMPUTABLE
    if not delimiter:
        return [source]
    return source.split(delimiter)


def _builtin_string_count(args: list[Any], vm: Any) -> Any:
    """Count occurrences of pattern in source string.

    Args: [source: str, pattern: str, mode: str ("all"/"leading"/"characters")]
    Returns: int
    """
    if len(args) < 3 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    source, pattern, mode = args[0], args[1], args[2]
    if (
        not isinstance(source, str)
        or not isinstance(pattern, str)
        or not isinstance(mode, str)
    ):
        return _UNCOMPUTABLE
    if mode == "all":
        return source.count(pattern) if pattern else 0
    if mode == "leading":
        count = 0
        pos = 0
        while pos <= len(source) - len(pattern) and pattern:
            if source[pos : pos + len(pattern)] == pattern:
                count += 1
                pos += len(pattern)
            else:
                break
        return count
    if mode == "characters":
        return len(source)
    return _UNCOMPUTABLE


def _builtin_string_replace(args: list[Any], vm: Any) -> Any:
    """Replace occurrences of pattern in source string.

    Args: [source: str, from_pat: str, to_pat: str, mode: str ("all"/"leading"/"first")]
    Returns: str
    """
    if len(args) < 4 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    source, from_pat, to_pat, mode = args[0], args[1], args[2], args[3]
    if (
        not isinstance(source, str)
        or not isinstance(from_pat, str)
        or not isinstance(to_pat, str)
        or not isinstance(mode, str)
    ):
        return _UNCOMPUTABLE
    if not from_pat:
        return source
    if mode == "all":
        return source.replace(from_pat, to_pat)
    if mode == "first":
        return source.replace(from_pat, to_pat, 1)
    if mode == "leading":
        result = source
        while result.startswith(from_pat):
            result = to_pat + result[len(from_pat) :]
        return result
    return _UNCOMPUTABLE


def _builtin_string_concat(args: list[Any], vm: Any) -> Any:
    """Concatenate a list of strings.

    Args: [parts: list[str]]
    Returns: str
    """
    if len(args) < 1 or _is_symbolic(args[0]):
        return _UNCOMPUTABLE
    parts = args[0]
    if not isinstance(parts, list):
        return _UNCOMPUTABLE
    if any(_is_symbolic(p) for p in parts):
        return _UNCOMPUTABLE
    return "".join(str(p) for p in parts)


def _builtin_string_concat_pair(args: list[Any], vm: Any) -> Any:
    """Concatenate two strings.

    Args: [left: str, right: str]
    Returns: str
    """
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return _UNCOMPUTABLE
    left, right = args[0], args[1]
    return str(left) + str(right)


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
    "__cobol_prepare_digits": _builtin_cobol_prepare_digits,
    "__cobol_prepare_sign": _builtin_cobol_prepare_sign,
    "__string_find": _builtin_string_find,
    "__string_split": _builtin_string_split,
    "__string_count": _builtin_string_count,
    "__string_replace": _builtin_string_replace,
    "__string_concat": _builtin_string_concat,
    "__string_concat_pair": _builtin_string_concat_pair,
}
