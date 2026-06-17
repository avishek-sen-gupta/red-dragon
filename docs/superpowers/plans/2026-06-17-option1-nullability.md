# Option-A Nullability (visible Union[T, Null]) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `null`→`UNKNOWN` inference shim so nullability is visible as `Union[T, Null]`, and make function return-type inference union all *explicit* returns while ignoring the *synthetic* fall-off-the-end return.

**Architecture:** Mark the synthetic trailing return that every frontend appends to a function/method/constructor/lambda body with a new `Return_.implicit=True` flag (done via a shared `emit_implicit_return` helper). Then change `_infer_return` to (a) skip `implicit` returns and (b) union the value-types of explicit returns instead of first-writer-wins. Finally delete the shim in `_infer_const` and the dead `is_optional`/`unwrap_optional` helpers. Decision memo: `docs/superpowers/specs/2026-06-17-nullability-model-decision.md`.

**Tech Stack:** Python 3.13, pytest (`poetry run python -m pytest`), black, tree-sitter frontends, `TypeExpr` ADT.

**Staging (each phase ends green):**
- Phase 1 (Tasks 1–3): add `implicit` field + `emit_implicit_return` helper, then mark every synthetic trailing return. Behavior-preserving (nothing reads the flag yet; shim still on). Suite stays green throughout.
- Phase 2 (Task 4): change `_infer_return` to skip-implicit + union-explicit. Shim still on, so null returns are still UNKNOWN; only multi-type non-null returns change. Update any resulting failures.
- Phase 3 (Task 5): remove the shim. Null becomes visible → variables and explicit-null returns become `Union[…, Null]`. Update all resulting inference-test expectations.
- Phase 4 (Task 6): delete dead helpers + their tests.

**Global conventions for every task:**
- Set the env first: `export PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"`.
- Run tests with `poetry run python -m pytest` (NOT `poetry run pytest`).
- Before each commit: `poetry run python -m black <changed files>`.
- Commit through the real pre-commit hooks (no `--no-verify`).
- `@covers(...)` decorator is required on every new `test_*` method (use `NotLanguageFeature.INFRASTRUCTURE` for inference-internal tests, or the relevant language feature for frontend tests).

---

### Task 1: Add the `implicit` flag to `Return_`

**Files:**
- Modify: `interpreter/instructions.py` (the `Return_` dataclass, ~line 901)
- Test: `tests/unit/test_map_registers_labels.py` (sibling unit coverage) or a new `tests/unit/test_return_implicit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_return_implicit.py`:

```python
"""Return_.implicit distinguishes synthetic fall-through returns from real ones."""

from interpreter.instructions import Return_
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


class TestReturnImplicitFlag:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_defaults_to_explicit(self):
        assert Return_(value_reg=Register("%0")).implicit is False

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_can_mark_implicit(self):
        assert Return_(value_reg=Register("%0"), implicit=True).implicit is True

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_implicit_survives_map_registers(self):
        inst = Return_(value_reg=Register("%0"), implicit=True)
        mapped = inst.map_registers(lambda r: r.rebase(100))
        assert mapped.implicit is True
        assert mapped.value_reg == Register("%100")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_return_implicit.py -v`
Expected: FAIL — `TypeError: Return_.__init__() got an unexpected keyword argument 'implicit'`.

- [ ] **Step 3: Add the field**

In `interpreter/instructions.py`, the `Return_` dataclass currently is:

```python
class Return_(InstructionBase):
    """RETURN: return from the current function."""

    value_reg: Register | None = None
```

Change to:

```python
class Return_(InstructionBase):
    """RETURN: return from the current function."""

    value_reg: Register | None = None
    implicit: bool = False  # True = synthetic fall-off-the-end return (lowering
    # artifact); such returns do not shape inferred return types.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_return_implicit.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite (the new field must not regress anything)**

Run: `poetry run python -m pytest -q -m 'not external and not nist'`
Expected: same green baseline as `main` (14233 passed, 66 skipped, 15 xfailed).

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/instructions.py tests/unit/test_return_implicit.py
git add interpreter/instructions.py tests/unit/test_return_implicit.py
git commit -m "feat(ir): Return_.implicit flag for synthetic fall-through returns (red-dragon-x78r)"
```

---

### Task 2: Add the `emit_implicit_return` helper

