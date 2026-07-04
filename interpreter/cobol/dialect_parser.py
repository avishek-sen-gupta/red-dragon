# pyright: standard
"""DialectParser — the injectable seam for CONSTRUCTING coprocessor-extension
statements (EXEC CICS, EXEC SQL, EXEC DLI) from raw ProLeap bridge JSON.

Symmetric with RedDragonExtensionLoweringStrategy (interpreter/cobol/
red_dragon_extension_strategy.py), but at statement-construction time rather
than lowering time. The two extension points are independently pluggable — a
consumer may register a DialectParser without any lowering strategy at all
(e.g. a future AST-only analysis pass), and vice versa. The frontend holds an
array of these; an empty array means every statement type must already be
recognized by RedDragon's own core dispatch table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DialectParser(Protocol):
    """One injectable parser for a coprocessor-extension statement's raw JSON."""

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
