# pyright: standard
"""PFPO's operand-format codes (PoO figure 9-25) as floating-point register layouts, and the name of its one builtin."""

from collections.abc import Mapping

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, SHORT_DFP, DfpLayout
from interpreter.hlasm.hfp_layout import EXTENDED_HFP, LONG_HFP, SHORT_HFP, HfpLayout

type PfpoLayout = BfpLayout | HfpLayout | DfpLayout

PFPO_BUILTIN = FuncName("__hlasm_pfpo")

LAYOUTS: Mapping[int, PfpoLayout] = {
    0x00: SHORT_HFP,
    0x01: LONG_HFP,
    0x02: EXTENDED_HFP,
    0x05: SHORT_LAYOUT,
    0x06: LONG_LAYOUT,
    0x07: EXTENDED_LAYOUT,
    0x08: SHORT_DFP,
    0x09: LONG_DFP,
    0x0A: EXTENDED_DFP,
}
