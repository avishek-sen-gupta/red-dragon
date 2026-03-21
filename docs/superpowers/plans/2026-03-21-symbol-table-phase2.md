# Symbol Table Phase 2: Per-Language Extractors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `_extract_symbols` for C#, Java, C++, and Python so the `SymbolTable` is populated before IR lowering.

**Architecture:** Each language gets an `extract_<lang>_symbols(root) -> SymbolTable` function that walks the tree-sitter AST for class definitions and extracts fields, methods, constants, and parents. Each frontend class overrides `_extract_symbols` to call it. No behavioral changes — Phase 3 consumes the table.

**Tech Stack:** Python 3.13+, tree-sitter, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-symbol-table-phase2-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/csharp/declarations.py` | Add `extract_csharp_symbols` | **Modify** |
| `interpreter/frontends/csharp/frontend.py` | Override `_extract_symbols` | **Modify** |
| `interpreter/frontends/java/declarations.py` | Add `extract_java_symbols` | **Modify** |
| `interpreter/frontends/java/frontend.py` | Override `_extract_symbols` | **Modify** |
| `interpreter/frontends/cpp/declarations.py` | Add `extract_cpp_symbols` | **Modify** |
| `interpreter/frontends/cpp/frontend.py` | Override `_extract_symbols` | **Modify** |
| `interpreter/frontends/python/declarations.py` | Add `extract_python_symbols` | **Modify** |
| `interpreter/frontends/python/frontend.py` | Override `_extract_symbols` | **Modify** |
| `tests/unit/test_symbol_extraction.py` | Unit tests for all 4 extractors | **Create** |

---

### Task 1: C# symbol extraction (TDD)

**Files:**
- Modify: `interpreter/frontends/csharp/declarations.py`
- Modify: `interpreter/frontends/csharp/frontend.py`
- Create: `tests/unit/test_symbol_extraction.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_symbol_extraction.py`:

```python
"""Unit tests for per-language symbol extraction."""

from __future__ import annotations

from interpreter.frontend import get_frontend
from interpreter.constants import Language
from interpreter.frontends.symbol_table import SymbolTable


def _extract(language: Language, source: str) -> SymbolTable:
    """Parse source and extract symbols via the frontend's _extract_symbols."""
    frontend = get_frontend(language)
    from interpreter.parser import TreeSitterParserFactory
    parser = TreeSitterParserFactory().get_parser(language)
    tree = parser.parse(source.encode())
    return frontend._extract_symbols(tree.root_node)


class TestCSharpSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.CSHARP, """\
class Circle {
    public int Radius;
    public string Name;
    public Circle(int r) { Radius = r; }
    public int Area() { return 0; }
}
""")
        assert "Circle" in st.classes
        ci = st.classes["Circle"]
        assert "Radius" in ci.fields
        assert "Name" in ci.fields
        assert ci.fields["Radius"].type_hint == "int"
        assert ci.fields["Radius"].has_initializer is False

    def test_extracts_methods(self):
        st = _extract(Language.CSHARP, """\
class Circle {
    public int Area() { return 0; }
}
""")
        assert "Area" in st.classes["Circle"].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.CSHARP, """\
class Circle {
    public static int Count = 0;
}
""")
        assert "Count" in st.classes["Circle"].constants

    def test_extracts_parents(self):
        st = _extract(Language.CSHARP, """\
class Shape {}
class Circle : Shape {
    public int Radius;
}
""")
        assert "Shape" in st.classes["Circle"].parents

    def test_filters_static_fields(self):
        st = _extract(Language.CSHARP, """\
class Circle {
    public int Radius;
    public static int Count = 0;
}
""")
        assert "Radius" in st.classes["Circle"].fields
        assert "Count" not in st.classes["Circle"].fields  # static → constants
```

- [ ] **Step 2: Run to verify fail**

Run: `poetry run python -m pytest tests/unit/test_symbol_extraction.py::TestCSharpSymbolExtraction -v`
Expected: FAIL — `_extract_symbols` returns empty

- [ ] **Step 3: Implement C# extractor**

Add to `interpreter/frontends/csharp/declarations.py`:

```python
from interpreter.frontends.symbol_table import (
    ClassInfo, FieldInfo, FunctionInfo, SymbolTable,
)


def extract_csharp_symbols(root) -> SymbolTable:
    """Extract symbols from C# tree-sitter AST."""
    classes: dict[str, ClassInfo] = {}
    _walk_for_classes(root, classes)
    return SymbolTable(classes=classes)


def _walk_for_classes(node, classes: dict[str, ClassInfo]) -> None:
    """Recursively find class_declaration nodes and extract their symbols."""
    if node.type == "class_declaration":
        ci = _extract_class_info(node)
        classes[ci.name] = ci
    for child in node.children:
        _walk_for_classes(child, classes)


