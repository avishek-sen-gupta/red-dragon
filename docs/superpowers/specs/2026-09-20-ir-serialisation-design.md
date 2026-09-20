# Serialising lowered programs to IR files — preliminary design

**Status:** preliminary. Analysis and options only — **not approved, not scheduled, nothing
is being built from this.** Bead: `red-dragon-ve36`.

**Goal:** stop re-lowering unchanged source on every run. Compile once to a durable
artefact and thereafter load it, the way z/OS compiles to a load module and then only
loads it.

## Why now

A CardDemo region of 19 programs takes ~60s to build, on every test run of
red-dragon-forge's Db2 tier. Cobble re-parses whole corpora repeatedly. Nothing about
the source changed between runs.

## What the analysis found

Three findings, each of which changes the shape of the work. All were measured or read
out of the code, not assumed.

### 1. There is no compile reuse today. `ast_cache_dir` is not a cache.

`compile_cobol` is two-phase — parse to JSON, then load and lower — and takes an
`ast_cache_dir`, which reads like a reuse cache. It is not one. `AstStore.parse_all`'s
own docstring says it parses every source *"replacing whatever was cached before"*.

Measured on `CBACT01C.cbl` with a warm `ast_cache_dir`:

    cold (parse + lower) = 1.37s
    warm (lower only)    = 1.42s

No improvement, and the parse progress bar runs both times. The directory exists to
**bound memory**, not to avoid work: Phase 1 spills each AST to disk so Phase 2 can load
them one at a time and *"ASTs never accumulate in memory across workers"*.

So this is not "add a second cache layer above the AST cache". It is introducing
compile reuse for the first time. The naming collision is itself a hazard — a reader
reasonably assumes caching already exists.

### 2. The lowered IR is **not self-contained**. This is the hard constraint.

Lowering registers builtins as a *side effect*, into a process-global table
(`squall/squall/strategy_stores.py:95`):

    Builtins.TABLE[func_name] = builtin

The emitted IR then refers to those builtins by name — `__cics_syncpoint_hook`,
`__cics_rollback_hook`, `__exec_sql`. Load a serialised `LinkedProgram` into a fresh
process without constructing the coprocessor strategies and the IR references names
nothing has registered. It would load cleanly and fail at execution.

Consequence: **deserialisation cannot skip strategy construction.** It can skip parsing
and lowering, which is where the time goes, but the specs must still be built so their
registrations happen. Either that is stated as a precondition of loading, or builtin
registration stops being a side effect and becomes part of the artefact — a declarative
manifest of required builtins that loading verifies against the live table, failing
loudly on a mismatch. The second is more work and considerably safer.

(red-dragon-forge has a test fixture that snapshots and restores `Builtins.TABLE` around
every test precisely because this global is load-bearing and order-dependent.)

### 3. The object graph shares instructions between two structures.

`LinkedProgram` holds both `merged_ir: list[InstructionBase]` and `merged_cfg: CFG`,
and `CFG.blocks[...].instructions` is also a `list[InstructionBase]` — the *same*
instruction objects, reachable two ways. `InstructionBase` carries
`id: InstructionId = field(..., compare=False)`.

A naive tree serialisation duplicates every instruction and breaks identity on reload.
Anything relying on `is` or on `id` uniqueness would silently misbehave. The artefact
needs instructions written once and referenced by id from the CFG — or the CFG dropped
from the artefact and rebuilt on load, which is cheap and sidesteps the problem
entirely. **Rebuilding the CFG on load is the recommended default** until measurement
shows it matters.

Otherwise the types are friendly: `InstructionBase` and its subclasses are frozen
dataclasses; `CFG`, `BasicBlock`, `FunctionRegistry` and `ModuleUnit` are plain
dataclasses of dicts, lists and `NewType`s over `str`/`int`, all JSON-representable.
Instruction subclasses need a discriminated union keyed by opcode, since `opcode` and
`operands` are abstract on the base.

## The cache key is the whole problem

