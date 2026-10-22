# pyright: standard
"""Unicode conversions and string searches: CU12, CU14, CU21, CU24, CU41, CU42, CUTFU and CUUTF (the older names of CU12 and CU21), SRST and SRSTU."""

from collections.abc import Mapping

from interpreter.hlasm.search_string import SEARCH_STRING, SEARCH_STRING_UNICODE
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unicode_conversion import (
    CONVERT_UTF8_TO_UTF16,
    CONVERT_UTF8_TO_UTF32,
    CONVERT_UTF16_TO_UTF8,
    CONVERT_UTF16_TO_UTF32,
    CONVERT_UTF32_TO_UTF8,
    CONVERT_UTF32_TO_UTF16,
)

UNICODE_STRING_SEARCH_LOWERINGS: Mapping[str, StatementLowering] = {
    "CU12": CONVERT_UTF8_TO_UTF16,
    "CUTFU": CONVERT_UTF8_TO_UTF16,
    "CU14": CONVERT_UTF8_TO_UTF32,
    "CU21": CONVERT_UTF16_TO_UTF8,
    "CUUTF": CONVERT_UTF16_TO_UTF8,
    "CU24": CONVERT_UTF16_TO_UTF32,
    "CU41": CONVERT_UTF32_TO_UTF8,
    "CU42": CONVERT_UTF32_TO_UTF16,
    "SRST": SEARCH_STRING,
    "SRSTU": SEARCH_STRING_UNICODE,
}
