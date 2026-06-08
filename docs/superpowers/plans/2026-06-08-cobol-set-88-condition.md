# COBOL `SET <88-condition-name> TO TRUE` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or
> superpowers:executing-plans. TDD throughout: failing test first, then implement.

**Beads:** `red-dragon-0cci` (P1)
**Goal:** `SET <88-level condition-name> TO TRUE` (and `TO FALSE`) writes the condition's
VALUE into its parent elementary item, so a subsequent test of that 88 evaluates correctly.
**Scope:** COBOL frontend only (`lower_arithmetic.py` / `statement_dispatch.py`); no core engine.

## Problem

`SET CDEMO-PGM-REENTER TO TRUE` is a no-op today. `lower_set` (`interpreter/cobol/lower_arithmetic.py`)
does `if not ctx.has_field(target_name, materialised): logger.warning("SET target %s not found
in layout"); continue`. An 88-level condition name is **not** a field in the layout (it lives in
the `ConditionNameIndex`), so the target is skipped and nothing is written.

Consequence (confirmed on the real `COMEN01C` menu): the program gates input-processing on
`IF NOT CDEMO-PGM-REENTER` and flips it with `SET CDEMO-PGM-REENTER TO TRUE`. With the SET a
no-op, the reenter flag never gets set, so the menu re-displays forever and never processes a
selected option. (Spike: turn-1 returned commarea is all-zeros; turn-2 re-renders the menu.)

## How 88-condition names are modelled (reuse — don't reinvent)

- `interpreter/cobol/condition_name_index.py`: `ConditionNameIndex.has_condition(name) -> bool`,
  `.lookup(name) -> ConditionEntry(parent_field_name: str, values: list[ConditionValue])`.
  `ConditionValue` carries the discrete value / THRU range (see `_emit_single_value_test` and
  `_expand_condition_name` in `condition_lowering.py` for how the parent field + values are used
  to lower a *read* of an 88 — the SET is the inverse: write the value into the parent).
- The index is already built (`build_condition_index(layout)`) and threaded into condition
  lowering. `lower_set` does **not** currently receive it.

## Tasks

### Task 1: Confirm the `SET ... TO TRUE/FALSE` representation
- [ ] Inspect how the bridge/ASG serializes `SET X TO TRUE` into `SetStatement` (`set_type`,
  `values`, `targets`). Determine the token used for TRUE/FALSE (likely `values[0] == "TRUE"`).
  Add a tiny JAR-gated parse/lower assertion if helpful. Record the exact representation.

### Task 2: Failing test (red)
- [ ] JAR-gated integration test (mirror `tests/integration/test_cobol_programs.py::_run_cobol`):
```cobol
       01 WS-FLG PIC X VALUE 'N'.
          88 FLG-ON  VALUE 'Y'.
          88 FLG-OFF VALUE 'N'.
       01 WS-R PIC 9 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           SET FLG-ON TO TRUE.
           IF FLG-ON MOVE 1 TO WS-R ELSE MOVE 2 TO WS-R END-IF.
           STOP RUN.
```
  Assert `WS-R == 1`. Confirm it FAILS today (no-op leaves WS-FLG='N' → FLG-ON false → WS-R=2).

### Task 3: Implement `SET <88> TO TRUE/FALSE` in `lower_set`
- [ ] Thread the `ConditionNameIndex` into `lower_set` (pass it from `statement_dispatch.py`
  the same way condition lowering receives it; or expose it via `ctx`). Confirm where the index
  is held at dispatch time and route it in.
- [ ] In the `set_type == "TO"` branch, BEFORE the `has_field` skip, handle a condition-name target:
  ```python
  if condition_index.has_condition(target_name):
      entry = condition_index.lookup(target_name)
      truth = str(value_str).strip().upper()
      if truth == "TRUE":
          cv = entry.values[0]              # first discrete value / range low
          lit = cv.from_val                  # the VALUE literal to write
      elif truth == "FALSE":
          # SET cond TO FALSE requires a `88 ... FALSE IS <lit>` clause; if the
          # index captured a false-value use it, else warn (do NOT no-op to TRUE).
          ...
      # write lit into the PARENT elementary field (like MOVE lit TO parent):
      pref, prr = ctx.resolve_field_ref(entry.parent_field_name, materialised)
      value_str_reg = ctx.const_to_reg(_quote_if_needed(lit))
      ctx.emit_encode_and_write(prr, pref.fl, value_str_reg, pref.offset_reg)
      continue
  ```
  Match the existing `lower_set` quoting/const conventions (`const_to_reg`, `emit_encode_and_write`).
  Handle multiple targets (`SET A B TO TRUE`) by looping (the existing `for target_name` loop).
- [ ] Keep the existing field-target `SET ... TO` and `SET ... UP/DOWN BY` paths unchanged. A
  genuinely unknown target (neither field nor condition-name) still warns (no silent success).

### Task 4: Verify
- [ ] New test passes; `SET FLG-ON TO TRUE` then `IF FLG-ON` is true; `SET FLG-OFF TO TRUE`
  then `IF FLG-ON` is false; multi-target `SET A B TO TRUE`.
- [ ] `poetry run python -m pytest tests/unit/cics/ tests/integration/cics/ tests/integration/test_cobol_programs.py -q` green.
- [ ] Full suite green; `lint-imports` clean; `black`.

### Task 5: Commit + re-spike the motivating case
- [ ] Commit (`fix(cobol): SET <88-condition-name> TO TRUE writes parent VALUE (red-dragon-0cci)`).
- [ ] Re-spike the real `COMEN01C` menu-action turn: with the reenter flag now settable, the
  second turn should reach `PROCESS-ENTER-KEY`. Expect the NEXT layer of gaps to surface there
  (class condition `IS NUMERIC` — separate issue; `PERFORM VARYING FROM LENGTH OF + ref-mod
  subscript in UNTIL` — separate issue). File/triage whatever appears.

## Risks / notes
- `SET ... TO FALSE` is uncommon and only well-defined with a `FALSE IS` clause; if the
  `ConditionNameIndex`/`ConditionValue` doesn't capture a false-value, warn rather than guess.
- No JAR rebuild needed (pure Python frontend change); the bridge already emits `SetStatement`.
- This unblocks the menu-action turn but is NOT sufficient alone — the class-condition and
  PERFORM-VARYING gaps behind it must also land for a menu option to reach its `XCTL`.
