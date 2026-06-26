# Public COBOL Compile API — Design

**Status:** Designed (2026-06-26). Brainstormed. Awaiting user review.

**Repo:** red-dragon (the shared substrate). Consumers (cicada, squall, jackal) bump the
submodule to adopt it.

## What this builds (plain terms)
One public API that turns COBOL **source** into a runnable **`LinkedProgram`** — replacing the
**four** copies of that same pipeline that exist across the mainframe stack today. The pipeline
(`frontend.lower → build_cfg → build_registry → LinkedProgram`) is identical in all four; they
diverge only at two injection points (the **extension lowering strategy** and the **parser**,
plus optional **CALL-subprogram linking**). This API factors out the shared core so consumers
stop reinventing it.

## Driver (why now)
Four divergent copies of the source→LinkedProgram pipeline:
1. **`run()`** (`interpreter/run.py`) — ~77 inline lines: `get_frontend(COBOL)` → `frontend.lower`
   → `build_cfg` → `build_registry` → single-module `LinkedProgram`, default strategy.
2. **cicada `compile_cics_program`** (`cics/bootstrap.py`) — same core, but injects a
   `CicsLoweringStrategy`, a pre-built parser + `cics_text_parser`, and resolves/links CALLed
   subprograms (`_resolve_call_sources` + `topological_sort` + `link_modules`).
3. **squall `compile_cobol`** (its test helper `tests/integration/squall_cobol_helpers.py`) —
   same core, injects a `SqlLoweringStrategy` + parser; already named `compile_cobol`, already
   returns `(frontend, linked)`.
4. **jackal (needed)** — has only high-level `run(source, …)`; needs a `LinkedProgram` to call
   `run_linked(io_provider=…, initial_vm=…)` for PARM (`jackal-1o2.13`).

The divergence is about to bite: jackal can't get a `LinkedProgram` without either duplicating
the pipeline a fifth time or this API. Consolidating now (same pattern as the shared
access-method storage engine) unifies the stack's compile entry and unblocks PARM.

## The two injection points (the only real variation)
- **Extension lowering strategy** — `CobolFrontend(extension_strategies=[…])`. cicada passes
  `[CicsLoweringStrategy]`, squall `[SqlLoweringStrategy]`, run()/jackal `[]`. (Both implement
  `RedDragonExtensionLoweringStrategy`; the frontend already composes them.)
- **Parser** — cicada/squall pass a pre-built ProLeap parser (because they prepass the source
  first); run() lets `get_frontend` build a default. The API accepts an optional parser.

Everything else is shared. The **prepass** (CICS/SQL text rewriting) and **strategy
construction** stay in the consumers — they are extension-specific. The API stays
language-agnostic: it knows "extension strategies" and "a parser" abstractly, never
"CICS"/"SQL".

## API (two tiers, in `interpreter/project/`)
Alongside the existing file-based `compile_module()`/`compile_directory()`:

```python
def compile_cobol_module(
    source: bytes,
    *,
    parser: CobolParser | None = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    cics_text_parser: CicsTextParserFn | None = None,
    observer: FrontendObserver = NullFrontendObserver(),
) -> tuple[CobolFrontend, ModuleUnit]:
    """The shared single-module core: build the frontend (default parser if none
    injected), lower, build_cfg, build_registry, package a ModuleUnit. Returns the
    frontend too — consumers need frontend.data_layout / program_id / symbol tables."""

def compile_cobol(
    source: bytes,
    *,
    parser: CobolParser | None = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    cics_text_parser: CicsTextParserFn | None = None,
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
) -> tuple[CobolFrontend, LinkedProgram]:
    """Compile the main module via compile_cobol_module, then OPTIONALLY resolve
    CALLed subprograms (program_source_dir / extra_subprogram_sources) and
    link_modules into a multi-module LinkedProgram. No subprograms → single-module
    LinkedProgram. Returns (main frontend, linked)."""
```

**Return shape `(frontend, linked)`** — matches squall's existing helper and serves every
consumer: squall reads `frontend.data_layout`, cicada `frontend.program_id`, run() builds its
COBOL entry-point from `frontend.func_symbol_table`. (The `LinkedProgram` already carries
`type_env_builder`/`symbol_table`/`data_layout`/symbol tables, but `program_id` and the live
frontend are convenient to hand back rather than re-derive.)

