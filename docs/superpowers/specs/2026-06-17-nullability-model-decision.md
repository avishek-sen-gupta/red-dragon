# Nullability Model — Decision Memo (red-dragon-x78r)

**Status:** Decided (2026-06-17). Decision memo only — no implementation in this spike.
**Driver:** Semantic cleanliness — the type system should not carry dead or
ambiguous nullability machinery, and the type of a variable assigned `null`
must be *retained*, not lost.

---

## TL;DR

- **Decision: Model A — null is an ordinary scalar; "nullable T" is the general
  `Union[T, Null]`.** No dedicated `Option`/`Maybe` ADT is added to the type
  system. `Option` stays what it already is in RedDragon: a *runtime library
  object* for source languages that have it (Rust today; Scala/Swift later) — a
  value-level construct, never the IR's universal nullability model.
- **Next step (recommended): remove the inference shim** that maps the `null`
  literal to `UNKNOWN`, so inferred variables become `Union[T, Null]` while
  annotated variables keep their declared type. This is the cleanest state and
  needs **zero new machinery** — the widening logic already exists.
- **Measured cost:** exactly **10 test failures** (out of 14233), all in
  `tests/integration/test_type_inference.py`, all about dynamic-language
  function return-type/signature inference now (correctly) reporting nullable
  returns. No production-code changes required; only test-expectation updates.
- **Option-style (the model the issue named) is rejected** — it is the one
  model that *risks losing the variable's type*, mismatches 14/15 source
  languages, and would require a hard cutover with large blast radius.

---

## The question that drove the decision

> When `null` is assigned to a variable that has a type, is the type retained or
> lost?

**Answer: retained — never lost — in every case.** This was verified empirically
against the live inference engine (`interpreter/api.py::lower_and_infer`), with
and without the current shim:

| Scenario | Today (shim on) | Shim removed (clean state) |
|---|---|---|
| Python `x='hi'; x=None` (inferred) | `String` | **`Union[Null, String]`** |
| Python `x=None; x='hi'` (inferred) | `String` | **`Union[Null, String]`** |
| Java `String s = null` (annotated) | `String` | `String` |
| Java `String s="hi"; s=null` (annotated) | `String` | `String` |

The guarantee comes from `store_var_type` (`interpreter/types/type_inference.py:220`):

1. **Seeded (annotated) variables — declared type wins.** Names in
   `_seeded_var_names` (populated from source annotations at the frontend
   seeding boundary) are *never widened*. A Java `String s = null` stays `String`.
2. **Inferred variables — widen, never overwrite.** When a variable already has
   a type and a different one is assigned, `store_var_type` computes
   `union_of(existing, new)`. The prior type is preserved inside the union.

So the variable's type is structurally safe regardless of model. The only real
variable is whether nullability is *visible*.

---

## Current state: union-based nullability is vestigial

Before deciding, the existing "union-based" machinery was audited. It is largely
dead:

- `optional()` in `type_expr.py` is **only** reached by `parse_type()` when it
  parses an `"Optional[...]"` annotation string. No frontend constructs it
  directly. (It is live but narrow — keep it.)
- `is_optional()` / `unwrap_optional()` have **no production consumers** (only
  unit tests in `tests/unit/test_type_expr.py`). They are dead.
- Coercion (`interpreter/types/coercion/`) does **not** special-case `Null` or
  optionals.
- The `null` literal infers as `UNKNOWN` via a deliberate shim
  (`type_inference.py:604`, tagged `red-dragon-x78r`), so today the type system
  never even sees a `Null`.
- Runtime `None` maps to `UNKNOWN` (`typed_value.py`).

We were therefore **not** choosing between two working models. We were deciding
whether to make nullability a first-class, *visible* part of the type system,
and in what shape.

---

## Models considered

### Model A — null-as-scalar, nullability via the general union (CHOSEN)

