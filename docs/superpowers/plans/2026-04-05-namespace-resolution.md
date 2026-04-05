# Namespace Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate cascading `SymbolicValue` chains from fully-qualified Java references (e.g. `java.util.Arrays.fill(arr, val)`) by teaching the frontend to resolve namespace paths through a tree and emit `LoadVar(short_name)` instead of `LOAD_VAR "java"` → `LOAD_FIELD "util"` → `LOAD_FIELD "Arrays"` chains.

**Architecture:** A `NamespaceTree` maps dotted package paths to type nodes. An injectable `NamespaceResolver` strategy on `TreeSitterEmitContext` intercepts `lower_field_access` calls, walks the tree, and emits `LoadVar(short_name)` at the type join point. The tree is built during `compile_directory()` from a fast pre-scan of source files + the existing stdlib stub registry.

**Tech Stack:** Python 3.13+, tree-sitter (Java grammar), existing `ModuleUnit`/`ExportTable`/`ClassRef` infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-05-namespace-resolution-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `interpreter/namespace.py` | `NamespaceNode`, `NamespaceType`, `NamespaceTree`, `NamespaceResolver` base, sentinels |
| Create | `interpreter/frontends/java/namespace.py` | `JavaNamespaceResolver`, `JavaPreScanResult`, `java_pre_scan()`, `build_java_namespace_tree()` |
| Modify | `interpreter/frontends/context.py:107-174` | Add `namespace_resolver` field to `TreeSitterEmitContext` |
| Modify | `interpreter/frontends/_base.py:338-363` | Pass `namespace_resolver` through `_lower_with_context()` and `lower()` |
| Modify | `interpreter/frontends/java/expressions.py:128-142` | Prepend resolver call in `lower_field_access` |
| Modify | `interpreter/project/compiler.py:75-111` | Add `namespace_resolver` param to `compile_module()` |
| Modify | `interpreter/project/compiler.py:136-197` | Add pre-scan + tree build + patch to `compile_directory()` |
| Create | `tests/unit/test_namespace.py` | Unit tests for `NamespaceTree` |
| Create | `tests/unit/test_java_namespace.py` | Unit tests for pre-scan, tree builder, resolver |
| Create | `tests/integration/project/test_java_namespace_resolution.py` | End-to-end integration test |

---

### Task 1: NamespaceNode, NamespaceType, NamespaceTree data structures

**Files:**
- Create: `interpreter/namespace.py`
- Create: `tests/unit/test_namespace.py`

- [ ] **Step 1: Write the failing test for NamespaceTree.resolve()**

```python
# tests/unit/test_namespace.py
"""Tests for namespace tree data structures and resolution algorithm."""

from __future__ import annotations

from interpreter.namespace import (
    NamespaceNode,
    NamespaceTree,
    NamespaceType,
)
from interpreter.refs.class_ref import NO_CLASS_REF


class TestNamespaceTreeResolve:
    def test_resolve_type_at_leaf(self):
        """java.util.Arrays → (NamespaceType('Arrays'), [], 'java.util.Arrays')."""
        tree = NamespaceTree()
        ns_type = NamespaceType(short_name="Arrays")
        tree.register_type("java.util.Arrays", ns_type)

        resolved, remaining, qualified = tree.resolve(["java", "util", "Arrays"])
        assert resolved is ns_type
        assert remaining == []
        assert qualified == "java.util.Arrays"

    def test_resolve_type_with_remaining_chain(self):
        """java.util.Arrays.fill → (NamespaceType, ['fill'], ...)."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(
            ["java", "util", "Arrays", "fill"]
        )
        assert resolved is not None
        assert resolved.short_name == "Arrays"
        assert remaining == ["fill"]
        assert qualified == "java.util.Arrays"

    def test_resolve_no_match(self):
        """com.unknown.Foo → (None, original_chain, '')."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(["com", "unknown", "Foo"])
        assert resolved is None
        assert remaining == ["com", "unknown", "Foo"]
        assert qualified == ""

    def test_resolve_partial_namespace_no_type(self):
        """java.util → no type at 'util', returns None."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        resolved, remaining, qualified = tree.resolve(["java", "util"])
        assert resolved is None

    def test_register_multiple_types_same_namespace(self):
        """java.util has both Arrays and ArrayList."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        tree.register_type(
            "java.util.ArrayList", NamespaceType(short_name="ArrayList")
        )

        r1, _, _ = tree.resolve(["java", "util", "Arrays"])
        r2, _, _ = tree.resolve(["java", "util", "ArrayList"])
        assert r1 is not None and r1.short_name == "Arrays"
        assert r2 is not None and r2.short_name == "ArrayList"

    def test_resolve_single_segment_type(self):
        """String at root → (NamespaceType, [], 'String')."""
        tree = NamespaceTree()
        tree.register_type("String", NamespaceType(short_name="String"))

        resolved, remaining, qualified = tree.resolve(["String"])
        assert resolved is not None
        assert resolved.short_name == "String"
        assert remaining == []

    def test_empty_chain_returns_none(self):
        tree = NamespaceTree()
        resolved, remaining, qualified = tree.resolve([])
        assert resolved is None


class TestNamespaceTreeRegister:
    def test_register_creates_intermediate_nodes(self):
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))

        assert "java" in tree.root.children
        assert "util" in tree.root.children["java"].children
        assert "Arrays" in tree.root.children["java"].children["util"].types

    def test_register_preserves_class_ref(self):
        from interpreter.refs.class_ref import ClassRef
        from interpreter.class_name import ClassName
        from interpreter.ir import CodeLabel

        ref = ClassRef(
            name=ClassName("Arrays"),
            label=CodeLabel("class_Arrays_0"),
            parents=(),
        )
        ns_type = NamespaceType(short_name="Arrays", class_ref=ref)
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", ns_type)

        resolved, _, _ = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.class_ref is ref
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_namespace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.namespace'`

