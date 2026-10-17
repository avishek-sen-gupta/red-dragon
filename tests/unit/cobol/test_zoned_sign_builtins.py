"""Builtins that take a signed zoned item's operational sign out of its bytes and put it back."""

from __future__ import annotations

from interpreter.cobol.byte_builtins import (
    _builtin_cobol_zoned_restore_sign,
    _builtin_cobol_zoned_strip_sign,
)
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm_types import VMState
from tests.covers import covers


def _args(*values):
    return [typed_from_runtime(v) for v in values]


@covers(CobolFeature.INSPECT_TALLYING, CobolFeature.SIGN_CLAUSE)
def test_strip_leaves_only_the_digit_characters():
    stripped = [
        _builtin_cobol_zoned_strip_sign(_args(*shape), VMState()).value
        for shape in (
            ([0xF1, 0xF2, 0xD3], 2, False),
            ([0xC1, 0xF2, 0xF3], 0, False),
            ([0x60, 0xF1, 0xF2], 0, True),
            ([0xF1, 0xF2, 0x4E], 2, True),
            ([0xF1, 0x40, 0x40], 2, False),
        )
    ]
    assert stripped == [
        [0xF1, 0xF2, 0xF3],
        [0xF1, 0xF2, 0xF3],
        [0xF1, 0xF2],
        [0xF1, 0xF2],
        [0xF1, 0x40, 0x40],
    ]


@covers(CobolFeature.INSPECT_REPLACING, CobolFeature.SIGN_CLAUSE)
def test_restore_puts_the_original_sign_back_on_the_new_digits():
    restored = [
        _builtin_cobol_zoned_restore_sign(_args(*shape), VMState()).value
        for shape in (
            ([0xF9, 0xF2, 0xF3], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF1, 0xF2, 0xF7], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF7, 0xF2, 0xF3], [0xC1, 0xF2, 0xF3], 0, False),
            ([0xF1, 0xF2, 0xC1], [0xF1, 0xF2, 0xD3], 2, False),
            ([0xF9, 0xF2], [0x60, 0xF1, 0xF2], 0, True),
            ([0xF3, 0xF4], [0xF1, 0xF2, 0x60], 2, True),
        )
    ]
    assert restored == [
        [0xF9, 0xF2, 0xD3],
        [0xF1, 0xF2, 0xD7],
        [0xC7, 0xF2, 0xF3],
        [0xF1, 0xF2, 0xC1],
        [0x60, 0xF9, 0xF2],
        [0xF3, 0xF4, 0x60],
    ]
