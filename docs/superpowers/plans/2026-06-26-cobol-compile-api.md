# Public COBOL Compile API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One public API — `compile_cobol_module` + `compile_cobol` — that turns COBOL source into a `LinkedProgram`, replacing the four divergent copies (run() inline, cicada `compile_cics_program`, squall's helper, jackal's need).

**Architecture:** Promote squall's already-generic `compile_cobol` helper into red-dragon `interpreter/project/`, parameterized at three injection points: `extension_strategies`, `parser`, and a per-callee `source_transform`. A two-tier API: a single-module core, and a program tier that optionally resolves + links CALLed subprograms (porting cicada's proven orchestration, made generic). Then refactor all four consumers onto it, each behavior-preserving against its own test suite.

**Tech Stack:** Python 3.13, frozen dataclasses, pytest, black. red-dragon (API + run()), then cicada + squall (refactor onto it, after a submodule bump).

## Global Constraints
- **Behavior-preserving** across all three consumer suites — this is a pure consolidation; no program output changes. The guards: red-dragon full suite (run() path), cicada CICS suite (incl. durable CardDemo flows), squall suite.
- red-dragon stays **language-agnostic** at the API layer: it knows `extension_strategies`, `parser`, `source_transform` abstractly — never "CICS"/"SQL". (COBOL-specific is fine; the generic non-COBOL `run()` path is untouched.)
- The **three injection points** with exact defaults: `extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = ()`; `parser: CobolParser | None = None` (build default via `get_frontend` when None); `source_transform: Callable[[str], str] = (lambda s: s)` (per-callee prepass; identity for run()/jackal).
- Return shape is **`(CobolFrontend, LinkedProgram)`** / **`(CobolFrontend, ModuleUnit)`** — consumers need `frontend.data_layout` / `program_id` / symbol tables.
- FP / imperative shell; **no `None` defaults that hide bugs; no defensive guards (fail loud); no regex.**
- Tooling: `uv run --no-sync python -m pytest …`; `uv run --no-sync python -m black …` before commit; real pre-commit hooks (full suite — slow, allow ~5 min). Cross-repo: Phase 1 merged to red-dragon main + bumped before Phases 2/3.

## File Structure
- **Create `interpreter/project/cobol_compile.py`** — the public API (`compile_cobol_module`, `compile_cobol`). Lives beside the existing `compiler.py`/`linker.py` in `interpreter/project/`.
- **Modify `interpreter/run.py`** — run()'s COBOL compile block (lines ~1270–1331) calls `compile_cobol`.
- **(Phase 2, cicada) `cics/bootstrap.py`** — `compile_cics_program` becomes a wrapper; delete `_compile_cics_module` + `_resolve_call_sources`.
- **(Phase 3, squall) `tests/integration/squall_cobol_helpers.py`** — `compile_cobol` becomes a thin call to the red-dragon API.

---

## Task 1 (red-dragon): `compile_cobol_module` — the single-module core

**Files:** Create `interpreter/project/cobol_compile.py`; Test `tests/unit/project/test_cobol_compile.py`.

**Interfaces:**
- Produces: `def compile_cobol_module(source: bytes, *, parser=None, copybook_dirs=None, extension_strategies=(), cics_text_parser=None, observer=NullFrontendObserver()) -> tuple[CobolFrontend, ModuleUnit]`.

- [ ] **Step 1: Write the failing test** — `tests/unit/project/test_cobol_compile.py`:
```python
from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.project.types import ModuleUnit
from tests.covers import covers, NotLanguageFeature

_SRC = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'HI'.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_returns_frontend_and_module():
    frontend, module = compile_cobol_module(_SRC)
    assert isinstance(module, ModuleUnit)
    assert len(module.ir) > 0
    # frontend exposes the data the consumers read off it
    assert frontend.data_layout is not None
    assert frontend.func_symbol_table is not None
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** — `interpreter/project/cobol_compile.py`. Build the frontend (default via `get_frontend` when no parser injected; else construct `CobolFrontend` directly with the injected parser + strategies), lower, package a `ModuleUnit`. Mirror `compile_module` (compiler.py:163) for the `ModuleUnit` fields (`build_export_table`, `extract_imports`):
```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.constants import Language
from interpreter.frontend import get_frontend, FrontendObserver, NullFrontendObserver
from interpreter.project.compiler import build_export_table
from interpreter.project.imports import extract_imports
from interpreter.project.types import ModuleUnit
import interpreter.constants as constants


