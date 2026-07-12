# pyright: standard
"""RedDragonExtensionLoweringStrategy — the injectable extension-lowering seam.

Split out of interpreter.frontend_extension so this module (the only one that
references interpreter.cobol.emit_context / sectioned_layout) is separate from
the parse-time DialectParser seam, which is VM/lowering-free and copyable by
static-analysis consumers. frontend_extension re-exports this name for
backward compatibility.
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
        """True if this strategy owns ``stmt`` (e.g. isinstance(stmt, YourDialectStatement))."""
        ...

    def preprocess_program_dict(self, data: dict) -> dict:
        """Transform the raw bridge JSON dict before generic COBOL parsing.
        Return ``data`` unchanged for a no-op."""
        ...

    def on_procedure_entry(
        self, ctx: EmitContext, materialised: MaterialisedSectionedLayout
    ) -> None:
        """Called once at the start of the procedure division."""
        ...

    def lower(
        self, ctx: EmitContext, stmt: Any, materialised: MaterialisedSectionedLayout
    ) -> None:
        """Lower one extension statement to IR."""
        ...
