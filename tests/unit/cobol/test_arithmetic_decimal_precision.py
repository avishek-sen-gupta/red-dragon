"""Decimal precision in COBOL arithmetic.

38.30 cannot be represented exactly in binary float; successive additions
accumulate a sub-cent error that is visible when the result is stored in a
PIC 9(n)V99 field and the field is read back.

Real-world consequence: a multi-operand COMPUTE involving fields valued at
38.30 produces a result 1 cent short of the correct value, causing a
subsequent exact-equality balance check to fire incorrectly.
"""

from __future__ import annotations

from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked
from tests.covers import NotLanguageFeature, covers

# Two fields each holding 38.30 (PIC 9(5)V99); COMPUTE adds them into a
# PIC 9(5)V99 result field.  Expected: 0007660 → $76.60.
_ADD_TWO_FEES = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ADDTWO.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-FEE-A     PIC 9(5)V99 VALUE 38.30.
       01  WS-FEE-B     PIC 9(5)V99 VALUE 38.30.
       01  WS-RESULT    PIC 9(5)V99 VALUE ZEROES.
       PROCEDURE DIVISION.
           COMPUTE WS-RESULT = WS-FEE-A + WS-FEE-B.
           GOBACK.
"""

# Five-operand COMPUTE: selling-price + two fees of 38.30 + one fee of 500
# minus a loan amount.
# selling=$480,000  fee-a=$38.30  fee-b=$38.30  fee-c=$500  loan=$300,000
# expected result = $180,576.60
_MULTI_OPERAND_COMPUTE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MULTIOP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PRICE      PIC 9(8)     VALUE 480000.
       01  WS-FEE-A      PIC 9(5)V99  VALUE 38.30.
       01  WS-FEE-B      PIC 9(5)V99  VALUE 38.30.
       01  WS-FEE-C      PIC 9(5)V99  VALUE 500.
       01  WS-LOAN       PIC 9(8)     VALUE 300000.
       01  WS-BALANCE    PIC 9(9)V99  VALUE ZEROES.
       PROCEDURE DIVISION.
           COMPUTE WS-BALANCE = WS-PRICE
                               + WS-FEE-A
                               + WS-FEE-B
                               + WS-FEE-C
                               - WS-LOAN.
           GOBACK.
"""


def _ws_zoned(vm, name: str) -> int:
    """Return a WS zoned-decimal field's raw digit string as an integer."""
    layout = vm.data_layout
    if layout is None:
        raise ValueError("no data_layout on vm")
    field = layout.get(name)
    if field is None:
        raise KeyError(name)
    off, sz = field["offset"], field["length"]
    for rk in vm.region_keys():
        rgn = bytes(vm.region_get(rk))
        if len(rgn) >= off + sz:
            return int("".join(str(b & 0x0F) for b in rgn[off : off + sz]))
    raise RuntimeError(f"region not found for {name}")


def _compile_and_run(source: bytes):
    parser = make_cobol_parser()
    _, linked = compile_cobol(source, parser=parser)
    # Entry point: the PROCEDURE DIVISION is lowered as func_<progid>_0.
    # entry_func_label is None for single-module programs; fall back to the
    # same func_* predicate that cicada's make_entry_point uses.
    entry_label = getattr(linked, "entry_func_label", None)
    if entry_label is not None:
        ep = EntryPoint.function(lambda ref, _l=str(entry_label): str(ref.label) == _l)
    else:
        ep = EntryPoint.function(
            lambda ref: str(ref.label).startswith("func_")
            and not str(ref.label).startswith("func_init_params_")
        )
    vm = run_linked(
        linked,
        entry_point=ep,
        max_steps=500_000,
        initial_vm=initial_vm_state(),
    )
    return vm, linked


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_add_two_38_30_fields_exact():
    """38.30 + 38.30 stored in PIC 9(5)V99 must equal exactly 76.60 (digits 0007660)."""
    vm, _ = _compile_and_run(_ADD_TWO_FEES)
    result = _ws_zoned(vm, "WS-RESULT")
    # 76.60 stored as 9(5)V99: 7 digits → 0007660
    assert result == 7660, (
        f"Expected 7660 ($76.60) but got {result} — "
        f"float accumulation error: 38.30+38.30 encoded as {result / 100:.2f}"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multi_operand_compute_exact():
    """price+fee-a+fee-b+fee-c-loan must equal exactly $180,576.60 (digits 18057660)."""
    vm, _ = _compile_and_run(_MULTI_OPERAND_COMPUTE)
    result = _ws_zoned(vm, "WS-BALANCE")
    # $180,576.60 as PIC 9(9)V99 (11 digits): 18057660
    assert result == 18057660, (
        f"Expected 18057660 ($180,576.60) but got {result} — "
        f"float accumulation error in multi-operand COMPUTE"
    )
