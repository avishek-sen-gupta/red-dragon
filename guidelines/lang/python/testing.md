## Testing — Python

Bindings for `testing.md`.

- **`pytest`** with fixtures; **`tmp_path`** for filesystem tests.
- **No `unittest.mock.patch`, no monkey-patching.** Inject fakes — a `FakeLLM` with scripted replies, an injected clock, an injected spawner.
- **Test trees**: unit tests in `tests/unit/`, integration tests in `tests/integration/`.
- **Expected failures** use `@pytest.mark.xfail(reason=...)` with an issue reference.
