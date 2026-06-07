# CICS — Top-Level Bootstrap + Real End-to-End Execution — Design Spec

**Date:** 2026-06-07
**Beads story:** `red-dragon-pz9g.9` (P1)
**Depends on:** F (`pz9g.7`), D (`pz9g.4`), E (`pz9g.5`)
**Fitness function:** the epic's actual goal — start at the entry transid and drive a
multi-turn online flow through **compiled-and-executed COBOL** (not stubbed `run_fn`),
asserting on screen output and carried state.

---

## Problem

Two missing pieces leave the epic's fitness function unproven:

1. **No bootstrap.** Nothing wires the startup sequence the spec (Sub-project C) describes:
   parse CSD → eagerly compile every program with `CicsLoweringStrategy` → build
   `program_cache` → construct the strategy with the VSAM engine + BMS map model + screen/
   input queues → run the dispatcher loop at the entry transid. The pieces exist
   (`parse_csd`, `run_cics`, `_run_dispatcher_with_runner`, the strategy) but are unassembled.
2. **No real execution test.** `tests/integration/cics/test_sign_on_flow.py` (pz9g.6) stubs
   `run_fn` entirely — it exercises the dispatcher loop and screen builtins but never compiles
   or runs real COBOL through the VM. The path COBOL → pre-pass → ProLeap → CICS lowering →
   VM → builtins → screen/COMMAREA has never run end-to-end.

---

## Design

### Bootstrap entrypoint

New module `interpreter/cics/bootstrap.py` exposing a single function that assembles and runs
a CICS region:

```
run_carddemo_region(
    csd_path, program_sources, fct_config, bms_maps_dir,
    entry_transid, input_queue, screen_queue,
) -> DispatchResult
```

Steps (mirrors spec C "Startup sequence"):
1. `parse_csd(csd_path)` → `transid_to_program: dict[str,str]`.
2. Construct shared runtime state: VSAM engine (from FCT), BMS loader (from maps dir),
   `context_holder`, `result_holder`, screen/input queues.
3. Construct **one** `CicsLoweringStrategy` over that shared state (registers all builtins
   into `Builtins.TABLE`).
4. Eagerly compile every distinct program named in the CSD: pre-pass → ProLeap → frontend
   `.lower()` with the strategy injected → link → `LinkedProgram`. Build
   `program_cache: dict[str, LinkedProgram]`. **Fail fast** on missing source or compile error.
5. Bind a real `run_fn` = `run_cics` (closing over the queues and holders).
6. `_run_dispatcher_with_runner(run_fn, program_cache, transid_to_program,
   CicsContext(entry_transid, b"", DFHENTER), screen_queue, input_queue)`.

The function is UI-agnostic: a test driver, TUI, or web frontend all interact only through
the two queues.

### Global `Builtins.TABLE` caveat

The strategy registers builtins into the process-global `Builtins.TABLE` (with the existing
overwrite warning). The bootstrap constructs exactly one strategy per region, so within a run
this is consistent. Tests that build multiple regions in one process must tolerate the
overwrite warning (or a future refactor moves the table into per-run state — out of scope here).

---

## Testing (TDD)

**Integration, JAR-gated** (`pytest.mark.skipif(not JAR_AVAILABLE, ...)`, like
`test_parse_strategy.py`):

- **Minimal real two-turn flow.** Two tiny COBOL programs (inline source) connected by a
  CSD: program 1 does `SEND MAP`, `RECEIVE MAP`, `RETURN TRANSID` carrying a COMMAREA;
  program 2 reads `DFHCOMMAREA`, `SEND MAP` reflecting the carried value, `RETURN`. Drive via
  scripted `input_queue`; assert the screen queue shows both maps and the second screen
  reflects data carried in the COMMAREA (proves F + dispatcher + BMS together).
- **Bootstrap fail-fast.** Missing program source → bootstrap raises before the loop starts.

**Unit:**
- `run_carddemo_region` parses the CSD and populates `program_cache` keyed by program name.

The non-JAR stub flow test from pz9g.6 stays (fast smoke of the loop); this story adds the
real-execution proof on top.

---

## Risks / open questions

- **ProLeap availability in CI.** Real-execution tests are JAR-gated and skip when the bridge
  JAR is absent — acceptable, matches existing CICS integration tests. Note the skip in
  output so it is never mistaken for coverage.
- **Compile cost.** Eager compilation of many programs is slow; for tests, compile only the
  two programs the CSD names. A real CardDemo region would compile all 17 — acceptable at
  startup, but log progress so a hang is diagnosable.
- **Depends on D and E being functionally complete** (not just plumbed), which in turn depend
  on F. This is the last story in the chain by design.
