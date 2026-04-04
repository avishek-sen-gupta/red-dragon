# Namespace Resolution + Runtime Library — Design

**Date:** 2026-04-05
**Status:** Draft
**Issue:** red-dragon-06p8
**Related:** red-dragon-y42x (TypeExpr/ClassRef unification)
**Builds on:** `2026-03-31-java-stdlib-stubs-experiment-design.md` (Layer 3)

---

## Problem

Fully-qualified Java references like `java.util.Arrays.fill(arr, val)` are
lowered as a `LOAD_VAR "java"` → `LOAD_FIELD "util"` → `LOAD_FIELD "Arrays"`
→ `CALL_METHOD "fill"` chain. Since `java` isn't a declared variable, each
step produces a cascading `SymbolicValue`. In BatchDriverTest this creates
67 avoidable symbolics from 19 IR instructions.

Even with the existing stdlib stubs experiment (which provides concrete
implementations), there's no mechanism to **route** qualified names to
those stubs. The stubs exist but the frontend doesn't know how to find them.

---

## Architecture: Three Layers

```
┌────────────────────────────────────���────────────┐
│ Layer 3: Runtime Library                        │
│ Concrete implementations of stdlib methods      │
│ Hand-written, static, checked-in ModuleUnits    │
│ (existing: experiments/java_stdlib/)             │
│ Arrays.fill, Math.max, ArrayList.add, ...       │
├─────────────────────────────────────────────────┤
│ Layer 2: Stub Types                             │
│ Hand-written class shells with method stubs     │
│ Methods without implementations → symbolic      ���
│ Static files, same ModuleUnit shape as Layer 3  │
├─────────────────────────────────────────────────┤
│ Layer 1: Namespace Tree                         │
│ Package → Type mapping                          │
│ Frontend consults during lowering               │
│ Populated from stub registry + project classes  │
│ Attached to VMState for future runtime use      │
└─────────────────────────────────────────────────┘
```

**Key change from earlier draft:** Stubs (Layer 2 and 3) are **static,
hand-written, checked-in files** — not auto-generated at compile time.
The coding agent writes them, they live in the repo, and new types are
added by writing new stub files. No runtime code generation.

---

## Layer 1: Namespace Tree

### Lifecycle

The namespace tree has a four-phase lifecycle:

1. **Pre-scan** — `compile_directory()` runs a fast tree-sitter pre-scan
   of all source files to discover `(package, class_names)` per file.
   No expression lowering — just top-level `package_declaration`,
   `class_declaration`, `interface_declaration`, `enum_declaration` nodes.

2. **Build tree** — populated from two sources:
   - **Stub registry** (static, always known) — types with hand-written
     ModuleUnits get `short_name` + real `ClassRef` from the stub.
   - **Project classes** (from pre-scan) — types get `short_name` only;
     `ClassRef` starts as `NO_CLASS_REF` (filled in phase 4).

3. **Frontend lowering** — tree is passed into `TreeSitterEmitContext`.
   The frontend reads `short_name` to emit `LoadVar(short_name)` when
   resolving qualified field_access chains. The `ClassRef` field is
   **not used** during lowering.

4. **Post-compile patch + VMState** — after all files are compiled,
   walk each ModuleUnit's `class_symbol_table` to fill in real ClassRefs
   for project classes. Attach tree to VMState for future runtime use.

```python
# Phase 1: Pre-scan
scan_results = {path: java_pre_scan(path) for path in source_files}

# Phase 2: Build tree
tree = build_java_namespace_tree(scan_results, STDLIB_REGISTRY)

# Phase 3: Frontend lowering (uses tree.short_name only)
ctx = TreeSitterEmitContext(..., namespace_resolver=JavaNamespaceResolver(tree))

# Phase 4: Patch ClassRefs + attach to VMState
patch_tree_class_refs(tree, compiled_modules)
vm = VMState(..., namespace_tree=tree)
```

### Data Structures

