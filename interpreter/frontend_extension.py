# pyright: standard
"""Generic frontend-extension seams: DialectParser, and a re-export of
RedDragonExtensionLoweringStrategy for backward compatibility.

Only COBOL uses these today, but neither protocol carries COBOL-specific
semantics beyond the ``ctx``/``materialised`` parameter types in
RedDragonExtensionLoweringStrategy — they live in their own module, separate
from ``interpreter.frontend``, so another language's frontend can adopt the
same seam later, and so that ``interpreter.cobol``'s own modules (which need
these types) never have to import through ``interpreter.frontend`` (whose own
``make_cobol_parser`` re-export would otherwise close a circular import).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from interpreter.frontend_extension_lowering import (
    RedDragonExtensionLoweringStrategy as RedDragonExtensionLoweringStrategy,
)


@runtime_checkable
class DialectParser(Protocol):
    """One injectable parser for a coprocessor-extension statement's raw JSON.

    Symmetric with RedDragonExtensionLoweringStrategy above, but at statement-
    construction time rather than lowering time. The two extension points are
    independently pluggable — a consumer may register a DialectParser without
    any lowering strategy at all (e.g. a future AST-only analysis pass), and
    vice versa.
    """

    def applies(self, data: dict) -> bool:
        """True if this parser owns *data* (e.g. data.get("type") == "EXEC_CICS")."""
        ...

    def parse(self, data: dict) -> Any:
        """Construct and return the typed statement object for *data*. The
        returned object must implement to_dict() (matching every other
        CobolStatementType member) but RedDragon does not otherwise constrain
        its shape."""
        ...


@dataclass(frozen=True)
class NullDialectParser:
    """Null object: never claims a statement. The default so nothing needs an
    Optional/None dialect_parser anywhere in a consumer's own data model."""

    def applies(self, data: dict) -> bool:
        return False

    def parse(self, data: dict) -> Any:
        raise AssertionError(
            "NullDialectParser.parse() should never be called — applies() always returns False"
        )
