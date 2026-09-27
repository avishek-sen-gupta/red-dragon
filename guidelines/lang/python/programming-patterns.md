## Programming Patterns — Python

Bindings for `programming-patterns.md`.

- **Dataclasses must be `frozen=True`.** No exceptions.
- **Empty defaults are `{}`, `[]`, `()`** — never `None`.
- **`Sequence` and `Mapping` from `collections.abc`** for parameters the function does not mutate.
- **Logging via the `logging` module.** Never `print`.