```python
@dataclass
class NamespaceNode:
    """A node in the package/namespace hierarchy."""
    children: dict[str, NamespaceNode]     # sub-namespaces
    types: dict[str, NamespaceType]        # types registered at this level

@dataclass
class NamespaceType:
    """A type reachable through namespace resolution."""
    short_name: str                        # "Arrays" — used by frontend for LoadVar
    class_ref: ClassRef = NO_CLASS_REF     # sentinel initially; patched post-compile
    module: ModuleUnit | None = None       # stub ModuleUnit, if one exists


class NamespaceTree:
    """Base namespace tree with default resolution algorithm.
    
    The resolution algorithm is shared across languages. Language-specific
    behavior comes from the seed (what's in the tree), not the walk
    (how we traverse it). Override resolve() only if a language needs
    fundamentally different resolution semantics (e.g. C++ partial
    namespace paths).
    """
    
    root: NamespaceNode
    
    def resolve(self, chain: list[str]) -> tuple[NamespaceType | None, list[str], str]:
        """Walk the tree to find the type join point.
        
        Returns:
            (resolved_type, remaining_chain, qualified_name)
            or (None, original_chain, "") if no match.
        """
        node = self.root
        for i, segment in enumerate(chain):
            if segment in node.types:
                qualified = ".".join(chain[:i + 1])
                return node.types[segment], chain[i + 1:], qualified
            if segment in node.children:
                node = node.children[segment]
                continue
            break
        return None, chain, ""
    
    def register_type(self, dotted_path: str, ns_type: NamespaceType) -> None:
        """Register a type at the given dotted path, creating namespace
        nodes as needed. E.g. register_type("java.util.Arrays", ...) creates
        java → util namespace nodes and registers Arrays as a type."""
        ...
```

### Pre-Scan

The pre-scan is a fast, Java-frontend-specific pass that extracts
declarations without lowering:

```python
@dataclass
class JavaPreScanResult:
    package: str | None             # "com.test" or None
    class_names: list[str]          # ["Helper", "Main"]
    imports: list[ImportRef]        # existing ImportRef type
```

One per file. The tree builder computes qualified names:
`package + "." + class_name` → `"com.test.Helper"`.

The pre-scan walks top-level tree-sitter nodes only:
`package_declaration`, `class_declaration`, `interface_declaration`,
`enum_declaration`. No expression lowering, no control flow — just
name extraction.

### Tree Population

The tree is populated from two sources (in priority order):

1. **Stub registry** — iterate `STDLIB_REGISTRY` (e.g.
   `{"java.lang.Math": MATH_MODULE, ...}`). Each entry gets a
   `NamespaceType` with `short_name` from the last segment,
   `class_ref` from the stub's exports, and `module` pointing to the
   stub ModuleUnit. These have real ClassRefs from the start.

2. **Project classes** — from pre-scan results. Each
   `(package, class_name)` pair registers a `NamespaceType` with
   `short_name=class_name`, `class_ref=NO_CLASS_REF`, `module=None`.
   Project classes override stubs at the same path (local wins).

**Imports are NOT registered in the tree.** They are not a population
source. The tree is populated purely from what we have implementations
for (stubs) and what the project defines (classes). If
`import java.sql.Types` appears but there's no stub for `java.sql.Types`,
the tree has no entry and the resolver falls through to existing
behaviour (cascading symbolics). Stubs are opt-in.

### Resolution Algorithm (mirrors JLS §6.5)

```
Given field_access chain: a.b.c.d(...)

1. Is "a" a declared local/parameter in current method?
   → YES: treat entire chain as normal field access (existing behavior)
   → NO:  enter namespace resolution (step 2)

2. Walk namespace tree from root:
   a → found as namespace node? continue
   a.b → found as namespace node? continue
   a.b.c → found as TYPE node? → JOIN POINT

3. Emit LoadVar(short_name) for the resolved type
   Remaining chain → sequential LoadField instructions

4. If chain doesn't match tree at all:
   Fall through to existing recursive lower_field_access (cascading symbolics)
```

### Scope Awareness

"Is root a declared variable?" checks `ctx._method_declared_names`,
which tracks **locals and parameters** within the current method body.
This check uses existing infrastructure (context.py:209 populates the
set on every `DeclVar` emission, context.py:481 resets at function
boundaries).

**Deliberate leniency vs. javac:** We do **not** check class fields.
In real Java, a field shadows a package name:

```java
class Foo {
    Object java;          // field named "java"
    void bar() {
        java.util.Arrays.fill(arr, 42);  // javac error: "cannot find
                                          // symbol: variable util
                                          // location: variable java
                                          // of type Object"
    }
}
```

