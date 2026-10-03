# CALL USING by address — design

Date: 2026-10-03. Issues: red-dragon-w8t3 (packing gaps), red-dragon-zerg (BY REFERENCE
writes lost on STOP RUN).

## Problem

`lower_call` (`interpreter/cobol/lower_call.py:160`) passes CALL USING arguments by
packing them into one fresh region. It copies each argument in at the caller's field
size, dispatches with `CallWithMemory`, and copies BY REFERENCE arguments back after
the return. The callee lays its whole LINKAGE section, as one `DataLayout`, over that
region (`__params_region`, `lower_data_division.py:85`).

That model has two parts. BY REFERENCE is simulated by copy-in/copy-out
(value-result), and all arguments share one packed buffer. Between them they cause
four reproduced failures (`tests/integration/test_cobol_call_using_slots.py`) plus
zerg:

| Case | Result today | Cause |
|---|---|---|
| a literal argument, then a field | the field binds to the first parameter | literals get no slot (`lower_call.py:190`) |
| OMITTED, then a field | same shift | OMITTED gets no slot (`:187`) |
| a callee parameter shorter than its argument | the next parameter lands inside the previous argument | the buffer is packed at the caller's sizes; the callee lays it out at its own |
| one field passed twice | the last copy-back wins | two copies of one storage |
| the callee ends with STOP RUN | its BY REFERENCE writes are lost (zerg) | the copy-back is caller IR after the call, and `Halt_` never returns |

No fix inside the packed buffer is complete. Placing an OMITTED or mis-sized argument
correctly needs the callee's declared sizes, which a dynamic CALL's caller cannot
know.

## Design

The caller passes **one address per argument, by position**. An address is a region
plus an offset into it. Each callee parameter is bound to the address at its position.

### Passing modes

| Mode | Address passed | Copies |
|---|---|---|
| BY REFERENCE | the argument's own region and offset | none |
| BY CONTENT | a fresh region holding a copy of the argument | one, on the way in |
| BY VALUE | as BY CONTENT | one, on the way in |
| literal (BY CONTENT or VALUE) | a fresh region holding the literal's bytes | one, on the way in |
| OMITTED | an omitted marker | none |

The copy-back is gone. BY REFERENCE writes land in the caller's storage as they
happen, which fixes the aliasing case and zerg together.

A BY REFERENCE argument's address comes from `resolve_field_ref`, the helper every
field access already uses. A subscripted, qualified or reference-modified argument
therefore passes exactly the bytes it names. Today `lower_call` resolves only the bare
name.

### Transport

`lower_call` builds the argument list with existing IR, as `NewArray` of `NewObject`.
Each element has two fields: `region` (a region address) and `offset` (an integer).
Every element also has an `omitted` field: false for a passed argument, true for
OMITTED. `CallWithMemory.params_reg`
carries that array, and the handler injects it into the callee frame as
`__call_arguments` in place of `__params_region`.

`results_reg` and `__results_region` go. The handler injects `__results_region`, but
no lowering ever reads it.

### Callee binding

Each LINKAGE 01-level gets its own binding: a region register and a base-offset
register. Field access is unchanged except for the offset. Where `resolve_field_ref`
emits `Const(fl.offset)` today, a LINKAGE field gets `base + (fl.offset -
record_start)`.

- **Parameter positions.** These come from `procedure_using`, which y2ce added. A
  program with no PROCEDURE DIVISION USING binds argument *i* to its *i*-th LINKAGE
  01 in declaration order. That is how a CICS program receives DFHCOMMAREA and a
  batch program receives PARM.
- **Binding is plain IR**, with no new builtin. For parameter *i*, the callee:
  1. `LoadVar`s `__call_arguments`;
  2. calls the existing `__list_len` builtin and `BranchIf`s on whether position *i*
     exists;
  3. if it does, `LoadIndex`es *i*, `LoadField`s the element's `omitted` flag and
     `BranchIf`s on it;
  4. if the argument is present and not omitted, `LoadField`s `region` and
     `offset`; otherwise it `AllocRegion`s a zero-filled region of the parameter's
     declared length, at offset 0.

  A reference to an omitted parameter is an error on a real system; zero-filled
  storage keeps the interpreter running, as zero-padding does today. The test happens
  at run time because a dynamic CALL's caller and callee cannot see each other's
  parameter counts.
- **LINKAGE 01s USING does not name** get the same zero-filled placeholder. They have
  no address unless something sets one, and SET ADDRESS OF is unsupported.