**Files:**
- Modify: `interpreter/frontends/common/declarations.py` (add helper near `lower_default_return` import, ~line 31)
- Test: `tests/unit/test_shared_literal_helpers.py` (existing shared-helper tests) — add a class

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_shared_literal_helpers.py`:

```python
class TestEmitImplicitReturn:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_emits_return_marked_implicit(self):
        from interpreter.constants import Language
        from interpreter.frontend_observer import FrontendObserver
        from interpreter.frontends.context import GrammarConstants, TreeSitterEmitContext
        from interpreter.frontends.common.declarations import emit_implicit_return
        from interpreter.instructions import Return_
        from interpreter.ir import Opcode

        class _Obs(FrontendObserver):
            def on_lowering_error(self, n, e): ...
            def on_node_lowered(self, n): ...

        ctx = TreeSitterEmitContext(
            language=Language.PYTHON, source=b"", observer=_Obs(),
            constants=GrammarConstants(),
        )
        emit_implicit_return(ctx, None)
        returns = [i for i in ctx.instructions if i.opcode == Opcode.RETURN]
        assert len(returns) == 1
        assert isinstance(returns[0], Return_)
        assert returns[0].implicit is True
```

(Ensure the file already imports `from tests.covers import NotLanguageFeature, covers`; add if missing.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_shared_literal_helpers.py::TestEmitImplicitReturn -v`
Expected: FAIL — `ImportError: cannot import name 'emit_implicit_return'`.

- [ ] **Step 3: Implement the helper**

In `interpreter/frontends/common/declarations.py`, add (after the imports, before `extract_param_name`):

```python
def emit_implicit_return(
    ctx: TreeSitterEmitContext,
    node: Any,  # tree-sitter node or None — untyped at Python boundary
) -> None:
    """Emit the synthetic fall-off-the-end return appended to a function body.

    Marks the Return_ as ``implicit=True`` so return-type inference ignores it
    (it is a lowering artifact, not a programmer-written return). Honours each
    language's ``default_return_value`` sentinel via ``lower_default_return``.
    """
    none_reg = lower_default_return(ctx, node, ctx.constants.default_return_value)
    ctx.emit_inst(Return_(value_reg=none_reg, implicit=True), node=node)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_shared_literal_helpers.py::TestEmitImplicitReturn -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
poetry run python -m black interpreter/frontends/common/declarations.py tests/unit/test_shared_literal_helpers.py
git add interpreter/frontends/common/declarations.py tests/unit/test_shared_literal_helpers.py
git commit -m "feat(frontends): emit_implicit_return helper marks synthetic returns (red-dragon-x78r)"
```

---

### Task 3: Mark every synthetic trailing return as implicit (all frontends)

**What counts as a synthetic trailing return (mark it):** the `Return_` emitted at the *end* of a function / method / constructor / lambda body-lowering routine to cover falling off the end — the pattern
`none_reg = lower_default_return(ctx, node, ctx.constants.default_return_value)` immediately followed by `ctx.emit_inst(Return_(value_reg=none_reg))`, sitting just before the function's `end_<name>` label or as the final emission of a def/lambda lowerer.

**What is NOT synthetic (leave `implicit=False`):**
- Return-*statement* handlers (`lower_return` / `lower_return_statement`) — these lower a programmer-written `return`/`return None`/bare `return`. A bare `return` legitimately contributes `Null`.
- Expression-context defaults — Scala `()` unit expressions, Lua/Ruby/Rust block-tail values, lambda bodies returning their expression. These are not fall-through returns.

**Procedure for each frontend below:** replace the synthetic trailing `lower_default_return(...) + emit_inst(Return_(value_reg=none_reg))` pair with `emit_implicit_return(ctx, node)` (import it from `interpreter.frontends.common.declarations`). For `_base.py:1089`, which builds the const inline, replace the trailing block with the marked form.