## Migration — CALL-resolution moves into red-dragon
cicada's `_resolve_call_sources` + `topological_sort` + `link_modules` orchestration is
**generic COBOL CALL linking**, not CICS-specific — it belongs in the language-agnostic
substrate. `compile_cobol`'s subprogram path absorbs it, so jackal batch (CardDemo region
CALLs) and squall can reuse it too. (`link_modules`/`topological_sort` already live in
red-dragon `interpreter/project/`; only cicada's source-resolution glue migrates.)

## Consumers refactor onto it (each behavior-preserving)
- **`run()`** (COBOL branch): replace the ~40 inline compile lines with
  `frontend, linked = compile_cobol(source, copybook_dirs=…)`, keep its entry-point computation
  + `run_linked` call. Non-COBOL languages keep run()'s existing generic frontend path
  untouched (this API is COBOL-only).
- **cicada `compile_cics_program`**: becomes a thin wrapper —
  `compile_cobol(prepassed_source, extension_strategies=[strategy], parser=cics_parser,
  cics_text_parser=parse_exec_cics_text, program_source_dir=…, extra_subprogram_sources=…)`;
  delete its now-duplicated `_compile_cics_module`/`_resolve_call_sources`. Prepass + strategy
  construction stay in cicada.
- **squall**: replace `tests/integration/squall_cobol_helpers.py::compile_cobol` with a thin
  call to the red-dragon API (`extension_strategies=[SqlLoweringStrategy]`, parser). Prepass +
  strategy stay squall's. (Promotes a test helper to a real dependency on the public API.)
- **jackal**: NOT in this spec — jackal's PARM slice (`jackal-1o2.13`) is the first feature
  consumer (`compile_cobol(source) → run_linked(io_provider, initial_vm)`); it lands after this.

## Error handling
- A CALL target that can't be resolved (no source on disk, not in extras) → fail loud (the
  existing linker behavior; preserved).
- No `None` defaults that hide bugs; FP core / imperative shell; no regex; explicit injection
  (no implicit global strategy/parser).

## Testing (TDD; behavior-preserving is the gate)
- **The guard (all three consumer suites stay green):** red-dragon's full suite (the `run()`
  path — 14k+), cicada's CICS suite (incl. the durable CardDemo flows — `compile_cics_program`),
  and squall's suite (its helper). This is the proof the consolidation changed nothing.
- **New unit tests for the API:**
  - `compile_cobol_module` lowers a trivial COBOL source → a `ModuleUnit` with non-empty IR;
    returns a frontend exposing `data_layout`.
  - `compile_cobol` with no subprograms → a single-module `LinkedProgram` that `run_linked`
    executes (round-trip a tiny program).
  - `compile_cobol` with `extra_subprogram_sources` (a caller + a CALLed callee) → a
    multi-module `LinkedProgram` where the CALL resolves at run time (mirrors cicada's
    subprogram path, language-agnostic test — no CICS).
  - An injected no-op `extension_strategies` entry is invoked during lowering (proves the
    injection seam).
- **Consumer-refactor parity:** each refactored consumer's existing tests are the parity
  witness (no new behavior asserted — the suites prove equivalence).

## Constraints
- **Behavior-preserving** across all three consumer suites; pure consolidation.
- red-dragon stays **language-agnostic** at the API layer (extension strategies + parser as
  abstractions; never CICS/SQL names). COBOL-specific is fine (it's `compile_cobol`); the
  generic non-COBOL `run()` path is untouched.
- FP / frozen where applicable; no `None` defaults hiding bugs; no defensive guards (fail loud);
  no regex. Python 3.13, black, real pre-commit hooks.

## Risks
- **Cross-repo, three consumers** — the refactor touches red-dragon + cicada + squall, each
  guarded by its own suite. Sequence: land the API in red-dragon (with run() refactored, full
  suite green) → bump + refactor cicada (CICS suite green) → bump + refactor squall (squall
  suite green). Each repo behavior-preserving independently.
- **Frontend construction parity** — `get_frontend` (run()) vs direct `CobolFrontend(...)`
  (cicada/squall) must converge without changing lowering. The API builds the frontend one way;
  run()'s default-parser path must produce identical IR (its full suite is the guard).
- **`(frontend, linked)` return** — run() currently keeps the frontend in locals; ensure the
  refactor threads the returned frontend to the exact same downstream uses (entry-point,
  type_env). The suite guards it.
- **Scope creep into a generic multi-language compile API** — resist; this is `compile_cobol`,
  COBOL-only. Other frontends are out of scope (YAGNI).

## Bookkeeping
- New red-dragon epic/issue (Compile API). **Prerequisite for `jackal-1o2.13` (PARM)** — that
  jackal spec already records the dependency.
- Follow-ons enabled: jackal batch multi-module CALL linking can later reuse `compile_cobol`'s
  subprogram path; squall's helper becomes a thin public-API call.
