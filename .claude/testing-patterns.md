## Testing Patterns

- **TDD:** Write failing tests first. For every bug fix, write a test that fails without the fix.
- **Review assertions after writing tests.** After writing tests, review every assertion for specificity. Replace weak assertions (`assert x is not None`, `assert "name" in result`, `assert len(items) > 0`) with concrete value assertions (`assert result == 30`, `assert items == [1, 2, 3]`). If a concrete assertion isn't possible, document why.
- **Unit vs integration:** Unit tests (no I/O) in `tests/unit/`. Integration tests (LLMs, databases, external repos) in `tests/integration/`.
- **Fixtures:** Use `pytest` fixtures and `tmp_path` for filesystem tests.
- **No mocking:** Do not use `unittest.mock.patch`. Use dependency injection with mock objects.
- **Assertions are sacred:** Do not modify test assertions unless certain the change is valid. Do not remove assertions without review.
- **No implementation hacks for tests:** Never add special behavior just to make tests pass. Document hard-to-implement behavior or ask for guidance.
- **xfail for frontend gaps:** If a frontend doesn't handle a feature yet, write the real test with correct assertions, mark it `xfail` with `reason="description — <issue-id>"`, and file a corresponding Beads issue. The xfail reason must reference the issue ID so it's traceable. Don't rename tests or write fallback programs. Exclude languages that genuinely lack the feature (e.g., C has no classes).
- **Both unit and integration tests** for every new feature. Unit tests verify IR structure (correct opcodes, no SYMBOLIC). Integration tests compile, execute through the VM, and assert on **concrete output values**. This applies even when verifying suspected already-working features — "it probably works" is not a substitute for a test that proves it. If a feature is being closed as "already handled," write the integration test that confirms it before closing.
