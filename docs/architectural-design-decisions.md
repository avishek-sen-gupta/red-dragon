# Architectural Decision Records

This document captures key architectural decisions made during the development of RedDragon. Entries are ordered chronologically and were retroactively extracted from the commit history.

---

### ADR-001: Flattened TAC IR as universal intermediate representation (2026-02-25)

**Context:** The project needed a single representation that all source languages lower into, enabling language-agnostic analysis and execution. A tree-based AST would require per-language walkers for every downstream pass.

**Decision:** Adopt a flattened three-address code (TAC) IR with 27 opcodes (see [IR Reference](ir-reference.md)). Every instruction is a flat dataclass with an opcode, operands, and a destination register. No nested expressions — all intermediates are explicit.

**Consequences:** CFG construction, dataflow analysis, and VM execution all operate on the same flat instruction list, eliminating duplication. Adding a new language frontend only requires emitting these opcodes. The trade-off is that lowering must decompose complex expressions (e.g., `a + b * c`) into multiple instructions, increasing IR verbosity.

---

### ADR-002: Modular package structure (2026-02-25)

**Context:** The initial implementation was a single monolithic `interpreter.py` file (~1200 lines). This made navigation, testing, and parallel development difficult.

**Decision:** Break the interpreter into a Python package (`interpreter/`) with focused modules: `ir.py` (IR types), `cfg.py` (CFG builder), `vm.py` (VM state and execution), `registry.py` (function/class registry), `builtins.py` (built-in function table), `executor.py` (opcode dispatch), and `run.py` (pipeline orchestration).

**Consequences:** Each module can be tested and understood independently. Import boundaries enforce separation of concerns. The cost is additional boilerplate in `__init__.py` for re-exports.

---

### ADR-003: Fully deterministic VM with symbolic values (2026-02-25)

**Context:** The original VM called an LLM whenever it encountered unknown values (unresolved imports, missing externals). This made execution non-deterministic, slow, and untestable.

**Decision:** Remove all LLM fallbacks from the VM execution path. When the VM encounters incomplete information, it creates symbolic values (`sym_0`, `sym_1`, ...) with descriptive hints instead of asking an LLM. Symbolic values propagate through arithmetic, calls, and field access deterministically.

**Consequences:** Execution is fully reproducible and requires 0 LLM calls for programs with concrete inputs. Data flow through programs with missing dependencies is still traced. The trade-off is that symbolic branches always take the true path (a simplification), and symbolic values cannot be resolved to concrete results without an external oracle.

---

### ADR-004: Heap materialisation for symbolic field access (2026-02-25)

**Context:** When the VM accesses `obj.field` on a symbolic object, repeated accesses to the same field were creating distinct symbolic values each time, breaking data-flow identity.

**Decision:** Materialise a heap object for symbolic values on first field access. Subsequent accesses to the same field on the same object return the same symbolic value, maintaining referential consistency.

**Consequences:** Symbolic data-flow analysis correctly tracks field identity across multiple access sites. The heap grows with materialised objects, but this is bounded by the number of distinct (object, field) pairs accessed.

---

### ADR-005: LLM-as-compiler-frontend (2026-02-25)

**Context:** Supporting languages without tree-sitter grammars required an alternative lowering path. Using an LLM as a "reasoning engine" to analyse code produces inconsistent, hallucination-prone results.

**Decision:** Constrain the LLM to act as a **compiler frontend**: the prompt provides all 27 opcode schemas (see [IR Reference](ir-reference.md)), concrete patterns for functions/classes/control flow, and a full worked example. The LLM's job is mechanical translation, not reasoning. Output is structured JSON matching the IR schema.

**Consequences:** LLM output is far more consistent because the task is pattern-matching rather than open-ended reasoning. Any language the LLM has seen in training can be lowered. The trade-off is that the prompt is large (~2K tokens) and quality depends on the LLM's familiarity with the source language.

---

### ADR-006: Multi-backend LLM abstraction (2026-02-25)

**Context:** Different users have access to different LLM providers (Claude, OpenAI, HuggingFace, Ollama). Hardcoding a single provider limits adoption.

**Decision:** Define an `LLMClient` abstract base class with a `generate(prompt) -> str` method. Implement concrete clients for Claude (Anthropic API), OpenAI, HuggingFace Inference Endpoints, and Ollama (local). Selection is via a `-b` CLI flag.

**Consequences:** Adding a new LLM provider requires only implementing the `LLMClient` interface. Users can run entirely locally with Ollama (no API key). The trade-off is that quality varies across providers — Claude produces the best IR, while smaller local models may require more retries.

---

### ADR-007: Closure capture-by-reference with shared environment cells (2026-02-25)

**Context:** The VM needed to support closures. Initial implementation captured variables by snapshot (copy at definition time), which broke patterns where closures mutate shared state (e.g., counter factories, callback registrations).

**Decision:** Implement closures with a shared `ClosureEnvironment` that holds mutable cells. All closures from the same enclosing scope share the same environment object. Variable reads/writes inside closures go through the environment, not the local scope.

**Consequences:** Mutations inside closures persist across calls and are visible to sibling closures from the same scope, matching Python/JavaScript semantics. The trade-off is increased complexity in the scope resolution chain (local scope → closure environment → enclosing scopes).

---

### ADR-008: Tree-sitter deterministic frontends with dispatch table engine (2026-02-25)

**Context:** Relying on LLMs for well-supported languages is slow, expensive, and non-deterministic. Tree-sitter provides fast, accurate parsing for many languages.

**Decision:** Build deterministic frontends for 15 languages using tree-sitter. Each frontend extends a `BaseFrontend` class that uses a dispatch table mapping AST node types to handler methods. Common patterns (if/else, while, for, return) are handled in the base class; language-specific constructs override or extend.

**Consequences:** Parsing is sub-millisecond with zero LLM calls. The dispatch table pattern makes adding new node types mechanical — add a method and register it. 15 languages share the same base infrastructure. The trade-off is that each language's AST quirks require language-specific handlers, and the dispatch table must be kept in sync with tree-sitter grammar updates.

---

### ADR-009: Iterative dataflow analysis (2026-02-26)

**Context:** Static analysis of data flow (which definitions reach which uses, which variables depend on which) requires a fixpoint computation over the CFG. The project needed reaching definitions, def-use chains, and variable dependency graphs.

**Decision:** Implement iterative worklist-based dataflow analysis: compute GEN/KILL sets per basic block, propagate reaching definitions to fixpoint, extract def-use chains from the fixpoint result, then build variable dependency graphs via transitive closure.

**Consequences:** Analysis is sound for intraprocedural flow and handles loops correctly via fixpoint iteration. Dependency graphs enable downstream consumers (e.g., impact analysis, slicing). The analysis is intraprocedural only — interprocedural flow is not tracked.

---

### ADR-010: Chunked LLM frontend with per-function decomposition (2026-02-26)

**Context:** Large source files overflow LLM context windows when sent as a single prompt. The LLM frontend failed on files with many functions/classes.

**Decision:** Add a chunked LLM frontend that: (1) uses tree-sitter to decompose the source into per-function/class chunks, (2) sends each chunk to the LLM independently, (3) renumbers registers and labels to avoid collisions, (4) reassembles into a single IR. Failed chunks produce `SYMBOLIC` placeholders.

**Consequences:** Files of arbitrary size can be processed. Each chunk fits within context limits. Renumbering ensures a consistent global register/label namespace. The trade-off is that cross-function references within a single chunk boundary may be lost, and tree-sitter is required even for the LLM path (to perform decomposition).

---

### ADR-011: Retry-on-parse-failure over JSON repair for LLM output (2026-02-26)

**Context:** LLM-generated IR occasionally contains malformed JSON. The initial approach used a `json_repair` library to heuristically fix broken JSON, but this silently produced invalid IR structures.

**Decision:** Remove the JSON repair layer. Instead, retry the LLM call up to 3 times on parse failure, including the error message in the retry prompt. If all retries fail, raise an explicit error.

**Consequences:** IR output is either valid (parsed correctly) or explicitly fails — no silent corruption. Retries with error context often succeed on the second attempt. The trade-off is slightly higher latency on malformed responses (up to 3 round-trips) and the possibility of total failure if the LLM consistently produces invalid output.

---

### ADR-012: Unit/integration test separation (2026-02-26)

**Context:** Tests were in a flat directory mixing pure-logic unit tests with tests that call LLMs or touch external repos. CI was slow and flaky because LLM tests ran on every push.

**Decision:** Reorganise tests into `tests/unit/` (pure logic, no I/O, deterministic) and `tests/integration/` (LLM calls, databases, external repos). CI runs only unit tests; integration tests run locally or in dedicated CI jobs.

**Consequences:** CI is fast and deterministic. Developers can run unit tests confidently without API keys. The separation enforces the discipline of dependency injection for testability. The trade-off is maintaining the directory boundary as the test suite grows.

---

### ADR-013: Registry split into 3 focused modules (2026-02-26)

**Context:** `interpreter/registry.py` had grown to handle function registration, class registration, and registry construction — three distinct responsibilities in one file.

**Decision:** Split into `interpreter/registry.py` (function registry), `interpreter/class_registry.py` (class registry), and `interpreter/registry_builder.py` (construction logic that scans IR to populate both registries).

**Consequences:** Each module has a single responsibility and can be tested independently. The builder is the only module that knows about both registries. The trade-off is three files instead of one, with cross-references between them.

---

### ADR-014: SYMBOLIC fallback with descriptive hints (2026-02-26)

**Context:** When a deterministic frontend encounters an AST node type it does not handle, it must decide between crashing, silently skipping, or producing a placeholder.

**Decision:** Emit a `SYMBOLIC` IR instruction with a descriptive hint string (e.g., `SYMBOLIC "unsupported: list_comprehension"`) for unhandled constructs. The VM treats these as symbolic values that propagate through execution.

**Consequences:** Frontends gracefully degrade — partial lowering is always available. The hints make it easy to identify which constructs need implementation. Over time, `SYMBOLIC` emissions are systematically replaced with real IR (the test count progression documents this). The trade-off is that analysis results are approximate for programs using unhandled constructs.

---

### ADR-015: Mermaid CFG output with subgraphs, call edges, and block collapsing (2026-02-26)

**Context:** Text-based CFG dumps are hard to visually navigate for non-trivial programs. The project needed a visual CFG representation that could be rendered in Markdown, GitHub, and documentation tools.

**Decision:** Add `--mermaid` flag that outputs CFG as a Mermaid flowchart. Function/class bodies render as subgraphs. `CALL_FUNCTION` sites connect to function entry blocks with dashed call edges. Blocks with more than 6 instructions collapse to show the first 4, an `... (N more)` placeholder, and the terminator.

**Consequences:** CFGs are visually navigable in any Mermaid-compatible renderer (GitHub, VS Code, docs). Block collapsing keeps large CFGs readable without hiding branch/return instructions. The trade-off is that Mermaid has layout limitations for very large graphs, and the collapsing heuristic may hide relevant instructions in the middle of long blocks.

---

### ADR-016: Composable API layer (2026-02-26)

**Context:** All functionality was accessible only through the CLI (`argparse`). Programmatic consumers (notebooks, other tools, tests) had to shell out or duplicate pipeline logic.

**Decision:** Extract CLI pipelines into composable functions: `lower_source()`, `dump_ir()`, `build_cfg_from_source()`, `dump_cfg()`, `dump_mermaid()`, `extract_function_source()`. Functions compose hierarchically (e.g., `dump_cfg` calls `build_cfg_from_source` which calls `lower_source`). Re-export from `interpreter/__init__.py`.

**Consequences:** Any pipeline stage is callable from Python without argparse. Tests exercise the API directly. The CLI becomes a thin wrapper. The trade-off is maintaining two entry points (CLI and API) that must stay in sync.

---

### ADR-017: Structured SourceLocation traceability on IR instructions (2026-02-26)

**Context:** When debugging lowering or analysing IR, there was no way to trace an IR instruction back to the source code that produced it.

**Decision:** Add a `SourceLocation` dataclass (file, start line/column, end line/column) to every `IRInstruction`. Deterministic frontends populate this from the tree-sitter AST node spans. LLM frontends emit `NO_SOURCE_LOCATION` (a sentinel) since they lack AST nodes.

**Consequences:** Debugging and tooling can map IR instructions back to source spans. Error messages reference concrete source locations. The trade-off is increased memory per instruction (one extra object) and the asymmetry between deterministic and LLM frontends.

---

### ADR-018: Standalone execute_cfg() for programmatic VM execution (2026-02-26)

**Context:** Running the VM required going through the full `run()` pipeline (parse → lower → build CFG → build registry → execute). Programmatic users who build or customise CFGs independently had no way to invoke just the execution phase.

**Decision:** Extract `execute_cfg(cfg, entry_point, registry, config) -> (VMState, ExecutionStats)` as a standalone function. It takes a pre-built CFG and registry, executes from a given entry point, and returns the final VM state and statistics.

**Consequences:** Programmatic consumers can build/modify CFGs and registries independently, then execute. Testing the VM in isolation is simpler. The trade-off is that callers must ensure the CFG and registry are consistent (matching labels, registered functions).

---

### ADR-019: Closure mutation: snapshot to shared environment cells (2026-02-26)

**Context:** The initial closure implementation (ADR-007) captured variables by snapshot. Testing revealed that patterns like counter factories (`def make_counter(): count = 0; def inc(): count += 1; return count; return inc`) returned stale values because each call re-read the snapshot.

**Decision:** Replace snapshot capture with shared `ClosureEnvironment` cells. The environment is a mutable mapping shared by all closures from the same enclosing scope. Reads and writes go through the environment, not local scope copies.

**Consequences:** Counter factories, callback registrations, and other mutation-through-closure patterns work correctly. Mutations persist across calls and are visible to sibling closures. This is a correctness fix — the snapshot approach was functionally broken for mutable closures.

---

### ADR-020: Extract dataclasses into dedicated model files (2026-02-26)

**Context:** VM, CFG, and pipeline data types (dataclasses) were defined alongside the logic that uses them. This created circular import risks and made it hard to import types without pulling in heavy modules.

**Decision:** Extract dataclasses into dedicated `*_types.py` files: `interpreter/vm_types.py`, `interpreter/cfg_types.py`, `interpreter/run_types.py`. Re-export from `__init__.py` so existing imports continue to work.

**Consequences:** Type definitions are importable without side effects. Circular imports between modules that share types are eliminated. The re-export layer maintains backwards compatibility. The trade-off is an additional layer of indirection when navigating from usage to definition.

---

### ADR-021: Two-layer IR statistics — pure counter + API wrapper (2026-02-26)

**Context:** There was no way to inspect the opcode distribution of lowered IR, useful for profiling frontend quality and comparing lowering across languages.

**Decision:** Add `count_opcodes(instructions) -> dict[str, int]` as a pure function in `interpreter/ir_stats.py`, and `ir_stats(source, language, ...) -> dict[str, int]` as an API wrapper in `interpreter/api.py` that calls `lower_source` then `count_opcodes`.

**Consequences:** The pure function is independently testable and usable by programmatic consumers who already have an instruction list. The API wrapper composes with the existing `lower_source` pipeline. No new dependencies introduced.

---

### ADR-022: Exercism integration test suite with file-based solutions and argument substitution (2026-02-28)

**Context:** The Rosetta cross-language test suite (8 algorithms x 15 languages = 464 tests) verifies frontend correctness via IR lowering and VM execution, but each algorithm is tested with only a single input. Exercism's problem-specifications repo provides 5-15 canonical test inputs per exercise, offering significantly more coverage per algorithm.

**Decision:** Integrate Exercism exercises as a second test suite (`tests/unit/exercism/`). Key design choices:
1. **Solutions as separate files** — Unlike Rosetta's inline `PROGRAMS` dict, each language solution is a separate file under `exercises/<name>/solutions/`. This avoids massive test files and makes solutions individually editable.
2. **Argument substitution via regex** — A `build_program()` helper finds the `answer = f(default_arg)` invocation line and substitutes new arguments for each canonical test case, supporting varied assignment forms (=, :=, : type =).
3. **Property-to-function mapping** — For multi-function exercises (difference-of-squares), canonical property names map to language-appropriate function names, with a `default_function_name` parameter enabling function name substitution.
4. **Reuse Rosetta conftest** — All shared helpers (`parse_for_language`, `execute_for_language`, `extract_answer`, `assert_clean_lowering`, `assert_cross_language_consistency`) are imported from the Rosetta conftest.

**Consequences:** 711 additional tests from 3 exercises across 15 languages:

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| leap | modulo, boolean logic, short-circuit eval | 9 | 15 | 2 | 270 | 287 |
| collatz-conjecture | while loop, conditional, integer division | 4 | 15 | 2 | 120 | 137 |
| difference-of-squares | while loop, accumulator, function composition | 9 | 15 | 2 | 270 | 287 |
| **Total** | | **22** | **45** | **6** | **660** | **711** |

Each exercise tests IR lowering quality, cross-language consistency, and VM execution correctness for every canonical test case. The file-based approach scales to additional exercises without growing test file size. The `exercism_harvest.py` script automates fetching new canonical data.

---

### ADR-023: String I/O support in Exercism suite — two-fer and hamming (2026-02-28)

**Context:** The first 3 Exercism exercises (leap, collatz, difference-of-squares) are numeric-only. Adding string-handling exercises broadens construct coverage to string concatenation, indexing, and character comparison.

**Decision:** Add two exercises that introduce string I/O:
1. **two-fer** — tests string concatenation (`+`, `..`, `.` depending on language) and string literal passing.
2. **hamming** — tests string indexing (`s[i]`), character comparison (`!=`), while loops, and multi-argument functions. Strand length is passed as an explicit third argument to avoid `len()` portability issues across languages.

Three VM/infrastructure prerequisites were needed:
- **Native string indexing** in `_handle_load_index` — when the resolved value is a raw Python `str` (not a heap reference) and the index is an `int`, return the character directly. Guards against false matches by checking the value is not in `vm.heap`.
- **Native call-index** in `_handle_call_function` — Scala's `s1(i)` syntax lowers to `CALL_FUNCTION` rather than `LOAD_INDEX`. When the resolved function value is a raw string (not a VM internal reference) and there's exactly one `int` argument, treat it as indexing.
- **PHP `.` concat operator** added to the VM `BINOP_TABLE`.
- **Pascal single-quote string literals** in `_format_string` for argument substitution.

**Consequences:** 274 additional tests (107 two-fer + 167 hamming), bringing Exercism total to 985 and overall to 2686. String handling is now verified end-to-end across all 15 languages with zero LLM calls.

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| leap | modulo, boolean logic, short-circuit eval | 9 | 15 | 2 | 270 | 287 |
| collatz-conjecture | while loop, conditional, integer division | 4 | 15 | 2 | 120 | 137 |
| difference-of-squares | while loop, accumulator, function composition | 9 | 15 | 2 | 270 | 287 |
| two-fer | string concatenation, string literals | 3 | 15 | 2 | 90 | 107 |
| hamming | string indexing, character comparison, while loop | 5 | 15 | 2 | 150 | 167 |
| **Total** | | **30** | **75** | **10** | **900** | **985** |

Combined with Rosetta, the full suite reaches 2686 tests.

---

### ADR-024: Expand Exercism suite with reverse-string, rna-transcription, and perfect-numbers (2026-02-28)

**Context:** The Exercism suite covered 5 exercises (985 tests) focusing on numeric logic and basic string operations (concatenation, indexing). Broader construct coverage was needed for backward iteration, character-by-character mapping with multi-branch conditionals, and string return values from numeric computations.

**Decision:** Add three exercises:
1. **reverse-string** — tests backward iteration (decrementing while loop from `n-1` to `0`), string building by character-by-character concatenation, and empty string initialization. Cases with apostrophes are filtered because Pascal's `''` escape sequence cannot round-trip through `_parse_const` (which strips outer quotes but does not un-escape inner doubled quotes).
2. **rna-transcription** — tests character comparison (`==`) with 4 separate `if` branches (avoiding language-specific `elif`/`elseif`/`elsif` syntax), forward iteration with string building, and single-character string matching.
3. **perfect-numbers** — tests divisor accumulation with modulo (`%`), three-way string return (`"perfect"`, `"abundant"`, `"deficient"`), and is the first exercise returning string values from a purely numeric computation. Cases with inputs > 10000 are filtered to keep VM execution tractable.

No VM prerequisites were needed — all required features (string indexing, string concat, string return, `_parse_const` string literal handling) were already in place from ADR-023.

**Consequences:** 651 additional tests (167 reverse-string + 197 rna-transcription + 287 perfect-numbers), bringing Exercism total to 1636 and overall to 3337. Unicode cases (wide chars, grapheme clusters) in reverse-string are filtered as they require grapheme-aware reversal beyond the VM's scope.

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| leap | modulo, boolean logic, short-circuit eval | 9 | 15 | 2 | 270 | 287 |
| collatz-conjecture | while loop, conditional, integer division | 4 | 15 | 2 | 120 | 137 |
| difference-of-squares | while loop, accumulator, function composition | 9 | 15 | 2 | 270 | 287 |
| two-fer | string concatenation, string literals | 3 | 15 | 2 | 90 | 107 |
| hamming | string indexing, character comparison, while loop | 5 | 15 | 2 | 150 | 167 |
| reverse-string | backward iteration, string building char-by-char | 5 | 15 | 2 | 150 | 167 |
| rna-transcription | character comparison, multi-branch if, char mapping | 6 | 15 | 2 | 180 | 197 |
| perfect-numbers | divisor loop, modulo, accumulator, three-way string return | 9 | 15 | 2 | 270 | 287 |
| **Total** | | **50** | **120** | **16** | **1500** | **1636** |

Combined with Rosetta, the full suite reaches 3337 tests.

---

### ADR-025: Exercism expansion — triangle and space-age (2026-02-28)

**Context:** The Exercism suite covered 8 exercises (1636 tests) focusing on numeric logic, string operations, and basic conditionals. Broader construct coverage was needed for compound boolean logic via nested ifs, validity guard clauses, 3-argument functions, floating-point division, float literal constants, and string-to-number mapping.

