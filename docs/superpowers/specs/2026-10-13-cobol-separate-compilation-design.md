# COBOL separate compilation: parse, lower and link chained through files — design

Date: 2026-10-13. Issue: red-dragon-ajps. Status: approved in brainstorm.

## The idea

Each COBOL compile stage reads files and writes files: parse writes an AST file
per program, lower writes a unit file per program, link writes a linked-program
file, and the run reads the linked file. `compile_cobol` runs the three stages in
order and hands over nothing but paths. A program is lowered once and its unit
is linked into many run units, across processes.

## Decisions (user, 2026-10-13)

- Purpose: compile once, link many; reuse across processes.
- No cache invalidation: a stage skips a program whose output file exists, and a
  caller that needs a rebuild deletes the work directory. Deciding whether an
  existing file is still good (copybook contents, lowering version, truncated
  files) is later work.
- Stages are chained only through files, inside one `compile_cobol` call as well.
- The unit format is typed JSON covering every instruction class.
- The serialiser uses one codec per field type, driven by the instruction
  dataclasses' own annotations; there are no mirror models.
- File names carry a digest of the source bytes and the lowering settings.
- The linked program is persisted; its CFG and registry are rebuilt on load.

## Prerequisite (done)

squall's EXEC SQL IR is self-contained (forge c3e56a9..5306143): no lowering
state is needed at run time. CICS IR already carried only primitive values.

## Design

### 1. File names

Every per-program file is `<stem>-<digest>.<kind>.json` in a work directory,
where `stem` is the source file's stem and `digest` covers the source bytes and
the lowering settings: addressing mode, extension strategy names, dialect parser
names, tolerant mode and copybook directories. One naming function computes
every name, so stages agree without a manifest, and a later process holding the
sources and settings can compute where the files are.

The linked file is `<main stem>-<digest>.linked.json`, where the digest covers
the unit files it is built from; `link_stage` returns its path.

Extension strategies gain a stable `name` (`"cics"`, `"sql"`) on the
`RedDragonExtensionLoweringStrategy` protocol, so the digest never depends on a
class's name.

### 2. The unit file

A `ModuleUnit` written as typed JSON with a format version. It gains two
language-neutral fields:

- `entry_label: CodeLabel = NO_LABEL` — the unit's un-namespaced entry function
  (`func_<pid>_0` for COBOL). Link namespaces the main unit's and sets
  `LinkedProgram.entry_func_label`, replacing the read of the main frontend's
  `program_id`.
- `data_layout` — the program's own layout. Link puts the main unit's on
  `LinkedProgram`, as today; callee layouts stay out of scope.

`type_env_builder` is not stored: it is always empty for COBOL.

### 3. The codec

`interpreter/project/unit_codec.py`, language-neutral:

- An instruction is `{"op": <class name>, <field>: <encoded value>, …}`. Encoding
  walks the dataclass's fields; decoding looks the class up by `op` and
  constructs it, so the result is the real instruction type.
- One codec per field type: `Register`, `VarName`, `FieldName`, `FuncName`,
  `ContinuationName`, `CodeLabel` and their null objects, `SourceLocation`,
  enums, tuples, `SpreadArguments`, `PathName`, every `TypeExpr` variant, and a
  tagged union for `Const.value` (int, float, str, bool, none, Decimal, bytes,
  lists of those).
- The tables a unit and a linked program carry: `ExportTable` (with `FuncRef`,
  `ClassRef`), `ImportRef`, `SymbolTable` (`ClassInfo`, `FieldInfo`), the data
  layout.
- An unknown `op`, a field type with no codec, or a format version it does not
  read raises `UnitFormatError` naming the file.

`write_unit` / `read_unit` and `write_linked` / `read_linked` are the file
boundary. `read_linked` rebuilds `merged_cfg` with `build_cfg(merged_ir)` and
`merged_registry` with `build_registry(...)`: both are derived from the merged
IR, and execution uses only the CFG's label lookup and program-order fall-through
(red-dragon-dp2o).

### 4. The stages

In `interpreter/project/cobol_compile.py`:

- `parse_stage(programs, parser, settings, work_dir) -> Mapping[Path, Path]` —
  source path to AST file. Programs whose AST file exists are skipped; the rest
  are parsed in parallel. Replaces `parallel_parse_to_cache`, which re-parsed
  everything into files named by a digest of the path.
- `lower_stage(program, ast_file, settings, strategies) -> Path` — reads the AST
  file and writes the unit file beside it, unless that exists. Its body is
  today's `compile_cobol_module` plus `entry_label` and `data_layout`.
- `link_stage(main_unit, units, work_dir) -> Path` — reads unit files only;
  builds the star import graph from the main unit, prepends the COBOL run-unit
  allocation, calls `link_modules`, sets `entry_func_label`, and writes the
  linked file, unless it exists.
- `compile_cobol(...)` runs parse, lower and link, then `read_linked`, and
  returns the `LinkedProgram`. `ast_cache_dir` becomes `work_dir` (a new temp
  directory when omitted).

### 5. Callers

`compile_cobol` and `compile_program` return the `LinkedProgram` alone; no
frontend survives lowering. Callers change mechanically: red-dragon's
`__main__`, `run()`, `coprocessor_compile` and tests; the forge's cicada
bootstrap and region, jackal's program compiler, squall's test helpers and the
root tests. `ast_paths` travels in the linked file, so jackal's AST re-read is
unchanged. Persistent work directories for cicada's region and jackal are forge
work that follows.

## Errors

- A program that fails to parse aborts the compile with `AstParseError`, as now.
- A callee that fails to lower is skipped with a warning and has no unit file;
  the main program's failure raises.
- A file that does not decode raises `UnitFormatError` naming it.

## Tests

- Round trip: `decode(encode(x)) == x` for every instruction class and every
  `TypeExpr` variant; a `ModuleUnit`; a linked file whose rebuilt CFG equals
  `build_cfg(merged_ir)`.
- Stages: a second compile in the same work directory calls neither the parser
  (an injected counting fake) nor lowering; changed settings produce different
  file names; a callee that fails to lower is skipped.
- Cross-process: compile in one process, run the linked file in a fresh one.
- Existing suites unchanged: red-dragon's full suite, forge `make test-all`,
  CardDemo over c3270.

## Out of scope

- Deciding whether an existing file is still current (copybooks read, lowering
  version, truncated files).
- Checking that linked units were lowered with the same settings: through
  `compile_cobol` they always are.
- Callee data layouts on `LinkedProgram`.
- The flat program counter (red-dragon-dp2o).
- Persistent work directories in the forge.
