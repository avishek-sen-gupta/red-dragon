# Coprocessor Spec-Building Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `build_cics_spec`/`build_sql_spec` out of red-dragon-forge and into Cicada/Squall themselves, and have every caller (including forge) use them — eliminating the spec-building duplication between forge's adapters and each coprocessor's own callers.

**Architecture:** Cicada gains `cics/coprocessor.py` (moved verbatim from forge's `adapters/cics.py`); `compile_cics_program` changes to take a pre-built `spec: CoprocessorSpec` instead of a raw `strategy: Any`, and since the spec now owns prepassing, every real caller of `compile_cics_program` and `run_carddemo_region` stops pre-passing by hand. Squall gains `squall/coprocessor.py` similarly; its test helper calls it directly instead of reimplementing the holder-cell pattern. Forge deletes `adapters/` entirely and imports straight from `cics.coprocessor`/`squall.coprocessor`.

**Tech Stack:** Python 3.13, pytest, ProLeap bridge (JAR-gated integration tests), uv/poetry across 3 repos (cicada, squall, red-dragon-forge) linked via git submodules to RedDragon (untouched by this plan).

## Global Constraints

- `build_cics_spec`'s and `build_sql_spec`'s own field logic does not change — this is a pure move plus the prepass-ownership consequence.
- `CoprocessorSpec`/`compile_program` (RedDragon, `interpreter/project/coprocessor_compile.py`) are not touched by this plan.
- `compile_cics_program`'s and `run_carddemo_region`'s *contracts* change deliberately: `compile_cics_program` takes `spec: CoprocessorSpec` instead of `strategy: Any`; `run_carddemo_region`'s `program_sources` values must be raw (NOT pre-passed) COBOL bytes. Every real caller of both functions is updated in the same change — no caller is left on the old contract.
- Cicada's full suite (348 tests) and Squall's full suite (271 passed, 1 skipped) must both still pass, unchanged counts — this is a structural move, not a behavior change, for every correctly-updated caller.
- red-dragon-forge's full suite (7 tests, unchanged count) must still pass, including the live-Db2 INQCUST e2e and the CEEDAYS LE-stub proof test.
- Db2 container flakiness is a known, benign, recurring issue: `docker exec squall-db2 su - db2inst1 -c 'db2start'` (occasionally preceded by `db2stop force`) is the documented, non-destructive recovery; never treat it as a real regression.
- Follow each repo's established cross-repo pin-bump discipline: after cicada and squall land and push their commits, bump red-dragon-forge's `vendor/cicada`/`vendor/squall` pins before running its suite.

---

### Task 1: Cicada — move build_cics_spec in, rewire compile_cics_program + every real caller

**Files:**
- Create: `cics/coprocessor.py`
- Modify: `cics/bootstrap.py`
- Modify: `cics/flow_map.py`
- Modify: `tests/integration/cics/test_link.py`
- Modify: `tests/integration/cics/test_carddemo_add_transaction.py`
- Modify: `tests/integration/cics/test_carddemo_reports.py`
- Modify: `tests/integration/cics/test_carddemo_signon_real.py` (3 call sites)
- Modify: `tests/integration/cics/test_region_e2e.py` (4 `program_sources` sites)
- Modify: `tests/integration/cics/test_region_subprogram_link.py` (1 `program_sources` site)

**Interfaces:**
- Produces: `cics.coprocessor.build_cics_spec(context_holder, result_holder=None, program_cache=None, vsam_engine=None, screen_queue=None, input_queue=None, **kwargs) -> CoprocessorSpec`; `compile_cics_program(source: bytes, parser: Any, spec: CoprocessorSpec, *, program_source_dirs: Sequence[Path] = ()) -> Any` (signature changed from `strategy: Any` to `spec: CoprocessorSpec`); `run_carddemo_region(...)`'s `program_sources` now means raw (un-pre-passed) bytes.
- Consumes: `interpreter.project.coprocessor_compile.{CoprocessorSpec, compile_program}` (already available via the existing `vendor/red-dragon` pin — no bump needed for this task).

This entire task lands as ONE commit: `compile_cics_program`'s signature change breaks every caller simultaneously, so partial completion would leave the repo red.

- [ ] **Step 1: Create `cics/coprocessor.py`**

```python
"""Wraps CicsLoweringStrategy as a CoprocessorSpec -- the seam
interpreter.project.coprocessor_compile.compile_program composes."""

from __future__ import annotations

from typing import Any

from cics.le_stubs import LE_STUBS_DIR
from cics.preprocessor import apply_cics_prepass
from cics.statements import CicsDialectParser
from cics.strategy import CicsLoweringStrategy

from interpreter.project.coprocessor_compile import CoprocessorSpec


def build_cics_spec(
    context_holder: list,
    result_holder: list | None = None,
    program_cache: dict | None = None,
    vsam_engine: Any = None,
    screen_queue: Any = None,
    input_queue: Any = None,
    **kwargs: Any,
) -> CoprocessorSpec:
    """Build the EXEC CICS CoprocessorSpec.

    ``context_holder``/``result_holder``/``program_cache`` are the same
    mutable cells CicsLoweringStrategy already uses internally -- pass the
    SAME dicts/lists across multiple compile_program() calls for programs
    that LINK to each other within one region.
    """

    def _make_strategy() -> CicsLoweringStrategy:
        return CicsLoweringStrategy(
            context_holder=context_holder,
            result_holder=result_holder,
            program_cache=program_cache,
            vsam_engine=vsam_engine,
            screen_queue=screen_queue,
            input_queue=input_queue,
            **kwargs,
        )

    return CoprocessorSpec(
        name="cics",
        make_strategy=_make_strategy,
        source_prepass=apply_cics_prepass,
        owns_execution=True,
        dialect_parser=CicsDialectParser(),
        extra_program_source_dirs=lambda: (LE_STUBS_DIR,),
    )
```

- [ ] **Step 2: Rewrite `compile_cics_program` in `cics/bootstrap.py`**

Current signature (to be replaced):
```python
def compile_cics_program(
    source: bytes,
    parser: Any,
    strategy: Any,
    *,
    program_source_dirs: Sequence[Path] = (),
) -> Any:
```

Replace the entire function body with:

```python
def compile_cics_program(
    source: bytes,
    parser: Any,
    spec: CoprocessorSpec,
    *,
    program_source_dirs: Sequence[Path] = (),
) -> Any:
    """Raw (NOT pre-passed) CICS COBOL ``source`` -> ``LinkedProgram`` with
    ``spec`` composed.

    ``spec`` (typically built by ``cics.coprocessor.build_cics_spec``) owns
    prepassing via its own ``source_prepass=apply_cics_prepass`` -- do NOT
    pre-pass ``source`` by hand before calling this function, or it will be
    prepassed twice.
    """
    from interpreter.project.coprocessor_compile import compile_program

    _frontend, linked = compile_program(
        source, parser, [spec], program_source_dirs=program_source_dirs
    )
    return linked
```

Add `from interpreter.project.coprocessor_compile import CoprocessorSpec` and
`from cics.coprocessor import build_cics_spec` to `cics/bootstrap.py`'s
top-level imports (needed by the type hint above and by
`run_carddemo_region` below).

- [ ] **Step 3: Rewrite `run_carddemo_region`'s strategy construction and docstring in `cics/bootstrap.py`**

Replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=vsam_engine,
        screen_queue=screen_queue,
        input_queue=input_queue,
        applid=applid,
        sysid=sysid,
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=vsam_engine,
        screen_queue=screen_queue,
        input_queue=input_queue,
        applid=applid,
        sysid=sysid,
    )