- [ ] **Step 3: Implement NamespaceNode, NamespaceType, NamespaceTree**

```python
# interpreter/namespace.py
"""Namespace tree for resolving qualified references (e.g. java.util.Arrays).

The tree maps dotted package paths to type nodes. The resolution algorithm
is shared across languages; language-specific behavior comes from the seed
(what's in the tree), not the walk (how we traverse it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interpreter.project.types import ModuleUnit
from interpreter.refs.class_ref import ClassRef, NO_CLASS_REF


@dataclass
class NamespaceType:
    """A type reachable through namespace resolution."""

    short_name: str  # "Arrays" — used by frontend for LoadVar
    class_ref: ClassRef = NO_CLASS_REF  # sentinel initially; patched post-compile
    module: ModuleUnit | None = None  # stub ModuleUnit, if one exists


@dataclass
class NamespaceNode:
    """A node in the package/namespace hierarchy."""

    children: dict[str, NamespaceNode] = field(default_factory=dict)
    types: dict[str, NamespaceType] = field(default_factory=dict)


class NamespaceTree:
    """Package → Type mapping consulted during frontend lowering.

    Resolution algorithm (mirrors JLS §6.5): walk segments from root,
    descending into child namespaces until a type node is found. Returns
    the type, any remaining chain segments, and the qualified name.
    """

    def __init__(self) -> None:
        self.root = NamespaceNode()

    def resolve(
        self, chain: list[str]
    ) -> tuple[NamespaceType | None, list[str], str]:
        """Walk the tree to find the type join point.

        Returns:
            (resolved_type, remaining_chain, qualified_name)
            or (None, original_chain, "") if no match.
        """
        if not chain:
            return None, chain, ""
        node = self.root
        for i, segment in enumerate(chain):
            if segment in node.types:
                qualified = ".".join(chain[: i + 1])
                return node.types[segment], chain[i + 1 :], qualified
            if segment in node.children:
                node = node.children[segment]
                continue
            break
        return None, chain, ""

    def register_type(self, dotted_path: str, ns_type: NamespaceType) -> None:
        """Register a type at the given dotted path.

        E.g. register_type("java.util.Arrays", ...) creates java → util
        namespace nodes and registers Arrays as a type under util.
        """
        parts = dotted_path.split(".")
        node = self.root
        for part in parts[:-1]:
            if part not in node.children:
                node.children[part] = NamespaceNode()
            node = node.children[part]
        node.types[parts[-1]] = ns_type
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_namespace.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/namespace.py tests/unit/test_namespace.py
git commit -m "feat: add NamespaceTree data structures for qualified name resolution"
```

---

### Task 2: NamespaceResolver base class and sentinel objects

**Files:**
- Modify: `interpreter/namespace.py`
- Modify: `tests/unit/test_namespace.py`

- [ ] **Step 1: Write the failing test for sentinels and base resolver**

Append to `tests/unit/test_namespace.py`:

```python
from interpreter.namespace import (
    NamespaceResolver,
    NO_RESOLUTION,
    NO_CHAIN,
)
from interpreter.register import Register


class TestNamespaceResolverBase:
    def test_base_resolver_returns_no_resolution(self):
        resolver = NamespaceResolver()
        result = resolver.try_resolve_field_access(None, None)
        assert result is NO_RESOLUTION

    def test_no_resolution_is_falsy(self):
        assert not NO_RESOLUTION

    def test_no_chain_is_falsy(self):
        assert not NO_CHAIN

    def test_register_is_not_no_resolution(self):
        reg = Register("%0")
        assert reg is not NO_RESOLUTION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_namespace.py::TestNamespaceResolverBase -v`
Expected: FAIL — `ImportError: cannot import name 'NamespaceResolver'`

- [ ] **Step 3: Implement NamespaceResolver, NO_RESOLUTION, NO_CHAIN**

Add to `interpreter/namespace.py` after the `NamespaceTree` class:

```python
from interpreter.register import Register


class _NoResolution:
    """Sentinel: resolver did not handle this field_access."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NO_RESOLUTION"


class _NoChain:
    """Sentinel: node isn't a pure identifier chain."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NO_CHAIN"


NO_RESOLUTION: _NoResolution | Register = _NoResolution()
NO_CHAIN: _NoChain | list[str] = _NoChain()


class NamespaceResolver:
    """Base: no-op resolver for languages without namespace resolution."""

    def try_resolve_field_access(
        self, ctx: TreeSitterEmitContext | None, node: object
    ) -> Register | _NoResolution:
        return NO_RESOLUTION  # type: ignore[return-value]
```

Note: The `TreeSitterEmitContext` forward reference uses `from __future__ import annotations` (already at top of file). Add the import:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_namespace.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/namespace.py tests/unit/test_namespace.py
git commit -m "feat: add NamespaceResolver base class and sentinel objects"
```

---

### Task 3: Add `namespace_resolver` field to TreeSitterEmitContext

**Files:**
- Modify: `interpreter/frontends/context.py:107-174`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_namespace.py — append

from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.constants import Language
from interpreter.frontends._base import NullFrontendObserver


class TestContextNamespaceResolver:
    def test_default_resolver_is_base(self):
        ctx = TreeSitterEmitContext(
            source=b"",
            language=Language.JAVA,
            observer=NullFrontendObserver(),
            constants=GrammarConstants(),
        )
        assert isinstance(ctx.namespace_resolver, NamespaceResolver)
        assert ctx.namespace_resolver.try_resolve_field_access(ctx, None) is NO_RESOLUTION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_namespace.py::TestContextNamespaceResolver -v`
Expected: FAIL — `TreeSitterEmitContext.__init__() ... unexpected keyword argument 'namespace_resolver'` or `AttributeError: 'TreeSitterEmitContext' object has no attribute 'namespace_resolver'`

- [ ] **Step 3: Add namespace_resolver field to TreeSitterEmitContext**

