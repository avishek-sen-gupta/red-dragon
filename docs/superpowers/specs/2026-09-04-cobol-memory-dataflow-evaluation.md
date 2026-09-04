# Memory Dataflow — Density Evaluation on Real COBOL

**Date:** 2026-09-04
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
in CBTRN02C, each time after a `MOVE <file>-STATUS TO IO-STATUS`. That is
precisely the shape risk 7.4 describes.

## 2. Results

Seven real CardDemo batch programs, every one that parses from this repo — no
selection, the numbers below are the first ones each program produced. All
figures with the reaching-definitions solver run to convergence (see §5).

| Program | Lines | Fields (nodes) | Direct edges | Mean out-degree | **Connected fraction** | Flow-sensitive fraction | Impact set: median / max |
|---|---:|---:|---:|---:|---:|---:|---:|
| CBACT02C | 178 | 15 | 9 | 0.60 | **0.114** | 0.114 | 0 / 7 |
| CSUTLDTC | 157 | 27 | 29 | 1.07 | **0.098** | 0.094 | 2 / 8 |
| CBACT01C | 430 | 62 | 104 | 1.68 | **0.188** | 0.186 | 13 / 49 |
| CBTRN03C | 649 | 99 | 95 | 0.96 | **0.081** | 0.081 | 12 / 34 |
| CBACT04C | 652 | 86 | 99 | 1.15 | **0.176** | 0.170 | 17 / 35 |
| CBTRN02C | 731 | 105 | 129 | 1.23 | **0.094** | 0.088 | 11 / 57 |
| CBSTM03A | 924 | 120 | 148 | 1.23 | **0.070** | 0.070 | 2 / 62 |

"Impact set" is the number of fields reachable **from** one field after
closure — the shape of the answer an actual impact query returns. It is
reported alongside the fraction because the fraction is a mean over pairs and
a mean can hide a graph where the fields anyone asks about reach everything.

Runtime is not a constraint: parse + lower ≈ 1.5 s, solve ≈ 2 s, graph +
closure < 0.1 s on the largest program. The `_transitive_closure` re-scan the
plan flagged as untested at scale is not the bottleneck at these sizes.

## 3. Verdict on risk 7.4

**The fraction is low enough. Context-insensitive `PERFORM` is empirically
usable on this corpus, and risk 7.4 does not materialise.**

Connected fraction sits between **0.07 and 0.19** across a 5× range of program
size, and *falls* as programs grow (the three largest are the three lowest).
The typical impact query returns **11–17 fields out of ~100** — a paragraph's
worth of program, which is a useful subset. It is emphatically not "most of
the program".

The largest impact sets are the ones that *should* be large: 57 of 105 fields
for `DALYTRAN-RECORD` in CBTRN02C, 49 of 62 for `ACCOUNT-RECORD` in CBACT01C.
Those are the input record areas of batch programs whose entire job is to
transform the input record. An impact analysis that did **not** say "changing
the input record affects most of this program" would be wrong.

The recommendation to escalate to paragraph summaries (spec §8) is therefore
**not** triggered by this measurement. Summaries remain worth building for
scope (2), which needs them anyway — but not to rescue the density.

## 4. Which construct carries the connectivity

Measured by ablation, not guessed. Each row re-runs the whole analysis with
one thing removed and re-reports the fraction.

| Ablation | CBACT01C | CBTRN02C |
|---|---:|---:|
| full analysis | 0.188 | 0.094 |
| drop the `PERFORM` return edges (unsound; differential only) | 0.173 | 0.042 |
| drop the four `IO-STATUS*` fields | 0.107 | 0.047 |
| drop the `file`-region fields (18 of 62 / 12 of 105) | **0.055** | **0.034** |
| drop the top 10 closure sinks | 0.082 | 0.033 |

Three findings, in order of size.

