# pyright: standard
"""EBCDIC (Code Page 037) ↔ Latin-1 lookup tables: a bijection over all 256 bytes."""

from __future__ import annotations

_EBCDIC_TO_ASCII: tuple[int, ...] = tuple(
    bytes(range(256)).decode("cp037").encode("latin-1")
)
_ASCII_TO_EBCDIC: tuple[int, ...] = tuple(
    bytes(range(256)).decode("latin-1").encode("cp037")
)


class EbcdicTable:
    """Bidirectional EBCDIC ↔ ASCII conversion tables."""

    EBCDIC_TO_ASCII = _EBCDIC_TO_ASCII
    ASCII_TO_EBCDIC = _ASCII_TO_EBCDIC

    @classmethod
    def ascii_to_ebcdic(cls, data: bytes) -> bytes:
        """Convert ASCII bytes to EBCDIC bytes."""
        return bytes(cls.ASCII_TO_EBCDIC[b] for b in data)

    @classmethod
    def ebcdic_to_ascii(cls, data: bytes) -> bytes:
        """Convert EBCDIC bytes to ASCII bytes."""
        return bytes(cls.EBCDIC_TO_ASCII[b] for b in data)
