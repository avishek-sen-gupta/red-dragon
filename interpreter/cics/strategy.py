"""ExecCicsStrategy protocol and null-object implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout

logger = logging.getLogger(__name__)


class ExecCicsStrategy(Protocol):
    """Injectable strategy for lowering EXEC CICS statements to IR."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Called once at the start of the procedure division."""
        ...

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        """Lower one EXEC CICS statement to IR."""
        ...


class CatchAllLoweringStrategy:
    """Default no-op strategy. Logs a warning for every EXEC CICS statement."""

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        pass

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.warning("EXEC CICS %s ignored (no CICS strategy injected)", stmt.verb)
