# Namespace Resolution + Runtime Library — Design

**Date:** 2026-04-05
**Status:** Draft
**Issue:** red-dragon-06p8
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
┌─────────────────────────────────────────────────┐
│ Layer 3: Runtime Library                        │
│ Concrete implementations of stdlib methods      │
│ (existing experiment: experiments/java-stdlib/)  │
│ Arrays.fill, Math.max, ArrayList.add, ...       │
├─────────────────────────────────────────────────┤
│ Layer 2: Stub Types                             │
│ Class declarations with method signatures       │
│ Methods without implementations → symbolic      │
│ Built from imports + AST usage scanning          │
├─────────────────────────────────────────────────┤
│ Layer 1: Namespace Tree                         │
│ Package → Type mapping built from imports        │
│ Frontend resolves field_access chains through it │
│ No new opcodes — emits qualified VarName         │
└─────────────────────────────────────────────────┘
```

---

## Layer 1: Namespace Tree

### Purpose

A compile-time data structure that maps dotted package paths to types.
The frontend consults it when lowering `field_access` chains to decide
where the namespace ends and member access begins (the "join point").

### Data Structures

```python
@dataclass
class NamespaceNode:
    """A node in the package/namespace hierarchy."""
    children: dict[str, NamespaceNode]     # sub-namespaces
    types: dict[str, QualifiedType]        # types registered at this level

@dataclass
class QualifiedType:
    """A type reachable through namespace resolution."""
    qualified_name: str                    # "java.util.Arrays"
    class_ref: ClassRef                    # ClassRef for VM dispatch
    module: ModuleUnit | None              # linked stub if available (Layer 2/3)
```

### Population Sources (in priority order)

1. **Import declarations** — `import java.util.Arrays` registers
   `java → util → Arrays(type)`. Wildcard `import java.util.*` registers
   `java → util` as a namespace; any undeclared identifier used under it
   is assumed to be a type at that level.

2. **Project classes** — auto-populated from `compile_directory()`. The
   registry already knows `com.test.BatchDriverTest` exists, so it gets
   registered as `com → test → BatchDriverTest(type)`.

3. **Runtime library registry** — types from Layer 3 stubs are registered
   in the tree. `STDLIB_REGISTRY["java.util.ArrayList"]` → type node at
   `java → util → ArrayList`.

### Resolution Algorithm (mirrors JLS §6.5)

```
Given field_access chain: a.b.c.d(...)

1. Is "a" a declared local/parameter/field in current scope?
   → YES: treat entire chain as normal field access (existing behavior)
   → NO:  enter namespace resolution (step 2)

2. Walk namespace tree from root:
   a → found as namespace node? continue
   a.b → found as namespace node? continue
   a.b.c → found as TYPE node? → JOIN POINT

3. Resolved type → ClassRef("a.b.c")
   Register ClassRef in symbol table so LOAD_VAR finds it
   Remaining ".d(...)" → CALL_METHOD on ClassRef (existing static dispatch)

4. If chain doesn't match tree at all:
   Register ClassRef for the full chain as fallback
   (single symbolic from unresolved method, not cascading from chain)
```

### Integration with Existing VM Dispatch

The VM already has full support for static dispatch via `ClassRef`:

- `_handle_load_var` (variables.py:86) — stores `ClassRef` in register
  for known class names
- `_handle_call_method` (calls.py:468) — when object is `ClassRef`,
  dispatches via `registry.class_methods[class_name]`
- `_handle_load_field` (memory.py:413) — when object is `ClassRef`,
  resolves static fields via symbol table constants

**No new VM dispatch is needed.** The namespace tree just populates the
class registry and symbol table with external types. After that,
`java.util.Arrays.fill(arr, val)` follows the exact same code path as
`Math.square(5)` — which already works.

### Where It Lives

- `interpreter/namespace.py` — `NamespaceNode`, `NamespaceTree` (build + resolve)
- Built once per `compile_directory()` / `run_project()` call
- Registers resolved types as `ClassRef` entries in the registry/symbol table
- Passed into the Java frontend lowering context

---

## Layer 2: Stub Types

### Purpose

For types discovered via imports that don't have runtime library
implementations (Layer 3), generate minimal class declarations so the
VM can resolve calls instead of producing cascading symbolics.

### Stub Generation

After building the namespace tree, scan the AST for usages of each
registered type:

```
import java.sql.Types;
...
java.sql.Types.VARCHAR     → type "java.sql.Types" has field "VARCHAR"
java.sql.Types.BINARY      → type "java.sql.Types" has field "BINARY"
```

Generate a `ModuleUnit` with:
- Field declarations for accessed static fields (value = symbolic)
- Method stubs for called methods (body returns symbolic)
- Register in the namespace tree's `QualifiedType.module`

### Key Property

Stub types are **usage-driven** — only methods/fields actually used in
the source code get stubs. No need for exhaustive JDK coverage.

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
during construction. When the frontend resolves `java.util.ArrayList`,
the tree returns a `QualifiedType` whose `module` points to the
ArrayList stub — calls route to real implementations.

---

## Frontend Integration

### Changes to Java Frontend

The Java expression lowerer for `field_access` needs a new path:

```python
def lower_field_access(ctx, node):
    # Collect the full chain of identifiers
    chain = _collect_field_access_chain(node)
    root = chain[0]
    
    # Step 1: is root a declared variable?
    if ctx.is_declared(root):
        return _lower_as_normal_field_access(ctx, node)  # existing behavior
    
    # Step 2: resolve through namespace tree
    qualified_type, remaining = ctx.namespace_tree.resolve(chain)
    
    if qualified_type is not None:
        # Emit LOAD_VAR for the class name — the symbol table holds a ClassRef
        # for this name (registered when the namespace tree was built).
        # This follows the same path as project-internal static dispatch:
        #   LOAD_VAR "Arrays" → ClassRef → CALL_METHOD "fill"
        type_reg = ctx.emit_load_var(VarName(qualified_type.qualified_name))
        # Lower remaining segments as normal CALL_METHOD / LOAD_FIELD on ClassRef
        return _lower_remaining_chain(ctx, type_reg, remaining)
    
    # Step 3: fallback — register a ClassRef for the full chain
    full_name = ".".join(chain)
    ctx.ensure_class_registered(full_name)  # creates ClassRef + stub in registry
    return ctx.emit_load_var(VarName(full_name))
