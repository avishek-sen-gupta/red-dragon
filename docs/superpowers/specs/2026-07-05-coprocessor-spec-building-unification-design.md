# Coprocessor Spec-Building Unification Design

## Problem

The prior coprocessor-compile unification (2026-07-05) hoisted the generic
composition harness (`CoprocessorSpec`/`compile_program`) out of
red-dragon-forge into RedDragon. It deliberately left each coprocessor's own
**spec-building** logic — "how do I turn my runtime state into a
`CoprocessorSpec`?" — duplicated between forge's adapters
(`red_dragon_forge/adapters/cics.py::build_cics_spec`,
`adapters/sql.py::build_sql_spec`) and each coprocessor's own callers:

- Squall's `tests/integration/squall_cobol_helpers.py::compile_cobol()`
  reimplements `build_sql_spec`'s exact holder-cell pattern (dclgen
  `field_meta` threaded from prepass to strategy construction) inline.
- Cicada's `cics/bootstrap.py::compile_cics_program` builds its own inline
  `CoprocessorSpec` (`dialect_parser=CicsDialectParser()`,
  `extra_program_source_dirs=lambda: (LE_STUBS_DIR,)`) around a
  caller-supplied `strategy`, duplicating the same two fields
  `build_cics_spec` already sets. `run_carddemo_region` separately builds
  `CicsLoweringStrategy` directly, duplicating `build_cics_spec`'s
  strategy-construction logic too.

This design moves each coprocessor's spec-building function into that
coprocessor's own repo (mirroring where `LE_STUBS_DIR` and
`SqlLoweringStrategy` already live), and has every caller — including
red-dragon-forge itself — use it, eliminating the duplication entirely
rather than accepting it as a fixed cost.

## Key finding: multi-instance CicsLoweringStrategy construction is already safe

`CicsLoweringStrategy.__init__` registers builtins into a process-global
table (`Builtins.TABLE`) and logs a warning if a second instance is
constructed in the same process ("Multiple CicsLoweringStrategy instances in
one process is unsupported"). This looked like a blocker for having
`build_cics_spec`'s `make_strategy` closure called fresh per compile — but
`red-dragon-forge/tests/integration/test_inqcust_e2e.py` **already does
exactly this** in its production capstone test: it calls `build_cics_spec()`
twice (once for INQCUST, once for a linked WRAPPER program), each call
building a fresh `CicsLoweringStrategy`, sharing only the external
`context_holder`/`result_holder`/`program_cache`. This passes today. So
reusing `build_cics_spec` from Cicada's own multi-program `run_carddemo_region`
carries no new risk — it's the same proven pattern.

## Design

### Cicada

**New file `cics/coprocessor.py`** — `build_cics_spec` moved verbatim from
`red_dragon_forge/adapters/cics.py`. No import-path changes needed inside the
function body: `LE_STUBS_DIR` (`cics.le_stubs`), `apply_cics_prepass`
(`cics.preprocessor`), `CicsDialectParser` (`cics.statements`), and
`CicsLoweringStrategy` (`cics.strategy`) are already local to this repo.

```python
"""Wraps CicsLoweringStrategy as a CoprocessorSpec — the seam
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
    mutable cells CicsLoweringStrategy already uses internally — pass the
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

**`cics/bootstrap.py` changes:**

`compile_cics_program`'s signature changes from taking a raw `strategy: Any`
to taking a pre-built `spec: CoprocessorSpec` — since every real caller
constructs a `CicsLoweringStrategy` with a parameter shape that maps directly
onto `build_cics_spec`'s own parameters (verified against all 6 call sites,
see Callers below), there's no reason for `compile_cics_program` to keep
building its own separate, duplicate spec around a bare strategy:

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
    prepassed twice (see "Prepass ownership" in the design doc).
    """
    from interpreter.project.coprocessor_compile import compile_program

    _frontend, linked = compile_program(
        source, parser, [spec], program_source_dirs=program_source_dirs
    )
    return linked
```

`run_carddemo_region` replaces its own `CicsLoweringStrategy(...)`
construction with `build_cics_spec(...)` (identical parameters), and passes
the resulting `spec` to `compile_cics_program` instead of a raw `strategy`.

**Callers verified to already match `build_cics_spec`'s parameter shape**
(context_holder, result_holder, vsam_engine, screen_queue, input_queue, plus
optional program_cache/td_queue): `run_carddemo_region`,
`tests/integration/cics/test_link.py`,
`tests/integration/cics/test_carddemo_add_transaction.py`,
`tests/integration/cics/test_carddemo_reports.py`,
`tests/integration/cics/test_carddemo_signon_real.py` (3 call sites within
this one file). These 5 all switch from `CicsLoweringStrategy(...)` +
`strategy=` to `build_cics_spec(...)` + `spec=`.

`tests/integration/cics/test_region_subprogram_link.py` and
`tests/integration/cics/test_region_e2e.py` call `run_carddemo_region` (not
`compile_cics_program` directly) — they need no strategy/spec change, but
DO need their manual `apply_cics_prepass(...)` call removed when building
`program_sources` (see Prepass ownership below).

`tests/unit/cics/test_bootstrap.py` monkeypatches `compile_cics_program`
itself and is unaffected by either change.

**`cics/flow_map.py`** (production, non-test code — found in a final sweep
of every `CicsLoweringStrategy(`/`compile_cics_program(` call site in this
repo) also calls `compile_cics_program` directly, with
`strategy = CicsLoweringStrategy(context_holder=[None], result_holder=[None],
observer=observer)` — matches `build_cics_spec`'s shape (`observer` flows
through its `**kwargs`). It currently hand-decodes, prepasses, and
re-encodes its source (`apply_cics_prepass(raw.decode(...)).encode()`)
before calling `compile_cics_program` — once `compile_cics_program` takes a
`spec` that already owns prepassing, and given `compile_program` itself
decodes/re-encodes around `source_prepass` internally, this entire
decode-prepass-encode dance in `flow_map.py` becomes dead code and is
deleted; `raw` (already bytes) is passed straight through.

