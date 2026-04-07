# Java Constant Declaration Lowering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower Java class `constant_declaration` nodes into concrete IR so `public static final` constants stop producing `unsupported:constant_declaration` symbolics.

**Architecture:** Extend the Java frontend's node-type table and statement dispatch to recognize `constant_declaration`, then reuse the existing Java declarator/initializer pattern in `declarations.py` to emit `DeclVar` values from initializer expressions. Keep the fix scoped to class constants only; interface constants stay in `red-dragon-ev6r`.

**Tech Stack:** Python, pytest, tree-sitter Java frontend, Red Dragon IR lowering

---

## File Map

- Modify: `interpreter/frontends/java/node_types.py`
  Responsibility: declare the Java tree-sitter node-type constant for `constant_declaration`.
- Modify: `interpreter/frontends/java/frontend.py`
  Responsibility: route `constant_declaration` through Java statement lowering.
- Modify: `interpreter/frontends/java/declarations.py`
  Responsibility: lower class `constant_declaration` declarators by reusing field-style initializer handling and emitting `DeclVar`.
- Modify: `tests/integration/test_java_constant_declaration.py`
  Responsibility: remove `xfail` and keep the acceptance assertions for concrete constant values.

### Task 1: Turn the Existing Acceptance Test Red

**Files:**
- Modify: `tests/integration/test_java_constant_declaration.py:47-52`
- Test: `tests/integration/test_java_constant_declaration.py`

- [ ] **Step 1: Remove the xfail marker from the integration test**

```python
class TestJavaConstantDeclaration:
    def test_static_final_constants_are_concrete(self, constants_project: Path):
        """public static final fields should lower to concrete values."""
        linked = compile_directory(constants_project, Language.JAVA)
```

- [ ] **Step 2: Run the test to verify it fails without the marker**

Run: `pytest tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete -v`
Expected: FAIL with symbolics that still include `unsupported:constant_declaration`.

- [ ] **Step 3: Do not broaden the fixture or assertions**

Keep the existing acceptance assertions exactly focused on:

```python
assert symbolics == [], f"Expected no symbolics: {symbolics}"
assert local_vars.get(VarName("g")) == "hello"
assert local_vars.get(VarName("m")) == 100
```

- [ ] **Step 4: Commit the red test state if working in strict TDD mode**

```bash
git add tests/integration/test_java_constant_declaration.py
git commit -m "test: unxfail java constant declaration coverage"
```

### Task 2: Teach the Java Frontend to Recognize `constant_declaration`

**Files:**
- Modify: `interpreter/frontends/java/node_types.py:74-90`
- Modify: `interpreter/frontends/java/frontend.py:110-138`
- Test: `tests/integration/test_java_constant_declaration.py`

- [ ] **Step 1: Add the Java node-type constant**

Update `interpreter/frontends/java/node_types.py` to include:

```python
    FIELD_DECLARATION = "field_declaration"
    CONSTANT_DECLARATION = "constant_declaration"
    STATIC_INITIALIZER = "static_initializer"
```

- [ ] **Step 2: Register statement dispatch for the new node type**

Update `interpreter/frontends/java/frontend.py` so the statement dispatch includes:

```python
            JavaNodeType.LOCAL_VARIABLE_DECLARATION: java_decl.lower_local_var_decl,
            JavaNodeType.CONSTANT_DECLARATION: java_decl.lower_constant_decl,
            JavaNodeType.RETURN_STATEMENT: common_assign.lower_return,
```

- [ ] **Step 3: Run the targeted test again**

Run: `pytest tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete -v`
Expected: FAIL, but now because `lower_constant_decl` does not exist yet or the dispatch reaches an incomplete implementation rather than falling back to unsupported-node behavior.

- [ ] **Step 4: Commit the dispatch plumbing**

```bash
git add interpreter/frontends/java/node_types.py interpreter/frontends/java/frontend.py
git commit -m "refactor: route java constant declarations through stmt lowering"
```

### Task 3: Implement Minimal Class Constant Lowering

**Files:**
- Modify: `interpreter/frontends/java/declarations.py:37-59`
- Modify: `interpreter/frontends/java/declarations.py:457-483`
- Test: `tests/integration/test_java_constant_declaration.py`