```

The key insight: `LOAD_VAR` already resolves to `ClassRef` for known class
names (variables.py:86). By registering external types in the class registry
during namespace tree construction, the existing dispatch path handles
everything — no new opcodes or VM logic needed.

### Scope Awareness

"Is root a declared variable?" requires knowing what's in scope. The
frontend already tracks declarations within the current function body.
Parameters and fields are also tracked. This check uses existing
infrastructure.

### Cross-Language Applicability

The namespace tree and resolution algorithm are language-agnostic. Other
frontends can use the same mechanism:

- **C#**: `System.IO.File.ReadAllText(...)` → `System → IO → File(type)`
- **Python**: `os.path.join(...)` → `os → path(module)` → `.join`
- **Go**: Package-qualified calls already work differently

Each frontend decides when to enter namespace resolution (undeclared root
check), but the tree structure and resolution algorithm are shared.

---

## Implementation Plan

### Phase 1: Namespace Tree + Resolution (eliminates cascading symbolics)

1. Implement `NamespaceNode` / `NamespaceTree` in `interpreter/namespace.py`
2. Build tree from import declarations in Java frontend
3. Add `resolve()` method implementing the JLS §6.5 algorithm
4. Register resolved types as `ClassRef` entries in the class registry
5. Modify `lower_field_access` to consult the tree
6. Test: `java.util.Arrays.fill(arr, val)` resolves via ClassRef static
   dispatch path (same as `Math.square(5)`), not LOAD_VAR chain

### Phase 2: Stub Types (proper call resolution)

1. AST usage scanner — discover methods/fields accessed per type
2. Stub `ModuleUnit` generator — creates class with method entries in
   `registry.class_methods` so `_handle_call_method` dispatches them
3. Stub method bodies return symbolic (external/unimplemented)
4. Register stubs in namespace tree and class registry
5. Test: `java.util.Arrays.fill(arr, val)` dispatches through ClassRef →
   registry.class_methods → stub body → symbolic return (single symbolic)

### Phase 3: Runtime Library Integration (concrete execution)

1. Wire existing `experiments/java-stdlib/` stubs into namespace tree
2. Replace stub method bodies with concrete implementations
3. Runtime library methods registered in `registry.class_methods` like
   any other class method — no special dispatch path
4. Test: `Arrays.fill(arr, 0)` → array contains zeros, not symbolics

### Phase 4: Cross-Language (optional)

1. Extract namespace tree building into shared infrastructure
2. C# frontend integration (`System.IO`, `System.Collections`, etc.)
3. Python module resolution

---

## Key Design Property

**No new VM dispatch mechanism.** The entire feature reuses the existing
`ClassRef` → `registry.class_methods` → static dispatch path that already
works for project-internal classes. The namespace tree is purely a
compile-time structure that populates the class registry with external
types. At runtime, `java.util.Arrays.fill(arr, val)` is indistinguishable
from a call to a project-defined static method.

---

## Success Criteria

1. **Phase 1**: `LOAD_VAR "java"` no longer appears in IR for resolved
   types. Field access chains on namespace roots produce `ClassRef`
   via qualified `LOAD_VAR`, not cascading symbolics.
2. **Phase 2**: Static method calls on imported types dispatch through
   `ClassRef` → `registry.class_methods` (verified by concrete
   return from stub body, not symbolic chain).
3. **Phase 3**: `java.util.Arrays.fill(arr, 0)` produces a concrete
   array with zeros through VM execution of runtime library IR.
