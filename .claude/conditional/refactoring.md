## Refactoring Principles

### Type propagation

When replacing a primitive (`str`) with a domain type (`CodeLabel`) across a codebase, use `get_impact_radius_tool` to map blast radius before starting, and `ast-grep` to find all construction sites structurally:

- **No coercion validators.** Do not add Pydantic `field_validator` or `__post_init__` hacks that auto-convert strings to the domain type. These mask call sites that should be explicitly updated. If Pydantic rejects a value, the caller is wrong — fix the caller.
- **Push wrapping to the origin.** Wrap at the point the value is created (`fresh_label()`, JSON parse boundary, LLM response), not at every intermediate consumer. If a factory returns the domain type, downstream code should never need to re-wrap.
- **No defensive `isinstance` checks.** Code like `label if isinstance(label, CodeLabel) else CodeLabel(label)` is a symptom of inconsistent callers. Fix the callers to always pass the right type. The handler should just read the value.
- **Domain methods over string extraction.** Add methods to the type (`starts_with`, `contains`, `namespace`, `extract_name`, `branch_targets`) instead of extracting `.value` and calling string methods. If you need `startswith`, add `starts_with` to the type.
- **`__contains__` and `__str__` make the type ergonomic.** `"x" in label` and f-string formatting should work naturally. Add `__contains__` and `__str__` to the domain type.
- **Validate at construction, not at use.** Add `__post_init__` to reject invalid values (e.g., `CodeLabel(value=CodeLabel(...))` double-wrapping) so bugs surface immediately at the construction site, not at some distant consumer.
- **Separate name generation from label generation.** If a factory (`fresh_label`) is used for both labels and non-label unique names (e.g., variable names), split it into `fresh_label() -> CodeLabel` and `fresh_name() -> str`. Don't let a label factory produce non-labels.
- **Serialization at the boundary.** Use `str(label)` only at JSON serialization, display, and string-keyed dict boundaries (e.g., `FuncRef.label` which is still `str`). Never `str()` in the middle of a pipeline just to feed it back into `CodeLabel(...)`.
- **File issues for the next ring.** After propagating the type into the immediate adjacents, file issues for the next ring of types that still use strings (e.g., `FuncRef.label`, `ClassRef.label`). Don't try to do everything in one session.
- **Grep for bare-string comparisons before committing.** Domain types that return `NotImplemented` from `__eq__` for `str` cause silent failures: `"name" in typed_dict` returns `False`, `value == "string"` returns `False`. Always search for `== "`, `in frozenset(`, and `not in` patterns against the migrated field. These are the #1 source of post-migration bugs.
- **`or None` defeats null-object sentinels.** Patterns like `result_reg or None` convert a falsy sentinel (`NO_REGISTER`, `NO_LABEL`) back to `None`, breaking the null-object pattern. Replace with direct pass-through: `result_reg=result_reg`.
- **Bridge removal is a separate commit.** Migrate all callers first, verify all tests pass, then remove the bridge conversion in a follow-up commit. This isolates failures.
- **Dict-literal kwargs are a separate migration surface.** `{"result_reg": "%0"}` in test fixtures is not caught by the same search as `result_reg="%0"`. JSON fixture dicts that feed `json.dumps()` must keep string values; dicts that feed `**kwargs` or direct API calls need domain types.
- **Domain types are not JSON-serializable.** Every `json.dumps` path, MCP formatting dict, and `to_dict()` method needs `str()` at the boundary. Check all serialization paths after migration.
