"""Primitive byte-manipulation builtins for the symbolic interpreter.

These are the atoms from which all COBOL encoding/decoding is built in IR.
Language-agnostic — no COBOL-specific logic here.
"""

from __future__ import annotations

import struct
from typing import Any

from interpreter.cobol.cobol_constants import (
    BuiltinName,
    ByteConstants,
    CobolEncoding,
    NibblePosition,
    ReplaceMode,
    TallyMode,
)
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators, _is_symbolic
from interpreter.vm.vm_types import BuiltinResult

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_nibble_get(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Extract high or low nibble from a byte value.

    Args: [byte_val: int, position: str ("high" or "low")]
    Returns: int (0-15)
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_val, position = args[0].value, args[1].value
    if not isinstance(byte_val, int) or not isinstance(position, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if position == NibblePosition.HIGH:
        return BuiltinResult(value=(byte_val >> 4) & ByteConstants.NIBBLE_MASK)
    if position == NibblePosition.LOW:
        return BuiltinResult(value=byte_val & ByteConstants.NIBBLE_MASK)
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_nibble_set(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Set high or low nibble of a byte value.

    Args: [byte_val: int, position: str ("high" or "low"), nibble: int]
    Returns: int (0-255)
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_val, position, nibble = args[0].value, args[1].value, args[2].value
    if (
        not isinstance(byte_val, int)
        or not isinstance(position, str)
        or not isinstance(nibble, int)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if position == NibblePosition.HIGH:
        return BuiltinResult(
            value=(nibble << 4) | (byte_val & ByteConstants.NIBBLE_MASK)
        )
    if position == NibblePosition.LOW:
        return BuiltinResult(
            value=(byte_val & ByteConstants.HIGH_NIBBLE_MASK)
            | (nibble & ByteConstants.NIBBLE_MASK)
        )
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_byte_from_int(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Clamp/mask integer to 0-255.

    Args: [value: int]
    Returns: int (0-255)
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=args[0].value & ByteConstants.BYTE_MASK)


def _builtin_int_from_byte(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Identity — for semantic clarity in IR.

    Args: [byte_val: int]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=args[0].value)


def _builtin_bytes_to_string(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Decode byte list to string.

    Args: [byte_list: list[int], encoding: str ("ascii" or "ebcdic")]
    Returns: str
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_list, encoding = args[0].value, args[1].value
    if not isinstance(byte_list, list) or not isinstance(encoding, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    raw = bytes(byte_list)
    if encoding == CobolEncoding.EBCDIC:
        ascii_bytes = EbcdicTable.ebcdic_to_ascii(raw)
        return BuiltinResult(value=ascii_bytes.decode("ascii", errors="replace"))
    if encoding == CobolEncoding.ASCII:
        return BuiltinResult(value=raw.decode("ascii", errors="replace"))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_string_to_bytes(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Encode string to byte list.

    Args: [string: str, encoding: str ("ascii" or "ebcdic")]
    Returns: list[int]
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    string, encoding = args[0].value, args[1].value
    if not isinstance(string, str) or not isinstance(encoding, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if encoding == CobolEncoding.EBCDIC:
        ascii_bytes = string.encode("ascii", errors="replace")
        ebcdic_bytes = EbcdicTable.ascii_to_ebcdic(ascii_bytes)
        return BuiltinResult(value=list(ebcdic_bytes))
    if encoding == CobolEncoding.ASCII:
        return BuiltinResult(value=list(string.encode("ascii", errors="replace")))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_list_get(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Get element at index from a list.

    Args: [lst: list, index: int]
    Returns: Any
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    lst, index = args[0].value, args[1].value
    if not isinstance(lst, list) or not isinstance(index, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if 0 <= index < len(lst):
        return BuiltinResult(value=lst[index])
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_list_set(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Return new list with element replaced at index.

    Args: [lst: list, index: int, value: Any]
    Returns: list
    """
    if len(args) < 3 or _is_symbolic(args[0].value) or _is_symbolic(args[1].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    lst, index, value = args[0].value, args[1].value, args[2].value
    if not isinstance(lst, list) or not isinstance(index, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if 0 <= index < len(lst):
        new_lst = list(lst)
        new_lst[index] = value
        return BuiltinResult(value=new_lst)
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_list_len(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Return list length.

    Args: [lst: list]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, list):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=len(args[0].value))


def _builtin_list_slice(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Return sublist [start:end].

    Args: [lst: list, start: int, end: int]
    Returns: list
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    lst, start, end = args[0].value, args[1].value, args[2].value
    if (
        not isinstance(lst, list)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=lst[start:end])


def _builtin_list_concat(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Concatenate two lists.

    Args: [lst1: list, lst2: list]
    Returns: list
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    lst1, lst2 = args[0].value, args[1].value
    if not isinstance(lst1, list) or not isinstance(lst2, list):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=lst1 + lst2)


def _builtin_make_list(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Create list of `size` elements, all set to `fill`.

    Args: [size: int, fill: int]
    Returns: list[int]
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    size, fill = args[0].value, args[1].value
    if not isinstance(size, int) or not isinstance(fill, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=[fill] * size)


def _builtin_cobol_prepare_digits(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Prepare digit list from a string value for COBOL numeric encoding.

    Args: [value_str: str, total_digits: int, decimal_digits: int, signed: bool]
    Returns: list[int] of digit values (0-9)
    """
    if len(args) < 4 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value_str, total_digits, decimal_digits, signed = (
        args[0].value,
        args[1].value,
        args[2].value,
        args[3].value,
    )
    if not isinstance(total_digits, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if isinstance(value_str, (int, float)):
        value_str = str(value_str)
    if not isinstance(value_str, str):
        return BuiltinResult(value=_UNCOMPUTABLE)

    from interpreter.cobol.data_filters import align_decimal, left_adjust

    clean = value_str.lstrip("+-")
    if decimal_digits > 0:
        integer_digits = total_digits - decimal_digits
        digit_str = align_decimal(clean, integer_digits, decimal_digits)
    else:
        integer_part = clean.split(".")[0] if "." in clean else clean
        digit_str = left_adjust(integer_part, total_digits)

    return BuiltinResult(value=[int(ch) if ch.isdigit() else 0 for ch in digit_str])


def _builtin_cobol_prepare_sign(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Compute sign nibble from a string value for COBOL numeric encoding.

    Args: [value_str: str, signed: bool]
    Returns: int (sign nibble: 0x0F unsigned, 0x0C positive, 0x0D negative)
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value_str, signed = args[0].value, args[1].value
    if isinstance(value_str, (int, float)):
        value_str = str(value_str)
    if not isinstance(value_str, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not signed:
        return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_UNSIGNED)
    negative = value_str.startswith("-")
    clean = value_str.lstrip("+-").replace(".", "")
    has_nonzero = any(ch != "0" for ch in clean if ch.isdigit())
    if negative and has_nonzero:
        return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_NEGATIVE)
    return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_POSITIVE)


def _builtin_string_find(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Find first occurrence of needle in source string.

    Args: [source: str, needle: str]
    Returns: int index (-1 if not found)
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, needle = args[0].value, args[1].value
    if not isinstance(source, str) or not isinstance(needle, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=source.find(needle))


def _builtin_string_split(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Split source string by delimiter.

    Args: [source: str, delimiter: str]
    Returns: list[str]
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, delimiter = args[0].value, args[1].value
    if not isinstance(source, str) or not isinstance(delimiter, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not delimiter:
        return BuiltinResult(value=[source])
    return BuiltinResult(value=source.split(delimiter))


def _builtin_string_count(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Count occurrences of pattern in source string.

    Args: [source: str, pattern: str, mode: str ("all"/"leading"/"characters")]
    Returns: int
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, pattern, mode = args[0].value, args[1].value, args[2].value
    if (
        not isinstance(source, str)
        or not isinstance(pattern, str)
        or not isinstance(mode, str)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if mode == TallyMode.ALL:
        return BuiltinResult(value=source.count(pattern) if pattern else 0)
    if mode == TallyMode.LEADING:
        count = 0
        pos = 0
        while pos <= len(source) - len(pattern) and pattern:
            if source[pos : pos + len(pattern)] == pattern:
                count += 1
                pos += len(pattern)
            else:
                break
        return BuiltinResult(value=count)
    if mode == TallyMode.CHARACTERS:
        return BuiltinResult(value=len(source))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_string_replace(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Replace occurrences of pattern in source string.

    Args: [source: str, from_pat: str, to_pat: str, mode: str ("all"/"leading"/"first")]
    Returns: str
    """
    if len(args) < 4 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, from_pat, to_pat, mode = (
        args[0].value,
        args[1].value,
        args[2].value,
        args[3].value,
    )
    if (
        not isinstance(source, str)
        or not isinstance(from_pat, str)
        or not isinstance(to_pat, str)
        or not isinstance(mode, str)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not from_pat:
        return BuiltinResult(value=source)
    if mode == ReplaceMode.ALL:
        return BuiltinResult(value=source.replace(from_pat, to_pat))
    if mode == ReplaceMode.FIRST:
        return BuiltinResult(value=source.replace(from_pat, to_pat, 1))
    if mode == ReplaceMode.LEADING:
        result = source
        while result.startswith(from_pat):
            result = to_pat + result[len(from_pat) :]
        return BuiltinResult(value=result)
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_string_concat(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Concatenate a list of strings.

    Args: [parts: list[str]]
    Returns: str
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    parts = args[0].value
    if not isinstance(parts, list):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if any(_is_symbolic(p) for p in parts):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value="".join(str(p) for p in parts))


def _builtin_string_concat_pair(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Concatenate two strings.

    Args: [left: str, right: str]
    Returns: str
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    left, right = args[0].value, args[1].value
    return BuiltinResult(value=str(left) + str(right))


def _builtin_int_to_binary_bytes(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Pack signed/unsigned integer as big-endian binary bytes.

    Args: [value: int, byte_count: int, signed: bool]
    Returns: list[int]
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value, byte_count, signed = args[0].value, args[1].value, args[2].value
    if not isinstance(value, int) or not isinstance(byte_count, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(
        value=list(value.to_bytes(byte_count, "big", signed=bool(signed)))
    )


def _builtin_binary_bytes_to_int(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Unpack big-endian binary bytes as signed/unsigned integer.

    Args: [byte_list: list[int], signed: bool]
    Returns: int
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_list, signed = args[0].value, args[1].value
    if not isinstance(byte_list, list):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(
        value=int.from_bytes(bytes(byte_list), "big", signed=bool(signed))
    )


def _builtin_float_to_bytes(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Pack IEEE 754 float to big-endian bytes.

    Args: [value: float|int, byte_count: int (4 or 8)]
    Returns: list[int]
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value, byte_count = args[0].value, args[1].value
    if not isinstance(value, (int, float)) or not isinstance(byte_count, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    fmt = ">f" if byte_count == 4 else ">d"
    return BuiltinResult(value=list(struct.pack(fmt, float(value))))


def _builtin_bytes_to_float(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Unpack big-endian IEEE 754 bytes to float.

    Args: [byte_list: list[int], byte_count: int (4 or 8)]
    Returns: float
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_list, byte_count = args[0].value, args[1].value
    if not isinstance(byte_list, list) or not isinstance(byte_count, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    fmt = ">f" if byte_count == 4 else ">d"
    (result,) = struct.unpack(fmt, bytes(byte_list))
    return BuiltinResult(value=float(result))


def _builtin_cobol_blank_when_zero(args: list[TypedValue], vm: Any) -> BuiltinResult:
    """Apply BLANK WHEN ZERO: if numeric value is zero, return EBCDIC spaces.

    Args: [encoded_bytes: list[int], value_str: str, byte_length: int]
    Returns: list[int] — encoded_bytes unchanged, or all-spaces if value is zero.
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    encoded_bytes, value_str, byte_length = args[0].value, args[1].value, args[2].value
    if not isinstance(encoded_bytes, list) or not isinstance(byte_length, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        is_zero = float(str(value_str)) == 0.0
    except (ValueError, TypeError):
        return BuiltinResult(value=encoded_bytes)
    return BuiltinResult(
        value=[ByteConstants.EBCDIC_SPACE] * byte_length if is_zero else encoded_bytes
    )


BYTE_BUILTINS: dict[str, Any] = {
    BuiltinName.NIBBLE_GET: _builtin_nibble_get,
    BuiltinName.NIBBLE_SET: _builtin_nibble_set,
    BuiltinName.BYTE_FROM_INT: _builtin_byte_from_int,
    BuiltinName.INT_FROM_BYTE: _builtin_int_from_byte,
    BuiltinName.BYTES_TO_STRING: _builtin_bytes_to_string,
    BuiltinName.STRING_TO_BYTES: _builtin_string_to_bytes,
    BuiltinName.LIST_GET: _builtin_list_get,
    BuiltinName.LIST_SET: _builtin_list_set,
    BuiltinName.LIST_LEN: _builtin_list_len,
    BuiltinName.LIST_SLICE: _builtin_list_slice,
    BuiltinName.LIST_CONCAT: _builtin_list_concat,
    BuiltinName.MAKE_LIST: _builtin_make_list,
    BuiltinName.COBOL_PREPARE_DIGITS: _builtin_cobol_prepare_digits,
    BuiltinName.COBOL_PREPARE_SIGN: _builtin_cobol_prepare_sign,
    BuiltinName.STRING_FIND: _builtin_string_find,
    BuiltinName.STRING_SPLIT: _builtin_string_split,
    BuiltinName.STRING_COUNT: _builtin_string_count,
    BuiltinName.STRING_REPLACE: _builtin_string_replace,
    BuiltinName.STRING_CONCAT: _builtin_string_concat,
    BuiltinName.STRING_CONCAT_PAIR: _builtin_string_concat_pair,
    BuiltinName.INT_TO_BINARY_BYTES: _builtin_int_to_binary_bytes,
    BuiltinName.BINARY_BYTES_TO_INT: _builtin_binary_bytes_to_int,
    BuiltinName.FLOAT_TO_BYTES: _builtin_float_to_bytes,
    BuiltinName.BYTES_TO_FLOAT: _builtin_bytes_to_float,
    BuiltinName.COBOL_BLANK_WHEN_ZERO: _builtin_cobol_blank_when_zero,
}