**Candidate trailing-return sites (verify each is the fall-through case before converting):**
- `interpreter/frontends/common/declarations.py:127-128` (the canonical one)
- `interpreter/frontends/_base.py:1087-1089`
- `interpreter/frontends/python/` (via common `lower_function_def`; confirm no extra trailing returns in `python/declarations.py`)
- `interpreter/frontends/javascript/declarations.py:320, 354`; `javascript/expressions.py:390, 537` (arrow/function-expression trailing)
- `interpreter/frontends/typescript/frontend.py:291, 491, 512, 658, 688, 722`
- `interpreter/frontends/java/declarations.py:133, 468`; `java/expressions.py:328` (lambda trailing — confirm)
- `interpreter/frontends/kotlin/` (trailing returns in its declarations)
- `interpreter/frontends/csharp/declarations.py:159, 204, 560, 602`; `csharp/expressions.py:615`
- `interpreter/frontends/go/declarations.py:105, 157, 289`; `go/expressions.py:410`
- `interpreter/frontends/rust/declarations.py:194, 199, 516`
- `interpreter/frontends/scala/declarations.py:285, 340, 504, 606`
- `interpreter/frontends/cpp/declarations.py:210, 388, 425, 494`; `cpp/expressions.py:388`
- `interpreter/frontends/c/declarations.py:427, 627`
- `interpreter/frontends/php/declarations.py:160, 197, 266, 463`; `php/expressions.py:759, 824`
- `interpreter/frontends/lua/declarations.py:165`; `lua/expressions.py:387`
- `interpreter/frontends/ruby/declarations.py:98, 210`; `ruby/expressions.py:357, 674`
- `interpreter/frontends/pascal/declarations.py:347, 578, 636, 788`
- `interpreter/frontends/common/declarations.py:198` (`emit_synthetic_init` constructor trailing return → also mark implicit)

**Do this as one sub-task per frontend** (16 commits: common+base, python, javascript, typescript, java, kotlin, csharp, go, rust, scala, cpp, c, php, lua, ruby, pascal). For EACH frontend:

- [ ] **Step 1: Write the failing test** (TDD — proves a value-returning function with fall-through does NOT pick up the synthetic return once inference is wired; until Task 4 lands this asserts the flag is set).

Add to that frontend's existing frontend test file (e.g. `tests/unit/test_<lang>_frontend.py`) — example for Python (`tests/unit/test_python_frontend.py`):

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_trailing_return_is_marked_implicit(self):
    from interpreter.ir import Opcode
    insts = get_frontend(Language.PYTHON).lower(b"def f():\n    return 42\n")
    returns = [i for i in insts if i.opcode == Opcode.RETURN]
    # Two returns: the explicit `return 42` and the synthetic trailing one.
    assert any(r.implicit for r in returns)        # synthetic present + marked
    assert any(not r.implicit for r in returns)    # explicit present + unmarked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_<lang>_frontend.py -k implicit -v`
Expected: FAIL — no return is marked implicit yet.

- [ ] **Step 3: Convert that frontend's trailing-return site(s)** to `emit_implicit_return(ctx, node)` per the procedure above.

- [ ] **Step 4: Run the frontend test + the frontend's full test file**

Run: `poetry run python -m pytest tests/unit/test_<lang>_frontend.py -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
poetry run python -m black interpreter/frontends/<lang>/ tests/unit/test_<lang>_frontend.py
git add interpreter/frontends/<lang>/ tests/unit/test_<lang>_frontend.py
git commit -m "refactor(<lang>): mark synthetic trailing return implicit (red-dragon-x78r)"
```

- [ ] **Step 6 (after all frontends done): full suite green, shim still on**

Run: `poetry run python -m pytest -q -m 'not external and not nist'`
Expected: 14233 passed (unchanged — the flag is set but not yet read).

---

### Task 4: Union explicit returns + skip implicit in `_infer_return`

**Files:**
- Modify: `interpreter/types/type_inference.py` — `_infer_return` (~line 912)
- Test: `tests/integration/test_type_inference.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_type_inference.py` (uses the existing `_lower_and_infer` helper and `FoundationTypeName`):

```python
class TestReturnUnionInference:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_two_distinct_explicit_returns_union(self):
        src = "def f(c):\n    if c:\n        return 1\n    return 'x'\n"
        _i, env = _lower_and_infer(src, "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert str(rt) == "Union[Int, String]"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_single_explicit_return_unchanged(self):
        src = "def f():\n    return 42\n"
        _i, env = _lower_and_infer(src, "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert rt == FoundationTypeName.INT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_type_inference.py::TestReturnUnionInference -v`
Expected: `test_two_distinct_explicit_returns_union` FAILS (first-writer-wins yields `Int`, not the union).

- [ ] **Step 3: Rewrite `_infer_return`**

Current body:

