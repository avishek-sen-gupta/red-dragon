"""Decoding a fixed-format mainframe member's bytes into text.

A leaf module: every path that turns a member's bytes into text goes through
it, so the codec choice is made once and is stated where it can be read.
"""

from __future__ import annotations


def decode_source(raw: bytes) -> str:
    """Decode a mainframe member as 8-bit text.

    Fixed-format members are 8-bit text, not UTF-8. latin-1 is the byte-identity
    codec — defined for all 256 byte values, so it never raises and never loses a
    character, and one byte stays one character so column positions and PIC
    lengths are unaffected.

    Measured on a production corpus (110 of 4639 members carry bytes >= 0x80):

    - No member is valid UTF-8 with non-ASCII content, so attempting UTF-8 first
      would buy nothing — no member would succeed under it.
    - One member has a byte in 0x80-0x9F, the only range where cp1252 and latin-1
      disagree: an opaque sentinel annotated ``CONTAINS HIGH-VALUES``, where
      cp1252's Y-diaeresis is no more correct than latin-1's U+009F. So cp1252
      buys nothing either.
    - ``errors="replace"`` is not free: 146 high bytes sit in the code area inside
      VALUE literals of a report layout, and would become U+FFFD.

    This is a decode choice, not a codepage claim. A genuinely EBCDIC member would
    come through as silent garbage rather than raising; all 110 measured members
    are ASCII with a handful of high bytes, hence ASCII-compatible and not EBCDIC.
    A future EBCDIC corpus needs detection, not this helper.
    """
    return raw.decode("latin-1")
