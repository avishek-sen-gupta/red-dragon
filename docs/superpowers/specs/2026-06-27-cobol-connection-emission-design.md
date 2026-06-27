# COBOL Connection Emission — Design Spec

**Date:** 2026-06-27  
**Status:** Approved

## Goal

Extract and emit inter-program connections discovered during COBOL lowering — `COPY` (copybook inclusion) and `CALL` (subprogram invocation) — as structured data. This is a separate, analysis-only mode: no VM execution takes place. Output is a `list[Connection]` returned from a dedicated API function, which callers can serialise to NDJSON and pipe to a file.

## Scope

- Input: a full COBOL project directory (multiple `.cbl` files with transitive CALL resolution)
- Connection types: `COPY` and `CALL`
- Invocation: Python API only; CLI exposure deferred until feature matures

## Data Model

`interpreter/project/cobol_connections.py` (new file):

```python
@dataclass(frozen=True)
class ProgramRef:
    name: str              # program/copybook name as written in source (or file stem for source)
    file_path: Path | None # resolved absolute path on disk; None for unresolved copybooks

@dataclass(frozen=True)
class Connection:
    kind: Literal["COPY", "CALL"]
    source: ProgramRef     # the program containing the COPY/CALL statement
    target: ProgramRef     # the referenced copybook or subprogram
```

`Connection` is directional: `source` references the file containing the statement; `target` references what it names.

`to_json()` on `Connection` emits a flat JSON object suitable for NDJSON output:
```json
{"kind": "COPY", "source_name": "COBOLPROG", "source_file": "src/COBOLPROG.cbl", "target_name": "DFHEIBLK", "target_file": null}
{"kind": "CALL", "source_name": "COBOLPROG", "source_file": "src/COBOLPROG.cbl", "target_name": "ACCTMGR", "target_file": "src/ACCTMGR.cbl"}
```

## How Connections Are Sourced

Both `COPY` and `CALL` statements are already extracted from raw COBOL source by `_extract_cobol_imports()` in `interpreter/project/imports.py` using a Lark grammar. They are stored in `ModuleUnit.imports` as `ImportRef` entries:
- `COPY DFHEIBLK` → `ImportRef(module_path="DFHEIBLK", kind=INCLUDE)`
- `CALL 'ACCTMGR'` → `ImportRef(module_path="ACCTMGR", kind=REQUIRE)`

Resolved file paths for `CALL` targets are available post-compilation in `LinkedProgram.import_graph: dict[Path, list[Path]]`.

Resolved file paths for `COPY` targets are **not** tracked (copybooks are inlined by the ProLeap bridge before red-dragon sees the ASG). `target.file_path` is `None` for COPY connections.

**No changes to the ProLeap bridge, `compile_cobol_module()`, `compile_cobol()`, or `ModuleUnit`.**

## API

`extract_cobol_connections()` in `interpreter/project/cobol_connections.py`:

```python
def extract_cobol_connections(
    source: bytes,
    source_file: Path,
    copybook_dirs: list[Path] = [],
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[Path, bytes] | None = None,
) -> list[Connection]
```

Signature mirrors `compile_cobol()` so callers can switch between them. Internally:

1. Calls `compile_cobol()` — produces `(_, linked_program)`. Compilation handles transitive CALL resolution across the whole project.
2. Builds `resolved_calls: dict[Path, dict[str, Path]]` from `linked_program.import_graph`: for each caller path, maps called program name → resolved callee path (by matching `ImportRef.module_path` against callee path stems).
3. Iterates `linked_program.modules.items()`. For each `(module_path, module)`:
   - `source_ref = ProgramRef(name=module_path.stem, file_path=module_path)`
   - `INCLUDE` refs → `Connection(kind="COPY", source=source_ref, target=ProgramRef(name=ref.module_path, file_path=None))`
   - `REQUIRE` refs → `Connection(kind="CALL", source=source_ref, target=ProgramRef(name=ref.module_path, file_path=resolved_calls.get(module_path, {}).get(ref.module_path)))`
4. Returns the combined list (COPYs and CALLs interleaved in module iteration order).

## Files

| File | Change |
|------|--------|
| `interpreter/project/cobol_connections.py` | **New** — `ProgramRef`, `Connection`, `extract_cobol_connections()` |
| `tests/unit/project/test_connections.py` | **New** — unit tests for data model and `to_json()` |
| `tests/integration/test_cobol_connections.py` | **New** — integration tests against real COBOL source |

No existing files are modified.

## Out of Scope

- Resolved file paths for COPY targets (deferred; requires bridge changes)
- `PROGRAM-ID` paragraph value as source identity (deferred; requires ASG access)
- CLI exposure (deferred until feature matures)
- Connection types beyond COPY and CALL