A stale artefact that loads successfully is far worse than no cache: it fails as a bug
in the program under test, at a distance from its cause. The key must cover at least:

1. **The coprocessor spec composition.** The subtle one. The same source lowered with
   the CICS spec alone and with CICS+SQL composed produces *different IR* — `EXEC SQL`
   becomes real calls only when squall's strategy is present. A key over source alone
   would serve CICS-only IR to a Db2 region, silently dropping every SQL statement.
   Identity *and version* of every strategy and dialect parser must be in the key.
2. **An IR/lowering schema version.** Four fixes landed on 2026-09-20 — INSPECT
   TALLYING and REPLACING operand resolution, FUNCTION argument subscripts,
   parenthesised FUNCTION groups — each of which changed emitted IR for *unchanged*
   source. Under a naive cache every one would have been masked until someone cleared
   it by hand. This is not hypothetical; it is this month.
3. **Copybook contents, not just program source.** A program's digest does not change
   when a copybook it `COPY`s changes. The existing AST spill keys on `_digest(src)` of
   the program alone; the same trap applies here and is worth fixing in both places.
4. **Every linked module's source**, not only the main program's.

## Known hole to reconcile

`cobol_compile.py:126-130` documents that disk resolution of callees is deliberately
excluded from the AST-cache path: *"callers using source_search_dirs + ast_cache_dir
together will get a LinkedProgram without disk-resolved callees."* An IR artefact must
not inherit that silent partial-linking behaviour. It should either cover disk-resolved
callees or refuse to cache when they are present — silently caching a partial link is
the worst available outcome.

## Options

**A. Per-module artefacts (object modules), linked on load.** Caches well across regions
sharing programs; the linker still runs. Closest to how a real toolchain works.

**B. Whole-program artefact (load module).** Simpler, skips linking too, but a
one-program change invalidates the whole thing, and two regions sharing 18 of 19
programs share nothing.

**C. Hybrid** — per-module artefacts plus a linked-program artefact keyed on the module
set.

A is the better default: invalidation is proportional to what changed. B's appeal is
that it also skips the linker, which has not been measured and may be negligible.

## What must be proven before this is worth shipping

**Round-trip equivalence, not speed.** Lower a corpus program, serialise, reload, and
assert the loaded `LinkedProgram` executes to the same VM state as the freshly-lowered
one. A cache that is merely fast is not the feature. Given that this project has
repeatedly found tests passing while the bug was still present, the equivalence check
must be shown failing when the artefact is deliberately stale.

Also worth measuring first, and cheap: **the lower-vs-link split**. The 1.37s above is
parse + lower for one small program; nobody has measured what fraction of a 19-program
region build is lowering versus linking versus parsing. If parsing dominates, a much
smaller change — making the AST spill an actual reuse cache — captures most of the win
at a fraction of the risk, and does not face the self-containment problem at all.

**That measurement should precede any decision between the options above.**

## Non-goals

- On-demand compilation at `CALL` time. Considered and rejected: it would model dynamic
  CALL faithfully (resolve against the search dirs at runtime, as z/OS resolves against
  STEPLIB) but requires the parser and compiler to stay live during execution. Owner's
  preference is to lower everything needed up front.
- Compiling every program in the search dirs unconditionally. Separate idea, separate
  trade-offs (compile time scales with directory size, one broken member breaks every
  build, same-named `PROGRAM-ID`s become ambiguous rather than resolved first-hit-wins).

## Open questions

1. Does the artefact include the CFG, or is it rebuilt on load? (Recommend rebuild.)
2. Does builtin registration stay a documented precondition, or become a verified
   manifest? (Recommend manifest, but it is the larger piece of work.)
3. Format — JSON for debuggability and diffability, or something compact? No evidence
   yet that size matters; start with JSON unless measurement says otherwise.
4. Where do artefacts live, and who invalidates them? A stale artefact directory
   surviving a `git pull` that changed lowering is finding 2's failure mode in the wild.
5. Is the same artefact usable by cobble's analysis path, or does analysis need
   something the execution path does not carry?
