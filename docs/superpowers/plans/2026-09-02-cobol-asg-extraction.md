# Extract the COBOL-ASG surface out of `interpreter/`

Goal: a sibling package holding "parse COBOL to an ASG and describe its data", so a
consumer that only reads COBOL never imports the VM. Driven by cobble, which needs exactly
that surface and nothing else.

## Why a sibling package rather than a lighter `interpreter`

Today cobble's import closure is **184 of `interpreter/`'s 301 modules, 45,244 loc** — the
VM, lowering, IR encoders, type inference and all fifteen language frontends — for ten
modules of declared surface. 164 of those 184 arrive through two `__init__.py` files that
run on *any* `interpreter.*` import: `interpreter/__init__.py` eagerly imports
`interpreter.api` and `interpreter.run`, and `interpreter/cobol/__init__.py` eagerly
imports `BYTE_BUILTINS`.

Deleting those re-exports would work — nothing imports them through the package root, and
the full suite passes without them. But it is the wrong fix to reach for, because a
top-level `cobol_asg/` makes the question moot: `import cobol_asg.cobol_parser` never
executes `interpreter/__init__.py` at all. Cobble stops importing `interpreter` in any form,
so what those files load stops being cobble's problem. Closure lands at **18 files, 4,661
loc** — the unit plus an empty `__init__.py`, and *zero* interpreter modules, which is
better than emptying the re-exports could achieve.

So `interpreter/__init__.py` and `interpreter/cobol/__init__.py` are **left exactly as they
are**. Trimming them is a separate, independently justified cleanup; it is not on this
plan's critical path, and doing both at once would confuse which change bought what.

`cobol_asg/__init__.py` stays empty — a docstring and no imports. That is the whole
mechanism, and phase 3's contract is what keeps it that way.

## The unit

17 modules, 4,661 loc. Zero imports leaving it — a true leaf, so the move is a rename and
nothing more. Third-party deps: `lark` (PICTURE + COPY grammars) and `tqdm` (only
`ast_store`). Column 1 is import-statement occurrences across this repo.

| refs | loc | module | role |
|---|---|---|---|
| 224 | 1582 | `interpreter/cobol/cobol_statements.py` | ASG statement vocabulary |
| 79 | 378 | `interpreter/cobol/asg_types.py` | ASG program/section/paragraph |
| 50 | 315 | `interpreter/cobol/cobol_expression.py` | ASG expressions |
| 43 | 149 | `interpreter/cobol/cobol_types.py` | COBOL data types |
| 29 | 29 | `interpreter/cobol/file_enums.py` | OPEN mode / organisation |
| 28 | 143 | `interpreter/cobol/cobol_parser.py` | ProLeap bridge front door |
| 26 | 214 | `interpreter/cobol/ref_mod.py` | reference modification |
| 22 | 481 | `interpreter/cobol/edit_picture.py` | edited-PICTURE formatting |
| 20 | 53 | `interpreter/cobol/subprocess_runner.py` | subprocess seam |
| 18 | 233 | `interpreter/cobol/pic_parser.py` | PICTURE parse |
| 16 | 69 | `interpreter/cobol/condition_name.py` | 88-level conditions |
| 14 | 52 | `interpreter/frontend_extension.py` | `DialectParser` protocol |
| 8 | 140 | `interpreter/cobol/ast_store.py` | ASG JSON cache |
| 4 | 238 | `interpreter/project/cobol_imports.py` | CALL/COPY extraction |
| 3 | 61 | `interpreter/project/import_types.py` | `ImportKind` / `ImportRef` |
| 1 | 490 | `interpreter/cobol/picture.py` | PICTURE grammar driver |
| 0 | 34 | `interpreter/cobol/source_text.py` | EBCDIC/ASCII decode |

Plus the data file `interpreter/cobol/picture.lark`. Loaded via
`Path(__file__).with_name("picture.lark")`, so it needs no code change — only to travel with
`picture.py`.

Consumers today: 25 non-test + 63 test modules in this repo; in red-dragon-forge, cicada
(39 files), cobble (22), jackal (5), squall (2).

What stays behind: `interpreter/cobol/` keeps its other 36 modules — `byte_builtins`,
`lower_*`, `ir_encoders`, `condition_lowering`, `emit_context`, `data_layout`,
`file_drivers`. That is the clean line: **`cobol_asg` parses, `interpreter.cobol` lowers.**

## Layout

Top-level `cobol_asg/`, sibling to `interpreter/`, shipped inside the existing `red-dragon`
wheel (`packages = ["interpreter", "cobol_asg"]`).

Rejected, with reasons:

- *Subpackage `interpreter/cobol_asg/`* — would leave the thing a part of `interpreter`,
  which defeats the point: the import would still run `interpreter/__init__.py`.