```python
    if not ctx.current_func_label:
        return
    current_label_key = FuncName(ctx.current_func_label)
    if current_label_key in ctx.func_return_types:
        return
    if inst.value_reg is None:
        return
    ret_type = ctx.register_types.get(_reg_key(inst.value_reg), UNKNOWN)
    if ret_type:
        ctx.func_return_types[current_label_key] = ret_type
```

Replace with:

```python
    if not ctx.current_func_label:
        return
    if getattr(inst, "implicit", False):
        return  # synthetic fall-through return is a lowering artifact, not a real return
    if inst.value_reg is None:
        return
    current_label_key = FuncName(ctx.current_func_label)
    ret_type = ctx.register_types.get(_reg_key(inst.value_reg), UNKNOWN)
    if not ret_type:
        return
    existing = ctx.func_return_types.get(current_label_key, UNKNOWN)
    ctx.func_return_types[current_label_key] = (
        union_of(existing, ret_type) if existing else ret_type
    )
```

(`union_of` is already imported at `type_inference.py:67`.)

- [ ] **Step 4: Run the new tests**

Run: `poetry run python -m pytest tests/integration/test_type_inference.py::TestReturnUnionInference -v`
Expected: PASS.

- [ ] **Step 5: Run full suite, fix resulting expectation churn (shim still on)**

Run: `poetry run python -m pytest -q -m 'not external and not nist'`
Any failures here are functions with two *different non-null* explicit return types that previously reported the first and now report a union. For each failing assertion, update the expected value to the emitted `Union[...]` (re-run with `-v` to read the actual value). These are correct.

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/types/type_inference.py tests/integration/test_type_inference.py
git add -A
git commit -m "feat(inference): union explicit return types, ignore synthetic returns (red-dragon-x78r)"
```

---

### Task 5: Remove the `null`→`UNKNOWN` shim in `_infer_const`

**Files:**
- Modify: `interpreter/types/type_inference.py` — `_infer_const` (~lines 596–607), plus the module/comment cleanup
- Test: `tests/integration/test_type_inference.py`, `tests/unit/test_type_inference.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_type_inference.py`:

```python
class TestNullVisibleInference:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_inferred_var_reassigned_null_is_union(self):
        _i, env = _lower_and_infer("x = 'hi'\nx = None\n", "python")
        assert str(env.var_types[VarName("x")]) == "Union[Null, String]"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_annotated_var_assigned_null_keeps_type(self):
        src = 'class C { void m() { String s = "hi"; s = null; } }'
        _i, env = _lower_and_infer(src, "java")
        assert env.var_types[VarName("s")] == FoundationTypeName.STRING

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_explicit_value_and_null_returns_union(self):
        src = "def f(c):\n    if c:\n        return 42\n    return None\n"
        _i, env = _lower_and_infer(src, "python")
        assert str(env.get_func_signature(FuncName("f")).return_type) == "Union[Int, Null]"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_void_function_has_no_return_type(self):
        _i, env = _lower_and_infer("def f():\n    pass\n", "python")
        rt = env.get_func_signature(FuncName("f")).return_type
        assert not rt  # UNKNOWN — only the (excluded) synthetic return exists
```

- [ ] **Step 2: Run to verify failure**

Run: `poetry run python -m pytest tests/integration/test_type_inference.py::TestNullVisibleInference -v`
Expected: `test_inferred_var_reassigned_null_is_union` and `test_explicit_value_and_null_returns_union` FAIL (shim still maps null to UNKNOWN → `x` is `String`, return is `Int`).

- [ ] **Step 3: Delete the shim**

In `_infer_const`, remove these two lines (currently ~604–605):

```python
    if isinstance(te, ScalarType) and te.name == FoundationTypeName.NULL:
        te = UNKNOWN
```

and update the preceding comment block (lines ~598–603) to:

```python
    # Typed literal: trust the Const's declared type_expr — no string re-inference.
    # Null literals infer as the Null scalar; nullability then surfaces as
    # Union[T, Null] via store_var_type widening and explicit-return unioning
    # (red-dragon-x78r). Synthetic fall-through returns are excluded in _infer_return.
