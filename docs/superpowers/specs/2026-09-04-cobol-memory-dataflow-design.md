# Memory-Level Dataflow Analysis for COBOL

**Date:** 2026-09-04
**Status:** Implemented. Shipped with one blocking limitation — file-region aliasing (red-dragon-7211) makes the graph unusable on file-heavy programs; see `2026-09-04-cobol-memory-dataflow-evaluation.md` §5c.
**Branch:** `worktree-cobol-memory-dataflow`

---

## 1. Problem

`interpreter/dataflow.py` computes reaching definitions, def-use chains, and a
variable dependency graph over the IR CFG. It decides whether two accesses touch
the same storage by **name equality** — `Definition.__eq__` compares
`(variable, block_label, instruction_index)`, where `variable` is a `VarName` or
a `Register`.

That assumption — *distinct names denote disjoint storage* — holds for all 15
existing frontends. It does not hold for COBOL, and the consequence is that the
analysis produces nothing useful for COBOL programs:

- COBOL fields are not variables. `lower_data_division.py:30` emits one
  `AllocRegion` per non-empty DATA DIVISION section, and every field is a byte
  slice of that buffer. Field access lowers to
  `LoadRegion(region_reg, offset_reg, length)` /
  `WriteRegion(region_reg, offset_reg, length, value_reg)`.
- `WriteRegion.writes()` returns `None` (`interpreter/instructions.py:1065`), so
  **every COBOL field assignment currently generates no `Definition` at all**.

Name equality is not merely imprecise for COBOL, it is **unsound**: it would
report `WS-A1` and its parent group `WS-A` as unrelated when they physically
share bytes. The same failure class applies to C `union`s and Fortran
`EQUIVALENCE`.

## 2. Goal and scope

Produce a **field-level dependency graph** for a COBOL program: for each declared
field, which other fields' values flowed into it.

| Dimension | Decision |
|---|---|
| Purpose | Comprehension / impact analysis. Over-approximate: a spurious edge is noise, a missing edge is a bug. |
| Dependence kind | **Data only.** No control dependence. |
| Program scope | **Single program.** `CALL` callees opaque. |
| `PERFORM` | **Context-insensitive.** Accepts unrealizable-path imprecision; measured in Stage 6. |
| Subscripts | Exact when the subscript is a literal, clamped to the enclosing `OCCURS` extent when computed. |
| Deliverable | Python API + JSON serializer for a graph viz. |

**Out of scope, but must not be precluded:** `CALL`-boundary aliasing;
dataset-mediated cross-program flow; control dependence; element-level subscript
precision; retrofitting `Definition`/`Use` onto instruction ids.

## 3. Memory model

### 3.1 Regions

`MaterialisedSectionedLayout` (`interpreter/cobol/sectioned_layout.py:32`) holds
up to six regions, each allocated by a single `AllocRegion` and sized
`layout.total_bytes` — and only when non-empty (`lower_data_division.py:61–81`):

| Region | Contents | COBOL section? |
|---|---|---|
| `working_storage` | all `01`/`77` in WORKING-STORAGE | yes |
| `linkage` | all `01` in LINKAGE | yes |
| `local_storage` | all `01` in LOCAL-STORAGE | yes |
| `file` | FD record areas | yes |
| `special_registers` | `RETURN-CODE` etc. | no — RedDragon synthetic |
| `indexes` | `INDEXED BY` items | no — RedDragon synthetic (`data_layout.py:670`) |

`RegionId` is therefore a **closed enum**, not an open universe of heap objects.

### 3.2 Verified layout behaviour

Probe program with three `01` levels in WORKING-STORAGE, run through
`CobolFrontend.data_layout`:

```
WS-A   offset= 0  len=15       01  WS-A.
WS-A1  offset= 0  len=10           05  WS-A1 PIC X(10).
WS-A2  offset=10  len= 5           05  WS-A2 PIC 9(5).
WS-B   offset=15  len= 4       01  WS-B.
WS-B1  offset=15  len= 4           05  WS-B1 PIC X(4).
WS-C   offset=19  len= 3       01  WS-C PIC X(3).
```

Emitted IR: `CONST [22]; ALLOC_REGION ['%1']` — a single 22-byte buffer for all
of WORKING-STORAGE, plus a separate 2-byte `special_registers` buffer.

Two properties the design depends on, both confirmed:

- **Containment is real.** Children sit inside their group's range, so a group
  write covers its children by range subsumption — no separate group/child rule.
- **Separation is real.** Distinct `01` records occupy disjoint ranges, so
  unrelated records cannot alias. Free, from the bridge-supplied offsets.

### 3.3 Aliasing is byte-range overlap

