"""RedDragonExtensionLoweringStrategy — the injectable seam for lowering embedded
coprocessor-extension statements (EXEC CICS, EXEC SQL, EXEC DLI) to IR.

The frontend holds an *array* of these. Each extension's full implementation lives
in its own runtime package (cicada for CICS, squall for SQL) and is injected at
CobolFrontend construction. The protocol is dialect-agnostic — it carries no
CICS/SQL semantics. An empty array means no extension processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout


@runtime_checkable
class RedDragonExtensionLoweringStrategy(Protocol):
    """One injectable extension-lowering strategy (CICS, SQL, …)."""

    def handles(self, stmt: Any) -> bool:
        """True if this strategy owns ``stmt`` (e.g. isinstance(stmt, ExecSqlStatement))."""
        ...

    def preprocess_program_dict(self, data: dict) -> dict:
        """Transform the raw bridge JSON dict before generic COBOL parsing.
        Return ``data`` unchanged for a no-op."""
        ...

    def on_procedure_entry(
        self, ctx: "EmitContext", materialised: "MaterialisedSectionedLayout"
    ) -> None:
        """Called once at the start of the procedure division."""
        ...

    def lower(
        self, ctx: "EmitContext", stmt: Any, materialised: "MaterialisedSectionedLayout"
    ) -> None:
        """Lower one extension statement to IR."""
        ...
