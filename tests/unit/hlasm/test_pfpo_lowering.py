# pyright: standard
"""PFPO lowering: GR0's word is read and checked in IR, every source format has its decoding and every target its encoding behind the format dispatch, one builtin converts, and GR1 takes the return code; no SYMBOLIC."""

from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import SPECIFICATION, lowered_ir, trace

PFPO_TRACE = trace("PFPO", ())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pfpo_decodes_every_source_and_encodes_every_target_around_one_call():
    assert (
        PFPO_TRACE[0],
        PFPO_TRACE.count("call pfpo"),
        PFPO_TRACE.count(SPECIFICATION),
        sorted({entry for entry in PFPO_TRACE if entry.startswith("call dfp")}),
        sorted({entry for entry in PFPO_TRACE if "fpr" in entry}),
        PFPO_TRACE.count("write gpr 12+4"),
        [i for i in lowered_ir("PFPO", ()) if isinstance(i, Symbolic)],
    ) == (
        "read gpr 4+4",
        1,
        1,
        [
            "call dfp decode_extended",
            "call dfp decode_long",
            "call dfp decode_short",
            "call dfp encode_extended",
            "call dfp encode_long",
            "call dfp encode_short",
        ],
        [
            "read fpr 32+4",
            "read fpr 32+8",
            "read fpr 48+8",
            "write fpr 0+4",
            "write fpr 0+8",
            "write fpr 16+8",
        ],
        2,
        [],
    )
