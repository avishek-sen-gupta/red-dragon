## Workflow — Python

Bindings for `workflow.md`.

### Build tool

Use the `uv run` prefix for all Python commands. On Poetry-managed projects
substitute `poetry run`.

### Verification gate

Substitute for the placeholders in `workflow.md`:

```bash
uv run black .                              # formatter
uv run pyright                              # strict mode, zero errors
python-fp-lint check --config fp.json src/  # linter
uv run pytest tests/                        # ALL tests, unit and integration
```

### The linter: python-fp-lint

[python-fp-lint](https://github.com/avishek-sen-gupta/python-fp-lint) fills the
linter slot. It is the executable half of these guidelines: most of the rules in
`guardrails.md`, `programming-patterns.md` and `testing.md` are decidable by a
checker, and this is the checker that decides them. Where a rule appears in both
places, the linter is the enforcement and the guideline file is the rationale.

Wire it into the commit itself rather than trusting yourself to run it. From the
root of the project being gated:

```bash
/path/to/python-fp-lint/install-precommit.sh
```

That copies the ast-grep rule files into `.python-fp-lint/`, seeds `fp.json` from
`config.example.json` with `lint_rules_dir` pointing there, wires the hook into
`.pre-commit-config.yaml`, and runs `pre-commit install`. Re-running refreshes
the rules and leaves the rest alone. It must run from the target repo root — it
takes the working directory as the project. For a manual gate outside pre-commit,
`uv tool install git+https://github.com/avishek-sen-gupta/python-fp-lint` puts
the command on `PATH`.

`fp.json` is the project's rule set: checked in, reviewed like source. `--config`
is required and has no default or search path — name the file or the command is a
usage error.

Three properties of the gate worth knowing before it surprises you:

- It lints the **staged blob**, not the worktree file. Those differ whenever a
  file is partially staged, and the blob is what gets committed.
- **Every** violation in a staged file blocks the commit, including ones that
  predate your change. Touching a file adopts it. Unstaged files are not examined.
- `--strict` (what the hook uses) exits 2 when a backend is missing. Without it a
  missing `sg` or `ruff` is skipped silently, turning a broken install into a
  passing commit.

**Never put a `.gitignore` inside `.python-fp-lint/`.** ast-grep then matches
nothing, and the gate passes everything while appearing to run.

### What the linter enforces

Each guideline below is checked, not merely stated. This table is why a
violation is a build failure rather than a review comment:

| Guideline | Rules |
|---|---|
| `programming-patterns.md` — no `for` loops with mutations | `no-loop-mutation`, `no-list-append`/`extend`/`insert`/`pop`/`remove`, `no-dict-clear`/`update`/`setdefault`, `no-set-add`/`discard`, `no-subscript-mutation` and the subscript family |
| `programming-patterns.md` — immutable by default, never mutated after construction | `no-unfrozen-dataclass`, `no-mutation-outside-init`, `no-local-augmented-mutation`, `no-attribute-augmented-mutation` |
| `guardrails.md` — the "any" type is banned | `no-any-type`, Ruff `ANN401` |
| `guardrails.md` — no untyped blobs | `no-object-type` |
| `programming-patterns.md` — no defensive programming, no null checks, no generic exception handling | `no-is-none`, `no-is-not-none`, `no-or-none-fallback`, Ruff `BLE` |
| `programming-patterns.md` — no null as a default parameter | `no-none-default-param`, `no-optional-none` |
| `programming-patterns.md` — read-only collection types for parameters | `no-list-dict-param-annotation` |
| `programming-patterns.md` — no static methods or static utility classes | `no-static-method`, `no-classmethod-utility` |
| `programming-patterns.md` — small, composable functions; no massive functions | Ruff `C901` (complexity, default ceiling 3), `PLR0915` (statements, default ceiling 10) |
| `programming-patterns.md` — prefer early return | `no-deep-nesting` |
| `programming-patterns.md` — log, never `print` | Ruff `T20` |
| `programming-patterns.md` — fully qualified imports, no relative imports | Ruff `TID252` |
| `testing.md` — concrete assertions, not not-null/containment/non-empty checks | `no-weak-assert` |
| `testing.md` — mark known gaps with a reason and an issue reference | `no-xfail-without-reason` |

Two gaps the linter cannot close, which is why pyright stays in the gate above:
`no-any-type` sees only *explicit* `Any`, so implicit `Any` from a missing
annotation is pyright's `reportUnknownParameterType`/`reportMissingParameterType`;
and unparameterised generics are pyright's `reportMissingTypeArgument`.

The rules with no checker — no gold plating, no comments, text-as-boundary, one
test per behaviour, ports-and-adapters — rest on review. Treat them with more
suspicion in self-review, not less, precisely because nothing fails when they
slip.

### Introspection

- Write temporary scripts to the scratchpad directory and run them with `uv run python <path>`. Clean up afterwards.
- Do not use `python -c` with multiline strings.