def _build_cobol_frontend(parser, extension_strategies, cics_text_parser, copybook_dirs, observer):
    if parser is None:
        return get_frontend(
            Language.COBOL,
            frontend_type=constants.FRONTEND_COBOL,
            observer=observer,
            copybook_dirs=copybook_dirs,
        )
    from interpreter.cobol.cobol_frontend import CobolFrontend
    return CobolFrontend(
        cobol_parser=parser,
        observer=observer,
        extension_strategies=list(extension_strategies),
        cics_text_parser=cics_text_parser,
    )


def compile_cobol_module(
    source: bytes,
    *,
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend = _build_cobol_frontend(
        parser, extension_strategies, cics_text_parser, copybook_dirs, observer
    )
    ir = frontend.lower(source)
    exports = build_export_table(ir, frontend.func_symbol_table, frontend.class_symbol_table)
    imports = tuple(extract_imports(source, path, Language.COBOL))
    module = ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
    return frontend, module
```
  Verify the exact `get_frontend`/`CobolFrontend`/`ModuleUnit`/`build_export_table` signatures against the source as you go (the plan's imports may need path adjustment — `build_export_table` is in `compiler.py`); fix to match. Do NOT add `None` defaults beyond those shown; no guards.

- [ ] **Step 4: Run → pass.** `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py -v` → PASS.

- [ ] **Step 5: Commit.**
```bash
uv run --no-sync python -m black interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git add interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git commit -m "feat(project): compile_cobol_module — shared single-module COBOL compile core (red-dragon-mc6u compile-api)"
```

---

## Task 2 (red-dragon): `compile_cobol` — program tier (single + multi-module)

**Files:** Modify `interpreter/project/cobol_compile.py`; Test `tests/unit/project/test_cobol_compile.py`.

**Interfaces:**
- Consumes: `compile_cobol_module` (Task 1); `link_modules` (`interpreter/project/linker.py` — `(modules, import_graph, project_root, topo_order, language, type_env_builder=, symbol_table=, data_layout=)`); `topological_sort`/`get_resolver` (`interpreter/project/resolver.py`); `extract_imports`; `build_cfg`, `build_registry`, `LinkedProgram`.
- Produces: `def compile_cobol(source, *, parser=None, copybook_dirs=None, extension_strategies=(), cics_text_parser=None, observer=NullFrontendObserver(), program_source_dir=None, extra_subprogram_sources=None, source_transform=lambda s: s) -> tuple[CobolFrontend, LinkedProgram]`.

**Reference:** cicada `cics/bootstrap.py::compile_cics_program` + `_resolve_call_sources` are the proven orchestration to port. The ONLY change in porting: the per-callee `apply_cics_prepass(...)` becomes `source_transform(...)`. The CALL walk uses red-dragon's own `extract_imports` + `get_resolver(Language.COBOL)` (already done in cicada's `_resolve_call_sources`).

- [ ] **Step 1: Write the failing tests** (single-module + multi-module CALL):
```python
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked, EntryPoint


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_single_module_runs():
    frontend, linked = compile_cobol(_SRC)
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
    # round-trips through run_linked (top-level COBOL entry)
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_links_extra_subprogram():
    caller = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""
    callee = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           DISPLAY 'IN CALLEE'.
           GOBACK.
"""
    frontend, linked = compile_cobol(caller, extra_subprogram_sources={"CALLEE": callee})
    # CALLEE linked as a second module
    assert len(linked.modules) >= 1
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_source_transform_applied_to_callees():
    seen: list[str] = []
    def xform(s: str) -> str:
        seen.append(s)
        return s
    caller = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""
    callee = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           GOBACK.
"""
    compile_cobol(caller, extra_subprogram_sources={"CALLEE": callee}, source_transform=xform)
    assert seen  # the callee source passed through the transform
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py -v` → FAIL (`compile_cobol` undefined).

- [ ] **Step 3: Implement `compile_cobol`** in `cobol_compile.py`. Compile the main module via `compile_cobol_module`; if no subprograms (no `program_source_dir`, no `extra_subprogram_sources`), build a single-module `LinkedProgram` exactly as run() does today (build_cfg + build_registry on the module IR — copy run.py:1299–1331's LinkedProgram construction verbatim). Otherwise, port cicada's `_resolve_call_sources` walk (generic: `extract_imports` + `get_resolver(Language.COBOL)`, applying `source_transform` to each resolved callee source instead of `apply_cics_prepass`), compile each subprogram module via `compile_cobol_module` (same strategies/parser), then `topological_sort` + `link_modules`. Read cicada `cics/bootstrap.py` lines 76–271 as the reference and adapt — do not invent fresh linking logic. Return `(main_frontend, linked)`.

- [ ] **Step 4: Run → pass + full red-dragon suite.** `uv run --no-sync python -m pytest tests/unit/project/test_cobol_compile.py -v` then `PROLEAP_BRIDGE_JAR=… uv run --no-sync python -m pytest -q` → all green.

- [ ] **Step 5: Commit.**
```bash
uv run --no-sync python -m black interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git add interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git commit -m "feat(project): compile_cobol — program tier with CALL-subprogram linking + source_transform (red-dragon compile-api)"
```

---

## Task 3 (red-dragon): refactor run()'s COBOL branch onto `compile_cobol`

**Files:** Modify `interpreter/run.py` (the COBOL portion of lines ~1270–1331); guard = full suite.

- [ ] **Step 1:** The behavior guard is the existing full suite — no new test. Confirm a baseline green first: `PROLEAP_BRIDGE_JAR=… uv run --no-sync python -m pytest -q`.

- [ ] **Step 2: Refactor.** For the COBOL language branch, replace the inline `get_frontend → frontend.lower → build_cfg → build_registry → LinkedProgram` block (run.py ~1274–1331) with `frontend, linked = compile_cobol(source.encode("utf-8"), copybook_dirs=copybook_dirs, observer=_StatsObserver(stats))`. Keep everything after — the COBOL entry-point computation (1340–1354, uses `frontend.func_symbol_table`) and the `run_linked(...)` call (1358) — unchanged. **Non-COBOL languages keep the existing inline path** (guard the refactor with `if lang == Language.COBOL: … else: <existing inline>`), since `compile_cobol` is COBOL-only. Preserve the `PipelineStats` fields run() reports: if `compile_cobol` doesn't populate `stats.cfg_time`/`registry_time`, either thread them or accept they fold into total — the full suite (incl. any stats test) is the gate; if a stats assertion breaks, preserve the field rather than weaken the test.

- [ ] **Step 3: Run the full suite (the behavior-preservation proof).** `PROLEAP_BRIDGE_JAR=… uv run --no-sync python -m pytest -q` → identical green to the baseline. Investigate any diff as a refactor bug; do not weaken a test.

- [ ] **Step 4: Commit** (real pre-commit, full suite runs).
```bash
uv run --no-sync python -m black interpreter/run.py
git add interpreter/run.py
git commit -m "refactor(run): COBOL branch compiles via compile_cobol (behavior-preserving) (red-dragon compile-api)"
```

- [ ] **Step 5: Merge Phase 1 to red-dragon main + push** (so consumers can bump). Merge `cobol-compile-api` → main (ff), push.

---

## Task 4 (cicada): refactor `compile_cics_program` onto `compile_cobol`

**Repo:** cicada. After Phase 1 is on red-dragon main. Bump `vendor/red-dragon`.

**Files:** Modify `cics/bootstrap.py`; guard = cicada full suite (incl. CardDemo CICS flows).

- [ ] **Step 1: Bump** `vendor/red-dragon` to red-dragon main (Phase 1). `git add vendor/red-dragon`. No JAR rebuild (Python-only); no `uv sync`.
- [ ] **Step 2: Baseline green** — `CARDDEMO_HOME=… PROLEAP_BRIDGE_JAR=… JCL_BRIDGE_JAR=… uv run --no-sync python -m pytest -q` (record the pass count).
- [ ] **Step 3: Refactor `compile_cics_program`** to a thin wrapper:
```python
from interpreter.project.cobol_compile import compile_cobol
from cics.preprocessor import apply_cics_prepass
# ... inside compile_cics_program, replacing the _compile_cics_module + _resolve_call_sources + link body:
    _frontend, linked = compile_cobol(
        source,  # already CICS-prepassed by the caller
        parser=parser,
        extension_strategies=[strategy],
        cics_text_parser=parse_exec_cics_text,
        program_source_dir=program_source_dir,
        extra_subprogram_sources=_encode_extras(extra_subprogram_sources),
        source_transform=lambda s: apply_cics_prepass(s),
    )
    return linked
```
  Preserve `compile_cics_program`'s existing return type/signature exactly (callers unchanged). **Delete** `_compile_cics_module` and `_resolve_call_sources` (now in red-dragon). Keep the main-program prepass + `strategy` construction where they are (caller-side / unchanged).
- [ ] **Step 4: Run cicada full suite (the guard).** All CardDemo CICS flows must stay green (same pass count). Any regression → systematic-debugging against the pre-refactor behavior; do not weaken a test.
- [ ] **Step 5: Commit** through cicada's real pre-commit; merge to cicada main + push.

---

## Task 5 (squall): replace its `compile_cobol` helper with the red-dragon API

**Repo:** squall. After Phase 1 on red-dragon main. Bump `vendor/red-dragon`.

**Files:** Modify `tests/integration/squall_cobol_helpers.py`; guard = squall full suite.

- [ ] **Step 1: Bump** `vendor/red-dragon` to red-dragon main; `git add vendor/red-dragon`.
- [ ] **Step 2: Baseline green** — run squall's full suite, record pass count.
- [ ] **Step 3: Replace the helper body** — `squall_cobol_helpers.py::compile_cobol` calls the red-dragon API, keeping its own prepass + strategy:
```python
from interpreter.project.cobol_compile import compile_cobol as _compile_cobol

def compile_cobol(source, bridge_jar_path, connections, copybook_dirs=None):
    dirs = copybook_dirs or []
    prepass = apply_sql_prepass(source, dirs)
    strategy = SqlLoweringStrategy(connections, prepass.field_meta)
    parser = make_cobol_parser(bridge_jar_path, copybook_dirs=dirs)
    frontend, linked = _compile_cobol(
        prepass.source.encode("utf-8"),
        parser=parser,
        extension_strategies=[strategy],
    )
    return frontend, linked
```
  (squall's programs are single-module today, so no `source_transform`/subprograms needed; if a squall test compiles a CALLing program, add `source_transform=lambda s: apply_sql_prepass(s, dirs).source` then.) Keep the helper's public signature + `(frontend, linked)` return identical.
- [ ] **Step 4: Run squall's full suite (the guard)** — same pass count, green.
- [ ] **Step 5: Commit** through squall's real pre-commit; merge to squall main + push.

---

## Self-Review
**Spec coverage:** `compile_cobol_module` → Task 1 ✓; `compile_cobol` two-tier + `source_transform` + CALL-linking → Task 2 ✓; run() refactor (COBOL-only, non-COBOL untouched) → Task 3 ✓; cicada wrapper + delete dupes → Task 4 ✓; squall helper → Task 5 ✓; promote-squall-helper origin → Tasks 1–2 (its pipeline is the reference) ✓; behavior-preserving three-suite guard → Tasks 3/4/5 full-suite gates ✓; cross-repo sequencing → Task 3 Step 5 merge gate before 4/5 ✓.
**Placeholder scan:** the multi-module impl (Task 2 Step 3) references cicada `bootstrap.py:76–271` as the concrete port source rather than re-deriving — an explicit file:line reference, not "TBD"; single-module construction copies run.py:1299–1331 verbatim. Single-module + injection tiers have complete code.
**Type consistency:** `compile_cobol_module(...) -> (frontend, ModuleUnit)` and `compile_cobol(...) -> (frontend, LinkedProgram)` used identically across tasks; `source_transform: Callable[[str], str]` identity default consistent; `extension_strategies`/`parser`/`cics_text_parser` names match the spec and `CobolFrontend.__init__`.
