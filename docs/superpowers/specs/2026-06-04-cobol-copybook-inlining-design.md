# COBOL COPY Copybook Inlining — Design

**Issue:** red-dragon-9w64 (P0 blocker)
**Date:** 2026-06-04
**Status:** Approved

## Problem

Copybook (`COPY`) inlining does not work in the current pipeline, and an
unresolvable `COPY` is a **hard parse failure**, not a graceful skip.

Root cause (empirically confirmed):

1. The pipeline always pipes source via **stdin**:
   `ProLeapCobolParser.parse(source: bytes)` → `RealSubprocessRunner` →
   `java -jar bridge` with source on stdin. The project compiler does
   `file_path.read_bytes()` then the same stdin path.
2. The bridge (`Main.java` `resolveInputFile`) writes stdin to a throwaway
   temp file via `Files.createTempFile` → the **system temp dir**
   (`java.io.tmpdir`).
3. ProLeap's `CobolParserRunnerImpl.createDefaultParams` sets
   `copyBookDirectories = [cobolFile.getParentFile()]` = the system temp dir,
   which never contains the program's copybooks.
4. Result:
   `CobolPreprocessorException: Could not find copy book MYBOOK in directory of
   COBOL input file or copy books param object.` → the entire parse fails.

`extract_imports` (the `MULTI_FILE_IMPORTS` feature) only **detects** `COPY`
references via regex for the dependency graph; it never inlines. No
`setCopyBookDirectories` plumbing is exposed from Python.

ProLeap itself supports `COPY` expansion correctly — the gap is purely in **how
the bridge is invoked**.

### Impact

Blocks parsing of essentially all real-world COBOL with copybooks — every
CardDemo program (`COCOM01Y` commarea, BMS symbolic maps, `DFHAID`,
`DFHBMSCA`, record layouts) and most batch programs. The CICS epic
(red-dragon-pz9g) implicitly assumed working `COPY` resolution.

## Approach

Thread an explicit copybook **search path** (a list of directories) from the
Python frontend to the bridge, where it configures ProLeap's resolver via
`CobolParserParams.setCopyBookDirectories(...)`. Source continues to flow via
**stdin** — copybook resolution is decoupled from source location, so no
temp-file relocation is needed.

ProLeap's `CobolParserParams` provides exactly the needed API:
`setCopyBookDirectories(List<File>)`, `setCopyBookExtensions(List<String>)`,
`setCopyBookFiles(List<File>)`, `setIgnoreSyntaxErrors(boolean)`.

### Why explicit dirs (not source-file-sibling or explicit file list)

- **vs source-file-sibling resolution:** only works when copybooks are
  siblings of the source; breaks for stdin and for CardDemo's split
  `cpy` / `cpy-bms` / bundled-system-copybook directories.
- **vs explicit file list (resolve names→paths in Python):** duplicates
  ProLeap's own name→file matching and forces us to own extension/case logic.
- **Explicit dirs** support multiple roots, work with stdin, and reuse
  ProLeap's resolver. Chosen.

## Data Flow

```
run() / compile_directory()
   → copybook_dirs: list[Path]                              (NEW param)
   → ProLeapCobolParser.parse(source, copybook_dirs)
   → bridge: java -jar bridge -copybook-dir D1 -copybook-dir D2 …
             (source on stdin, unchanged)
   → Main.java builds CobolParserParams
              .setCopyBookDirectories([D1, D2, …])
              .setCopyBookExtensions([…])
   → ProLeap preprocessor expands COPY against those dirs   (one parse pass)
```

## Component Changes

### 1. Bridge `Main.java`

- Accept repeatable `-copybook-dir <dir>` arguments (alongside the existing
  `-format`).
- Build a `CobolParserParams`:
  - `setCopyBookDirectories(dirs)` from the passed `-copybook-dir` values.
  - `setCopyBookExtensions([...])` — standard set (see Extensions below).
  - `setFormat(format)` as today.
- Switch from the 2-arg `analyzeFile(file, format)` to the params overload
  `analyzeFile(file, params)`.
- Source acquisition (stdin → temp file) is unchanged.

### 2. Python `cobol_parser.py`

- `CobolParser` ABC: `parse(source: bytes)` →
  `parse(source: bytes, copybook_dirs: list[Path] = [])`.
- `ProLeapCobolParser.parse`: append one `-copybook-dir <dir>` arg per entry in
  `copybook_dirs` to the java command.

### 3. `run.py` / `compiler.py`

- `run()` gains an optional `copybook_dirs` parameter, default empty.
  **Default-empty means no behavior change for COPY-free programs** — which is
  every existing single-file test.
- `compile_directory()` defaults `copybook_dirs` to **all directories under the
  project root, recursively collected**, so `app/cpy`, `app/cpy-bms`, etc. are
  covered with zero configuration. An explicit argument overrides the default.

## Extensions & Case

`setCopyBookExtensions(["", "cpy", "CPY", "cob", "cbl", "copy", "COPY"])` —
covers CardDemo's `.cpy` / `.CPY` and extensionless copybooks.

Note: macOS APFS is case-insensitive by default, so `.cpy` / `.CPY` resolve
interchangeably on a local dev machine; the explicit extension list keeps
resolution correct on case-sensitive hosts and CI too.

## Error Handling

A missing copybook stays **fail-fast**, but the raw Java
`CobolPreprocessorException` is caught at the subprocess boundary and re-raised
as the existing `CobolParseError` carrying:

- the **copybook name** that could not be found, and
- the **list of directories searched**.

No silent wrong parse; no raw Java stack trace leaking to the caller.

## Testing

- **Unit:**
  - `parse()` emits the correct `-copybook-dir` args for a given
    `copybook_dirs` list.
  - `compile_directory` collects the project-root tree into `copybook_dirs`.
- **Integration (required):**
  - A program that `COPY`s a co-located copybook parses; the copybook's data
    items appear in the ASG; and a field from the copybook is **used in
    PROCEDURE DIVISION and executed** end-to-end via `run()`.
  - Multi-copybook resolution.
  - `COPY … OF library` form.
  - A genuinely missing copybook → clean `CobolParseError` naming the copybook
    and the searched dirs (not a raw Java trace).
- **Regression:** existing stdin-based, COPY-free tests remain green
  (default-empty `copybook_dirs`).

## Scope Boundary

This issue covers **only** the resolution mechanism. Shipping the actual system
copybooks (`DFHAID`, `DFHBMSCA`) is red-dragon-pz9g.1 (the CICS EIB child) —
content that rides on the path this enables.

## Acceptance Criteria

1. A program with `COPY BOOK` referencing a co-located copybook parses
   successfully and the copybook's data items appear in the ASG.
2. Multi-copybook and `COPY … OF library` forms resolve.
3. A genuinely missing copybook produces a clear, surfaced error (not a silent
   wrong result), naming the copybook and the dirs searched.
4. The copybook search path is configurable from the Python frontend.
5. Unit + integration tests cover `COPY` inlining end-to-end (data item from a
   copybook used in PROCEDURE DIVISION and executed).
6. Existing stdin-based callers still work.
