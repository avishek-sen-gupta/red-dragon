# Scope-Stack Type-Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two single mutable scope pointers (`current_func_label`, `current_class_name`) in the type-inference pass with one scope **stack** that pushes on function/class entry and pops on the matching end, so branched-return functions infer return types, variables stop bleeding across functions, and class context stops bleeding past `end_class`.

**Architecture:** In `interpreter/types/type_inference.py`, add `scope_stack: list[tuple[str, object]]` to `_InferenceContext`; make `current_func_label`/`current_class_name` pure computed **properties** over that stack; rewrite `_infer_label` to push on `is_function()`/`is_class()` and pop (via an asserting `_pop_frame`) on `is_end_class()`/`is_end_label()`, leaving control-flow labels untouched; reset the stack at the top of each fixpoint pass. Pure inference change — no VM/frontend/TypeExpr changes.

**Tech Stack:** Python 3.13, pytest (`poetry run python -m pytest`), black, `TypeExpr` ADT.

**Spec:** `docs/superpowers/specs/2026-06-18-scope-stack-inference-design.md`.

**Implementation principles (binding — from the spec):**
- **TDD** — failing test first, every step.
- **FP / no hidden state** — frames are immutable tuples; `current_func_label`/`current_class_name` are pure computed properties over `scope_stack` (no shadow fields, no setters).
- **No defensive programming** — assert invariants and fail loud; do not add guards for IR states that well-formed input makes impossible.
- **No `None` in signatures** — global scope is `""` / `UNKNOWN`, never `None`.
- **No default parameters** — explicit args on new helpers (the one allowed default is the dataclass `field(default_factory=list)`).
- **Strong assertions only** — tests assert the *exact* inferred type, never "a type exists."

**Global conventions for every task:**
- Set env first: `export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"`.
- Run tests with `poetry run python -m pytest`; format with `poetry run python -m black` (note the `-m`).
- Commit through the **real** pre-commit hooks (no `--no-verify`); the hook runs black, lint, pyright-warn, import-linter, and the full suite (incl. CardDemo CICS e2e). Export `PROLEAP_BRIDGE_JAR` in the **same** command as `git commit`, and verify the commit landed (`git log --oneline -1`).
- `@covers(NotLanguageFeature.INFRASTRUCTURE)` on every new inference test method.
- Work on a feature branch (NOT `main`). Create it in Task 1 step 0.

**Baseline:** `main` is green at 14249 passed, 66 skipped, 15 xfailed (after the nullability merge). The pre-existing untracked file `docs/superpowers/plans/2026-06-13-perform-varying-after.md` must remain untracked — never `git add -A`; stage specific files.

---

### Task 1: Scope-stack mechanism (atomic) + regression tests + churn absorption

**Files:**
- Modify: `interpreter/types/type_inference.py`
  - frame constants near `_GLOBAL_SCOPE` (~line 175)
  - `_InferenceContext` fields (~lines 188-189) + new properties
  - `store_var_type`/`lookup_var_type` are UNCHANGED (they read the property)
  - new module-level `_pop_frame` (near `_infer_label`)
  - `_infer_label` rewrite (~lines 490-507)
  - fixpoint loop per-pass reset (~lines 423-427)
- Test: `tests/integration/test_type_inference.py` (new `TestScopeStackInference` class)

> This task is intentionally atomic: the stack, the properties, and the `_infer_label` rewrite are mutually dependent and cannot be committed half-applied (the dataclass would have neither the fields nor working properties). TDD is driven by the first regression test; the full mechanism is implemented to make it pass, then the remaining matrix tests are added and the suite churn is absorbed — all in one commit.

- [ ] **Step 0: Branch**

```bash
cd /Users/asgupta/code/red-dragon
git checkout main && git pull --ff-only
git checkout -b scope-stack-inference
```

- [ ] **Step 1: Write the first failing test (branched return → Union)**

Add to `tests/integration/test_type_inference.py`. First confirm the file already imports `FuncName`, `FoundationTypeName`, `VarName`, `NotLanguageFeature`/`covers`, and the `_lower_and_infer` helper (they are used by existing classes there — reuse, do not redefine). Add:

```python
class TestScopeStackInference:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_branched_return_unions(self):
        src = "def f(c):\n    if c:\n        return 1\n    return 'x'\n"
        _i, env = _lower_and_infer(src, "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert str(rt) == "Union[Int, String]"
```

- [ ] **Step 2: Run it — verify it fails**

```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m pytest "tests/integration/test_type_inference.py::TestScopeStackInference::test_branched_return_unions" -v
```
Expected: FAIL — emits `''` (UnknownType): the branched function is orphaned today because `_infer_label` clears `current_func_label` on the `if` control-flow labels.

- [ ] **Step 3: Add frame constants**

In `interpreter/types/type_inference.py`, near `_GLOBAL_SCOPE = ""` (~line 175), add:

```python
_FUNC_FRAME = "func"
_CLASS_FRAME = "class"
```

