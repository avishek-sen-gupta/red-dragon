# pyright: standard
"""Primitive byte-manipulation builtins for the symbolic interpreter.

These are the atoms from which all COBOL encoding/decoding is built in IR.
Language-agnostic — no COBOL-specific logic here.
"""

from __future__ import annotations

import math
import struct

from interpreter.cobol.cobol_constants import (
    BuiltinName,
    ByteConstants,
    CobolEncoding,
    NibblePosition,
    ReplaceMode,
    TallyMode,
)
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators, VMState, _is_symbolic
from interpreter.vm.vm_types import BuiltinResult

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_nibble_get(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_nibble_set(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_byte_from_int(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Clamp/mask integer to 0-255.

    Args: [value: int]
    Returns: int (0-255)
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=args[0].value & ByteConstants.BYTE_MASK)


def _builtin_int_from_byte(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Identity — for semantic clarity in IR.

    Args: [byte_val: int]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=args[0].value)


def _builtin_bytes_to_string(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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
    if encoding == CobolEncoding.LATIN1:
        # Byte-faithful identity: every byte 0-255 maps 1:1 to a code point.
        return BuiltinResult(value=raw.decode("latin-1"))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_string_to_bytes(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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
    if encoding == CobolEncoding.LATIN1:
        # Byte-faithful identity: every code point 0-255 maps 1:1 to a byte.
        return BuiltinResult(value=list(string.encode("latin-1")))
    return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_list_get(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_list_set(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_list_len(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Return list length.

    Args: [lst: list]
    Returns: int
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, list):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=len(args[0].value))


def _builtin_list_slice(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_list_concat(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_make_list(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_cobol_prepare_digits(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_cobol_prepare_sign(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_string_find(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_string_split(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_multi_delimiter_split(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Split source on whichever candidate delimiter matches nearest, repeated
    until the source is exhausted (COBOL UNSTRING ... DELIMITED BY d1 OR d2 OR ...).

    Args: [source: str, delim1: str, delim2: str, ...] — one or more delimiters.
    Returns: list[str]. A single delimiter behaves identically to
        str.split(delimiter) (str.split's own behavior is the N=1 case of this
        same repeated-nearest-match scan).
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source = args[0].value
    delimiters = [a.value for a in args[1:]]
    if not isinstance(source, str) or not all(isinstance(d, str) for d in delimiters):
        return BuiltinResult(value=_UNCOMPUTABLE)
    parts: list[str] = []
    remaining = source
    while True:
        best_pos = -1
        best_delim = ""
        for d in delimiters:
            if not d:
                continue
            pos = remaining.find(d)
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos
                best_delim = d
        if best_pos < 0:
            parts.append(remaining)
            break
        parts.append(remaining[:best_pos])
        remaining = remaining[best_pos + len(best_delim) :]
    return BuiltinResult(value=parts)


def _builtin_multi_delimiter_consumed_length(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Length of source consumed by the first target_count delimiter-splits
    (COBOL UNSTRING ... WITH POINTER: the cursor advances past whatever was
    actually consumed, delimiter included — not an assumed fixed delimiter
    width). Performs the same repeated-nearest-match scan as
    MULTI_DELIMITER_SPLIT, but returns the consumed prefix length instead of
    the split parts.

    Args: [source: str, target_count: int, delim1: str, delim2: str, ...]
    Returns: int. If fewer than target_count delimiters are found, returns
        len(source) (the whole remaining source was consumed).
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source = args[0].value
    target_count = args[1].value
    delimiters = [a.value for a in args[2:]]
    if (
        not isinstance(source, str)
        or not isinstance(target_count, int)
        or not all(isinstance(d, str) for d in delimiters)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    consumed = 0
    remaining = source
    for _ in range(target_count):
        best_pos = -1
        best_delim = ""
        for d in delimiters:
            if not d:
                continue
            pos = remaining.find(d)
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos
                best_delim = d
        if best_pos < 0:
            consumed += len(remaining)
            remaining = ""
            break
        consumed += best_pos + len(best_delim)
        remaining = remaining[best_pos + len(best_delim) :]
    return BuiltinResult(value=consumed)


def _builtin_string_count(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_string_boundary_slice(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Slice source down to a BEFORE/AFTER INITIAL boundary.

    Args: [source: str, boundary_text: str, kind: str ("before"/"after")]
    Returns: str — the bounded region; if boundary_text is not found at all,
        the entire source string is returned unchanged (standard COBOL
        behavior per red-dragon-4q25.13 acceptance criterion 5).
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, boundary_text, kind = (a.value for a in args)
    if not all(isinstance(v, str) for v in (source, boundary_text, kind)):
        return BuiltinResult(value=_UNCOMPUTABLE)
    pos = source.find(boundary_text)
    if pos < 0:
        return BuiltinResult(value=source)
    if kind == "before":
        return BuiltinResult(value=source[:pos])
    return BuiltinResult(value=source[pos + len(boundary_text) :])


def _builtin_string_boundary_split(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Split source at a BEFORE/AFTER INITIAL boundary into [bounded, remainder].

    Args: [source: str, boundary_text: str, kind: str ("before"/"after")]
    Returns: list[str] of exactly 2 elements: [bounded_part, remainder_part].
        bounded_part is the region a bounded operation (e.g. REPLACING) should
        act on; remainder_part is everything else in source, to be spliced
        back around the (possibly modified) bounded_part to reconstruct the
        full string. If boundary_text is not found at all, bounded_part is
        the entire source and remainder_part is "" (nothing left over) —
        consistent with STRING_BOUNDARY_SLICE's own not-found fallback.
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, boundary_text, kind = (a.value for a in args)
    if not all(isinstance(v, str) for v in (source, boundary_text, kind)):
        return BuiltinResult(value=_UNCOMPUTABLE)
    pos = source.find(boundary_text)
    if pos < 0:
        return BuiltinResult(value=[source, ""])
    if kind == "before":
        return BuiltinResult(value=[source[:pos], source[pos:]])
    return BuiltinResult(
        value=[source[pos + len(boundary_text) :], source[: pos + len(boundary_text)]]
    )


def _builtin_string_replace(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_string_concat(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_string_concat_pair(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Concatenate two strings.

    Args: [left: str, right: str]
    Returns: str
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    left, right = args[0].value, args[1].value
    return BuiltinResult(value=str(left) + str(right))


def _builtin_int_to_binary_bytes(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_binary_bytes_to_int(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_float_to_bytes(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_bytes_to_float(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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


def _builtin_cobol_blank_when_zero(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
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


def _builtin_cobol_round(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Round a numeric value using COBOL ROUNDED semantics (half-away-from-zero).

    Args: [value_str: str, decimal_digits: int]
    Returns: str — the rounded value as a string.
    """
    if (
        len(args) < 2
        or any(_is_symbolic(a.value) for a in args)
        or any(a.value is _UNCOMPUTABLE for a in args)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from decimal import ROUND_HALF_UP, Decimal

    decimal_digits = int(args[1].value)
    quantizer = Decimal(10) ** -decimal_digits
    d = Decimal(str(args[0].value)).quantize(quantizer, rounding=ROUND_HALF_UP)
    return BuiltinResult(value=str(d))


def _builtin_cobol_apply_edit_picture(
    args: list[TypedValue], vm: VMState
) -> BuiltinResult:
    """Apply a COBOL numeric edit picture to a numeric value string.

    Args: [value_str: str, pic_string: str]
    Returns: str — the edited display string, exactly the picture's width.
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from interpreter.cobol.edit_picture import format_edited

    value_str, pic_string = str(args[0].value), str(args[1].value)
    return BuiltinResult(value=format_edited(value_str, pic_string))


def _builtin_string_slice(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Extract substring: value[start : start + length].

    Args: [value: str, start: int, length: int]
    Returns: str
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    start = int(args[1].value)
    length = int(args[2].value)
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value[start : start + length])


def _builtin_string_splice(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Replace substring: value[:start] + replacement + value[start + length:].

    Args: [value: str, start: int, length: int, replacement: str]
    Returns: str
    """
    if len(args) < 4 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    start = int(args[1].value)
    length = int(args[2].value)
    replacement = args[3].value
    if not isinstance(value, str) or not isinstance(replacement, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value[:start] + replacement + value[start + length :])


def _builtin_string_zfill(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Zero-pad a string on the left to the given width.

    Args: [value: str, width: int]
    Returns: str — value.zfill(width) but never truncates if longer
    """
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    width = int(args[1].value)
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value.zfill(width))


def _builtin_upper_case(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION UPPER-CASE: uppercase a string value.

    Args: [value: str]
    Returns: str
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value.upper())


def _builtin_lower_case(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION LOWER-CASE: lowercase a string value.

    Args: [value: str]
    Returns: str
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value.lower())


def _builtin_cobol_trim(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION TRIM: strip leading and trailing spaces from a string.

    COBOL FUNCTION TRIM defaults to removing spaces from BOTH ends (the
    LEADING/TRAILING qualifiers are optional). CardDemo's 1205-COMPARE-OLD-NEW
    uses it to normalise fields before comparison.

    Args: [value: str]
    Returns: str
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value.strip(" "))


def _builtin_current_date(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION CURRENT-DATE: 21-char timestamp string.

    Format (21 chars): YYYYMMDD HHMMSS hh ±hhmm
      - 8 chars date (YYYYMMDD)
      - 6 chars time (HHMMSS)
      - 2 chars hundredths of a second (hh)
      - 1 char GMT offset sign (+/-)
      - 4 chars GMT offset magnitude (hhmm)

    No arguments.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M%S")
    hundredths = f"{now.microsecond // 10000:02d}"
    # UTC: GMT offset is +00:00, encoded as sign (+) plus 4-char "hhmm" ("0000").
    gmt_part = "+0000"
    return BuiltinResult(value=date_part + time_part + hundredths + gmt_part)


def _builtin_is_numeric(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL `IS NUMERIC` class test for an alphanumeric operand.

    Args: [value: str]
    Returns: bool — True when the value is non-empty and all characters are
    digits. Sign/decimal handling for signed display numerics is deferred; the
    common all-digits case is covered (red-dragon-pz9g.20).
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=len(value) > 0 and value.isdigit())


def _builtin_is_alphabetic(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL `IS ALPHABETIC` class test for an alphanumeric operand.

    Args: [value: str]
    Returns: bool — True when every character is a letter or a space.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=all(ch.isalpha() or ch == " " for ch in value))


def _builtin_is_alphabetic_lower(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL `IS ALPHABETIC-LOWER` class test.

    Args: [value: str]
    Returns: bool — True when every character is a lowercase letter or a space.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(
        value=all((ch.isalpha() and ch.islower()) or ch == " " for ch in value)
    )


def _builtin_is_alphabetic_upper(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL `IS ALPHABETIC-UPPER` class test.

    Args: [value: str]
    Returns: bool — True when every character is an uppercase letter or a space.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(
        value=all((ch.isalpha() and ch.isupper()) or ch == " " for ch in value)
    )


def _numval_to_number(text: str):
    """Parse a NUMVAL/NUMVAL-C cleaned numeric string to int or Decimal.

    `text` must already have currency/grouping stripped (NUMVAL-C) or be a raw
    NUMVAL argument. Recognises a leading or trailing `+`/`-` sign and the
    trailing credit/debit markers `CR`/`DB` (both negative). Surrounding spaces
    are ignored. An all-blank/empty argument is zero. Returns an int when the
    value has no fractional part, otherwise a Decimal (mirrors how other COBOL
    numeric builtins keep exact decimals).
    """
    from decimal import Decimal, InvalidOperation

    s = text.strip().upper()
    if not s:
        return 0
    negative = False
    # Trailing credit/debit markers -> negative.
    if s.endswith("CR") or s.endswith("DB"):
        negative = True
        s = s[:-2].strip()
    # Leading sign.
    if s and s[0] in "+-":
        negative = negative ^ (s[0] == "-")
        s = s[1:].strip()
    # Trailing sign.
    if s and s[-1] in "+-":
        negative = negative ^ (s[-1] == "-")
        s = s[:-1].strip()
    s = s.replace(" ", "")
    if not s:
        return 0
    try:
        dec = Decimal(s)
    except InvalidOperation:
        return None
    if negative:
        dec = -dec
    # Collapse to int when integral so callers comparing against 0 see ints.
    if dec == dec.to_integral_value():
        return int(dec)
    return dec


def _numval_c_clean(text: str) -> str:
    """Strip currency symbol and grouping commas for the NUMVAL-C grammar."""
    out = []
    for ch in text:
        if ch in "$,":
            continue
        out.append(ch)
    return "".join(out)


def _builtin_length(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION LENGTH(x): byte length of the argument.

    Args: [value: str]
    Returns: int — len(value). The argument is the character data of the
    operand; a PIC X(n) field arrives space-padded to width n, so LENGTH yields
    that width. (Distinct from the `LENGTH OF` ref-mod special register.)
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=len(value))


def _builtin_numval(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION NUMVAL(s): numeric value of a numeric string.

    Supports surrounding spaces, a decimal point, a leading or trailing
    `+`/`-` sign and trailing `CR`/`DB` markers. Returns int when integral else
    Decimal. An all-blank argument is 0.

    Deferred edge cases: locale decimal-comma, embedded blanks between digits,
    and explicit `E` exponents are not handled (not used by COACTUPC).
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    result = _numval_to_number(value)
    if result is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=result)


def _builtin_numval_c(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION NUMVAL-C(s): like NUMVAL but tolerant of a currency
    symbol (`$`) and grouping commas (e.g. "$1,234.56" -> 1234.56).

    Deferred edge cases: non-`$` currency symbols and locale grouping/decimal
    conventions are not handled (COACTUPC uses `$`/`,`/`.`).
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    result = _numval_to_number(_numval_c_clean(value))
    if result is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=result)


def _test_numval_offset(text: str, *, currency: bool) -> int:
    """Validate a NUMVAL[-C] argument; 0 if valid else 1-based bad-char pos.

    Per ISO COBOL the result is the character position of the first character
    that violates the NUMVAL grammar. We implement the common grammar:
    optional leading spaces, an optional leading sign, digits with at most one
    decimal point, optional trailing sign or CR/DB, optional trailing spaces.
    For NUMVAL-C a `$` (leading, after spaces/sign) and grouping `,` are also
    permitted. An all-blank/empty argument is valid (0).

    Deferred: exact ISO positional rules for malformed sign/decimal ordering are
    simplified to "first character not consumable by the grammar".
    """
    if text.strip() == "":
        return 0
    seen_digit = False
    seen_dot = False
    seen_sign = False
    i = 0
    n = len(text)
    # Leading spaces.
    while i < n and text[i] == " ":
        i += 1
    # Optional leading sign.
    if i < n and text[i] in "+-":
        seen_sign = True
        i += 1
        while i < n and text[i] == " ":
            i += 1
    # Optional leading currency.
    if currency and i < n and text[i] == "$":
        i += 1
    while i < n:
        ch = text[i]
        if ch.isdigit():
            seen_digit = True
            i += 1
        elif ch == "." and not seen_dot:
            seen_dot = True
            i += 1
        elif currency and ch == ",":
            i += 1
        elif ch == " ":
            break
        else:
            break
    # Optional trailing sign or CR/DB.
    rest = text[i:]
    stripped = rest.strip()
    if stripped in ("+", "-") and not seen_sign:
        i = n
        stripped = ""
    elif stripped.upper() in ("CR", "DB"):
        i = n
        stripped = ""
    # Remaining must be only trailing spaces.
    while i < n and text[i] == " ":
        i += 1
    if i < n:
        return i + 1
    if not seen_digit:
        return 1
    return 0


def _builtin_test_numval(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION TEST-NUMVAL(s): 0 if s is a valid NUMVAL argument else the
    1-based position of the first offending character (red-dragon-zuhj).
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_test_numval_offset(value, currency=False))


def _builtin_test_numval_c(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION TEST-NUMVAL-C(s): 0 if s is a valid NUMVAL-C argument else
    the 1-based position of the first offending character (red-dragon-zuhj).
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_test_numval_offset(value, currency=True))


def _builtin_integer_of_date(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION INTEGER-OF-DATE(yyyymmdd): integer date.

    Returns the number of days from the COBOL standard epoch (1600-12-31) to the
    given Gregorian date, so 1601-01-01 is day 1 (verified: 2024-01-01 = 154498).
    The argument may be an int or a numeric string of the form CCYYMMDD.

    Deferred: invalid dates (bad month/day) raise via the date constructor and
    yield UNCOMPUTABLE rather than an ISO-defined error code.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from datetime import date

    raw = args[0].value
    if isinstance(raw, float):
        raw = int(raw)
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw.isdigit():
            return BuiltinResult(value=_UNCOMPUTABLE)
        raw = int(raw)
    if not isinstance(raw, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    year, month, day = raw // 10000, (raw // 100) % 100, raw % 100
    try:
        target = date(year, month, day)
    except ValueError:
        return BuiltinResult(value=_UNCOMPUTABLE)
    epoch = date(1600, 12, 31)
    return BuiltinResult(value=(target - epoch).days)


def _coerce_intrinsic_int(raw: object) -> int | None:
    """Coerce a builtin argument value to an int, or None if not integer-valued.

    Accepts ints, integer-valued floats, and numeric strings (optional sign).
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw) if raw == int(raw) else None
    if isinstance(raw, str):
        s = raw.strip()
        digits = s.lstrip("+-")
        if digits.isdigit():
            return -int(digits) if s.startswith("-") else int(digits)
    return None


def _builtin_mod(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MOD(x, y): x modulo y.

    Defined as x - y * FUNCTION INTEGER(x / y), i.e. a floored modulo whose
    result carries the sign of the divisor y — which is exactly Python's ``%``
    for integers (MOD(-7, 3) == 2, MOD(7, -3) == -2). Arguments are integers; a
    zero divisor or a non-integer/symbolic argument yields UNCOMPUTABLE.
    """
    if len(args) < 2 or _is_symbolic(args[0].value) or _is_symbolic(args[1].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_int(args[0].value)
    y = _coerce_intrinsic_int(args[1].value)
    if x is None or y is None or y == 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=x % y)


def _builtin_date_of_integer(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION DATE-OF-INTEGER(n): the Gregorian date as a CCYYMMDD integer.

    Inverse of INTEGER-OF-DATE: n is the number of days after the COBOL standard
    epoch (1600-12-31), so 1 -> 16010101 and 154498 -> 20240101. A non-positive,
    out-of-range, non-integer, or symbolic argument yields UNCOMPUTABLE.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from datetime import date, timedelta

    n = _coerce_intrinsic_int(args[0].value)
    if n is None or n < 1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    epoch = date(1600, 12, 31)
    try:
        d = epoch + timedelta(days=n)
    except (OverflowError, ValueError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=d.year * 10000 + d.month * 100 + d.day)


def _builtin_string_convert(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """INSPECT ... CONVERTING from TO to: positional per-character translate.

    Args: [source: str, from_chars: str, to_chars: str]
    Returns: str — every character of `source` that appears in `from_chars` is
    replaced by the character at the same position in `to_chars`; other
    characters are left unchanged. When a character occurs more than once in
    `from_chars`, its first position determines the mapping (COBOL semantics).

    Deferred edge cases: the optional BEFORE/AFTER delimiter phrase is not
    handled (CardDemo's alpha edits convert the whole reference-modified slice).
    """
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    source, from_chars, to_chars = args[0].value, args[1].value, args[2].value
    if (
        not isinstance(source, str)
        or not isinstance(from_chars, str)
        or not isinstance(to_chars, str)
    ):
        return BuiltinResult(value=_UNCOMPUTABLE)
    table: dict[str, str] = {}
    for i, ch in enumerate(from_chars):
        if ch in table:
            continue  # first occurrence wins
        table[ch] = to_chars[i] if i < len(to_chars) else ch
    return BuiltinResult(value="".join(table.get(ch, ch) for ch in source))


def _builtin_reverse(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION REVERSE(s): s with characters in reverse order."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=value[::-1])


def _coerce_intrinsic_decimal(raw: object):
    """Coerce a builtin argument value to a Decimal, or None if not numeric.

    Accepts ints, floats, Decimals, and numeric strings. Shared by MAX/MIN/SUM
    so mixed int/float/string arguments compare and combine without the
    ``TypeError`` Python raises for direct Decimal-vs-float comparison.
    """
    from decimal import Decimal, InvalidOperation

    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, Decimal)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


def _decimal_to_intrinsic(value):
    """Decimal -> int when integral, else Decimal (mirrors NUMVAL's convention)."""
    return int(value) if value == value.to_integral_value() else value


def _builtin_max(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MAX(a, b, ...): the largest numeric argument."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    values = []
    for a in args:
        if _is_symbolic(a.value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        d = _coerce_intrinsic_decimal(a.value)
        if d is None:
            return BuiltinResult(value=_UNCOMPUTABLE)
        values.append(d)
    return BuiltinResult(value=_decimal_to_intrinsic(max(values)))


def _builtin_min(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MIN(a, b, ...): the smallest numeric argument."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    values = []
    for a in args:
        if _is_symbolic(a.value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        d = _coerce_intrinsic_decimal(a.value)
        if d is None:
            return BuiltinResult(value=_UNCOMPUTABLE)
        values.append(d)
    return BuiltinResult(value=_decimal_to_intrinsic(min(values)))


def _builtin_sum(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION SUM(a, b, ...): the sum of all numeric arguments.

    No arguments sums to 0 (matches the ISO definition of an empty SUM).
    """
    from decimal import Decimal

    values = []
    for a in args:
        if _is_symbolic(a.value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        d = _coerce_intrinsic_decimal(a.value)
        if d is None:
            return BuiltinResult(value=_UNCOMPUTABLE)
        values.append(d)
    return BuiltinResult(value=_decimal_to_intrinsic(sum(values, Decimal(0))))


def _builtin_random(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION RANDOM [(seed)]: next value 0 <= n < 1 in a VM-scoped
    pseudo-random sequence backed by Python's ``random`` module — an accepted
    deviation from ISO COBOL's implementation-defined generator (red-dragon-clpn).

    No argument: returns the next value in the current sequence (a fresh
    unseeded generator on first use). seed == 0: reseed non-reproducibly from
    system entropy. seed > 0: reseed deterministically and remember the seed.
    seed < 0: restart the sequence from the last positive seed supplied (falls
    back to a fresh unseeded generator if none was ever supplied).
    """
    import random as _random_mod

    if vm.cobol_random is None:
        vm.cobol_random = _random_mod.Random()

    if args:
        if _is_symbolic(args[0].value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        seed = _coerce_intrinsic_int(args[0].value)
        if seed is None:
            return BuiltinResult(value=_UNCOMPUTABLE)
        if seed > 0:
            vm.cobol_random = _random_mod.Random(seed)
            vm.cobol_random_seed = seed
        elif seed == 0:
            vm.cobol_random = _random_mod.Random()
        elif vm.cobol_random_seed is not None:
            vm.cobol_random = _random_mod.Random(vm.cobol_random_seed)
        else:
            vm.cobol_random = _random_mod.Random()

    return BuiltinResult(value=vm.cobol_random.random())


def _coerce_intrinsic_float(raw: object) -> float | None:
    """Coerce a builtin argument value to a float, or None if not numeric."""
    d = _coerce_intrinsic_decimal(raw)
    return float(d) if d is not None else None


def _builtin_abs(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ABS(x): the absolute value of x."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_decimal_to_intrinsic(abs(d)))


def _builtin_sqrt(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION SQRT(x): the non-negative square root of x.

    Uses Decimal.sqrt() (28 significant digits by default) so perfect squares
    come back exact rather than float-approximated. A negative argument is an
    ISO-defined argument error and yields UNCOMPUTABLE.
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None or d < 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_decimal_to_intrinsic(d.sqrt()))


def _builtin_sin(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION SIN(x): the sine of x (radians)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.sin(x))


def _builtin_cos(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION COS(x): the cosine of x (radians)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.cos(x))


def _builtin_tan(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION TAN(x): the tangent of x (radians)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.tan(x))


def _builtin_asin(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ASIN(x): the arcsine of x (radians); x must be in [-1,1]."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None or x < -1 or x > 1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.asin(x))


def _builtin_acos(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ACOS(x): the arccosine of x (radians); x must be in [-1,1]."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None or x < -1 or x > 1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.acos(x))


def _builtin_atan(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ATAN(x): the arctangent of x (radians); no domain restriction."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.atan(x))


def _coerce_intrinsic_decimal_list(args: list[TypedValue]):
    """Coerce every arg's value to Decimal, or return None if any fails/symbolic."""
    values = []
    for a in args:
        if _is_symbolic(a.value):
            return None
        d = _coerce_intrinsic_decimal(a.value)
        if d is None:
            return None
        values.append(d)
    return values


def _builtin_range(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION RANGE(a, b, ...): max(args) - min(args)."""
    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_decimal_to_intrinsic(max(values) - min(values)))


def _builtin_mean(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MEAN(a, b, ...): the arithmetic mean of the arguments."""
    from decimal import Decimal

    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(
        value=_decimal_to_intrinsic(sum(values, Decimal(0)) / len(values))
    )


def _builtin_median(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MEDIAN(a, b, ...): the middle value; for an even number
    of arguments, the average of the two middle sorted values."""
    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        result = ordered[mid]
    else:
        result = (ordered[mid - 1] + ordered[mid]) / 2
    return BuiltinResult(value=_decimal_to_intrinsic(result))


def _builtin_midrange(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION MIDRANGE(a, b, ...): (max(args) + min(args)) / 2."""
    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=_decimal_to_intrinsic((max(values) + min(values)) / 2))


def _builtin_variance(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION VARIANCE(a, b, ...): sample variance (n-1 divisor),
    matching the ISO/IBM definition; a single argument yields 0 by convention
    (avoids a division by zero)."""
    from decimal import Decimal

    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    n = len(values)
    if n == 1:
        return BuiltinResult(value=0)
    mean = sum(values, Decimal(0)) / n
    sq_dev = sum(((v - mean) ** 2 for v in values), Decimal(0))
    return BuiltinResult(value=_decimal_to_intrinsic(sq_dev / (n - 1)))


def _builtin_ord_max(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ORD-MAX(a, b, ...): the 1-based position of the first
    occurrence of the largest argument."""
    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=values.index(max(values)) + 1)


def _builtin_ord_min(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ORD-MIN(a, b, ...): the 1-based position of the first
    occurrence of the smallest argument."""
    values = _coerce_intrinsic_decimal_list(args)
    if not values:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=values.index(min(values)) + 1)


def _builtin_concatenate(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION CONCATENATE(a, b, ...): all string arguments joined in order."""
    parts = []
    for a in args:
        if _is_symbolic(a.value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        if not isinstance(a.value, str):
            return BuiltinResult(value=_UNCOMPUTABLE)
        parts.append(a.value)
    return BuiltinResult(value="".join(parts))


def _builtin_exp(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION EXP(x): e^x."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        return BuiltinResult(value=math.exp(x))
    except OverflowError:
        return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_log(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION LOG(x): the natural logarithm of x; x must be > 0
    (ISO argument-error condition otherwise)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None or x <= 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.log(x))


def _builtin_factorial(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION FACTORIAL(n): n! for a non-negative integer n."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None or d < 0 or d != d.to_integral_value():
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.factorial(int(d)))


def _builtin_integer(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION INTEGER(x): the greatest integer not greater than x (floor)."""
    from decimal import ROUND_FLOOR

    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=int(d.to_integral_value(rounding=ROUND_FLOOR)))


def _builtin_integer_part(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION INTEGER-PART(x): x truncated toward zero."""
    from decimal import ROUND_DOWN

    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=int(d.to_integral_value(rounding=ROUND_DOWN)))


def _builtin_fraction_part(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION FRACTION-PART(x): x - FUNCTION INTEGER-PART(x)."""
    from decimal import ROUND_DOWN

    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    d = _coerce_intrinsic_decimal(args[0].value)
    if d is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    trunc = d.to_integral_value(rounding=ROUND_DOWN)
    return BuiltinResult(value=_decimal_to_intrinsic(d - trunc))


def _builtin_rem(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION REM(x, y): x - y * FUNCTION INTEGER-PART(x / y).

    Unlike MOD (floored, sign follows the divisor), REM truncates toward zero
    so its result's sign follows the dividend x.
    """
    from decimal import ROUND_DOWN

    if len(args) < 2 or _is_symbolic(args[0].value) or _is_symbolic(args[1].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_decimal(args[0].value)
    y = _coerce_intrinsic_decimal(args[1].value)
    if x is None or y is None or y == 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    trunc = (x / y).to_integral_value(rounding=ROUND_DOWN)
    return BuiltinResult(value=_decimal_to_intrinsic(x - y * trunc))


def _builtin_substitute(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION SUBSTITUTE(source, search-1, replace-1 [, search-2,
    replace-2]...): every occurrence of each search string replaced by its
    paired replacement, applied in order over the running result (the basic
    ALL-implied form — the FIRST/LAST qualifier extension is not handled).
    """
    if len(args) < 3 or (len(args) - 1) % 2 != 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    if any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not isinstance(args[0].value, str):
        return BuiltinResult(value=_UNCOMPUTABLE)
    result = args[0].value
    for i in range(1, len(args), 2):
        search, replacement = args[i].value, args[i + 1].value
        if not isinstance(search, str) or not isinstance(replacement, str):
            return BuiltinResult(value=_UNCOMPUTABLE)
        result = result.replace(search, replacement)
    return BuiltinResult(value=result)


def _builtin_exp10(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION EXP10(x): 10^x."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        return BuiltinResult(value=math.pow(10, x))
    except OverflowError:
        return BuiltinResult(value=_UNCOMPUTABLE)


def _builtin_log10(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION LOG10(x): the base-10 logarithm of x; x must be > 0
    (ISO argument-error condition otherwise)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    x = _coerce_intrinsic_float(args[0].value)
    if x is None or x <= 0:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=math.log10(x))


def _builtin_char(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION CHAR(n): the nth character (1-based) in the program
    collating sequence — this codebase's EBCDIC table. n must be in [1,256].
    """
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    n = _coerce_intrinsic_int(args[0].value)
    if n is None or n < 1 or n > 256:
        return BuiltinResult(value=_UNCOMPUTABLE)
    ascii_code = EbcdicTable.EBCDIC_TO_ASCII[n - 1]
    return BuiltinResult(value=chr(ascii_code))


def _builtin_ord(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ORD(c): the 1-based ordinal position of the single
    character c in the program collating sequence (inverse of CHAR, subject
    to duplicate-mapping collapse in the EBCDIC control-character range)."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if not isinstance(value, str) or len(value) != 1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    ebcdic_byte = EbcdicTable.ASCII_TO_EBCDIC[ord(value)]
    return BuiltinResult(value=ebcdic_byte + 1)


def _builtin_day_of_integer(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION DAY-OF-INTEGER(n): the Julian date YYYYDDD, n days after
    the COBOL standard epoch (1600-12-31). Sibling of DATE-OF-INTEGER, which
    returns the Gregorian YYYYMMDD form of the same day."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from datetime import date, timedelta

    n = _coerce_intrinsic_int(args[0].value)
    if n is None or n < 1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    epoch = date(1600, 12, 31)
    try:
        d = epoch + timedelta(days=n)
    except (OverflowError, ValueError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    day_of_year = (d - date(d.year, 1, 1)).days + 1
    return BuiltinResult(value=d.year * 1000 + day_of_year)


def _builtin_integer_of_day(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION INTEGER-OF-DAY(yyyyddd): integer day count since the
    COBOL standard epoch (1600-12-31); inverse of DAY-OF-INTEGER."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    from datetime import date, timedelta

    raw = _coerce_intrinsic_int(args[0].value)
    if raw is None or raw < 1001:
        return BuiltinResult(value=_UNCOMPUTABLE)
    year, ddd = raw // 1000, raw % 1000
    if ddd < 1 or ddd > 366:
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        d = date(year, 1, 1) + timedelta(days=ddd - 1)
    except (OverflowError, ValueError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if d.year != year:
        return BuiltinResult(value=_UNCOMPUTABLE)
    epoch = date(1600, 12, 31)
    return BuiltinResult(value=(d - epoch).days)


def _builtin_annuity(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION ANNUITY(rate, periods): the amortizing payment factor
    for a loan of 1 unit repaid over `periods` periods at interest `rate` —
    rate / (1 - (1+rate)^-periods), or 1/periods when rate is 0."""
    if len(args) < 2 or _is_symbolic(args[0].value) or _is_symbolic(args[1].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    rate = _coerce_intrinsic_decimal(args[0].value)
    periods = _coerce_intrinsic_int(args[1].value)
    if rate is None or periods is None or periods < 1 or rate == -1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    from decimal import Decimal

    if rate == 0:
        return BuiltinResult(value=_decimal_to_intrinsic(Decimal(1) / periods))
    denominator = 1 - (1 + rate) ** (-periods)
    return BuiltinResult(value=_decimal_to_intrinsic(rate / denominator))


def _builtin_present_value(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION PRESENT-VALUE(rate, cashflow-1, ...): the sum of each
    cashflow-i discounted at `rate` for i periods."""
    if len(args) < 2 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    rate = _coerce_intrinsic_decimal(args[0].value)
    if rate is None or rate == -1:
        return BuiltinResult(value=_UNCOMPUTABLE)
    cashflows = _coerce_intrinsic_decimal_list(args[1:])
    if not cashflows:
        return BuiltinResult(value=_UNCOMPUTABLE)
    from decimal import Decimal

    total = sum(
        (cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows)), Decimal(0)
    )
    return BuiltinResult(value=_decimal_to_intrinsic(total))


_DEFAULT_YY_CUTOFF = 50


def _expand_two_digit_year(yy: int, cutoff: int) -> int:
    """Expand a 2-digit year using the standard COBOL sliding-window rule:
    yy >= cutoff -> 1900+yy (previous century); yy < cutoff -> 2000+yy.

    Default cutoff (when omitted by the caller) is 50 — the common
    production COBOL default (IBM Enterprise COBOL, GnuCOBOL), not a
    system-clock-derived window.
    """
    return (1900 if yy >= cutoff else 2000) + yy


def _builtin_date_to_yyyymmdd(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION DATE-TO-YYYYMMDD(yymmdd [, cutoff]): expand a 6-digit
    YYMMDD date to 8-digit YYYYMMDD using the sliding-window year rule."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    raw = _coerce_intrinsic_int(args[0].value)
    if raw is None or raw < 0 or raw > 999999:
        return BuiltinResult(value=_UNCOMPUTABLE)
    cutoff = _DEFAULT_YY_CUTOFF
    if len(args) >= 2:
        if _is_symbolic(args[1].value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        c = _coerce_intrinsic_int(args[1].value)
        if c is None or c < 0 or c > 99:
            return BuiltinResult(value=_UNCOMPUTABLE)
        cutoff = c
    yy, mmdd = raw // 10000, raw % 10000
    return BuiltinResult(value=_expand_two_digit_year(yy, cutoff) * 10000 + mmdd)


def _builtin_day_to_yyyyddd(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION DAY-TO-YYYYDDD(yyddd [, cutoff]): expand a 5-digit
    YYDDD Julian date to 7-digit YYYYDDD using the sliding-window year rule."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    raw = _coerce_intrinsic_int(args[0].value)
    if raw is None or raw < 0 or raw > 99999:
        return BuiltinResult(value=_UNCOMPUTABLE)
    cutoff = _DEFAULT_YY_CUTOFF
    if len(args) >= 2:
        if _is_symbolic(args[1].value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        c = _coerce_intrinsic_int(args[1].value)
        if c is None or c < 0 or c > 99:
            return BuiltinResult(value=_UNCOMPUTABLE)
        cutoff = c
    yy, ddd = raw // 1000, raw % 1000
    return BuiltinResult(value=_expand_two_digit_year(yy, cutoff) * 1000 + ddd)


def _builtin_year_to_yyyy(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """COBOL FUNCTION YEAR-TO-YYYY(yy [, cutoff]): expand a 2-digit year to a
    4-digit year using the sliding-window year rule."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    yy = _coerce_intrinsic_int(args[0].value)
    if yy is None or yy < 0 or yy > 99:
        return BuiltinResult(value=_UNCOMPUTABLE)
    cutoff = _DEFAULT_YY_CUTOFF
    if len(args) >= 2:
        if _is_symbolic(args[1].value):
            return BuiltinResult(value=_UNCOMPUTABLE)
        c = _coerce_intrinsic_int(args[1].value)
        if c is None or c < 0 or c > 99:
            return BuiltinResult(value=_UNCOMPUTABLE)
        cutoff = c
    return BuiltinResult(value=_expand_two_digit_year(yy, cutoff))


from typing import Any

BYTE_BUILTINS: dict[FuncName, Any] = (
    {  # Any: Callable[(list[TypedValue], VMState) -> BuiltinResult] — builtin boundary
        FuncName(BuiltinName.NIBBLE_GET): _builtin_nibble_get,
        FuncName(BuiltinName.NIBBLE_SET): _builtin_nibble_set,
        FuncName(BuiltinName.BYTE_FROM_INT): _builtin_byte_from_int,
        FuncName(BuiltinName.INT_FROM_BYTE): _builtin_int_from_byte,
        FuncName(BuiltinName.BYTES_TO_STRING): _builtin_bytes_to_string,
        FuncName(BuiltinName.STRING_TO_BYTES): _builtin_string_to_bytes,
        FuncName(BuiltinName.LIST_GET): _builtin_list_get,
        FuncName(BuiltinName.LIST_SET): _builtin_list_set,
        FuncName(BuiltinName.LIST_LEN): _builtin_list_len,
        FuncName(BuiltinName.LIST_SLICE): _builtin_list_slice,
        FuncName(BuiltinName.LIST_CONCAT): _builtin_list_concat,
        FuncName(BuiltinName.MAKE_LIST): _builtin_make_list,
        FuncName(BuiltinName.COBOL_PREPARE_DIGITS): _builtin_cobol_prepare_digits,
        FuncName(BuiltinName.COBOL_PREPARE_SIGN): _builtin_cobol_prepare_sign,
        FuncName(BuiltinName.STRING_FIND): _builtin_string_find,
        FuncName(BuiltinName.STRING_SPLIT): _builtin_string_split,
        FuncName(BuiltinName.MULTI_DELIMITER_SPLIT): _builtin_multi_delimiter_split,
        FuncName(
            BuiltinName.MULTI_DELIMITER_CONSUMED_LENGTH
        ): _builtin_multi_delimiter_consumed_length,
        FuncName(BuiltinName.STRING_COUNT): _builtin_string_count,
        FuncName(BuiltinName.STRING_REPLACE): _builtin_string_replace,
        FuncName(BuiltinName.STRING_CONCAT): _builtin_string_concat,
        FuncName(BuiltinName.STRING_CONCAT_PAIR): _builtin_string_concat_pair,
        FuncName(BuiltinName.INT_TO_BINARY_BYTES): _builtin_int_to_binary_bytes,
        FuncName(BuiltinName.BINARY_BYTES_TO_INT): _builtin_binary_bytes_to_int,
        FuncName(BuiltinName.FLOAT_TO_BYTES): _builtin_float_to_bytes,
        FuncName(BuiltinName.BYTES_TO_FLOAT): _builtin_bytes_to_float,
        FuncName(BuiltinName.COBOL_BLANK_WHEN_ZERO): _builtin_cobol_blank_when_zero,
        FuncName(BuiltinName.COBOL_ROUND): _builtin_cobol_round,
        FuncName(
            BuiltinName.COBOL_APPLY_EDIT_PICTURE
        ): _builtin_cobol_apply_edit_picture,
        FuncName(BuiltinName.STRING_SLICE): _builtin_string_slice,
        FuncName(BuiltinName.STRING_BOUNDARY_SLICE): _builtin_string_boundary_slice,
        FuncName(BuiltinName.STRING_BOUNDARY_SPLIT): _builtin_string_boundary_split,
        FuncName(BuiltinName.STRING_SPLICE): _builtin_string_splice,
        FuncName(BuiltinName.STRING_ZFILL): _builtin_string_zfill,
        FuncName(BuiltinName.UPPER_CASE): _builtin_upper_case,
        FuncName(BuiltinName.LOWER_CASE): _builtin_lower_case,
        FuncName(BuiltinName.TRIM): _builtin_cobol_trim,
        FuncName(BuiltinName.CURRENT_DATE): _builtin_current_date,
        FuncName(BuiltinName.IS_NUMERIC): _builtin_is_numeric,
        FuncName(BuiltinName.IS_ALPHABETIC): _builtin_is_alphabetic,
        FuncName(BuiltinName.IS_ALPHABETIC_LOWER): _builtin_is_alphabetic_lower,
        FuncName(BuiltinName.IS_ALPHABETIC_UPPER): _builtin_is_alphabetic_upper,
        FuncName(BuiltinName.LENGTH): _builtin_length,
        FuncName(BuiltinName.NUMVAL): _builtin_numval,
        FuncName(BuiltinName.NUMVAL_C): _builtin_numval_c,
        FuncName(BuiltinName.TEST_NUMVAL): _builtin_test_numval,
        FuncName(BuiltinName.TEST_NUMVAL_C): _builtin_test_numval_c,
        FuncName(BuiltinName.INTEGER_OF_DATE): _builtin_integer_of_date,
        FuncName(BuiltinName.DATE_OF_INTEGER): _builtin_date_of_integer,
        FuncName(BuiltinName.MOD): _builtin_mod,
        FuncName(BuiltinName.STRING_CONVERT): _builtin_string_convert,
        FuncName(BuiltinName.REVERSE): _builtin_reverse,
        FuncName(BuiltinName.MAX): _builtin_max,
        FuncName(BuiltinName.MIN): _builtin_min,
        FuncName(BuiltinName.SUM): _builtin_sum,
        FuncName(BuiltinName.RANDOM): _builtin_random,
        FuncName(BuiltinName.ABS): _builtin_abs,
        FuncName(BuiltinName.SQRT): _builtin_sqrt,
        FuncName(BuiltinName.SIN): _builtin_sin,
        FuncName(BuiltinName.COS): _builtin_cos,
        FuncName(BuiltinName.TAN): _builtin_tan,
        FuncName(BuiltinName.ASIN): _builtin_asin,
        FuncName(BuiltinName.ACOS): _builtin_acos,
        FuncName(BuiltinName.ATAN): _builtin_atan,
        FuncName(BuiltinName.RANGE): _builtin_range,
        FuncName(BuiltinName.MEAN): _builtin_mean,
        FuncName(BuiltinName.MEDIAN): _builtin_median,
        FuncName(BuiltinName.MIDRANGE): _builtin_midrange,
        FuncName(BuiltinName.VARIANCE): _builtin_variance,
        FuncName(BuiltinName.ORD_MAX): _builtin_ord_max,
        FuncName(BuiltinName.ORD_MIN): _builtin_ord_min,
        FuncName(BuiltinName.CONCATENATE): _builtin_concatenate,
        FuncName(BuiltinName.EXP): _builtin_exp,
        FuncName(BuiltinName.LOG): _builtin_log,
        FuncName(BuiltinName.FACTORIAL): _builtin_factorial,
        FuncName(BuiltinName.INTEGER): _builtin_integer,
        FuncName(BuiltinName.INTEGER_PART): _builtin_integer_part,
        FuncName(BuiltinName.FRACTION_PART): _builtin_fraction_part,
        FuncName(BuiltinName.REM): _builtin_rem,
        FuncName(BuiltinName.SUBSTITUTE): _builtin_substitute,
        FuncName(BuiltinName.EXP10): _builtin_exp10,
        FuncName(BuiltinName.LOG10): _builtin_log10,
        FuncName(BuiltinName.CHAR): _builtin_char,
        FuncName(BuiltinName.ORD): _builtin_ord,
        FuncName(BuiltinName.DAY_OF_INTEGER): _builtin_day_of_integer,
        FuncName(BuiltinName.INTEGER_OF_DAY): _builtin_integer_of_day,
        FuncName(BuiltinName.ANNUITY): _builtin_annuity,
        FuncName(BuiltinName.PRESENT_VALUE): _builtin_present_value,
        FuncName(BuiltinName.DATE_TO_YYYYMMDD): _builtin_date_to_yyyymmdd,
        FuncName(BuiltinName.DAY_TO_YYYYDDD): _builtin_day_to_yyyyddd,
        FuncName(BuiltinName.YEAR_TO_YYYY): _builtin_year_to_yyyy,
    }
)
