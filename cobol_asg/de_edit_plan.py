"""Where de-editing finds a numeric-edited image's digits and sign, fixed by its PICTURE."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeEditPlan:
    """Each stored digit's image position with its place value, each image
    position whose character makes the value negative, and the decimal places.

    A P position contributes a zero digit, so it has no term but still counts
    toward the place values and the scale.
    """

    digit_terms: tuple[tuple[int, int], ...]
    negative_marks: tuple[tuple[int, str], ...]
    scale: int