| COBOL construct | Captured by overlap because |
|---|---|
| group ↔ elementary | group extent contains child extent |
| `REDEFINES` | same offset, overlapping extents |
| `RENAMES` (`66`) | `renames_from`/`renames_thru` give the span |
| `OCCURS` | elements are disjoint sub-extents of the table extent |
| reference modification | sub-extent of the field extent |
| distinct `01` records | disjoint extents ⇒ correctly *not* aliased |

Cross-region overlap is always false. That is a hard non-aliasing boundary in
this scope; scope (2) later adds `CALL USING` as the one deliberate cross-region
binding.

### 3.4 Abstract state

Byte *values* are abstracted away; what is retained is, per byte range, the set
of write sites that produced it:

```
σ : Extent → set[Definition]
```

Worked example on the probe layout:

```cobol
MOVE 'HI'   TO WS-A1.    *> d1   ws[0..9]   ↦ {d1}
MOVE WS-A1  TO WS-B1.    *> d2   reads ws[0..9] → {d1};  ws[15..18] ↦ {d2}
MOVE ZERO   TO WS-A2.    *> d3   ws[10..14] ↦ {d3}
MOVE SPACES TO WS-A.     *> d4   covers ws[0..14] ⇒ kills d1, d3
```

`d4` subsumes both children, so it kills them — no rule needed beyond
subsumption. Conversely `MOVE 7 TO WS-QTY(I)` with computed `I` clamps to the
table extent, which *may* overlap but does not *contain* any element, so it
**adds** without killing: `↦ {d1, d5}`, "could be either". The over-approximation
falls out of the may/must distinction rather than a special case.

### 3.5 The ⊤ cliff, and why it does not occur

If an access cannot be bounded, it must be assumed to write the whole region;
every field then depends on everything, and after transitive closure the report
says "changing anything affects everything". One unbounded write poisons the
program.

This is avoided **structurally, not numerically**. Every access already flows
through `MaterialisedSectionedLayout.resolve()` and
`EmitContext.resolve_field_ref()`, which know the field's identity and its
enclosing layout. Extents are therefore *emitted* from known structure rather
than *recovered* by abstract-interpreting `BINOP` arithmetic on offset
registers. Worst case is clamping to a declared field's own extent. There is no
path to a region-wide write, and consequently **no interval domain, no widening
operator, no convergence tuning**.

## 4. Architecture

The frontend emits memory effects; a generic engine runs the fixpoint.

`emit_context.py` is the only place holding both the source construct
(`fl: FieldLayout`, structured subscript `ExprNode`s, `source_location`) *and*
the byte layout (offset, length, region). Neither the ASG nor the IR has both.
Rejected alternatives:

- **Source-level analyzer over the ASG.** Would need a second, independent
  encoding of ~40 COBOL verbs' read/write semantics, plus its own CFG for
  `GO TO` / `PERFORM THRU` / fall-through. The existing `lower_*.py` encoding is
  validated by ~14k tests and the NIST-85 corpus; a parallel one would be
  validated by nothing and would silently drift — the same divergence pattern as
  `red-dragon-ilb6`, `r9s9`, `qhtv`, `bqds`.
- **Analysis on raw IR.** Inherits the ⊤ cliff: recovering field identity from
  `BINOP` chains requires an interval domain with widening, to reconstruct
  information that was known and discarded during lowering.

### 4.1 Extent computation

`ResolvedFieldRef` (`field_resolution.py:13`) is the choke point — built in
exactly two places (`resolve_field_ref`, `resolve_field_ref_from`). It gains a
statically-known extent:

```python
@dataclass(frozen=True)
class FieldExtent:
    region: RegionId
    start: int
    length: int
    precision: Precision      # EXACT | CLAMPED
    field_name: str           # qualified, for reporting
```

`resolve_field_ref` already receives `subscripts: tuple[ExprNode, ...]` as
structured nodes (`red-dragon-l445`, `6ddr`), so it can see directly whether a
subscript is a literal (`EXACT`) or computed (`CLAMPED`, via the existing
`subscript_stride()` at `sectioned_layout.py:95`). Multi-dimensional stride
accumulation (`red-dragon-1wy3`) is reused as-is.

`resolve()` additionally returns the `RegionId` it matched, which it currently
computes and discards.

### 4.2 The recorder

```python
class MemoryEffectRecorder(Protocol):
    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None: ...

class NullRecorder:           # default; analysis off, zero cost
    def record(self, inst_id: InstructionId, effect: MemoryEffect) -> None: pass
```

`MemoryEffect` is `(kind: READ | WRITE, extent: FieldExtent, source_location)`.
The sidecar is `dict[InstructionId, MemoryEffect]`, keyed by the universal
instruction id (§4.3) — no separate id space.

### 4.3 Instruction identity

`Definition`/`Use` currently hand-roll `__hash__`/`__eq__` over
`(variable, block_label, instruction_index)` *because instructions have no
identity* — frozen dataclasses with value equality cannot serve as identity
keys. That positional coordinate is stable only while nothing re-blocks or
reorders the stream.