In `interpreter/frontends/context.py`, add the import near the top:

```python
from interpreter.namespace import NamespaceResolver
```

Then add the field after `_method_declared_names` (line 168):

```python
    # Namespace resolver — injectable strategy for qualified name resolution
    namespace_resolver: NamespaceResolver = field(default_factory=NamespaceResolver)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_namespace.py::TestContextNamespaceResolver -v`
Expected: PASS

Run: `poetry run python -m pytest tests/unit/test_namespace.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/context.py tests/unit/test_namespace.py
git commit -m "feat: add namespace_resolver field to TreeSitterEmitContext"
```

---

### Task 4: Thread namespace_resolver through lower() and compile_module()

**Files:**
- Modify: `interpreter/frontends/_base.py:338-363`
- Modify: `interpreter/project/compiler.py:75-111`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_namespace.py — append

from interpreter.project.compiler import compile_module
from interpreter.constants import Language
from pathlib import Path
import tempfile


class TestCompileModuleNamespaceResolver:
    def test_compile_module_accepts_namespace_resolver(self):
        """compile_module() should accept an optional namespace_resolver param."""
        java_src = "class Foo { }"
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False) as f:
            f.write(java_src)
            f.flush()
            path = Path(f.name)

        resolver = NamespaceResolver()
        module = compile_module(path, Language.JAVA, namespace_resolver=resolver)
        assert module is not None
        path.unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_namespace.py::TestCompileModuleNamespaceResolver -v`
Expected: FAIL — `TypeError: compile_module() got an unexpected keyword argument 'namespace_resolver'`

- [ ] **Step 3: Add namespace_resolver param to compile_module() and BaseFrontend.lower()**

**`interpreter/project/compiler.py`** — modify `compile_module()` signature and body:

```python
from interpreter.namespace import NamespaceResolver

def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
    namespace_resolver: NamespaceResolver | None = None,
) -> ModuleUnit:
    # ... existing code until frontend.lower(source) ...
    ir = frontend.lower(source, namespace_resolver=namespace_resolver)
    # ... rest unchanged ...
```

**`interpreter/frontends/_base.py`** — modify `lower()` and `_lower_with_context()`:

```python
from interpreter.namespace import NamespaceResolver

# In lower():
def lower(
    self, source: bytes, namespace_resolver: NamespaceResolver | None = None
) -> list[InstructionBase]:
    # ... existing parse code ...
    if grammar_constants is not None:
        result = self._lower_with_context(source, root, namespace_resolver)
    else:
        # ... legacy path unchanged ...

# In _lower_with_context():
def _lower_with_context(
    self,
    source: bytes,
    root: Any,
    namespace_resolver: NamespaceResolver | None = None,
) -> list[InstructionBase]:
    grammar_constants = self._build_constants()
    symbol_table = self._extract_symbols(root)
    ctx = TreeSitterEmitContext(
        source=source,
        language=self._language,
        observer=self._observer,
        constants=grammar_constants,
        type_map=self._build_type_map(),
        stmt_dispatch=self._build_stmt_dispatch(),
        expr_dispatch=self._build_expr_dispatch(),
        block_scoped=self.BLOCK_SCOPED,
        symbol_table=symbol_table,
        **({"namespace_resolver": namespace_resolver} if namespace_resolver else {}),
    )
    # ... rest unchanged ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_namespace.py -v`
Expected: All PASS

Run: `poetry run python -m pytest tests/unit/test_java_frontend.py -v`
Expected: All PASS (no regression)

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/_base.py interpreter/project/compiler.py tests/unit/test_namespace.py
git commit -m "feat: thread namespace_resolver through lower() and compile_module()"
```

---

### Task 5: Java pre-scan — extract package + class names from source

**Files:**
- Create: `interpreter/frontends/java/namespace.py`
- Create: `tests/unit/test_java_namespace.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_java_namespace.py
"""Tests for Java namespace resolution: pre-scan, tree builder, resolver."""

from __future__ import annotations

from interpreter.frontends.java.namespace import (
    JavaPreScanResult,
    java_pre_scan,
)