`javac` rejects this code — the field `java` shadows the package.
Since RedDragon analyses code that has already compiled, this collision
cannot occur in practice. We accept the leniency: if a field shadows
a package root, our resolver would attempt namespace resolution, fail
to find the type, and fall through to symbolic — a graceful degradation,
not a crash.

### Symbol Table vs Namespace Tree: Separation of Concerns

The symbol table and namespace tree are **independent resolution paths**:

- **Symbol table** — unqualified names only (`"Arrays"`, `"Math"`).
  Project classes always win. Imports register only if no project class
  with that name exists (matching Java's shadowing semantics).
- **Namespace tree** — qualified paths only (`java.util.Arrays`).
  Returns `short_name` for `LoadVar`, does not go through symbol table.

```
Unqualified:  Arrays.fill(...)              → LOAD_VAR "Arrays" → symbol table → ClassRef
Qualified:    java.util.Arrays.fill(...)    → namespace tree → LoadVar("Arrays") → ClassRef
```

Both paths converge: `LoadVar` resolves to a ClassRef (from the stub's
`DeclVar` or the project's `lower_class_def`), then `CALL_METHOD`
dispatches statically via `registry.class_methods`. This already works
(calls.py:450).

### Disambiguation

If a project defines `class Arrays` and code also `import java.util.Arrays`:
- Unqualified `Arrays` → symbol table → project's ClassRef (local wins)
- `java.util.Arrays` → namespace tree → stdlib ClassRef (qualified path)
- This matches Java's actual shadowing semantics (JLS §6.3.1)

### Override Point

The base `NamespaceTree.resolve()` handles the common case: walk from root,
find join point at type node. Languages needing different resolution can
subclass:

```python
class CppNamespaceTree(NamespaceTree):
    """C++ allows partial namespace resolution via 'using namespace'."""
    
    def resolve(self, chain: list[str]) -> ...:
        # Try from each imported namespace, not just root
        for ns in self.using_namespaces:
            result = self._resolve_from(ns, chain)
            if result[0] is not None:
                return result
        return super().resolve(chain)
```

For now, only the base `NamespaceTree` is implemented. The override
mechanism exists for future use.

### Java-Specific: No Partial Namespace Resolution Needed

Java wildcard imports (`import java.util.*`) import types, not packages.
`import java.*` does NOT make `util` available as a name. So resolution
always starts from the root of the tree — there are no partial namespace
paths in valid Java.

### Integration with Existing VM Dispatch

The VM already has full support for static dispatch via `ClassRef`:

- `_handle_const` (variables.py:42) — when CONST operand is a class label
  string, looks up `class_symbol_table` and stores ClassRef in register
- `_handle_call_method` (calls.py:450) — when object is `ClassRef`,
  dispatches via `registry.lookup_methods(class_name, method_name)`
- `_handle_load_field` (memory.py:413) — when object is `ClassRef`,
  resolves static fields via `symbol_table.classes[class_name].constants`;
  if no ClassInfo exists (external type without stub), falls through
  gracefully to symbolic via `fresh_symbolic(hint="ClassName.field")`

**No new VM dispatch is needed.** The namespace tree routes qualified
names to `LoadVar(short_name)` during lowering. At runtime, `LoadVar`
resolves to a ClassRef (placed by the stub's `DeclVar`). From there,
the existing ClassRef → static dispatch path handles everything.

---

## Layer 2: Stub Types

### Purpose

For external types that need resolution but don't require concrete
implementations, provide **hand-written static stub ModuleUnits** —
empty class shells with optional method stubs.

### Stub Shape

Stubs follow the same pattern as the existing `experiments/java_stdlib/`
stubs. A minimal stub for a type with no methods:

```python
# 6 instructions — empty class shell
_CLS = "class_Arrays_0"
_END_CLS = "end_class_Arrays_1"

ARRAYS_IR = (
    Label_(label=CodeLabel("entry_Arrays")),
    Branch(label=CodeLabel(_END_CLS)),
    Label_(label=CodeLabel(_CLS)),
    Label_(label=CodeLabel(_END_CLS)),
    Const(result_reg=Register("%0"), value=_CLS),
    DeclVar(name=VarName("Arrays"), value_reg=Register("%0")),
)

ARRAYS_MODULE = ModuleUnit(
    path=Path("java/util/Arrays.java"),
    language=Language.JAVA,
    ir=ARRAYS_IR,
    exports=ExportTable(
        functions={},
        classes={ClassName("Arrays"): CodeLabel(_CLS)},
    ),
    imports=(),
)
```

Stubs with method bodies add the standard BRANCH-over function blocks
(see `experiments/java_stdlib/stubs/java_lang_math.py` for the pattern).
Method stubs that return symbolic use `Symbolic(hint="...")` + `Return_`.

### Key Properties

- **Static, hand-written, checked-in.** No auto-generation at compile time.
- **Opt-in.** If no stub exists for an imported type, the resolver falls
  through to existing behaviour (cascading symbolics).
- **Same shape as Layer 3.** The only difference is method body content —
  stubs return symbolic, runtime library returns concrete values. Upgrading
  a stub to a runtime implementation is just filling in method bodies.

---

## Layer 3: Runtime Library

### Purpose

Concrete implementations of frequently-used stdlib methods. These are
hand-written `ModuleUnit`s with real IR that the VM executes to produce
concrete values.

### Already Designed

See `2026-03-31-java-stdlib-stubs-experiment-design.md` for:
- Stub shape (ModuleUnit with IR + ExportTable)
- Object representation (heap conventions for ArrayList, HashMap, etc.)
- Registry structure (STDLIB_REGISTRY dict)
- Testing approach (compile Java → link with stubs → VM execute → assert concrete)

### Integration Point

Runtime library `ModuleUnit`s are registered in the namespace tree
during construction via the stub registry. When the frontend resolves
`java.util.ArrayList`, the tree returns a `NamespaceType` whose `module`
points to the ArrayList stub — linking includes it, and calls route to
real implementations at runtime.

---

## Frontend Integration

### Changes to Java Frontend

The Java expression lowerer for `field_access` gains a namespace
resolution pre-check:

```python
def lower_field_access(ctx, node):
    # Try namespace resolution (injectable, no-op for some languages)
    result = ctx.namespace_resolver.try_resolve_field_access(ctx, node)
    if result is not NO_RESOLUTION:
        return result
    
    # Existing behavior: recursive lowering
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)
    reg = ctx.fresh_reg()
    ctx.emit_inst(LoadField(result_reg=reg, obj_reg=obj_reg, field_name=FieldName(field_name)), node=node)
    return reg
```

### Namespace Resolver (Injectable Strategy)

```python
class NamespaceResolver:
    """Base: no-op resolver for languages without namespace resolution."""
    
    def try_resolve_field_access(self, ctx, node) -> Register | NoResolution:
        return NO_RESOLUTION


class JavaNamespaceResolver(NamespaceResolver):
    """Java-specific: resolves field_access chains through namespace tree."""
    
    def __init__(self, tree: NamespaceTree):
        self.tree = tree
    
    def try_resolve_field_access(self, ctx, node) -> Register | NoResolution:
        chain = _collect_field_access_chain(ctx, node)
        if chain is NO_CHAIN:
            return NO_RESOLUTION
        
        root = chain[0]
        if root in ctx._method_declared_names:
            return NO_RESOLUTION  # declared variable, not a namespace
        
        ns_type, remaining, qualified_name = self.tree.resolve(chain)
        if ns_type is None:
            return NO_RESOLUTION  # no match — fall through to existing behaviour
        
        # Emit LoadVar for the resolved type's short name
        type_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadVar(result_reg=type_reg, name=VarName(ns_type.short_name)),
            node=node,
        )
        return _lower_remaining_chain(ctx, type_reg, remaining, node)
```

### Chain Collection

```python
def _collect_field_access_chain(ctx, node) -> list[str] | _NoChain:
    """Walk nested field_access to collect ["java", "util", "Arrays"].
    Returns NO_CHAIN if root isn't a plain identifier."""
    segments = []
    while node.type == "field_access":
        field = node.child_by_field_name("field")
        segments.append(ctx.node_text(field))
        node = node.child_by_field_name(ctx.constants.attr_object_field)
    if node.type == "identifier":
        segments.append(ctx.node_text(node))
        segments.reverse()
        return segments
    return NO_CHAIN
```

### Remaining Chain Lowering

After resolving the type, any remaining segments are emitted as
sequential `LoadField` instructions:

```python
def _lower_remaining_chain(ctx, base_reg, remaining, node):
    """Emit LoadField for each segment after the type join point."""
    reg = base_reg
    for segment in remaining:
        next_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(result_reg=next_reg, obj_reg=reg, field_name=FieldName(segment)),
            node=node,
        )
        reg = next_reg
    return reg
```

### Sentinel Objects

Following existing null object patterns in the codebase:

```python
NO_RESOLUTION = _NoResolution()     # sentinel: resolver didn't handle this
NO_CHAIN = _NoChain()               # sentinel: node isn't a pure identifier chain
```

### Wiring

```python
# Java: resolver with namespace tree
ctx = TreeSitterEmitContext(..., namespace_resolver=JavaNamespaceResolver(tree))

# Go, Lua, etc.: no-op resolver (default)
ctx = TreeSitterEmitContext(..., namespace_resolver=NamespaceResolver())
```

### How It Works End-to-End

**`java.util.Arrays.fill(arr, val)` — method call on external type:**

Tree-sitter AST:
```
method_invocation
  object: field_access          ← "java.util.Arrays"
  name: identifier              ← "fill"
  arguments: argument_list      ← (arr, val)
```

1. `lower_method_invocation` calls `ctx.lower_expr(object)` →
   dispatches to `lower_field_access`
2. `lower_field_access` → namespace resolver intercepts
3. `_collect_field_access_chain` → `["java", "util", "Arrays"]`
4. `"java"` not in `_method_declared_names` → enter resolution
5. Tree resolves: `java → util → Arrays(type)` → `short_name="Arrays"`
6. Emit `LoadVar("Arrays")` → register holds ClassRef
   (stub's `DeclVar("Arrays", ...)` ran first via linker topo order)
7. No remaining chain → return register
8. Back in `lower_method_invocation`: `CALL_METHOD %reg fill (arr, val)`
9. At runtime: `_handle_call_method` sees ClassRef, dispatches via
   `registry.lookup_methods(ClassName("Arrays"), FuncName("fill"))`

**`java.sql.Types.VARCHAR` — static field on type without remaining chain:**

1. Chain: `["java", "sql", "Types", "VARCHAR"]`
2. Tree resolves: `java → sql → Types(type)`, remaining: `["VARCHAR"]`
3. Emit `LoadVar("Types")` → ClassRef register
4. `_lower_remaining_chain` emits `LoadField("VARCHAR")` on ClassRef
5. At runtime: `_handle_load_field` on ClassRef → falls through to
   symbolic `fresh_symbolic(hint="Types.VARCHAR")` (no ClassInfo exists)

### Scope: `compile_directory()` Only

Namespace resolution requires the linker to merge stub ModuleUnits
with project code. This only works in `compile_directory()` mode
(multi-file with linker). **Single-file mode does not perform namespace
resolution** — existing behaviour (cascading symbolics) is preserved.

---

## Compilation Flow (`compile_directory()`)

### Revised Flow

```
1. Scan source files (by extension)
         ↓
2. Pre-scan all files (Java-specific)
   Extract (package, class_names, imports) per file
   Fast tree-sitter walk — no expression lowering
         ↓
3. Build namespace tree
   Source 1: Stub registry (short_name + ClassRef + ModuleUnit)
   Source 2: Project classes (short_name only, ClassRef = NO_CLASS_REF)
         ↓
4. Compile each file → ModuleUnit
   Frontend has tree in context via JavaNamespaceResolver
   Uses short_name to emit LoadVar for qualified references
         ↓
5. Patch tree: fill in ClassRefs for project classes
   Walk each ModuleUnit's class_symbol_table
         ↓
6. Link: project modules + ALL stub modules (unconditional)
   Stubs run first in topo order (no deps)
   Their DeclVar makes type names available as variables
         ↓
7. Execute linked program
   VMState holds tree reference for future runtime use
```

### Linking Strategy

All stub ModuleUnits from the registry are linked **unconditionally**
— no filtering by imports. The stub registry is small (hand-written),
so the overhead of unused stubs is negligible. Their top-level code
(class declaration + `DeclVar`) runs first in topo order, making type
names available as variables for user code.

---

## Cross-Language Applicability

The namespace tree and resolution algorithm are language-agnostic. Other
frontends can use the same mechanism:

- **C#**: `System.IO.File.ReadAllText(...)` → `System → IO → File(type)`
- **Python**: `os.path.join(...)` → `os → path(module)` → `.join`
- **Go**: Package-qualified calls already work differently
- **C++**: Would need `CppNamespaceTree` override for partial resolution

Each language provides its own pre-scan function and seed. The tree
structure and base resolution algorithm are shared.

---

## Implementation Plan

### Phase 1: Namespace Tree + Resolution (eliminates cascading symbolics)

1. Implement `NamespaceNode` / `NamespaceType` / `NamespaceTree` in
   `interpreter/namespace.py`
2. Implement `JavaPreScanResult` and `java_pre_scan()` — fast
   tree-sitter extraction of package + class names + imports
3. Implement `build_java_namespace_tree()` — populates tree from
   stub registry + pre-scanned project classes
4. Add `namespace_resolver` field to `TreeSitterEmitContext`
5. Implement `JavaNamespaceResolver` with `_collect_field_access_chain`,
   `_lower_remaining_chain`, and the `LoadVar(short_name)` emission
6. Modify `lower_field_access` to call resolver before existing logic
7. Update `compile_directory()`: pre-scan → build tree → compile with
   tree → patch ClassRefs → link with all stubs
8. Add `namespace_tree` field to `VMState` (attached at execution start)
9. Test: `java.util.Arrays.fill(arr, val)` produces `LoadVar("Arrays")`
   + `CALL_METHOD fill`, not `LOAD_VAR "java"` chain

### Phase 2: Expand Stub Coverage

1. Write empty-class-shell stubs for commonly-used JDK types
   (java.util.Arrays, java.sql.Types, etc.)
2. Add method stubs for frequently-called methods (return symbolic)
3. Test: each stubbed type resolves via namespace tree and produces
   single symbolic from method call (not cascading from chain)

### Phase 3: Runtime Library Integration (concrete execution)

1. Wire existing `experiments/java_stdlib/` stubs into the stub registry
2. Runtime library methods are already concrete implementations —
   they register in `registry.class_methods` like any other class
3. Test: `Arrays.fill(arr, 0)` → array contains zeros, not symbolics

### Phase 4: Cross-Language (optional)

1. Implement pre-scan + seed for C#, Python, etc.
2. If needed, subclass `NamespaceTree` for language-specific resolution
3. Python module resolution

---

## Key Design Properties

1. **Namespace tree has a clear lifecycle** — built from pre-scan +
   stub registry before compilation, used by frontend during lowering
   (via `short_name`), patched with ClassRefs post-compile, attached
   to VMState for runtime.

2. **Base resolution is shared, seed is per-language.** The tree walk
   algorithm is the same for all languages. What differs is the initial
   content (Java seeds `java.*`, C# seeds `System.*`, etc.).

3. **Override point for resolution.** Languages needing different walk
   semantics (e.g. C++ partial namespace paths) can subclass
   `NamespaceTree` and override `resolve()`.

4. **No new VM dispatch mechanism.** The entire feature reuses the
   existing `LoadVar` → ClassRef → `registry.class_methods` → static
   dispatch path. The namespace tree just teaches the frontend to emit
   `LoadVar(short_name)` instead of cascading `LOAD_FIELD` chains.

5. **Qualified name is derived from tree position**, not stored as a
   field. `resolve()` builds the dotted name during traversal.

6. **Stubs are static, hand-written, opt-in.** No auto-generation.
   Types without stubs fall through to existing cascading symbolic
   behaviour. Adding a type = writing a stub file + registering it.

7. **All stubs linked unconditionally.** No import filtering. The
   stub registry is small; unused stubs just declare variables nobody
   references.

8. **Frontend uses `short_name`, not ClassRef.** During lowering the
   tree provides the short type name for `LoadVar`. ClassRef is
   available in the tree for runtime use but is not needed at compile
   time. Project-class ClassRefs start as `NO_CLASS_REF` and are
   patched after compilation.

---

## Success Criteria

1. **Phase 1**: `LOAD_VAR "java"` no longer appears in IR for resolved
   types. Field access chains on namespace roots produce
   `LoadVar(short_name)`, not cascading `LOAD_FIELD` instructions.
2. **Phase 2**: Static method calls on stubbed types dispatch through
   ClassRef → `registry.class_methods` → stub body → symbolic return
   (single symbolic, not cascading chain).
3. **Phase 3**: `java.util.Arrays.fill(arr, 0)` produces a concrete
   array with zeros through VM execution of runtime library IR.