```

Replace the loop body's call:
```python
        program_cache[prog_name] = compile_cics_program(
            source,
            parser,
            strategy,
            program_source_dirs=program_source_dirs,
        )
```
with:
```python
        program_cache[prog_name] = compile_cics_program(
            source,
            parser,
            spec,
            program_source_dirs=program_source_dirs,
        )
```

Update `run_carddemo_region`'s docstring: the line
`` ``program_sources`` maps each program name to its **pre-passed** COBOL source
bytes.`` becomes
`` ``program_sources`` maps each program name to its **raw (NOT pre-passed)**
COBOL source bytes -- ``compile_cics_program`` prepasses via the spec now.``

Since `CicsLoweringStrategy` is no longer constructed directly in
`bootstrap.py`, remove its now-unused `from cics.strategy import
CicsLoweringStrategy` import if this was the only use in the file (check
with `grep -n CicsLoweringStrategy cics/bootstrap.py` after this step —
should show zero matches).

- [ ] **Step 4: Rewrite `cics/flow_map.py`'s `extract_transaction_flow_map`**

Replace:
```python
        # compile_cics_program expects pre-passed bytes; apply the prepass here
        prepassed = apply_cics_prepass(raw.decode("utf-8", errors="replace")).encode()
        observer = _CollectingObserver(prog_name)
        strategy = CicsLoweringStrategy(
            context_holder=[None],
            result_holder=[None],
            observer=observer,
        )
        # Positional args: source, parser, strategy
        compile_cics_program(prepassed, parser, strategy)
