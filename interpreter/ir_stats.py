"""Pure functions for computing statistics over IR instruction lists."""

from __future__ import annotations

from collections import Counter

from interpreter.ir import IRInstruction


def count_opcodes(instructions: list[IRInstruction]) -> dict[str, int]:
    """Return a frequency map of opcode names in the given instruction list.

    Args:
        instructions: A list of IR instructions.

    Returns:
        A dict mapping opcode name strings to their occurrence counts.
        Empty dict for an empty input list.
    """
    return dict(Counter(inst.opcode.value for inst in instructions))
