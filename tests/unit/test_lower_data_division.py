"""Unit tests for lower_data_division — TDD anchor for str → Register migration."""

from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_data_division import lower_data_division
from cobol_memory.region_id import RegionId
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_data_division_returns_register():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    layout = DataLayout()
    result = lower_data_division(ctx, layout, RegionId.WORKING_STORAGE)
    assert isinstance(result, Register), f"Expected Register, got {type(result)}"
