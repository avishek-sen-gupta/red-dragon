"""FUNCTION WHEN-COMPILED: the bridge's compile stamp, read into the ASG and
rendered in the function's 21-character form."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cobol_asg.asg_types import CobolASG
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.when_compiled import when_compiled_text
from tests.covers import covers


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_compile_stamp_reads_into_the_asg_and_renders_in_21_characters():
    """IBM Enterprise COBOL LR, WHEN-COMPILED: YYYYMMDDHHMMSShh, then the sign
    and hours and minutes of the offset from Greenwich mean time."""
    behind = CobolASG.from_dict({"compiled_at": "2026-10-17T16:05:09.346-04:30"})
    ahead = datetime(2026, 1, 2, 3, 4, 5, 60000, tzinfo=timezone(timedelta(hours=1)))
    assert (
        behind.compiled_at,
        when_compiled_text(behind.compiled_at),
        when_compiled_text(ahead),
        CobolASG.from_dict(behind.to_dict()).compiled_at,
    ) == (
        datetime(
            2026,
            10,
            17,
            16,
            5,
            9,
            346000,
            tzinfo=timezone(-timedelta(hours=4, minutes=30)),
        ),
        "2026101716050934-0430",
        "2026010203040506+0100",
        behind.compiled_at,
    )