- [ ] **Step 4: Replace the two pointer fields with a stack field**

In `_InferenceContext`, DELETE these two field lines (~188-189):

```python
    current_func_label: str = ""
    current_class_name: TypeExpr = UNKNOWN
```

and add a stack field in their place:

```python
    scope_stack: list[tuple[str, object]] = field(default_factory=list)
    # frame = (_FUNC_FRAME, func_label: str) | (_CLASS_FRAME, class_type: TypeExpr)
```

- [ ] **Step 5: Add the computed properties**

Inside `_InferenceContext`, add these two properties (place them just above `lookup_func_return_type`, ~line 213):

```python
    @property
    def current_func_label(self) -> str:
        """Label of the innermost enclosing function, or "" at top level / inside a
        class body. Pure view over scope_stack."""
        if self.scope_stack and self.scope_stack[-1][0] == _FUNC_FRAME:
            return str(self.scope_stack[-1][1])
        return ""

    @property
    def current_class_name(self) -> TypeExpr:
        """TypeExpr of the nearest enclosing class (searching outward from the top),
        or UNKNOWN if not inside a class. Lets a method body still resolve its class
        while its own FUNC frame is on top."""
        for kind, payload in reversed(self.scope_stack):
            if kind == _CLASS_FRAME:
                assert isinstance(payload, TypeExpr)
                return payload
        return UNKNOWN
```

(`store_var_type`/`lookup_var_type` and all other readers already use `self.current_func_label`/`self.current_class_name`; they now transparently read these properties — do NOT change them.)

- [ ] **Step 6: Add the asserting pop helper**

As a module-level function immediately above `def _infer_label(` (~line 483):

```python
def _pop_frame(ctx: _InferenceContext, kind: str) -> None:
    """Pop the top scope frame, asserting it is the expected kind.

    Well-formed IR has balanced, properly nested entry/end labels, so the matching
    top frame is an invariant. Fail loud on violation rather than defending against it.
    """
    assert ctx.scope_stack, f"scope-stack underflow: end label with no open {kind} frame"
    top_kind = ctx.scope_stack[-1][0]
    assert top_kind == kind, (
        f"scope-stack imbalance: end label expected top {kind} frame, got {top_kind}"
    )
    ctx.scope_stack.pop()
```

- [ ] **Step 7: Rewrite `_infer_label`**

Replace the current body (the `if is_function() … elif class … else current_func_label=""` block, ~lines 488-507) with:

```python
def _infer_label(
    inst: Label_,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
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
    elif inst.label.is_end_label():  # end_ prefix but not end_class → function end
        _pop_frame(ctx, _FUNC_FRAME)
    # any other label (control-flow: for_end, if_*, loop_end, …) → no scope change
```

Order matters: `is_end_class()` is checked before `is_end_label()` because `is_end_label()` is true for `end_class_*` too. The class-name extraction uses `constants.CLASS_LABEL_PREFIX` exactly as the previous code did — class-name spelling is unchanged, only push/pop timing changes.

- [ ] **Step 8: Reset the stack at the top of each fixpoint pass**

In `infer_types`, the fixpoint loop (~lines 423-427) is:

```python
    while current_size > prev_size:
        prev_size = current_size
        for inst in instructions:
            _infer_instruction(inst, ctx, type_resolver)
        current_size = len(ctx.register_types) + len(ctx.func_return_types)
        passes += 1
```

Add `ctx.scope_stack.clear()` as the first statement inside the loop body:

```python
    while current_size > prev_size:
        prev_size = current_size
        ctx.scope_stack.clear()
        for inst in instructions:
            _infer_instruction(inst, ctx, type_resolver)
        current_size = len(ctx.register_types) + len(ctx.func_return_types)
        passes += 1
```

- [ ] **Step 9: Run the first test — verify it passes**

```bash
poetry run python -m pytest "tests/integration/test_type_inference.py::TestScopeStackInference::test_branched_return_unions" -v
```
Expected: PASS (`Union[Int, String]`).

- [ ] **Step 10: Add the rest of the regression matrix**

Append to `TestScopeStackInference` (run each after adding; adjust an EXPECTED string only if the engine emits a differently-but-correctly-ordered union — never to hide a wrong value):

```python
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_branched_value_and_null_unions(self):
        src = "def f(c):\n    if c:\n        return 42\n    return None\n"
        _i, env = _lower_and_infer(src, "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert str(rt) == "Union[Int, Null]"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_cross_function_var_bleed(self):
        # Two functions, each a local `v` of a different type assigned inside an if.
        src = (
            "def a(c):\n    if c:\n        v = 5\n    return 0\n\n"
            "def b(c):\n    if c:\n        v = 'hi'\n    return 1\n"
        )
        _i, env = _lower_and_infer(src, "python")
        # Each function's `v` is scoped to that function — not merged into one global Union.
        a_scope = next(s for s in env.scoped_var_types if "func_a" in s)
        b_scope = next(s for s in env.scoped_var_types if "func_b" in s)
        assert env.scoped_var_types[a_scope][VarName("v")] == FoundationTypeName.INT
        assert env.scoped_var_types[b_scope][VarName("v")] == FoundationTypeName.STRING

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_closure_restores_parent_scope(self):
        # A lambda in the middle of f, then a return after it → f still infers Int
        # (the lambda's end_ label must pop back to f's frame).
        src = "def f():\n    g = lambda x: x\n    return 7\n"
        _i, env = _lower_and_infer(src, "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert rt == FoundationTypeName.INT
```