### Prepass ownership

This is a real, deliberate behavior point, not an oversight: after this
change, `apply_cics_prepass` runs exactly once — inside `compile_program`,
driven by `spec.source_prepass` (which `build_cics_spec` always sets). Every
`compile_cics_program` caller listed above currently pre-passes its own
source by hand (`apply_cics_prepass(SOURCE).encode()`) before calling it —
**that manual pre-pass must be removed from every caller** as part of this
change, otherwise the double-prepass bug fixed in the prior
coprocessor-compile-unification round (2026-07-05,
`fix(bootstrap): stop double-prepassing...`) reappears. `compile_cics_program`
's docstring and each caller's own comments referencing "already prepassed"
must be updated to reflect that `spec` owns prepassing now, not the caller.

**This propagates one level up, to `run_carddemo_region`'s own contract.**
Today its docstring requires `program_sources` to hold **pre-passed** bytes
(every real caller hand-calls `apply_cics_prepass` before building that
dict) — but `run_carddemo_region` forwards those bytes straight into
`compile_cics_program`, which will now prepass them again via the spec. So
`run_carddemo_region`'s contract changes too: `program_sources` must now
hold **raw, NOT pre-passed** COBOL source bytes. Docstring updated
accordingly. Both real callers must drop their manual pre-pass when building
`program_sources`:

- `tests/integration/cics/test_region_e2e.py` (2 call sites, lines ~100-101,
  ~228ish — each currently does `apply_cics_prepass(SGNPGM_SRC).encode()`
  etc. when building the `program_sources` dict)
- `tests/integration/cics/test_region_subprogram_link.py` (1 call site,
  `apply_cics_prepass(MAINLNK_SRC).encode()`)

`tests/unit/cics/test_bootstrap.py` passes synthetic byte literals
(`b"src-sgn"`) as `program_sources` values and monkeypatches
`compile_cics_program` itself, so real prepassing never runs in that test —
unaffected by this contract change.

### Squall

**New file `squall/coprocessor.py`** — `build_sql_spec` moved verbatim from
`red_dragon_forge/adapters/sql.py`. Same no-import-changes-needed property:
`SqlBackend`/`DbConnector`/`NullDbConnector`/`FieldMeta`/`apply_sql_prepass`/
`SqlDialectParser`/`SqlLoweringStrategy` are all already local to Squall.

**`tests/integration/squall_cobol_helpers.py`'s `compile_cobol()`** calls
`build_sql_spec(connections, copybook_dirs=dirs)` directly instead of
reimplementing the holder-cell pattern inline:

```python
def compile_cobol(
    source: str,
    bridge_jar_path: str,
    connections,
    copybook_dirs: list[Path] | None = None,
) -> tuple[CobolFrontend, LinkedProgram]:
    from squall.coprocessor import build_sql_spec
    from interpreter.project.coprocessor_compile import compile_program

    dirs = copybook_dirs or []
    parser = make_cobol_parser(bridge_jar_path, copybook_dirs=dirs)
    spec = build_sql_spec(connections, copybook_dirs=dirs)
    return compile_program(source.encode("utf-8"), parser, [spec])
```

`make_cobol_parser()`, `run_cobol()`, `read_ws_field()`, and the `bridge_jar`
fixture are unaffected.

### red-dragon-forge

`red_dragon_forge/adapters/` (both `cics.py` and `sql.py`, plus the
now-empty `__init__.py` and the directory itself) is deleted entirely.
`tests/integration/test_cics_adapter.py`, `test_cics_sql_composition.py`,
`test_inqcust_e2e.py`, and `test_sql_adapter.py` import `build_cics_spec`/
`build_sql_spec` directly from `cics.coprocessor`/`squall.coprocessor`.
`red_dragon_forge/run.py` is unaffected (it never imported from `adapters/`).

## Non-goals

- No change to `build_cics_spec`'s or `build_sql_spec`'s own field logic —
  this is a pure move plus the prepass-ownership fix already implied by
  giving `compile_cics_program` a pre-built spec.
- No change to `CoprocessorSpec`/`compile_program` themselves (RedDragon is
  untouched by this design).
- No change to `run_carddemo_region`'s or `compile_cics_program`'s runtime
  *results* for equivalent input (same COBOL source compiled and dispatched
  the same way). Their **contracts do change**, deliberately (see Prepass
  ownership): `compile_cics_program` takes a `spec` instead of a `strategy`,
  and `run_carddemo_region`'s `program_sources` must now be raw
  (un-pre-passed) bytes rather than pre-passed bytes. Every real caller of
  both functions is updated in this same change, so no caller is left on
  the old contract.

## Testing

Cicada's full suite (348 tests, unchanged count) and Squall's full suite
(271 passed, 1 skipped, unchanged count) must both still pass — this is a
structural move, not a behavior change, for every correctly-updated caller.
red-dragon-forge's full suite (7 tests, unchanged count) must still pass,
including the live-Db2 INQCUST e2e and the CEEDAYS LE-stub proof test.
