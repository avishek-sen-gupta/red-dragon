## Design Principles

- **Use existing infrastructure before adding new abstractions.** Ask: "does the system already have something that solves this?" The answer is usually yes. Example: anonymous class alias resolution was solved by reading the variable store at `new_object` time — the variable store already was a pointer table. Zero new infrastructure.
- **Start from the simplest possible mechanism.** Begin with minimal intervention. Add complexity only when proven insufficient.
- **Prefer emitting equivalent IR over threading conventions through multiple layers.** If a feature can be expressed using existing opcodes and builtins, do that. Example: rest parameters (`...args`) → `slice(arguments, N)` in IR, reusing the existing `slice` builtin.
- **No speculative code without tests.** Every code path must have a test that exercises it.
- **Stay consistent with established patterns.** When the codebase has a way of doing something (e.g., `TypeExpr` ADT), use it.
- **Never mask bugs with workaround guards.** Don't add `is not None` checks to make tests pass. Fix the root cause.
- **Pass decisions through data, don't re-derive downstream.** If a decision was made upstream, attach it to the data (e.g., `is_ctor` flag on `StackFrame`). Don't re-detect via fragile lookups.
- **Do not encode information in string representations.** Use typed objects (`Pointer`, `FuncRef`, `ClassRef`, etc.). Never use string prefixes, patterns, or regex to deduce what a value represents — use `isinstance`.

## Programming Patterns

### Code style

- Functional programming style. Avoid `for` loops with mutations — use comprehensions, `map`, `filter`, `reduce`.
- Prefer early return. Use `if` for exceptional cases, not the happy path.
- Small, composable functions. No massive functions.
- Fully qualified imports. No relative imports.
- One class per file (dataclass or otherwise).
- Logging, not `print` statements.
- Constants instead of magic strings and numbers. Wrap globals in classes.
- Enums for fixed string sets, not raw strings.

### Types and values

- No defensive programming. No `None` checks, no generic exception handling. If unsure, pause and ask.
- No `None` as a default parameter. Use empty structures (`{}`, `[]`, `()`).
- No `None` returns from non-None return types. Use null object pattern.
- No mutation after construction. Inject all dependencies at construction time.
- Domain-appropriate wrapping types for data crossing function boundaries. Wrap/unwrap at boundary layers only.
- Resolve enums into executable objects early in the call chain, then inject as dependencies.

### Architecture

- Ports-and-adapters. Functional core, imperative shell.
- Dependency injection for external systems (Neo4j, OS, file I/O, clocks, GUIDs).
- No static methods.
