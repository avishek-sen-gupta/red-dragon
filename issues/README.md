# issues/ — version-controlled issue graph

`issues.jsonl` is the tracked snapshot of the Beads issue graph (epics, stories, status, labels,
and all dependency edges). It is the source of truth for the backlog *in git*.

| Path | Tracked? | Role |
|---|---|---|
| `.beads/` | no (gitignored) | local Dolt working DB — rebuildable |
| `issues/issues.jsonl` | **yes** | portable, diffable snapshot |

This repo uses the **manual-export** model: the canonical RedDragon DB is local, not synced via a
Dolt remote. `bd` writes the snapshot here automatically (see below); git is what makes it durable.

## Auto-export

`.beads/config.yaml` sets `export.path: ../issues/issues.jsonl` with `export.auto: true`, so `bd`
refreshes this file after write commands, throttled to once per 60s.

`export.git-add` is deliberately **false** — the export is never staged for you. Two consequences:

- `git status` can go dirty at unpredictable moments while you work. That is the export, not a bug.
- **Staging is yours to do.** Before committing an issue change, check the file is current and stage it:

```bash
bd export -o issues/issues.jsonl   # force a write, ignoring the throttle
git add issues/issues.jsonl
```

This is a deliberate *step*, not a git hook. A hook that regenerates a tracked file mid-commit
fights pre-commit's stash-restore and intermittently aborts the commit — that is why the old
`beads-backup` pre-commit hook was disabled and has now been removed.

## Fresh clone

`bd init` is the right tool — its intrusive behaviour is opt-out, and the two flags that matter are
`--skip-hooks` and `--skip-agents`. Verified clean on 2026-09-26 with bd 1.3.0:

```bash
bd init --prefix red-dragon --non-interactive --quiet --skip-hooks --skip-agents --role maintainer
bd import issues/issues.jsonl
bd config set export.auto true
bd config set export.path "../issues/issues.jsonl"
bd config set import.auto false
```

With those flags `bd init` touches nothing outside `.beads/`: no `core.hooksPath`, no git hooks, no
`AGENTS.md`/`CLAUDE.md` rewrite, no `.agents/`, `.codex/` or `.cursor/`. **Without** them it does all
of those — and the `core.hooksPath` change is the dangerous one, because git honours exactly one
hooks directory, so repointing it silently orphans `.git/hooks` and the pre-commit framework's real
hooks. It stays silent because `bd` copies the pre-commit shim into its own directory, so the suite
still appears to run.

`--role maintainer` only avoids an interactive prompt; `--non-interactive` alone would default to it.

### Gotchas

- **Do not batch `bd config set` in a tight loop.** Rapid successive `bd` invocations contend on
  `.beads.gate.lock` and the write fails. Combined with `cmd >/dev/null 2>&1 && echo ok` the failure
  is invisible. Run them one at a time and read the `Set <key> = <value>` confirmation.
- **`export.path` escapes `.beads/`** despite the config comment saying to keep paths under it —
  `../issues/issues.jsonl` works and is what this repo uses.
- **bd 1.3.0 removed the `pre_triage` status.** The 7 issues that carried it are stored here as
  `status: deferred` with the label `pre-triage`, so the snapshot imports cleanly as-is. If you ever
  restore an older snapshot containing a literal `pre_triage`, the import fails with
  `invalid status: pre_triage` partway through — it is resumable, so remap and re-run.

### Verifying a rebuild

```bash
bd export -o /tmp/rebuilt.jsonl
diff <(sort /tmp/rebuilt.jsonl) <(sort issues/issues.jsonl)
```

A rebuild from this snapshot round-trips exactly: 1,440 issues, identical titles, statuses,
priorities, bodies and dependency counts.