`Null` is an ordinary `ScalarType` (already true after red-dragon-v0l2).
"Nullable T" is `Union[T, Null]`, produced by the *same* union-join that merges
any heterogeneous branches. No dedicated nullability node exists.

- **Pro:** Maximum cleanliness — there is no special construct to misuse or let
  rot. Matches 14/15 source languages, which model null as a bare value. Zero
  new `TypeExpr` nodes. Fully incremental. Retains the underlying type by
  construction (widening + seeded precedence, both already implemented).
- **Con:** No *enforcement* of unwrapping. That is an analysis feature, not a
  representation choice — and null-safety analysis is explicitly **not** the
  driver here. If wanted later, `is_optional`/`unwrap_optional` (or fresh
  helpers) can be reintroduced as the sanctioned consumer API over `UnionType`.

### Model B — option-style sum type (`Option[T]`, no bare null) — REJECTED

The Rust/Haskell/ML/Swift model named in the issue.

- **Pro:** Forces explicit handling; elegant in isolation.
- **Con:** Severe mismatch with RedDragon's reality.
  - 14/15 frontends lower a bare `null`/`nil`/`None` *value*; only Rust uses
    `Option` natively. Adopting Option-style means rewriting every frontend's
    null literal into `Some`/`None` constructors.
  - The VM's runtime representation would have to change so every `None` becomes
    a wrapper object — breaking equality, coercion, field access, and the
    symbolic engine.
  - It is a **hard cutover** with large blast radius that *fights* source
    semantics (a Java `String s = null` is genuinely a bare null, not
    `None : Option[String]`).
  - **It is the model that risks "losing" the variable's type** — the value's
    shape changes to `Option[?]`, and the bare `String` no longer flows through
    unchanged. This is the exact failure mode the driver wants to avoid.
  - RedDragon already has the *right* home for Option: a runtime prelude object
    (`interpreter/frontends/rust/declarations.py` registers `Option`/`Box` with
    `match_args`). Source-level `Option` is a value-level library type, not a
    type-system nullability model.

### Model C — wire up the union helpers into a real, enforced feature — DEFERRED

Make union-nullability a fully-tracked, analysis-enforced feature (Python
`Optional`, TS `T | null`).

- **Con:** This is the null-safety-analysis project, which is not the driver. It
  is a superset of "remove the shim"; it can be pursued later on top of Model A
  if null-safety analysis becomes a goal.

---

## Recommended next step (separate ticket, not this spike)

Remove the `null`→`UNKNOWN` inference shim at `type_inference.py:604–605` so the
typed `Null` literal flows into inference. Result:

- Inferred variables that are ever assigned `null` become `Union[…, Null]`
  (type retained, nullability now visible).
- Annotated variables keep their exact declared type (seeded precedence).
- Functions with implicit / fall-through `return` infer a `Union[…, Null]`
  return type — which is *correct* (they really can return null).

**Blast radius (measured by disabling the shim and running the full suite):**
**10 failing tests**, all in `tests/integration/test_type_inference.py`, all
asserting dynamic-language (Lua, JavaScript) function return-type / signature
inference under the old "implicit return → no/UNKNOWN type" assumption. These
are test-expectation updates, not production fixes. The remaining 14223 tests
pass unchanged.

Optional cleanup to bundle with that work (pure dead-code removal, serves the
cleanliness driver):

- Delete `is_optional()` and `unwrap_optional()` from `type_expr.py` and their
  unit tests (no production consumers). Keep `optional()` (used by
  `parse_type` for `Optional[...]` annotations).

If/when null-safety analysis is later desired (a future, separate driver),
reintroduce a consumer API over `UnionType` and build the dataflow check on top
of Model A — no representational change needed.

---

## What this memo does NOT do

- No code changes (decision memo only).
- Does not commit to building null-safety analysis.
- Does not change runtime `None` handling.

The shim removal + dead-helper cleanup should be filed as a small follow-up
implementation ticket under this decision.
