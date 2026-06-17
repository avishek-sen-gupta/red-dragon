# Scope-Stack Type-Inference Design (red-dragon-b4j6)

**Status:** Implemented function-scope only (2026-06-18) on branch `scope-stack-inference`,
commit `a469a6e4`. The scope stack drives `current_func_label` — fixing branched-return
orphaning and cross-function variable bleed across all 15 frontends (the reported bug).
**Class unification was NOT shipped:** Java/C#/Scala emit methods *flattened after*
`end_class` (empty class body), and the old `current_class_name` "bleed" (set on class
entry, never reset) is the load-bearing mechanism that attributes those flattened methods
to their class. Popping a class frame at `end_class` breaks them. So `current_class_name`
was kept as its original bled field; class-attribution behaviour is unchanged from main.
The class-scope bug (bleed onto a top-level function following a class; reliance on
positional flattening) is deferred to a separate follow-up — the principled fix is to
normalize the 3 frontends' IR so methods nest inside the class label range. The §Components
"§1 current_class_name property" and the class push/pop-for-attribution parts of this design
are therefore superseded by "keep current_class_name as a bled field"; the function-scope
parts shipped as designed.

**Problem:** Type inference tracks the current scope with two single mutable pointers,
`current_func_label` and `current_class_name`, on `_InferenceContext`
(`interpreter/types/type_inference.py`). `_infer_label` sets `current_func_label`
only on a function-entry label and **blanks it to `""` on every other label**, including
intra-body control-flow labels (`for_end`, `if_*`, `loop_end`, …). It is never
restored. `current_class_name` is set on a class-entry label and **never reset** at
the class end. Both are "a single pointer that should be a stack."

**Consequences (both verified empirically on `main`):**
1. **Return types dropped.** Once any control-flow label appears in a function body,
   `current_func_label` is `""` for the rest of the body, so `_infer_return` bails at its
   first guard. Functions with branched/multiple returns infer **no** return type. Example:
   `def a(c):\n if c: return 1\n return 0` → return type empty.
2. **Variable mis-scoping / cross-function bleed.** `current_func_label` is the *scope key*
   for `store_var_type`/`lookup_var_type`. Blanked to `""`, locals declared inside a
   control-flow block are filed under the **global** scope. Two unrelated locals named `v`
   in different functions merge into one `Union[Int, String]`. (Masked in lookups because
   `lookup_var_type` falls back to the global scope and `flat_var_types()` unions across
   scopes — but it is still incorrect cross-contamination.)
3. **Class context bleed.** `current_class_name` persists past `end_class`, so code after a
   class can be mis-attributed to that class.

**Goal:** Replace both single pointers with a single **scope stack** that pushes on
function/class entry and pops on the matching end, leaving control-flow labels alone —
fixing return-type orphaning, variable mis-scoping, and class bleed in one coherent
mechanism. Correct for nested functions, closures, methods, and nested classes.

This completes the return-type half of the union-based nullability model
(red-dragon-x78r), which deliberately deferred this fix.

---

## Key enabling fact (verified)

Function and class **entry/end** labels use the `end_`/`func_`/`class_` **prefix**
convention, while **all** control-flow labels use a `_end` **suffix** (`for_end`,
`loop_end`, `try_end`, `switch_end`, `while_end`, `case_end`, `block_end`, …) or other
non-`end_` names. So the existing `CodeLabel` predicates reliably bracket real scopes:
- `is_function()` — function entry (`func_*`, possibly namespaced).
- `is_class()` — class entry (`class_*`/`prelude_class_*`; already excludes end-class).
- `is_end_class()` — class end (`end_class_*`/`prelude_end_class_*`).
- `is_end_label()` — starts with `end_` (function ends AND class ends).
  → A **function** end is `is_end_label() and not is_end_class()`.

A full scan of `fresh_label(...)` literals across all frontends confirmed every
`end_`-prefixed label is a function/method/getter/setter/anon/init/class end; no
control-flow label starts with `end_`.

Lambdas/closures emit `func_*` + `end_*` labels **inline and nested** within the
enclosing function body (`Branch(end); Label(func_…); …; Label(end_…)`), so a stack is
required to restore the parent scope after a nested function ends. The inference walk is
linear (it processes every instruction in order, not following branches), so it encounters
these labels in properly nested order.

