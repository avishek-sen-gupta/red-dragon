"""FUNCTION WHEN-COMPILED: the compile clock's stamp, read once per program when it
is lowered and rendered in the function's 21-character form; the ASG carries none."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cobol_asg.asg_types import CobolASG
from interpreter.cobol.compile_clock import CompileClock
from interpreter.cobol.compile_options import CompileOptions
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.cobol.when_compiled import when_compiled_text
from tests.covers import covers


@dataclass(frozen=True)
class _FixedClock(CompileClock):
    at: datetime

    def now(self) -> datetime:
        return self.at


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_compile_stamp_comes_from_the_compile_clock_and_renders_in_21_characters():
    """IBM Enterprise COBOL LR, WHEN-COMPILED: YYYYMMDDHHMMSShh, then the sign
    and hours and minutes of the offset from Greenwich mean time."""
    behind = datetime(
        2026, 10, 17, 16, 5, 9, 346000, tzinfo=timezone(-timedelta(hours=4, minutes=30))
    )
    ahead = datetime(2026, 1, 2, 3, 4, 5, 60000, tzinfo=timezone(timedelta(hours=1)))
    ctx = EmitContext(
        dispatch_fn=dispatch_statement,
        options=CompileOptions(clock=_FixedClock(behind)),
    )
    assert (
        ctx.compiled_at,
        when_compiled_text(ctx.compiled_at),
        when_compiled_text(ahead),
        CobolASG.from_dict({"compiled_at": "2026-10-17T16:05:09.346-04:30"}).to_dict(),
    ) == (behind, "2026101716050934-0430", "2026010203040506+0100", {})