`env.scoped_var_types` is a confirmed attribute on `TypeEnvironment` (`MappingProxyType[str, MappingProxyType[VarName, TypeExpr]]`); its keys are function-label strings like `'func_a_0'`, `'func_b_0'`, and `''` for global. The `next(...)` selectors above match `'func_a'`/`'func_b'` substrings and will resolve. This test MUST assert per-function scoping via `scoped_var_types` (NOT `env.var_types`, which flattens scopes and would hide the bug).

- [ ] **Step 11: Class-scope regression guards**

Confirm existing class/method inference still holds and class context does not bleed. Add:

```python
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_class_method_attributed_to_class(self):
        src = (
            "class C:\n    def m(self):\n        return 5\n\n"
            "def top():\n    return 'x'\n"
        )
        _i, env = _lower_and_infer(src, "python")
        # top() is a standalone function, NOT a method of C (class scope popped at end_class).
        assert str(env.get_func_signature(FuncName("top")).return_type) == "String"
```
If method-signature lookup for `m` has a dedicated accessor used by existing class tests in this file, add an assertion that `C.m` is recorded under class `C` using that same accessor (read the existing class-method tests to copy the exact API). Keep assertions exact.

- [ ] **Step 12: Run the new class + full suite; absorb churn**

```bash
poetry run python -m pytest tests/integration/test_type_inference.py tests/unit/test_type_inference.py -v
poetry run python -m pytest -q -m 'not external and not nist'
```
Expect failures in the **type-inference test files** only — assertions encoding the OLD (incorrect) behavior:
- branched-return functions that previously inferred nothing now infer a type/`Union`;
- functions/vars that previously bled to global scope now scope correctly;
- class context no longer bleeding may change a few method-attribution expectations.

For each failure: run with `-v`, read the emitted value, and update the expectation to the new **semantically-correct** value (exact type — no weakening, no `assert exists`). 

**Guardrail (do not violate):** a failure OUTSIDE the type-inference test files — especially execution/VM, CICS/CardDemo, interprocedural/dataflow — is NOT an expectation update. Scope-tracking must not change runtime behavior, and `_pop_frame` asserting means an unbalanced-label crash is possible. If any such failure or any `AssertionError` from `_pop_frame` appears, STOP and report it with the failing test and traceback — it signals either an unbalanced-label emission (fix the root label emission, do not soften the assert) or a real scoping regression to investigate. Do not paper over it.

Iterate until the full suite is green.

- [ ] **Step 13: Format + commit (real hooks, specific files)**

```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m black interpreter/types/type_inference.py tests/integration/test_type_inference.py tests/unit/test_type_inference.py
git add interpreter/types/type_inference.py tests/integration/test_type_inference.py tests/unit/test_type_inference.py
git commit -m "fix(inference): scope stack replaces single func/class pointers; branched returns + var scoping correct (red-dragon-b4j6)"
git log --oneline -1
```

---

### Task 2: Final verification + close-out

**Files:**
- Modify: `docs/superpowers/specs/2026-06-18-scope-stack-inference-design.md` (status line)

- [ ] **Step 1: Confirm the old pointers are fully gone**

```bash
grep -n "current_func_label\s*=\|current_class_name\s*=" interpreter/types/type_inference.py
```
Expected: NO assignment lines (both are now read-only properties; only `scope_stack` is mutated). The only matches should be inside the property definitions / reads.

- [ ] **Step 2: Full suite, final**

```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
poetry run python -m pytest -q -m 'not external and not nist'
```
Expected: fully green.

- [ ] **Step 3: Update spec status** in `docs/superpowers/specs/2026-06-18-scope-stack-inference-design.md` from `Designed (2026-06-18). Awaiting spec review → implementation plan.` to `Implemented (<date>) on branch scope-stack-inference.` Commit it (`git add <that file>; git commit -m "docs: mark scope-stack design implemented (red-dragon-b4j6)"`).

- [ ] **Step 4: Merge to main** (controller does this via finishing-a-development-branch): no-ff merge `scope-stack-inference` into `main`, push.

- [ ] **Step 5: Close `red-dragon-b4j6`** with a summary: final test counts, that branched-return functions now infer return types (incl. `Union[T, Null]`), variable cross-function bleed fixed, class bleed fixed, and that this completes the return-type half of red-dragon-x78r's nullability model.