- [ ] **Step 1: Add a narrow helper that lowers initialized variable declarators to `DeclVar`**

Add a helper near `lower_local_var_decl()` that keeps the existing declarator traversal pattern and skips malformed / uninitialized declarators:

```python
def _lower_initialized_declarators(ctx: TreeSitterEmitContext, node: Any) -> None:
    for child in node.children:
        if child.type != JavaNodeType.VARIABLE_DECLARATOR:
            continue
        name_node = child.child_by_field_name("name")
        value_node = child.child_by_field_name("value")
        if not name_node or not value_node:
            continue
        var_name = ctx.node_text(name_node)
        val_reg = ctx.lower_expr(value_node)
        ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=val_reg), node=node)
```

- [ ] **Step 2: Reuse that helper from local variable declarations**

Replace the current body of `lower_local_var_decl()` with a call that preserves the existing type seeding behavior and declarator lowering shape:

```python
def lower_local_var_decl(ctx: TreeSitterEmitContext, node: Any) -> None:
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            if name_node:
                ctx.seed_var_type(ctx.node_text(name_node), type_hint)
    _lower_initialized_declarators(ctx, node)
```

- [ ] **Step 3: Add the class constant lowerer using the same helper**

Add a new function in `interpreter/frontends/java/declarations.py`:

```python
def lower_constant_decl(ctx: TreeSitterEmitContext, node: Any) -> None:
    """Lower Java class constant_declaration nodes as DeclVar values."""
    type_hint = extract_normalized_type(ctx, node, "type", ctx.type_map)
    for child in node.children:
        if child.type == JavaNodeType.VARIABLE_DECLARATOR:
            name_node = child.child_by_field_name("name")
            if name_node:
                ctx.seed_var_type(ctx.node_text(name_node), type_hint)
    _lower_initialized_declarators(ctx, node)
```

- [ ] **Step 4: Keep `_collect_field_inits()` unchanged unless the implementation proves duplication is harmful**

The field-initializer collector serves constructor/class-init behavior and should remain:

```python
def _collect_field_inits(
    ctx: TreeSitterEmitContext, node: Any
) -> list[FieldInit]:
```

Do not refactor class-field initialization behavior as part of this task.

- [ ] **Step 5: Run the targeted integration test to verify the fix**

Run: `pytest tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete -v`
Expected: PASS

- [ ] **Step 6: Commit the implementation**

```bash
git add interpreter/frontends/java/declarations.py tests/integration/test_java_constant_declaration.py
git commit -m "fix: lower java class constant declarations"
```

### Task 4: Verify the Change Against the Wider Java Surface

**Files:**
- Modify: none unless verification exposes a bug
- Test: `tests/integration/test_java_constant_declaration.py`

- [ ] **Step 1: Run the focused integration test file**

Run: `pytest tests/integration/test_java_constant_declaration.py -v`
Expected: PASS

- [ ] **Step 2: Run nearby Java frontend coverage if available in this repo slice**

Run: `pytest tests/integration -k "java and constant" -v`
Expected: PASS with the constant declaration test included.

- [ ] **Step 3: If the Java frontend has a more focused declarations suite, run it too**

Run: `pytest tests -k "java and declaration" -v`
Expected: PASS, or no relevant tests selected besides already-passing coverage.

- [ ] **Step 4: Commit only if verification required follow-up fixes**

```bash
git add <files changed during verification>
git commit -m "test: stabilize java constant declaration lowering"
```

### Task 5: Land the Issue Cleanly

**Files:**
- Modify: Beads metadata only if updating issue state in this session

- [ ] **Step 1: Inspect the final diff before landing**

Run: `git diff --stat HEAD~1..HEAD`
Expected: changes limited to the Java frontend files and the constant declaration integration test.

- [ ] **Step 2: Re-run the single acceptance test as a final guard**

Run: `pytest tests/integration/test_java_constant_declaration.py::TestJavaConstantDeclaration::test_static_final_constants_are_concrete -v`
Expected: PASS

- [ ] **Step 3: Update the Beads issue when implementation is actually complete**

Run:

```bash
bd close red-dragon-1ycy --reason "Java class constant_declaration nodes now lower to concrete DeclVar values; integration coverage passes." --json
```

Expected: issue closed, with `red-dragon-ev6r` remaining open for the interface-only follow-up.
