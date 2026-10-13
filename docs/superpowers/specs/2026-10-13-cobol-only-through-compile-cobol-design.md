# COBOL only through compile_cobol — design

**Date:** 2026-10-13
**Status:** approved in conversation; second of three specs (the first removed the
single-file surfaces, ADR-180; the third gives the tree-sitter languages one
multi-file compile core)

## Context

COBOL compiles two ways. `compile_cobol` is the full path: AST cache, extension
strategies, dialect parsers, LP32/LP64, the main program's data layout and entry
label. Every forge runtime reaches it through `coprocessor_compile.compile_program`.
`compile_directory` also accepts COBOL and compiles every `.cbl`/`.cob` under a tree
with none of that; about 40 red-dragon tests and `python -m interpreter <dir>` use it.

`compile_cobol` also decides *what* to compile: it walks `CALL 'LITERAL'` edges from
the main program through `source_search_dirs`. Production toolchains do not. A build
names the programs to compile, one per compile; the binder pulls statically called
program objects from libraries by name, and the runtime loads dynamically called ones
from load libraries — already compiled, never compiled at run time. So the core gets
a fixed list, and finding that list is a separate shell step.

## Design

### Core: `compile_cobol`

```python
def compile_cobol(
    source: bytes,
    *,
    parser: CobolParser,
    programs: Sequence[SourceFile] = (),
    copybook_dirs: Sequence[Path] = (),
    extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
    dialect_parsers: Sequence[DialectParser] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    ast_cache_dir: Path | None = None,
    tolerant: bool = False,
    lp: LP = LP.LP32,
) -> tuple[Frontend, LinkedProgram]
```

- Compiles the main program and every program in `programs`, and links them. It
  searches no directory.
- `source_search_dirs`, `extra_subprogram_sources` and `source_transform` are removed;
  `programs` replaces all three.
- A program that fails to lower is skipped with a warning, as today.
- Not pure: ProLeap is a JVM subprocess that reads copybooks itself, and the AST cache
  is on disk. What it gives up is discovery.
- The import graph stays a star (main depends on every other program); deriving it
  from recorded CALL targets belongs to red-dragon-ajps.

### `SourceFile`

`interpreter/project/source_file.py`: a frozen dataclass `SourceFile(path: Path,
source: bytes)`. The path becomes the module path, so it sets the module's label
prefix. Spec 3's tree-sitter core takes the same type.

### Shell: `discover_called_programs`

`interpreter/project/cobol_discovery.py`:

```python
def discover_called_programs(
    source: bytes,
    search_dirs: Sequence[Path],
    source_transform: Callable[[str], str] = _identity,
) -> tuple[SourceFile, ...]
```

Today's `_resolve_call_sources`, moved unchanged in behaviour: transitive
`CALL 'LITERAL'` edges, each target looked up by program name in the search
directories in order (first hit wins), `source_transform` applied to every program it
reads, dynamic `CALL identifier` not followed.

### `compile_program`

Signature unchanged, so cicada, jackal and squall do not change. It now:

1. rewrites the main program with every spec's prepass;
2. discovers called programs through the merged search directories, with the same
   rewrite as `source_transform`;
3. rewrites the merged `linked_subprogram_sources`, each as `SourceFile(Path(f"{name}.cbl"), …)`;
4. makes the strategies;
5. calls `compile_cobol` with the discovered and linked programs.

Discovery now happens before any strategy is made, so the ordering guarantee is whole
again: every prepass runs on every compiled program before any `make_strategy`. The
`CoprocessorSpec` and `compile_program` docstrings say so.

A linked subprogram whose name a discovered program also has: the linked one wins,
as `extra_subprogram_sources` wins today.

### `compile_directory`

Stops accepting COBOL: `_module_frontend`, `_collect_copybook_dirs` and the COBOL
entries in `_LANGUAGE_EXTENSIONS` and `_COPYBOOK_EXTENSIONS` go, and with them the
`Language.COBOL` test in `project/compiler.py`. A language with no registered
extensions raises `ValueError` instead of linking an empty program.

`CobolImportResolver` and COBOL import extraction stay; discovery uses them.

### COBOL CLI

`python -m interpreter MAIN.cbl [--search-dir DIR]... [--max-steps N] [--log-level L] [--verbose]`

- The file is the main program and the entry.
- Each `--search-dir`, in order, is searched for called programs and used as a
  copybook directory.
- It compiles through `compile_program` with no specs and runs from the linked
  program's entry label.
- Directory mode and `--entry` go. A directory argument is an error naming the file
  it expects.

## Tests

- **Unit:** `discover_called_programs` — transitive discovery, first directory wins,
  the transform applied to every program it reads, a dynamic CALL not followed.
  `compile_cobol`'s defaults test names `programs`. The coprocessor ordering test
  gains a discovered callee: every source rewrite, the callee's
  included, comes before every `make_strategy`.
- **Moved:** the `compile_directory(tmp_path, Language.COBOL)` tests in
  `test_cobol_programs.py`, `test_cobol_copybook_inlining.py`,
  `test_cobol_call_by_data_name.py`, `test_cobol_procedure_using.py` and the COBOL case
  in `test_all_languages_execution.py` call `compile_cobol` with the main program and
  an in-memory `programs` list, and `copybook_dirs=[tmp_path]` where they use
  copybooks. `run_cobol_programs` in `cobol_helpers.py` passes `programs`. Assertions
  do not change.
- **Moved:** `test_source_transform_applied_to_on_disk_callees_only` becomes a
  discovery test.
- **Deleted:** `test_collect_project_copybook_dirs`, with `_collect_copybook_dirs`.
- **New:** `compile_directory` raises for a language with no registered extensions;
  the CLI runs a main program whose callee and copybook are found through
  `--search-dir`, and rejects a directory argument.

## Living documentation

`README.md` ("Running COBOL"), `docs/linker-design.md` and
`docs/frontend-design/cobol.md` wherever they describe COBOL through
`compile_directory`, directory mode or `source_search_dirs` on `compile_cobol`. An
ADR (ADR-181) records the core/shell split and the production-toolchain reasoning.

## Done when

- `compile_cobol` has no `source_search_dirs`, `extra_subprogram_sources` or
  `source_transform` parameter, and nothing calls `compile_directory` with COBOL.
- `project/compiler.py` names no COBOL.
- red-dragon's gate is green; the forge, bumped to the result, is green under
  `make test-all`.
