"""TypedValue — wraps a raw value with its type hint for type-aware execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TypedValue:
    """A value paired with its IR type hint.

    When an IR instruction carries a non-empty type_hint and writes to a
    result register, the handler wraps the value in TypedValue so that
    downstream consumers (e.g. BINOP) can apply type-aware coercion.
    """

    value: Any
    type_hint: str = ""