---

## Components

### 1. Data model (`_InferenceContext`)

Add module-level frame-kind constants and a stack field:
```python
_FUNC_FRAME = "func"
_CLASS_FRAME = "class"
# in _InferenceContext:
scope_stack: list[tuple[str, object]] = field(default_factory=list)
# frame = (_FUNC_FRAME, func_label_str) | (_CLASS_FRAME, class_TypeExpr)
```

`current_func_label` and `current_class_name` change from **stored fields** to
**computed read-only properties** (single source of truth = `scope_stack`):
- `current_func_label` → the label of the top frame **if it is a FUNC frame**, else `""`.
- `current_class_name` → the payload of the **nearest CLASS frame from the top**, else
  `UNKNOWN`.

Rationale for "nearest class": a method body has `[CLASS(C), FUNC(m)]` — its own FUNC
frame is on top, but it must still resolve its enclosing class `C` for method-type
attribution. "Top frame if FUNC else ''" for `current_func_label` reproduces today's
"class body is not a function scope" semantics (`[CLASS(C)]` → `current_func_label == ""`).

These properties replace the existing fields; no other code writes them (only `_infer_label`
did, and it now manages the stack instead). All readers — `store_var_type`/`lookup_var_type`,
`_infer_symbolic` (param collection), `_infer_const` (class-method attribution),
`_infer_return` — are unchanged; they read the properties.

### 2. `_infer_label` rewrite
```python
def _infer_label(inst, ctx, type_resolver):
    if not inst.label.is_present():
        return
    if inst.label.is_function():
        ctx.scope_stack.append((_FUNC_FRAME, str(inst.label)))
        ctx.func_param_types.setdefault(str(inst.label), [])
    elif inst.label.is_class():
        cls = scalar(TypeName(inst.label.extract_name(constants.CLASS_LABEL_PREFIX)))
        ctx.scope_stack.append((_CLASS_FRAME, cls))
        ctx.class_method_types.setdefault(cls, {})
    elif inst.label.is_end_class():
        _pop_frame(ctx, _CLASS_FRAME)
    elif inst.label.is_end_label():        # end_ prefix but not end_class → function end
        _pop_frame(ctx, _FUNC_FRAME)
    # any other label (control-flow): no scope change
```
Note on class-name extraction: the current code extracts with `CLASS_LABEL_PREFIX`
(`"class_"`). Prelude classes use `prelude_class_`. The implementation must extract the
class name correctly for both prelude and namespaced class labels — match whatever
`extract_name` + the current `_infer_label` already produce for `current_class_name`
(preserve existing class-name values exactly; this design does not change how class names
are spelled, only when they are pushed/popped).

### 3. Pop helper (strong-assertion, not defensive)
Well-formed IR guarantees balanced, properly nested entry/end labels, so the matching top
frame is an **invariant**, not a possibility to defend against. The helper *asserts* the
invariant and fails loud if violated — no silent no-op:
```python
def _pop_frame(ctx, kind: str) -> None:
    assert ctx.scope_stack, f"scope-stack underflow: end label with no open {kind} frame"
    top_kind, _ = ctx.scope_stack[-1]
    assert top_kind == kind, (
        f"scope-stack imbalance: end label expected top {kind} frame, got {top_kind}"
    )
    ctx.scope_stack.pop()
```
These are strong structural assertions (they verify the entry/end nesting invariant), not
vacuous ones. If a frontend ever emits unbalanced labels, this surfaces it immediately at
the root cause rather than masking it.

### 4. Per-pass reset
`infer_types` runs a fixpoint that re-walks the entire instruction list each pass. Add
`ctx.scope_stack.clear()` at the **top of each pass**, immediately before the
`for inst in instructions:` loop. Balanced labels leave the stack empty at pass end anyway,
but the explicit reset guarantees pushes never accumulate across passes.

---

## Data flow

Top-level/entry code (before any function label) runs with an empty stack →
`current_func_label == ""` (global scope), `current_class_name == UNKNOWN` — unchanged from
today. As the walk enters and leaves functions/classes, the stack tracks the exact
innermost scope, so every `STORE_VAR`/`DECL_VAR` (variable scoping), `SYMBOLIC` (param
collection), `CONST`-funcref (method attribution), and `RETURN` (return-type union) is
attributed to the correct function/class for the entire body — including after control-flow
labels and after nested closures.

