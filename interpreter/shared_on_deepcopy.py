"""Base for immutable values that a deepcopy shares instead of rebuilding."""

from collections.abc import Mapping
from typing import Self


class SharedOnDeepcopy:
    def __deepcopy__[T](self, memo: Mapping[int, T]) -> Self:
        return self
