"""ExecCicsStrategy protocol and null-object default implementation.

These live in the COBOL layer so the frontend has a typed seam for CICS
injection without depending on the interpreter.cics package. The full
implementation (CicsLoweringStrategy) lives in the CICS runtime and is
injected at CobolFrontend construction time.

NOTE: As of the extension_strategies array migration, RedDragon's own frontend no
longer uses this module. It is retained only for cicada's backward-compatible
re-export and will be removed once cicada migrates to RedDragonExtensionLoweringStrategy.
"""

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

    def preprocess_program_dict(self, data: dict) -> dict:  # type: ignore[return]
        """Pre-process the raw bridge JSON dict before generic COBOL parsing.

        Default no-op. Override to transform CICS-specific expression nodes
        (e.g. DFHRESP) into generic ones before ``CobolASG.from_dict`` runs.
        """
        return data

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

    def preprocess_program_dict(self, data: dict) -> dict:
        return data

    def on_procedure_entry(
        self,
        ctx: "EmitContext",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.debug("on_procedure_entry: no-op (CatchAllLoweringStrategy)")

    def lower(
        self,
        ctx: "EmitContext",
        stmt: "ExecCicsStatement",
        materialised: "MaterialisedSectionedLayout",
    ) -> None:
        logger.warning("EXEC CICS %s ignored (no CICS strategy injected)", stmt.verb)