**Decision:** Add two exercises:
1. **triangle** — tests compound boolean logic using nested `if` statements (avoiding `and`/`&&` keywords), validity guard clauses (triangle inequality: `a + b <= c`, `b + c <= a`, `a + c <= b`), three separate functions per solution (`isEquilateral`, `isIsosceles`, `isScalene`), 3-argument functions returning boolean-as-integer (1/0), and floating-point side values. All 21 canonical cases are included. Uses the multi-property pattern from difference-of-squares.
2. **space-age** — tests floating-point division, float literal constants (orbital period ratios), string equality comparison in an if-chain mapping planet names to ratios, and mixed string+integer arguments returning a float result. The error case (`"Sun"`) is auto-filtered by `load_canonical_cases`. Float comparison uses tolerance of 0.01. Adding this exercise uncovered that the Ruby frontend was missing a dispatch entry for `parenthesized_statements` (Ruby's tree-sitter grammar uses this node type instead of `parenthesized_expression`); this was fixed by adding the mapping to `_lower_paren` in `RubyFrontend`.

No VM prerequisites were needed — floats, division, string comparison, and boolean returns were already in place.

**Consequences:** 904 additional tests (647 triangle + 257 space-age), bringing Exercism total to 2540 (plus 1 xfail) and overall to 4242 (plus 3 xfailed).

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| leap | modulo, boolean logic, short-circuit eval | 9 | 15 | 2 | 270 | 287 |
| collatz-conjecture | while loop, conditional, integer division | 4 | 15 | 2 | 120 | 137 |
| difference-of-squares | while loop, accumulator, function composition | 9 | 15 | 2 | 270 | 287 |
| two-fer | string concatenation, string literals | 3 | 15 | 2 | 90 | 107 |
| hamming | string indexing, character comparison, while loop | 5 | 15 | 2 | 150 | 167 |
| reverse-string | backward iteration, string building char-by-char | 5 | 15 | 2 | 150 | 167 |
| rna-transcription | character comparison, multi-branch if, char mapping | 6 | 15 | 2 | 180 | 197 |
| perfect-numbers | divisor loop, modulo, accumulator, three-way string return | 9 | 15 | 2 | 270 | 287 |
| triangle | nested ifs, validity guards, 3-arg functions, float sides, multi-property | 21 | 15 | 2 | 630 | 647 |
| space-age | float division, float constants, string-to-number mapping | 8 | 15 | 2 | 240 | 257 |
| **Total** | | **79** | **150** | **20** | **2370** | **2540** |

Combined with Rosetta, the full suite reaches 4242 tests.

---

### ADR-026: Exercism expansion — grains, isogram, nth-prime, resistor-color + Rust expression-position loops (2026-02-28)

**Context:** The Exercism suite covered 10 exercises (2540 tests). Broader construct coverage was needed for exponentiation via loops, large integer arithmetic (2^63), zero-argument function calls, nested while loops with continue, case-insensitive character comparison via helper functions, trial division primality testing, and string-to-integer if-chain mapping. During implementation, a Rust frontend gap was discovered: `while_expression`, `loop_expression`, `for_expression`, `continue_expression`, and `break_expression` appeared only in `_STMT_DISPATCH` but not in `_EXPR_DISPATCH`, causing `SYMBOLIC unsupported` when these constructs appeared in expression position (e.g., as the last expression in an `if` body block, which `_lower_block_expr` treats as an expression).

**Decision:** Add four exercises:
- **grains** (8 cases) — multi-property (`square`/`total`) with 2 functions per solution. Tests exponentiation via repeated multiplication, large integers (square(64) = 2^63), and zero-argument function calls (`total()`).
- **isogram** (14 cases) — boolean 1/0 return. Uses a `toLowerChar` helper with 26 if-statements for case-insensitive comparison. Tests nested while loops, `continue` in inner/outer loops, function composition, string indexing, and character equality.
- **nth-prime** (3 cases, filtered from 5 — 10001st prime skipped for step count) — trial division with nested loops. Tests primality checking, conditional increment, and counting loops.
- **resistor-color** (3 cases, colorCode property only — colors returns array, unsupported) — if-chain mapping 10 color names to codes 0-9.

Additionally, fix the Rust frontend to register loop/break/continue node types in `_EXPR_DISPATCH` alongside their existing `_STMT_DISPATCH` entries. The expression-position handlers lower the construct as a statement, then return a unit-valued register (`NONE_LITERAL`).

**Consequences:** 908 additional tests (257 grains + 437 isogram + 107 nth-prime + 107 resistor-color), bringing Exercism total to 3448 and overall to 5150 (plus 3 xfailed). The Rust frontend fix is not specific to isogram — it enables any Rust program that uses loops in expression position (e.g., `let x = while ... { ... };`), improving general Rust coverage.

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| grains | exponentiation, large integers, zero-arg calls | 8 | 15 | 2 | 240 | 257 |
| isogram | nested while, continue, toLowerChar helper | 14 | 15 | 2 | 420 | 437 |
| nth-prime | trial division, nested loops, primality | 3 | 15 | 2 | 90 | 107 |
| resistor-color | string-to-int if-chain, string equality | 3 | 15 | 2 | 90 | 107 |
| **New total** | | **28** | **60** | **8** | **840** | **908** |

Combined with previous exercises and Rosetta, the full suite reaches 5150 tests.

---

### ADR-027: Exercism expansion — pangram, bob, luhn, acronym (2026-02-28)

**Context:** The Exercism suite covered 14 exercises (3448 tests, 5150 total). Further construct coverage was needed for: string variable indexing (using local string variables as lookup tables), two-pass string validation with right-to-left traversal, multi-branch string classification, word boundary detection, and `toUpperChar`/`charToDigit` helper patterns.

**Decision:** Add four exercises:
- **pangram** (11 cases) — boolean 1/0 return. Uses `toLowerChar` helper + nested loops: outer loop over 26 letters in a local `"abcdefghijklmnopqrstuvwxyz"` string, inner loop scanning the sentence. Early exit via `si = n` when letter found to reduce VM step count. Tests string variable indexing, nested loops, and case-insensitive comparison.
- **bob** (22 cases, filtered from 26 — 4 cases with tab/newline/carriage return removed since VM cannot represent escape sequences in string literals) — string return. Uses `isUpperChar` and `isLowerChar` helpers (26 if-statements each returning 1/0). Classifies input as silence, yelling question, yelling, question, or default. Pascal excluded from execution tests due to apostrophe in response "Calm down, I know what I'm doing!" triggering ADR-024 limitation.
- **luhn** (22 cases) — boolean 1/0 return. Uses `charToDigit` helper (10 if-statements mapping digit characters to integers, -1 for non-digits). Two-pass algorithm: first pass validates characters and counts digits, second pass computes Luhn checksum right-to-left with every-other-digit doubling. Tests modulo arithmetic, right-to-left iteration, conditional doubling.
- **acronym** (9 cases) — string return. Uses `toUpperChar` helper (26 if-statements mapping lowercase to uppercase). Detects word boundaries (space, hyphen, underscore are separators; apostrophe, comma, period are NOT). Pascal excluded from execution tests due to apostrophe in "Halley's Comet" input (ADR-024).

**Consequences:** 1926 additional tests (347 pangram + 633 bob + 677 luhn + 269 acronym), bringing Exercism total to 5374 and overall to 7076 (plus 3 xfailed). Two exercises (bob, acronym) exclude Pascal from execution tests, but Pascal lowering and cross-language consistency tests still run for all 15 languages.

| Exercise | Constructs tested | Cases | Lowering | Cross-lang | Execution | Total |
|----------|-------------------|-------|----------|------------|-----------|-------|
| pangram | toLowerChar, string indexing, nested loops | 11 | 15 | 2 | 330 | 347 |
| bob | isUpperChar/isLowerChar, string classification | 22 | 15 | 2 | 616 | 633 |
| luhn | charToDigit, two-pass validation, modulo | 22 | 15 | 2 | 660 | 677 |
| acronym | toUpperChar, word boundary, string building | 9 | 15 | 2 | 252 | 269 |
| **New total** | | **64** | **60** | **8** | **1858** | **1926** |

Combined with previous exercises and Rosetta, the full suite reaches 7076 tests.

---

### ADR-028: Configurable LLM plausible-value resolver for unresolved function calls (2026-02-28)

**Context:** When the VM encounters a call to an unresolved function (e.g., `math.sqrt(16)` where `math` is an unresolved import), it creates a `SymbolicValue` placeholder. This symbolic value propagates through all subsequent computation — `sym_N + 1 → sym_M` — causing "precision death" where concrete values degrade into entirely symbolic expressions. For programs with many stdlib calls, this makes the execution trace uninformative.

**Decision:** Introduce a ports-and-adapters `UnresolvedCallResolver` ABC with two implementations:

1. **`SymbolicResolver`** — extracts the existing `_symbolic_call_result`/`_symbolic_method_result` logic into a proper class (default, preserves current behavior)
2. **`LLMPlausibleResolver`** — makes a lightweight LLM call with a focused prompt to get plausible concrete return values, with support for side effects via `heap_writes`/`var_writes` in the response

The resolver is injected through the existing `**kwargs` chain: `VMConfig → execute_cfg → _try_execute_locally → LocalExecutor.execute → handler`. An `UnresolvedCallStrategy` enum (`SYMBOLIC` | `LLM`) on `VMConfig` controls which resolver is instantiated.

Side effects use the existing `StateUpdate` format (heap_writes/var_writes) rather than generating IR — the LLM already speaks this mutation language, and `apply_update()` handles it natively.

**Consequences:**
- Default behavior unchanged (symbolic strategy)
- LLM mode eliminates precision death for stdlib calls — e.g., `math.sqrt(16) → 4.0`, `4.0 + 1 = 5.0` computed locally
- Fallback to symbolic on LLM failure (network errors, invalid JSON)
- 17 new unit tests covering both resolvers, side effects, fallback, and prompt construction

---

### ADR-029: COBOL support via ProLeap parser bridge, byte-addressed memory regions, and language-agnostic IR extensions (2026-03-02)

**Context:** RedDragon supports 15 languages via tree-sitter deterministic frontends and any language via LLM frontends. Adding COBOL support for reverse engineering legacy code requires:
1. A proper COBOL parser (tree-sitter's COBOL grammar is insufficient for production COBOL)
2. Modelling COBOL's byte-level memory layout (PIC clauses, REDEFINES, COMP-3 packed decimal, zoned decimal, EBCDIC encoding)
3. Modelling COBOL's paragraph-based control flow (PERFORM, SECTION/PARAGRAPH, not function-based)

The existing IR has no concept of byte-addressed memory — `LOAD_FIELD`/`STORE_FIELD` are name-based and each field is independent. COBOL's REDEFINES means two data items alias the same bytes, so writing through one field must be visible when reading through another. The smojol project (`~/code/smojol`) already implements a full COBOL byte-level memory model in Java with `MemoryRegion`, `RangeMemoryAccess`, `DataTypeSpec` subclasses (zoned decimal, COMP-3, alphanumeric), and REDEFINES-as-overlapping-views.

**Decision:** A multi-part design spanning the Java bridge, IR extensions, VM extensions, COBOL type system, and COBOL frontend.

#### Part 1: ProLeap parser bridge (Java subprocess)

Use [proleap-cobol-parser](https://github.com/uwol/proleap-cobol-parser) (ANTLR4-based, JDK 17, Maven) via a subprocess bridge. A thin Java CLI (`proleap-bridge`) wraps ProLeap and serialises **both** the AST (syntax tree) and ASG (Abstract Semantic Graph) to JSON on stdout. The ASG provides resolved PERFORM targets, data item hierarchies, REDEFINES chains, variable references, PIC clauses, and EXEC SQL/CICS/SQLIMS nodes.

The Python side defines an abstract `CobolParser` port with a `ProLeapCobolParser` adapter that invokes the subprocess and parses the JSON output. This follows the existing ports-and-adapters pattern (cf. `ParserFactory` for tree-sitter, `LLMClient` for LLM providers).

```
CobolParser (ABC)                    ← Python port
    ↑
ProLeapCobolParser                   ← adapter: subprocess → JSON → Python dicts
    ↓
proleap-bridge.jar                   ← thin Java CLI wrapper
    ↓
ProLeap COBOL Parser (Java library)  ← ANTLR4 grammar, AST + ASG
```

#### Part 2: Language-agnostic byte-addressed memory (3 new IR opcodes)

Add three new opcodes to the IR that provide raw byte-addressed memory operations. These are **language-agnostic** — not COBOL-specific. A C frontend could use them for `struct` layouts; a binary protocol parser could use them for packet fields.

| Opcode | Operands | Description |
|--------|----------|-------------|
| `ALLOC_REGION` | `size` (literal) | Allocate a zeroed byte region of `size` bytes, return region address |
| `WRITE_REGION` | `region_reg`, `offset_reg`, `length` (literal), `value_reg` | Write `value_reg` bytes into region at byte offset |
| `LOAD_REGION` | `region_reg`, `offset_reg`, `length` (literal) | Read bytes from region at byte offset, return as value |

Key design choices:
- **Offset is a register** (can be computed at runtime for OCCURS/table indexing via BINOP arithmetic)
- **Length is a literal** (known from PIC clause at compile time)
- **No encoding/decoding in the VM** — the VM moves raw bytes. Type-aware encoding (zoned decimal, COMP-3, alphanumeric, EBCDIC) is performed by **synthetic IR functions** emitted by the COBOL frontend. The VM never knows about COBOL data types.

The VM adds a `regions: dict[str, bytearray]` store alongside the existing `heap: dict[str, HeapObject]`. Region addresses use a `"rgn_"` prefix to distinguish from heap addresses.

#### Part 3: COBOL type encoding/decoding as pure IR functions

The COBOL frontend emits encoding/decoding as **pure IR functions** composed from primitive builtins and standard IR opcodes (arithmetic, `CALL_FUNCTION`, `RETURN`). These functions are NOT native Python builtins — they are generated IR instruction sequences. Python reference implementations in `interpreter/cobol/` serve as ground-truth for validation and are used by `ir_encoders.py` builders to emit equivalent IR.

| IR function builder | Reference impl | Purpose |
|---|---|---|
| `build_encode_alphanumeric_ir()` | `alphanumeric.encode_alphanumeric()` | String → EBCDIC bytes, right-padded |
| `build_decode_alphanumeric_ir()` | `alphanumeric.decode_alphanumeric()` | EBCDIC bytes → string |
| `build_encode_zoned_ir()` | `zoned_decimal.encode_zoned()` | Digit list → zoned decimal bytes (sign nibble) |
| `build_decode_zoned_ir()` | `zoned_decimal.decode_zoned()` | Zoned decimal bytes → number |
| `build_encode_comp3_ir()` | `comp3.encode_comp3()` | Digit list → packed BCD bytes (sign nibble) |
| `build_decode_comp3_ir()` | `comp3.decode_comp3()` | Packed BCD bytes → number |

IR functions are specialized for compile-time-known PIC parameters (total_digits, decimal_digits) — matching how COBOL compilers work. The generated IR is straight-line code with unrolled loops (digit counts are always compile-time constants from PIC clauses).

Only **~12 primitive byte-manipulation builtins** are registered as native Python in `Builtins.TABLE`. These are the atoms from which all encoding/decoding IR is composed:

| Builtin | Signature | Purpose |
|---|---|---|
| `__nibble_get` | `(byte_val, position)` | Extract high/low nibble from a byte |
| `__nibble_set` | `(byte_val, position, nibble)` | Set high/low nibble, return new byte |
| `__byte_from_int` | `(value)` | Clamp/mask integer to 0-255 |
| `__int_from_byte` | `(byte_val)` | Identity (semantic clarity in IR) |
| `__bytes_to_string` | `(byte_list, encoding)` | Decode byte list to string ("ascii"/"ebcdic") |
| `__string_to_bytes` | `(string, encoding)` | Encode string to byte list ("ascii"/"ebcdic") |
| `__list_get` | `(lst, index)` | Get element at index |
| `__list_set` | `(lst, index, value)` | Return new list with element replaced |
| `__list_len` | `(lst)` | Return list length |
| `__list_slice` | `(lst, start, end)` | Return sublist [start:end] |
| `__list_concat` | `(lst1, lst2)` | Concatenate two lists |
| `__make_list` | `(size, fill)` | Create list of `size` elements, all set to `fill` |

The `__bytes_to_string`/`__string_to_bytes` builtins handle EBCDIC encoding internally (using the ported `ByteConverter` lookup tables) when `encoding="ebcdic"`. The EBCDIC table is an implementation detail, not exposed as a builtin.

#### Part 4: COBOL-specific lowering

The COBOL frontend (`CobolFrontend`, a direct `Frontend` subclass — not `BaseFrontend`) consumes the ProLeap ASG and lowers COBOL constructs as follows:

**DATA DIVISION:**
- Each `01`-level record → `ALLOC_REGION` with total byte size computed from PIC clauses
- Each elementary item → a (region, offset, length, encoding) tuple tracked at lowering time
- REDEFINES → no special handling; the redefined item shares the same region and overlapping (offset, length) range. Writing through one field and reading through another **just works** because they address the same bytes.
- OCCURS → repeated items at computed offsets; variable indexing uses BINOP to compute `(index - 1) * element_size`
- 88-level conditions → lowered as `LOAD_REGION` + `BINOP ==` comparisons against permitted values

**PROCEDURE DIVISION (Strategy 2 — paragraphs as inline blocks):**
- Each paragraph/section → `LABEL paragraph_name` ... instructions ... `LABEL end_paragraph_name`
- `PERFORM X` → `BRANCH X` + (at end of X) `BRANCH return_point`. This preserves COBOL's flat control flow model with goto-with-return semantics.
- `PERFORM X THRU Y` → same, but covers the range of paragraphs from X to Y
- `PERFORM VARYING` → C-style for loop pattern (init → condition → body → update → branch back)
- `EVALUATE` → if/else chain (same pattern as JavaScript `switch`)
- `IF/ELSE` → standard `BRANCH_IF` pattern

**MOVE/COMPUTE/arithmetic:**
- `MOVE X TO Y` → `LOAD_REGION` (decode X) + `CALL_FUNCTION __cobol_encode_<type>` + `WRITE_REGION` (to Y's offset)
- `COMPUTE X = expr` → lower expression to BINOP chain + encode + write
- `ADD X TO Y` → `LOAD_REGION` both + `BINOP +` + encode + `WRITE_REGION`
- Group MOVE → `LOAD_REGION` raw bytes from source group + `WRITE_REGION` to target group (same byte count, raw copy)

**EXEC SQL/CICS/SQLIMS:**
- ProLeap's ASG has dedicated metamodel packages (`execsql/`, `execcics/`, `execsqlims/`) for these
- Lowered as `SYMBOLIC "EXEC_SQL:<sql_text>"` with host variable references extracted from the ASG and emitted as `LOAD_REGION` before the SYMBOLIC instruction, establishing def-use chains from COBOL variables into the SQL statement

#### Part 5: Testing strategy

**Phase 1 — Type system (no parser dependency):**
Test the COBOL encoding/decoding logic independently, ported from smojol's test suite and extended:

| smojol test file | Tests to port | Coverage |
|---|---|---|
| `DataTypesTest.java` | 30+ tests | Zoned decimal (signed/unsigned), COMP-3 (read/write/arithmetic), alphanumeric (padding/truncation), decimal alignment, sign handling, table indexing, overflow, zero handling, empty string defaults |
| `DataTypeRedefinitionsTest.java` | 2+ tests | REDEFINES as overlapping byte views (read numeric as alpha, read through smaller alias) |
| `DataLayoutBuilderTest.java` | 6 tests | PIC string parsing (simple/complex alphanumeric, numeric with repetition, signed) |
| `DataTypeParserTest.java` | 3 tests | ANTLR PIC clause parsing for numeric/alphanumeric formats |

Additional RedDragon-specific tests:
- Encoding/decoding round-trips for all type combinations
- REDEFINES with 3+ overlapping views
- Nested REDEFINES (A REDEFINES B, C REDEFINES B)
- OCCURS with variable index computation
- Group MOVE across differently-structured records
- EBCDIC ↔ ASCII conversion tables (full 256-byte verification)
- Symbolic value propagation through `ALLOC_REGION`/`WRITE_REGION`/`LOAD_REGION`
- Byte-level builtins (nibble get/set, byte↔int, string↔bytes)

**Phase 2 — IR opcodes and VM:**
Test `ALLOC_REGION`, `WRITE_REGION`, `LOAD_REGION` at the VM level with hand-crafted IR. No COBOL frontend needed — just raw byte operations verified against expected byte patterns.

**Phase 3 — COBOL frontend lowering:**
Test the full pipeline: COBOL source → ProLeap bridge → ASG → IR → CFG → execution. Uses the ProLeap bridge subprocess.

**Consequences:**

Benefits:
- Full COBOL support including REDEFINES, COMP-3, zoned decimal, EBCDIC, OCCURS, 88-levels, EXEC SQL/CICS
- Byte-addressed memory is language-agnostic — reusable for C structs, binary protocols, etc.
- No COBOL-specific code in the VM — all encoding/decoding logic is in the IR as synthetic functions
- REDEFINES falls out for free from byte-addressed memory (overlapping offset/length ranges on the same region)
- Dataflow analysis works unchanged — `WRITE_REGION`/`LOAD_REGION` define and use registers like any other instruction
- Smojol's battle-tested type encoding logic is ported with its test cases as a baseline

Trade-offs:
- JDK 17 required at runtime for the ProLeap bridge subprocess
- JVM startup latency (~1-2s per parse invocation); acceptable for analysis workloads, upgradeable to a persistent process later
- More verbose IR per data access (every field read/write has an encoding/decoding function call wrapped around it)
- Byte-level builtins (nibble manipulation, EBCDIC tables) add ~14 new entries to the builtins table
- COBOL paragraphs as inline blocks (Strategy 2) produces larger CFGs than the function-based alternative, but preserves COBOL's actual execution model

#### Part 6: Phase 2 Implementation — Python-side COBOL Frontend (2026-03-02)

Phase 2 implemented the COBOL frontend that consumes ProLeap JSON ASG and lowers it to RedDragon IR.

**JSON ASG Contract** (`interpreter/cobol/asg_types.py`):
Frozen dataclasses with `from_dict`/`to_dict` round-trip serialization:
- `CobolField` — DATA DIVISION items (level, PIC, USAGE, offset, VALUE, REDEFINES, children)
- `CobolStatement` — PROCEDURE DIVISION statements (type, operands, children, condition)
- `CobolParagraph`, `CobolSection` — structural containers
- `CobolASG` — top-level ASG (data_fields, sections, paragraphs)

**PIC Clause Parser** (`interpreter/cobol/pic_parser.py`):
ANTLR4-based parser ported from smojol's `CobolDataTypes.g4`/`CobolDataTypesLexer.g4`:
- `parse_pic(pic, usage) -> CobolTypeDescriptor` — parses PIC strings like `S9(5)V99`, `X(8)`
- ANTLR visitor walks the parse tree to extract sign, integer digits, decimal digits, alphanumeric length
- `usage` parameter overrides category: `"COMP-3"` → `COMP3`, `"DISPLAY"` → `ZONED_DECIMAL`
- Grammar `superClass` option and `@lexer::members` block removed for Python compatibility

**Data Layout Builder** (`interpreter/cobol/data_layout.py`):
Pure function `build_data_layout(fields) -> DataLayout`:
- Recursively flattens `CobolField` trees into `FieldLayout` maps
- Computes byte lengths via `parse_pic` + `CobolTypeDescriptor.byte_length`
- REDEFINES fields share offsets and do NOT increase parent group size

**CobolFrontend** (`interpreter/cobol/cobol_frontend.py`):
Direct `Frontend` subclass (not `BaseFrontend`), implementing `lower(tree, source) -> list[IRInstruction]`:
- **Data Division lowering:** `ALLOC_REGION` for total record size, encode initial VALUE clauses via inline IR
- **Procedure Division lowering:** Statement-by-statement dispatch for MOVE, ADD, SUBTRACT, MULTIPLY, DIVIDE, IF, PERFORM, DISPLAY, STOP_RUN, GOTO, EVALUATE
- **Inline IR:** Encoding/decoding IR from `ir_encoders.py` is inlined (not called as functions) — register mapping handles parameter passing
- **Condition lowering:** Simple pattern matching on "field OP value" strings from the ASG
- Two new builtins (`__cobol_prepare_digits`, `__cobol_prepare_sign`) handle runtime string-to-digits conversion for MOVE targets

**Subprocess Bridge** (`interpreter/cobol/cobol_parser.py`, `subprocess_runner.py`):
- `CobolParser` ABC, `ProLeapCobolParser` adapter (subprocess → JSON → `CobolASG`)
- `SubprocessRunner` ABC, `RealSubprocessRunner` (production), testable via DI
- Bridge JAR path configurable via `PROLEAP_BRIDGE_JAR` environment variable

**Integration:** Added `FRONTEND_COBOL` constant and `"cobol"` branch in `get_frontend()` and `run()`.

**Testing:** 65 new unit tests covering ASG round-trip, PIC parsing (16 cases), data layout (8 cases), frontend lowering (16 cases), parser bridge (5 cases), and end-to-end fixture tests (9 cases). All 7502 tests pass.

---

### ADR-030: COBOL PERFORM semantics via named continuations (2026-03-02)

**Context:** COBOL's `PERFORM X` transfers control to paragraph X and implicitly returns when execution reaches the end of that paragraph. `PERFORM X THRU Y` executes paragraphs X through Y by fall-through and returns after Y completes. The prior implementation (ADR-029) emitted a bare `BRANCH` with no return mechanism — execution would branch to the target paragraph but never return to the caller.

Three design alternatives were considered:

- **A1: Call stack** — Use `CALL_FUNCTION`/`RETURN` to model PERFORM as a function call. Rejected because COBOL paragraphs are not functions: overlapping PERFORM ranges, fall-through between paragraphs, and PERFORM THRU semantics don't fit a strict call/return model.
- **A2: Inline duplication** — Copy paragraph body at every PERFORM site. Rejected because it duplicates code, breaks shared labels, and doesn't handle PERFORM THRU or overlapping ranges.
- **A3: Named continuations** — Add two generic VM opcodes that implement a named continuation table. The COBOL frontend uses these to faithfully emulate PERFORM return semantics.

**Decision:** Adopt A3 — named continuations via two new opcodes:

| Opcode | Operands | Semantics |
|--------|----------|-----------|
| `SET_CONTINUATION` | `[name, label]` | Write `name → label` into the continuation table. Overwrites any existing entry (last-writer-wins). |
| `RESUME_CONTINUATION` | `[name]` | If `name` is set: branch to its label and clear the entry. If not set: no-op (fall through). |

**COBOL frontend lowering:**

Every paragraph emits `RESUME_CONTINUATION("para_{name}_end")` at its boundary. This is a no-op during sequential execution (the name is not set). When a PERFORM targets this paragraph, the caller first sets the continuation, then branches:

```
SET_CONTINUATION ["para_X_end", "perform_return_N"]
BRANCH para_X
LABEL perform_return_N
```

For `PERFORM X THRU Y`, the continuation is keyed to Y's end — intermediate paragraphs' `RESUME_CONTINUATION` calls are no-ops since the name doesn't match.

**CFG treatment:** `RESUME_CONTINUATION` is a block terminator (it may branch dynamically). The CFG builder emits a fall-through edge only — the branch target is dynamic and cannot be statically resolved. `SET_CONTINUATION` is a regular (non-terminating) instruction.

**Consequences:**

Benefits:
- Faithful COBOL PERFORM semantics including PERFORM THRU, overlapping ranges, and last-writer-wins for degenerate cases
- Language-agnostic opcodes — reusable for any language with similar "perform and return" control flow (e.g., Fortran computed GO TO, PL/I ON-units)
- No changes to the call stack — paragraphs remain inline code, not functions
- PERFORM THRU falls out naturally from keying the continuation to the THRU endpoint

Trade-offs:
- Dynamic branch targets in RESUME_CONTINUATION mean the CFG cannot statically wire return edges — static analysis sees only the fall-through path. Future work can trace SET_CONTINUATION instructions to wire additional edges.
- The continuation table adds a small state footprint to the VM (one dict entry per active PERFORM)

---

### ADR-031: Typed COBOL statement hierarchy, PERFORM loop variants, and section-level PERFORM (2026-03-02)

**Context:** The `CobolStatement` class was a flat bag of optional fields (`operands`, `children`, `condition`, `thru`) shared across 10+ statement types. The Java bridge discarded `PerformType` information entirely, so PERFORM TIMES, UNTIL, and VARYING loops were silently dropped. Section-level PERFORM (where the target is a section containing multiple paragraphs) was also unsupported.

**Decision:**

1. **Typed statement hierarchy:** Replace `CobolStatement` with a discriminated union of frozen dataclasses (`MoveStatement`, `ArithmeticStatement`, `IfStatement`, `PerformStatement`, `DisplayStatement`, `GotoStatement`, `StopRunStatement`, `EvaluateStatement`, `WhenStatement`, `WhenOtherStatement`). Each type carries only its specific fields. A `parse_statement(dict)` function dispatches on the `type` discriminator.

2. **PERFORM specs:** Three frozen dataclasses — `PerformTimesSpec`, `PerformUntilSpec`, `PerformVaryingSpec` — carried as an optional `spec` field on `PerformStatement`.

3. **Java bridge PerformType serialization:** `serializePerformType()` extracts `PerformType` from both `PerformProcedureStatement` and `PerformInlineStatement`, emitting `perform_type`, `times`, `until`, `varying_var`, `varying_from`, `varying_by`, `test_before` JSON fields.

4. **Loop lowering:** All three loop patterns compose from existing opcodes (no new VM opcodes):
   - TIMES: `STORE_VAR` counter + `LOAD_VAR`/`BINOP >=`/`BRANCH_IF` loop
   - UNTIL: condition `BRANCH_IF` loop (TEST BEFORE: check-then-body; TEST AFTER: body-then-check)
   - VARYING: field init + condition loop + `BINOP +` increment + encode-back

5. **Section-level PERFORM:** Frontend builds a `_section_paragraphs` lookup. When PERFORM target matches a section name, it branches to `section_X` and sets continuation at `section_X_end`. Sections emit `RESUME_CONTINUATION("section_X_end")` after their last paragraph.

**Consequences:**

Benefits:
- Type safety: field access is checked at the type level (`stmt.source` vs `stmt.operands[0]`)
- No new VM opcodes — loops compose from STORE_VAR/LOAD_VAR/BINOP/BRANCH_IF
- Section PERFORM and paragraph PERFORM share the same continuation mechanism
- Java bridge now preserves full PerformType information

Trade-offs:
- Existing code constructing `CobolStatement` directly must migrate to the new types
- `isinstance` dispatch in `_lower_statement` is slightly more verbose than dict dispatch

---

### ADR-032: COMPUTE statement support with recursive-descent expression parser (2026-03-02)

**Context:** The COBOL `COMPUTE` statement assigns the result of an arbitrary arithmetic expression to one or more target variables (e.g., `COMPUTE WS-RESULT = WS-A + WS-B * 2`). Unlike simple arithmetic statements (ADD, SUBTRACT, etc.) which operate on two operands, COMPUTE requires parsing and evaluating full arithmetic expressions with operator precedence and parentheses.

**Decision:** Implement COMPUTE end-to-end across all three pipeline layers:

1. **Bridge** (`StatementSerializer.java`): Extract the expression with original source spacing preserved (using ANTLR `getInputStream().getText(Interval)` instead of `getText()`) to disambiguate COBOL hyphenated identifiers (e.g., `WS-A`) from subtraction. Emit structured JSON: `{"type": "COMPUTE", "expression": "WS-A + WS-B * 2", "targets": ["WS-RESULT"]}`.

2. **Expression parser** (`cobol_expression.py`): Recursive-descent parser with frozen dataclass expression tree nodes (`LiteralNode`, `FieldRefNode`, `BinOpNode`). Standard two-level precedence: additive (`+`, `-`) and multiplicative (`*`, `/`), with parentheses. Regex tokenizer handles COBOL identifiers with hyphens, decimal literals, operators, and parentheses. All functions are pure (no mutation).

3. **Frontend lowering** (`cobol_frontend.py`): Tree-walk the expression AST emitting IR — `LOAD_REGION` + decode for field references, `CONST` for literals, `BINOP` for operators. Result is converted to string and encoded/written to each target field via `_emit_encode_from_string`.

**Alternatives considered:**
- Parsing expression text without bridge changes (splitting on whitespace) — rejected because `getText()` strips spaces, making `WS-A+WS-B` ambiguous (identifier vs subtraction)
- Emitting a structured expression tree from the bridge — more complex Java changes for marginal benefit; space-preserved text is sufficient for the recursive-descent parser
- Reusing ArithmeticStatement for COMPUTE — rejected because COMPUTE has fundamentally different structure (expression string + multiple targets vs. single source + single target)

Benefits:
- Correct operator precedence and parenthesis handling
- Multiple target assignment support (`COMPUTE A B = expr`)
- Expression parser is independently testable (18 unit tests)
- Closes the last DISPATCH_MISSING gap — all 12 bridge-serialised types now fully handled

---

### ADR-033: COBOL Tier 1 + Tier 2 statement expansion — CONTINUE, EXIT, INITIALIZE, SET, STRING, UNSTRING, INSPECT (2026-03-02)

**Context:** The COBOL frontend audit showed 12/51 statement types HANDLED and 39 BRIDGE_UNKNOWN. To increase coverage toward production COBOL programs, we prioritised two tiers: Tier 1 (quick-win no-ops and simple assignment) and Tier 2 (high-value string operations found in most production COBOL).

**Decision:** Implement 7 new statement types across the three-layer pipeline (bridge → dataclass → lowering):

**Tier 1 — Quick Wins:**
1. **CONTINUE** — no-op sentinel, emits nothing in IR
2. **EXIT** — no-op paragraph-end sentinel, emits nothing in IR
3. **INITIALIZE** — resets fields to type-appropriate defaults (SPACES for alphanumeric, ZEROS for numeric) using existing `_emit_field_encode` infrastructure
4. **SET** — two forms: TO (assign value) and BY (UP/DOWN increment/decrement), reusing arithmetic patterns from ADD/SUBTRACT

**Tier 2 — String Operations:**
5. **STRING** — concatenates delimited sending fields into a target; uses `__string_split` + `__list_get` for delimiter truncation, `__string_concat` for assembly
6. **UNSTRING** — splits a source field by delimiter and distributes parts to target fields; uses `__string_split` IR builder
7. **INSPECT** — two sub-forms: TALLYING (counts pattern occurrences via `__string_count`) and REPLACING (substitutes patterns via `__string_replace`)

**String operation architecture:** Added 5 new low-level builtins to `byte_builtins.py` (`__string_find`, `__string_split`, `__string_count`, `__string_replace`, `__string_concat`) and 4 IR instruction builders to `ir_encoders.py`. The builtins are atomic operations that produce SYMBOLIC values for symbolic inputs (same pattern as all existing builtins). The IR builders compose builtins into `list[IRInstruction]` for inline expansion at lowering sites.

**Alternatives considered:**
- Implementing string ops as single CALL_FUNCTION instructions — rejected because multi-step operations (decode → process → encode) need to be visible to data-flow analysis as separate IR instructions
- Skipping INSPECT REPLACING write-back — rejected because COBOL INSPECT modifies the source field in-place

**Consequences:** Coverage increased from 12/51 to 19/51 HANDLED (37%), with 0 DISPATCH_MISSING. The string builtins are reusable for future string-related statements. Test count increased from 7608 to 7639 (31 new tests).

### ADR-034: COBOL SEARCH statement — linear table search with loop-based IR lowering (2026-03-02)

**Context:** SEARCH is a table lookup statement unique to COBOL. It iterates through a table (defined with OCCURS) using a VARYING index, testing WHEN conditions at each iteration, with an optional AT END clause for exhaustion. It does not require external I/O and is commonly found in production COBOL programs.

**Decision:** Implement SEARCH across all three pipeline layers:

1. **Bridge** (`serializeSearch`) — extracts table name, varying index, WHEN phrases (condition + child statements), and AT END phrases from ProLeap's `SearchStatement` ASG node
2. **Dataclass** (`SearchStatement` + `SearchWhen`) — frozen dataclasses with recursive child statement parsing
3. **Lowering** (`_lower_search`) — emits a counter-based loop with:
   - Safety-bound counter (max 256 iterations) to prevent infinite loops in concrete execution
   - WHEN condition chain: each WHEN is a `BRANCH_IF` — if true, execute body and jump to end; if false, fall through to next WHEN
   - Index increment: if VARYING is specified, decode → increment → encode → write back
   - AT END clause: executed when the bound is reached

**Alternatives considered:**
- Unbounded loop relying on table-size metadata — rejected because the SEARCH statement alone doesn't carry the OCCURS count; the table definition is in DATA DIVISION and would require cross-referencing data layout with procedure statements
- Treating SEARCH as EVALUATE (no loop) — rejected because SEARCH semantics require index auto-increment between iterations

**Consequences:** Coverage increased from 19/51 to 20/51 HANDLED (39%). The loop + WHEN chain pattern is reusable for SEARCH ALL (binary search) if implemented later. Test count increased from 7639 to 7647 (8 new tests).

### ADR-035: Symbolic CALL, ALTER, ENTRY, CANCEL — inter-program and dynamic control flow (2026-03-02)

**Context:** CALL is the most commonly used inter-program statement in production COBOL. ALTER, ENTRY, and CANCEL are low-effort additions that don't require I/O.

**Decision:** Implement all four across the three-layer pipeline:

1. **CALL** — Symbolic subprogram invocation. Extracts program name (`getProgramValueStmt`), USING parameters with BY REFERENCE/CONTENT/VALUE types, and GIVING target. Lowers to `CALL_FUNCTION` with decoded parameter registers. The called program is treated as an unresolved external — same pattern as unresolved function calls in tree-sitter frontends. GIVING writes the symbolic return value back to the target field. Full cross-program resolution (LINKAGE SECTION mapping, BY REFERENCE memory sharing) is deferred to a future multi-program analysis pass.

2. **ALTER** — Dynamic GO TO retargeting. `ALTER PARA-1 TO PROCEED TO PARA-2` emits `STORE_VAR __alter_PARA-1 = "para_PARA-2"`. This captures the data flow of the retargeting for analysis, even though actual dynamic branch resolution isn't implemented.

3. **ENTRY** — Alternate subprogram entry point. Emits a `LABEL entry_<name>` so the entry point is visible in the CFG.

4. **CANCEL** — Program state invalidation. No-op for static analysis since it has no data-flow effect in a single-program context.

**Consequences:** Coverage increased from 20/51 to 24/51 HANDLED (47%). CALL enables data-flow tracking through subprogram boundaries (symbolically). Test count increased from 7647 to 7662 (15 new tests).

### ADR-036: Injectable I/O provider for COBOL ACCEPT, READ, WRITE, OPEN, CLOSE (2026-03-02)

**Context:** 5 of the remaining 27 unhandled COBOL statement types are I/O operations (ACCEPT, READ, WRITE, OPEN, CLOSE). These require external data sources (files, console) that don't exist during static analysis. The codebase already has a pluggable strategy pattern for unresolved calls (`UnresolvedCallResolver` ABC with symbolic/LLM implementations, injected via `VMConfig`).

**Decision:** Implement an injectable I/O provider system following the same ports-and-adapters pattern:

1. **Provider ABC** (`CobolIOProvider` in `interpreter/cobol/io_provider.py`) with a single `handle_call(func_name, args)` entry point. Two implementations: `NullIOProvider` (returns `UNCOMPUTABLE` for all calls — default) and `StubIOProvider` (returns queued test data for ACCEPT, manages stub file records for READ/WRITE/OPEN/CLOSE). A `_COBOL_IO_DISPATCH` dict maps `__cobol_*` function names to abstract method names, keeping the routing declarative.

2. **Direct provider dispatch in executor** — in `_handle_call_function`, before builtins, check `vm.io_provider` for `__cobol_*`-prefixed function names. If the provider returns a concrete value, use it; if `UNCOMPUTABLE`, fall through to symbolic wrapping. This keeps the executor language-agnostic (no COBOL knowledge, just checks for a provider).

3. **CALL_FUNCTION lowering** — all 5 I/O statements lower to `CALL_FUNCTION` with `__cobol_*` names (`__cobol_accept`, `__cobol_open_file`, `__cobol_close_file`, `__cobol_read_record`, `__cobol_write_record`). This reuses existing executor dispatch — no new opcodes needed.

4. **Injection via VMConfig** — `io_provider` field added to both `VMConfig` (frozen config) and `VMState` (runtime state), wired in `execute_cfg`.

5. **Audit classification** — I/O types are classified as `HANDLED_STUB` (not `HANDLED`) in the audit matrix, marking them as functional but dependent on an external provider for concrete execution. This distinguishes them from fully deterministic statement types.

**Alternatives considered:**
- Registering `__cobol_*` functions as builtins in `byte_builtins.py` — rejected because I/O operations are inherently side-effectful and external; builtins are for deterministic computation
- Adding new IR opcodes (READ_FILE, WRITE_FILE, etc.) — rejected because CALL_FUNCTION reuses existing executor dispatch and keeps I/O operations visible in data-flow analysis as regular function calls
- Making provider methods per-operation (separate `accept()`, `read()`, etc. on VMState) — rejected because a single `handle_call()` entry point is cleaner and language-agnostic

**Consequences:** Coverage increased from 24/51 to 29/51 (24 HANDLED + 5 HANDLED_STUB = 57%). The provider system enables concrete execution of I/O-heavy COBOL programs with injected test data. Test count increased from 7662 to 7714 (52 new tests).

---

### ADR-037: REWRITE, START, DELETE — file I/O extensions via existing provider pattern (2026-03-02)

**Context:** 3 additional COBOL file I/O statement types (REWRITE, START, DELETE) were not yet handled in the pipeline. All three follow the same I/O provider pattern established in ADR-036 for ACCEPT, READ, WRITE, OPEN, CLOSE.

**Decision:** Extend all three layers (bridge, dataclass, frontend lowering) and the I/O provider with REWRITE, START, DELETE using the existing pattern:

1. **Java bridge** — `serializeRewrite` extracts `getRecordCall()` and optional `getFrom().getFromCall()`. `serializeStart` extracts `getFileCall()` and optional `getKey().getComparisonCall()`. `serializeDelete` extracts `getFileCall()`.

2. **Python dataclasses** — `RewriteStatement(record_name, from_field)` mirrors `WriteStatement`. `StartStatement(file_name, key)` mirrors `ReadStatement` with a key field. `DeleteStatement(file_name)` is minimal.

3. **Frontend lowering** — All three emit `CALL_FUNCTION` with `__cobol_rewrite_record`, `__cobol_start_file`, `__cobol_delete_record` respectively, following the same pattern as `_lower_write`/`_lower_read`.

4. **I/O provider** — Three new entries in `_COBOL_IO_DISPATCH`. `NullIOProvider` returns `UNCOMPUTABLE`. `StubIOProvider`: REWRITE replaces last written record, START is a no-op (returns 0), DELETE removes the first queued record.

5. **Audit** — REWRITE, START, DELETE added to `BRIDGE_SERIALIZED_TYPES`, `_BRIDGE_TO_DISPATCH`, `_LOWERED_TYPES`, and `_IO_STUB_TYPES`.

**Consequences:** Coverage increased from 29/51 to 32/51 (24 HANDLED + 8 HANDLED_STUB = 63%). No new opcodes or architectural changes required — the provider pattern from ADR-036 scaled cleanly to three additional I/O operations.

---

### ADR-038: COBOL integration tests and bridge/frontend fixes for GIVING and EVALUATE/WHEN (2026-03-02)

**Context:** All existing COBOL e2e tests used `_FakeParser` with hand-crafted JSON — they never exercised the ProLeap Java bridge. Additionally, the bridge had two serialization gaps: (1) MULTIPLY/DIVIDE GIVING forms produced empty targets, and (2) EVALUATE/WHEN flattened all children without preserving WHEN conditions or the EVALUATE subject.

**Decision:** Three-part fix:

1. **Bridge fixes** — `serializeMultiply`/`serializeDivide` now check `getMultiplyType()`/`getDivideType()` and handle BY_GIVING/INTO_GIVING/BY_GIVING forms by extracting the GIVING phrase targets into a `"giving"` JSON array. `serializeEvaluate` now extracts the EVALUATE subject via `getSelect().getSelectValueStmt()`, serializes each `WhenPhrase` as a `WHEN` child with a `"condition"` field extracted from `When.getCondition().getValue().getValueStmt()`, and handles `WhenOther` as a `WHEN_OTHER` child.

2. **Python frontend** — `ArithmeticStatement` gains a `giving: list[str]` field. `_lower_arithmetic` dispatches to `_lower_arithmetic_giving` when `giving` is non-empty, computing `source OP target` and storing in each giving field. `EvaluateStatement` gains a `subject: str` field. `_lower_evaluate` constructs `"subject = value"` conditions when subject is present.

3. **Integration tests** — `tests/integration/test_cobol_programs.py` with 15 tests covering the full pipeline (source → ProLeap bridge → ASG → IR → CFG → VM). Tests skip when the bridge JAR is absent. COBOL FIXED format source is generated via a `_to_fixed()` helper.

**Consequences:** Full pipeline coverage from real COBOL source code. Bridge now correctly serializes MULTIPLY/DIVIDE GIVING and EVALUATE/WHEN/WHEN OTHER. Integration tests are self-contained (inline COBOL) and skip gracefully in CI without the JAR.

**Update (2026-03-02):** Extended from 15 to 29 integration tests. Added coverage for INITIALIZE, SET (TO/UP BY/DOWN BY), SEARCH (WHEN match + AT END), INSPECT (TALLYING + REPLACING), CALL (symbolic), STRING (concatenation), and UNSTRING (splitting). Fixed two bugs discovered during expansion: (1) `_lower_string` stored register *names* as literal constants via `_const_to_reg(part_regs)` instead of folding pairwise — added `__string_concat_pair` builtin. (2) `_lower_unstring` passed COBOL figurative constant "SPACES" as literal text — added `_translate_cobol_figurative()` lookup. Full coverage matrix documented in `docs/frontend-design/cobol.md`.

---

### ADR-039: Internalise parsing in Frontend.lower() (2026-03-02)

**Context:** `Frontend.lower(tree, source)` required callers to pre-parse source code with tree-sitter and pass the tree. This leaked parsing responsibility into orchestrators (`api.py`, `run.py`), forced every new frontend type (COBOL, LLM) to accept a `tree` parameter it ignored, and created three separate code paths in `run.py` for deterministic/LLM/COBOL frontends.

**Decision:** Each frontend now owns its parsing. The signature changed from `lower(self, tree, source: bytes)` to `lower(self, source: bytes)`. Key changes:

1. **`FrontendObserver` protocol** (`frontend_observer.py`) — timing callbacks `on_parse(duration)` and `on_lower(duration)` with a `NullFrontendObserver` default. Replaces the external timing that `run.py` previously performed around its own parse calls.

2. **`BaseFrontend`** — constructor now accepts `(parser_factory: ParserFactory, language: str, observer)`. `lower()` calls `parser_factory.get_parser(language).parse(source)` internally, timing both phases via the observer.

3. **All 15 language frontends** — constructors updated to accept and forward `(parser_factory, language, observer)`. Lua's redundant `lower()` override removed.

4. **Non-deterministic frontends** — `CobolFrontend`, `LLMFrontend`, `ChunkedLLMFrontend` drop the `tree` parameter. `ChunkedLLMFrontend` always parses internally (removed the `if tree is None` branch).

5. **Orchestrators** — `api.py:lower_source()` collapsed from three branches to a single `get_frontend(...).lower(source_bytes)`. `run.py:run()` uses a `_StatsObserver` and a single `get_frontend()` call, eliminating the three-branch dispatch.

**Consequences:** Single uniform API for all frontend types. Orchestrators no longer need to know which frontends use tree-sitter. Adding a new frontend type only requires implementing `lower(source: bytes)`. Timing is handled internally via the observer pattern rather than externally in the orchestrator. Trade-off: each `BaseFrontend` subclass now carries a `parser_factory` and `language` field, adding constructor boilerplate.

---

### ADR-040: Language StrEnum — bounded language parameter validation (2026-03-02)

**Context:** Frontend constructors and API functions accepted `language: str`, an unbounded string that silently broke at runtime deep inside tree-sitter if misspelled (e.g., `"pythonn"` instead of `"python"`). There was no compile-time or construction-time validation of language names.

**Decision:** Replace raw `language: str` with a `Language(StrEnum)` in `interpreter/constants.py`. Each member's value is the tree-sitter language name string (e.g., `Language.PYTHON = "python"`). Since `StrEnum` members *are* strings, they pass through to `tslp.get_parser(language)` without conversion — fully backward-compatible at runtime.

- **Internal APIs** (`BaseFrontend`, `ParserFactory`, `get_frontend`, `get_deterministic_frontend`, all 15 frontend constructors, `LLMFrontend`, `ChunkedLLMFrontend`) use `Language` directly in their type signatures.
- **Boundary APIs** (`api.py` functions, `run.py:run()`) accept `str | Language` and convert at the boundary via `Language(language)`, which raises `ValueError` for invalid language strings.
- `SUPPORTED_DETERMINISTIC_LANGUAGES` is now derived from the enum: `tuple(lang.value for lang in Language if lang != Language.COBOL)`.

**Alternatives considered:**
- Plain string validation with an allow-list check — rejected because it duplicates the language list and provides no IDE/type-checker support.
- Regular `Enum` (non-str) — rejected because it would require `.value` conversions everywhere tree-sitter expects a string; `StrEnum` eliminates this friction entirely.

**Consequences:** Invalid language names are caught at construction time with a clear `ValueError` (`'pythonn' is not a valid Language`). IDE autocompletion lists all supported languages. All 7781 existing tests pass unchanged because `Language.PYTHON == "python"` is `True` and `StrEnum` members are accepted wherever `str` is expected.

---

### ADR-041: COBOL OCCURS (Table/Array) support — single-dimension with subscript resolution (2026-03-03)

**Context:** COBOL OCCURS defines tables (arrays), fundamental to real COBOL programs and prerequisite for meaningful SEARCH operations. OCCURS was entirely unimplemented: the Java bridge ignored it, the Python data model had no concept of it, and the frontend couldn't handle subscripted field references like `WS-TABLE(WS-IDX)`.

**Decision:** Implement single-dimension OCCURS with literal and field-based subscripts using three key design choices:

1. **String-encoded subscripts:** Subscripted references stay as strings throughout the pipeline: `"WS-TABLE(WS-IDX)"`. This avoids changing 30+ statement dataclasses. The bridge constructs these strings from `TableCall.getSubscripts()`. The frontend parses them at resolution time via `_parse_subscript_notation()`.

2. **Centralized offset resolution:** All field access funnels through `_resolve_field_ref()` which parses subscript notation, looks up the base FieldLayout, and for subscripted refs emits runtime offset arithmetic: `base + (index - 1) * element_size`. A `ResolvedFieldRef` dataclass carries both the element-level `FieldLayout` and the computed offset register.

3. **Bridge-computed element_size:** The Java bridge emits `occurs` and `element_size` in the JSON. `computeByteLength()` was refactored into `computeElementSize()` (single element) and `computeByteLength()` (element × count). This keeps offset arithmetic correct because child offsets are relative to the first element.

**Scope:** Single-dimension OCCURS with literal and field-based subscripts. Multi-dimensional OCCURS and OCCURS DEPENDING ON are out of scope.

**Changes:**
- `DataFieldSerializer.java`: Added `extractOccurs()`, `computeElementSize()`, emits `occurs` and `element_size` in JSON.
- `StatementSerializer.java`: `extractCallName()` detects `TABLE_CALL`, unwraps subscripts into `"FIELD(SUBSCRIPT)"` notation.
- `CobolField`: Added `occurs: int = 0` and `element_size: int = 0`.
- `FieldLayout`: Added `occurs_count: int = 0` and `element_size: int = 0`.
- `_compute_group_length()`: Multiplies by OCCURS count when > 0.
- `CobolFrontend`: Added `_parse_subscript_notation()`, `ResolvedFieldRef`, `_resolve_field_ref()`, `_has_field()`. Updated `_emit_decode_field()`, `_emit_field_encode()`, `_emit_encode_and_write()` with optional `offset_reg`. Updated all ~29 field-access call sites.
- `cobol_expression.py`: Extended `_TOKEN_RE` to capture `FIELD(SUBSCRIPT)` as single tokens.

**Alternatives considered:**
- Structured subscript objects in statement dataclasses — rejected because it would require changing 30+ frozen dataclasses and all their serialization logic for a feature that only affects field access resolution.
- Distributed offset resolution at each call site — rejected in favour of centralized `_resolve_field_ref()` to avoid duplicating subscript arithmetic logic across 29 call sites.

**Consequences:** 20 new unit tests and 3 new integration tests (elementary OCCURS, field subscript, PERFORM VARYING loop). All 7801 existing unit tests and 32 integration tests pass. COBOL programs can now define tables and access elements via literal or field-based subscripts.

---

### ADR-042: Level-88 condition names, FILLER disambiguation, and multi-value VALUE clauses (2026-03-03)

**Context:** The DATA DIVISION audit showed three related features at NOT_EXTRACTED or BRIDGE_ONLY status: level-88 condition names (e.g. `88 STATUS-ACTIVE VALUE 'A'`), FILLER fields (anonymous padding fields that collide on the name "FILLER"), and multi-value VALUE clauses (`VALUE 'A' 'B' 'C'` or `VALUE 'A' THRU 'Z'`). These are fundamental COBOL features used in virtually all production programs.

**Decision:** Implement all three features across all pipeline layers with three key design choices:

1. **Bridge-level FILLER disambiguation:** The Java bridge renames FILLER fields to `FILLER_1`, `FILLER_2`, etc. using an instance counter on the serializer. This pushes disambiguation to the earliest possible point, ensuring unique field names throughout the pipeline without any downstream changes.

2. **Condition name index with expansion in condition lowering:** Rather than embedding level-88 semantics in every statement lowerer, a `ConditionNameIndex` maps condition names to their parent field and values. The existing `lower_condition()` function gains a single-token check: when a condition string is a known condition name, it expands to `parent == v1 OR parent == v2 ...` for discrete values and `parent >= from AND parent <= to` for THRU ranges. The index is built once from `DataLayout.fields` and threaded via `EmitContext`.

3. **Backward-compatible multi-value extraction:** The bridge emits both `"value"` (first value as string, for backward compatibility) and `"values"` (full array of `{"from": ..., "to": ...}` intervals). Python model carries both fields. Level-88 conditions use the same interval format in a `"conditions"` array on the parent field.

**Changes:**
- `DataFieldSerializer.java`: Added `disambiguateFiller()`, `serializeConditions()`, `extractAllValues()`, `serializeValueInterval()`, `stripQuotes()`. Changed from static-only to instance methods for FILLER counter state. `serializeEntries()` creates an instance internally.
- `condition_name.py`: New file — `ConditionValue` and `ConditionName` frozen dataclasses with `from_dict`/`to_dict`.
- `condition_name_index.py`: New file — `ConditionEntry`, `ConditionNameIndex`, `build_condition_index()`.
- `asg_types.py`: `CobolField` gains `conditions: list[ConditionName]` and `values: list[ConditionValue]`.
- `data_layout.py`: `FieldLayout` gains `conditions` and `values`, propagated in `_flatten_field()`.
- `condition_lowering.py`: `lower_condition()` gains `condition_index` parameter; new `_expand_condition_name()`, `_emit_single_value_test()`, `_emit_or_chain()` functions.
- `emit_context.py`: `EmitContext.__init__()` accepts `condition_index`, passes it to `lower_condition()`.
- `cobol_frontend.py`: `lower()` calls `build_condition_index()` and passes index to `EmitContext`.
- `audit_cobol_frontend.py`: Added ENTRY_CONDITION_88, CLAUSE_FILLER, CLAUSE_VALUE_MULTI to all three coverage sets.

**Consequences:** 18 new unit tests covering condition value/name construction, condition name index building, and condition lowering expansion (single-value, multi-value OR, THRU range, mixed, unknown passthrough). All 7958 unit tests and 32 integration tests pass. Three features move from NOT_EXTRACTED to HANDLED in the audit.

---

### ADR-043: Storage modifier clauses — SIGN, JUSTIFIED, SYNCHRONIZED, OCCURS DEPENDING ON (2026-03-03)

**Context:** The DATA DIVISION audit showed four features at NOT_EXTRACTED: CLAUSE_SIGN, CLAUSE_JUSTIFIED, CLAUSE_SYNCHRONIZED, and CLAUSE_OCCURS_DEPENDING. All four have full ProLeap API support but required extraction in the Java bridge, modelling in Python, and (for SIGN and JUSTIFIED) new encoder/decoder IR variants. These clauses control how COBOL fields are physically stored in memory and are common in production programs.

**Decision:** Implement all four clauses across the full pipeline (bridge → model → type system → layout → IR encoders → dispatch), each as a separate commit to maintain bisectability:

1. **SIGN IS LEADING/TRAILING [SEPARATE CHARACTER]:** Controls where the sign lives in a zoned decimal field. Four combinations: trailing embedded (default — sign nibble in high nibble of last byte), leading embedded (sign nibble in first byte), trailing separate (sign as dedicated byte 0x4E/0x60 after digits, +1 byte), leading separate (sign byte before digits, +1 byte). New IR encoder/decoder variants: `build_encode_zoned_separate_ir()` and `build_decode_zoned_separate_ir()` for separate-sign fields, plus `sign_leading` parameter on existing zoned IR builders. `CobolTypeDescriptor.byte_length` adds +1 when `sign_separate` is True.

2. **JUSTIFIED RIGHT:** Right-justifies alphanumeric fields (left-pads with spaces). New IR encoder: `build_encode_alphanumeric_justified_ir()` concatenates padding + input, then slices the last N bytes using `__list_len` for dynamic offset computation. No decoder changes needed — decoding is identical to left-justified.

3. **SYNCHRONIZED:** Forces natural word boundary alignment for COMP/BINARY fields (2-byte for ≤4 digits, 4-byte for ≤9 digits, 8-byte for ≤18 digits). Handled entirely in the Java bridge's offset computation via `computeSyncAlignment()` — no Python-side encoder changes needed because the bridge emits correctly aligned offsets.

4. **OCCURS DEPENDING ON:** `OCCURS m TO n DEPENDING ON counter-field` creates variable-length arrays. Bridge extracts `occurs_depending_on` (field name), `occurs` (max count from `getTo()`), and `occurs_min` (min count from `getFrom()`). Storage allocation uses max count. Python model and layout propagate the metadata for runtime bounds checking.

**Key design choices:**
- SIGN clause adds `sign_leading`/`sign_separate` booleans to `CobolTypeDescriptor`, `FieldLayout`, and `CobolField` — threaded through `parse_pic()` to the type descriptor at construction time.
- EBCDIC sign byte encoding: `0x4E` for positive, `0x60` for negative (standard EBCDIC `+`/`-` characters), computed as `0x4E + is_neg * 0x12`.
- SYNCHRONIZED alignment is bridge-only — the bridge rounds offsets up to natural boundaries and inserts implicit slack bytes. Python sees correct offsets without needing alignment logic.
- OCCURS DEPENDING ON uses max allocation for storage layout (matching IBM behaviour) with min/max metadata for optional runtime bounds checking.

**Changes:**
- `DataFieldSerializer.java`: Added `extractSign()`, `extractJustified()`, `extractSynchronized()`, `computeSyncAlignment()`, alignment logic in `serializeChildren()`, `computeElementSize()` +1 byte for SEPARATE sign. Updated `extractOccurs()` for DEPENDING ON max/min.
- `asg_types.py`: `CobolField` gains `sign_leading`, `sign_separate`, `justified_right`, `synchronized`, `occurs_depending_on`, `occurs_min`.
- `cobol_types.py`: `CobolTypeDescriptor` gains `sign_separate`, `sign_leading`, `justified_right`. `byte_length` updated for SEPARATE.
- `pic_parser.py`: `parse_pic()` accepts and propagates `sign_leading`, `sign_separate`, `justified_right`.
- `data_layout.py`: `FieldLayout` gains `sign_separate`, `sign_leading`, `justified_right`, `occurs_depending_on`, `occurs_min`. `_flatten_field()` propagates all fields.
- `ir_encoders.py`: New `build_encode_zoned_separate_ir()`, `build_decode_zoned_separate_ir()`, `build_encode_alphanumeric_justified_ir()`. Updated existing zoned builders with `sign_leading` param.
- `emit_context.py`: Updated `emit_encode_numeric()`, `emit_decode_field()`, `emit_numeric_encode_from_string()`, `emit_encode_value()`, `emit_encode_alphanumeric()`, `emit_encode_from_string()` for sign and justified dispatch.
- `audit_cobol_frontend.py`: All four features added to `DD_BRIDGE_EXTRACTED`, `DD_PYTHON_MODELLED`, `DD_FRONTEND_HANDLED`.

**Consequences:** 35+ new unit tests covering all sign variants (leading/trailing, embedded/separate, encode/decode, round-trip), justified encoding (short/exact/over/empty), synchronized alignment, and OCCURS DEPENDING ON metadata propagation. Four features move from NOT_EXTRACTED to HANDLED in the DATA DIVISION audit. All existing tests pass unchanged.

---

### ADR-044: Level-66 RENAMES support — contiguous field aliasing (2026-03-03)

**Context:** COBOL level-66 RENAMES creates an alternative name for a contiguous range of fields within a group. For example, `66 WS-FULL-NAME RENAMES WS-FIRST THRU WS-LAST` creates a field overlaying from WS-FIRST through WS-LAST. The DATA DIVISION audit showed ENTRY_RENAME_66 as NOT_EXTRACTED.

**Decision:** Implement RENAMES as a read-only alias — no new storage allocation. The bridge extracts `renames_from` (the FROM field name) and optionally `renames_thru` (the TO field name for THRU syntax) from `DataDescriptionEntryRename`. The Python model carries these as string fields on `CobolField`. The data layout builder uses a two-pass approach: first pass flattens all non-RENAMES fields, second pass resolves RENAMES fields by looking up the from/thru fields in the already-computed layout map. Offset = from_field.offset. Byte length = (thru_field.offset + thru_field.byte_length) - from_field.offset. For simple RENAMES (no THRU), thru defaults to from. RENAMES fields are always typed as ALPHANUMERIC. RENAMES does NOT increase `total_bytes`.

**Changes:**
- `DataFieldSerializer.java`: Added `serializeRename()` method, `DataDescriptionEntryRename` handling in `serializeEntries()` and `serializeChildren()`.
- `asg_types.py`: `CobolField` gains `renames_from`, `renames_thru` string fields.
- `data_layout.py`: `FieldLayout` gains `renames_from`, `renames_thru`. New `_resolve_renames()` helper. `build_data_layout()` uses two-pass approach.
- `audit_cobol_frontend.py`: `ENTRY_RENAME_66` added to all three coverage sets.

**Consequences:** ENTRY_RENAME_66 moves from NOT_EXTRACTED to HANDLED. Six new unit tests verify round-trip serialization, layout resolution (simple and THRU), and audit classification. All existing tests pass unchanged.

---

### ADR-045: BLANK WHEN ZERO clause support (2026-03-03)

**Context:** COBOL's `BLANK WHEN ZERO` clause specifies that a numeric field should display as all spaces when its value is zero. The DATA DIVISION audit showed CLAUSE_BLANK_WHEN_ZERO as NOT_EXTRACTED. This is a display-level semantic — storage size is unchanged, but the encoded bytes must be EBCDIC spaces (0x40) when the value is numerically zero.

**Decision:** Implement BLANK WHEN ZERO across all three pipeline layers. The bridge extracts the clause from ProLeap's `BlankWhenZeroClause` API. The Python model carries `blank_when_zero: bool` on `CobolField` and propagates it through `parse_pic()` to `CobolTypeDescriptor`. The frontend uses two encoding strategies: (1) for literal values (`emit_encode_value`), a Python-level check short-circuits to EBCDIC spaces when the value is zero; (2) for runtime values (`emit_encode_from_string`), a `__cobol_blank_when_zero` builtin wraps the encoded result and replaces it with spaces if the value string is numerically zero. This avoids needing branching IR in the inline_ir path which only supports straight-line code.

**Changes:**
- `DataFieldSerializer.java`: Added `extractBlankWhenZero()` method emitting `blank_when_zero: true`.
- `asg_types.py`: `CobolField` gains `blank_when_zero: bool`.
- `cobol_types.py`: `CobolTypeDescriptor` gains `blank_when_zero: bool`.
- `pic_parser.py`: `parse_pic()` accepts and propagates `blank_when_zero` parameter.
- `data_layout.py`: `_flatten_field()` passes `blank_when_zero` to `parse_pic()`.
- `byte_builtins.py`: New `_builtin_cobol_blank_when_zero` registered in `BYTE_BUILTINS`.
- `emit_context.py`: `_is_zero_value()`, `_emit_ebcdic_spaces()`, `_emit_blank_when_zero_wrap()` helpers; both literal and runtime encode paths updated.
- `audit_cobol_frontend.py`: `CLAUSE_BLANK_WHEN_ZERO` added to all three coverage sets.

**Consequences:** CLAUSE_BLANK_WHEN_ZERO moves from NOT_EXTRACTED to HANDLED. Twelve new unit tests cover round-trip serialization, type descriptor propagation, PIC parser integration, builtin function behaviour, data layout propagation, and audit classification. All existing tests pass unchanged.

---

### ADR-046: ADD/SUBTRACT GIVING clause support in bridge (2026-03-03)

**Context:** `MULTIPLY ... GIVING` and `DIVIDE ... GIVING` already worked end-to-end, but `ADD ... TO ... GIVING` and `SUBTRACT ... FROM ... GIVING` crashed with `KeyError: ''` because the Java bridge's `serializeAdd()` and `serializeSubtract()` only handled the non-GIVING forms (`AddToStatement`, `SubtractFromStatement`), ignoring `AddToGivingStatement` and `SubtractFromGivingStatement`. The Python side (`lower_arithmetic_giving` in `lower_arithmetic.py`) already handles the `giving` list correctly for all four arithmetic ops.

**Decision:** Bridge-only fix. Add `else if` branches in `serializeAdd()` and `serializeSubtract()` to handle the GIVING variants. For ADD: `getFroms()` and `getTos()` become operands, `getGivings()` becomes the `giving` JSON array. For SUBTRACT: the minuend goes first in operands (source), subtrahends second (target), because `lower_arithmetic_giving` computes `source op target`. The operand ordering is critical — `SUBTRACT X FROM Y GIVING Z` emits `operands=[Y, X]` so Python computes `Y - X`.

**Changes:**
- `StatementSerializer.java`: Added `AddToGivingStatement` branch in `serializeAdd()` and `SubtractFromGivingStatement` branch in `serializeSubtract()`. New imports: `AddToGivingStatement`, `ToGiving`, `SubtractFromGivingStatement`, `MinuendGiving`.

**Consequences:** All four arithmetic GIVING forms (ADD, SUBTRACT, MULTIPLY, DIVIDE) now work end-to-end through the bridge. Four new integration tests and four new unit tests verify the round-trip and execution. All 8075 tests pass.

---

### ADR-047: Cross-language e2e tests for closures, classes, and exceptions (2026-03-03)

**Context:** The Rosetta suite tested 8 algorithms (GCD, factorial, fibonacci, bubble sort, is_prime, interprocedural, fizzbuzz) and the Exercism suite tested 18 exercises — all across 15 languages. However, three feature categories had no cross-language coverage: closures (Python-only in `test_closures.py`), class/object operations (untested), and exception handling (untested).

**Decision:** Add three new Rosetta test files following the established pattern (PROGRAMS dict, lowering tests across all 15 langs, execution tests across STANDARD_EXECUTABLE_LANGUAGES):

1. **`test_rosetta_closures.py`** — Factory function returning a closure that captures an enclosing variable. Languages with true closure support (Python, JS, TS, Lua, PHP, Ruby) use nested functions. Languages without first-class closures (C, C++, Go, Pascal, Java, C#, Kotlin, Scala, Rust) use equivalent two-argument function calls. Expected: `answer = 15`.

2. **`test_rosetta_classes.py`** — Object/struct creation with field mutation. Python uses full class with `__init__`/`increment`/`get_value` methods. JS/TS use object literals with field access. PHP uses `stdClass`. Ruby/Lua use hash/table indexing. Rust uses struct field access. Java/C#/Scala/Kotlin use class-level state. C/C++/Go/Pascal use local variable mutation. Expected: `answer = 3`.

3. **`test_rosetta_exceptions.py`** — Try/catch structural lowering and happy-path execution. 10 languages (Python, JS, TS, Java, Ruby, PHP, C#, C++, Kotlin) generate labeled try/catch blocks with `SYMBOLIC caught_exception` in the catch clause; the test verifies this structure. 5 languages (C, Go, Rust, Lua, Pascal) lack native try/catch and use direct assignment. The execution test verifies the try body runs and branches past the catch block (catch blocks are structurally present but unreachable in the current VM since THROW is a no-op). Expected: `answer = -1`.

**Limitations discovered:**
- Kotlin/Scala function references (`::adder`, `adder _`) produce unsupported SYMBOLIC instructions — closure tests use simplified two-argument patterns for these languages.
- Class instantiation via `new_object` + `call_method constructor` (JS/TS/Java/C#/Kotlin) stores the constructor's return value instead of the object reference — only Python's `call_function ClassName` path correctly returns the heap object. This prevented testing true class instantiation across most languages.
- Scala's `catch { case e: Exception => ... }` pattern is not recognized as a catch clause by the frontend (no `SYMBOLIC caught_exception` generated).
- Pascal's `try/except/end` is lowered flat (all children as sequential statements) rather than as labeled try/catch blocks.
- C/C++ struct field access (`c.count`) doesn't resolve correctly when the struct is locally declared — `LOAD_FIELD` returns symbolic values.

**Consequences:** 156 new tests (47 closures + 47 classes + 62 exceptions) bring the total to 8232 tests (8170 unit + 62 integration, 6 skipped, 3 xfailed). The three test files document both the VM's current capabilities and its limitations around closures, class instantiation, and exception control flow — providing regression coverage and serving as a roadmap for future VM enhancements.

---

### ADR-048: Fix Scala catch clause recognition in try/catch lowering (2026-03-03)

**Context:** Scala's `catch { case e: Exception => ... }` was silently dropped during lowering. The `_extract_try_parts()` method in the Scala frontend used `child.child_by_field_name("body")` to find the catch body, but tree-sitter's Scala grammar stores the `case_block` as an unnamed child of `catch_clause`, not as a named `body` field. Similarly, `finally_clause` stores its `block` child without a `body` field name. As a result, catch clauses produced no `SYMBOLIC caught_exception` in the IR, and finally blocks were dropped.

**Decision:** Two-line fix in `_extract_try_parts()`:
1. Replace `child.child_by_field_name("body")` with `next((c for c in child.children if c.type == "case_block"), None)` for catch clauses.
2. Add a fallback `or next((c for c in child.children if c.type == "block"), None)` for the finally clause.

The inner `case_clause` field names (`pattern`, `body`) do resolve correctly via `child_by_field_name`, so the per-case extraction logic was already correct — only the outer container lookup was broken.

**Consequences:** Scala now generates proper try/catch/finally block structure with `SYMBOLIC caught_exception` per case clause. Five new unit tests verify single catch, multiple catches, exception variable storage, try_end branching, and finally blocks. Scala added to `TRY_CATCH_LANGUAGES` in the Rosetta exception e2e tests. All 8238 tests pass.

---

### ADR-049: Fix Pascal try/except to use structured _lower_try_catch (2026-03-03)

**Context:** Pascal's `_lower_pascal_try()` was a stub that simply iterated all children as sequential statements, causing both the try body and except body to execute unconditionally. This meant exception handlers ran even in the happy path.

**Decision:** Replace the flat iteration with a proper `_extract_pascal_try_parts()` method that parses the Pascal `try` AST node by tracking `kExcept`/`kFinally` keyword boundaries:
- Before `kExcept`/`kFinally`: first `statements` child → try body
- After `kExcept`: `exceptionHandler` children → catch clauses (each with identifier, typeref, and handler body)
- After `kFinally`: `statements` child → finally body

The extracted parts are passed to the base class `_lower_try_catch()`, producing proper labeled blocks (try_body, catch_N, try_finally, try_end) with BRANCH instructions and `SYMBOLIC caught_exception` per handler.

**Consequences:** Pascal now generates structured try/catch/finally block IR identical to the other 10 try/catch-supporting languages. Five new unit tests verify caught_exception generation, exception variable storage, try_end labels, finally blocks, and non-sequential execution. Pascal added to `TRY_CATCH_LANGUAGES` in Rosetta e2e. Rosetta exception e2e now uses a proper `try/except/on e: Exception do` program for Pascal. All 8244 tests pass.

---

### ADR-050: Implement THROW exception control flow with TRY_PUSH/TRY_POP (2026-03-03)

**Context:** The VM had TRY_PUSH and TRY_POP opcodes defined in the IR but no runtime support. THROW was a no-op — it logged but didn't redirect execution. Exception handlers (catch blocks) were dead code; the VM always fell through the try body and branched past them.

**Decision:** Implement a three-part exception control flow mechanism:
1. **IR emission**: `_lower_try_catch` (and Ruby's `_lower_try_catch_ruby`) emit `TRY_PUSH` before the try body (with catch labels, finally label, and end label as operands) and `TRY_POP` after the try body (before the BRANCH to exit target).
2. **Executor handlers**: `_handle_try_push` pushes an `ExceptionHandler` onto `VMState.exception_stack`; `_handle_try_pop` pops it. `_handle_throw` checks the exception stack — if a handler exists, pops it and sets `next_label` to the first catch label; otherwise marks the throw as uncaught.
3. **Run loop**: Caught throws (THROW with `next_label`) follow the label to the catch block instead of calling `_handle_return_flow`. Uncaught throws still propagate to the caller.

Also fixed Ruby's `raise` to emit `THROW` instead of `CALL_FUNCTION`.

**Consequences:** Exception control flow now works end-to-end: throw redirects to catch, code after throw is skipped, finally blocks execute on both normal and exceptional paths, and no-exception paths skip catch blocks. 14 new tests (5 Python execution, 2 IR emission, 7 cross-language) verify the behavior across Python, JavaScript, Java, PHP, Ruby, Kotlin, and C++. All 8258 tests pass.

---

### ADR-051: Fix class instantiation for non-Python frontends (2026-03-03)

**Context:** Class instantiation only worked for Python. Java, C#, and Scala emit method definitions *after* the `end_class` label (so they execute at top level for field initializers and static blocks). The registry scanner only tracked methods *inside* `class_X`...`end_class_X` labels, so hoisted methods were never associated with their class. Additionally, JavaScript's `new` expression returned the constructor's return value instead of the object address, and `_try_class_constructor_call` assumed all constructors have an explicit `self`/`this` first parameter (Python-style), breaking Java/C++ where `this` is implicit.

**Decision:** Three-part fix:
1. **Registry scanner** (`_scan_classes` in `registry.py`): Keep `in_class` set after `end_class_X` instead of clearing it. Function refs after `end_class` are correctly associated with the preceding class. The next `class_X` label for a different class resets the association.
2. **Constructor `this` binding** (`_try_class_constructor_call` in `executor.py`): Detect whether the first parameter is an explicit `self`/`this` (Python-style). If not, explicitly bind `this` to the object address and map all parameters to constructor arguments without the offset.
3. **JavaScript `new` expression** (`_lower_new_expression` in `javascript.py`): Return the `NEW_OBJECT` register (object address) instead of the `CALL_METHOD` register (constructor return value).

**Consequences:** Class instantiation now works for Java (constructor dispatched, `this` bound, fields set), C#, Scala, and JavaScript. Eight new unit tests verify class method registration (Java, C#, Scala), constructor dispatch, field setting, and object allocation. All 8266 tests pass.

---

### ADR-052: Rosetta destructuring test — 5-language subset (2026-03-03)

**Context:** Previous Rosetta tests cover all 15 languages. Destructuring is a language-specific feature with dedicated lowering methods in only a subset of frontends: Python (`_lower_tuple_unpack`), JavaScript (`_lower_array_destructure`), TypeScript (inherited from JS), Rust (`_lower_tuple_destructure`), Scala (`_lower_scala_tuple_destructure`), and Kotlin (`_lower_multi_variable_destructure`). Kotlin uses `arrayOf` (a VM builtin) instead of `listOf`/`Pair` (which are unresolved function calls).

**Decision:** Create a 6-language Rosetta test that verifies genuine destructuring lowering by asserting the IR contains `LOAD_INDEX` opcodes (the IR pattern all destructuring methods emit). This is not a full 15-language test — the `assert_cross_language_consistency` helper is not used. Cross-language checks are custom and scoped to the 6 participating languages. VM execution verifies `answer == 15` with 0 LLM calls.

**Consequences:** The destructuring code path is verified end-to-end for 6 languages (IR emission + VM execution). The test explicitly documents which languages have destructuring support and which do not, serving as a living inventory. All 8292 tests pass.

---

### ADR-053: Rosetta nested functions test — 10-language subset (2026-03-03)

**Context:** The original nested functions test (commit `593c58e`, reverted in `44620d5`) used sibling functions for 12/15 languages — it didn't actually test nested function definitions. Only 10 of the 15 deterministic frontends support genuine nested function definitions: Python, JavaScript, TypeScript, Rust, Lua, Ruby, Go, Kotlin, Scala, PHP. The remaining 5 (C, C++, Java, C#, Pascal) lack nested function syntax.

**Decision:** Create a 10-language Rosetta test that verifies genuine nested function lowering by asserting the IR contains a `func_inner` or `func___anon` label nested inside the outer function body — proving the inner function was lowered as a nested definition, not a sibling. The test uses `outer(x)` containing `inner(y) → y * 2`, returning `inner(x) + 5`, with `answer = outer(3) → 11`. The `assert_cross_language_consistency` helper is not used (it requires all 15 languages). Cross-language checks are custom and scoped to the 10 participating languages.

**Consequences:** Nested function lowering is verified end-to-end for 10 languages (IR structure + VM execution producing `answer == 11` with 0 LLM calls). The test explicitly documents which languages support nested function definitions and which do not. All 8334 tests pass.

---

### ADR-054: Rosetta nested function scoping test — 7-language subset (2026-03-03)

**Context:** The existing nested functions test (ADR-053) verifies that inner functions work correctly when called from inside the outer function, but does not verify that inner functions are inaccessible from outside — a key scoping property. Of the 10 languages with nested function support, 7 have genuine inner-function scoping (inner is local to outer's scope): Python, JavaScript, TypeScript, Rust, Go, Kotlin, Scala. The remaining 3 (Ruby, PHP, Lua) leak inner functions to enclosing/global scope by language design, so testing inaccessibility would not reflect actual language semantics.

**Decision:** Add a `TestNestedFunctionScoping` class to the existing nested functions test file, parametrized over the 7 scoped languages. Each program calls `outer(3)` (producing `result = 11`), then attempts `inner(3)` from outside. The VM's frame-based variable lookup naturally enforces scoping: `inner`'s function reference is stored via `STORE_VAR` inside `outer`'s frame, and when `outer` returns, its frame is popped, making `inner` unreachable. The test asserts that `leaked` is a `SymbolicValue` (symbolic resolution, not a concrete result), confirming 0 LLM calls.

**Consequences:** Inner function scoping is verified for 7 languages (21 new tests: 7 languages × 3 assertions). The test documents the scoping semantics distinction between the 7 scoped languages and the 3 that leak. All 8355 tests pass.

### ADR-055: Rosetta leaky inner function scoping xfail tests — Ruby, PHP, Lua (2026-03-03)

**Context:** ADR-054 excluded Ruby, PHP, and Lua from the inner-function scoping test because these languages do not scope inner functions to the enclosing function. In Ruby, `def inner(y)` inside `outer` defines a method on the default definee (accessible globally). In PHP, a nested `function inner($y)` becomes global after the enclosing function is first called. In Lua, `function inner(y)` without the `local` keyword assigns to global scope. In real execution, calling `inner(3)` from outside `outer` returns 6 (concrete: `3 * 2`). However, the VM enforces stricter frame-based scoping — `inner`'s function reference is stored in `outer`'s frame and becomes inaccessible after `outer` returns, producing a `SymbolicValue`.

**Decision:** Add a `TestNestedFunctionLeakyScoping` class parametrized over the 3 leaky languages (Ruby, PHP, Lua). Each program calls `outer(3)` (producing `result = 11`), then attempts `inner(3)` from outside. The test includes: (1) `test_inner_accessible_inside_outer` — verifies `result == 11` (passes); (2) `test_inner_leaks_outside_outer` — marked `xfail(strict=True)`, asserts `leaked == 6` (expected to fail because the VM blocks the leak with frame-based scoping); (3) `test_zero_llm_calls` — verifies 0 LLM calls (passes). The `_extract_var` helper is updated to accept a `language` parameter for PHP `$` prefix handling via `_var_name_for_language`.

**Consequences:** 9 new tests (3 languages × 3 assertions), of which 3 are strict xfails documenting the VM's frame-based scoping limitation. The xfails serve as living documentation: if the VM ever gains language-aware scoping for leaky languages, the xfails will start passing and `strict=True` will flag them for update. All 8361 tests pass (8299 unit + 62 integration, 4 skipped, 6 xfailed).

### ADR-056: Fix closure test discrepancies — honest documentation of two-tier Rosetta closures (2026-03-03)

**Context:** A test discrepancy audit (15 findings across 95 unit test files) identified two closure-related violations: (1) HIGH — `test_rosetta_closures.py` claimed all 15 languages test closures, but only 4 (Python, JavaScript, TypeScript, Lua) implement genuine closures; the other 11 use plain two-argument functions. (2) MEDIUM — `test_closures.py:test_two_closures_share_state` creates one closure and calls it 3 times, testing accumulator persistence rather than two closures sharing state.

**Decision:** (1) Rewrite the Rosetta closures module docstring and PROGRAMS comment block to honestly describe two tiers: "Tier 1 — Genuine closures" (4 languages) and "Tier 2 — Function-call fallback" (11 languages). Add `CLOSURE_LANGUAGES` and `FALLBACK_LANGUAGES` frozenset constants with an assertion that their union equals the full program set. (2) Rename `test_two_closures_share_state` to `test_accumulator_persists_mutations` with an accurate docstring.

**Consequences:** Test documentation now accurately describes what each tier tests. One new test (`test_tier_constants_cover_all_programs`) ensures the tier classification stays in sync with the program set. All 8362 tests pass (8300 unit + 62 integration, 4 skipped, 6 xfailed).

---

### ADR-057: Upgrade Go, Kotlin, Scala to genuine closures in Rosetta test (2026-03-03)

**Context:** ADR-056 established a two-tier classification for the Rosetta closures test: 4 languages with genuine closures and 11 with plain two-argument fallback functions. However, Go, Kotlin, and Scala all support nested functions that genuinely capture enclosing variables — Go via anonymous `func` literals, Kotlin via local `fun` declarations, and Scala via local `def` declarations. These three languages were unnecessarily in Tier 2.

**Decision:** Upgrade Go, Kotlin, and Scala from Tier 2 (fallback) to Tier 1 (genuine closures). Each now implements `make_adder(x)` returning a nested function `adder(y)` that captures `x` from the enclosing scope, matching the pattern used by Python, JavaScript, TypeScript, and Lua. The remaining 8 languages stay as fallback: Java, C#, C, C++, Pascal (no nested functions), Rust (`fn` items don't capture), Ruby (`def` doesn't capture outer locals), and PHP (`function` doesn't capture without `use`).

**Consequences:** Tier 1 grows from 4 to 7 languages; Tier 2 shrinks from 11 to 8. The test now exercises genuine closure semantics in every language that supports them. The docstring and comment block document why Rust, Ruby, and PHP remain in Tier 2 despite having nested function syntax.

---

### ADR-058: Upgrade Pascal to genuine closure in Rosetta test (2026-03-03)

**Context:** Pascal has supported nested functions with lexical capture since the 1970s. The tree-sitter grammar correctly parses nested `defProc` nodes, but `_lower_pascal_proc` in the Pascal frontend only extracted the `declProc` (metadata) and `block` (body) children, skipping sibling `defProc` children. This meant nested functions parsed but were never lowered to IR, so Pascal was unnecessarily placed in Tier 2 (plain function fallback) of the Rosetta closures test.

**Decision:** Fix `_lower_pascal_proc` to iterate over `node.children` and recursively call `_lower_pascal_proc` on any nested `defProc` children before lowering the body block. This follows the same pattern used by all other frontends that support nested functions. With the frontend fix in place, upgrade Pascal from Tier 2 (fallback) to Tier 1 (genuine closures) in the Rosetta closures test. The Pascal program now uses `make_adder(x)` containing a nested `adder(y)` that captures `x` from the enclosing scope, with `answer := make_adder(10)` producing 15.

**Consequences:** Tier 1 grows from 7 to 8 languages; Tier 2 shrinks from 8 to 7. Pascal now exercises genuine nested-function closure semantics. The remaining 7 fallback languages (Java, C#, C, C++, Rust, Ruby, PHP) stay in Tier 2 for legitimate reasons (no nested functions or no lexical capture).

---

### ADR-059: Upgrade remaining 6 languages to genuine closures in Rosetta test (2026-03-03)

**Context:** After ADR-058, 7 fallback languages remained: Java, Ruby, PHP, C#, C, C++, Rust. Investigation revealed that 6 of these have working closure/lambda frontend support (only C truly lacks closure syntax). Three VM-level issues prevented their use: (1) `CALL_METHOD` on a FUNC_REF (needed by Java `.apply()` and Ruby `.call()`) fell through to the symbolic resolver instead of invoking the function; (2) `CALL_UNKNOWN` on a FUNC_REF (needed by PHP arrow-function dynamic calls) also fell through to symbolic resolution; (3) C++ lambda parameter extraction used `node.child_by_field_name("declarator")` but didn't unwrap the `lambda_declarator` to find the `parameter_list` inside; and Ruby's `_lower_ruby_lambda` dispatched the block body to `_lower_ruby_block` (creating a sub-function) instead of inlining the lambda body.

**Decision:** Apply five fixes: (1) Add a FUNC_REF check in `_handle_call_method` before the type_hint/resolver fallthrough — if `obj_val` is a FUNC_REF, delegate to `_try_user_function_call`; (2) Add a FUNC_REF check in `_handle_call_unknown` before symbolic resolution; (3) Fix C++ `_lower_lambda` to unwrap `lambda_declarator` → `parameter_list` before calling `_lower_c_params`; (4) Fix Ruby `_lower_ruby_lambda` to inline the block body's children directly instead of dispatching to `_lower_ruby_block`; (5) Fix C# `_lower_lambda` to emit a proper `FUNC_REF_TEMPLATE` instead of a raw `func:` label reference. With these fixes, upgrade all 6 languages to genuine closure programs: PHP (arrow function), Rust (closure expression), C# (local function), C++ (lambda expression), Java (lambda with `.apply()`), Ruby (lambda with `.call()`).

**Consequences:** Tier 1 grows from 8 to 14 languages; Tier 2 shrinks to just C (which genuinely has no closure syntax). The VM now correctly dispatches method and dynamic calls on FUNC_REFs, which benefits any future language that uses similar patterns. Four frontend/VM fixes were needed, each with targeted unit tests.

---

### ADR-060: Add lambda/arrow-function coverage to Rosetta closure test (2026-03-03)

**Context:** The Rosetta closure test (test_rosetta_closures.py) exercises only the nested `def`/`function` form. Five languages also support a lambda/arrow-function closure form, but three had bugs preventing their lambdas from working: (1) Python `_lower_lambda` emitted a raw `func:label` string instead of the proper `FUNC_REF_TEMPLATE` format, causing the VM to fail on dispatch; (2) Kotlin `_lower_lambda_literal` skipped the `lambda_parameters` child entirely, so lambda params were never bound; (3) Scala `_lower_lambda_expr` skipped the `bindings` child, so lambda params were also never bound. Additionally, both Kotlin and Scala lambdas always returned `None` instead of implicitly returning the last expression's value.

**Decision:** Apply three frontend fixes and add a companion Rosetta test: (1) Fix Python `_lower_lambda` to use `FUNC_LABEL_PREFIX` in label generation and `FUNC_REF_TEMPLATE.format()` for the function reference, matching every other frontend; (2) Fix Kotlin `_lower_lambda_literal` to extract `lambda_parameters → variable_declaration → simple_identifier` as params (emitting `SYMBOLIC param:name` + `STORE_VAR`), and implicitly return the last expression in the `statements` body; (3) Fix Scala `_lower_lambda_expr` to extract `bindings → binding → identifier` as params, and implicitly return the last body expression. Add `test_rosetta_closures_lambda.py` exercising `make_adder(10)(5) = 15` for all 5 lambda-capable languages (Python, JS, TS, Kotlin, Scala) with clean lowering, cross-language consistency, and VM execution assertions.

**Consequences:** Lambda/arrow closures now work correctly for Python, Kotlin, and Scala. The new Rosetta test provides 17 test cases covering the lambda form across 5 languages. The implicit-return-last-expression pattern in Kotlin and Scala lambdas matches the language semantics faithfully.

---

### ADR-061: Upgrade Rosetta classes test to genuine class/struct operations (2026-03-04)

**Context:** `test_rosetta_classes.py` claimed to test "class instantiation, field access, and method calls" but 8 of 15 language programs (Java, C#, Scala, Kotlin, Go, C, C++, Pascal) used plain variable arithmetic with zero class/object operations. The VM itself was correct (Python proved this); all bugs were in the frontends.

**Decision:** Fix 7 frontends and upgrade all 8 programs to genuine class/struct operations:

- **Java/C#/Scala** (Phase 1): Methods didn't declare `this` as a parameter. The VM's `_handle_call_method` binds the receiver object to `params[0]`, so methods must have `SYMBOLIC param:this` + `STORE_VAR this` at their start. Added `_emit_this_param()` and `_has_static_modifier()` to each frontend, injecting `param:this` only for non-static methods. C# additionally needed `"this"` added to `_EXPR_DISPATCH` (tree-sitter produces node type `"this"`, not `"this_expression"`).
- **Go/C/C++** (Phase 2): Go already worked; just upgraded the test program. C's `_lower_declaration` emitted `CONST None` for `struct Counter c;` — added `_extract_struct_type()` to detect `struct_specifier` and emit `CALL_FUNCTION Counter`. C++ extended this to also detect bare `type_identifier` nodes (C++ uses `Counter c;` without `struct` keyword).
- **Kotlin** (Phase 3): Three bugs: (1) `_node_text(navigation_suffix)` returned `.count` with leading dot — added `_extract_nav_field_name()` to unwrap to inner `simple_identifier`; (2) assignment to `directly_assignable_expression` with `navigation_suffix` fell through to `STORE_VAR` — added explicit branch emitting `STORE_FIELD`; (3) no `param:this` injection for class methods.
- **Pascal** (Phase 4): Three bugs: (1) `declType` was a no-op — added `_lower_pascal_decl_type` emitting `CLASS_REF` for record types; (2) record-typed variables emitted `CONST None` — track `_record_types` set and emit `CALL_FUNCTION` for allocation; (3) `exprDot` assignment targets fell through to `STORE_VAR "c.count"` — added `exprDot` branch in `_lower_pascal_assignment` emitting `STORE_FIELD`.

Programs are organised in three tiers: Tier 1 (class with methods: Python, Java, C#, Kotlin, Scala), Tier 2 (object/struct field access: JS, TS, PHP, Ruby, Lua, Go, C, C++, Rust), Tier 3 (record field access: Pascal).

**Consequences:** All 15 languages now exercise genuine class/struct/record operations. The test validates real field access and method dispatch rather than plain variable arithmetic. Seven frontends received targeted fixes that also benefit any future programs using these patterns.

---

### ADR-062: Promote 6 Tier 2 languages to Tier 1 class methods in Rosetta classes (2026-03-04)

**Context:** After ADR-061, 5 languages (Python, Java, C#, Kotlin, Scala) used genuine class methods in `test_rosetta_classes.py` while 6 others (JS, TS, PHP, Go, C++, Rust) were at Tier 2 (field-only). Examination showed these 6 languages already had working class/method infrastructure in their frontends, only needing `param:this`/`param:self` injection.

**Decision:** Promote 6 languages from Tier 2 to Tier 1 by injecting the receiver parameter:

- **JS/TS** (Phase 1): Added `_emit_this_param()` and `_has_static_modifier()` to `JavaScriptFrontend`. `_lower_method_def` now injects `param:this` for non-static methods (including constructors). TS inherits JS fix. Static detection checks for `"static"` child token.
- **PHP** (Phase 1): Added `_emit_this_param()` (emitting `param:$this`) and `_has_static_modifier()` (checking for `static_modifier` child) to `PhpFrontend`. Updated `_lower_php_object_creation` from `CALL_FUNCTION` to `NEW_OBJECT` + `CALL_METHOD("__construct")` to match the class instantiation pattern.
- **Go** (Phase 2): Converted `_lower_go_type_decl` for struct types from emitting `SYMBOLIC "struct:..."` to a proper `CLASS_LABEL`/`END_CLASS_LABEL` block. Go methods (defined at package level with receivers) are associated via the registry's hoisted-method scan. No changes needed to `_lower_go_method_decl` — it already injected the receiver as the first parameter.
- **C++** (Phase 2): Added `_emit_this_param()` and `_lower_cpp_method()` to `CppFrontend`. Overrode `_lower_struct_body` to delegate to `_lower_cpp_class_body`, which dispatches `function_definition` children to the new `_lower_cpp_method` (with `param:this` injection). Struct bodies now handle inline methods.
- **Rust** (Phase 3): No frontend changes needed. `_extract_param_name` already handled `self_parameter` → `"self"`, and `_lower_impl_item` emitted a CLASS block with methods inside. Direct struct instantiation (`Counter { count: 0 }`) used instead of `Counter::new()` since scoped identifiers (`Type::method`) don't resolve to class-scoped functions.

Updated tier classification: Tier 1 (11): Python, Java, C#, Kotlin, Scala, JS, TS, PHP, Go, C++, Rust. Tier 2 (3): Ruby, Lua, C. Tier 3 (1): Pascal.

**Consequences:** 11 of 15 languages now exercise the full class/method dispatch pipeline (class registration, `CALL_METHOD`, receiver binding, `STORE_FIELD`/`LOAD_FIELD` through `this`/`self`). Ruby/Lua/C remain at Tier 2 due to fundamental architecture mismatches (Ruby's `@var` → plain identifier, Lua's table-based objects, C's lack of methods on structs).

---

### ADR-063: Promote Ruby to Tier 1 class/method semantics (2026-03-04)

**Context:** Ruby was stuck at Tier 2 (hash-based field access) in the Rosetta classes test. The Ruby frontend already had class/method infrastructure (`_lower_ruby_class`, `_lower_ruby_method`, `_lower_ruby_call`) but lacked four capabilities: (1) `@var` instance variables mapped to plain `LOAD_VAR`/`STORE_VAR` instead of field operations on `self`, (2) no implicit `self` parameter injection for instance methods, (3) `Counter.new()` dispatched as a regular method call instead of object construction, (4) `initialize` was not mapped to the canonical `__init__` constructor name.

**Decision:** Five targeted changes to `ruby.py`:
1. **`_lower_instance_variable`**: New dispatch handler for `instance_variable` nodes — strips `@` prefix, emits `LOAD_VAR self` + `LOAD_FIELD self_reg "field"` (read) or `STORE_FIELD self_reg "field" val_reg` (write via `_lower_store_target`).
2. **`_emit_self_param`**: Emits `SYMBOLIC param:self` + `STORE_VAR self` at method entry, matching the `_emit_this_param` pattern used by JS/PHP/Java/Kotlin/Scala/C#/C++.
3. **`_lower_ruby_method(inject_self=True)`**: When called from class body, injects `self` param and maps `initialize` → `__init__`.
4. **`_lower_ruby_call` `new` detection**: When receiver starts with uppercase and method is `new`, emits `NEW_OBJECT(class)` + `CALL_METHOD(obj, "__init__", args)` instead of a regular method call.
5. **`_lower_ruby_class` body iteration**: Replaced `_lower_block(body_node)` with explicit child iteration — `method` children get `inject_self=True`, others get `_lower_stmt`.

**Consequences:** Ruby is promoted to Tier 1 (12 languages total). The Rosetta classes test now uses a genuine Ruby class with `initialize`, `increment`, and `get_value` methods. Lua and C remain at Tier 2. Pascal remains at Tier 3.

---

### ADR-063.1: Refactor tree-sitter frontends from monolithic files to modular packages with pure functions + context (2026-03-04)

**Status:** Accepted

**Context:** All 13 tree-sitter frontends (excluding C++/TypeScript which are inheritance wrappers, and COBOL which was already modular) were monolithic single files of 780–1,658 lines each, cramming 30–55 handler methods into one class. This made them hard to navigate, test in isolation, and compose. The COBOL frontend had already been successfully decomposed into 16 focused modules with an `EmitContext` pattern.

**Decision:** Refactor all tree-sitter frontends to a modular pure-functions + injected-context architecture:

1. **`TreeSitterEmitContext`** (`interpreter/frontends/context.py`): A dataclass holding all mutable state (registers, labels, instructions, loop/break stacks), dispatch tables, grammar constants, and utility methods (`fresh_reg`, `fresh_label`, `emit`, `lower_block`, `lower_stmt`, `lower_expr`). Passed as the first argument to all pure-function lowerers.

2. **`GrammarConstants`** (same file): A dataclass holding overridable grammar field names and literal strings per language (function name/params/body fields, if condition/consequence/alternative fields, block node types, comment types, canonical literals).

3. **Common lowerers** (`interpreter/frontends/common/`): Pure functions extracted from `BaseFrontend` into 5 modules — `expressions.py`, `control_flow.py`, `declarations.py`, `assignments.py`, `exceptions.py`. Each function has signature `(ctx: TreeSitterEmitContext, node) -> str | None`.

4. **Per-language packages** (`interpreter/frontends/<lang>/`): Each monolithic `<lang>.py` becomes a package with `__init__.py`, `frontend.py` (thin orchestrator), `expressions.py`, `control_flow.py`, `declarations.py`. The frontend class overrides only `_build_constants()`, `_build_stmt_dispatch()`, `_build_expr_dispatch()`.

5. **Dual-mode `BaseFrontend`**: Supports both legacy (bound methods in `_STMT_DISPATCH`/`_EXPR_DISPATCH`) and context mode (pure functions via `_build_*()` methods), enabling incremental migration.

6. **Inheritance preserved**: C++ extends C's frontend, TypeScript extends JavaScript's — both call `super()._build_*()` and overlay their own entries.

**Consequences:** All 15 frontends are now modular packages (13 fully converted + 2 inheritance wrappers). 8469 tests pass with zero regressions. Each handler is independently testable as a pure function. Common patterns are shared via `common/` modules. The `_base.py` file is reduced to a thin orchestration template.

---

### ADR-063.2: Migrate from provider-specific SDKs to LiteLLM (2026-03-04)

**Context:** The LLM integration layer had 4 near-identical `LLMClient` subclasses (`ClaudeLLMClient`, `OpenAILLMClient`, `OllamaLLMClient`, `HuggingFaceLLMClient`) each wrapping a provider-specific SDK, and 4 identical `LLMBackend` subclasses differing only in the provider string passed to the factory. This duplication meant every new provider required a new class pair, and two direct SDK dependencies (`anthropic`, `openai`) had to be maintained separately.

**Decision:** Replace the `anthropic` and `openai` direct dependencies with `litellm`, which provides a unified `completion()` interface that handles provider routing internally. Collapse the 4 client classes into a single `LiteLLMClient` that accepts an injectable `completion_fn` callable (defaulting to `litellm.completion()`), and the 4 backend classes into a single `LLMInterpreterBackend` that accepts any `LLMClient`. A `_resolve_model()` function maps `(provider, model, base_url)` to LiteLLM model strings (e.g. `ollama/qwen2.5-coder:7b-instruct`).

**Consequences:** SDK dependencies reduced from 2 to 1. `llm_client.py` reduced from ~247 to ~130 lines, `backend.py` from ~237 to ~163 lines. The `LLMClient` ABC and `LLMBackend` ABC are preserved as injection seams — all downstream code (`llm_frontend.py`, `unresolved_call.py`, `run.py`) is unchanged. Adding a new provider now requires only a `_ProviderDefaults` entry and a model string mapping in `_resolve_model()`. The `get_backend()` factory signature is preserved for backward compatibility. 8493 tests pass with zero regressions.

---

### ADR-064: LLM-assisted AST repair for deterministic frontends (2026-03-05)

**Context:** When tree-sitter parses malformed source code (e.g. missing closing parentheses, unclosed braces), it produces ERROR/MISSING nodes in the AST. The deterministic frontends emit `SYMBOLIC "unsupported:ERROR"` for these nodes — analysis continues but the broken regions are opaque. For real-world incomplete/malformed code, this limits the coverage of deterministic analysis.

**Decision:** Add a `RepairingFrontendDecorator` that wraps any deterministic frontend via the decorator pattern. When the initial tree-sitter parse has errors: (1) extract error spans from the AST, (2) send them to an LLM with surrounding context to repair syntax, (3) patch the source and re-parse, (4) retry up to N times if errors persist, (5) fall back to the original source if all retries fail. The repair is enabled only when an explicit `repair_client` LLMClient is provided to `get_frontend()`, ensuring zero overhead for the default path. The implementation lives in `interpreter/ast_repair/` with 6 focused modules: `ErrorSpan` (dataclass), `ErrorSpanExtractor` (tree-sitter walker), `SourcePatcher` (byte-level patching), `RepairPrompter` (LLM prompt builder/parser), `RepairConfig` (tuning knobs), and `RepairingFrontendDecorator` (the decorator itself).

**Consequences:** All 15 deterministic languages get AST repair for free via a single decorator. The repair is fully optional — `get_frontend("python")` returns an unwrapped `PythonFrontend` with zero overhead; `get_frontend("python", repair_client=llm)` wraps it. Error detection uses tree-sitter's `is_error`/`is_missing` node properties (not string type names). The `SourcePatcher` applies patches from end-of-file backward to preserve byte offsets. 8535 tests pass with zero regressions (66 new tests added).

---

### ADR-065: Cross-language IR equivalence tests for lowering verification (2026-03-05)

**Context:** The Rosetta suite verifies that each frontend produces clean, structurally consistent IR (entry labels, opcode presence, variance bounds). However, it does not verify that all 15 frontends produce *structurally identical* IR for the same algorithm — only that each individually passes quality thresholds. Without equivalence testing, subtle lowering divergences (redundant stores, extra branches) can accumulate undetected.

**Decision:** Add a new `tests/unit/equivalence/` suite that extracts function bodies via `extract_function_instructions`, strips LABEL pseudo-instructions, and compares the raw opcode sequences across all 15 languages. Two test files cover recursive and iterative factorial. Per-language tests verify extractability, required opcodes, recursive self-calls (rec) / multiply operators (iter), and zero unsupported symbolics. Cross-language tests assert all 15 produce identical opcode sequences.

**Consequences:** Iterative factorial passes — all 15 frontends produce identical opcode sequences. Recursive factorial reveals 4 frontends (kotlin, pascal, rust, scala) emitting minor redundant instructions (extra STORE_VAR, LOAD_VAR, BRANCH). These are semantically correct (VM produces correct results) but structurally divergent. The recursive equivalence test is marked `xfail(strict=True)` pending frontend fixes. 8667 tests pass, 22 xfailed.

### ADR-066: Code quality and architecture analysis tooling (2026-03-05)

**Context:** The project had only Black (formatting) and pytest as dev tooling. As the codebase grew to 150+ modules, there was no automated way to track cyclomatic complexity, maintainability, import boundary violations, or module dependency structure.

**Decision:** Add five analysis tools as dev dependencies — radon (complexity/maintainability metrics), pylint (static linting), import-linter + grimp (architectural boundary contracts), and pydeps (dependency visualization). All run in CI as a report-only job (`continue-on-error: true`). Two import-linter contracts encode existing architectural intent: (1) VM/executor must not import frontends, (2) IR module is a leaf with no imports from other interpreter modules. Pylint is configured in `.pylintrc` with rules disabled that conflict with project style (e.g., `too-few-public-methods` for dataclasses, `missing-docstring`). Only import-linter can actually fail the analysis job — this is intentional since it guards real architecture boundaries.

**Consequences:** `interpreter.run` was initially included in the VM-no-frontend contract but had to be excluded — it's the orchestration layer that legitimately connects frontends to the VM. Pylint scores 9.70/10 on initial run. Radon identifies several D-complexity functions in `dataflow.py`, `cfg.py`, and `run.py` as candidates for future decomposition. All 8670 tests continue to pass.

### ADR-067: Pluggable type ontology for type-aware VM execution (2026-03-05)

**Context:** The VM's BINOP handler uses Python's native operators, causing impedance mismatches for languages with different type semantics (e.g., `5 / 2 = 2.5` in Python vs. `5 / 2 = 2` in HLASM/COBOL integer arithmetic). The IR already carries an optional `type_hint` field on `IRInstruction`, but it was unused. A fixed type system would not accommodate the diverse type semantics across 15+ supported languages.

**Decision:** Implement a three-layer pluggable type system: (1) **TypeGraph** — an immutable DAG of TypeNodes with transitive subtype queries and least-upper-bound computation (default hierarchy: Any → Number/String/Bool/Object/Array, Number → Int/Float); (2) **TypeConversionRules** ABC — maps (operator, left_type, right_type) to a ConversionResult specifying operand coercers and operator overrides (DefaultTypeConversionRules handles Int/Int division→floor division, Int/Float promotion, Bool→Int promotion); (3) **TypeResolver** — composes TypeConversionRules with hint-missing logic (both empty → identity, one missing → assume symmetric, both present → delegate). NullTypeResolver is the null-object default that preserves current VM behavior with no coercion. TypedValue wraps raw values with their type hint for propagation through registers. TypeName StrEnum canonicalises type names.

**Consequences:** The type system is independently testable at each layer (62 new tests). When no type hints are present, behavior is byte-for-byte identical to current behavior (NullTypeResolver returns IDENTITY_CONVERSION). Per-language type semantics can be configured by injecting different TypeConversionRules implementations. The TypeGraph is extensible via `extend()` for language-specific types (e.g., PackedDecimal under Number for COBOL). VM integration (wiring TypeResolver into executor BINOP handling) is deferred to a subsequent commit.

---

### ADR-068: Frontend type annotation extraction — wiring type hints from AST to IR (2026-03-05)

**Context:** ADR-067 established a pluggable type ontology (TypeGraph, TypeConversionRules, TypeResolver) but no frontend populated `IRInstruction.type_hint`. Statically-typed languages carry type annotations in their tree-sitter ASTs (e.g., `int x = 42` in Java, `let x: i32 = 42` in Rust, `x: int` in Python) that frontends were discarding. Without type hints flowing through the IR, the type-aware VM execution layer has nothing to work with.

**Decision:** Extract type annotations from tree-sitter ASTs in all 12 statically-typed frontends (Java, Go, Rust, C, C++, C#, Kotlin, Scala, Pascal, TypeScript, Python, PHP) and wire them into IR instructions via the existing `type_hint` field. Three components: (1) **`type_extraction.py`** — a shared utility module with `LANGUAGE_TYPE_MAP` (per-language raw→canonical mappings for all 12 languages), `normalize_type_hint()` (maps language-specific type names like `i32`→`Int`, `f64`→`Float`, `string`→`String`), `extract_type_from_field()` (reads type from tree-sitter field-named children), and `extract_type_from_child()` (reads type from first matching child node type, for Kotlin's `user_type`). (2) **`emit()` type_hint parameter** — `TreeSitterEmitContext.emit()` accepts `type_hint: str = ""` and passes it through to `IRInstruction`. (3) **Per-frontend wiring** — each frontend's declaration/parameter lowerers call extraction utilities and pass the normalized hint to `ctx.emit()` on SYMBOLIC (params) and STORE_VAR (declarations) instructions. JS, Ruby, and Lua are skipped (no type annotations).

**Consequences:** All 12 frontends now propagate type hints from source annotations to IR. The type-aware VM (TypeResolver + ConversionRules from ADR-067) can consume these hints for operator coercion and type checking. Languages without explicit type annotations (JS, Ruby, Lua) or variables without annotations (Python untyped params, Go short-var-decl `:=`) correctly produce empty `type_hint=""`. Unknown/user-defined types pass through as-is (e.g., `MyClass` stays `MyClass`). 91 new tests (61 normalization + 5 emit context + 28 frontend + 2 integration) with 0 regressions.

---

### ADR-069: Per-frontend type maps — co-locate type maps with frontend classes (2026-03-05)

**Context:** ADR-068 introduced `LANGUAGE_TYPE_MAP` in `type_extraction.py` — a centralized dict mapping all 12 languages' raw type strings to canonical names. While functional, this violated the ports-and-adapters tenet: each frontend should own its own configuration. The centralized dict created coupling between `type_extraction.py` and every language's type vocabulary, and `normalize_type_hint()` required a `Language` enum parameter just to index into the map.

**Decision:** Move per-language type maps from the centralized `LANGUAGE_TYPE_MAP` dict into each frontend class as a `_build_type_map() -> dict[str, str]` method (alongside existing `_build_constants`, `_build_stmt_dispatch`, `_build_expr_dispatch`). `BaseFrontend._lower_with_context()` calls `self._build_type_map()` and passes the result to `TreeSitterEmitContext` via a new `type_map: dict[str, str]` field. `normalize_type_hint()` signature changes from `(raw, language: Language)` to `(raw, type_map: dict[str, str])`. Call sites change from `ctx.language` to `ctx.type_map`. `LANGUAGE_TYPE_MAP` and the `Language` import are deleted from `type_extraction.py`. C++ inherits and extends C's type map via `super()._build_type_map()`. Frontends without type annotations (JS, Ruby, Lua) inherit the empty default.

**Consequences:** Each frontend now owns its type vocabulary, consistent with the ports-and-adapters pattern. `normalize_type_hint()` is a pure function with no dependency on `Language` enum. Adding a new language's type map requires only adding `_build_type_map()` to the frontend class — no centralized file to edit. All 8849 tests pass with 0 regressions.

### ADR-070: Static type inference pass — propagate types from IR instructions to registers and variables (2026-03-06)

**Context:** ADR-067–069 established type hints on IR instructions (frontends extract type annotations, normalize to canonical names, attach to SYMBOLIC/STORE_VAR). However, type information does not propagate through the instruction chain: when `BINOP + %0 %1` executes, it cannot determine that `%0` is `Int` and `%1` is `Float`. A static analysis pass is needed to build a complete type environment before execution.

**Decision:** Introduce `infer_types(instructions, type_resolver) → TypeEnvironment` as a standalone pure function in `interpreter/type_inference.py`. The pass walks the flat IR instruction list once (forward pass) and builds two immutable maps: `register_types` (%0→Int, %4→Float) and `var_types` (x→Int, name→String). Type inference rules: SYMBOLIC uses `inst.type_hint`; CONST infers from literal value; LOAD_VAR copies from `var_types`; STORE_VAR uses explicit `type_hint` or inherits from source register; BINOP delegates to `TypeResolver.resolve_binop()` for result type; UNOP inherits operand type; NEW_OBJECT uses class name; NEW_ARRAY produces "Array". The output `TypeEnvironment` is frozen (MappingProxyType) — computed once, read-only during execution. Register names are globally unique, so the map is flat. Variable names may collide across function scopes; for now, `var_types` is last-write-wins (correct within a single function's instruction sequence). The pass is entirely additive — no existing files modified.

**Consequences:** Any downstream consumer (executor, future optimisation passes) can look up a register or variable's type via `type_env.register_types["%0"]` without needing TypedValue wrapping or parallel mutable state. The pass is decoupled from the executor — it produces data, the executor will consume it in a future step. 54 new tests (36 unit + 18 integration) cover all inference rules, full propagation chains, NullTypeResolver behaviour, and cross-language integration (Java, Go, TypeScript, C, C++).

---

### ADR-071: Infer return types from function/method signatures (2026-03-06)

**Context:** ADR-070 established a static type inference pass that propagates types through IR chains. However, `CALL_FUNCTION` result registers remained untyped for non-constructor calls because no return type information was available. When `int add(int a, int b)` returns a value, the result register of `CALL_FUNCTION add %x %y` had no type — even though the return type is declared in the source.

**Decision:** Three-layer approach: (1) All 12 typed-language frontends (Java, C#, C, C++, Go, Rust, Kotlin, Scala, TypeScript, Python, PHP, Pascal) extract return types from function declarations and emit them as `type_hint` on the function's LABEL instruction. (2) The type inference pass builds a `func_return_types` map from LABEL type_hints and CONST function references. (3) `_infer_call_function` looks up the called function name in `func_return_types` to type the result register. Explicit `type_hint` on CALL_FUNCTION (constructors) takes precedence. Three languages without return type syntax (JavaScript, Ruby, Lua) are left unchanged. CALL_METHOD return type inference (requires class-type → method → return-type resolution) is deferred.

**Consequences:** Function call result registers are now typed for all 12 typed languages, enabling downstream consumers (executor, optimisation passes) to use return type information. The approach is additive — no existing behaviour changed, constructor type_hint overrides still work. 35 new tests (4 unit + 31 integration) cover the inference chain, all 12 frontends, and 3 no-return-type frontends.

---

### ADR-072: Tier 1 + Tier 2 type inference enhancements — 6 new opcode handlers (2026-03-06)

**Context:** ADR-070/071 established the type inference pass handling 10 of 30 opcodes. Several remaining opcodes carry exploitable type information: builtin function calls (`len`, `str`, `range`), RETURN expressions in unannotated functions, boolean/length UNOP operators, CALL_METHOD with class context, STORE_FIELD/LOAD_FIELD for class fields, and ALLOC_REGION/LOAD_REGION for memory regions.

**Decision:** Six enhancements within the existing single-pass `_InferenceContext` model — no architectural changes: (1) **Builtin return types** — `_BUILTIN_RETURN_TYPES` dict maps 12 builtins (len→Int, str→String, range→Array, abs→Number, etc.) as fallback in `_infer_call_function` after type_hint and func_return_types. (2) **RETURN backfill** — `_infer_return` handler looks up the return expression's register type and backfills `func_return_types` for unannotated functions, giving return types to Python/Ruby/JS/Lua functions. (3) **UNOP refinement** — `not`/`!`→Bool, `#`→Int, others pass-through. (4) **CALL_METHOD return types** — class scope tracking via `class_`/`end_class_` LABEL prefixes, method return type recording in `_infer_const`, `_infer_call_method` handler with fallback to global function table. (5) **Class field type table** — `_infer_store_field` records field types per class, `_infer_load_field` looks them up. (6) **ALLOC_REGION/LOAD_REGION tagging** — trivial handlers for Region and Array types. Three new context fields: `current_class_name`, `class_method_types`, `field_types`.

**Consequences:** The inference pass now handles 16 of 30 opcodes. 39 new tests (30 unit + 9 integration) cover all 6 features. Unannotated functions in dynamically-typed languages now get return types when they return typed expressions. Class method calls and field accesses are now typed. No regressions — all 9059 tests pass.

### ADR-073: Tier 3 type inference — self/this typing, CALL_UNKNOWN, LOAD_INDEX/STORE_INDEX (2026-03-06)

**Context:** ADR-072 brought the inference pass to 16 of 30 opcodes. Three gaps remained that carry useful type information: (1) `param:self`/`param:this` arriving untyped breaks field tracking for OOP languages, (2) CALL_UNKNOWN (indirect calls through registers) was unhandled, (3) LOAD_INDEX/STORE_INDEX had no element type tracking. The remaining 11 opcodes (BRANCH, BRANCH_IF, THROW, TRY_PUSH, TRY_POP, WRITE_REGION, SET_CONTINUATION, RESUME_CONTINUATION, PHI, COMPARE, NOP) are pure control flow / side-effect with no result registers to type.

**Decision:** Three enhancements within the existing single-pass model: (1) **self/this class typing** — `_infer_symbolic` extended to recognize `param:self`, `param:this`, `param:$this` inside class scope and assign the enclosing class name as the register type; explicit `type_hint` takes priority; covers Python/Ruby, Java/C#/JS/TS/C++/Kotlin/Scala/Go, PHP. (2) **CALL_UNKNOWN handler** — new `register_source_var` context field populated by LOAD_VAR maps registers back to variable names; `_infer_call_unknown` resolves the target register to a function name via this mapping, then tries `func_return_types` and `_BUILTIN_RETURN_TYPES`. (3) **Array element type tracking** — new `array_element_types` context field; `_infer_store_index` records element types keyed by array register; `_infer_load_index` looks them up; last-write-wins semantics.

**Consequences:** The inference pass now handles 19 of 30 opcodes (the remaining 11 have no typeable result). 18 new tests (15 unit + 3 integration) cover all 3 features. self/this typing unlocks field type tracking for all OOP languages — Python `self.age = 5; return self.age` now produces a fully-typed chain. No regressions — all 9077 tests pass.

---

### ADR-074: Type-aware register resolution via `_resolve_typed_reg` (2026-03-06)

**Context:** Python's `/` operator always produces a `float`, so array index computation (e.g. `4 / 2 → 2.0`) generates float register values. `STORE_INDEX` and `LOAD_INDEX` use `str(idx_val)` as heap keys, meaning `str(2.0) → "2.0"` and `str(2) → "2"` — a silent data loss bug where stored values become unretrievable. The type inference pass (ADR-070–073) already computes `TypeEnvironment.register_types` (e.g. `"%4" → "Int"`), and `DefaultTypeConversionRules.coerce_assignment` already knows how to cast (Float→Int via `math.trunc`). These were not wired together at runtime.

**Decision:** Add a `_resolve_typed_reg(vm, operand, type_env, conversion_rules)` wrapper in `vm.py` that resolves a register value and coerces it to the type declared by the `TypeEnvironment` using `TypeConversionRules.coerce_assignment`. A `_typed_resolve(vm, operand, kwargs)` helper in `executor.py` extracts `type_env` and `conversion_rules` from handler kwargs. All opcode handlers that previously called `_resolve_reg` now call `_typed_resolve` instead. `_resolve_reg` itself remains unchanged — handlers opt in explicitly via the wrapper. `TypeEnvironment` and `TypeConversionRules` are threaded through `LocalExecutor.execute()`, `_try_execute_locally()`, `execute_cfg()`, `execute_cfg_traced()`, and `run()`. Default parameters (`_EMPTY_TYPE_ENV`, `_IDENTITY_RULES`) ensure full backward compatibility — tests that don't provide a type environment get identity (no-op) coercion. `run()` now calls `infer_types()` after lowering and passes the resulting `TypeEnvironment` and `DefaultTypeConversionRules` into `execute_cfg()`.

**Consequences:** Float register values from division are coerced to int when the type environment declares them as Int, fixing the heap key mismatch bug. All existing tests continue to pass unchanged (9096 tests, 4 skipped, 22 xfailed). 19 new tests: 14 unit tests for `_resolve_typed_reg` and `_runtime_type_name`, 3 updated bug-proving tests (xfail markers removed), 2 integration tests verifying end-to-end division→index round-trip. **Superseded by ADR-075.**

---

### ADR-075: Move type coercion from read-time to write-time in `apply_update` (2026-03-06)

**Context:** ADR-074 introduced `_typed_resolve` in `executor.py`, which coerced register values at every read site (every opcode handler). This meant every handler threaded `type_env` and `conversion_rules` through kwargs, creating pervasive coupling. The `TypeEnvironment` and `TypeConversionRules` were passed through `LocalExecutor.execute()` and `_try_execute_locally()` solely so individual handlers could access them.

**Decision:** Move coercion to `apply_update` in `vm.py` — the single point where register values are written to the VM. A new `_coerce_value(val, reg, type_env, conversion_rules)` function applies coercion to a value given a register name. `apply_update` gains `type_env` and `conversion_rules` parameters (defaulting to `_EMPTY_TYPE_ENV` / `_IDENTITY_RULES`) and calls `_coerce_value` in the register-writes loop after `_deserialize_value`. `_resolve_typed_reg` is refactored to delegate to `_resolve_reg` + `_coerce_value` — its public contract is unchanged. All opcode handlers revert to plain `_resolve_reg`. The `_typed_resolve` helper, `_EMPTY_TYPE_ENV`, and `_IDENTITY_RULES` constants are removed from `executor.py`. `type_env` / `conversion_rules` are removed from `LocalExecutor.execute()` and `_try_execute_locally()` signatures. In `run.py`, all three `apply_update` call sites (`_handle_call_dispatch_setup`, `execute_cfg` main loop, `execute_cfg_traced` main loop) gain the type parameters.

**Consequences:** Coercion happens exactly once per register write rather than at every read. Handlers are simpler — no type-threading kwargs. The `_resolve_typed_reg` API remains available for direct use (e.g. tests). All 9096 tests pass (4 skipped, 22 xfailed).

---

### ADR-076: Eliminate `IRInstruction.type_hint` via `TypeEnvironmentBuilder` (2026-03-06)

**Context:** `IRInstruction.type_hint` was an indirection: frontends embedded type annotations on instructions during lowering, then `infer_types()` extracted them back into maps (`register_types`, `var_types`, `func_return_types`, `func_param_types`). The frontend already knows which register/variable/function it's typing at emit time, so the instruction-level field was unnecessary coupling — type metadata on a data structure meant for computation and control flow.

**Decision:** Two-phase removal. **Phase 1:** Introduce `TypeEnvironmentBuilder` (mutable dataclass with `register_types`, `var_types`, `func_return_types`, `func_param_types` dicts and a `build()` method producing frozen `TypeEnvironment`). `TreeSitterEmitContext` gains a `type_env_builder` field and routing logic: `emit()` with `type_hint=` populates the builder instead of the instruction. `infer_types()` accepts a `type_env_builder` parameter and pre-populates its `_InferenceContext` from it, eliminating all `inst.type_hint` reads. `Frontend` ABC and subclasses expose `type_env_builder` property. `run.py` passes `frontend.type_env_builder` to `infer_types()`. **Phase 2:** Remove `type_hint` field from `IRInstruction` entirely. Replace `emit(..., type_hint=)` with explicit seed helpers (`seed_func_return_type`, `seed_register_type`, `seed_var_type`, `seed_param_type`) on `TreeSitterEmitContext`. Update ~60 frontend call sites across 13 language frontends. The `_route_type_hint` method is replaced by `_track_label` (label/function context tracking only) plus the four seed helpers.

**Consequences:** IR instructions are now purely about computation and control flow — no type metadata. Type annotations flow directly from frontends into the builder, eliminating the extract-then-reassemble round-trip. The builder pattern makes type seeding explicit and testable. All 9104 tests pass (4 skipped, 22 xfailed).

---

### ADR-079: Comprehensive cross-language type inference integration tests (2026-03-06)

**Context:** The type inference engine supports ~12 distinct inference scenarios (BINOP resolution, UNOP refinement, return backfill, typed param seeding, field tracking, CALL_METHOD return types, NEW_OBJECT typing), but integration tests only covered a subset per language. For example, BINOP resolution and UNOP refinement had zero cross-language tests.

**Decision:** Add 10 new parametrized test classes to `tests/integration/test_type_inference.py`, covering every inference scenario across all applicable languages (up to 15). Each class uses `pytest.fixture(params=...)` with a `SOURCES` dict mapping language → source snippet, providing clear per-language failure messages. This TDD pass also exposed three IR lowering gaps documented below.

**IR Lowering Gaps Discovered:**

1. **Scala frontend: `this.field` in getter lowered as `LOAD_VAR` instead of `LOAD_FIELD`** — In Scala class methods, `this.age` access produces `load_var age` rather than `load_field %reg age`. `STORE_FIELD` via `this.age = ...` in setter works correctly. The getter path does not recognise the `field_access` node as a field dereference. Marked as `xfail` in `TestFieldTypeTrackingOOP`.

2. **Ruby frontend: implicit return does not wire expression value to `RETURN`** — Ruby's `def get_age; @age; end` (implicit return) generates `LOAD_FIELD` for `@age` but returns `const None` instead of the loaded register. Explicit `return @age` is needed for the value to propagate. This prevents return backfill and CALL_METHOD result typing for implicit-return methods. Marked as `xfail` in `TestCallMethodReturnTypesOOP`.

3. **Kotlin/Scala expression-bodied functions: return value not wired** — Kotlin `fun f() = 42` computes `const 42` but returns `const None`. Scala `def f() = 42` does not even capture the literal. Block-body functions with explicit `return` work correctly. Kotlin backfill test uses block body as workaround; Scala excluded from return backfill tests.

**Consequences:** Test count increased from 9020 to 9243 (223 new test IDs). 3 new xfails document genuine frontend gaps. All 15 languages now have BINOP, comparison, and UNOP coverage. Field tracking covers 8 OOP languages, CALL_METHOD covers 9, and NEW_OBJECT covers 5 additional languages.

---

### ADR-080: Fix 3 IR lowering gaps in Scala, Kotlin, and Ruby frontends (2026-03-06)

**Context:** ADR-079 exposed three frontend lowering gaps sharing the same root cause: function bodies unconditionally emit `CONST default_return_value` + `RETURN`, discarding the actual last expression value. This blocked return backfill, CALL_METHOD result typing, and field tracking for affected languages.

**Decision:** Fix all three gaps with minimal, targeted changes to each frontend's declaration lowerer:

1. **Scala expression-bodied functions** (`interpreter/frontends/scala/declarations.py`): In `lower_function_def`, detect whether `body_node` is a bare expression (not in `block_node_types` and no `stmt_dispatch` handler). If so, `lower_expr` it and emit RETURN with the result, skipping the default nil return. Fixes both `this.age` getters (GAP-001) and `def f() = 42` (GAP-003).

2. **Kotlin expression-bodied functions** (`interpreter/frontends/kotlin/declarations.py`): `_lower_function_body` now returns the register of the last expression if the body is expression-bodied. `lower_function_decl` wires that register to RETURN instead of nil.

3. **Ruby implicit return** (`interpreter/frontends/ruby/declarations.py`): New `_lower_body_with_implicit_return` helper detects when the last named child of a method body is an expression (not a statement). Both `lower_ruby_method` and `lower_ruby_singleton_method` use this helper.

**Consequences:** All 3 xfail markers removed from `tests/integration/test_type_inference.py`. Scala added to `TestReturnBackfillAllLanguages`. Test count: 9258 passed, 4 skipped, 22 xfailed (down from 25 xfailed).

---

### ADR-081: Builtin method return types and UNOP `~` → Int (2026-03-07)

**Context:** The type inference pass handled CALL_METHOD return types only via user-defined class method tables and a func_return_types fallback. Common builtin methods like `.upper()`, `.split()`, `.find()`, `.startswith()` — whose return types are universally known — were left untyped when no user-defined class method matched. Separately, the UNOP `~` (bitwise NOT) relied on operand-type propagation, which produced no type when the operand was untyped, even though `~` always produces an integer.

**Decision:** Two additions to `interpreter/type_inference.py`:

1. **Builtin method return types table** (`_BUILTIN_METHOD_RETURN_TYPES`): 60+ method names mapped to their canonical return types — String methods (`.upper()`, `.lower()`, `.strip()`, `.replace()`, etc.), Int methods (`.find()`, `.index()`, `.count()`, `.size()`), Bool methods (`.startswith()`, `.endswith()`, `.contains()`, `.includes()`), and Array methods (`.split()`, `.keys()`, `.values()`, `.items()`). Cross-language coverage includes Python, JavaScript, Java, Ruby, Kotlin, Go, and Lua naming conventions. Wired as the final fallback in `_infer_call_method` — user-defined class methods and func_return_types take priority.

2. **UNOP `~` → Int**: Added `"~": TypeName.INT` to `_UNOP_FIXED_TYPES`.

**Consequences:** Test count: 9289 passed, 4 skipped, 22 xfailed (31 new tests: 8 unit, 23 integration across Python/JavaScript/Java/Ruby/Kotlin). Builtin method types now propagate through STORE_VAR, BINOP, and downstream instructions without requiring frontend type annotations.

---

### ADR-082: Fixpoint type inference for forward reference resolution (2026-03-07)

**Context:** The type inference pass (`infer_types`) walked the IR instruction list once, top-to-bottom. When function A calls function B and B is defined later in the IR (common in Python, JavaScript, Ruby where source order doesn't match call order), the call site has no return type information — B's RETURN hasn't been processed yet. This cascades: A's return type also can't be backfilled, and variables assigned from A's result stay untyped.

**Decision:** Replace the single `for inst in instructions` loop with a fixpoint loop that repeats until no new types are discovered. Convergence is measured by `len(register_types) + len(func_return_types)` — when neither dict grows, the loop terminates. All existing handler guards (`if result_reg in register_types: return`, `if func_label in func_return_types: return`, etc.) are already correct for multi-pass: they prevent clobbering types from earlier passes while allowing unfilled gaps to be resolved on subsequent passes.

**Consequences:** Test count: 9298 passed, 4 skipped, 22 xfailed (9 new tests: 5 unit, 4 integration across Python/JavaScript/Ruby). Forward reference chains of arbitrary depth resolve correctly (tested with a→b→c chain). Programs without forward references converge in one pass (no performance regression). The fixpoint loop typically runs 2 passes for real code with forward references.

---

### ADR-083: Class inheritance via linearized parent chain in FunctionRegistry (2026-03-08)

**Context:** The VM currently has no concept of class inheritance. Classes are lowered to labeled IR blocks; `NEW_OBJECT` creates a heap object tagged with a `type_hint` string; `CALL_METHOD` resolves methods via a flat `registry.class_methods[type_hint][method_name]` lookup. This works for single-class dispatch but fails when a subclass inherits methods from a parent: `Dog extends Animal` where `Dog` doesn't override `getLegs()` — the executor looks for `getLegs` in `Dog`'s method table, doesn't find it, and falls through to the symbolic resolver. There is no parent chain to walk. Similarly, `super.method()` is emitted as a raw `CALL_FUNCTION("super", ...)` which goes symbolic.

Multiple frontends already parse inheritance syntax — Java's tree-sitter grammar exposes a `superclass` field on `class_declaration`, Python exposes parent classes via `argument_list` on `class_definition` — but no frontend extracts or records these relationships.

**Decision:** Add a linearized parent chain to `FunctionRegistry` and walk it during method dispatch. The design has three layers:

1. **Registry (data model):** Add `class_parents: dict[str, list[str]]` to `FunctionRegistry`. Each entry maps a class name to its **already-linearized** method resolution order (MRO), excluding the class itself. For `class Dog extends Animal`, the entry is `{"Dog": ["Animal"]}`. For Python's `class C(A, B)` with C3 linearization, the entry is `{"C": ["A", "B"]}` (the frontend computes the order).

2. **Frontends (extraction):** Each frontend extracts inheritance relationships during class lowering and records them in the emit context. The `_scan_classes` function in `registry.py` is extended to detect inheritance metadata emitted as IR annotations or by parsing the class reference format. The language-specific MRO computation (trivial linear chain for Java/C#/Kotlin; C3 linearization for Python; trait linearization for Scala/Ruby) is the frontend's responsibility — the registry stores only the final resolved order.

3. **Executor (resolution):** `_handle_call_method` is extended with a fallback loop: when `class_methods[type_hint]` does not contain the requested method, iterate through `class_parents[type_hint]` and check each parent's method table. The first match wins. This is a single, language-agnostic loop — all language-specific complexity is in how the parent list was constructed.

**`super` handling:** `super.method()` is resolved by looking up the method starting from `class_parents[current_class][0]` (the immediate parent), skipping the current class's own method table. The frontend emits enough context (the enclosing class name) for the executor to determine where to start the search.

**Why not vtable lowering (LLVM-style)?** An alternative is to have each frontend copy parent methods into the child's IR block during lowering, so the flat registry already contains everything. This was rejected because: (a) it duplicates method-copying logic across 15 frontends; (b) it loses the inheritance relationship, which is valuable for code analysis; (c) it doesn't naturally handle `super`, which requires knowing the parent chain at dispatch time.

**Why a pre-linearized list?** The alternative is storing raw parent declarations and computing MRO at dispatch time. Pre-linearization was chosen because: (a) MRO computation is a frontend concern — each language has different rules; (b) the executor stays language-agnostic with a simple linear scan; (c) the list is computed once at lowering time, not on every method call.

**Language-specific MRO strategies:**

| Language | Inheritance model | MRO strategy |
|----------|-------------------|--------------|
| Java, C#, Kotlin | Single class inheritance (+ interfaces) | Linear chain: `[Parent, Grandparent, ...]` |
| Python | Multiple inheritance | C3 linearization |
| Ruby | Single inheritance + mixins | Linear: `[Mixin2, Mixin1, Parent]` (last included first) |
| Scala | Single class + traits | Trait linearization (right-to-left, depth-first, deduplicated) |
| C++ | Multiple inheritance (virtual/non-virtual) | Frontend resolves; virtual bases deduplicated |
| JavaScript/TypeScript | Prototype chain (no `extends` in class sense until ES6) | Single prototype chain |
| Go | Embedding (not inheritance) | Flat — embedded struct methods promoted to embedder |
| PHP | Single inheritance + traits | Linear chain + trait `use` order |
| C, Rust, Lua, Pascal | No class inheritance | Not applicable |

**Implementation plan:**

Phase 1 — Data model and single inheritance:
- Add `class_parents` field to `FunctionRegistry`
- Extend `_scan_classes` to populate parent chains from IR metadata
- Add parent-chain fallback loop to `_handle_call_method`
- Implement extraction in Java frontend (simplest case: `superclass` field)
- Unit tests: inherited method dispatch, `super` calls
- Integration tests: Java polymorphism with inherited methods

Phase 2 — Remaining single-inheritance languages:
- Python, C#, Kotlin, Ruby, PHP, JavaScript/TypeScript, Scala
- Each frontend extracts its specific syntax and computes MRO

Phase 3 — Multiple inheritance:
- Python C3 linearization
- Scala trait linearization
- C++ virtual base classes (if needed)

**IR changes:** None. The 27-opcode IR is unchanged. Inheritance metadata is conveyed either through an extension to the `<class:Name@label>` reference format (e.g., `<class:Dog@label:Animal>`) or through a new metadata instruction that the registry scanner picks up. The preferred approach is extending the class reference format, as it keeps inheritance co-located with the class definition and requires no new opcodes.

**Consequences:** Method dispatch for inherited methods will resolve concretely instead of going symbolic. `super` calls will dispatch to the correct parent method. The flat `class_methods` table remains the primary lookup; the parent chain is only consulted on cache miss. No performance impact for classes without inheritance. The executor remains language-agnostic — all MRO complexity is pushed to frontends, consistent with the ports-and-adapters architecture (ADR-002).

---

### ADR-084: Function-scoped variable types in type inference (2026-03-08)

**Context:** The type inference pass tracked variable types in a flat `dict[str, str]` (`var_types`), keyed only by variable name. When two functions use the same variable name with different types (e.g., `x = 42` in `make_int()` and `x = "hello"` in `make_str()`), the first STORE_VAR wins and pollutes the second function's type — `make_str` would incorrectly report `Int` for `x` instead of `String`. Register types (`%0`, `%1`, ...) are globally unique and unaffected.

**Decision:** Replace the flat `var_types: dict[str, str]` with a nested `scoped_var_types: dict[str, dict[str, str]]`, keyed by function label (from LABEL instructions). A `_GLOBAL_SCOPE = ""` key holds file-level variables. Lookup follows function-scope-first, global-scope-fallback semantics. The final `TypeEnvironment.var_types` is assembled by flattening all scopes (later scopes overwrite earlier ones for same-named variables, which is acceptable since the flat dict is a summary view).

**Alternatives considered:**
- **Prefixed variable names** (e.g., `func_f::x`): Would leak implementation details into the public `var_types` API and break downstream consumers expecting plain variable names.
- **No change** (document as known limitation): Rejected because the bug silently produces wrong types, which propagates to return type inference and function signatures.

**Consequences:** Variable types are correctly isolated per function. Global variables remain visible inside functions via fallback lookup. The public `TypeEnvironment.var_types` API is unchanged (flat dict). Cross-language integration tests verify scoping across all 15 languages.

---

### ADR-085: Parameterized types via TypeExpr algebraic data type (2026-03-08)

**Context:** The type system represented all types as flat strings (`"Int"`, `"String"`, `"Array"`). This meant C pointer types (`int*`, `int**`) collapsed to their base type (`"Int"`), losing pointer information. More broadly, parameterized types like `Array<String>`, `Map<String, Int>`, and `Pointer<Int>` couldn't be represented, queried for subtype relationships, or distinguished from their raw constructors.

**Decision:** Introduce a `TypeExpr` algebraic data type with three forms:

```python
@dataclass(frozen=True)
class TypeExpr: ...                          # base

@dataclass(frozen=True)
class ScalarType(TypeExpr):                  # e.g. Int, String
    name: str

@dataclass(frozen=True)
class ParameterizedType(TypeExpr):           # e.g. Pointer[Int], Map[String, Int]
    constructor: str
    arguments: tuple[TypeExpr, ...]
```

Each `TypeExpr` has a canonical string representation via `__str__` that round-trips through `parse_type()`. This means parameterized type *strings* (like `"Pointer[Int]"`) flow through the existing string-based `TypeEnvironment` and type inference without requiring immediate migration of all consumers. The `TypeExpr` ADT is used for construction/formatting and for structured queries (subtype checks, LUB) via new `TypeGraph` methods.

**TypeGraph extensions:**
- `is_subtype_expr(child, parent)` — covariant: `Pointer[Int] ⊆ Pointer[Number]` iff `Int ⊆ Number`; `Pointer[Int] ⊆ Pointer` (raw constructor is supertype)
- `common_supertype_expr(a, b)` — pairwise LUB: `LUB(Pointer[Int], Pointer[Float]) = Pointer[Number]`

**New TypeName constants:** `Pointer`, `Map`, `Region` added to the type ontology DAG as children of `Any`.

**C/C++ frontend integration:** The C frontend detects `pointer_declarator` nesting in declarations and parameters, counts the depth, and wraps the base type using `pointer(scalar(base))`. `int **pp` becomes `"Pointer[Pointer[Int]]"`. The C++ frontend reuses C's `lower_declaration` and gets this for free. Previously, bare pointer declarations (e.g., `float *fp;`) were silently dropped — now they emit proper `STORE_VAR` with pointer types.

**Migration strategy:** `TypeEnvironment` now stores `TypeExpr` objects (Phase 1 complete). `TypeEnvironmentBuilder` stays string-based; `build()` converts via `parse_type()`. Future phases will:
1. ~~Migrate `TypeEnvironment` internals to store `TypeExpr` objects~~ (DONE — ADR-085a)
2. ~~Extract parameterized types from Java/C#/Scala/Kotlin generics~~ (DONE — ADR-086)
3. Add type variable support for true generics

**Type representation boundary (updated 2026-03-08):** The type inference engine (`_InferenceContext`) now operates on `TypeExpr` objects internally.  The `parse_type()` boundary has moved upstream: `infer_types()` parses the builder's string seeds into `TypeExpr` before starting the inference walk.  After convergence, `TypeEnvironment` is built directly from `TypeExpr` values — no roundtrip through strings.

- **Frontends** extract type text from ASTs → `TreeSitterEmitContext.seed_*()` calls `parse_type()` → `TypeEnvironmentBuilder` (stores `dict[str, TypeExpr]`)
- **`infer_types()`** copies builder's `TypeExpr` values directly — no parsing needed
- **`_InferenceContext`** operates on `TypeExpr` — all registers, vars, return types, field types, class method types store `TypeExpr`; `current_class_name` is `TypeExpr`; `field_types` and `class_method_types` use `TypeExpr` outer keys (no `str()` conversion for dict lookup)
- **`UNKNOWN` sentinel** (`UnknownType` singleton) replaces empty strings as the "type not yet known" marker; falsy for `if expr:` checks
- **Builtin lookup tables** (`_BUILTIN_RETURN_TYPES`, `_BUILTIN_METHOD_RETURN_TYPES`) store `TypeExpr` values
- **`TypeResolver`** and **`TypeConversionRules`** accept/return `TypeExpr`
- **`ConversionResult.result_type`** is `TypeExpr` (default `UNKNOWN`)
- **`TypeEnvironment`** stores frozen `TypeExpr` objects with string-compatible equality

**Alternatives considered:**
- **String conventions without ADT** (e.g., `"Pointer[Int]"` with ad-hoc parsing): Rejected — fragile for nesting, no structured equality/hashing, no subtype logic.
- **Keep inference on strings** (original decision 2026-03-08): Superseded — type algebra operations (unification, LUB, variance) require structured types during inference, not just at the output boundary.

**Consequences:** C pointer types now carry full type information through the pipeline. The TypeExpr ADT provides a foundation for future parameterized type extraction across all frontends. TypeGraph can answer subtype and LUB questions for arbitrary nesting depth. No existing tests broken — all changes are additive.

### ADR-086: Generic type extraction for Java, C#, Scala, Kotlin (2026-03-08)

**Context:** After establishing the parameterised type system (ADR-085), the next step was extracting generic types from language-specific AST nodes so that `List<String>` in Java becomes `List[String]` in the type environment, not the raw source text `"List<String>"`.

**Decision:** Add structural generic type extraction in `type_extraction.py` that walks the tree-sitter AST for generic type nodes and recursively decomposes them into bracket notation, normalising each component type through the frontend's `type_map`. This is a shared utility used by all four frontends.

**AST patterns handled:**
- Java: `generic_type` → `type_identifier` + `type_arguments`
- C#: `generic_name` → `identifier` + `type_argument_list`
- Scala: `generic_type` → `type_identifier` + `type_arguments` (Scala uses `[]` in source but tree-sitter uses the same node structure)
- Kotlin: `user_type` → `type_identifier` + `type_arguments` → `type_projection` (unwrapped)

**Key functions:**
- `extract_normalized_type(ctx, node, field_name, type_map)` — replaces the `extract_type_from_field` + `normalize_type_hint` combo for frontends with generics
- `extract_normalized_type_from_child(ctx, node, child_types, type_map)` — same but for languages using child-based type extraction (Kotlin)
- `_decompose_generic()` — recursive decomposition with per-component normalisation

**Type inference priority fix:** `_InferenceContext.store_var_type()` now checks `lookup_var_type()` across all scopes before writing, ensuring seeded types from explicit declarations take precedence over inferred types from constructor calls (e.g., `List<String> items = new ArrayList<>()` keeps `List[String]`, not `ArrayList<>`).

**Consequences:** Generic type declarations in Java, C#, Scala, and Kotlin now produce structured parameterised types in the type environment. Inner types are normalised (e.g., Java's `Integer` → `Int`). Nested generics work recursively. 25 unit tests + 9 integration tests added. All 9543 existing tests pass.

### ADR-087: Array element type promotion to Array[ElementType] (2026-03-08)

**Context:** The type inference engine tracked array element types (via STORE_INDEX) in `array_element_types` but discarded this information when building the final `TypeEnvironment`. Variables typed as `Array` contained no information about their element type.

**Decision:** After inference converges, promote variables and registers typed as `Array` to `Array[ElementType]` when the element type is known from STORE_INDEX operations. Also propagate element types through LOAD_VAR so that `items = [1, 2, 3]; x = items[0]` correctly infers `x` as `Int`.

**Implementation:**
- New `var_array_element_types` dict in `_InferenceContext` maps variable names to their known element types
- `_infer_store_var` records element type associations when storing an array register into a variable
- `_infer_load_var` propagates element types from variables to loaded registers
- `_promote_array_element_types()` runs after inference converges, upgrading `Array` → `Array[ElementType]`
- Type inference priority: seeded types from explicit declarations (in any scope) take precedence over inferred types from constructor calls

**Consequences:** `items = [1, 2, 3]` now produces `var_types["items"] == "Array[Int]"` across Python, JavaScript, Ruby, and any language using NEW_ARRAY + STORE_INDEX. 5 unit tests + 4 integration tests added. All 9552 tests pass.

### ADR-088: Union types, Optional, and union-aware type inference (2026-03-08)

**Context:** The type system could not represent values that may be one of several types. Variables assigned different types on different code paths (e.g. `x = 5; x = "hello"`) retained only the first type. TypeScript union types (`string | number`), Kotlin nullable (`String?`), Rust `Option<T>`, and Python `Union[str, int]` were all unrepresentable.

**Decision:** Add `UnionType(members: frozenset[TypeExpr])` as a fourth TypeExpr variant alongside ScalarType, ParameterizedType, and UnknownType.

**Design details:**
- `union_of(*types)` constructor handles flattening nested unions, deduplication, singleton elimination (`Union[Int]` → `Int`), and UNKNOWN filtering
- Canonical string form: `"Union[Int, String]"` with alphabetically sorted members for deterministic hashing
- `parse_type("Union[Int, String]")` and `parse_type("Optional[Int]")` produce UnionType (Optional is sugar for `Union[T, Null]`)
- `optional(T)`, `is_optional(t)`, `unwrap_optional(t)` convenience functions
- `Null` is `ScalarType("Null")` — no new class needed

**TypeGraph extensions:**
- `is_subtype_expr`: `Union[A, B] ⊆ T` iff all members are subtypes of T; `T ⊆ Union[A, B]` iff T is subtype of at least one member
- `common_supertype_expr`: when either operand is a union, merge all members into a single union

**Inference engine:**
- `store_var_type` widened to union-aware: if a variable already has inferred type T and a new assignment has type S ≠ T, the variable type becomes `Union[T, S]`
- Seeded types (from `TypeEnvironmentBuilder.var_types`) are tracked via `_seeded_var_names` frozenset and are never widened — explicit declarations always take precedence
- Fixpoint convergence guaranteed: union widening is monotonic (types only grow, never shrink)

**Alternatives considered:**
- **Widen to common supertype** (e.g. `Int + String → Any`): Rejected — loses information. Union preserves all possible types.
- **Branch-aware narrowing** (track types per CFG path): Deferred to Phase 5 (Type Narrowing). Current linear-pass widening is simpler and handles the common case.
- **Separate NullType class**: Rejected — `ScalarType("Null")` is sufficient and avoids adding another class.

**Consequences:** 51 new tests (30 unit for UnionType/Optional, 13 unit for TypeGraph union subtype/LUB, 4 unit for inference widening, 4 integration for Python/JS source programs). All 9664 tests pass. No existing test changed.

### ADR-089: Function types with contravariant subtyping (2026-03-08)

**Context:** The type system had no representation for callable types. Functions stored as CONST references lost their type information — a variable holding a function reference was typed as a plain string or remained unknown. This prevented reasoning about higher-order functions, callback types, and indirect calls through typed function references.

**Decision:** Add `FunctionType(params: tuple[TypeExpr, ...], return_type: TypeExpr)` as a fifth TypeExpr variant.

**Design details:**
- Canonical string form: `Fn(Int, String) -> Bool` — parens for params, arrow for return
- `fn_type(params, ret)` convenience constructor
- Parser extended: `_parse_name` stops at `(` and `)`, `_parse_function_type` handles `Fn(...)  -> T` syntax
- `parse_type("Fn(Int, String) -> Bool")` round-trips correctly through `str()`

**TypeGraph extensions:**
- Subtype: `Fn(A1, A2) -> R1 ⊆ Fn(B1, B2) -> R2` iff params are contravariant (`B1 ⊆ A1`, `B2 ⊆ A2`) and return is covariant (`R1 ⊆ R2`). Arity mismatch → not a subtype.
- LUB: same-arity functions get pairwise LUB on params (intersection semantics) and return (union semantics). Different arities → `Any`.

**Inference engine:**
- CONST function references: when the referenced function has known parameter and return types, the register is typed as `FunctionType` instead of leaving it unknown
- CALL_UNKNOWN: if the target register holds a `FunctionType`, the call result register gets the function's return type

**Alternatives considered:**
- **Arrow syntax `(Int, String) => Bool`**: Rejected — conflicts with potential lambda syntax. `Fn(...)` prefix is unambiguous.
- **Separate CallableType class**: Rejected — `FunctionType` with params tuple is sufficient. Overloaded callables can use `UnionType` of multiple `FunctionType`s.

**Consequences:** 54 new tests (31 unit for FunctionType/parsing, 15 unit for TypeGraph function subtype/LUB, 5 unit for inference, 3 integration for Python/Java source programs). All 9718 tests pass. No existing test changed.

### ADR-090: Tuple types with per-index element tracking (2026-03-08)

**Context:** Python tuple literals `(1, "hello")` lowered via `NEW_ARRAY` with a `"tuple"` kind marker but were typed identically to arrays (`Array`). This lost the heterogeneous, fixed-size nature of tuples — `t[0]` on a `Tuple[Int, String]` should resolve to `Int`, not an unspecific element type.

**Decision:** Reuse `ParameterizedType("Tuple", ...)` (no new TypeExpr class) with per-index element type tracking in the inference engine.

**Design details:**
- `tuple_of(*elements)` convenience constructor returns `ParameterizedType("Tuple", tuple(elements))`
- `TypeName.TUPLE` added to constants; `TypeNode("Tuple", parents=("Any",))` added to `DEFAULT_TYPE_NODES`
- `_InferenceContext` extended with: `const_values` (register → raw CONST string), `tuple_registers` (set of registers created via `NEW_ARRAY "tuple"`), `tuple_element_types` (register → {index: TypeExpr}), `var_tuple_element_types` (var name → {index: TypeExpr})
- `_infer_new_array`: detects `"tuple"` first operand, types register as `Tuple` (not `Array`), marks it as tuple
- `_infer_store_index`: for tuple registers, records per-index element type using `const_values` to resolve the integer index
- `_infer_load_index`: for tuple registers, resolves the specific element type at the known index
- `_promote_tuple_element_types`: after fixpoint, promotes `Tuple` registers/variables to `Tuple[T1, T2, ...]` using sorted index order

**TypeGraph:** Already handled — `ParameterizedType` subtype/LUB with same constructor + pairwise elements covers `Tuple[A, B] ⊆ Tuple[C, D]` (covariant) and length-mismatch rejection.

**Alternatives considered:**
- **Dedicated TupleType class**: Rejected — `ParameterizedType("Tuple", ...)` is sufficient and reuses existing infrastructure.
- **Array with union element type**: Rejected — `Array[Union[Int, String]]` loses positional information. Tuples are heterogeneous by position.

**Consequences:** 28 new tests (9 unit for tuple_of constructor/parsing, 11 unit for TypeGraph subtype/LUB, 4 unit for inference, 4 integration for Python source programs). All 9746 tests pass. No existing test changed.

### ADR-091: Type aliases with transitive resolution (2026-03-08)

**Context:** C `typedef int UserId;`, TypeScript `type StringMap = Map<string, string>`, and similar type alias declarations were either ignored or emitted as runtime CONST/STORE_VAR instructions. Variable types seeded as alias names (e.g., `UserId`) were never resolved to their underlying types.

**Decision:** Add a type alias registry (`type_aliases: dict[str, TypeExpr]`) to `TypeEnvironmentBuilder`, `_InferenceContext`, and `TypeEnvironment`. Resolve aliases at the seeding boundary in `infer_types()`.

**Design details:**
- `_resolve_alias(t, aliases)` expands `ScalarType` names through the alias registry transitively (with depth limit for cycle protection). `ParameterizedType` arguments are resolved recursively.
- `_resolve_aliases_in_dict(d, aliases)` resolves all values in a dict.
- `infer_types()` resolves all seeded register types, var types, func return types, and param types through the alias registry before starting the inference walk.
- `TypeEnvironment.type_aliases` exposes the alias registry in the final result.
- `TreeSitterEmitContext.seed_type_alias(alias_name, target_type)` lets frontends seed aliases.

**Frontend changes:**
- C `lower_typedef`: now seeds type alias instead of emitting CONST/STORE_VAR. Handles pointer declarators (e.g., `typedef int* IntPtr` → `IntPtr = Pointer[Int]`).

**Alternatives considered:**
- **Resolve at parse_type boundary**: Rejected — aliases are structural, not syntactic. Resolution belongs in the inference engine.
- **Store aliases in TypeGraph as edges**: Rejected — aliases are transparent (no subtype relationship), just name mappings.

**Consequences:** 7 new tests (5 unit, 2 integration). 3 existing C frontend typedef tests updated to check alias seeding instead of CONST/STORE_VAR emission. All 9753 tests pass.

### ADR-092: Interface/trait typing with TypeGraph extension (2026-03-08)

**Context:** Java `implements`, Kotlin `:`, and TypeScript `implements` clauses were partially extracted (interfaces included in the class reference parent list for method resolution) but not available for TypeGraph subtype queries. `Dog ⊆ Comparable` could not be checked.

**Decision:** Add `interface_implementations: dict[str, list[str]]` to `TypeEnvironmentBuilder` and `TypeEnvironment`, and `extend_with_interfaces()` to `TypeGraph` for building class→interface subtype edges.

**Design details:**
- `TypeNode.kind` field added: `"class"` (default) or `"interface"` — distinguishes interfaces from concrete types
- `TypeGraph.extend_with_interfaces(implementations)`: for each `class → [iface1, iface2]`, adds interface nodes as children of `Any` (if missing), and adds the class node with interfaces as parents (preserving existing parents)
- `TypeEnvironmentBuilder.interface_implementations` and `TreeSitterEmitContext.seed_interface_impl()` for frontend seeding
- Java `_extract_java_parents` extended to extract `super_interfaces → type_list → type_identifier` nodes alongside `superclass`
- Separate `_extract_java_interfaces` for dedicated interface extraction and seeding

**Alternatives considered:**
- **Interfaces as TypeExpr variants**: Rejected — interfaces are graph nodes, not type expressions
- **Automatic TypeGraph extension in infer_types**: Deferred — callers can extend TypeGraph themselves using `env.interface_implementations`

**Consequences:** 8 new tests (6 unit for TypeGraph interface subtype/extension, 2 integration for Java source programs). All 9761 tests pass. No existing test changed.

### ADR-093: Variance annotations for parameterized type subtyping (2026-03-08)

**Context:** All parameterized type arguments were treated as covariant (`List[Int] ⊆ List[Number]`). This is correct for read-only containers but unsound for mutable ones — `MutableList[Int]` should NOT be a subtype of `MutableList[Number]`.

**Decision:** Add a variance registry to `TypeGraph` mapping constructor names to per-argument variance annotations.

**Design details:**
- `Variance` enum in constants: `COVARIANT`, `CONTRAVARIANT`, `INVARIANT`
- `TypeGraph.__init__` accepts optional `variance_registry: dict[str, tuple[Variance, ...]]`
- `is_subtype_expr`: per-argument check uses `_check_variance` — covariant (default): child ⊆ parent, contravariant: parent ⊆ child, invariant: must be equal
- `common_supertype_expr`: `_lub_with_variance` — invariant arguments must be equal (fallback to Any), covariant/contravariant use standard LUB
- `with_variance(registry)`: produces new TypeGraph with merged variance annotations
- `extend()` and `extend_with_interfaces()` preserve the variance registry

**Alternatives considered:**
- **Variance in TypeExpr**: Rejected — variance is a property of the constructor, not the type expression. Registry-based approach is simpler and avoids polluting TypeExpr.
- **Default to invariant**: Rejected — breaks backwards compatibility. Covariant default matches existing behavior.

**Consequences:** 9 new tests (all unit for TypeGraph variance subtype/LUB). All 9770 tests pass. No existing test changed.

### ADR-094: Bounded type variables (TypeVar) for generic type parameters (2026-03-08)

**Context:** The type system lacked support for generic type parameters like Java's `<T extends Number>` or Kotlin's `<T : Comparable>`. Without type variables, generic container and function types couldn't express bounds on their type parameters.

**Decision:** Add `TypeVar` as a new `TypeExpr` variant representing bounded type variables.

**Design details:**
- `TypeVar(name: str, bound: TypeExpr = UNKNOWN)` dataclass in `type_expr.py`
- `typevar(name, bound)` convenience constructor
- `TypeVar.__str__` returns `"T: Number"` (bounded) or `"T"` (unbounded)
- Subtype rules in `TypeGraph.is_subtype_expr`:
  - TypeVar child: subtype if its bound is subtype of parent (unbounded → bound=Any)
  - TypeVar parent: child satisfies it if child is subtype of the bound
- TypeVars compose with parameterized types: `Array[Int] ⊆ Array[T: Number]` via covariant argument checking

**Alternatives considered:**
- **TypeVar as ScalarType with naming convention**: Rejected — loses bound information and requires out-of-band tracking
- **Separate generic parameter registry**: Rejected — embedding bound in TypeExpr is simpler and self-contained
- **TypeVar in LUB computation**: Deferred — LUB of two TypeVars is not yet needed; can be added when generic inference requires it

**Consequences:** 20 new tests (10 unit for TypeVar ADT, 8 unit for TypeGraph subtype rules, 2 integration for bounded TypeVar with containers). All 9790 tests pass. No existing test changed.

### ADR-095: LLVM-style frontend variable scoping with metadata (2026-03-09)

**Context:** The type inference engine has per-function scoping (`scoped_var_types`), but two problems remain: (1) `flat_var_types()` collapses all scopes via `dict.update()`, so later functions overwrite earlier ones — `x: Int` in `foo()` and `x: String` in `bar()` produces `x: String` in the flat output; (2) block-scoped languages (Java, C, C++, C#, Go, Kotlin, Scala, Rust, TypeScript `let`/`const`) should not let inner-block variable declarations overwrite outer-scope types.

**Decision:** Follow the LLVM compiler frontend approach: resolve variable scoping at IR emission time in the frontend, not in the inference engine. Frontends for block-scoped languages disambiguate variable names before emitting `STORE_VAR`/`LOAD_VAR`, so the IR never contains name collisions. Original names and scope metadata are preserved separately.

**Design details:**
- `TreeSitterEmitContext` gains a scope stack (`_block_scope_stack`) and methods: `enter_block_scope()`, `exit_block_scope()`, `declare_block_var(name)` → mangled name, `resolve_var(name)` → current binding
- When a block-scoped frontend encounters a declaration that shadows an outer variable, `declare_block_var` returns a mangled name (e.g., `x$1`) and records metadata `VarScopeInfo(original_name, scope_depth)`
- `STORE_VAR` and `LOAD_VAR` use the mangled name — the inference engine sees unique names, no collisions
- Function-scoped frontends (Python, Ruby, PHP, COBOL, etc.) never call `enter_block_scope`, so behavior is unchanged
- Mixed-scoping languages (JS/TS with `var` vs `let`) use `declare_block_var` for `let`/`const` and raw names for `var`
- `TypeEnvironment` exposes `scoped_var_types` (per-function) and `var_scope_metadata` (mangled→original mapping)
- `flat_var_types()` changed from `dict.update()` overwrite to `union_of()` merge

**Alternatives considered:**
- **SCOPE_ENTER/SCOPE_EXIT opcodes + STORE_LOCAL**: Rejected — adds complexity to the IR and inference engine. LLVM, GCC, and JVM all resolve scoping before or during IR emission, not in the IR itself.
- **Per-frontend ScopingPolicy enum with label-based inference**: Rejected — fragile, depends on label naming conventions, can't handle mixed scoping (JS `var` vs `let`)
- **Scope-qualified variable names (`func_foo_0::x`)**: Rejected — pollutes the public API and breaks all existing consumers of `var_types`

**Consequences:** Core infrastructure commit adds scope tracker to context, metadata storage, flat_var_types fix, and scoped_var_types exposure. Per-frontend commits follow for each block-scoped language.

**Status (2026-03-09):** Fully integrated into all 9 block-scoped frontends (Java, C, C++, C#, Rust, Go, Kotlin, Scala, TypeScript). Each frontend sets `BLOCK_SCOPED = True` on `BaseFrontend`, which passes `block_scoped=True` to `TreeSitterEmitContext`. `lower_block()` auto-enters/exits scopes for block node types. Declaration lowerers call `declare_block_var()` for local variable declarations. `lower_identifier()` and `lower_store_target()` call `resolve_var()` for all variable reads/writes. Pascal's `STATEMENT` was removed from its `block_node_types` (it's a statement wrapper, not a block container). `lower_stmt()` dispatch order fixed: stmt_dispatch handlers take priority, block_node_types fallback handles bare `{ }` blocks. Kotlin's `_lower_control_body` extended to unwrap `statements` blocks with proper scope entry/exit. 16 integration tests verify shadowing across all 9 block-scoped frontends and non-mangling for Python and JavaScript `var`.

### ADR-096: Frontend scoping gap audit (2026-03-09)

**Context:** After implementing LLVM-style block scoping (ADR-095) for the standard scenarios (nested blocks, loop variables, catch clauses, C-style for-loop init), a deep audit revealed 12 additional variable-binding constructs across 8 languages where scoping is incorrect or the construct is not fully lowered. These are recorded here for future resolution.

**Gaps identified:**

**P0 — Init statements silently dropped (code lost from IR):**

| # | Construct | Language | File | Issue |
|---|-----------|----------|------|-------|
| 1 | `if x := expr; cond { }` | Go | `go/control_flow.py` `lower_go_if` | `initializer` field completely ignored; init statement never lowered |
| 2 | `switch x := expr; val { }` | Go | `go/control_flow.py` `lower_expression_switch` | `initializer` field completely ignored; init statement never lowered |
| 3 | `try (Resource r = new ...) { }` | Java | `java/control_flow.py` `lower_try` | `resource_specification` field ignored; resource var never declared or initialized |

**P1 — Variable not bound or scoped correctly:**

| # | Construct | Language | File | Issue |
|---|-----------|----------|------|-------|
| 4 | `if let Some(x) = expr { }` | Rust | `rust/expressions.py` `lower_let_condition` | Pattern variable `x` not destructured/bound; treated as value comparison |
| 5 | `while let Some(x) = expr { }` | Rust | common `lower_while` + `lower_let_condition` | Same as if-let; pattern variable not bound |
| 6 | `match expr { Some(x) => { } }` | Rust | `rust/expressions.py` `lower_match_expr` | Match arm pattern variables not bound or scoped per arm |
| 7 | `if (int x = expr) { }` | C++ | `cpp/expressions.py` `lower_condition_clause` | `condition_clause` handler picks init-statement as condition; actual condition never evaluated |
| 8 | `using (var x = ...) { }` | C# | `csharp/control_flow.py` `lower_using_stmt` | Variable not scoped to using block; leaks to enclosing scope |
| 9 | `case Pattern(x) =>` in match | Scala | `scala/expressions.py` `lower_match_expr` | Pattern-bound variables not scoped per case arm |

**P2 — Destructuring not decomposed:**

| # | Construct | Language | File | Issue |
|---|-----------|----------|------|-------|
| 10 | `when (val x = expr) { }` | Kotlin | `kotlin/expressions.py` `lower_when_expr` | Bound variable in when subject not declared/scoped |
| 11 | Destructuring in for `for ((k,v) in map)` | Kotlin | `kotlin/control_flow.py` `lower_for_stmt` | Only single var extracted; multi-binding not decomposed |
| 12 | Structured bindings `auto [a,b] = pair` in for | C++ | `cpp/control_flow.py` `lower_range_for` | Structured binding not decomposed into individual vars |
| 13 | Switch expression pattern vars | C# | `csharp/control_flow.py` `lower_switch_expr` | Pattern-bound variables in switch arms not scoped |
| 14 | `for (const [k,v] of map) { }` | TS/JS | `javascript/control_flow.py` `lower_for_of` | Destructuring pattern not decomposed; `declare_block_var(None)` called |

**Decision:** Record these gaps for incremental resolution. P0s (Go if/switch init, Java try-with-resources) are functional breakage — code is silently lost from the IR. P1s are scoping errors where variables leak or aren't bound. P2s are destructuring limitations where only partial variable extraction occurs.

**Status:** Mostly resolved. P0 #1-3 (Go if/switch init, Java try-with-resources), P1 #7-8 (C++ if-init, C# using scope), P2 #10 (Kotlin when-subject binding), P2 #11-12, #14 (for-loop destructuring in Kotlin, C++, JS/TS) are all fixed. Remaining open: P1 #4-6 (Rust pattern matching), P1 #9 (Scala pattern matching), P2 #13 (C# switch expression patterns) — all require pattern matching architecture.

---

### ADR-097: For-loop destructuring support (2026-03-09)

**Context:** For-of/for-in loops with destructuring patterns (`for (const [k, v] of arr)` in JS/TS, `for ((a, b) in pairs)` in Kotlin, `for (auto [a, b] : pairs)` in C++) were not decomposing the pattern into individual variables — they either extracted a single variable name or produced `None`.

**Decision:** Reuse existing per-language destructuring helpers where available (JS `_lower_array_destructure`/`_lower_object_destructure`, Kotlin `_lower_multi_variable_destructure` pattern). For C++ structured bindings, add new `_lower_structured_binding` helper. All share the same IR pattern: positional `LOAD_INDEX` + `STORE_VAR` per element, or `LOAD_FIELD` + `STORE_VAR` for object destructuring.

**Changes:**
- `javascript/control_flow.py`: `lower_for_of` and `lower_for_in` detect `array_pattern`/`object_pattern` nodes and delegate to existing destructuring helpers via `_lower_for_destructure`
- `kotlin/control_flow.py`: `lower_for_stmt` detects `multi_variable_declaration` and decomposes via `_lower_for_multi_destructure`
- `cpp/control_flow.py`: `lower_range_for` detects `structured_binding_declarator` and decomposes via `_lower_structured_binding`
- `cpp/node_types.py`: Added `STRUCTURED_BINDING_DECLARATOR` constant

**Status:** Complete. 11 unit tests + 20 integration tests.

---

### ADR-098: Python comprehension variable scoping (2026-03-09)

**Context:** Python 3 scopes comprehension loop variables to the comprehension body — `[x for x in items]` should not leak `x` to the enclosing scope. The Python frontend was lowering comprehension loops without block scoping, causing the loop variable to overwrite any outer variable with the same name. Additionally, comprehension loops had an SSA counter bug (same pattern as for-each loops — using SSA register directly instead of STORE_VAR/LOAD_VAR).

**Decision:** Apply two fixes to `_lower_comprehension_loop` and `lower_dict_comprehension` in `python/expressions.py`:
1. **SSA counter fix**: Use `STORE_VAR`/`LOAD_VAR` for `__for_idx` instead of reusing the SSA register directly.
2. **Block scoping**: Register the loop variable name in `_base_declared_vars` before entering a block scope, then use `declare_block_var()` to mangle the name (e.g., `x` → `x$1`). Body expressions automatically resolve the mangled name via `resolve_var()`. `exit_block_scope()` is called before the increment section.

**Changes:**
- `interpreter/frontends/python/expressions.py`: `_lower_comprehension_loop` and `lower_dict_comprehension` — SSA fix + block scope with name mangling
- List, set comprehensions and generator expressions all share `_lower_comprehension_loop`, so the fix applies uniformly
- Dict comprehension has its own inline loop that was separately fixed

**Status:** Complete. 5 unit tests + 4 integration tests.

---

### ADR-099: Pointer aliasing with promote-on-address-of (2026-03-09)

**Context:** The symbolic VM models struct/object fields on the heap but keeps primitive variables in `StackFrame.local_vars`. Taking `&x` on a primitive produces a symbolic value with no backing storage, so `*ptr = 99` doesn't update `x`. This breaks faithful execution of C/C++/Rust pointer semantics.

**Decision:** Adopt a KLEE-inspired memory model with three components:

1. **`Pointer(base, offset)` dataclass** — immutable value type representing a typed pointer. `base` is a heap address, `offset` is an integer byte/element offset. Pointer arithmetic produces new Pointer objects with adjusted offsets.

2. **`ADDRESS_OF` opcode** — new IR opcode that takes a variable name as operand and returns a `Pointer`. When executed, promotes the variable's value from `local_vars` to a `HeapObject` (with field `"0"` holding the value), records the mapping in `StackFrame.var_heap_aliases`, and returns `Pointer(heap_addr, 0)`.

3. **Alias-aware variable access** — `LOAD_VAR` and `STORE_VAR` check `var_heap_aliases` first; if the variable is aliased, reads/writes go through the heap object instead of `local_vars`. This ensures `*ptr = 99` (which writes to the heap) is visible when reading `x`.

**Scope:** C and Rust frontends (C++ inherits from C). Supports nested pointers (`int **pp = &ptr`), pointer arithmetic (`ptr + n`), and pointer indexing (`ptr[n]` = `*(ptr + n)`). Does not yet support `&arr[i]` or `&s.field` (complex lvalue addressing).

**Changes:**
- `interpreter/vm_types.py`: New `Pointer` dataclass, `var_heap_aliases` on `StackFrame`
- `interpreter/ir.py`: New `ADDRESS_OF` opcode
- `interpreter/executor.py`: New `_handle_address_of`, modified `_handle_load_var`, `_handle_store_var`, `_handle_load_field`, `_handle_store_field`, `_handle_binop`, `_handle_load_index`
- `interpreter/vm.py`: Pointer deserialization
- `interpreter/frontends/c/expressions.py`: `lower_pointer_expr` emits `ADDRESS_OF` for `&identifier`
- `interpreter/frontends/rust/expressions.py`: `lower_reference_expr` emits `ADDRESS_OF` for `&identifier`

**Status:** In progress.

### ADR-100: Interface-aware type inference (2026-03-11)

**Context:** The type inference engine resolves method return types via `class_method_types[ClassName][method]`, falling back to `func_return_types[method]` and then `_BUILTIN_METHOD_RETURN_TYPES`. When a variable is typed as an interface (e.g., `Comparable`, `Shape`), calls on it produce UNKNOWN because the interface's method signatures are never linked to the type inference pipeline.

The infrastructure is half-built: `TypeEnvironment.interface_implementations` maps classes to their interfaces, and `TypeGraph.extend_with_interfaces()` can add interface subtype edges — but neither is used in production. The root cause is that Java, C#, TypeScript, and Kotlin lower interfaces as `NEW_OBJECT` with member name enumeration, discarding method return types. PHP, Scala, and Rust already lower interface/trait bodies as CLASS blocks, so their method types flow into inference naturally.

**Decision:** Three-phase enhancement to make type inference interface-aware.

#### Phase 1: Align interface lowering across frontends

Change Java, C#, TypeScript, and Kotlin frontends to lower interface/trait method declarations as function definitions (like PHP/Scala/Rust already do), so that `seed_func_return_type()` captures method return types.

| Frontend | Current | Target |
|----------|---------|--------|
| Java `lower_interface_decl` | NEW_OBJECT + STORE_INDEX per member | CLASS block + lower_method_decl per method |
| C# `lower_interface_decl` | NEW_OBJECT + STORE_INDEX per member | CLASS block + lower_method_decl per method |
| TypeScript `lower_interface_decl` | NEW_OBJECT + STORE_INDEX per member | CLASS block + lower method signatures |
| Kotlin | No dedicated handler | Add interface handler mirroring class lowering |
| Go | No dedicated handler | Add interface handler extracting method set |

**Files:** `java/declarations.py`, `csharp/declarations.py`, `typescript.py`, `kotlin/declarations.py`, `go/declarations.py`

**Tests:** Unit tests per frontend verifying interface methods produce FUNC_DEF labels with seeded return types. Integration tests verifying `func_return_types` contains interface method entries after lowering.

#### Phase 2: Wire interface chain into inference dispatcher

Extend `_infer_call_method()` in `type_inference.py` to walk `interface_implementations` when direct class lookup fails:

```python
# After class_method_types lookup fails:
if class_name_str in ctx.interface_implementations:
    for iface in ctx.interface_implementations[class_name_str]:
        iface_type = ScalarType(iface)
        if iface_type in ctx.class_method_types:
            ret = ctx.class_method_types[iface_type].get(method_name, UNKNOWN)
            if ret:
                ctx.register_types[inst.result_reg] = ret
                return
```

Also thread `interface_implementations` from `TypeEnvironment` into `_InferenceContext` (currently not passed).

**Files:** `type_inference.py` (~15 lines), `type_environment.py` (no change needed — field exists)

**Tests:** Unit tests: class implements interface → method call on class-typed var resolves via interface. Integration tests: TS/Java/C# programs with interface-typed variables get correct return types.

#### Phase 3: Wire TypeGraph extension into production

Call `extend_with_interfaces()` in `infer_types()` so that `is_subtype_expr()` and `common_supertype_expr()` respect interface hierarchies:

```python
# In infer_types(), after building TypeGraph:
if env.interface_implementations:
    type_graph = type_graph.extend_with_interfaces(env.interface_implementations)
```

This enables covariance checks like `Dog <: Comparable` in type narrowing.

**Files:** `type_inference.py` (~3 lines)

**Tests:** Integration test: variable typed as interface, assigned from implementing class, method call return type resolved.

#### Estimated scope

| Phase | Prod LOC | Test LOC | Commits |
|-------|----------|----------|---------|
| 1 — Frontend alignment | ~120 | ~100 | 5 (one per language) |
| 2 — Inference dispatcher | ~15 | ~40 | 1 |
| 3 — TypeGraph wiring | ~3 | ~20 | 1 |
| **Total** | **~138** | **~160** | **7** |

#### Trade-offs considered

- **Alternative: Synthesise interface method types from implementing classes** — infer `Comparable.compareTo` return type by looking at all classes that implement `Comparable`. Rejected: requires whole-program analysis, fragile with partial lowering, and the interface declaration already has the type info.
- **Alternative: Only fix the inference dispatcher (Phase 2) without frontend changes** — would work for Scala/Rust/PHP where types already flow, but leaves Java/C#/TS/Kotlin broken. Rejected: incomplete fix.
- **Alternative: Store interface method types in a new `interface_method_types` dict** — rejected in favour of reusing `class_method_types` keyed by interface name, since the TypeGraph already treats interfaces as types.

**Status:** Phase 1 (5 frontends) and Phase 2 (chain walk + seeding) complete. Phase 3 (TypeGraph extension) deferred — `is_subtype_expr()` has no production consumer yet. Tracked as red-dragon-gsl.

---

### ADR-101: JS/TS frontend lowering — optional_chain, computed_property_name, interface signatures (2026-03-11)

**Context:** The frontend lowering gap analysis identified 5 P1 gaps in JS/TS that affect common modern code patterns: `optional_chain` (`?.`), `computed_property_name` (`{ [expr]: value }`), and three TS interface signature types (`property_signature`, `call_signature`/`construct_signature`, `index_signature`). These gaps produce SYMBOLIC on frequently encountered code, and the interface signatures directly complement the ADR-100 chain walk.

**Decision:**

#### 1. `optional_chain` — already consumed by parent handlers

Tree-sitter parses `obj?.prop` as a `member_expression` with an `optional_chain` child node between object and property. The existing `lower_js_attribute` and `lower_js_subscript` extract the `object` and `property`/`index` fields, which are present regardless of `?.`. The `optional_chain` node is an unnamed child that is naturally skipped.

**No code changes needed.** Null-check IR (e.g., `BRANCH_IF` on null before `LOAD_FIELD`) was considered and rejected: the symbolic VM does not model null semantics, so the additional IR would add complexity with no analysis benefit. Close the gap, add tests to lock behaviour.

#### 2. `computed_property_name` — evaluate expression, use STORE_INDEX

In object literal `pair` handling, when the `key` field is a `computed_property_name` node (instead of `property_identifier`), evaluate the inner expression via `ctx.lower_expr()` and use the resulting register as the key for `STORE_INDEX`. The existing code path already uses `STORE_INDEX`; the only change is evaluating the key dynamically instead of as a const literal.

**Files:** `javascript/expressions.py` (~5 lines in `lower_js_object_literal`)

#### 3. `property_signature` — extract name + type, seed for inference

Extract property name and type annotation from `property_signature` nodes inside interface bodies. Emit as `STORE_VAR` with type seeding inside the class label block, making the property type available for ADR-100 chain walk resolution.

**Files:** `typescript.py` (~15 lines, new `_lower_ts_interface_property` function + dispatch in `lower_interface_decl`)

#### 4. `call_signature` / `construct_signature` — already handled

These are already dispatched to `_lower_ts_interface_method` in `lower_interface_decl` (lines 157-160). `call_signature` uses synthetic name `__call`, `construct_signature` uses `__new` (derived from `name` field fallback). No additional work needed.

#### 5. `index_signature` — documented no-op

`[key: string]: number` defines a type-level wildcard — "any subscript access returns type X." There is no IR representation for default-index-type semantics. The inference engine would need a new concept (default return type for `LOAD_INDEX` on a given class) which is not justified by the frequency of this pattern. Treat as a no-op; skip silently in `lower_interface_decl`.

**Trade-offs considered:**

- **Optional chain null-check IR:** Rejected. Would generate branches the VM can't evaluate meaningfully. The data flow (which variable flows where) is preserved without null checks.
- **Index signature as default type:** Would require a new inference concept (`default_index_type` per class). Deferred until a concrete need arises.
- **Property signature as STORE_FIELD:** Considered emitting `STORE_FIELD` on a class object, but `STORE_VAR` inside the class label block is consistent with how method signatures are lowered, and the inference engine walks `class_method_types` which is populated from function labels within class blocks.

**Status:** Implementing. Tracked as red-dragon-gvu.2.

---

### ADR-102: `using` declaration lowered as `const` without `Symbol.dispose()` semantics (2026-03-12)

**Context:** JavaScript's TC39 Explicit Resource Management proposal introduces `using x = expr` and `await using x = expr`. When the variable goes out of scope, the runtime calls `x[Symbol.dispose()]` (or `Symbol.asyncDispose` for `await using`). Our tree-sitter parser recognises `using_declaration` nodes, but they were unhandled — falling through to SYMBOLIC.

**Decision:** Lower `using_declaration` identically to `lexical_declaration` (`const`/`let`). The `variable_declarator` child structure is the same, so the existing `lower_js_var_declaration` handler is reused. **`Symbol.dispose()` semantics are not implemented** — no scope-exit hook or implicit disposal call is emitted.

**Rationale:** The assignment semantics (`using x = expr` binds `x` to `expr`'s value) are the only part that affects data flow and execution. The disposal semantics would require scope-exit hooks in the VM — infrastructure that does not exist and is not justified by the current use cases. Without this lowering, `using` declarations produce SYMBOLIC, losing all downstream data flow.

**Consequences:** Variables declared with `using` are fully usable in subsequent expressions, method calls, and computations. The VM will not call `Symbol.dispose()` at scope exit, so resource cleanup behaviour is not modelled. If scope-exit semantics are needed in the future, the VM would need a scope-exit callback mechanism — this is a separate, larger effort.

**Files:** `node_types.py` (+1 line), `frontend.py` (+1 line dispatch entry). TypeScript inherits via `super()._build_stmt_dispatch()`.

---

### ADR-103: Rust Box<T> as pass-through, Option<T> as real class (2026-03-15)

**Context:** The Rust Rosetta linked list test uses `Option<Box<Node>>` with `.as_ref().unwrap()` for traversal. Without `Box` and `Option` class definitions, constructor calls fell through to `CALL_UNKNOWN` and produced `SymbolicValue` instead of concrete `answer = 6`. The original spec (red-dragon-62g) modeled `Box` as a real heap object with a `value` field, and `*box_expr` as `LOAD_FIELD "value"`. However, Rust's `Deref` trait makes `Box<T>` auto-deref to `T` transparently on field access, method calls, and function arguments — the compiler inserts `*` operations automatically. Our VM has no auto-deref mechanism, so after `.unwrap()` returns a Box object, `node.value` accesses Box's `value` field (the inner Node address) instead of the Node's integer `value` field.

**Decision:** `Box::new(expr)` is lowered as a **pass-through** — it returns its argument directly without creating a Box object. `Some(expr)` is lowered as `CALL_FUNCTION "Option"`, creating a real Option object with `__init__`, `unwrap`, and `as_ref` methods defined in a Rust-specific prelude. The prelude is emitted via a `_emit_prelude` hook on `BaseFrontend` (no-op default), overridden in `RustFrontend`.

**Rationale:**
- In our reference-based VM, all values are already heap-allocated — Box's purpose (moving values from stack to heap) is a no-op.
- Auto-deref through `Box` is Rust-specific (`Deref` trait) and not applicable to any other supported language. Baking it into the VM would add Rust-specific behavior to the language-agnostic core.
- The pass-through makes `Some(Box::new(node))` store the Node directly, so `.unwrap()` returns the Node — matching Rust's auto-deref semantics without VM changes.

**Known limitations:**
- `*box_val` (explicit deref on a Box variable) produces wrong results: since `box_val` IS the inner value, the deref's `LOAD_FIELD "value"` accesses the inner object's `value` field rather than unwrapping a Box wrapper.
- `Box<T>` and `T` are indistinguishable at runtime — type_hint reflects the inner type, not `Box<T>`.
- The Box prelude class is emitted but never instantiated (dead code in the IR).

**Future:** Making Box a real object requires frontend type tracking to insert auto-deref at the right points. The Rust frontend currently has no struct field type metadata and no mechanism to resolve expression types during lowering (see red-dragon-riy). This is deferred until we understand which real-world Rust patterns require it.

**Files:** `interpreter/frontends/rust/expressions.py` (pass-through in `_lower_box_new`, `_lower_some`), `interpreter/frontends/rust/declarations.py` (prelude emission), `interpreter/frontends/rust/frontend.py` (dispatch + `_emit_prelude` override), `interpreter/frontends/_base.py` (`_emit_prelude` hook), `interpreter/registry.py` (prelude class label recognition), `interpreter/executor.py` (base-name extraction, `type_hint_source`), `interpreter/vm_types.py` (`HeapObject.type_hint` → `TypeExpr`).

---

### ADR-104: Lua table-based OOP via frontend STORE_FIELD + LOAD_FIELD + CALL_UNKNOWN (2026-03-15)

**Context:** Lua has no classes — OOP is done via tables with function-valued fields (`function Counter.new()` is sugar for `Counter["new"] = function()`). The Lua frontend was emitting `DECL_VAR "Counter.new"` for dotted function declarations and `CALL_METHOD` for dotted function calls. This failed because: (1) methods stored as top-level variables don't populate the table's fields dict, (2) `CALL_METHOD` looks up `registry.class_methods["table"]` which is empty, (3) falls through to symbolic.

**Decision:** Fix entirely in the Lua frontend with no VM changes:
1. **Dotted function declarations** (`function Counter.new()`): extract table name and method name from the `dot_index_expression` AST node. Use only the method name (`new`) as the function label name. Emit `LOAD_VAR "Counter"` + `STORE_FIELD %obj "new" %func` instead of `DECL_VAR "Counter.new"`.
2. **Dotted function calls** (`Counter.increment(counter)`): emit `LOAD_VAR "Counter"` + `LOAD_FIELD %obj "increment"` + `CALL_UNKNOWN %func args...` instead of `CALL_METHOD`. Uses `CALL_UNKNOWN` (not `CALL_FUNCTION`) because the function reference is in a register.

**Rationale:**
- Lua's dot syntax IS field access + function call, not method dispatch. Only colon syntax (`:`) implies implicit self — that's a separate concern (out of scope).
- Frontend-only: no VM complexity added. Semantically correct for how Lua actually works.
- `CALL_UNKNOWN` is the established pattern in the Lua frontend for all dynamic call targets.

**Files:** `interpreter/frontends/lua/declarations.py` (dotted declaration → STORE_FIELD), `interpreter/frontends/lua/expressions.py` (dotted call → LOAD_FIELD + CALL_UNKNOWN), `tests/unit/test_lua_frontend.py`, `tests/integration/test_lua_table_oop_execution.py`.

---

### ADR-105: Structured function references via symbol table (2026-03-15)

**Context:** Function references were stringly-typed — frontends emitted `CONST "<function:name@label>"` and every consumer (registry, type inference, executor) regex-parsed this string back via `FUNC_REF_PATTERN`. This was fragile (dotted names like `Counter.new` broke `\w+` matching) and violated the principle of passing decisions through data rather than re-deriving them downstream.

**Decision:** Replace with a symbol table (`dict[str, FuncRef]`) on `TreeSitterEmitContext`. Frontends call `ctx.emit_func_ref(name, label)` which registers a `FuncRef(name, label)` in the symbol table and emits `CONST label` (plain string). The symbol table flows through the pipeline: `build_registry()`, `infer_types()`, and `execute_cfg()` all accept `func_symbol_table`. At runtime, `_handle_const` looks up the label in the symbol table and creates a `BoundFuncRef(func_ref, closure_id)` stored in the register. All consumer sites use `isinstance(val, BoundFuncRef)` instead of regex. The LLM frontend boundary retains a local regex (`_LLM_FUNC_REF_RE`) for parsing LLM-emitted `<function:...>` strings, converting to structured refs before pipeline entry.

**Deletions:** `FUNC_REF_PATTERN`, `FUNC_REF_TEMPLATE` (constants.py), `_parse_func_ref()`, `RefPatterns.FUNC_RE` (registry.py), `_FUNC_REF_EXTRACT`, `_FUNC_REF_PATTERN` (type_inference.py).

**Files:** `interpreter/func_ref.py` (new: `FuncRef`, `BoundFuncRef`), `interpreter/frontends/context.py` (`func_symbol_table`, `emit_func_ref`), `interpreter/executor.py` (7 call sites → `isinstance`), `interpreter/registry.py` (symbol table lookup), `interpreter/type_inference.py` (symbol table lookup), `interpreter/run.py` (threading + `_format_val`), `interpreter/llm_frontend.py` (boundary conversion), all 15 frontend dirs.

---

### ADR-106: Structured class references via symbol table (2026-03-15)

**Context:** Class references were stringly-typed — frontends emitted `CONST "<class:name@label>"` or `CONST "<class:name@label:Parent1,Parent2>"` and every consumer (registry, type inference, executor) regex-parsed this string back. This was the same fragility that `FUNC_REF_PATTERN` had (fixed in ADR-105).

**Decision:** Replace with a symbol table (`dict[str, ClassRef]`) on `TreeSitterEmitContext`. Frontends call `ctx.emit_class_ref(name, label, parents)` which registers a `ClassRef(name, label, parents)` and emits `CONST label` (plain string). Unlike function references, class references have no runtime binding equivalent (`BoundFuncRef` for closures) — `ClassRef` objects are stored directly in registers. Consumer sites use `isinstance(val, ClassRef)` (executor) or `label in class_symbol_table` (registry, type inference). A `NO_CLASS_REF` null object sentinel eliminates None checks. The LLM frontend boundary retains a local regex for parsing LLM-emitted strings. With this change, all stringly-typed reference patterns are eliminated from the pipeline.

**Deletions:** `CLASS_REF_PATTERN`, `CLASS_REF_TEMPLATE`, `CLASS_REF_WITH_PARENTS_TEMPLATE` (constants.py), `RefPatterns`, `RefParseResult`, `_parse_class_ref()` (registry.py), `_CLASS_REF_PATTERN` (type_inference.py), `make_class_ref()` (common/declarations.py).

**Files:** `interpreter/class_ref.py`, `interpreter/frontends/context.py`, `interpreter/executor.py`, `interpreter/registry.py`, `interpreter/type_inference.py`, `interpreter/run.py`, all 15 frontend dirs.

---

### ADR-107: `_resolve_reg` returns `TypedValue` — unified register resolution (2026-03-18)

**Context:** `_resolve_reg()` in `vm.py` returned bare Python values (unwrapping `TypedValue` via `.value`), while `_resolve_binop_operand()` returned the full `TypedValue`. This split forced write callsites (DECL_VAR, STORE_VAR, STORE_FIELD, STORE_INDEX, STORE_INDIRECT, RETURN) to re-wrap bare values via `typed_from_runtime()`, losing parameterized type information (e.g. `pointer(scalar("Dog"))` was flattened to a generic type). The two functions had identical logic except for the final unwrap step.

**Decision:** Change `_resolve_reg()` to return `TypedValue` directly. Delete `_resolve_binop_operand()` (now identical). Write callsites use the `TypedValue` as-is without re-wrapping. Read callsites that need bare values extract `.value` (for `isinstance`, `_heap_addr`, `bool`, `int`, dict keys, etc.). `typed_from_runtime()` remains as a fallback inside `_resolve_reg()` for registers that hold non-`TypedValue` values (e.g. raw constants).

**Consequences:** Parameterized type information is preserved through the register→handler→storage pipeline — e.g. a `pointer(scalar("Dog"))` stored via `STORE_VAR` retains its full type instead of being flattened. The dual-function API surface is simplified to a single `_resolve_reg()`. All callers are updated: 7 write callsites drop redundant `typed_from_runtime()` wrapping, 19 read callsites add `.value` extraction.

---

### ADR-108: Heap object references migrated from bare strings to `Pointer` dataclass (2026-03-18)

**Context:** Heap objects were referenced by bare strings (e.g. `"obj_0"`, `"arr_0"`) throughout the VM. `NEW_OBJECT` and `NEW_ARRAY` returned these strings directly, and `LOAD_FIELD`/`STORE_FIELD` had separate code paths for bare string addresses vs. `Pointer` objects. The `_heap_addr()` helper had to pattern-match on both strings and `Pointer` instances, and parameterized type information (e.g. "this is a pointer to a Dog") was lost because bare strings carry no type metadata.

**Decision:** Migrate all heap object references to `Pointer(base, offset)` dataclass instances. `NEW_OBJECT` and `NEW_ARRAY` now produce `Pointer(base=heap_addr, offset=0)` wrapped in `TypedValue` with parameterized types (e.g. `pointer(scalar("Dog"))`). `_heap_addr()` is updated to extract the base address from `Pointer` instances. `LOAD_FIELD` and `STORE_FIELD` are unified — the separate `Pointer` branch is eliminated because all heap references are now `Pointer` objects. Builtins that allocate heap objects (e.g. `slice`, `range`, `dict`) return `Pointer` in `TypedValue`.

**Rationale:**
- Bare string addresses were stringly-typed — they carried no semantic information about what they pointed to. `Pointer` is a proper domain type that can carry base/offset and be composed with `TypedValue` for parameterized types.
- The dual code paths in `LOAD_FIELD`/`STORE_FIELD` (one for strings, one for Pointer) were a maintenance burden and a source of subtle bugs when one path was updated but not the other.
- Pointer arithmetic (ADR-099) already required `Pointer` objects; having `NEW_OBJECT`/`NEW_ARRAY` produce bare strings that were later wrapped into `Pointer` was an unnecessary conversion step.

**Consequences:** All heap references are now `Pointer` objects from creation through consumption. `_heap_addr()` handles `Pointer` uniformly. `LOAD_FIELD`/`STORE_FIELD` have a single code path. Type information flows end-to-end — a `NEW_OBJECT "Dog"` produces `TypedValue(Pointer(base="obj_0", offset=0), pointer(scalar("Dog")))`, and this type is preserved through `STORE_VAR`, `LOAD_VAR`, and field access. The trade-off is that all code that previously compared or matched on bare heap address strings must now go through `_heap_addr()` or access `pointer.base`.
