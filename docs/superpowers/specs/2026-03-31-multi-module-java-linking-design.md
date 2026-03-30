# Multi-Module Java Linking: Source Root Discovery and Wildcard Imports

**Date:** 2026-03-31
**Issue:** red-dragon-z5jr
**Status:** Design approved

## Problem

The `JavaImportResolver` searches 4 fixed roots under a single `project_root`. Multi-module Maven projects have multiple modules, each with its own `src/main/java/` tree. When a file imports a package from a sibling module (e.g., `import com.example.utils.*`), the resolver can't find it because it only searches under the entry file's project root.

Additionally, wildcard imports (`import com.example.utils.*`) have no resolution logic — the resolver tries to find a single file `com/example/utils.java` which doesn't exist. It's a directory containing many `.java` files.

The linker (`link_modules`) already handles label namespacing and register rebasing correctly. The bottleneck is entirely in the resolver.

## Design

### 1. Source Root Discovery

A `SourceRootDiscovery` ABC with one method:

```python
class SourceRootDiscovery(ABC):
    def discover(self, project_root: Path) -> list[Path]: ...
```

Two implementations:

- **`MavenSourceRootDiscovery`** — Scans `project_root` and sibling directories recursively for `src/main/java/` trees. Returns all found as source roots. Handles multi-module Maven projects where modules are siblings or children under a common parent.

- **`ExplicitSourceRootDiscovery`** — Takes a `list[Path]` at construction. Returns them directly. For non-standard layouts and testing.

Discovery runs once in `compile_project()`, not per-resolve call.

### 2. `JavaImportResolver` Multi-Root Support

The resolver receives discovered source roots at construction time:

```python
class JavaImportResolver(ImportResolver):
    def __init__(self, source_roots: list[Path] = ()):
        self._source_roots = list(source_roots)
```

The `resolve()` method searches `self._source_roots` first. If none were provided (empty list), falls back to the current 4-pattern search under `project_root` — preserving backwards compatibility for single-module projects.

### 3. `ImportResolver` ABC Return Type Change

Change the ABC from single to list return:

```python
class ImportResolver(ABC):
    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> list[ResolvedImport]: ...
```

All existing resolvers change their return from `ResolvedImport(...)` to `[ResolvedImport(...)]` — mechanical one-liner per resolver.

`compile_project()`'s BFS loop changes from:

```python
resolved = resolver.resolve(ref, project_root)
if resolved.resolved_path is not None:
    ...
```

to:

```python
for resolved in resolver.resolve(ref, project_root):
    if resolved.is_resolved():
        ...
```

### 4. `ResolvedImport` Null Object Pattern

Replace `resolved_path: Path | None` with a null object sentinel:

```python
NO_PATH = Path("")

@dataclass(frozen=True)
class ResolvedImport:
    ref: ImportRef
    resolved_path: Path = NO_PATH
    is_external: bool = False

    def is_resolved(self) -> bool:
        return self.resolved_path != NO_PATH and not self.is_external
```

Callers use `resolved.is_resolved()` instead of `resolved.resolved_path is not None`. The field is never `None`.

### 5. Wildcard Import Resolution

When `ref.names == ("*",)`, `JavaImportResolver` maps the module path to a directory and globs `*.java`:

1. `com.example.utils` → `com/example/utils/`
2. Search each source root for that directory
3. Glob `*.java` in the directory
4. Return one `ResolvedImport` per file found

For specific imports (e.g., `import com.models.Result`), return a single-element list as today.

### 6. `compile_project()` Wiring

When `language == Language.JAVA`:

1. Run `MavenSourceRootDiscovery().discover(project_root)` to find all source roots
2. Construct `JavaImportResolver(source_roots=discovered_roots)`
3. Pass it into the BFS import discovery loop

For all other languages, `get_resolver(language)` continues to work as today. `compile_project()` constructs the multi-root resolver directly when discovery finds multiple roots, bypassing `get_resolver()` for Java.

## Files Changed

- `interpreter/project/resolver.py` — `ImportResolver` ABC return type, `ResolvedImport` null object, `JavaImportResolver` multi-root + wildcard, `SourceRootDiscovery` ABC + implementations
- `interpreter/project/compiler.py` — `compile_project()` wiring for multi-root discovery
- All other resolver classes — mechanical return type change (`ResolvedImport(...)` → `[ResolvedImport(...)]`)

## Testing

### Unit tests

- `MavenSourceRootDiscovery` — discovers `src/main/java/` trees in sibling directories
- `ExplicitSourceRootDiscovery` — returns exactly what was passed in
- `JavaImportResolver` multi-root — resolves specific import across roots
- `JavaImportResolver` wildcard — `com.example.*` returns all `.java` files in directory
- `ResolvedImport.is_resolved()` — true for real path, false for `NO_PATH` and external
- Existing resolvers — still work with `list[ResolvedImport]` return type

### Integration test

A synthetic multi-module Java project in `tmp_path` with 4 modules, 9 files:

```
project/
  math-lib/src/main/java/com/math/
    Adder.java          — class Adder(int base) { int add(int x) }
    Multiplier.java     — class Multiplier(int factor) { int multiply(int x) }
  models/src/main/java/com/models/
    Result.java         — class Result(String label, int value) { getLabel(), getValue() }
    Pair.java           — class Pair(int first, int second) { getFirst(), getSecond() }
  utils/src/main/java/com/utils/
    Formatter.java      — class Formatter(String prefix) { String format(int val) }
  app/src/main/java/com/app/
    Calculator.java     — import com.math.*; import com.models.Result;
    Main.java           — import com.app.Calculator; import com.models.*;
```

Import patterns: wildcard cross-module (`com.math.*`), specific cross-module (`com.models.Result`), wildcard cross-module (`com.models.*`), specific same-module (`com.app.Calculator`).

Assertions after `compile_project()` → `run(entry_point="main")`:
- `c` is `Pointer` (Calculator constructed)
- `r` is `Pointer` (Result constructed via cross-module dispatch)
- `val == 43` (10 + 3 from Adder + 3 * 10 from Multiplier)
- `label == "result"` (concrete string from Result constructor)
