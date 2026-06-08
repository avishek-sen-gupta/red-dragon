# BMS-Tools Pipeline Integration — Design

**Date:** 2026-06-08
**Status:** Approved (design); pending implementation plan
**Beads:** closes `red-dragon-zvta` (BMS loader cannot parse real BMS); supersedes the regex `_parse_bms_file`. Related: `red-dragon-pz9g.5` (BMS Screen Engine), `red-dragon-pz9g.10` (symbolic maps).

## Goal

Obtain **real** BMS map layouts through the full `bms-tools` pipeline instead of the
regex stub. **Non-negotiable invariant:** BMS symbolic map structures come from
`bms-tools` (`.bms HLASM → hlasm_export → bms_copybook_gen → symbolic copybook`),
not from a hand-written stub or an ad-hoc parser.

## Background — why this exists

`interpreter/cics/bms/loader.py::_parse_bms_file` is a minimal regex parser that
extracts **zero** maps from real BMS macro source (verified: `BmsLoader(maps_dir=
.../app/bms)` → `maps loaded: []`). It cannot handle col-72 continuation lines,
arbitrary parameter order, multi-map mapsets, or unlabeled fields, and its
`(row-1)*80+(col-1)` offset model does not match the symbolic-map layout the COBOL
program actually uses. Consequently every CICS test registers **hand-fabricated
stub maps** (`register_stub`) with invented offsets, masking that real maps don't
load.

The plan that built the BMS engine (`docs/superpowers/plans/2026-06-06-cics-E-bms.md`,
Task E1) specified `bms-tools` as the parser, with a fallback: "if not available,
use a minimal stub." The implementation shipped the **fallback** and never replaced
it. This design replaces it with the real pipeline.

## The key realization

`bms-tools` emits **symbolic copybooks** — the same artifact a program `COPY`s. Once
those copybooks are generated into a directory and that directory is on the COBOL
`copybook_dirs` list, the symbolic maps are included into programs **like any other
copybook**. The program's `DATA DIVISION` layout (`data_layout`) then holds the map
groups (`CACTVWAO`/`CACTVWAI`) and their fields with real offsets — for free, via the
existing COBOL layout engine. There is **no separate map-parsing or offset math** to
do, and **no map registry to maintain**.

## Architecture

A **stage-0 generation step**, then ordinary copybook inclusion.

```
[BMS_TOOLS_HOME set?]
   │ yes
   ▼
.bms sources ──hlasm_export (C++)──▶ JSON ──bms-copybook-gen (Py)──▶ <map>.cpy
                                                                        │
                                          symbolic-copybooks dir ◀──────┘
                                                                        │
   append to copybook_dirs ◀────────────────────────────────────────────┘
                                                                        │
   COBOL compile: programs COPY symbolic maps → data_layout has CACTVWAO/AI fields
                                                                        │
   SEND/RECEIVE MAP read/write those fields from the layout ◀───────────┘
```

### Access model — Option A (external, gated)

- `BMS_TOOLS_HOME` points at a **locally built** `~/code/bms-tools` checkout. The
  user builds the C++ `hlasm_export` binary once (per its own build instructions).
- red-dragon **never builds C++**. The heavy HLASM-LSP toolchain stays out of
  red-dragon's build/CI.
- Anything requiring the pipeline **skips when `BMS_TOOLS_HOME` is unset or the
  `hlasm_export` binary is absent** — mirroring the existing `CARDDEMO_HOME` /
  `JAR_AVAILABLE` gating in `tests/integration/cobol_helpers.py`.

### Stage-0 generation

At region/test setup (when gated on), red-dragon runs the bms-tools pipeline over a
`.bms` source directory and writes one symbolic copybook per map into a
**symbolic-copybooks output dir**. Invocation is by **subprocess**, matching
bms-tools' own documented usage:

```
hlasm_export <map>.bms | bms-copybook-gen > <out>/<map>.cpy
```

- `hlasm_export` is `$BMS_TOOLS_HOME/<path>/hlasm_export` (exact path captured during
  implementation from the built tree).
- `bms-copybook-gen` is invoked via its CLI (`$BMS_TOOLS_HOME/python/bms_copybook_gen`
  entry point) or `python -m bms_copybook_gen`; no Python import dependency is added
  to red-dragon (keeps the boundary a clean subprocess pipeline).
- The output dir is a fresh, generated directory (e.g. a temp dir or a region-scoped
  build dir) — **not committed**, regenerated each run, preserving the invariant that
  layouts always come from the pipeline.

### Wiring

The generated symbolic-copybooks dir is appended to the `copybook_dirs` passed to the
`ProLeapCobolParser` in the CICS compile path (`interpreter/cics/bootstrap.py`
`compile_cics_program` / `run_carddemo_region`, and the test harnesses). No change to
copybook resolution semantics — it is just one more directory.

