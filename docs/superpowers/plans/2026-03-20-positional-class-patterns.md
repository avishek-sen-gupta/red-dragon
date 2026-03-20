# Positional Class Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `case Point(a, b):` work by resolving `__match_args__` from the AST to map positions to field names.

**Architecture:** Add `_resolve_match_args` helper that walks the tree-sitter AST to find the class definition and extract `__match_args__`. Modify `parse_pattern`'s `class_pattern` handling to convert positional args to keyword args when `__match_args__` is found. No VM or compiler changes.

**Tech Stack:** Python 3.13+, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-positional-class-patterns-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/python/patterns.py` | Add `_resolve_match_args`, modify `class_pattern` handling | **Modify** |
| `tests/integration/test_python_pattern_matching.py` | Integration tests + fix existing xfail | **Modify** |

---

### Task 1: `_resolve_match_args` + modify `parse_pattern` (TDD)

**Files:**
- Modify: `interpreter/frontends/python/patterns.py`
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/integration/test_python_pattern_matching.py`:

```python
class TestPositionalClassPattern:
    def test_class_positional_with_match_args(self):
        """Point(3, b) with __match_args__ — b bound to 4."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(3, b):
        result = b
""",
            max_steps=3000,
        )
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py::TestPositionalClassPattern::test_class_positional_with_match_args -v`
Expected: FAIL — positional args use LOAD_INDEX which produces symbolic

- [ ] **Step 3: Implement `_resolve_match_args` and modify `class_pattern` handling**

Add to `interpreter/frontends/python/patterns.py`:

```python
def _find_module_root(node) -> object:
    """Walk up via .parent to reach the module root node."""
    current = node
    while current.parent:
        current = current.parent
    return current


def _resolve_match_args(node, class_name: str) -> list[str]:
    """Find __match_args__ for class_name by walking the AST.

    Returns list of field names, or empty list if not found.
    """
    root = _find_module_root(node)
    class_def = _find_class_def(root, class_name)
    if class_def is None:
        return []
    body = class_def.child_by_field_name("body")
    if body is None:
        return []
    return _extract_match_args_from_body(body)


def _find_class_def(node, class_name: str):
    """Recursively find a class_definition node with matching name."""
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node and name_node.text.decode() == class_name:
            return node
    return next(
        (result for child in node.children if (result := _find_class_def(child, class_name))),
        None,
    )


def _extract_match_args_from_body(body) -> list[str]:
    """Extract field names from __match_args__ = ("x", "y") in a class body."""
    for child in body.children:
        if child.type != "assignment":
            continue
        left = child.child_by_field_name("left")
        right = child.child_by_field_name("right")
        if left and left.text.decode() == "__match_args__" and right and right.type == "tuple":
            return [
                sc.text.decode()
                for s in right.children
                if s.type == "string"
                for sc in s.children
                if sc.type == "string_content"
            ]
    return []
```

Then modify the `class_pattern` block in `parse_pattern`. Currently (around line 104-126):

```python
    # Class pattern
    if node_type == PythonNodeType.CLASS_PATTERN:
        dotted = next(c for c in node.children if c.type == "dotted_name")
        class_name = ctx.node_text(dotted)
        case_patterns = [
            c for c in node.children if c.type == PythonNodeType.CASE_PATTERN
        ]
        positional: list[Pattern] = []
        keyword: list[tuple[str, Pattern]] = []
        for child in case_patterns:
            inner = next(c for c in child.children if c.is_named)
            if inner.type == PythonNodeType.KEYWORD_PATTERN:
                parts = [c for c in inner.children if c.is_named]
                kw_name = ctx.node_text(parts[0])
                kw_val = parse_pattern(ctx, parts[1])
                keyword.append((kw_name, kw_val))
            else:
                positional.append(parse_pattern(ctx, child))
        return ClassPattern(
            class_name=class_name,
            positional=tuple(positional),
            keyword=tuple(keyword),
        )
```

Replace with:

```python
    # Class pattern
    if node_type == PythonNodeType.CLASS_PATTERN:
        dotted = next(c for c in node.children if c.type == "dotted_name")
        class_name = ctx.node_text(dotted)
        case_patterns = [
            c for c in node.children if c.type == PythonNodeType.CASE_PATTERN
        ]
        positional: list[Pattern] = []
        keyword: list[tuple[str, Pattern]] = []
        for child in case_patterns:
            inner = next(c for c in child.children if c.is_named)
            if inner.type == PythonNodeType.KEYWORD_PATTERN:
                parts = [c for c in inner.children if c.is_named]
                kw_name = ctx.node_text(parts[0])
                kw_val = parse_pattern(ctx, parts[1])
                keyword.append((kw_name, kw_val))
            else:
                positional.append(parse_pattern(ctx, child))
        # Resolve positional args via __match_args__ if available
        if positional:
            match_args = _resolve_match_args(node, class_name)
            if match_args:
                keyword.extend(
                    (match_args[i], pat)
                    for i, pat in enumerate(positional)
                    if i < len(match_args)
                )
                positional = []
        return ClassPattern(
            class_name=class_name,
            positional=tuple(positional),
            keyword=tuple(keyword),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py::TestPositionalClassPattern -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/python/patterns.py tests/integration/test_python_pattern_matching.py
git commit -m "feat: resolve __match_args__ for positional class patterns (TDD)"
```

---

### Task 2: More integration tests + fix xfail + full suite + push

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Add more integration tests**

Add to `TestPositionalClassPattern`:

```python
    def test_class_positional_two_captures(self):
        """Point(a, b) captures both fields via __match_args__."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(a, b):
        ra = a
        rb = b
""",
            max_steps=3000,
        )
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 3
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 4

    def test_class_positional_literal_rejects(self):
        """Point(99, b) with non-matching x — falls to default."""
        _, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
result = "default"
match p:
    case Point(99, b):
        result = "matched"
    case _:
        result = "default"
""",
            max_steps=3000,
        )
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "default"

    def test_class_positional_in_sequence_with_star(self):
        """Positional class patterns inside a list with star."""
        vm, local_vars = _run_python(
            """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

points = [Point(1, 2), Point(3, 4), Point(5, 6)]
match points:
    case [Point(a, b), *rest]:
        ra = a
        rb = b
        rest_len = len(rest)
""",
            max_steps=5000,
        )
        assert isinstance(local_vars["ra"], int) and local_vars["ra"] == 1
        assert isinstance(local_vars["rb"], int) and local_vars["rb"] == 2
        assert isinstance(local_vars["rest_len"], int) and local_vars["rest_len"] == 2
```

- [ ] **Step 2: Fix existing xfail test**

Find `test_class_positional` in the existing test file. It uses `Pair(a, b)` without `__match_args__`. Update it to include `__match_args__` and remove the `@pytest.mark.xfail` decorator:

```python
    def test_class_positional(self):
        _, local_vars = _run_python(
            """\
class Pair:
    __match_args__ = ("a", "b")
    def __init__(self, a, b):
        self.a = a
        self.b = b

p = Pair(10, 20)
match p:
    case Pair(a, b):
        result = a + b
""",
            max_steps=2000,
        )
        assert local_vars["result"] == 30
```

- [ ] **Step 3: Run all tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS (minus remaining xfails for other features)

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m black . && poetry run python -m pytest -x --tb=short`
Expected: All pass, no regressions.

- [ ] **Step 5: Close issue and push**

```bash
bd update red-dragon-jkw2 --status closed
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for positional class patterns with __match_args__"
git push origin main
```
