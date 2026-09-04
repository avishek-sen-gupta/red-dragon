# Memory Dataflow — Density Evaluation on Real COBOL

**Date:** 2026-09-04 (revised after review)
**Settles:** spec risk 7.4, "context-insensitive `PERFORM` may be empirically
unusable"
**Tool:** `scripts/memory_dataflow_density.py`
**Measured at:** the branch head that includes the `PERFORM` return-edge
wiring. Any density figure taken before that commit is an artefact — the CFG
was severed at every `PERFORM`, so the graph read as sparse for entirely the
wrong reason and is not comparable.

---

## 1. The question

The analysis merges every call site of a paragraph. COBOL's idiom is a handful
of shared utility paragraphs performed from dozens of places over a flat
WORKING-STORAGE with no scoping to contain the spill. Sound, but if the merge
reconnects the program, an impact query returns most of it and the analysis is
useless in practice however correct it is.

Headline metric: after transitive closure, what fraction of the n·(n−1)
ordered field pairs is connected? 1.0 means every field affects every other.

The idiom is genuinely present in the corpus, so the test is a fair one:
`9910-DISPLAY-IO-STATUS` is performed from **10** sites in CBACT01C and **18**
in CBTRN02C, each time after a `MOVE <file>-STATUS TO IO-STATUS`; CBEXPORT
writes one `EXPORT-RECORD` from five separate export paragraphs. That is
precisely the shape risk 7.4 describes.

## 2. Results

### How the corpus was enumerated

`scripts/memory_dataflow_density.py --corpus <dir>` globs every `*.cbl` /
`*.CBL` in the CardDemo `app/cbl` directory and measures all of them,
**printing a row for every file including the ones that fail**. The corpus is
read off the filesystem, never typed by hand: an earlier revision of this
document listed seven programs and claimed they were all of them, and the six
it had never enumerated included the counterexample in §3. The `--corpus`
mode exists so that cannot recur.

Of the 31 sources in that directory, **14 analyse** and **17 fail** — every
failure is an online CICS program, and all of them fail the same way (see
§5). Corpus checkout: CardDemo at commit `a8292010`, a local vendored
checkout; the sources are not in this repo, so the ablation numbers below are
reproducible only against that checkout.

### The table

Every analysable program, in directory order, at `--max-iterations 2000000`
with `solver converged: yes` printed for each — so none of these figures is
truncated by the `DATAFLOW_MAX_ITERATIONS` hazard described in §5.

| Program | Lines | Fields (nodes) | Direct edges | Mean out-degree | **Connected fraction** | Flow-sensitive | Impact median / max |
|---|---:|---:|---:|---:|---:|---:|---:|
| CBACT01C | 430 | 62 | 104 | 1.68 | 0.188 | 0.186 | 13 / 49 |
| CBACT02C | 178 | 15 | 9 | 0.60 | 0.114 | 0.114 | 0 / 7 |
| CBACT03C | 178 | 15 | 9 | 0.60 | 0.114 | 0.114 | 0 / 7 |
| CBACT04C | 652 | 86 | 99 | 1.15 | 0.176 | 0.170 | 17 / 35 |
| CBCUS01C | 178 | 15 | 9 | 0.60 | 0.114 | 0.114 | 0 / 7 |
| **CBEXPORT** | **582** | **141** | **383** | **2.72** | **0.660** | **0.660** | **103 / 110** |
| CBIMPORT | 487 | 137 | 168 | 1.23 | 0.021 | 0.021 | 2 / 118 |
| CBSTM03A | 924 | 120 | 148 | 1.23 | 0.070 | 0.070 | 2 / 62 |
| CBSTM03B | 230 | 14 | 8 | 0.57 | 0.044 | 0.044 | 0 / 2 |
| CBTRN01C | 494 | 34 | 30 | 0.88 | 0.176 | 0.120 | 3 / 21 |
| CBTRN02C | 731 | 105 | 129 | 1.23 | 0.094 | 0.088 | 11 / 57 |
| CBTRN03C | 649 | 99 | 95 | 0.96 | 0.081 | 0.081 | 12 / 34 |
| COBSWAIT | 41 | 2 | 1 | 0.50 | 0.500 | 0.500 | 0 / 1 |
| CSUTLDTC | 157 | 27 | 29 | 1.07 | 0.098 | 0.094 | 2 / 8 |

"Impact" is the number of fields reachable **from** one field after closure —
the shape of the answer an impact query actually returns. It is reported
alongside the fraction because the fraction is a mean over pairs, and a mean
can hide a graph where the fields anyone asks about reach everything.

Two rows are degenerate and should not be read as evidence either way:
COBSWAIT has 2 nodes (a single edge is 0.5 by construction), and
CBACT02C/03C/CBCUS01C are the same 178-line print-the-file skeleton three
times over.

