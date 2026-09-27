## Workflow — RedDragon

Bindings for `workflow.md`. Where this file and the generic one differ, this one
is the reality of the repo; the generic file is the target.

### Verification gate: what actually blocks a commit

`.pre-commit-config.yaml` is the gate. It is not uniform — some hooks block and
some only report, and the difference matters when deciding whether a failure is
allowed to stand.

**Blocking:**

- **Black** — formats and re-stages only the files pre-commit hands it
- **python-fp-lint** (the upstream `python-fp-lint` hook) — lints **staged blobs**
- **import-linter** — the `.importlinter` contracts
- **Full test suite** — `make test PYTEST_ARGS="-x -q"`, which builds the ProLeap
  bridge JAR first if it is missing. Several minutes; treat it as slow, not hung.
- **Terminology guard** and **Talisman**

**Advisory, wrapped in `|| true`:** the `pyright` hook and the repo-wide
"Python FP lint (warnings only)" hook. Neither can fail a commit. They exist so
the numbers stay visible while the backlog is worked down, so read their output
rather than assuming a green commit means zero errors.

Individual gates:

```bash
uv run python -m black .
uv run pyright                                                    # advisory in the hook
uv run python -m python_fp_lint check --config fp.json interpreter/ cobol_asg/
uv run lint-imports
make test PYTEST_ARGS="-q"                                        # builds the JAR, then the full suite
```

### Pyright: per-file promotion, not a repo-wide flag

`pyrightconfig.json` sets `typeCheckingMode: basic` for the whole repo. Files are
promoted individually by adding `# pyright: standard` as the first line; 240 files
carry it today. A promoted file is held to zero errors. An unpromoted file is not,
and its errors are expected rather than a regression.

So: promote a file when you have finished annotating it, never promote one you have
not just verified, and do not raise the repo-wide mode to make a single file strict.
Because the hook is advisory, pyright never blocks — run it yourself and compare the
count against what you started with.

### python-fp-lint: the ratchet

`fp-baseline.json` holds a single total. The gate lints the staged blob, and **every**
violation in a staged file blocks the commit, including violations that predate your
change — touching a file adopts it. When the total falls the baseline tightens
automatically and stages itself; it never loosens.

A high baseline is fine. Suppressions are not: **no exclusions — `fp.json` entries,
`# noqa`, per-file ignores, or anything else — without explicit review and approval.**
Fixing the violation or raising the baseline are the two available moves.

### Beads issue graph

`.beads/` (the Dolt working DB) is gitignored. `issues/issues.jsonl` is the tracked
source of truth for issues and every dependency edge. See `issues/README.md`.

- `export.auto = true` and `export.path = ../issues/issues.jsonl`, so the snapshot
  regenerates after any issue change. **Staging is still manual** — `git add
  issues/issues.jsonl` belongs in the same commit as the issue change.
- `import.auto = false`, so a fresh clone rebuilds its DB with
  `bd import issues/issues.jsonl`.
- Manual-export model: this DB is not synced through a Dolt remote.

File the issue before starting work, and give it enough detail that someone
arriving cold understands the problem without re-reading the surrounding code:
what is wrong, where it manifests, and the known constraints. When brainstorming
turns up something pertinent — a rejected approach, an edge case, a related issue
— put that on the issue too rather than only in the session.

### Working across 15 frontends

- **Verify a language's actual capability against the VM and frontend source.**
  Do not assume a feature is supported because a sibling language supports it.
- Consult the existing frontend and VM implementation, and the docs under
  `docs/frontend-design/`, before choosing an approach for a new language feature.
- For COBOL semantics the authorities are z/OS, IBM Enterprise COBOL and
  GnuCOBOL — research them rather than guessing. Reserve questions for genuine
  policy choices research cannot settle, such as which century-cutoff convention
  the project wants.

### Tests

- Unit tests assert **IR structure** — the expected opcodes, and no `SYMBOLIC`
  left behind. Integration tests compile, execute through the VM, and assert
  concrete output values.
- `@covers` from `tests/covers.py` marks which language feature a test exercises;
  233 test files use it. The hook that once enforced it is gone, so it rests on
  review.
- An `xfail` reason must cite the bead id, so the gap stays traceable:
  `@pytest.mark.xfail(reason="... — red-dragon-xxxx")`. Exclude languages that
  genuinely lack the feature rather than xfailing them (C has no classes).
- The default run excludes `external` and `nist` (see `project-context.md`). Do
  not read a green default run as covering them.

### Talisman

`.talismanrc` still contains duplicate entries for a few filenames. They are
residue of an earlier policy that treated duplicates as correct; under
`data-security.md` only the first entry per filename is honoured. Do not add to
them, and do not take them as a pattern to follow.