- *Its own distribution now* — would let a consumer install the parser without litellm,
  tree-sitter, mcp or pydantic. Nothing can exploit that yet: cobble also imports cicada,
  jackal and squall, and all three need the VM, so cobble's venv keeps red-dragon
  regardless. Deferred to phase 5, where it is a small additive change.
- *Its own git repo* — two submodules in forge and cross-repo version skew, for no gain over
  phase 5.

Module names carry over unchanged (`cobol_asg.cobol_statements`, not
`cobol_asg.statements`). The `cobol_` prefix is redundant inside the package, but keeping it
makes the whole move one mechanical substitution that a reviewer can verify by eye. Dropping
the prefixes is a separate, independently revertible commit if wanted.

Name: `cobol_asg` — the ASG is the artifact, and the type/PICTURE modules exist to describe
its data. `cobol_surface` is the alternative if "ASG" reads too narrow for the PICTURE half.

## Phase 1 — move the modules (DONE, 2026-09-02)

Phases 1-3 landed as one change: they are not separable at the gate, because the existing
`cobol-isolation` contract's `ignore_imports` name edges that phase 1 deletes, so
`lint-imports` cannot pass on phase 1 alone.

Result: `import cobol_asg.*` loads **18 modules and zero `interpreter` modules**, against 184
for the same surface before. Suite **15008 passed / 66 skipped / 17 xfailed** — identical to
the pre-move baseline. 6/6 contracts kept. Black clean over all 107 changed files. Pyright
708 errors, all pre-existing: 706 in files this change never touched (concentrated in the
language frontends), 2 in touched files but on lines it never edited
(`condition_lowering.py:810`, `lower_string_inspect.py:717`) — the repo runs pyright as
`|| true` in pre-commit, so a nonzero count is its normal state.


```bash
cd /Users/avisheksengupta/code/red-dragon
mkdir cobol_asg
for m in asg_types ast_store cobol_expression cobol_parser cobol_statements cobol_types \
         condition_name edit_picture file_enums pic_parser picture ref_mod source_text \
         subprocess_runner; do
  git mv interpreter/cobol/$m.py cobol_asg/$m.py
done
git mv interpreter/cobol/picture.lark cobol_asg/picture.lark
git mv interpreter/frontend_extension.py cobol_asg/frontend_extension.py
git mv interpreter/project/cobol_imports.py cobol_asg/cobol_imports.py
git mv interpreter/project/import_types.py cobol_asg/import_types.py
```

`cobol_asg/__init__.py`: a docstring saying the package must stay import-free, and nothing
else. An eager re-export here would rebuild the exact problem this plan exists to route
around.

Then rewrite the references. 203 lines across 97 files here, 141 across 70 files in forge.
Use a script, not `sed`:

```python
# scripts/rewrite_cobol_asg_imports.py — run once per repo, then delete.
import re, sys
from pathlib import Path

MOVED = """asg_types ast_store cobol_expression cobol_parser cobol_statements cobol_types
condition_name edit_picture file_enums pic_parser picture ref_mod source_text
subprocess_runner""".split()
RENAMES = {f"interpreter.cobol.{m}": f"cobol_asg.{m}" for m in MOVED}
RENAMES["interpreter.project.cobol_imports"] = "cobol_asg.cobol_imports"
RENAMES["interpreter.project.import_types"] = "cobol_asg.import_types"
RENAMES["interpreter.frontend_extension"] = "cobol_asg.frontend_extension"

DOTTED = re.compile(
    r"(?:" + "|".join(re.escape(k) for k in sorted(RENAMES, key=len, reverse=True)) + r")\b"
)
# `from interpreter.cobol import picture` — the three call sites that name the
# submodule rather than dotting into it.
PKG_FORM = re.compile(
    r"from interpreter\.(?:cobol|project) import (" + "|".join(MOVED) + r")\b"
)

for path in Path(sys.argv[1]).rglob("*.py"):
    if any(p in path.parts for p in (".venv", "__pycache__", "node_modules")):
        continue
    src = path.read_text()
    out = PKG_FORM.sub(r"from cobol_asg import \1", DOTTED.sub(lambda m: RENAMES[m.group()], src))
    if out != src:
        path.write_text(out)
```

The `(?:...)\b` grouping is load-bearing, and getting it wrong is silent.
`interpreter.frontend_extension` is a prefix of `interpreter.frontend_extension_lowering`, a
*different* module that stays in `interpreter/`. `_` is a word character, so `\b` refuses
that match — but `A|B|C\b` binds the `\b` to `C` alone, so the alternation must be wrapped.
Written without the group, the script rewrites `frontend_extension_lowering` too, and
nothing fails until import time. Both forms were checked against the eleven call-site shapes
in this repo, including `interpreter.cobol.byte_builtins`,
`interpreter.cobol.cobol_frontend`, `interpreter.project.compiler` and the
`logger="interpreter.run"` string, all of which must come through untouched.

Config to update in the same commit:

- `pyproject.toml`: `[tool.hatch.build.targets.wheel] packages = ["interpreter", "cobol_asg"]`
  and `[tool.coverage.run] source = ["interpreter", "cobol_asg"]`.
- `.importlinter`: add `cobol_asg` to `root_packages`.
- `fp.json`, `.pylintrc`, `.pre-commit-config.yaml`: check for `interpreter`-rooted paths.
- `.talismanrc` needs nothing — none of its 5 `interpreter/cobol|project` entries names a
  moved file.

Verify:

```bash
make test    # pre-move baseline, 2026-09-02: 15008 passed / 66 skipped / 17 xfailed
uv run lint-imports
uv run python -m black --check . && uv run pyright
```

## Phase 2 — move the unit's own tests (DONE, 2026-09-02)

Eleven test modules import nothing outside the unit and move to `tests/cobol_asg/`:

```
tests/integration/test_bridge_computed_goto.py
tests/integration/test_bridge_string_inspect_unstring_json.py
tests/unit/cobol/test_ast_store.py
tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py
tests/unit/cobol/test_dialect_parser.py
tests/unit/cobol/test_file_enums.py
tests/unit/test_asg_types.py
tests/unit/test_cobol_asg_types.py
tests/unit/test_condition_name.py
tests/unit/test_pic_parser.py
tests/unit/test_ref_mod.py
```

After the move these eleven load no VM at all, which is the cheapest available check that
the seam is real. The other 52 that touch the unit also touch lowering or the VM; they stay
where they are.

## Phase 3 — the contract that holds the seam (DONE, 2026-09-02)

This is the load-bearing phase. Without it, one convenience import inside `cobol_asg`
silently restores the whole dependency.

```ini
[importlinter:contract:cobol-asg-is-a-leaf]
name = The COBOL ASG surface must not import the interpreter
type = forbidden
source_modules =
    cobol_asg
forbidden_modules =
    interpreter
```

The existing `COBOL module only imported by frontend factory` contract also gets shorter.
Three of its seven `ignore_imports` exceptions exist only because parsing and lowering share
`interpreter.cobol`, and dissolve here:

```
interpreter.frontend -> interpreter.cobol.cobol_parser
interpreter.frontend -> interpreter.cobol.subprocess_runner
interpreter.project.cobol_compile -> interpreter.cobol.ast_store
```

## Phase 4 — forge side

Needs phases 1-3 committed and pushed in red-dragon first; forge consumes it as a submodule,
and CLAUDE.md forbids editing `vendor/red-dragon` in place.

```bash
cd /Users/avisheksengupta/code/red-dragon-forge
git -C vendor/red-dragon fetch origin && git -C vendor/red-dragon checkout <new-sha>
uv run python scripts/rewrite_cobol_asg_imports.py .   # 70 files: cicada 39, cobble 22, jackal 5, squall 2
uv sync --all-packages
```

`cobble/pyproject.toml` drops `red-dragon` for `cobol-asg` — cobble imports *only* unit
modules, so the declared dependency narrows to exactly what it uses. cicada, jackal and
squall keep both.

Add to the root `.importlinter`, now that cobble's actual surface admits it:

```ini
[importlinter:contract:cobble-does-not-import-the-interpreter]
name = cobble must not import the interpreter
type = forbidden
source_modules =
    cobble
forbidden_modules =
    interpreter
```

Verify: `make test-all`, `uv run lint-imports`, and cobble's graph identity check
(`cd cobble && make compare`, must stay 449/803 with an empty diff). Run squall's and
jackal's suites explicitly — the closure analysis behind this plan baselined cobble and
cicada but not those two.

## Phase 5 — its own distribution (deferred)

Add `cobol_asg/pyproject.toml` (deps: `lark`, `tqdm`) and have red-dragon depend on it by
path. Do this when something wants the COBOL parser without the VM's dependency tree. Until
then it buys nothing, because cobble reaches the VM through cicada anyway.

## Phase 6 — get `tqdm` out of `ast_store` (independent, do any time)

`ast_store.py` is the unit's only `tqdm` user: a progress bar inside library code, which
decides for its caller that there is a terminal to draw on. Replace with a progress callback
the caller supplies. Removes a dependency from the package and a policy from the library.

## Not in scope: the dead re-exports

`interpreter/__init__.py`'s eager `api` + `run` imports and `interpreter/cobol/__init__.py`'s
eager `BYTE_BUILTINS` have no users through the package root — 119 files import those names
from the modules directly, and nothing reads them as package attributes. Removing them is a
real cleanup, and it was measured to be a no-op (full suite green, `interpreter.api`,
`interpreter.run` and `interpreter.vm.builtins` all still import, forge unaffected). It is
deliberately *not* part of this plan: after phase 1 no COBOL-parsing consumer touches those
files, so the change stands or falls on its own merits and belongs in its own commit.
