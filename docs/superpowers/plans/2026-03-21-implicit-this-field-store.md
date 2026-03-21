# Implicit `this` Field Store — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix bare field assignments in Java/C#/C++ constructors to emit `STORE_FIELD this` instead of `STORE_VAR`.

**Architecture:** Add `_class_field_names: set[str]` to `TreeSitterEmitContext`. Populate it during class lowering from the already-collected `field_inits`. Check it in each language's store target function — if the target is a bare identifier matching a field name, emit `LOAD_VAR this` + `STORE_FIELD` instead of `STORE_VAR`.

**Tech Stack:** Python 3.13+, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-implicit-this-field-store-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/context.py` | Add `_class_field_names` field | **Modify** (1 line) |
| `interpreter/frontends/csharp/declarations.py` | Populate `_class_field_names` | **Modify** (~3 lines) |
| `interpreter/frontends/csharp/expressions.py` | Check field names in store target | **Modify** (~6 lines) |
| `interpreter/frontends/java/declarations.py` | Populate `_class_field_names` | **Modify** (~3 lines) |
| `interpreter/frontends/java/expressions.py` | Check field names in store target | **Modify** (~6 lines) |
| `interpreter/frontends/cpp/declarations.py` | Populate `_class_field_names` | **Modify** (~3 lines) |
| `interpreter/frontends/c/expressions.py` | Check field names in store target (C++ uses C's store target) | **Modify** (~6 lines) |
| `tests/integration/test_implicit_this_field_store.py` | Integration tests | **Create** |

---

### Task 1: Add `_class_field_names` to context + C# fix (TDD)

**Files:**
- Modify: `interpreter/frontends/context.py`
- Modify: `interpreter/frontends/csharp/declarations.py`
- Modify: `interpreter/frontends/csharp/expressions.py`
- Create: `tests/integration/test_implicit_this_field_store.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_implicit_this_field_store.py`:

```python
"""Integration tests: implicit this field store in constructors."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run(source: str, language: Language, max_steps: int = 2000) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestCSharpImplicitThis:
    def test_constructor_field_assignment(self):
        """C#: Radius = r in constructor should store on this, not as local."""
        local_vars = _run("""\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static Circle c = new Circle(5);
    static int result = c.Radius;
}
""", Language.CSHARP)
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5

    def test_multiple_field_assignments(self):
        """C#: Multiple field assignments in constructor."""
        local_vars = _run("""\
class Point {
    public int X;
    public int Y;
    public Point(int x, int y) { X = x; Y = y; }
}
class M {
    static Point p = new Point(3, 4);
    static int rx = p.X;
    static int ry = p.Y;
}
""", Language.CSHARP)
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 3
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_implicit_this_field_store.py::TestCSharpImplicitThis -v`
Expected: FAIL — `result` is symbolic

- [ ] **Step 3: Add `_class_field_names` to context**

In `interpreter/frontends/context.py`, add after `byref_params` (around line 139):

```python
    # Field names for the current class — used to detect implicit this in constructors
    _class_field_names: set[str] = field(default_factory=set)
```

- [ ] **Step 4: Populate field names in C# class lowering**

In `interpreter/frontends/csharp/declarations.py`, find `lower_class_declaration` where it sets `ctx._current_class_name = class_name` (around line 295). After collecting `field_inits`, add:

```python
    ctx._class_field_names = {name for name, _ in field_inits}
```

And where it restores `ctx._current_class_name = saved_class` (around line 319), add:

```python
    ctx._class_field_names = set()
```

Also need to collect field names from field declarations that DON'T have initializers (just `public int Radius;`). Check the existing collection — `_collect_csharp_field_inits` only collects fields WITH initializers. We need ALL field names.

Read `_collect_csharp_field_inits` to understand, then add a separate collection of all field names:

```python
    # Collect ALL field names (not just ones with initializers)
    all_field_names: set[str] = set()
    for child in deferred:
        if child.type == NT.FIELD_DECLARATION and not _has_static_modifier(ctx, child):
            for vc in child.children:
                if vc.type == NT.VARIABLE_DECLARATION:
                    for decl in vc.children:
                        if decl.type == NT.VARIABLE_DECLARATOR:
                            name_node = decl.child_by_field_name("name")
                            if name_node:
                                all_field_names.add(ctx.node_text(name_node))
    ctx._class_field_names = all_field_names
```

- [ ] **Step 5: Check field names in C# store target**

In `interpreter/frontends/csharp/expressions.py`, modify `lower_csharp_store_target` (line 759). The `NT.IDENTIFIER` branch currently does:

```python
    if target.type == NT.IDENTIFIER:
        emit_byref_store(ctx, ctx.node_text(target), val_reg, node=parent_node)
```

Change to:

```python
    if target.type == NT.IDENTIFIER:
        name = ctx.node_text(target)
        if name in ctx._class_field_names:
            this_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg], node=parent_node)
        else:
            emit_byref_store(ctx, name, val_reg, node=parent_node)
```

- [ ] **Step 6: Run tests**

Run: `poetry run python -m pytest tests/integration/test_implicit_this_field_store.py::TestCSharpImplicitThis -v`
Expected: PASS

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py --tb=short -q`
Expected: All pass (no regression)

