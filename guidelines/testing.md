## Testing

See `guardrails.md` first — few tests, each covering a whole behaviour. These patterns govern how those tests are written, not how many there are.

- **TDD.** Write failing tests first. For a bug fix, extend an existing behaviour test so it fails without the fix rather than adding a new test file.
- **Unit and integration, both, for every feature.** Start from the smallest feasible unit of code. They live in separate trees, named in the language layer. Unit tests (no I/O, no network) verify structure — correct shape, no placeholders. Integration tests (LLM calls, databases, real subprocesses) run end-to-end and assert on **concrete output values**. This holds even for a feature you suspect already works: if it is being closed as "already handled", write the test that confirms it before closing.
- **No mocking.** No monkey-patching, no patching of module internals. Inject fakes — a scripted fake LLM, an injected clock, an injected spawner.
- **Fixtures.** Use test framework fixtures and temp directories for filesystem tests.
- **Concrete assertions.** After writing a test, replace weak assertions — a not-null check, a substring or containment check, a non-empty length check — with an equality assertion against the actual expected value. If a concrete assertion isn't possible, say why.
- **Mutation-check a new test before trusting it.** Break the code it covers in the two most obvious ways and confirm it fails. A test written after the code is a hypothesis until it has failed at least once.
- **Assertions are sacred.** Do not weaken or remove an assertion to make a test pass. Change one only when you are certain the new expected value is correct, and never remove one without review.
- **No implementation hacks for tests.** Never add behaviour that exists only to make a test pass. Document hard-to-implement behaviour, or ask.
- **Mark known gaps, don't hide them.** For unimplemented behaviour, write the real test with correct assertions and mark it as an expected failure with a reason and an issue reference, using the framework's marker. Don't rename the test or write a fallback.
