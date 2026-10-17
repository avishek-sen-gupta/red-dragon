"""STRING's transfer (ANSI X3.23-1985 STRING general rules).

The delimited sendings are moved one character at a time into the receiver,
starting at the pointer. The overflow condition arises when the pointer is
below 1 or past the receiver before the transfer, or when characters remain
once the receiver is full. Characters the transfer does not reach keep their
value, and the pointer advances by the characters moved.
"""

from __future__ import annotations

from collections.abc import Sequence

from interpreter.cobol.string_outcome import StringOutcome


def string_into(receiver: str, pointer: int, parts: Sequence[str]) -> StringOutcome:
    if pointer < 1 or pointer > len(receiver):
        return StringOutcome(image=receiver, pointer=pointer, overflow=True)
    sent = "".join(parts)
    start = pointer - 1
    moved = sent[: len(receiver) - start]
    return StringOutcome(
        image=receiver[:start] + moved + receiver[start + len(moved) :],
        pointer=pointer + len(moved),
        overflow=len(moved) < len(sent),
    )
