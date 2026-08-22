# PIC P Decimal Scaling — Resume Notes

**Issue:** red-dragon-qhtv
**Plan:** `docs/superpowers/plans/2026-08-22-pic-p-decimal-scaling.md`
**Spec:** `docs/superpowers/specs/2026-08-22-pic-p-decimal-scaling-design.md`
**Stopped:** 2026-08-22, mid Task 3 fix round, at the user's instruction (the
pre-commit full-suite hook was monopolising the machine).

## State

Merged to `main`. Commits, oldest first:

| Commit | What | Verified? |
|--------|------|-----------|
| `e8cda012` | Task 1 — `scale` field on `CobolTypeDescriptor`, populated by the Lark transformer | YES — full suite green, task review clean |
| `aad7986c` | Task 2 — encode divides by `10**scale` (`pic_scale.py`, `emit_encode_numeric`) | YES — full suite green |
| `e2123cbe` | Task 2 fix — `format(x,"f")` instead of `str(Decimal)`, closing scientific-notation corruption | YES — re-review verdict ADDRESSED |
| `68580223` | Task 3 — decode multiplies; runtime `COBOL_PREPARE_DIGITS` encode path also scaled | YES — 14928 passed; task review PASS/PASS |
| `a63b86d6` | Task 3 fix round 1 — negative-scale coverage + `decimal.InvalidOperation` guard | **NO — committed `--no-verify`, suite run killed before finishing, never re-reviewed** |

## What is DONE

- Tasks 1, 2, 3 of the plan, including their reviews.
- `PIC 999PP` + `MOVE 12300` now stores `123` (was `300`) on BOTH encode paths.
- `parse_pic("999PP")` and `parse_pic("PP999")` are no longer identical descriptors.

## What is NOT done

1. **Verify `a63b86d6`.** Run the full suite. It was never confirmed green.
2. **Re-review `a63b86d6`.** It was a fix round; the scoped re-review never ran.
   Open findings it was meant to address are Important 1 (negative-scale
   coverage) and Important 2 (Decimal guard) — see the ledger.
3. **Task 4 — edited pictures.** `interpreter/cobol/edit_picture.py` does not
   apply P scaling. `parse_edit_picture("ZZZPP").scale` and
   `format_edited("900","ZZZPP") == "  9"` are both unimplemented. Brief is at
   `.superpowers/sdd/2026-08-22-pic-p-decimal-scaling/task-4-brief.md`.
4. **Task 5 — docs + parity.** `edit_picture.py`'s module docstring still says
   P scaling is unsupported. The Python/Java width parity sweep has not been
   re-run since Task 1.

## Findings that outlived the run — read these before resuming

**The spec is wrong about encode.** It names ONE encode path. There are two:
`emit_encode_numeric` (compile-time literals / VALUE clauses) and
`emit_numeric_encode_from_string` → the `COBOL_PREPARE_DIGITS` builtin (runtime
`MOVE`). The issue's headline case travels the SECOND path, so Task 2 alone did
not fix the reported bug. Task 3 was widened by ruling to cover it. **The spec's
Components section should be corrected.**

**The plan's own acceptance test was wrong.** Task 3's
`test_scaled_value_reads_back_at_full_magnitude` asserted on `WS-SRC`'s bytes at
offset 0, not `WS-OUT`'s — `P` occupies no storage, so `WS-SRC PIC 999PP` is
3 bytes and `WS-OUT` starts at offset 3. The test never exercised decode at all.
The implementer caught it and swapped the `PIC ZZZPP` receiver for `PIC 9(5)`;
review adjudicated that a strengthening, confirmed by perturbation.

**Deferred minors** (full text in the ledger):
- New unit tests in `tests/unit/test_byte_builtins.py:841,855` lack `@covers`.
- The two encode paths truncate differently for unscaled input: `byte_builtins`
  uses `clean.split(".")[0]`, `pic_scale` uses `clean.replace(".","")`. `"12.5"`
  into a 3-digit field gives `125` vs `12`. Pre-existing, unreachable on the
  scaled path — but worth its own issue, given this task's whole premise was
  those two paths silently diverging.
- Positive scale is decoded through `float`, lossy above 2^53. Plan-mandated.
- `pic_parser.py`'s "P on both sides raises" branch has no test.
- The end-to-end `999PP → ZZZPP` integration MOVE removed in Task 3 has no
  scheduled home; Task 4 covers `format_edited` at unit level only.

## Resuming

The SDD ledger is at
`.superpowers/sdd/2026-08-22-pic-p-decimal-scaling/progress.md` (git-ignored, so
it is on this machine only). Briefs for Tasks 4 and 5 are beside it. Resume by
verifying `a63b86d6` first, then Task 4.

**Operational note for whoever resumes:** every commit triggers a pre-commit
hook that runs the full suite (~3 minutes). Five tasks of commit-per-task plus
verification runs saturated the machine. Batch the commits, or run the suite
once at the end rather than per task.
