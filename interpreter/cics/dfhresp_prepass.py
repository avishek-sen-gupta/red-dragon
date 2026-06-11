# pyright: standard
"""CICS DFHRESP expression node pre-pass.

Recursively replaces ``{"kind":"dfhresp","condition":"X"}`` nodes in the raw
bridge JSON with ``{"kind":"lit","value":"N"}`` before the generic COBOL
expression tree ever sees them.  Called by :class:`CicsLoweringStrategy` as
part of :meth:`preprocess_program_dict` (red-dragon-kieo).
"""

from __future__ import annotations

import logging

from interpreter.cics.preprocessor import _DFHRESP_TABLE, _DFHRESP_UNKNOWN

logger = logging.getLogger(__name__)


def resolve_dfhresp_nodes(data: object) -> object:
    """Return *data* with every dfhresp expression node replaced by a lit node."""
    if isinstance(data, dict):
        if data.get("kind") == "dfhresp":
            cond = str(data.get("condition", "")).upper()
            code = _DFHRESP_TABLE.get(cond)
            if code is None:
                logger.warning(
                    "Unknown DFHRESP condition %r — using sentinel %d",
                    cond,
                    _DFHRESP_UNKNOWN,
                )
                code = _DFHRESP_UNKNOWN
            return {"kind": "lit", "value": str(code)}
        return {k: resolve_dfhresp_nodes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_dfhresp_nodes(item) for item in data]
    return data
