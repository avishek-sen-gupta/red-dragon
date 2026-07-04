# No-`None`-default parameter cleanup — design

**Ticket:** red-dragon-nz4y
**Date:** 2026-07-04

## Problem

`.claude/conditional/design-principles.md` states:

> No `None` as a default parameter. Use empty structures (`{}`, `[]`, `()`).
> No `None` returns from non-None return types. Use null object pattern.

A new pylint checker (`pylint_plugins/no_none_default.py`, message `no-none-default` / `C9701`) mechanically enforces this: it flags any function/method parameter whose default is a literal `None` constant, while correctly *not* flagging parameters that already use the null-object pattern (e.g. `observer: FrontendObserver = NullFrontendObserver()`, `source_transform: Callable = lambda s: s`). Run repo-wide over `interpreter/` (tests excluded, matching `.pylintrc` scope), it found **70 violations across 25 files**, enumerated in full in red-dragon-nz4y.

These are not 70 independent mistakes. Every site's actual default value and body usage was checked (not inferred from the parameter name) before bucketing — two separate verification passes each caught real mis-classifications (the first pass silently dropped 3 sites and mis-classified a 4th; a second pass, checking actual body behavior rather than just what sits next to a parameter, found 4 more). The numbers below are the final, twice-verified picture and sum to exactly 70. This spec covers **49 sites** actually being fixed now (buckets A, B, C, D below); **18 sites** are deferred to bucket E (see "Out of scope"); **3 sites** (`cobol_parser`, `llm_client` ×2) are deferred to a separate follow-up story, red-dragon-79iv, since fixing them properly is a real architectural change (splitting `get_frontend`'s per-language optional dependencies into required-arg entry points), not a mechanical signature-default swap.

## Buckets and fixes

### Bucket A — pure collections and body-confirmed static fallbacks (18 sites)

`X: list[...] | None = None` / `dict[...] | None = None`, where the function body already does the `or []` / `or {}` unwrap — or a `Path | None = None` where the body's fallback is a fixed literal (verified, not assumed) rather than derived from another parameter.

**Fix:** move the default into the signature directly; delete the now-dead `or` fallback in the body.

Sites:
- `copybook_dirs` (8×: `cobol_parser.py` ×2, `frontend.py`, `cobol_compile.py` ×2, `cobol_connections.py`, `compiler.py`, `run.py`) → `[]`
- `resolved_imports` (`cobol_frontend.py`) → `{}`
- `file_control`, `path_overrides` (`real_file_provider.py`) → `[]` / `{}`
- `extra_subprogram_sources` (2×: `cobol_compile.py`, `cobol_connections.py`) → `{}`
- `params` (`instructions.py`) → `[]`
- `data_layout` (`linker.py`) → `{}`
- `source_roots` (`resolver.py`) → `[]`
- `program_source_dir` (2×: `cobol_compile.py`, `cobol_connections.py`) → `Path(".")` — verified: `cobol_compile.py:144` already does `base = program_source_dir or Path(".")`; this is a fixed literal, safe to hoist into the signature.

Safe under the project's "no mutation after construction" convention — none of these sites mutate the parameter in place; they read it or copy it (`dict(x or {})`, `list(x or [])`), so a shared literal default carries no cross-call state.

### Bucket B — reuse an existing sentinel (20 sites)

The codebase already has null-object sentinels for exactly these shapes — verified by reading each function's actual body (not just what sits next to the violation), which caught one mis-classification (`symbol_table`, moved out — see below):

- **`node`-family, tree-sitter source nodes used only for diagnostics/source-location, never mutated (15 sites: `node` ×13 across `frontends/_base.py`, `frontends/context.py`, `frontends/csharp/expressions.py`, `frontends/rust/expressions.py`; plus `go/declarations.py`'s `prev_value_node` and `java/declarations.py`'s `compact_body`, same concept under a different name).** Add one new sentinel, `NO_NODE`, following the exact shape of `NO_REGISTER`/`NO_LABEL`/`NO_SOURCE_LOCATION` — already siblings of `node` in the same signature at `_base.py:181`'s `_emit`. 3 of these 15 sites (`csharp/expressions.py` ×2, `java/declarations.py`'s `compact_body`) currently have **no type annotation at all** (`node=None`) — add it in the same edit.
- **`zoned_display_reg: Register | None = None`** (`lower_arithmetic.py`) → `NO_REGISTER` directly (already imported/used one file over in the COBOL lowering path).
- **`observer: FrontendObserver | None = None`** (`emit_context.py:101`) → `NullFrontendObserver()`, matching the already-correct pattern used one file over in `cobol_frontend.py:66` and in `compile_cobol`/`get_frontend`. Verified in passing: `EmitContext._observer` is assigned at construction but never read anywhere else in `emit_context.py`, and nothing outside the class reads it either (only `cobol_frontend.py:227` writes it in, forwarding its own already-non-`None` `self._observer`) — worth a one-line note in the fix commit that this may be dead state, but not in scope to remove here.
- **`literal_type: str | None = None`** (`ir.py:249`) — keep the empty-string default (`""`); do not retype to `TypeExpr = UNKNOWN`. Verified: this is a raw string tag (e.g. an ints/floats-style literal marker), a different concept from `instructions.py`'s `TypeExpr`-typed `return_type` field it was compared against — no retyping in scope here.
- **`type_env: TypeEnvironment | None = None`** (`handlers/calls.py:137`) — verified safe: body does `if type_env is None: type_env = TypeEnvironment(register_types=MappingProxyType({}), var_types=MappingProxyType({}))`, an empty-but-valid instance, never mutated afterward. Hoist directly into the signature default.
- **`type_env_builder: TypeEnvironmentBuilder | None = None`** (`linker.py:461`) — verified safe: `link_modules` only reads/forwards it (`type_env_builder=type_env_builder` when building the returned `LinkedProgram`), never mutates it in place. `TypeEnvironmentBuilder()` (all fields `default_factory`) is a valid zero-arg default.

