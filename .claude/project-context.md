## Project Context

- **Language:** Python 3.13+ (main codebase), Markdown (docs)
- **Package manager:** Poetry (`poetry run` prefix for all commands)
- **Test framework:** pytest with pytest-xdist (parallel by default)
- **Formatter:** Black
- **Architectural contracts:** import-linter (`.importlinter`)
- **Pre-commit hooks:** Talisman (secret detection)
- **Issue tracker:** Beads (`bd`)
- **ADRs:** `docs/architectural-design-decisions.md`
- **Specs (immutable):** `docs/superpowers/specs/` and `docs/superpowers/plans/` — never modify these. Newer specs supersede older ones by convention.

## Task Tracking

Use `bd` (Beads) for ALL task tracking. Do NOT use markdown TODO lists.

1. File an issue before starting work: `bd create "title" --description="..." -t bug|feature|task -p 0-4`
   - **Exhaustive details required.** The description must include enough context for someone (or a future agent) to understand the problem and approach without re-reading the surrounding code. Include: what is wrong or missing, where in the codebase it manifests, and any known constraints.
   - If the brainstorm or planning phase yields pertinent extra detail (trade-offs considered, rejected approaches, edge cases discovered, related issues), add that to the Beads issue as well.
2. Claim it: `bd update <id> --claim`
3. When done: `bd close <id> --reason "..."`
4. Before every commit: `bd backup`

## External Dependencies

- Integration tests depend on local repo paths (`~/code/mojo-lsp`, `~/code/smojol`).
- COBOL frontend requires JDK 17+ and the ProLeap bridge JAR.
- Neo4j is optional (for graph persistence).
- Universal CTags is external (for code symbol extraction).