```

Also rewrite the existing unit test `tests/unit/test_type_inference.py::TestConstInference::test_const_none_not_typed` (currently asserts `Register("%0") not in env.register_types`) — its premise is now reversed. Add `from interpreter.types.type_expr import NULL` to that file's imports and replace the test with:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_const_none_typed_null(self):
    instructions = [
        _make_inst(Opcode.LABEL, label=CodeLabel("entry")),
        _make_inst(Opcode.CONST, result_reg=Register("%0"), operands=["None"]),
    ]
    env = infer_types(
        instructions,
        _default_resolver(),
        func_symbol_table=_build_func_symbol_table(instructions),
    )
    assert env.register_types[Register("%0")] == NULL
```

- [ ] **Step 4: Run the new tests**

Run: `poetry run python -m pytest tests/integration/test_type_inference.py::TestNullVisibleInference tests/unit/test_type_inference.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite, update all resulting expectation churn**

Run: `poetry run python -m pytest -q -m 'not external and not nist'`
Failures will be in `tests/integration/test_type_inference.py` and `tests/unit/test_type_inference.py` only — functions/vars that now correctly carry `Null`/`Union[…, Null]`. For each:
- Run the specific test with `-v` to read the emitted type.
- Update the expected value to match (e.g. `== FoundationTypeName.INT` → `== "Union[Int, Null]"` using `str(...)`, or `== ""`/`is None` void assertions stay as-is because synthetic returns are excluded).
Do NOT weaken assertions to hide a change — match the emitted, semantically-correct value. If any non-inference test fails, STOP: that indicates a real regression, not an expectation update — investigate before proceeding.

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/types/type_inference.py tests/
git add -A
git commit -m "feat(inference): remove null->UNKNOWN shim; nullability visible as Union[T,Null] (red-dragon-x78r)"
```

---

### Task 6: Delete the dead `is_optional` / `unwrap_optional` helpers

**Files:**
- Modify: `interpreter/types/type_expr.py` (remove `is_optional`, `unwrap_optional`; keep `optional` — still used by `parse_type` for `Optional[...]`)
- Modify: `tests/unit/test_type_expr.py` (remove the tests for the deleted helpers)

- [ ] **Step 1: Confirm no production consumers remain**

Run: `grep -rn "is_optional\|unwrap_optional" interpreter/ | grep -v "_is_optional_register"`
Expected: only the definitions in `type_expr.py` (no callers). If any caller exists, STOP and reassess.

- [ ] **Step 2: Remove the functions**

Delete `is_optional(...)` and `unwrap_optional(...)` from `interpreter/types/type_expr.py` (the `optional(...)` function and `NULL`/`_NULL` stay). Update the `_NULL` comment to drop the `is_optional / unwrap_optional` mention.

- [ ] **Step 3: Remove their tests**

In `tests/unit/test_type_expr.py`, delete the import of `is_optional, unwrap_optional` and the test methods `test_is_optional_true`, `test_is_optional_false_for_scalar`, `test_is_optional_false_for_union_without_null`, `test_unwrap_optional`, `test_unwrap_optional_multi_member`, `test_unwrap_non_optional_returns_as_is`. Keep `test_optional_creates_union_with_null`, `test_parse_optional`, `test_roundtrip_optional_becomes_union`.

- [ ] **Step 4: Run the type_expr tests**

Run: `poetry run python -m pytest tests/unit/test_type_expr.py -v`
Expected: PASS (no import errors, remaining tests green).

- [ ] **Step 5: Full suite**

Run: `poetry run python -m pytest -q -m 'not external and not nist'`
Expected: fully green.

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/types/type_expr.py tests/unit/test_type_expr.py
git add -A
git commit -m "refactor(types): delete dead is_optional/unwrap_optional helpers (red-dragon-x78r)"
```

---

### Task 7: Final verification + close-out

- [ ] **Step 1: Full suite via real hooks** — run `poetry run python -m pytest -q -m 'not external and not nist'`; expected fully green.
- [ ] **Step 2: Confirm shim gone** — `grep -rn "FoundationTypeName.NULL" interpreter/types/type_inference.py` should show no `te = UNKNOWN` shim.
- [ ] **Step 3: Update the decision memo** status line in `docs/superpowers/specs/2026-06-17-nullability-model-decision.md` from "Decided — no implementation" to "Implemented (red-dragon-x78r)".
- [ ] **Step 4: Commit** the memo status update through hooks.
- [ ] **Step 5: Close `red-dragon-x78r`** with a summary comment (final test counts, files touched).