def _extract_class_info(node) -> ClassInfo:
    """Extract ClassInfo from a class_declaration node."""
    name_node = node.child_by_field_name("name")
    class_name = name_node.text.decode() if name_node else "__anon__"
    body = node.child_by_field_name("body")

    fields: dict[str, FieldInfo] = {}
    methods: dict[str, FunctionInfo] = {}
    constants: dict[str, str] = {}
    parents: list[str] = []

    # Extract parents from base_list
    base_list = next((c for c in node.children if c.type == "base_list"), None)
    if base_list:
        parents = [
            c.text.decode() for c in base_list.children
            if c.type == "identifier" or c.type == "qualified_name"
        ]

    if body:
        for child in body.children:
            if child.type == "field_declaration":
                is_static = any(
                    c.type == "modifier" and c.text.decode() == "static"
                    for c in child.children
                )
                for vc in child.children:
                    if vc.type == "variable_declaration":
                        type_node = next((c for c in vc.children if c.type in (
                            "predefined_type", "identifier", "generic_name", "nullable_type",
                        )), None)
                        type_hint = type_node.text.decode() if type_node else ""
                        for decl in vc.children:
                            if decl.type == "variable_declarator":
                                n = decl.child_by_field_name("name")
                                v = decl.child_by_field_name("value")
                                if n:
                                    fname = n.text.decode()
                                    if is_static:
                                        constants[fname] = v.text.decode() if v else ""
                                    else:
                                        fields[fname] = FieldInfo(
                                            name=fname,
                                            type_hint=type_hint,
                                            has_initializer=v is not None,
                                        )
            elif child.type == "method_declaration":
                mname_node = child.child_by_field_name("name")
                if mname_node:
                    mname = mname_node.text.decode()
                    params_node = child.child_by_field_name("parameters")
                    params = tuple(
                        p.child_by_field_name("name").text.decode()
                        for p in (params_node.children if params_node else [])
                        if p.type == "parameter" and p.child_by_field_name("name")
                    )
                    ret_node = child.child_by_field_name("type")
                    ret_type = ret_node.text.decode() if ret_node else "void"
                    methods[mname] = FunctionInfo(name=mname, params=params, return_type=ret_type)

    return ClassInfo(
        name=class_name,
        fields=fields,
        methods=methods,
        constants=constants,
        parents=tuple(parents),
    )
```

In `interpreter/frontends/csharp/frontend.py`, add the override:

```python
from interpreter.frontends.csharp.declarations import extract_csharp_symbols
from interpreter.frontends.symbol_table import SymbolTable

# Inside CSharpFrontend class:
    def _extract_symbols(self, root) -> SymbolTable:
        return extract_csharp_symbols(root)
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_symbol_extraction.py::TestCSharpSymbolExtraction -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/csharp/declarations.py interpreter/frontends/csharp/frontend.py tests/unit/test_symbol_extraction.py
git commit -m "feat: C# symbol extraction — _extract_symbols populates SymbolTable (TDD)"
```

---

### Task 2: Java symbol extraction (TDD)

**Files:**
- Modify: `interpreter/frontends/java/declarations.py`
- Modify: `interpreter/frontends/java/frontend.py`
- Modify: `tests/unit/test_symbol_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_symbol_extraction.py`:

```python
class TestJavaSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.JAVA, """\
class Circle {
    int radius;
    String name;
    Circle(int r) { radius = r; }
    int area() { return 0; }
}
""")
        assert "Circle" in st.classes
        ci = st.classes["Circle"]
        assert "radius" in ci.fields
        assert "name" in ci.fields
        assert ci.fields["radius"].type_hint == "int"

    def test_extracts_methods(self):
        st = _extract(Language.JAVA, """\
class Circle {
    int area() { return 0; }
}
""")
        assert "area" in st.classes["Circle"].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.JAVA, """\
class Circle {
    static int COUNT = 0;
}
""")
        assert "COUNT" in st.classes["Circle"].constants

    def test_extracts_parents(self):
        st = _extract(Language.JAVA, """\
class Shape {}
class Circle extends Shape {
    int radius;
}
""")
        assert "Shape" in st.classes["Circle"].parents
```

- [ ] **Step 2: Implement Java extractor**

Add `extract_java_symbols(root) -> SymbolTable` to `interpreter/frontends/java/declarations.py`. Same pattern as C# but:
- Java uses `variable_declarator` directly under `field_declaration` (field name via `name` field)
- Static modifier is in `modifiers` node containing `static`
- Parents via `superclass` node (extract identifier text)
- Method params from `formal_parameters` → `formal_parameter` → `name`

Override in `interpreter/frontends/java/frontend.py`:
```python
    def _extract_symbols(self, root) -> SymbolTable:
        return extract_java_symbols(root)