- [ ] **Step 7: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/context.py interpreter/frontends/csharp/declarations.py interpreter/frontends/csharp/expressions.py tests/integration/test_implicit_this_field_store.py
git commit -m "feat: C# implicit this field store in constructors (TDD)"
```

---

### Task 2: Java fix

**Files:**
- Modify: `interpreter/frontends/java/declarations.py`
- Modify: `interpreter/frontends/java/expressions.py`
- Modify: `tests/integration/test_implicit_this_field_store.py`

- [ ] **Step 1: Write failing test**

Add to `tests/integration/test_implicit_this_field_store.py`:

```python
class TestJavaImplicitThis:
    def test_constructor_field_assignment(self):
        """Java: radius = r in constructor should store on this."""
        local_vars = _run("""\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
}
class M {
    static Circle c = new Circle(5);
    static int result = c.radius;
}
""", Language.JAVA)
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5

    def test_multiple_field_assignments(self):
        local_vars = _run("""\
class Point {
    int x;
    int y;
    Point(int a, int b) { x = a; y = b; }
}
class M {
    static Point p = new Point(3, 4);
    static int rx = p.x;
    static int ry = p.y;
}
""", Language.JAVA)
        assert isinstance(local_vars["rx"], int) and local_vars["rx"] == 3
        assert isinstance(local_vars["ry"], int) and local_vars["ry"] == 4
```

- [ ] **Step 2: Run test to verify it fails, then implement**

In `interpreter/frontends/java/declarations.py`, find `lower_class_decl` where `field_inits` are collected and `ctx._current_class_name` is set. Add field name collection similar to C#:

```python
    # Collect ALL field names (not just ones with initializers)
    all_field_names: set[str] = set()
    for child in deferred:
        if child.type == JavaNodeType.FIELD_DECLARATION and not _has_static_modifier(child):
            for decl in child.children:
                if decl.type == JavaNodeType.VARIABLE_DECLARATOR:
                    name_node = decl.child_by_field_name("name")
                    if name_node:
                        all_field_names.add(ctx.node_text(name_node))
    ctx._class_field_names = all_field_names
```

And clear it when restoring class name: `ctx._class_field_names = set()`

In `interpreter/frontends/java/expressions.py`, modify `lower_java_store_target` (line 272). Change the `JavaNodeType.IDENTIFIER` branch:

```python
    if target.type == JavaNodeType.IDENTIFIER:
        name = ctx.node_text(target)
        if name in ctx._class_field_names:
            this_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg], node=parent_node)
        else:
            ctx.emit(Opcode.STORE_VAR, operands=[name, val_reg], node=parent_node)
```

- [ ] **Step 3: Run tests**

Run: `poetry run python -m pytest tests/integration/test_implicit_this_field_store.py -v`
Expected: All PASS

Run: `poetry run python -m pytest tests/unit/test_java_frontend.py --tb=short -q`
Expected: No regression

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/java/declarations.py interpreter/frontends/java/expressions.py tests/integration/test_implicit_this_field_store.py
git commit -m "feat: Java implicit this field store in constructors (TDD)"
```

---

### Task 3: C++ fix

**Files:**
- Modify: `interpreter/frontends/cpp/declarations.py`
- Modify: `interpreter/frontends/c/expressions.py` (C++ uses C's store target via `lower_c_store_target`)
- Modify: `tests/integration/test_implicit_this_field_store.py`

- [ ] **Step 1: Write failing test**

Add to `tests/integration/test_implicit_this_field_store.py`:

```python
class TestCppImplicitThis:
    def test_constructor_field_assignment(self):
        """C++: x = v in constructor should store on this."""
        local_vars = _run("""\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
};
int main() {
    Circle c(5);
    int result = c.radius;
}
""", Language.CPP)
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5
```

- [ ] **Step 2: Run test to verify it fails, then implement**

In `interpreter/frontends/cpp/declarations.py`, find `lower_class_specifier` where `field_inits` are collected (around line 223-230). Add:

```python
    ctx._class_field_names = {name for name, _ in field_inits}
```

After the class body is lowered (after line 246), clear:

```python
    ctx._class_field_names = set()
```

Note: C++ field_inits only collects fields WITH initializers. Need to also collect bare declarations. In `_lower_cpp_class_body_b2`, field declarations are processed — extract names from `field_declaration` nodes that have `field_identifier` children.

Actually simpler: extract ALL field names from the body node before lowering:

```python
    # Collect ALL field names from field_declaration nodes
    if body_node:
        all_field_names: set[str] = set()
        for child in body_node.children:
            if child.type == CppNodeType.FIELD_DECLARATION:
                for fc in child.children:
                    if fc.type == "field_identifier":
                        all_field_names.add(ctx.node_text(fc))
        ctx._class_field_names = all_field_names
```

In `interpreter/frontends/c/expressions.py`, modify `lower_c_store_target` (line 64). Change the `CNodeType.IDENTIFIER` branch:

```python
    if target.type == CNodeType.IDENTIFIER:
        name = ctx.node_text(target)
        if name in ctx._class_field_names:
            this_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg], node=parent_node)
        else:
            ctx.emit(Opcode.STORE_VAR, operands=[name, val_reg], node=parent_node)
```

- [ ] **Step 3: Run tests**

Run: `poetry run python -m pytest tests/integration/test_implicit_this_field_store.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/cpp/declarations.py interpreter/frontends/c/expressions.py tests/integration/test_implicit_this_field_store.py
git commit -m "feat: C++ implicit this field store in constructors (TDD)"
```

---

### Task 4: Remove C# xfail + full suite + push

- [ ] **Step 1: Remove xfail from C# recursive_with_capture test**

In `tests/integration/test_csharp_pattern_matching.py`, find `test_switch_expr_recursive_with_capture` and remove its `@pytest.mark.xfail` decorator.

- [ ] **Step 2: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All pass, no regressions.

- [ ] **Step 4: Close issue and push**

```bash
bd update red-dragon-yn17 --status closed
git add -A
git commit -m "fix: remove xfail for C# recursive pattern capture — field store now works"
git push origin main
```