### SEND / RECEIVE MAP rewrite

The builtins bridge the program's symbolic-map fields (in the WS region) and the
outside world (the `screen_queue` / `input_queue`). The field set is the children of
the symbolic group in the program's layout — no registry.

- **`SEND MAP('M') FROM(<map>O)`**: read each leaf field of the output group from the
  WS region and enqueue `{map:'M', fields:{<base>:<value>, ...}}` on `screen_queue`.
- **`RECEIVE MAP('M') INTO(<map>I)`**: for each field value taken from `input_queue`,
  write it into the matching `<base>I` leaf in the WS region and set `<base>L` to the
  input length. EIBAID write-back is unchanged.

The leaf set + offsets/lengths come from the symbolic group in the program's layout.
**Implementation note (not a user-facing decision):** the lowering layer
(`strategy.py` via `EmitContext`) already has the structured layout, so the
group's leaf descriptors (name, offset, length) are resolved at lower-time and passed
into the builtin call as constant arguments; the builtin then slices the WS region by
those descriptors. (`vm.data_layout` is a flattened dict that loses group membership,
which is why resolution happens where the structured layout is available.) This keeps
the builtins pure functions of their arguments and adds no new VM state. The field set
is static — correct, because the copybook is static.

### Deletion

`interpreter/cics/bms/loader.py` is removed in full: `BmsLoader`, `BmsMap`,
`BmsField`, `_parse_bms_file`, `symbolic_names`, `extract_fields`, `write_fields`.
The `SEND`/`RECEIVE MAP` builtin factories drop their `loader` parameter. All
`register_stub` call sites are removed (see Testing).

## Data flow (runtime, one turn)

1. (Setup, once) bms-tools generates symbolic copybooks → out dir on `copybook_dirs`.
2. Program compiled; `data_layout` contains `CACTVWAO` / `CACTVWAI` groups + fields.
3. Program `MOVE`s values into `<base>O` fields, then `EXEC CICS SEND MAP FROM(...O)`.
4. `SEND MAP` reads those `<base>O` fields from WS → `screen_queue`.
5. `EXEC CICS RECEIVE MAP INTO(...I)` ← `input_queue` values written into `<base>I`
   fields (+ `<base>L`).

## Error handling

- `BMS_TOOLS_HOME` unset / `hlasm_export` missing → pipeline-dependent tests **skip**
  (gated). No fallback parser, no stub — the invariant forbids a silent alternative.
- A `.bms` that `hlasm_export` cannot parse → the subprocess fails; surface the
  stderr/diagnostics and fail loudly (do not silently produce an empty copybook).
- A `SEND/RECEIVE MAP` for a group not present in `data_layout` → loud error
  (the program's `COPY` or the generation step is wrong), not a silent empty screen.

## Testing strategy

- **Gated integration / durable tests:** the real CardDemo test
  (`test_carddemo_signon_real.py`) and CICS region tests stop calling `register_stub`.
  They run stage-0 generation over `$CARDDEMO_HOME/bms` (gated on both `BMS_TOOLS_HOME`
  and `CARDDEMO_HOME`) and assert on `screen_queue` field values produced from the real
  generated copybooks. This is the end-to-end proof that real maps load.
- **Pure unit tests** that need a fixed field set use a **small real symbolic copybook
  fixture** (committed `.cpy`) compiled through the normal layout path — never a stub
  registry. `SEND/RECEIVE MAP` unit tests assert read-from-WS / write-to-WS behavior
  against that fixture's layout.
- **Generation unit test (gated on `BMS_TOOLS_HOME`):** run the pipeline over one real
  `.bms` and assert the generated copybook contains the expected `<map>O`/`<map>I`
  groups and fields — proves the subprocess wiring.
- Full suite stays green with `BMS_TOOLS_HOME` unset (those tests skip).

## Migration / sequencing notes

- Removing `loader.py` and the `loader` builtin params touches `strategy.py`,
  `builtins/screen.py`, and several CICS tests — done in one cohesive change so the
  tree never has a half-deleted loader.
- The durable test currently passes with stubs; after migration it requires
  `BMS_TOOLS_HOME` (and the built binary) to run, otherwise skips. Acceptable — it was
  already gated on `CARDDEMO_HOME`.

## Out of scope

- `red-dragon-6ddr` (stringly-typed subscript/ref-mod field references) — separate P0.
- Real 3270 screen geometry / attribute rendering (POS/ATTRB). Only field **values**
  by name are needed for the emulation + tests; screen coordinates are not consumed.
- Generating symbolic copybooks for the program's own `COPY` resolution beyond the BMS
  maps — the maps are the only thing bms-tools supplies; other copybooks resolve as
  today.
```