## Error handling
- Malformed/unbalanced labels are an invariant violation, not an expected condition:
  `_pop_frame` asserts and fails loud (see §3) — no defensive recovery.
- Empty stack reads from the computed properties are a normal state (top-level/global code),
  not an error: `current_func_label` returns `""` and `current_class_name` returns `UNKNOWN`.

## Implementation principles (binding on the plan)

- **TDD.** Every behavioural change is driven by a failing test first (red → green). The
  test matrix below is the starting set; add a failing test before each implementation step.
- **FP / no hidden state.** Frames are immutable tuples. `current_func_label` /
  `current_class_name` are *pure computed properties* over `scope_stack` — single source of
  truth, no shadow fields, no setter side effects. Helpers (`_pop_frame`, property bodies)
  are pure functions of their inputs. The fixpoint walk remains the existing imperative
  shell; new logic stays pure within it.
- **No defensive programming.** Do not add guards for conditions that well-formed IR makes
  impossible (e.g. silently tolerating an unbalanced stack). Assert the invariant and fail
  loud instead.
- **No `None` in signatures.** New functions/properties take and return concrete types — no
  `Optional`/`| None` parameters or returns. (The global/top-level scope is the empty string
  `""` and `UNKNOWN`, never `None`.)
- **No default parameters.** New helper functions take all arguments explicitly. (The one
  permitted default is the dataclass field initializer `scope_stack: list[...] =
  field(default_factory=list)`, which is the field's initial value, not a function default.)
- **Strong assertions only — no vacuous ones.** Assertions must verify a real invariant
  (e.g. the entry/end nesting in `_pop_frame`, or that a specific function infers a specific
  `Union[...]`). No `assert x is not None`-style placeholders, no asserting a value equals
  itself, no asserting only that "something" was produced when the exact expected value is
  knowable. Tests assert the precise inferred type, not merely that a type exists.

## Testing

New tests in `tests/integration/test_type_inference.py` (use the existing
`_lower_and_infer` helper) unless noted:
1. **Branched return → Union:** `def f(c):\n    if c:\n        return 1\n    return 'x'`
   → `str(return_type) == "Union[Int, String]"`.
2. **Branched value + null → Union[T, Null]:** `def f(c):\n    if c:\n        return 42\n    return None`
   → `str(return_type) == "Union[Int, Null]"`.
3. **No cross-function variable bleed:** two functions, each with a local `v` of a different
   type assigned inside an `if`; assert each function's `v` is its own scalar type
   (scoped via `env.scoped_var_types`), not one merged `Union[Int, String]`.
4. **Nested closure restores parent scope:** a function containing a lambda in the middle,
   then `return <int>` after the lambda → the outer function still infers `Int` (the
   closure's `end_` label must pop back to the parent frame).
5. **Method sees enclosing class (regression guard):** an existing class-method
   type-attribution test continues to pass (method return/param types attributed to the
   class).
6. **Class scope does not bleed:** a class with a method followed by a top-level function;
   the top-level function is not attributed to the class (`current_class_name` popped at
   `end_class`).

Plus: the **full suite** must stay green after absorbing the (expected, correct) churn in
the two type-inference test files. Any failure outside type inference — especially
execution/VM/CICS/CardDemo — is a real regression (scope tracking must not affect runtime)
and must be investigated, not papered over.

## Out of scope
- COBOL: COBOL paragraphs/sections do not use the tree-sitter `func_`/`end_` function
  convention the same way; this design targets the 15 tree-sitter frontends' inference.
  The implementation must confirm the COBOL inference path is unaffected (its tests stay
  green) but does not add COBOL scope-stack behaviour. **Because `_pop_frame` now asserts
  balanced labels (no defensive no-op), this must be checked early**: if COBOL (or any
  frontend) emits `func_`/`end_` or `class_`/`end_class_` labels that are not balanced and
  properly nested in the inference walk, the assertion will fire. That is the correct
  fail-loud behaviour; the fix is to correct the offending label emission, not to soften the
  assertion. The first implementation step after wiring the stack is a full-suite run to
  surface any such imbalance immediately.
- No change to runtime/VM, frontends, or the `TypeExpr` ADT. Pure inference-pass change.
