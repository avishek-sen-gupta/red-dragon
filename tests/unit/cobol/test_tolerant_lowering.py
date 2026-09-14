"""Tolerant lowering is opt-in: statement lowering errors propagate by default."""

from __future__ import annotations

import pytest

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.register import NO_REGISTER
from tests.covers import NotLanguageFeature, covers


class _Boom(Exception):
    pass


def _raising_dispatch(_ctx, _stmt, _layout) -> None:
    raise _Boom("unresolvable field")


def _layout() -> MaterialisedSectionedLayout:
    empty = (DataLayout(), NO_REGISTER)
    return MaterialisedSectionedLayout(
        working_storage=empty, linkage=empty, local_storage=empty
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lowering_error_propagates_by_default():
    ctx = EmitContext(dispatch_fn=_raising_dispatch)
    with pytest.raises(_Boom, match="unresolvable field"):
        ctx.lower_statement(object(), _layout())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_tolerant_lowering_skips_failing_statement():
    ctx = EmitContext(dispatch_fn=_raising_dispatch, tolerant=True)
    ctx.lower_statement(object(), _layout())
    assert ctx.instructions == []
