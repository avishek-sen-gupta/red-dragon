"""A nonnumeric literal as written in the source, and the characters it stands for."""

from __future__ import annotations

_DELIMITERS = ('"', "'")
_WRITTEN_DELIMITER = '"'


def literal_characters(written: str) -> str:
    """The characters a nonnumeric literal stands for.

    Its delimiters are removed and each doubled delimiter inside it is one
    delimiter character (ANSI X3.23-1985 nonnumeric literals): ``'"A""B"'`` is
    ``A"B``. Text that is not delimited, such as a numeric literal, a figurative
    constant's name or a hexadecimal literal, is returned as written.
    """
    if len(written) >= 2 and written[0] in _DELIMITERS and written[-1] == written[0]:
        return written[1:-1].replace(written[0] * 2, written[0])
    return written


def written_literal(characters: str) -> str:
    """A nonnumeric literal that stands for ``characters``, as the source could write it."""
    doubled = characters.replace(_WRITTEN_DELIMITER, _WRITTEN_DELIMITER * 2)
    return f"{_WRITTEN_DELIMITER}{doubled}{_WRITTEN_DELIMITER}"
