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

#### Part 3: COBOL type encoding/decoding as synthetic IR functions

The COBOL frontend emits encoding/decoding functions into the IR during DATA DIVISION lowering. These functions contain the logic ported from smojol's `DataTypeSpec` subclasses:

| Synthetic function | Ports from smojol | Purpose |
|---|---|---|
| `__cobol_encode_alpha` | `AlphanumericDataTypeSpec.set()` | String → EBCDIC bytes, right-padded |
| `__cobol_decode_alpha` | `AlphanumericDataTypeSpec.readPublic()` | EBCDIC bytes → string |
| `__cobol_encode_zoned` | `ZonedDecimalDataTypeSpec.set()` | Number → zoned decimal bytes (sign nibble) |
| `__cobol_decode_zoned` | `ZonedDecimalDataTypeSpec.readFormatted()` | Zoned decimal bytes → number |
| `__cobol_encode_comp3` | `Comp3DataTypeSpec.set()` | Number → packed BCD bytes (sign nibble) |
| `__cobol_decode_comp3` | `Comp3DataTypeSpec.readFormatted()` | Packed BCD bytes → number |

These are emitted as standard IR function definitions (using existing `BRANCH`/`LABEL`/`CALL_FUNCTION`/`RETURN` opcodes). The VM executes them like any other function — no COBOL-specific code in the VM.

However, since these functions manipulate individual bytes and nibbles, the IR also needs **byte-level builtins** (language-agnostic, not COBOL-specific):

| Builtin | Purpose |
|---|---|
| `byte_get_nibble(byte, position)` | Extract high/low nibble from a byte |
| `byte_set_nibble(byte, position, value)` | Set high/low nibble in a byte |
| `byte_from_int(n)` | Integer (0-255) → byte |
| `int_from_byte(b)` | Byte → integer (0-255) |
| `bytes_to_string(bytes)` | Byte array → string (ASCII) |
| `string_to_bytes(s)` | String → byte array (ASCII) |
| `ebcdic_to_ascii(byte)` | Single byte EBCDIC → ASCII conversion |
| `ascii_to_ebcdic(byte)` | Single byte ASCII → EBCDIC conversion |

The EBCDIC conversion tables are ported from smojol's `ByteConverter` (256-entry static lookup tables).

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
- Byte-level builtins (nibble manipulation, EBCDIC tables) add ~8 new entries to the builtins table
- COBOL paragraphs as inline blocks (Strategy 2) produces larger CFGs than the function-based alternative, but preserves COBOL's actual execution model