`InstructionBase` gains:

```python
id: InstructionId = field(default=NO_INSTRUCTION_ID, compare=False)
```

`compare=False` preserves value equality semantics; sidecars key on `inst.id`,
never on `inst`. Precedent: `source_location` is already universal base-class
metadata (`instructions.py:112`). Risk is low — no test in `tests/` compares
whole instruction objects by value.

**Mint strategy: emit-time, per frontend.** A counter in the emit context.
COBOL adopts now; the other 15 carry `NO_INSTRUCTION_ID` until they need it.
Rejected: a post-lowering numbering pass, because the recorder runs *during*
emission, so its sidecar would have to be keyed by emission order and zipped
afterwards — an unenforced assumption that emission order equals final order.

`map_registers()` must **preserve** the id (same instruction, rewritten). A pass
that splits or synthesizes instructions must mint fresh ids.

### 4.4 Completeness invariant

The silent failure mode is a lowering path that emits an access without
declaring an effect — exactly the shape of today's `WriteRegion.writes() → None`
bug.

Verified: only three region opcodes exist (`AllocRegion`, `LoadRegion`,
`WriteRegion`), constructed in only two files — 7 sites in `emit_context.py`,
4 in `lower_call.py` (the `CALL USING` params/results marshalling; in this scope
they record effects but get no cross-region binding).

All of them funnel through two private `EmitContext` helpers,
`_emit_load_region` / `_emit_write_region`, which emit the instruction **and**
record the effect in one step. The invariant is then mechanically checkable:
*no `LoadRegion` or `WriteRegion` is constructed outside those two helpers*,
asserted by an ast-grep test. A lowering site cannot forget an effect because it
has no other way to emit the access.

### 4.5 Engine parameterization

Reaching definitions is already an abstract interpretation: domain = powerset of
definition sites, join = union, transfer = `gen ∪ (in − kill)`. The current
analysis and the memory-level analysis share the CFG, the fact lattice, the
transfer function, and the fixpoint. **Only the alias relation differs**, and it
is currently hard-coded into `Definition.__eq__`.

```python
class AbstractLocation(Protocol):
    def may_alias(self, other: AbstractLocation) -> bool: ...
    def must_cover(self, other: AbstractLocation) -> bool: ...
```

- `Register` — both are name equality. Sound: IR temporaries are genuinely disjoint.
- `FieldExtent` — `may_alias` is range intersection within one region;
  `must_cover` is range subsumption; cross-region is always `False`.

Both coexist in one analysis, which is required anyway: COBOL IR mixes them,
since `%4 = LOAD_REGION ...` defines a *register* from an *extent*.

Three changes in `dataflow.py`, and only these three:

1. **GEN** — currently `dict[var] → Definition` ("last def of each variable").
   Becomes a forward simulation within the block: a new definition removes prior
   definitions it `must_cover` and coexists with ones it merely `may_alias`.
2. **KILL** — becomes all definitions elsewhere that this block's definitions
   `must_cover`. **Only `must` kills**; a may-write cannot kill.
3. **Def-use matching** — `d.variable == var` becomes
   `d.location.may_alias(use.location)`. Already a linear scan, so no complexity
   regression, though fact sets grow.

`_trace_to_named_vars` extends to terminate at a `FieldExtent` as well as a
`VarName`, bridging register chains back to memory.

**Termination.** Every extent derives from a declared `FieldLayout` or a clamped
`OCCURS` extent, so the set of abstract locations is finite and known before the
fixpoint starts. Powerset lattice + monotone transfer + union join ⇒
convergence without widening. `DATAFLOW_MAX_ITERATIONS` stays as a backstop.

### 4.6 Output

`MemoryDataflowResult` carries the extent-level graph plus a field-level
projection (each extent mapped to the declared fields it overlaps; qualified
names as node ids), and `to_json()` producing:

```json
{"nodes": [...], "edges": [{"from": ..., "to": ..., "via": ["<source_location>"]}]}
```

Edge direction follows **data flow**: `{"from": "WS-PRICE", "to": "WS-TOTAL"}`
means a value flowed from `WS-PRICE` into `WS-TOTAL`, i.e. `WS-TOTAL` depends on
`WS-PRICE`. `via` lists the source locations of the statements carrying the
flow, so a reader can jump to the COBOL lines responsible for an edge. Note this
is the reverse of `DataflowResult.dependency_graph`, which maps
*var → vars it depends on*; the JSON is edge-oriented for viz consumption while
the in-memory result keeps the existing dependency-map orientation.

