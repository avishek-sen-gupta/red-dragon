## Project Context

- **Language:** Python 3.13+ (`requires-python = ">=3.13,<4.0"`)
- **Purpose:** RedDragon — an experimental toolkit for "executing" frequently-incomplete code (legacy source, decompiled binaries, partial extracts, missing dependencies), lowering 15 tree-sitter languages and COBOL to one 37-opcode IR and running it on a VM.
- **Package manager:** uv — `uv run` prefixes every Python command
- **Test framework:** pytest with pytest-xdist, parallel by default. `addopts = "-n auto --dist=worksteal -m 'not external and not nist'"`, so the default run **excludes** two marker sets.
- **Formatter:** Black
- **Type checker:** Pyright, `pyrightconfig.json` — `typeCheckingMode: basic` over `interpreter`, `cobol_asg`, `mcp_server`, with per-file promotion to `standard` (see `project/workflow.md`)
- **Linter:** python-fp-lint, `fp.json`, with the ratchet baseline in `fp-baseline.json`
- **Architecture contracts:** import-linter, `.importlinter`
- **Secret detection:** Talisman, `.talismanrc`
- **Terminology guard:** `precommit-scripts/check-terminology`, with rules at `~/.config/git/terminology.toml` generated from a blocklist by `precommit-scripts/blocklist-to-toml`. Both live outside the repo, so they are per-machine.
- **Issue tracker:** beads (`bd`) over Dolt. `.beads/` is gitignored; `issues/issues.jsonl` is the tracked source of truth. See `issues/README.md`.
- **ADRs:** `docs/architectural-design-decisions.md`
- **Living docs:** `README.md`, `docs/ir-reference.md`, `docs/type-system.md`, `docs/linker-design.md` — updated in the same commit as the change they describe
- **Specs (immutable):** `docs/superpowers/specs/`, `docs/superpowers/plans/` — never modify. Newer specs supersede older ones by convention.

### Test markers

Registered in `pyproject.toml`. Two are excluded from the default run:

- `external` — needs live LLM APIs; run with `-m external`
- `nist` — the NIST-85 COBOL conformance suite; run with `-m nist` (most currently fail, see red-dragon-m0oa.7)
- `carddemo_e2e` — AWS CardDemo end-to-end CICS tests, skipped in CI

### Package layout

The four import-linter root packages — `interpreter`, `cobol_asg`, `cobol_memory`,
`cobol_numeric` — are siblings, not subpackages, and the contracts exist to keep
them that way: importing anything under `interpreter` runs
`interpreter/__init__.py`, which loads the VM. `cobol_asg` parses COBOL,
`interpreter.cobol` lowers it, and `cobol_memory` holds storage algebra. A
consumer that only reads COBOL or computes byte ranges must not pay for the VM.

## External Dependencies

- uv (packaging), pytest, pytest-xdist, Black, Pyright, pre-commit
- python-fp-lint — ast-grep, Ruff and beniget backends; needs `sg` and `ruff` reachable
- import-linter (`lint-imports`)
- tree-sitter and tree-sitter-language-pack — the 15 deterministic frontends
- Pydantic — boundary parsing; textual — the TUI
- **JDK 17+ and Maven**, for the ProLeap COBOL parser bridge. `make jar` builds
  `proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar`, `make test` depends on
  it, and the parser JAR itself resolves from `~/.m2`.
- Talisman — secret scanning
- beads (`bd`) over Dolt — issue tracking
- ast-grep and ripgrep on PATH

## Related Projects

- **red-dragon-forge** — sibling repo, shares these conventions and the same lint
  and type-check gates.
- **python-fp-lint** — the linter in the verification gate, developed alongside
  this repo rather than vendored.
- **cicada** — the CICS/CardDemo runtime and its end-to-end tests moved there
  (see 975277bf); this repo no longer wires that toolchain.
- **cobble** — its knowledge-graph extractor imports `cobol_asg` and nothing
  else, which is what the `cobol-asg-is-a-leaf` contract protects.
- **agent-guidelines-templates** — where the language-neutral and Python
  guideline files come from; fixes general enough to apply elsewhere belong
  upstream there rather than here.