`MaterialisedSectionedLayout.linkage` changes from one `(DataLayout, Register)` to a
mapping from each 01 to its binding. Its single-register readers change with it:
`resolve_with_region`, the stride and OCCURS helpers, `enclosing_record_extent`,
`has_field`, `group_leaf_names`, CORRESPONDING's `_find_group_and_reg`
(`lower_arithmetic.py:897`), and INITIALIZE's fallback (`:2200`).

### Analysis extents

Recorded memory effects keep LINKAGE in static coordinates. Each 01 sits at its
offset in `laid_end_to_end(_in_using_order(...))`, exactly as now. A LINKAGE extent
therefore stays distinct per 01, so one 01 never may-aliases another. Giving every 01
a base of 0 under one `RegionId.LINKAGE` would make every 01 alias every other. The
run-time base offset applies to execution only.

Without a copy-back, the facts it recorded have to come from somewhere else. The
`CallWithMemory` instruction itself records a READ of every argument it passes and a
WRITE of every BY REFERENCE argument, the callee being free to write it. The CALL's
dataflow is therefore unchanged, minus the buffer-slot effects. Today those slots
falsely may-alias the caller's own LINKAGE fields: CALLPROBE's LK-ARG slot `0..9`
aliases LK-LEAD `0..5`.

The fresh region behind a BY CONTENT or BY VALUE copy, or a literal, gets a new
`RegionId.CALL_ARGUMENT`. That keeps its write away from every program section.

### Harnesses

cicada (`cicada/cics/vm_init.py:16`, `conversational.py:36`) and jackal
(`jackal/jackal/cobol_step.py:72`) inject `__params_region` as a single region.

- Red-dragon gains `call_arguments(vm, addresses)`, which builds `__call_arguments`
  and its heap objects for a harness frame. Both harnesses pass a single address,
  their region at offset 0. That binds to the first LINKAGE 01, which is what they
  mean today: DFHCOMMAREA or the PARM area.
- There is no `__params_region` fallback. An IR `LoadVar` of a variable the harness
  never set cannot fall back cleanly. The forge bump that takes this change also moves
  cicada and jackal to `call_arguments`, in the same commit, because the bump alone
  would break both harnesses.

cobble is not affected. It reads none of red-dragon's recorded effects and lays out
LINKAGE itself, per 01.

## Behaviour changes for review

1. **A callee parameter wider than its argument reads the caller's next bytes**, as on
   a real system, not zeros.
   `test_callee_linkage_wider_than_caller_arg_reads_zero_pad`
   (`tests/integration/test_cobol_programs.py:6177` class) pins zeros. That assertion
   would change.
2. **A CALL with no USING binds no LINKAGE.** The callee's LINKAGE 01s get zero-filled
   placeholders. Today the callee's LINKAGE is laid over the caller's
   WORKING-STORAGE (`lower_call.py:228`), which no COBOL runtime does.
3. **The zerg xfail flips**:
   `test_stop_run_loses_by_reference_write_known_gap` (`test_cobol_programs.py:6733`).
4. **Unit tests that pin the current IR shape are rewritten**: ALLOC_REGION/copy-in,
   copy-back, `params_reg == results_reg`, and the two-effects-per-direction
   recording. The files are `tests/unit/test_lower_call_with_memory.py`,
   `test_call_with_memory.py`, `test_handle_call_with_memory_singleton.py`,
   `test_lower_sectioned_data_division.py`, and
   `cobol/test_recorded_memory_effects.py`.

## Out of scope

- **SET ADDRESS OF and POINTER.** Unsupported today, and they stay unsupported. The
  per-01 binding is what they would hook into.
- **A write past the end of a region** grows the bytearray (`vm/vm.py:226`) instead of
  failing. This is unchanged and unrelated to argument passing, and should be filed
  separately.
- **A numeric literal passed BY CONTENT** is passed as its display text. An exact
  IBM-style representation (one that follows the literal's own type) is a follow-up.
- **cicada's LINK builtin** writes a LINKAGE-relative offset into WORKING-STORAGE
  when its COMMAREA is a LINKAGE item (`cicada/cics/strategy.py:629`,
  `builtins/vsam.py:37`). It is a separate cicada bug; this design does not change
  that path.

## Order of work

1. **Red-dragon.** Argument array, IR binding, call-site effects,
   `RegionId.CALL_ARGUMENT`, and `call_arguments(vm, addresses)`. The four slot tests
   pass and the zerg xfail flips. Shape tests are rewritten, and items 1–2 above
   follow your review.
2. **Forge.** Bump red-dragon, and move cicada and jackal to `call_arguments` in the
   same commit. Their COMMAREA and PARM tests, and every other suite, run by hand
   first, since the hooks skip suites on a pure bump.