> **Known limitation — `via` renders `<unknown>` today.** The COBOL frontend
> never populates `InstructionBase.source_location`: measured 0 of 151
> instructions on a representative program. The `via` mechanism is plumbed
> correctly end to end and will populate itself the moment the lowering stamps
> locations, but until then every entry is `<unknown>`. This is pre-existing and
> COBOL-wide, not specific to this analysis — filed as **red-dragon-bmx3**.
> A consumer must not read `<unknown>` as "no statement produced this edge";
> that meaning is reserved for the empty list on a transitive edge.

No TUI panel, MCP tool, or report generator in this spec.

## 5. Testing

- **Alias algebra (unit).** `may_alias` / `must_cover` on `FieldExtent`,
  including the laws: `must_cover ⇒ may_alias`; `may_alias` symmetric;
  cross-region always false.
- **Layout → extent (unit).** Per construct: group covers children, `REDEFINES`
  overlaps, `RENAMES` spans, `OCCURS` exact under a literal subscript and clamped
  under a computed one, ref-mod sub-extent.
- **Neighbour constraint.** Every layout fixture must have neighbouring fields on
  both sides of the field under test, and assert their extents too. Single-field
  fixtures cannot catch width errors — that is how `red-dragon-ilb6` and
  `red-dragon-r9s9` shipped. An extent one byte too long is invisible in
  isolation and immediately visible against a neighbour.
- **Regression net.** Stage 1 is behaviour-preserving; the existing
  `tests/unit/test_dataflow.py` and the full suite must pass **unchanged, with no
  test edits**. A test needing modification means the refactor was not
  behaviour-preserving — stop.
- **Integration.** Real COBOL source through parse → lower → CFG → analyze,
  asserting field-level edges. This deliberately deviates from the project's
  usual "integration exercises the VM via `run()`" rule, because the analysis is
  a static pass that never executes. Golden cases: group write kills children;
  `REDEFINES` alias edge; computed subscript adds without killing; and a
  **characterization test for the `PERFORM` context merge**, asserting the known
  spurious edge explicitly rather than leaving it undocumented.
- **Completeness invariant.** ast-grep test per §4.4.
- **Evaluation harness.** Run on a real CardDemo program; record graph density
  (edges per node, fraction of field pairs transitively connected). A recorded
  baseline, not a pass/fail gate.

Implementation follows the TDD skill: failing test first, at every stage.

## 6. Staging

| Stage | Work | Risk |
|---|---|---|
| 0 | Universal `InstructionId` on `InstructionBase` (`compare=False`); emit-time mint in COBOL `EmitContext` | Low |
| 1 | `AbstractLocation` protocol + `Register` impl; refactor `dataflow.py` onto `may_alias`/`must_cover`. **Zero behaviour change.** | **Highest blast radius** — shared by 15 frontends |
| 2 | `RegionId`, `FieldExtent`, `ResolvedFieldRef` extension, `resolve()` returns region id | Mechanical but broad |
| 3 | Recorder protocol, two funnel helpers, completeness invariant | Silent-omission risk |
| 4 | Engine consumes sidecar; extent fixpoint; field-level projection | Core correctness |
| 5 | JSON serializer | Low |
| 6 | Evaluate on a real program; decide whether context-insensitivity holds | Decision point, not code |

Stage 1 lands **first and alone**: it is the change that can break the other 15
frontends, it is behaviour-preserving, and in isolation the existing suite is an
unambiguous verdict. All COBOL-specific work lands after that gate.

## 7. Open risks

1. **Stage 1 subtly non-behaviour-preserving.** `Definition.__hash__` is used in
   set operations; a location-based hash must stay consistent with the new
   equality. Hash/equality consistency needs direct tests, not only end-to-end
   ones.
2. **`must_cover` wrong in the permissive direction silently drops
   dependencies** — the one failure mode this design exists to prevent. Needs
   direct unit tests of the predicate itself.
3. **Reference modification with computed start *and* length** is unverified;
   probe before planning Stage 2 in detail.
4. **Context-insensitive `PERFORM` may be empirically unusable.** COBOL's shared
   utility paragraphs (`9000-WRITE-RECORD` performed from dozens of sites) plus
   flat WORKING-STORAGE scope could reconnect the graph via a second route.
   Measured in Stage 6; upgrade path is paragraph summaries, which
   `interpreter/interprocedural/summaries.py` already shapes and which scope (2)
   would need anyway.

## 8. Follow-on work

- Retrofit `Definition`/`Use` onto instruction ids (deferred by decision).
- Scope (2): `CALL USING` region-to-region binding (callee `linkage` extent ↔
  caller `working_storage` extent). Note `linkage` is sized by the caller, not
  by `total_bytes` (`data_layout.py:670`).
- Scope (3): dataset-mediated cross-program flow via FD/VSAM record layouts.
- Control dependence as a separate edge kind.
- TUI `DataflowGraphPanel` wiring; MCP query tool.
