# Architectural Decision Records

This document captures key architectural decisions made during the development of RedDragon. Entries are ordered chronologically and were retroactively extracted from the commit history.

---

### ADR-001: Flattened TAC IR as universal intermediate representation (2026-02-25)

**Context:** The project needed a single representation that all source languages lower into, enabling language-agnostic analysis and execution. A tree-based AST would require per-language walkers for every downstream pass.

**Decision:** Adopt a flattened three-address code (TAC) IR with ~19 opcodes (`CONST`, `BINOP`, `STORE_VAR`, `LOAD_VAR`, `BRANCH_IF`, `LABEL`, `CALL_FUNCTION`, `RETURN`, etc.). Every instruction is a flat dataclass with an opcode, operands, and a destination register. No nested expressions — all intermediates are explicit.

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

**Context:** When symbolic execution accesses `obj.field` on a symbolic object, repeated accesses to the same field were creating distinct symbolic values each time, breaking data-flow identity.

**Decision:** Materialise a heap object for symbolic values on first field access. Subsequent accesses to the same field on the same object return the same symbolic value, maintaining referential consistency.

**Consequences:** Symbolic data-flow analysis correctly tracks field identity across multiple access sites. The heap grows with materialised objects, but this is bounded by the number of distinct (object, field) pairs accessed.

---

### ADR-005: LLM-as-compiler-frontend (2026-02-25)

**Context:** Supporting languages without tree-sitter grammars required an alternative lowering path. Using an LLM as a "reasoning engine" to analyse code produces inconsistent, hallucination-prone results.

**Decision:** Constrain the LLM to act as a **compiler frontend**: the prompt provides all 19 opcode schemas, concrete patterns for functions/classes/control flow, and a full worked example. The LLM's job is mechanical translation, not reasoning. Output is structured JSON matching the IR schema.

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
