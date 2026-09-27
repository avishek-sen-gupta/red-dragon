## Programming Patterns

### Code style

- Functional style. Avoid `for` loops with mutations — use comprehensions, `map`, `filter`, `reduce`, streams. **STOP USING FOR LOOPS WITH MUTATIONS IN THEM. JUST STOP.**
- Prefer early return. Use `if` for exceptional cases, not the happy path.
- Small, composable functions. No massive functions.
- Fully qualified imports. No relative imports.
- One class per file (dataclass, record or otherwise).
- Log, never `print`. Log copiously through long-running tasks and loops.
- Constants instead of magic strings and numbers. Wrap globals in classes or modules.
- Enums for fixed value sets, not raw strings.

### Types and values

- Immutable by default. Objects are constructed complete, with all dependencies injected at construction, and never mutated after.
- No defensive programming. No null checks, no generic exception handling. If unsure, pause and ask.
- No null as a default parameter — use empty collections.
- No null returns from non-null return types. Use the null object pattern.
- Domain-appropriate wrapping types for data crossing function boundaries. Wrap and unwrap at boundary layers only.
- Read-only collection types for parameters the function does not mutate.
- Resolve enums into executable objects early in the call chain, then inject those objects as dependencies.

### Architecture

- Ports-and-adapters. Functional core, imperative shell.
- Mutable state lives only in the imperative shell (file writes, subprocess spawning, databases, network and LLM calls). The functional core takes and returns immutable values.
- **The shell is named, not assumed.** A class claiming to be shell needs an argument for why threading its state through as parameters would move the mutation without removing it.
- Inject external systems (databases, OS, file I/O, clocks, GUIDs, subprocess spawning) rather than importing the concrete modules.
- No static methods, and no static utility classes — encapsulate behaviour in objects.
