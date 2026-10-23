# pyright: standard
"""Rounding methods (PoO 9-14) and the instruction and FPC codes that select them."""

from collections.abc import Mapping
from enum import Enum


class RoundingMode(Enum):
    NEAREST_EVEN = "nearest-even"
    NEAREST_AWAY = "nearest-away"
    NEAREST_TOWARD_ZERO = "nearest-toward-zero"
    TOWARD_ZERO = "toward-zero"
    TOWARD_POSITIVE = "toward-positive"
    TOWARD_NEGATIVE = "toward-negative"
    AWAY_FROM_ZERO = "away-from-zero"
    PREPARE_SHORTER = "prepare-shorter"


BFP_FPC_MODES: Mapping[int, RoundingMode] = {
    0: RoundingMode.NEAREST_EVEN,
    1: RoundingMode.TOWARD_ZERO,
    2: RoundingMode.TOWARD_POSITIVE,
    3: RoundingMode.TOWARD_NEGATIVE,
    7: RoundingMode.PREPARE_SHORTER,
}

BFP_MODIFIER_MODES: Mapping[int, RoundingMode] = {
    1: RoundingMode.NEAREST_AWAY,
    3: RoundingMode.PREPARE_SHORTER,
    4: RoundingMode.NEAREST_EVEN,
    5: RoundingMode.TOWARD_ZERO,
    6: RoundingMode.TOWARD_POSITIVE,
    7: RoundingMode.TOWARD_NEGATIVE,
}

DFP_FPC_MODES: Mapping[int, RoundingMode] = {
    0: RoundingMode.NEAREST_EVEN,
    1: RoundingMode.TOWARD_ZERO,
    2: RoundingMode.TOWARD_POSITIVE,
    3: RoundingMode.TOWARD_NEGATIVE,
    4: RoundingMode.NEAREST_AWAY,
    5: RoundingMode.NEAREST_TOWARD_ZERO,
    6: RoundingMode.AWAY_FROM_ZERO,
    7: RoundingMode.PREPARE_SHORTER,
}

DFP_MODIFIER_MODES: Mapping[int, RoundingMode] = {
    1: RoundingMode.NEAREST_AWAY,
    3: RoundingMode.PREPARE_SHORTER,
    4: RoundingMode.NEAREST_EVEN,
    5: RoundingMode.TOWARD_ZERO,
    6: RoundingMode.TOWARD_POSITIVE,
    7: RoundingMode.TOWARD_NEGATIVE,
    8: RoundingMode.NEAREST_EVEN,
    9: RoundingMode.TOWARD_ZERO,
    10: RoundingMode.TOWARD_POSITIVE,
    11: RoundingMode.TOWARD_NEGATIVE,
    12: RoundingMode.NEAREST_AWAY,
    13: RoundingMode.NEAREST_TOWARD_ZERO,
    14: RoundingMode.AWAY_FROM_ZERO,
    15: RoundingMode.PREPARE_SHORTER,
}

HFP_MODIFIER_MODES: Mapping[int, RoundingMode] = {
    0: RoundingMode.TOWARD_ZERO,
    1: RoundingMode.NEAREST_AWAY,
    4: RoundingMode.NEAREST_EVEN,
    5: RoundingMode.TOWARD_ZERO,
    6: RoundingMode.TOWARD_POSITIVE,
    7: RoundingMode.TOWARD_NEGATIVE,
}

HFP_TO_BFP_MODIFIER_MODES: Mapping[int, RoundingMode] = {
    0: RoundingMode.TOWARD_ZERO,
    **BFP_MODIFIER_MODES,
}