No trend is claimed across size. There is none in this data: 0.176 at 652
lines (CBACT04C), 0.070 at 924 (CBSTM03A), 0.660 at 582 (CBEXPORT).

Runtime is not a constraint: parse + lower ≈ 1.6 s, solve ≈ 4 s worst case,
graph + closure ≈ 0.1 s. The `_transitive_closure` re-scan the plan flagged as
untested at scale is not the bottleneck at these sizes.

## 3. CBEXPORT — the decisive program

CBEXPORT is exactly the shape risk 7.4 predicts: six FDs, one `EXPORT-RECORD`
written from five export paragraphs, a shared `9999-ABEND`, and **319
REACHING edges against 64 VALUE edges** — a graph made overwhelmingly of
reaching-definition edges rather than of direct value flow. Its median impact
query returns **103 of 141 fields, 73% of the program**. As shipped, on this
program, the analysis is useless.

Ablating it decides what is responsible:

| Ablation on CBEXPORT | Fraction |
|---|---:|
| full analysis | **0.660** |
| drop the `PERFORM` return edges (unsound; differential only) | 0.454 |
| drop the `file`-region fields (58 of 141) | **0.015** |

Removing the `PERFORM` merge takes it from 0.660 to 0.454 — still unusable.
Removing the file-region fields takes it to **0.015**. The connectivity is not
coming from context insensitivity. It is coming from `file`-region aliasing
(§4c), and once that is fixed CBEXPORT becomes the *sparsest* program in the
corpus rather than the densest.

## 4. Verdict on risk 7.4 — conditional

**Context-insensitive `PERFORM` does not mush the graph. But that conclusion
holds only once file-region aliasing (red-dragon-7211) is fixed. As shipped
today, the analysis returns most of the program on a real batch program.**

Both halves matter and neither should be quoted without the other:

* **The design bet is sound.** On no program does removing the `PERFORM`
  merge account for the density: −8% on CBACT01C, −55% on CBTRN02C, −31% on
  CBEXPORT, and in the one case where the graph is unusable the merge leaves
  it unusable (0.454) while the file-region fix makes it excellent (0.015).
  Escalating to paragraph summaries (spec §8) would not fix CBEXPORT. They
  remain worth building for scope (2), which needs them anyway — but not to
  rescue the density.
* **The analysis is not usable today.** One of 14 programs returns 73% of
  itself to a median impact query, and it is not an exotic one. A consumer
  built on the current output will meet CBEXPORT-shaped programs.

So red-dragon-7211 is not a "cheapest available precision win"; it is the
**precondition of the usability verdict**.

Where the impact sets are large for good reason, they should not be mistaken
for mush: 57 of 105 fields for `DALYTRAN-RECORD` in CBTRN02C, 49 of 62 for
`ACCOUNT-RECORD` in CBACT01C. Those are the input record areas of batch
programs whose whole job is to transform the input record. An impact analysis
that did *not* say "changing the input record affects most of this program"
would be wrong.

## 5. Which construct carries the connectivity

Measured by ablation, not guessed. Each row re-runs the whole analysis with
one thing removed and re-reports the fraction; both ablations are flags on the
committed tool (`--sever-perform`, `--drop-region FILE`), so every number in
these tables is reproducible without a scratch script.

| Ablation | CBACT01C | CBTRN02C | CBEXPORT |
|---|---:|---:|---:|
| full analysis | 0.188 | 0.094 | 0.660 |
| drop the `PERFORM` return edges (unsound; differential only) | 0.173 | 0.042 | 0.454 |
| drop the four `IO-STATUS*` fields | 0.107 | 0.047 | 0.660 |
| drop the `file`-region fields | **0.055** | **0.034** | **0.015** |
| drop the top 10 closure sinks | 0.082 | 0.033 | — |

**(a) Node collapse is not the cause.** The flow-sensitive fraction — the same
reachability recomputed over definition-SITE nodes, so two writes to one field
stay distinct and a killed definition stops propagating — is at or below the
field-graph fraction on every program, and equal to it on most. The largest
gap is **CBTRN01C, 0.176 against 0.120 (Δ0.056)**; every other program is
within 0.006, and CBEXPORT is identical at 0.660. So the one-node-per-field
projection accounts for a few points at most and for none of the CBEXPORT
result. This mattered: attributing the density to the wrong layer would have
sent the roadmap at flow sensitivity instead of at the real cause below.

**(b) The `PERFORM` merge contributes but never dominates.** −8% on CBACT01C,
−55% on CBTRN02C, −31% on CBEXPORT. Even where it halves the graph, the
*with-merge* number is still 0.094; and where the graph is genuinely unusable
its removal does not rescue it.

**(c) The dominant source is that every FD record area is laid out at offset 0
of one shared `file` region.** Dumping the recorded extents for CBTRN02C:

