# pyright: standard
"""Positions in an HFP builtin's result list, and its condition bits: the maskable ones sit at their program-mask positions."""

CONDITIONS_SLOT = 3

SIGNIFICANCE_BIT = 0b0001
UNDERFLOW_BIT = 0b0010
OVERFLOW_BIT = 0b1_0000
DIVIDE_BIT = 0b10_0000
SQUARE_ROOT_BIT = 0b100_0000
MASKABLE_BITS = SIGNIFICANCE_BIT | UNDERFLOW_BIT