**(a) Node collapse is not the cause.** The flow-sensitive fraction — the same
reachability recomputed over definition-SITE nodes, so two writes to one field
stay distinct and a killed definition stops propagating — tracks the
field-graph fraction to within 0.006 on every program. Whatever connectivity
exists is not manufactured by the one-node-per-field projection. This
mattered: attributing the density to the wrong layer would have sent the
roadmap at flow sensitivity instead of at the real cause below.

**(b) The `PERFORM` merge contributes, but modestly, and never dominates.**
Severing the return edges takes CBACT01C from 0.188 to 0.173 (−8%) and
CBTRN02C from 0.094 to 0.042 (−55%). The larger figure is the honest one to
quote for the merge's contribution — and even where it halves the graph, the
*with-merge* number is still 0.094. The merge inflates the graph; it does not
mush it.

**(c) The dominant source is not `PERFORM` at all — it is that every FD
record area is laid out at offset 0 of one shared `file` region.** Dumping the
recorded extents for CBTRN02C:

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

The effect is measurable and large: removing the `file`-region fields takes
CBACT01C from 0.188 to 0.055 and CBTRN02C from 0.094 to 0.034 — a bigger drop
than any other ablation, and bigger than the `PERFORM` merge in both. It also
produces visibly wrong edges: `FD-TRAN-CAT-KEY` in CBTRN02C shows direct
dependencies on `FD-ACCTFILE-REC`, `FD-REJS-RECORD`, `FD-TRANFILE-REC` and
`FD-TRAN-RECORD` — four unrelated files.

Note this is an over-approximation, so it is *sound* and it does not
invalidate the verdict — the true fractions are lower than the ones measured,
which only strengthens §3. But it is the single highest-value precision fix
available, and it is cheaper than paragraph summaries: give each FD its own
base offset within the `file` region (or its own region) and the spurious
edges disappear by range disjointness with no change to the analysis. Filed as
**red-dragon-7211** (P1).

The secondary source is the genuine shared-global pattern: all six file status
fields flow into `IO-STATUS`, and from there into the `IO-STATUS-04` /
`TWO-BYTES-*` decode chain of the display paragraph. That is *real* data flow
through a shared variable, not a `PERFORM` artefact — a context-sensitive
analysis would produce the same field-level edges, because `IO-STATUS` is one
field however many contexts write it. Notably these hubs are **sinks**: they
have high in-degree and near-zero out-degree, so they absorb connectivity
rather than spreading it, and they inflate the pair count without degrading
impact queries.

## 5. Two measurement hazards found while doing this

**The default iteration cap is exhausted by real programs.**
`DATAFLOW_MAX_ITERATIONS = 1000` counts worklist *pops*, not sweeps.
`solve_reaching_definitions` warns and returns a **truncated, edge-missing**
result. Three of the seven programs (CBTRN02C, CBTRN03C, CBSTM03A — everything
from ~650 lines up) hit it. On these programs the truncated and converged
graphs happened to be identical, so the numbers in §2 are unaffected, but the
margin is luck: at larger scale the cap silently under-reports, which is the
one failure direction this design exists to avoid. The script therefore
reports convergence explicitly and takes `--max-iterations`; all figures above
were taken converged. A caller of the analysis gets only a `logger.warning`.
Filed as **red-dragon-aso9** (P2).

**Online CICS programs cannot be analysed from this repo.** `COBIL00C` and the
other online programs fail at `ValueError: Unknown COBOL statement type:
'EXEC_CICS'` — the CICS dialect parser and lowering strategy live downstream,
not here. Reported rather than worked around. It bounds this evaluation: the
verdict covers batch programs. Online programs have a different paragraph
idiom (a screen-handling driver with heavily shared send/receive paragraphs)
and the measurement should be repeated there when the harness allows it.

## 6. How to reproduce

```bash
export PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
uv run python scripts/memory_dataflow_density.py <program>.cbl \
    --copybook-dir <carddemo>/app/cpy --copybook-ext cpy --copybook-ext CPY \
    --max-iterations 2000000 --decompose
```

The CardDemo sources are not vendored in this repo; point `--copybook-dir` at
a local checkout of the sample application.

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