```
FILE      0 +350  FD-TRAN-RECORD
FILE      0 +50   FD-XREFFILE-REC
FILE      0 +300  FD-ACCTFILE-REC
FILE      0 +430  FD-REJS-RECORD
FILE      0 +50   FD-TRAN-CAT-BAL-RECORD
FILE      0 +350  FD-TRANFILE-REC
```

Six different files' record areas, all starting at byte 0 of the same region,
therefore all mutually `may_alias` and all mutually `must_cover`-ing the
shorter ones. A write to one file's record area is modelled as a write to
every other file's. Real COBOL gives each FD its own record area unless
`SAME RECORD AREA` is specified.

The effect is the largest in the corpus: CBEXPORT 0.660 → 0.015, CBACT01C
0.188 → 0.055, CBTRN02C 0.094 → 0.034 — bigger than the `PERFORM` merge on
every program measured. It also produces visibly wrong edges:
`FD-TRAN-CAT-KEY` in CBTRN02C shows direct dependencies on `FD-ACCTFILE-REC`,
`FD-REJS-RECORD`, `FD-TRANFILE-REC` and `FD-TRAN-RECORD` — four unrelated
files.

The direction is over-approximating, so it is *sound*; the true graph is
sparser than the one measured, which only strengthens §4's first half. The fix
is cheap and needs no change to the analysis: give each FD its own base offset
within the `file` region (or its own region) and the spurious edges disappear
by range disjointness. Filed as **red-dragon-7211** (P1).

The secondary source is the genuine shared-global pattern: all six file status
fields flow into `IO-STATUS`, and from there into the `IO-STATUS-04` /
`TWO-BYTES-*` decode chain of the display paragraph. That is *real* data flow
through a shared variable, not a `PERFORM` artefact — a context-sensitive
analysis would produce the same field-level edges, because `IO-STATUS` is one
field however many contexts write it. These hubs are **sinks**: high
in-degree, near-zero out-degree, so they inflate the pair count without
degrading impact queries. CBEXPORT has no `IO-STATUS` chain at all, which is
why that ablation moves nothing there.

## 6. Two measurement hazards found while doing this

**The default iteration cap is exhausted by real programs.**
`DATAFLOW_MAX_ITERATIONS = 1000` counts worklist *pops*, not sweeps.
`solve_reaching_definitions` warns and returns a **truncated, edge-missing**
result, and `analyze_memory_dataflow` gives the caller no signal at all.
Programs from roughly 650 lines up hit it. **Every figure in this document was
taken with `--max-iterations 2000000` and with convergence printed**, so none
of them is affected — but a caller of the shipped analysis has no way to know
whether its result converged. Filed as **red-dragon-aso9**.

**Online CICS programs cannot be analysed from this repo.** All 17 failures in
§2 are online programs. They fail first on CICS system copybooks (`DFHAID`
etc., not in `app/cpy`); supplying those gets one step further and then fails
with `ValueError: Unknown COBOL statement type: 'EXEC_CICS'` — the CICS
dialect parser and lowering strategy live downstream, not here. Reported
rather than worked around. It bounds this evaluation: the verdict covers batch
programs. Online programs have a different paragraph idiom (a screen-handling
driver with heavily shared send/receive paragraphs) and the measurement should
be repeated there when the harness allows it.

## 7. How to reproduce

```bash
export PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar

# the whole corpus, failures included
uv run python scripts/memory_dataflow_density.py \
    --corpus <carddemo>/app/cbl \
    --copybook-dir <carddemo>/app/cpy --copybook-ext cpy --copybook-ext CPY \
    --max-iterations 2000000

# one program, with the edge decomposition
uv run python scripts/memory_dataflow_density.py <carddemo>/app/cbl/CBEXPORT.cbl \
    --copybook-dir <carddemo>/app/cpy --copybook-ext cpy --copybook-ext CPY \
    --max-iterations 2000000 --decompose

# the two ablations
... --drop-region FILE        # attribute connectivity to the file region
... --sever-perform           # UNSOUND; differential against the full run only
```

CardDemo is not vendored in this repo; point the paths at a local checkout
(the figures here are from commit `a8292010`).

The metric was validated by hand before being trusted, on programs whose
answer can be worked out on paper:

* three fields, `A → B → C`: 3 connected pairs of 6 = 0.500, mean out-degree
  0.67. Both reported.
* five fields with a reused temporary (`A → T → B`, then `C → T → D`): the
  field graph must report 8/20 = 0.400 (it collapses the two writes to `T`,
  manufacturing `A → D` and `C → B`) while the flow-sensitive metric must
  report 6/20 = 0.300. Both reported, which is what makes the two columns in
  §2 meaningful when they *do* differ.
* a group written and a child read across a `PERFORM`: the closed graph
  matches `analyze_memory_dataflow`'s own `field_graph` exactly, confirming
  the script measures the shipped analysis and not a private re-derivation.