class TestJavaPreScan:
    def test_single_class_with_package(self):
        source = b"""
package com.example;
public class Helper { }
"""
        result = java_pre_scan(source)
        assert result.package == "com.example"
        assert result.class_names == ["Helper"]

    def test_multiple_classes(self):
        source = b"""
package com.test;
class Foo { }
interface Bar { }
enum Baz { }
"""
        result = java_pre_scan(source)
        assert result.package == "com.test"
        assert sorted(result.class_names) == ["Bar", "Baz", "Foo"]

    def test_no_package(self):
        source = b"class Main { }"
        result = java_pre_scan(source)
        assert result.package is None
        assert result.class_names == ["Main"]

    def test_imports_extracted(self):
        source = b"""
package com.test;
import java.util.Arrays;
import java.io.*;
class Main { }
"""
        result = java_pre_scan(source)
        assert len(result.imports) == 2
        assert any("java.util.Arrays" in str(imp) for imp in result.imports)

    def test_record_declaration(self):
        source = b"""
package com.dto;
record Point(int x, int y) { }
"""
        result = java_pre_scan(source)
        assert result.class_names == ["Point"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestJavaPreScan -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.frontends.java.namespace'`

- [ ] **Step 3: Implement java_pre_scan()**

```python
# interpreter/frontends/java/namespace.py
"""Java-specific namespace resolution: pre-scan, tree builder, resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from interpreter.parser import TreeSitterParserFactory
from interpreter.project.types import ImportRef

if TYPE_CHECKING:
    pass

# Node types that declare types at the top level
_TYPE_DECLARATION_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)

_PARSER_FACTORY = TreeSitterParserFactory()


@dataclass
class JavaPreScanResult:
    """Pre-scan output for a single Java source file."""

    package: str | None = None
    class_names: list[str] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)


def java_pre_scan(source: bytes) -> JavaPreScanResult:
    """Fast tree-sitter extraction of package + class names + imports.

    Walks only top-level nodes — no expression lowering, no control flow.
    """
    parser = _PARSER_FACTORY.get_parser("java")
    tree = parser.parse(source)
    root = tree.root_node

    result = JavaPreScanResult()

    for child in root.children:
        if child.type == "package_declaration":
            # package com.example;  →  scoped_identifier or identifier
            name_node = child.child_by_field_name("name") or _first_named_child(child)
            if name_node is not None:
                result.package = source[name_node.start_byte : name_node.end_byte].decode()

        elif child.type in _TYPE_DECLARATION_TYPES:
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                result.class_names.append(
                    source[name_node.start_byte : name_node.end_byte].decode()
                )

        elif child.type == "import_declaration":
            _extract_import(child, source, result)

    return result


def _first_named_child(node: object) -> object | None:
    """Return the first named child of a tree-sitter node."""
    for child in node.children:  # type: ignore[attr-defined]
        if child.is_named:
            return child
    return None


def _extract_import(node: object, source: bytes, result: JavaPreScanResult) -> None:
    """Extract an ImportRef from an import_declaration node."""
    text = source[node.start_byte : node.end_byte].decode().strip()  # type: ignore[attr-defined]
    # import java.util.Arrays;  or  import java.io.*;
    text = text.removeprefix("import").strip().rstrip(";").strip()
    is_static = text.startswith("static ")
    if is_static:
        text = text.removeprefix("static").strip()

    if text.endswith(".*"):
        module_path = text[:-2]
        names = ("*",)
    else:
        parts = text.rsplit(".", 1)
        if len(parts) == 2:
            module_path, name = parts
            names = (name,)
        else:
            module_path = text
            names = ()

    result.imports.append(
        ImportRef(module_path=module_path, names=names, is_system=True)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestJavaPreScan -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/java/namespace.py tests/unit/test_java_namespace.py
git commit -m "feat: add java_pre_scan() for fast package/class extraction"
```

---

### Task 6: build_java_namespace_tree() — populate tree from stubs + pre-scan

**Files:**
- Modify: `interpreter/frontends/java/namespace.py`
- Modify: `tests/unit/test_java_namespace.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_java_namespace.py`:

```python
from pathlib import Path

from interpreter.frontends.java.namespace import build_java_namespace_tree
from interpreter.namespace import NamespaceType
from interpreter.refs.class_ref import NO_CLASS_REF, ClassRef
from interpreter.class_name import ClassName
from interpreter.ir import CodeLabel
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.constants import Language


def _make_stub_module(class_name: str, label_str: str) -> ModuleUnit:
    """Minimal stub ModuleUnit for testing."""
    from interpreter.instructions import Label_, Branch, Const, DeclVar
    from interpreter.register import Register
    from interpreter.var_name import VarName

    cls_label = f"class_{class_name}_0"
    end_label = f"end_class_{class_name}_1"
    return ModuleUnit(
        path=Path(f"stub/{class_name}.java"),
        language=Language.JAVA,
        ir=(
            Label_(label=CodeLabel(f"entry_{class_name}")),
            Branch(label=CodeLabel(end_label)),
            Label_(label=CodeLabel(cls_label)),
            Label_(label=CodeLabel(end_label)),
            Const(result_reg=Register("%0"), value=cls_label),
            DeclVar(name=VarName(class_name), value_reg=Register("%0")),
        ),
        exports=ExportTable(
            classes={ClassName(class_name): CodeLabel(cls_label)},
        ),
        imports=(),
    )


class TestBuildJavaNamespaceTree:
    def test_stub_registry_populates_tree(self):
        stub = _make_stub_module("Arrays", "class_Arrays_0")
        registry = {Path("java/util/Arrays.java"): stub}

        tree = build_java_namespace_tree(
            scan_results={},
            stdlib_registry=registry,
        )

        resolved, remaining, qualified = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.short_name == "Arrays"
        assert resolved.module is stub
        assert remaining == []

    def test_project_classes_populate_tree(self):
        scan_results = {
            Path("/proj/Helper.java"): JavaPreScanResult(
                package="com.test", class_names=["Helper"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry={},
        )

        resolved, _, _ = tree.resolve(["com", "test", "Helper"])
        assert resolved is not None
        assert resolved.short_name == "Helper"
        assert resolved.class_ref is NO_CLASS_REF  # not yet patched
        assert resolved.module is None

    def test_project_class_overrides_stub(self):
        stub = _make_stub_module("Arrays", "class_Arrays_0")
        registry = {Path("java/util/Arrays.java"): stub}
        scan_results = {
            Path("/proj/Arrays.java"): JavaPreScanResult(
                package="java.util", class_names=["Arrays"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry=registry,
        )

        resolved, _, _ = tree.resolve(["java", "util", "Arrays"])
        assert resolved is not None
        assert resolved.module is None  # project override, not stub

    def test_no_package_class_not_registered(self):
        """Classes without a package are not registered in namespace tree."""
        scan_results = {
            Path("/proj/Main.java"): JavaPreScanResult(
                package=None, class_names=["Main"]
            ),
        }

        tree = build_java_namespace_tree(
            scan_results=scan_results,
            stdlib_registry={},
        )

        resolved, _, _ = tree.resolve(["Main"])
        assert resolved is None  # no package → not in namespace tree
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestBuildJavaNamespaceTree -v`
Expected: FAIL — `ImportError: cannot import name 'build_java_namespace_tree'`

- [ ] **Step 3: Implement build_java_namespace_tree()**

Add to `interpreter/frontends/java/namespace.py`:

```python
from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.namespace import NamespaceTree, NamespaceType
from interpreter.project.types import ModuleUnit
from interpreter.refs.class_ref import NO_CLASS_REF


def build_java_namespace_tree(
    scan_results: dict[Path, JavaPreScanResult],
    stdlib_registry: dict[Path, ModuleUnit],
) -> NamespaceTree:
    """Build namespace tree from stub registry + pre-scanned project classes.

    Stubs are registered first. Project classes override stubs at the
    same path (local wins).
    """
    tree = NamespaceTree()

    # Source 1: Stub registry — types with real ModuleUnits
    for stub_path, module in stdlib_registry.items():
        dotted = _path_to_dotted(stub_path)
        short_name = dotted.rsplit(".", 1)[-1]

        # Extract ClassRef from stub's exports if available
        class_ref = NO_CLASS_REF
        for cls_name, cls_label in module.exports.classes.items():
            if cls_name.value == short_name:
                class_ref = module.exports.classes[cls_name]
                # We need the actual ClassRef, not CodeLabel — construct from exports
                from interpreter.refs.class_ref import ClassRef as ClassRefType

                class_ref = ClassRefType(
                    name=cls_name, label=cls_label, parents=()
                )
                break

        tree.register_type(
            dotted,
            NamespaceType(short_name=short_name, class_ref=class_ref, module=module),
        )

    # Source 2: Project classes — short_name only, ClassRef = NO_CLASS_REF
    for file_path, scan in scan_results.items():
        if scan.package is None:
            continue  # no package → not addressable via qualified name
        for class_name in scan.class_names:
            dotted = f"{scan.package}.{class_name}"
            tree.register_type(
                dotted,
                NamespaceType(short_name=class_name, class_ref=NO_CLASS_REF),
            )

    return tree


def _path_to_dotted(path: Path) -> str:
    """Convert stub path to dotted name: java/util/Arrays.java → java.util.Arrays."""
    return ".".join(path.with_suffix("").parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/java/namespace.py tests/unit/test_java_namespace.py
git commit -m "feat: add build_java_namespace_tree() from stubs + pre-scan"
```

---

### Task 7: JavaNamespaceResolver — chain collection + resolution + emission

**Files:**
- Modify: `interpreter/frontends/java/namespace.py`
- Modify: `tests/unit/test_java_namespace.py`

- [ ] **Step 1: Write the failing test for _collect_field_access_chain**

Append to `tests/unit/test_java_namespace.py`:

```python
from interpreter.frontends.java.namespace import (
    JavaNamespaceResolver,
    _collect_field_access_chain,
)
from interpreter.namespace import NO_CHAIN, NO_RESOLUTION
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontends._base import NullFrontendObserver
from interpreter.frontends.java.node_types import JavaNodeType
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import Opcode


_PARSER = TreeSitterParserFactory()


def _parse_expr_node(java_expr: str):
    """Parse a Java expression and return the root expression node."""
    source = f"class X {{ void m() {{ {java_expr}; }} }}".encode()
    parser = _PARSER.get_parser("java")
    tree = parser.parse(source)
    # Navigate: program > class_declaration > class_body > method_declaration
    #   > method body (block) > expression_statement > expression
    cls = tree.root_node.children[0]
    body = cls.child_by_field_name("body")
    method = [c for c in body.children if c.type == "method_declaration"][0]
    block = method.child_by_field_name("body")
    expr_stmt = [c for c in block.children if c.type == "expression_statement"][0]
    return expr_stmt.children[0], source


def _make_java_ctx(source: bytes, resolver=None) -> TreeSitterEmitContext:
    from interpreter.frontends.java.frontend import JavaFrontend

    frontend = JavaFrontend(_PARSER, "java")
    constants = frontend._build_constants()
    ctx = TreeSitterEmitContext(
        source=source,
        language=Language.JAVA,
        observer=NullFrontendObserver(),
        constants=constants,
        **({"namespace_resolver": resolver} if resolver else {}),
    )
    return ctx


class TestCollectFieldAccessChain:
    def test_simple_chain(self):
        """java.util.Arrays → ['java', 'util', 'Arrays']."""
        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain == ["java", "util", "Arrays"]

    def test_deeper_chain(self):
        """java.util.Arrays.fill → ['java', 'util', 'Arrays', 'fill']."""
        node, source = _parse_expr_node("java.util.Arrays.fill")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain == ["java", "util", "Arrays", "fill"]

    def test_non_identifier_root_returns_no_chain(self):
        """this.field → NO_CHAIN (root is 'this', not identifier)."""
        node, source = _parse_expr_node("this.field")
        ctx = _make_java_ctx(source)
        chain = _collect_field_access_chain(ctx, node)
        assert chain is NO_CHAIN


class TestJavaNamespaceResolver:
    def test_resolve_qualified_type(self):
        """java.util.Arrays → LoadVar('Arrays')."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is not NO_RESOLUTION
        # Verify emitted instructions
        load_vars = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_VAR]
        assert len(load_vars) == 1
        assert load_vars[0].name.value == "Arrays"

    def test_resolve_with_remaining_field(self):
        """java.sql.Types.VARCHAR → LoadVar('Types') + LoadField('VARCHAR')."""
        tree = NamespaceTree()
        tree.register_type("java.sql.Types", NamespaceType(short_name="Types"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.sql.Types.VARCHAR")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is not NO_RESOLUTION
        load_vars = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_VAR]
        load_fields = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_vars) == 1
        assert load_vars[0].name.value == "Types"
        assert len(load_fields) == 1
        assert load_fields[0].field_name.value == "VARCHAR"

    def test_declared_local_skips_resolution(self):
        """If 'java' is a local variable, skip namespace resolution."""
        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("java.util.Arrays")
        ctx = _make_java_ctx(source, resolver)
        ctx._method_declared_names.add("java")

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is NO_RESOLUTION

    def test_no_tree_match_falls_through(self):
        """com.unknown.Foo → NO_RESOLUTION."""
        tree = NamespaceTree()
        resolver = JavaNamespaceResolver(tree)

        node, source = _parse_expr_node("com.unknown.Foo")
        ctx = _make_java_ctx(source, resolver)

        result = resolver.try_resolve_field_access(ctx, node)
        assert result is NO_RESOLUTION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestCollectFieldAccessChain -v`
Expected: FAIL — `ImportError: cannot import name '_collect_field_access_chain'`

- [ ] **Step 3: Implement JavaNamespaceResolver + helpers**

Add to `interpreter/frontends/java/namespace.py`:

```python
from interpreter.field_name import FieldName
from interpreter.instructions import LoadField, LoadVar
from interpreter.namespace import (
    NO_CHAIN,
    NO_RESOLUTION,
    NamespaceResolver,
    NamespaceTree,
    _NoChain,
    _NoResolution,
)
from interpreter.register import Register
from interpreter.var_name import VarName

if TYPE_CHECKING:
    from interpreter.frontends.context import TreeSitterEmitContext


def _collect_field_access_chain(
    ctx: TreeSitterEmitContext, node: object
) -> list[str] | _NoChain:
    """Walk nested field_access to collect ['java', 'util', 'Arrays'].

    Returns NO_CHAIN if root isn't a plain identifier.
    """
    segments: list[str] = []
    while node.type == "field_access":  # type: ignore[attr-defined]
        field_node = node.child_by_field_name("field")  # type: ignore[attr-defined]
        segments.append(ctx.node_text(field_node))
        node = node.child_by_field_name(ctx.constants.attr_object_field)  # type: ignore[attr-defined]
    if node.type == "identifier":  # type: ignore[attr-defined]
        segments.append(ctx.node_text(node))
        segments.reverse()
        return segments
    return NO_CHAIN  # type: ignore[return-value]


def _lower_remaining_chain(
    ctx: TreeSitterEmitContext,
    base_reg: Register,
    remaining: list[str],
    node: object,
) -> Register:
    """Emit LoadField for each segment after the type join point."""
    reg = base_reg
    for segment in remaining:
        next_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=next_reg,
                obj_reg=reg,
                field_name=FieldName(segment),
            ),
            node=node,
        )
        reg = next_reg
    return reg


class JavaNamespaceResolver(NamespaceResolver):
    """Java-specific: resolves field_access chains through namespace tree."""

    def __init__(self, tree: NamespaceTree) -> None:
        self.tree = tree

    def try_resolve_field_access(
        self, ctx: TreeSitterEmitContext, node: object
    ) -> Register | _NoResolution:
        chain = _collect_field_access_chain(ctx, node)
        if chain is NO_CHAIN:
            return NO_RESOLUTION  # type: ignore[return-value]

        root = chain[0]  # type: ignore[index]
        if root in ctx._method_declared_names:
            return NO_RESOLUTION  # type: ignore[return-value]

        ns_type, remaining, qualified_name = self.tree.resolve(chain)  # type: ignore[arg-type]
        if ns_type is None:
            return NO_RESOLUTION  # type: ignore[return-value]

        # Emit LoadVar for the resolved type's short name
        type_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=type_reg, name=VarName(ns_type.short_name)),
            node=node,
        )
        return _lower_remaining_chain(ctx, type_reg, remaining, node)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/java/namespace.py tests/unit/test_java_namespace.py
git commit -m "feat: add JavaNamespaceResolver with chain collection and resolution"
```

---

### Task 8: Wire resolver into lower_field_access

**Files:**
- Modify: `interpreter/frontends/java/expressions.py:128-142`
- Modify: `tests/unit/test_java_namespace.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_java_namespace.py`:

```python
class TestFieldAccessWithResolver:
    def test_qualified_reference_emits_load_var(self):
        """Full pipeline: java.util.Arrays resolves to LoadVar('Arrays')."""
        from interpreter.frontends.java.frontend import JavaFrontend

        tree = NamespaceTree()
        tree.register_type("java.util.Arrays", NamespaceType(short_name="Arrays"))
        resolver = JavaNamespaceResolver(tree)

        source = b"class X { void m() { java.util.Arrays.fill(arr, 0); } }"
        frontend = JavaFrontend(_PARSER, "java")
        ir = frontend.lower(source, namespace_resolver=resolver)

        # Should have LoadVar("Arrays"), NOT LoadVar("java")
        load_vars = [i for i in ir if i.opcode == Opcode.LOAD_VAR]
        load_var_names = [i.name.value for i in load_vars]
        assert "Arrays" in load_var_names, f"Expected LoadVar('Arrays'), got: {load_var_names}"
        assert "java" not in load_var_names, f"LoadVar('java') should not appear: {load_var_names}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestFieldAccessWithResolver -v`
Expected: FAIL — `LoadVar('java')` appears because `lower_field_access` doesn't call the resolver yet.

- [ ] **Step 3: Add resolver call to lower_field_access**

In `interpreter/frontends/java/expressions.py`, modify `lower_field_access`:

```python
from interpreter.namespace import NO_RESOLUTION


def lower_field_access(
    ctx: TreeSitterEmitContext, node: Any
) -> Register:  # Any: tree-sitter node — untyped at Python boundary
    # Try namespace resolution first
    result = ctx.namespace_resolver.try_resolve_field_access(ctx, node)
    if result is not NO_RESOLUTION:
        return result

    # Existing behavior: recursive lowering
    obj_node = node.child_by_field_name(ctx.constants.attr_object_field)
    field_node = node.child_by_field_name("field")
    if obj_node is None or field_node is None:
        return lower_const_literal(ctx, node)
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)),
        node=node,
    )
    return reg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py -v`
Expected: All PASS

Run: `poetry run python -m pytest tests/unit/test_java_frontend.py -v`
Expected: All PASS (no regression — default resolver is no-op)

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/java/expressions.py tests/unit/test_java_namespace.py
git commit -m "feat: wire namespace resolver into Java lower_field_access"
```

---

### Task 9: Update compile_directory() — pre-scan, build tree, patch, link stubs

**Files:**
- Modify: `interpreter/project/compiler.py:136-197`
- Modify: `tests/unit/test_java_namespace.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_java_namespace.py`:

```python
import tempfile

from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram


class TestCompileDirectoryNamespaceResolution:
    def test_compile_directory_uses_namespace_tree(self, tmp_path):
        """compile_directory() should pre-scan, build tree, and resolve namespaces."""
        # Two-file project: Helper in com.test package, Main uses it qualified
        helper_src = """\
package com.test;
public class Helper {
    public static int add(int a, int b) { return a + b; }
}
"""
        main_src = """\
package com.app;
import com.test.Helper;
public class Main {
    public static void main() {
        int result = com.test.Helper.add(1, 2);
    }
}
"""
        # Maven-style layout
        helper_dir = tmp_path / "src" / "main" / "java" / "com" / "test"
        helper_dir.mkdir(parents=True)
        (helper_dir / "Helper.java").write_text(helper_src)

        main_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        main_dir.mkdir(parents=True)
        (main_dir / "Main.java").write_text(main_src)

        linked = compile_directory(tmp_path, Language.JAVA)
        assert isinstance(linked, LinkedProgram)

        # Verify: LoadVar("Helper") appears, LoadVar("com") does NOT
        load_vars = [
            i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR
        ]
        load_var_names = [i.name.value for i in load_vars]
        assert "Helper" in load_var_names, (
            f"Expected LoadVar('Helper') from namespace resolution, got: {load_var_names}"
        )
        assert "com" not in load_var_names, (
            f"LoadVar('com') should not appear after namespace resolution: {load_var_names}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestCompileDirectoryNamespaceResolution -v`
Expected: FAIL — `compile_directory` doesn't do pre-scan or tree building yet, so `LoadVar("com")` appears.

- [ ] **Step 3: Update compile_directory() with namespace resolution flow**

In `interpreter/project/compiler.py`, add imports and modify the Java branch:

```python
from interpreter.frontends.java.namespace import (
    JavaNamespaceResolver,
    JavaPreScanResult,
    build_java_namespace_tree,
    java_pre_scan,
)
from interpreter.namespace import NamespaceResolver
```

Replace the body of `compile_directory()`:

```python
def compile_directory(
    directory: Path,
    language: Language,
) -> LinkedProgram:
    """Compile all source files in a directory tree."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    # --- Java namespace resolution: pre-scan + build tree ---
    namespace_resolver: NamespaceResolver | None = None
    if language == Language.JAVA:
        scan_results = {path: java_pre_scan(path.read_bytes()) for path in source_files}
        from experiments.java_stdlib.registry import STDLIB_REGISTRY

        tree = build_java_namespace_tree(scan_results, STDLIB_REGISTRY)
        namespace_resolver = JavaNamespaceResolver(tree)

    # --- Compile each module (with namespace resolver if available) ---
    modules = {
        path: compile_module(path, language, namespace_resolver=namespace_resolver)
        for path in source_files
    }

    # Build import graph from modules' resolved imports
    if language == Language.JAVA:
        discovered_roots = MavenSourceRootDiscovery().discover(directory)
        resolver = (
            JavaImportResolver(source_roots=discovered_roots)
            if discovered_roots
            else get_resolver(language)
        )
    else:
        resolver = get_resolver(language)

    import_graph: dict[Path, list[Path]] = {path: [] for path in source_files}
    for path, module in modules.items():
        for ref in module.imports:
            for resolved in resolver.resolve(ref, directory):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target in import_graph and target not in import_graph[path]:
                        import_graph[path].append(target)

    topo_order = topological_sort(import_graph)

    # --- Link: project modules + stub modules ---
    stub_modules: dict[Path, ModuleUnit] = {}
    if language == Language.JAVA:
        for stub_path, stub_module in STDLIB_REGISTRY.items():
            stub_modules[stub_path] = stub_module

    all_modules = {**stub_modules, **modules}

    # Stub modules have no dependencies — add them to import graph with empty deps
    stub_import_graph = {path: [] for path in stub_modules}
    full_import_graph = {**stub_import_graph, **import_graph}

    # Stubs go first in topo order (no deps), then project files
    full_topo_order = list(stub_modules.keys()) + topo_order

    linked = link_modules(
        modules=all_modules,
        import_graph=full_import_graph,
        project_root=directory,
        topo_order=full_topo_order,
        language=language,
    )

    # --- Post-compile: patch ClassRefs for project classes ---
    if language == Language.JAVA and namespace_resolver is not None:
        _patch_namespace_tree_class_refs(
            namespace_resolver.tree,  # type: ignore[attr-defined]
            modules,
        )

    return linked
```

Add the patch helper function:

```python
def _patch_namespace_tree_class_refs(
    tree: NamespaceTree,
    modules: dict[Path, ModuleUnit],
) -> None:
    """Fill in real ClassRefs for project classes from compiled ModuleUnits."""
    from interpreter.namespace import NamespaceTree

    for path, module in modules.items():
        for cls_name, cls_label in module.exports.classes.items():
            # Walk the tree to find the matching NamespaceType
            _patch_type_in_tree(tree, cls_name.value, cls_label)


def _patch_type_in_tree(
    tree: NamespaceTree, class_name: str, class_label: CodeLabel
) -> None:
    """Find a NamespaceType by short_name and patch its ClassRef."""
    from interpreter.refs.class_ref import ClassRef
    from interpreter.class_name import ClassName

    _patch_node(tree.root, class_name, class_label)


def _patch_node(
    node: NamespaceNode, class_name: str, class_label: CodeLabel
) -> bool:
    """Recursively search for a type with matching short_name and patch it."""
    from interpreter.refs.class_ref import ClassRef
    from interpreter.class_name import ClassName
    from interpreter.namespace import NamespaceNode

    for type_name, ns_type in node.types.items():
        if ns_type.short_name == class_name and not ns_type.class_ref.is_present():
            ns_type.class_ref = ClassRef(
                name=ClassName(class_name), label=class_label, parents=()
            )
            return True
    for child in node.children.values():
        if _patch_node(child, class_name, class_label):
            return True
    return False
```

Also add the missing import at the top of compiler.py:

```python
from interpreter.namespace import NamespaceTree, NamespaceNode
from interpreter.ir import CodeLabel
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_java_namespace.py::TestCompileDirectoryNamespaceResolution -v`
Expected: PASS

Run: `poetry run python -m pytest tests/integration/project/test_java_multi_module.py -v`
Expected: All PASS (no regression)

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/compiler.py tests/unit/test_java_namespace.py
git commit -m "feat: add pre-scan + namespace tree to compile_directory() for Java"
```

---

### Task 10: End-to-end integration test — qualified references resolve and execute

**Files:**
- Create: `tests/integration/project/test_java_namespace_resolution.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/project/test_java_namespace_resolution.py
"""End-to-end integration test for Java namespace resolution.

Verifies that fully-qualified Java references (java.util.Arrays, etc.)
produce LoadVar(short_name) instead of cascading LOAD_FIELD chains,
and that the linked program executes correctly with stdlib stubs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.ir import Opcode
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked, EntryPoint


class TestJavaNamespaceResolutionE2E:
    @pytest.fixture
    def qualified_ref_project(self, tmp_path: Path) -> Path:
        """Java project with fully-qualified stdlib references."""
        main_src = """\
package com.app;

public class Main {
    public static void run() {
        double val = java.lang.Math.sqrt(16.0);
    }
}
"""
        main_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        main_dir.mkdir(parents=True)
        (main_dir / "Main.java").write_text(main_src)
        return tmp_path

    def test_no_cascading_load_var_java(self, qualified_ref_project: Path):
        """LOAD_VAR 'java' should not appear; LoadVar('Math') should."""
        linked = compile_directory(qualified_ref_project, Language.JAVA)

        load_vars = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR]
        names = [i.name.value for i in load_vars]

        assert "Math" in names, f"Expected LoadVar('Math'), got: {names}"
        assert "java" not in names, f"Cascading LoadVar('java') should be gone: {names}"

    def test_no_cascading_load_field_lang(self, qualified_ref_project: Path):
        """LOAD_FIELD 'lang' should not appear in the user module IR."""
        linked = compile_directory(qualified_ref_project, Language.JAVA)

        # Only check fields in user code instructions (after stubs)
        load_fields = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_FIELD]
        field_names = [i.field_name.value for i in load_fields]

        assert "lang" not in field_names, (
            f"Cascading LoadField('lang') should be gone: {field_names}"
        )

    def test_qualified_math_sqrt_executes_concrete(self, qualified_ref_project: Path):
        """java.lang.Math.sqrt(16.0) should produce 4.0 via stub execution."""
        linked = compile_directory(qualified_ref_project, Language.JAVA)

        vm = run_linked(linked, entry_point=EntryPoint.by_name("run"), max_steps=500)
        frame = vm.call_stack[0]

        from interpreter.var_name import VarName
        from interpreter.types.typed_value import TypedValue

        val = frame.local_vars.get(VarName("val"))
        if isinstance(val, TypedValue):
            val = val.value
        assert val == 4.0, f"Expected 4.0 from Math.sqrt(16), got: {val}"

    @pytest.fixture
    def cross_module_qualified_project(self, tmp_path: Path) -> Path:
        """Project where one module references another via qualified name."""
        helper_src = """\
package com.lib;

public class Helper {
    public static int doubleIt(int n) {
        return n * 2;
    }
}
"""
        main_src = """\
package com.app;

public class Main {
    public static void run() {
        int result = com.lib.Helper.doubleIt(21);
    }
}
"""
        lib_dir = tmp_path / "src" / "main" / "java" / "com" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "Helper.java").write_text(helper_src)

        app_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
        app_dir.mkdir(parents=True)
        (app_dir / "Main.java").write_text(main_src)
        return tmp_path

    def test_cross_module_qualified_resolves(self, cross_module_qualified_project: Path):
        """com.lib.Helper.doubleIt(21) should resolve Helper via namespace tree."""
        linked = compile_directory(cross_module_qualified_project, Language.JAVA)

        load_vars = [i for i in linked.merged_ir if i.opcode == Opcode.LOAD_VAR]
        names = [i.name.value for i in load_vars]

        assert "Helper" in names
        assert "com" not in names

    def test_cross_module_qualified_executes(self, cross_module_qualified_project: Path):
        """com.lib.Helper.doubleIt(21) → 42."""
        linked = compile_directory(cross_module_qualified_project, Language.JAVA)
        vm = run_linked(linked, entry_point=EntryPoint.by_name("run"), max_steps=500)
        frame = vm.call_stack[0]

        from interpreter.var_name import VarName
        from interpreter.types.typed_value import TypedValue

        result = frame.local_vars.get(VarName("result"))
        if isinstance(result, TypedValue):
            result = result.value
        assert result == 42, f"Expected 42, got: {result}"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/integration/project/test_java_namespace_resolution.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite for regression check**

Run: `poetry run python -m pytest --timeout=120 -x -q`
Expected: All ~13,267 tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/project/test_java_namespace_resolution.py
git commit -m "test: add end-to-end integration tests for Java namespace resolution"
```

---

### Task 11: Format and final validation

- [ ] **Step 1: Run formatter**

```bash
poetry run python -m black .
```

- [ ] **Step 2: Run full test suite**

```bash
poetry run python -m pytest --timeout=120 -x -q
```

Expected: All tests pass.

- [ ] **Step 3: Final commit if formatting changed anything**

```bash
git add -u
git commit -m "style: format namespace resolution code"
```
