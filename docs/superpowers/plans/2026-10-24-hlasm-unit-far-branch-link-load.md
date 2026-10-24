# HLASM unit .13: far branch and return; CALL, LINK, LOAD, DELETE

Bead red-dragon-6uyp.13. Spec: `2026-10-24-hlasm-system-services-design.md` decisions 3 and 5;
rulings R66, R69, R74.

## Research (IBM first, z390 second)

- **LOAD** (Assembler Services Reference, LOAD description): on success GPR 0 holds the entry
  point, bit 32 set for AMODE 31; GPR 1's high byte holds the APF code and its low three bytes
  the module length in doublewords; GPR 15 is 0. When ERRET gets control, GPR 1 holds the
  system completion code that would have been issued and GPR 15 a non-zero reason code.
- **806** (MVS System Codes): the module was not found; reason code 04 for "not found".
  We put the code in GPR 1 as the ABEND macro places a system code (bits 8-19:
  `X'00806000'`) and 4 in GPR 15. The manual does not show the GPR 1 layout; this is our reading.
- **LINK**: registers 2-14 come back as they were, R15 holds the called program's code, R0
  and R1 are what the called program left. The pages at hand do not say whether R14 is a
  work register; we restore it.
- z390 (`sz390.svc_load`): R0 entry, R1 length in doublewords, R15 0; a missing module
  gives R1 0 and R15 4 and no abend. z390's macros pass the name differently; the protocol
  between our macros and our SVC lowering is ours.

## Our SVC protocol

| SVC | In | Out |
|---|---|---|
| 6 LINK | R0 → 8-byte EBCDIC name, R1 parameter list | R15 the program's code; R2-R14 restored |
| 8 LOAD | R0 → name, R15 ERRET address or 0 | R0 entry \| X'80000000', R1 length in doublewords, R15 0; missing: ERRET with R1 X'00806000', R15 4, else abend S806 |
| 9 DELETE | R0 → name | R15 0 |

## Shapes

- **Names table** `__hlasm_names`: a start-up object keyed by the name's 8 EBCDIC bytes read as an
  integer; each entry holds `address` and `length` (the owning module's region in doublewords).
  Built at bind time from the SD and LD names (R74). No new builtin.
- **Module function** `__hlasm_module_<M>(target, below)`: declares `__hlasm_return_to` (R14
  masked to 31 bits at entry) and takes `__hlasm_below` (bit set of modules with an activation
  below it), then dispatches on `target`. Each module has a bit, `__hlasm_bit_<M>`, set at start-up.
- **Dispatch**: `hl_dispatch` returns when the masked target equals `__hlasm_return_to`;
  `hl_link_dispatch` skips that test. Both reach the statement chain, then call the job-step
  function `__hlasm_far_branch(target, below, me, linking)`. It finds the owner in the far-branch
  table: own module → S0C1; another module → return (1) when not linking and the module's bit
  is in `below`, else call `__hlasm_module_<X>(target, below | me)` and answer 0; a stub →
  `CallWithMemory __entry_<NAME>`, R15 = result, target = R14, 0; nothing → S0C1. On 0 the
  caller re-dispatches on `__hlasm_target`; on 1 it returns.
- This replaces .8's `__hlasm_stub_call` and the stub-range test in `hl_link_dispatch`: one
  far-branch path for stubs and modules. BSM/BASSM compare against `__hlasm_return_to`
  instead of the 0xFF0 sentinel, which is now only the job step's R14.
- **LINK** sets R14 to the sentinel, R15 to the entry, and calls the far branch with
  `below = me = 0` (a system boundary, as the job step); a name not in the table issues
  `CallWithMemory` on `__entry_<NAME>` built from the trimmed EBCDIC name.

## Macros (ours)

- `CALL ep|(15)|(r)[,(p,...)][,VL][,MF=L|(E,list)]`: `L 15,=V(ep)` or `LR 15,r`; inline list
  through `BRAS 1`, VL marks the last word; `BALR 14,15`. MF=L lays out the list only;
  MF=(E,list|(r)) points R1 at it and stores each parameter, then `OI` for VL.
- `LINK EP=|EPLOC=[,PARAM=(...)][,VL=1]`, `LOAD EP=|EPLOC=[,ERRET=]`, `DELETE EP=|EPLOC=`:
  name through `BRAS 0` over `CL8`, `LA 0,addr` or `LR 0,r`. Missing or both EP and EPLOC:
  MNOTE 8.

## Tests

- Unit `test_lowering_skeleton`: new labels, the return comparison against
  `__hlasm_return_to`, the far-branch call; `test_branch_and_link_lowering` mode test.
- Integration `test_far_branch.py`: CALL via V-con with VL list and RC; LOAD then `CALL (15)`
  with R0/R1 values and DELETE R15; LINK EP= PARAM VL; skip-level return (A→B→C→A);
  `B 4(,14)`; LINK/LOAD missing (stub path, refusal message, S806, ERRET R1/R15); unowned
  address S0C1; CALL MF=L/E.
- z390 `test_far_branch_differential.py`: CALL through SYSOBJ; LINK and LOAD of an asml'd module.

## Commits

1. Plan.
2. Far branch and return (module function, dispatch, far-branch function, BSM/BASSM, tests, docs).
3. LINK/LOAD/DELETE SVCs, names table, CALL/LINK/LOAD/DELETE macros, tests, z390, docs, bead.