```
with:
```python
        observer = _CollectingObserver(prog_name)
        spec = build_cics_spec(
            context_holder=[None],
            result_holder=[None],
            observer=observer,
        )
        # Positional args: source, parser, spec
        compile_cics_program(raw, parser, spec)
```

Update the local imports inside `extract_transaction_flow_map` (currently
`from cics.dispatcher import parse_csd`, `from cics.bootstrap import
compile_cics_program`, `from cics.strategy import CicsLoweringStrategy`,
`from cics.preprocessor import apply_cics_prepass`): remove the
`CicsLoweringStrategy` and `apply_cics_prepass` imports (no longer used in
this function), add `from cics.coprocessor import build_cics_spec`.

- [ ] **Step 5: Update `tests/integration/cics/test_link.py`**

Replace the import block:
```python
from cics.preprocessor import apply_cics_prepass
from cics.strategy import CicsLoweringStrategy
```
with:
```python
from cics.coprocessor import build_cics_spec
```

Replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        screen_queue=screen_q,
        input_queue=input_q,
        program_cache=program_cache,
    )

    mutator = compile_cics_program(
        apply_cics_prepass(_MUTATOR_SRC).encode(), cobol_parser, strategy
    )
    wrapper = compile_cics_program(
        apply_cics_prepass(_WRAPPER_SRC).encode(), cobol_parser, strategy
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        screen_queue=screen_q,
        input_queue=input_q,
        program_cache=program_cache,
    )

    mutator = compile_cics_program(_MUTATOR_SRC.encode(), cobol_parser, spec)
    wrapper = compile_cics_program(_WRAPPER_SRC.encode(), cobol_parser, spec)
```

- [ ] **Step 6: Update `tests/integration/cics/test_carddemo_add_transaction.py`**

Replace the import lines:
```python
from cics.preprocessor import apply_cics_prepass
from cics.strategy import CicsLoweringStrategy
```
with:
```python
from cics.coprocessor import build_cics_spec
```

Replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    # COTRN02C CALLs 'CSUTLDTC' to validate the Orig/Proc dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the app's
    # cbl dir.
    addtran = compile_cics_program(
        apply_cics_prepass(addtran_path.read_text()).encode(),
        parser,
        strategy,
        program_source_dirs=[app / "cbl"],
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(signon_path.read_bytes(), parser, spec)
    menu = compile_cics_program(menu_path.read_bytes(), parser, spec)
    # COTRN02C CALLs 'CSUTLDTC' to validate the Orig/Proc dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the app's
    # cbl dir.
    addtran = compile_cics_program(
        addtran_path.read_bytes(),
        parser,
        spec,
        program_source_dirs=[app / "cbl"],
    )
```

- [ ] **Step 7: Update `tests/integration/cics/test_carddemo_reports.py`**

Same pattern as Step 6. Replace the import lines:
```python
from cics.preprocessor import apply_cics_prepass
from cics.strategy import CicsLoweringStrategy
```
with:
```python
from cics.coprocessor import build_cics_spec
```

Replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
        td_queue=td_queue,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    # CORPT00C CALLs 'CSUTLDTC' to validate the start/end dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the app's
    # cbl dir.
    reports = compile_cics_program(
        apply_cics_prepass(reports_path.read_text()).encode(),
        parser,
        strategy,
        program_source_dirs=[app / "cbl"],
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
        td_queue=td_queue,
    )

    signon = compile_cics_program(signon_path.read_bytes(), parser, spec)
    menu = compile_cics_program(menu_path.read_bytes(), parser, spec)
    # CORPT00C CALLs 'CSUTLDTC' to validate the start/end dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the app's
    # cbl dir.
    reports = compile_cics_program(
        reports_path.read_bytes(),
        parser,
        spec,
        program_source_dirs=[app / "cbl"],
    )
```

- [ ] **Step 8: Update `tests/integration/cics/test_carddemo_signon_real.py` (3 call sites)**

Replace the import lines:
```python
from cics.preprocessor import apply_cics_prepass
from cics.strategy import CicsLoweringStrategy
```
with:
```python
from cics.coprocessor import build_cics_spec
```

**Call site 1** (around line 244) — replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=_usrsec_engine(tmp_path / "vsam"),
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=_usrsec_engine(tmp_path / "vsam"),
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(signon_path.read_bytes(), parser, spec)
    menu = compile_cics_program(menu_path.read_bytes(), parser, spec)
```

**Call site 2** (around line 496) — replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    acctupd = compile_cics_program(
        apply_cics_prepass(acctupd_path.read_text()).encode(), parser, strategy
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(signon_path.read_bytes(), parser, spec)
    menu = compile_cics_program(menu_path.read_bytes(), parser, spec)
    acctupd = compile_cics_program(acctupd_path.read_bytes(), parser, spec)
```

**Call site 3** (around line 907) — replace:
```python
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    # COTRN02C CALLs 'CSUTLDTC' to validate the Orig/Proc dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the
    # CardDemo cbl/ dir so the date validation completes and the
    # ADD-TRANSACTION WRITE path runs.
    tranadd = compile_cics_program(
        apply_cics_prepass(tranadd_path.read_text()).encode(),
        parser,
        strategy,
        program_source_dirs=[app / "cbl"],
    )
```
with:
```python
    spec = build_cics_spec(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(signon_path.read_bytes(), parser, spec)
    menu = compile_cics_program(menu_path.read_bytes(), parser, spec)
    # COTRN02C CALLs 'CSUTLDTC' to validate the Orig/Proc dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source, but compile_cics_program
    # always contributes the LE-service stubs). Resolve CSUTLDTC from the
    # CardDemo cbl/ dir so the date validation completes and the
    # ADD-TRANSACTION WRITE path runs.
    tranadd = compile_cics_program(
        tranadd_path.read_bytes(),
        parser,
        spec,
        program_source_dirs=[app / "cbl"],
    )
```

- [ ] **Step 9: Update `tests/integration/cics/test_region_e2e.py` (4 `program_sources` sites)**

This file calls `run_carddemo_region`, not `compile_cics_program` directly —
only the manual `apply_cics_prepass(...)` calls when building each
`program_sources` dict need to change (no strategy/spec construction here).

**Site 1** (around line 99-102) — replace:
```python
    program_sources = {
        "SGNPGM": apply_cics_prepass(SGNPGM_SRC).encode(),
        "MENUPGM": apply_cics_prepass(MENUPGM_SRC).encode(),
    }
```
with:
```python
    program_sources = {
        "SGNPGM": SGNPGM_SRC.encode(),
        "MENUPGM": MENUPGM_SRC.encode(),
    }
```

**Site 2** (around line 157) — replace:
```python
        program_sources={"DNPGM": apply_cics_prepass(DATANAME_PGM_SRC).encode()},
```
with:
```python
        program_sources={"DNPGM": DATANAME_PGM_SRC.encode()},
```

**Site 3** (around line 228-231) — replace:
```python
    program_sources = {
        "ASKPGM": apply_cics_prepass(ASKPGM_SRC).encode(),
        "RESUMEPGM": apply_cics_prepass(RESUMEPGM_SRC).encode(),
    }
```
with:
```python
    program_sources = {
        "ASKPGM": ASKPGM_SRC.encode(),
        "RESUMEPGM": RESUMEPGM_SRC.encode(),
    }
```

**Site 4** (around line 292) — replace:
```python
        program_sources={"TDRESPGM": apply_cics_prepass(TDRESPGM_SRC).encode()},
```
with:
```python
        program_sources={"TDRESPGM": TDRESPGM_SRC.encode()},
```

Remove the now-unused `from cics.preprocessor import apply_cics_prepass`
import (line 30) once all 4 sites are updated — confirm with
`grep -n apply_cics_prepass tests/integration/cics/test_region_e2e.py`
(should show zero matches after this step).

- [ ] **Step 10: Update `tests/integration/cics/test_region_subprogram_link.py`**

Replace:
```python
    result = run_carddemo_region(
        transid_to_program={"CC00": "MAINLNK"},
        program_sources={"MAINLNK": apply_cics_prepass(MAINLNK_SRC).encode()},
        parser=parser,
        entry_transid="CC00",
        screen_queue=screen_q,
        input_queue=input_q,
        program_source_dirs=[cbl_dir],
    )
```
with:
```python
    result = run_carddemo_region(
        transid_to_program={"CC00": "MAINLNK"},
        program_sources={"MAINLNK": MAINLNK_SRC.encode()},
        parser=parser,
        entry_transid="CC00",
        screen_queue=screen_q,
        input_queue=input_q,
        program_source_dirs=[cbl_dir],
    )
```

Remove the now-unused `from cics.preprocessor import apply_cics_prepass`
import (line 27) — this file's only use of `apply_cics_prepass` was this
one call site.

Also update the module docstring's second paragraph, which currently reads
"We compile the main with `program_source_dirs` pointing at a dir that also
holds the callee source" — no change needed there (still accurate), but the
docstring does not mention prepassing so nothing else to fix.

- [ ] **Step 11: Run the full cicada suite**

Run: `make test`
Expected: 348 passed (same as before this task)

- [ ] **Step 12: Commit and push**

```bash
git add cics/coprocessor.py cics/bootstrap.py cics/flow_map.py \
  tests/integration/cics/test_link.py \
  tests/integration/cics/test_carddemo_add_transaction.py \
  tests/integration/cics/test_carddemo_reports.py \
  tests/integration/cics/test_carddemo_signon_real.py \
  tests/integration/cics/test_region_e2e.py \
  tests/integration/cics/test_region_subprogram_link.py
git commit -m "refactor: move build_cics_spec into cics.coprocessor, compile_cics_program takes a spec"
git push origin main
```

Record the resulting commit SHA — it is needed for Task 3's pin bump.

---

### Task 2: Squall — move build_sql_spec in, rewire the test compile helper

**Files:**
- Create: `squall/coprocessor.py`
- Modify: `tests/integration/squall_cobol_helpers.py`

**Interfaces:**
- Produces: `squall.coprocessor.build_sql_spec(connections: Mapping[str, SqlBackend], copybook_dirs: Sequence[Path] = (), initial_connector: DbConnector = NullDbConnector()) -> CoprocessorSpec`.
- Consumes: `interpreter.project.coprocessor_compile.{CoprocessorSpec, compile_program}` (already available via the existing `vendor/red-dragon` pin — no bump needed for this task).

- [ ] **Step 1: Create `squall/coprocessor.py`**

```python
"""Wraps Squall's SqlLoweringStrategy as a CoprocessorSpec -- the seam
interpreter.project.coprocessor_compile.compile_program composes."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from squall.backend import SqlBackend
from squall.connector import DbConnector, NullDbConnector
from squall.parser.sql_model import FieldMeta
from squall.preprocess import apply_sql_prepass
from squall.statements import SqlDialectParser
from squall.strategy import SqlLoweringStrategy

from interpreter.project.coprocessor_compile import CoprocessorSpec


def build_sql_spec(
    connections: Mapping[str, SqlBackend],
    copybook_dirs: Sequence[Path] = (),
    initial_connector: DbConnector = NullDbConnector(),
) -> CoprocessorSpec:
    """Build the EXEC SQL CoprocessorSpec.

    ``source_prepass`` expands EXEC SQL INCLUDE -> COPY and gathers the dclgen
    field metadata into a private holder as a side effect; ``make_strategy``
    reads that holder when called. ``compile_program`` always runs every
    spec's prepass before any spec's make_strategy, so the holder is populated
    in time (see CoprocessorSpec's docstring for why this ordering is required
    for SQL specifically, unlike CICS).

    ``initial_connector``, when it resolves a backend, is already current when
    the program starts -- models the CICS Db2 attachment facility, which hands
    a plan-bound program a live thread before its first SQL statement runs
    (the program itself never issues ``EXEC SQL CONNECT``, e.g. Bank-of-Z's
    ``INQCUST``). The default ``NullDbConnector()`` preserves squall's faithful
    disconnected-start behaviour for programs that CONNECT themselves; pass a
    ``squall.connector.NamedDbConnector(name)`` to model the attachment facility.
    """
    field_meta_holder: list[Mapping[str, FieldMeta]] = [{}]

    def _prepass(source: str) -> str:
        result = apply_sql_prepass(source, copybook_dirs)
        field_meta_holder[0] = result.field_meta
        return result.source

    def _make_strategy() -> SqlLoweringStrategy:
        return SqlLoweringStrategy(
            connections, field_meta_holder[0], initial_connector=initial_connector
        )

    return CoprocessorSpec(
        name="sql",
        make_strategy=_make_strategy,
        source_prepass=_prepass,
        owns_execution=False,
        dialect_parser=SqlDialectParser(),
    )
```

- [ ] **Step 2: Rewrite `compile_cobol()` in `tests/integration/squall_cobol_helpers.py`**

Replace the entire function body:

```python
def compile_cobol(
    source: str,
    bridge_jar_path: str,
    connections,
    copybook_dirs: list[Path] | None = None,
) -> tuple[CobolFrontend, LinkedProgram]:
    """Compile a COBOL source string to a LinkedProgram.

    *connections* is the connection registry (name -> backend) the program's
    EXEC SQL CONNECT selects from at run time; a run starts disconnected.

    Builds one CoprocessorSpec (squall.coprocessor.build_sql_spec) around a
    private holder that threads the prepass's dclgen field_meta into the SQL
    strategy, and delegates to RedDragon's shared compile_program
    (interpreter.project.coprocessor_compile) -- the same composition
    mechanism Cicada and red-dragon-forge use.

    Returns (frontend, linked) so that callers can access frontend.data_layout
    for assertions and pass the LinkedProgram to run_linked.
    """
    from squall.coprocessor import build_sql_spec
    from interpreter.project.coprocessor_compile import compile_program

    dirs = copybook_dirs or []
    parser = make_cobol_parser(bridge_jar_path, copybook_dirs=dirs)
    spec = build_sql_spec(connections, copybook_dirs=dirs)
    return compile_program(source.encode("utf-8"), parser, [spec])
```

This replaces the current body, which manually builds a `CoprocessorSpec`
inline with its own holder-cell (`field_meta_holder`) and `_prepass`
closure — delete that inline construction along with the now-unused
`from squall.statements import SqlDialectParser` and
`from interpreter.project.coprocessor_compile import CoprocessorSpec,
compile_program` local imports inside the old body (the new body imports
only `build_sql_spec` and `compile_program`). The unused top-level imports
`apply_sql_prepass` (from `squall.preprocess`) and `SqlLoweringStrategy`
(from `squall.strategy`) can also be removed from this file's top-level
import block if this function was their only use — check with
`grep -n "apply_sql_prepass\|SqlLoweringStrategy" tests/integration/squall_cobol_helpers.py`
after this step (should show no remaining references outside comments, if
any).

`make_cobol_parser()`, `run_cobol()`, `read_ws_field()`, and the
`bridge_jar` fixture are unaffected — do not modify them.

- [ ] **Step 3: Run the full squall suite**

```bash
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
export SQUALL_DB2_DSN2="DATABASE=MOJO2;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
uv run --no-sync python -m pytest tests/ -q
```

Expected: 271 passed, 1 skipped (same as before this task)

- [ ] **Step 4: Commit and push**

```bash
git add squall/coprocessor.py tests/integration/squall_cobol_helpers.py
git commit -m "refactor(test-helpers): move build_sql_spec into squall.coprocessor, use it directly"
git push origin main
```

Record the resulting commit SHA — it is needed for Task 3's pin bump.

---

### Task 3: red-dragon-forge — delete adapters/, rewire consumers, bump pins

**Files:**
- Delete: `red_dragon_forge/adapters/cics.py`
- Delete: `red_dragon_forge/adapters/sql.py`
- Delete: `red_dragon_forge/adapters/__init__.py`
- Delete: `red_dragon_forge/adapters/` (the now-empty directory)
- Modify: `tests/integration/test_cics_adapter.py`
- Modify: `tests/integration/test_cics_sql_composition.py`
- Modify: `tests/integration/test_inqcust_e2e.py`
- Modify: `tests/integration/test_sql_adapter.py`
- Modify: `vendor/cicada`, `vendor/squall` (pin bumps)

**Interfaces:**
- Consumes: `cics.coprocessor.build_cics_spec` (Task 1, via bumped `vendor/cicada`); `squall.coprocessor.build_sql_spec` (Task 2, via bumped `vendor/squall`).

- [ ] **Step 1: Bump `vendor/cicada` and `vendor/squall`**

```bash
cd vendor/cicada && git fetch origin && git checkout <task-1-commit-sha> && cd ../..
cd vendor/squall && git fetch origin && git checkout <task-2-commit-sha> && cd ../..
```

`vendor/red-dragon` is unchanged by this plan (Tasks 1 and 2 didn't touch
RedDragon) — no bump needed, and `scripts/check_red_dragon_pin.py` should
still report all three RedDragon pins matching without any change here.

- [ ] **Step 2: Delete `red_dragon_forge/adapters/`**

```bash
rm -rf red_dragon_forge/adapters
```

- [ ] **Step 3: Rewrite `tests/integration/test_cics_adapter.py`'s import**

Replace:
```python
from red_dragon_forge.adapters.cics import build_cics_spec
```
with:
```python
from cics.coprocessor import build_cics_spec
```

- [ ] **Step 4: Rewrite `tests/integration/test_cics_sql_composition.py`'s imports**

Replace:
```python
from red_dragon_forge.adapters.cics import build_cics_spec
from red_dragon_forge.adapters.sql import build_sql_spec
```
with:
```python
from cics.coprocessor import build_cics_spec
from squall.coprocessor import build_sql_spec
```

- [ ] **Step 5: Rewrite `tests/integration/test_inqcust_e2e.py`'s imports**

Replace:
```python
from red_dragon_forge.adapters.cics import build_cics_spec
from red_dragon_forge.adapters.sql import build_sql_spec
```
with:
```python
from cics.coprocessor import build_cics_spec
from squall.coprocessor import build_sql_spec
```

- [ ] **Step 6: Rewrite `tests/integration/test_sql_adapter.py`'s import**

Replace:
```python
from red_dragon_forge.adapters.sql import build_sql_spec
```
with:
```python
from squall.coprocessor import build_sql_spec
```

- [ ] **Step 7: Run the full red-dragon-forge suite**

```bash
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
uv run --no-sync python -m pytest tests/ -v
```

Expected: 7 passed (same as before this task, including the live-Db2
`test_inqcust_found_and_not_found` and the CEEDAYS proof test
`test_cics_program_calling_le_service_stub_resolves`)

If any `db2`-backed test fails with a communication error, restart Db2
(`docker exec squall-db2 su - db2inst1 -c 'db2start'`) and re-run — not a
regression from this task.

- [ ] **Step 8: Verify no remaining reference to the deleted adapters**

Run: `grep -rn "red_dragon_forge.adapters" --include="*.py" . | grep -v vendor`
Expected: no output (zero matches)

- [ ] **Step 9: Commit**

```bash
git add -A -- red_dragon_forge tests vendor
git commit -m "refactor: delete red_dragon_forge/adapters/, use cics.coprocessor/squall.coprocessor directly"
```

(No push — this repo has no remote.)

---

## Final Verification

After all three tasks: re-run cicada's, squall's, and red-dragon-forge's
full suites one more time in sequence to confirm no cross-repo drift, and
re-run `scripts/check_red_dragon_pin.py` in red-dragon-forge one final
time (should be unaffected by this plan, still reporting all three
RedDragon pins matching, since no repo's `vendor/red-dragon` moved).
