## Refactoring — Python

Bindings for `refactoring.md`.

- **No defensive type checks.** `x if isinstance(x, T) else T(x)` means the callers disagree. Fix the callers.
- **Watch for `or None`-style fallbacks.** `result or None` converts a falsy sentinel back to `None`, breaking the null-object pattern. Use direct pass-through.
- **No coercion validators.** A Pydantic `field_validator` or `model_post_init` that quietly converts a string into the domain type hides the call sites that should have been updated.
