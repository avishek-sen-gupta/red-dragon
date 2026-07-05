# Coprocessor-Compile Unification Design

## Problem

Three repos independently compose "one or more extension strategies + dialect
parsers + extra program-source search directories, then call `compile_cobol`"
into a working `LinkedProgram`:

- **red-dragon-forge** (`red_dragon_forge/coprocessor.py` + `compile.py`):
  generic, N-way composition over an arbitrary list of `CoprocessorSpec`s.
- **Cicada** (`cics/bootstrap.py::compile_cics_program`): the same shape,
  hand-rolled for exactly one CICS strategy.
- **Squall** (`tests/integration/squall_cobol_helpers.py::compile_cobol`): the
  same shape again, hand-rolled for exactly one SQL strategy.

This is real, recurring duplication — not merely stylistic. It was proven
costly this session: a single upstream RedDragon signature change
(`program_source_dir` → `program_source_dirs`) required separate,
independent edits across all three call sites, in lock-step, to avoid
breaking any of them.

Forge's own `CoprocessorSpec`/`compile_program` are, on inspection, already
fully generic — neither imports `cics.*` or `squall.*`. They live in forge
only by project-layout convention.

## Why the fix isn't "cicada/squall depend on forge"

Forge's `adapters/cics.py` imports `cics.*` and `adapters/sql.py` imports
`squall.*` (forge → cicada, forge → squall). If cicada or squall depended on
forge for the shared composition logic, that would be a circular package
dependency. The shared piece must live below all three consumers — which
RedDragon already is.

## Design

### New RedDragon module: `interpreter/project/coprocessor_compile.py`

A sibling of the existing `interpreter/project/cobol_compile.py` and
`cobol_connections.py`. Contains, moved essentially verbatim from
`red_dragon_forge/coprocessor.py` + `compile.py` (import paths adjusted):

```python
@dataclass(frozen=True)
class CoprocessorSpec:
    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    dialect_parser: DialectParser = NullDialectParser()
    extra_program_source_dirs: Callable[[], Sequence[Path]] = (
        _no_extra_program_source_dirs
    )


def compile_program(
    source: bytes,
    parser: Any,
    specs: Sequence[CoprocessorSpec],
    *,
    program_source_dirs: Sequence[Path] = (),
) -> tuple[Any, LinkedProgram]:
    ...
```

Names are unchanged ("coprocessor" is already established vocabulary across
Cicada/Squall/forge docs). No import-linter changes are needed: this module
touches only `interpreter.project.cobol_compile.compile_cobol` and
`interpreter.frontend_extension` types — never `interpreter.cobol.*`
directly — exactly like `cobol_compile.py` itself is already exempt.

### Cicada: `cics/bootstrap.py`

`compile_cics_program`'s public signature
(`source, parser, strategy, *, program_source_dirs`) is unchanged. Internally
it builds exactly one `CoprocessorSpec`:

```python
spec = CoprocessorSpec(
    name="cics",
    make_strategy=lambda: strategy,
    source_prepass=apply_cics_prepass,
    dialect_parser=CicsDialectParser(),
    extra_program_source_dirs=lambda: (LE_STUBS_DIR,),
)
_frontend, linked = compile_program(
    source, parser, [spec], program_source_dirs=program_source_dirs
)
```

`run_carddemo_region`'s signature and behavior are unchanged (it already only
forwards to `compile_cics_program`). No CardDemo test file needs to change.

### Squall: `tests/integration/squall_cobol_helpers.py`

`compile_cobol()`'s public signature is unchanged. Internally it builds one
`CoprocessorSpec` mirroring forge's existing `build_sql_spec` pattern — a
private one-element holder list threads `field_meta` from
`source_prepass` (wrapping `apply_sql_prepass`) into `make_strategy`:

```python
field_meta_holder: list[Mapping[str, FieldMeta]] = [{}]

def _prepass(source: str) -> str:
    result = apply_sql_prepass(source, dirs)
    field_meta_holder[0] = result.field_meta
    return result.source

spec = CoprocessorSpec(
    name="sql",
    make_strategy=lambda: SqlLoweringStrategy(connections, field_meta_holder[0]),
    source_prepass=_prepass,
    dialect_parser=SqlDialectParser(),
)
return compile_program(source.encode("utf-8"), parser, [spec])
```

No squall unit/integration test needs to change beyond this one helper file.

### red-dragon-forge

`red_dragon_forge/coprocessor.py` and `red_dragon_forge/compile.py` are
deleted outright — not kept as re-exports. `adapters/cics.py`,
`adapters/sql.py`, `run.py`, and forge's own test files import
`CoprocessorSpec`/`compile_program` directly from
`interpreter.project.coprocessor_compile`.

`build_cics_spec`/`build_sql_spec` are unchanged in shape and stay in forge —
they remain the only place forge imports both `cics.*` and `squall.*`
together, per forge's existing "only adapters/ (besides run.py)" convention.

### Testing

Forge's existing `tests/integration/test_coprocessor.py` and
`test_compile_program.py` (already fake-strategy-based, no real cics/squall
dependency) move into RedDragon's own unit-test suite as
`tests/unit/project/test_coprocessor_compile.py`, as the canonical coverage
for this mechanism, rather than being duplicated across two repos. They're
deleted from forge once RedDragon's copy exists.

Cicada's and squall's existing end-to-end suites (CardDemo integration tests,
EXEC SQL tests) already prove behavior is unchanged, since neither's public
call signature moves.

## Sequencing

1. RedDragon: add `coprocessor_compile.py` + its own tests (moved from
   forge's fakes). Commit, push.
2. Cicada and Squall, in either order: bump `vendor/red-dragon`, rewire
   internally, verify existing suites unchanged. Commit, push each.
3. red-dragon-forge last: delete `coprocessor.py`/`compile.py`, rewire
   `adapters/`/`run.py`/tests, bump all three vendor pins (+ nested copies),
   verify full suite including the live-Db2 INQCUST e2e and the CEEDAYS
   proof test. Commit (no remote to push to).

## Non-goals

- No change to `CoprocessorSpec`/`compile_program`'s behavior or field
  shapes beyond the import-path move.
- No change to any coprocessor's own strategy/dialect-parser construction
  logic (`CicsLoweringStrategy`, `SqlLoweringStrategy`, etc.) — only the
  composition harness moves.
- No change to cicada's or squall's public call signatures.