```

- [ ] **Step 3: Run tests, commit**

```bash
poetry run python -m black .
git add interpreter/frontends/java/declarations.py interpreter/frontends/java/frontend.py tests/unit/test_symbol_extraction.py
git commit -m "feat: Java symbol extraction — _extract_symbols populates SymbolTable (TDD)"
```

---

### Task 3: C++ symbol extraction (TDD)

**Files:**
- Modify: `interpreter/frontends/cpp/declarations.py`
- Modify: `interpreter/frontends/cpp/frontend.py`
- Modify: `tests/unit/test_symbol_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_symbol_extraction.py`:

```python
class TestCppSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.CPP, """\
class Circle {
    int radius;
    Circle(int r) { radius = r; }
    int area() { return 0; }
};
""")
        assert "Circle" in st.classes
        ci = st.classes["Circle"]
        assert "radius" in ci.fields

    def test_extracts_methods(self):
        st = _extract(Language.CPP, """\
class Circle {
    int area() { return 0; }
};
""")
        assert "area" in st.classes["Circle"].methods

    def test_extracts_parents(self):
        st = _extract(Language.CPP, """\
class Shape {};
class Circle : public Shape {
    int radius;
};
""")
        assert "Shape" in st.classes["Circle"].parents
```

- [ ] **Step 2: Implement C++ extractor**

Add `extract_cpp_symbols(root) -> SymbolTable` to `interpreter/frontends/cpp/declarations.py`. C++ specifics:
- Class node is `class_specifier`
- Fields use `field_identifier` (not `variable_declarator`)
- Methods are `function_definition` nodes
- Parents via `base_class_clause` → identifiers
- Static via `storage_class_specifier` containing `static`

Override in `interpreter/frontends/cpp/frontend.py`:
```python
    def _extract_symbols(self, root) -> SymbolTable:
        return extract_cpp_symbols(root)
```

- [ ] **Step 3: Run tests, commit**

```bash
poetry run python -m black .
git add interpreter/frontends/cpp/declarations.py interpreter/frontends/cpp/frontend.py tests/unit/test_symbol_extraction.py
git commit -m "feat: C++ symbol extraction — _extract_symbols populates SymbolTable (TDD)"
```

---

### Task 4: Python symbol extraction (TDD)

**Files:**
- Modify: `interpreter/frontends/python/declarations.py` (or create `interpreter/frontends/python/symbol_extraction.py` if declarations.py is large)
- Modify: `interpreter/frontends/python/frontend.py`
- Modify: `tests/unit/test_symbol_extraction.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_symbol_extraction.py`:

```python
class TestPythonSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.PYTHON, """\
class Circle:
    def __init__(self, radius):
        self.radius = radius
    def area(self):
        return self.radius * self.radius
""")
        assert "Circle" in st.classes
        ci = st.classes["Circle"]
        assert "radius" in ci.fields

    def test_extracts_methods(self):
        st = _extract(Language.PYTHON, """\
class Circle:
    def area(self):
        return 0
""")
        assert "area" in st.classes["Circle"].methods

    def test_extracts_class_constants(self):
        st = _extract(Language.PYTHON, """\
class Circle:
    COUNT = 0
    PI = 3.14
""")
        assert "COUNT" in st.classes["Circle"].constants
        assert "PI" in st.classes["Circle"].constants

    def test_extracts_match_args(self):
        st = _extract(Language.PYTHON, """\
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y
""")
        assert st.classes["Point"].match_args == ("x", "y")

    def test_extracts_parents(self):
        st = _extract(Language.PYTHON, """\
class Shape:
    pass
class Circle(Shape):
    pass
""")
        assert "Shape" in st.classes["Circle"].parents
```

- [ ] **Step 2: Implement Python extractor**

Python is different from the other three:
- Class node is `class_definition`
- Fields come from `self.x = ...` assignments inside `__init__` method body
- Class-body `assignment` nodes (not `self.`) are constants
- `__match_args__ = ("x", "y")` is a special assignment — extract tuple string elements
- Methods are `function_definition` nodes in class body
- Parents via `argument_list` in class definition header

Add `extract_python_symbols(root) -> SymbolTable` in a suitable location. For `self.x` field extraction:
1. Find `function_definition` named `__init__` in class body
2. Walk its body for `assignment` nodes where left side is `attribute` with object `self`
3. Extract the attribute name

For `__match_args__`:
1. Find `assignment` in class body where left is `identifier("__match_args__")`
2. Right side is `tuple` containing `string` nodes
3. Extract `string_content` text from each

Override in `interpreter/frontends/python/frontend.py`:
```python
    def _extract_symbols(self, root) -> SymbolTable:
        return extract_python_symbols(root)
```

- [ ] **Step 3: Run tests, commit**

```bash
poetry run python -m black .
git add interpreter/frontends/python/ tests/unit/test_symbol_extraction.py
git commit -m "feat: Python symbol extraction with __match_args__ support (TDD)"
```

---

### Task 5: Full test suite + push

- [ ] **Step 1: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All pass, no regressions (purely additive — no code consumes the symbol table yet).

- [ ] **Step 3: Push**

```bash
git push origin main
```
