## Guardrails — Python

Bindings for `guardrails.md`. Nothing here restates a rule; each item names the
concrete Python thing the neutral rule refers to.

### Fully typed, no escape hatches

- **Pyright runs in strict mode and must pass with zero errors.**
- **`Any` is banned** — no `from typing import Any`, no `: Any`, no `dict[str, Any]`. Where a type is hard to express use a `Protocol`, a `TypeVar`, or a union; where it is genuinely unknown at a boundary, parse it into a Pydantic model there.
- **No `object`, and no JSON-blob aliases.** `object`, `JsonValue`, `JsonDict`, `JsonObject` and hand-rolled recursive JSON aliases are `Any` with extra steps.
- **Every generic is parameterised**: `dict[str, int]` not `dict`, `list[Node]` not `list`, `tuple[int, str]` not `tuple` — `Sequence`, `Mapping`, `set`, `frozenset` and `Iterable` alike. Pyright strict enforces this via `reportMissingTypeArgument`.

### State types for the checker

- **A class implementing a `Protocol` inherits it**, even though structural typing would accept it silently. Inheriting puts the error on the broken class rather than the distant list where the objects meet the annotation, and makes implementations navigable from the protocol. Contracts satisfied by types outside the codebase — a shape matching `subprocess.Popen`, say — stay structural.

### Text is a boundary

JSON exists only as text in files. On entering Python it becomes a Pydantic model via `model_validate_json`.

- Model and API output meets `model_validate_json` first.
- Serialise with `model_dump_json` / `model_json_schema` in the adapter, at the last possible moment.
- Anything read from a JSON file becomes a model immediately. Never index a parsed dict.
- Where the model class is generated at runtime, the containing type is **generic** (`Container[InT]`) and the class is resolved by import before validation — late-bound, not unknown.
