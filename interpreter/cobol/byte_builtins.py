# pyright: standard
"""Primitive byte-manipulation builtins for the symbolic interpreter.

These are the atoms from which all COBOL encoding/decoding is built in IR.
Language-agnostic — no COBOL-specific logic here.
"""

from __future__ import annotations

import struct
from interpreter.func_name import FuncName
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
        FuncName(BuiltinName.STRING_COUNT): _builtin_string_count,
        FuncName(BuiltinName.STRING_REPLACE): _builtin_string_replace,
        FuncName(BuiltinName.STRING_CONCAT): _builtin_string_concat,
        FuncName(BuiltinName.STRING_CONCAT_PAIR): _builtin_string_concat_pair,
        FuncName(BuiltinName.INT_TO_BINARY_BYTES): _builtin_int_to_binary_bytes,
        FuncName(BuiltinName.BINARY_BYTES_TO_INT): _builtin_binary_bytes_to_int,
        FuncName(BuiltinName.FLOAT_TO_BYTES): _builtin_float_to_bytes,
        FuncName(BuiltinName.BYTES_TO_FLOAT): _builtin_bytes_to_float,
        FuncName(BuiltinName.COBOL_BLANK_WHEN_ZERO): _builtin_cobol_blank_when_zero,
        FuncName(BuiltinName.STRING_SLICE): _builtin_string_slice,
        FuncName(BuiltinName.STRING_SPLICE): _builtin_string_splice,
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
        FuncName(BuiltinName.STRING_CONVERT): _builtin_string_convert,
    }
)