**Moved out of bucket B after body verification — `symbol_table: SymbolTable | None = None` (`linker.py:462`):** the body does `symbol_table.classes.update(module.symbol_table.classes)` — an **in-place mutation**, the same class of risk as bucket D's `vm`/`initial_vm`. A literal `SymbolTable.empty()` default would share and mutate one instance across every caller that omits the argument. **Decision (confirmed with user): leave this one exactly as-is for now** — not fixed in this pass, not moved to bucket D either. It stays on red-dragon-nz4y, deferred alongside bucket E, until a future pass revisits it deliberately.

### Bucket C — needs a new no-op object, template exists one parameter away (6 sites)

- **`cics_text_parser` (5 sites: `cobol_frontend.py`, `frontend.py`, `cobol_compile.py` ×2, `cobol_connections.py`)** — typed as `Callable`. Verified: it flows into a `ContextVar[CicsTextParserFn | None]` whose own `default=None` is untouched by this fix (only the *constructor parameter's* default changes). `compile_cobol`'s own signature already has the right template: `source_transform: Callable[[str], str] = lambda s: s`. Fix: a no-op callable constant (`_NO_CICS_TEXT_PARSER`) that raises a clear error if ever actually invoked (a non-CICS program should never reach this code path) — a small improvement over `None` silently propagating until something calls it and gets a confusing `TypeError`.
- **`asg: CobolASG | None = None`** (`emit_context.py`) — verified safe: `emit_context.py:112` already does `self._asg = asg if asg is not None else _CobolASG()`, a genuine empty-but-valid zero-arg construction, never mutated via this parameter afterward. Hoist `CobolASG()` directly into the signature default.

**Moved out of bucket C after body verification:**
- **`cobol_parser: Any = None`** (`frontend.py`) and **`llm_client: Any = None`** (2 sites: `frontend.py`, `run.py`) — both turned out to be factory-construction fallbacks (`if cobol_parser is None: <build a real ProLeapCobolParser via subprocess + bridge JAR>`; `if llm_client is None: get_llm_client(provider=llm_provider)`), not no-op sentinels. **Decision (confirmed with user): deferred to a separate follow-up story, red-dragon-79iv** — properly fixing these means extracting per-language required-arg entry points out of the general-purpose `get_frontend`, which is real architectural work, not a mechanical default swap. Not touched by this epic at all.
- **`ctx: HandlerContext | None = None`** (`handlers/_common.py`) — verified: the body's `elif ctx is not None and isinstance(...): ctx.function_scoping.register_func(...)` uses `None` as a genuine "was a context explicitly given" control-flow signal, not an empty-struct stand-in; swapping in the existing `_default_handler_context()` factory would silently change behavior (the branch would always fire instead of being skippable). **Decision (confirmed with user): leave this one exactly as-is for now.** Stays on red-dragon-nz4y, deferred alongside bucket E.

### Bucket D — mutable/lifecycle state where the default itself is unsafe (5 sites, all `run.py`)

`execute_cfg`, `run_resumable`, `execute_cfg_traced` (`vm: VMState | None = None`), `run_linked_resumable`, `run_linked` (`initial_vm: VMState | None = None`).

**Decision (confirmed):** drop the default entirely — make `vm`/`initial_vm` required keyword arguments. `VMState` is genuinely mutated in place during execution; a literal default like `VMState()` would bind one shared instance reused across every call that omits the argument, including across the `ThreadPoolExecutor` usage elsewhere in this codebase — exactly the mutable-default-argument bug this cleanup exists to eliminate, reintroduced by a naive "use an empty structure" fix. Every existing call site that currently omits `vm`/`initial_vm` must be updated to pass `VMState()` explicitly.

Note: `ast_cache_dir` (see below) looks superficially similar — another "stateful resource" parameter — but is **not** in this bucket. Its correct fix is different enough (see Out of scope) that folding it in here would be wrong.

## Out of scope (deferred — bucket E, 18 sites)

Not touched in this pass; each needs individual semantic verification, and a mechanical fix risks a real correctness or ergonomics regression:

- **`project_root: str | Path | None = None`** (2×, `api.py:345,373`) — verified: `directory = Path(project_root) if project_root else entry_path.parent`. The true default is *derived from another parameter* (`entry_file`'s parent directory), not a static value. Python can't express a default that references a sibling parameter — `None`-as-sentinel, resolved in the body, is structurally the only mechanism available here, not an oversight.
- **`ast_cache_dir: Path | None = None`** (`cobol_compile.py:109`) — verified: `None` triggers "create and own a `TemporaryDirectory`, clean it up in `finally`"; a caller-supplied path is used and left alone. This is a genuine three-state lifecycle signal ("ephemeral, manage it for me" vs. "here's a real path"), not an absence-of-value. Dropping the default (bucket D's fix) would force every simple caller to manage `TemporaryDirectory` lifecycle themselves for no benefit — an ergonomics regression, not an improvement. Needs its own design pass, not a blind pattern match to bucket D.
- **`io_provider: Any = None`** (4×, `run.py`) — already carries a comment suggesting the choice is deliberate (`# avoids COBOL import in core VM — see red-dragon-r32l`), not an oversight.
- **`value: Any = None`** (`run.py:665,1103`) — the resumed-coroutine value; `None` may be genuine data (resuming with an actual `None`), not "absence." A blind empty-structure substitution would corrupt real values.
- **`finally_node` / `else_node: Any = None`** (2 sites, 4 params total: `_base.py:1261`, `frontends/common/exceptions.py:29`) — plausibly foldable into bucket B's `NO_NODE` sentinel, but every consumer's `is None` check needs auditing first, since these represent "this clause is genuinely absent in the source" — the fix touches more than the signature.
- **`text: str | None = None`** (2×, `frontends/common/expressions.py`), **`source: bytes | None = None`** (`compiler.py`) — `None` likely means "derive from the sibling `node`/`file_path` parameter instead," not "empty" — needs a body check before choosing `""`/`b""` vs. keeping the sentinel-driven branch.
- **`symbol_table: SymbolTable | None = None`** (`linker.py`) — mutated in place (`symbol_table.classes.update(...)`); confirmed with user to leave as-is for now (see bucket B).
- **`ctx: HandlerContext | None = None`** (`handlers/_common.py`) — `None` is a real control-flow signal, not an empty-struct stand-in; confirmed with user to leave as-is for now (see bucket C).

Beads issue red-dragon-nz4y stays open, scoped down to these 18 deferred sites, once buckets A–D close. Separately, **3 sites** (`cobol_parser`, `llm_client` ×2) move to a dedicated follow-up story, red-dragon-79iv — not part of red-dragon-nz4y's remaining scope at all.

## Testing strategy

Every touched signature is used across the frontend and project-compilation layers — these are behavior-relevant changes (new required args, changed defaults, deleted dead fallback code), not pure refactors. Per project convention, each fix needs its own test:

- Bucket A/B: existing tests exercising these call paths should keep passing unchanged (the callee always effectively saw `[]`/`{}`/the sentinel via the `or` fallback anyway) — add one direct unit test per changed function confirming the omitted-argument call path still produces the same behavior, now enforced by the signature rather than a body-level `or`.
- Bucket C: new test for `_NO_CICS_TEXT_PARSER`'s actual behavior when invoked (should raise clearly, not silently misbehave), plus a test confirming `asg`'s omitted-argument path still produces an equivalent empty `CobolASG()`.
- Bucket D: this is the one bucket with a real call-site migration — every existing caller of `execute_cfg`/`run_resumable`/`execute_cfg_traced`/`run_linked_resumable`/`run_linked` that omits `vm`/`initial_vm` needs updating to pass `VMState()` explicitly. The full test suite is the regression gate here, since these functions are exercised extremely broadly across `tests/integration/`.

Run `poetry run python -m pytest` (full suite) after each bucket, not just at the end — bucket D especially should land as its own commit/verification step given its call-site blast radius.

## Sequencing

A → B → C → D: progressively higher-effort, and D requires the widest call-site migration (now that the design decision is made). Bucket E stays queued on red-dragon-nz4y, deferred, not touched by this work. `cobol_parser`/`llm_client` are entirely out of this epic, tracked separately on red-dragon-79iv.
