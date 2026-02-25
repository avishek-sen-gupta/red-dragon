# LLM Symbolic Interpreter

![CI](https://github.com/avishek-sen-gupta/red-dragon/actions/workflows/ci.yml/badge.svg)

A symbolic interpreter that parses source code, lowers it to a three-address code IR, builds a control flow graph, and executes it via a deterministic VM — falling back to an LLM only when the program references externals or operates on symbolic values.

## Project structure

```
interpreter.py           # CLI entry point (argparse + main)
interpreter/
├── __init__.py          # re-exports run
├── constants.py         # Named constants (eliminates magic strings)
├── ir.py                # Opcode, IRInstruction
├── parser.py            # ParserFactory (DI), TreeSitterParserFactory, Parser
├── frontend.py          # Frontend ABC, get_frontend() factory (delegates to frontends/)
├── frontends/           # Deterministic tree-sitter frontends (15 languages)
│   ├── __init__.py      # FRONTEND_REGISTRY, get_deterministic_frontend()
│   ├── _base.py         # BaseFrontend — language-agnostic IR lowering infrastructure
│   ├── python.py        # PythonFrontend
│   ├── javascript.py    # JavaScriptFrontend
│   ├── typescript.py    # TypeScriptFrontend (extends JavaScriptFrontend)
│   ├── java.py          # JavaFrontend
│   ├── ruby.py          # RubyFrontend
│   ├── go.py            # GoFrontend
│   ├── php.py           # PhpFrontend
│   ├── csharp.py        # CSharpFrontend
│   ├── c.py             # CFrontend
│   ├── cpp.py           # CppFrontend (extends CFrontend)
│   ├── rust.py          # RustFrontend
│   ├── kotlin.py        # KotlinFrontend
│   ├── scala.py         # ScalaFrontend
│   ├── lua.py           # LuaFrontend
│   └── pascal.py        # PascalFrontend
├── llm_client.py        # LLMClient ABC, Claude/OpenAI/Ollama/HuggingFace clients
├── llm_frontend.py      # LLMFrontend — LLM-based source-to-IR lowering
├── chunked_llm_frontend.py  # ChunkedLLMFrontend — tree-sitter chunking + per-chunk LLM lowering
├── cfg.py               # BasicBlock, CFG, build_cfg()
├── dataflow.py          # Iterative dataflow analysis (reaching defs, def-use chains, dependency graphs)
├── registry.py          # FunctionRegistry, LocalExecutor (dispatch table), builtins
├── vm.py                # SymbolicValue, VMState, StateUpdate, ExecutionResult, Operators
├── backend.py           # LLMBackend (DI for clients), Claude/OpenAI/Ollama/HuggingFace backends
└── run.py               # run() orchestrator (decomposed helpers)
tests/
├── test_llm_client.py           # LLMClient unit tests (DI with fake API clients)
├── test_llm_frontend.py         # LLM frontend parsing, validation, prompt tests
├── test_chunked_llm_frontend.py # Chunked LLM frontend tests (extractor, renumberer, integration)
├── test_frontend_factory.py     # get_frontend() factory tests
├── test_backend_refactor.py     # Backend refactor + get_backend() factory tests
├── test_closures.py             # Closure capture and invocation tests
├── test_dataflow.py             # Dataflow analysis tests (reaching defs, def-use, dependency graph)
├── test_python_frontend.py      # Python frontend tests
├── test_javascript_frontend.py  # JavaScript frontend tests
├── test_typescript_frontend.py  # TypeScript frontend tests
├── test_java_frontend.py        # Java frontend tests
├── test_ruby_frontend.py        # Ruby frontend tests
├── test_go_frontend.py          # Go frontend tests
├── test_php_frontend.py         # PHP frontend tests
├── test_csharp_frontend.py      # C# frontend tests
├── test_c_frontend.py           # C frontend tests
├── test_cpp_frontend.py         # C++ frontend tests
├── test_rust_frontend.py        # Rust frontend tests
├── test_kotlin_frontend.py      # Kotlin frontend tests
├── test_scala_frontend.py       # Scala frontend tests
├── test_lua_frontend.py         # Lua frontend tests
└── test_pascal_frontend.py      # Pascal frontend tests
```

## How it works

```
Source Code
    │
    ├──── deterministic path ──── tree-sitter ──── Language Frontend ──┐
    │                              (15 languages)                     │
    ├──── LLM path (--frontend llm) ──── LLMFrontend ────────────────┤
    │                                                                 │
    └──── chunked LLM (--frontend chunked_llm) ──── tree-sitter ─────┤
                     chunk → LLM × N → renumber → reassemble         │
                                                                      ▼
                                                          Flattened High-Level TAC (IR)
                                                              │  CFG builder
                                                              ▼
                                                          Control Flow Graph
                                                              │  VM + function registry
                                                              ▼
                                                          Deterministic Execution
                                                              │  fallback on symbolic values
                                                              ▼
                                                          LLM Oracle (only when needed)
```

1. **Parse** — Tree-sitter (via `tree-sitter-language-pack`) parses source into an AST (deterministic path), or the LLM lowers source directly to IR (LLM path), or tree-sitter decomposes the file into top-level chunks for per-chunk LLM lowering (chunked LLM path)
2. **Lower** — A language-specific frontend converts the AST into a flattened three-address code IR (~19 opcodes). Each of the 15 supported languages has a dedicated `BaseFrontend` subclass with dispatch tables mapping tree-sitter node types to IR opcodes. With `--frontend llm`, the LLM performs this lowering step directly from source code. With `--frontend chunked_llm`, tree-sitter extracts top-level functions/classes/statements, each chunk is lowered independently by the LLM, and results are reassembled with renumbered registers and labels
3. **Build CFG** — IR instructions are partitioned into basic blocks with control flow edges
4. **Dataflow analysis** (optional) — Iterative reaching definitions, def-use chains, and variable dependency graphs via classic worklist-based fixed-point computation
5. **Build registry** — Function and class definitions are indexed from the IR, mapping names to CFG labels and extracting parameter lists
5. **Execute** — The VM walks the CFG deterministically:
   - **Local execution** handles constants, loads, stores, arithmetic, branches, function/method calls (by stepping into the body), closures (captured enclosing scope), constructor dispatch (`__init__`), heap field access, and builtins (`len`, `range`, `print`, `int`, `str`, etc.)
   - **LLM fallback** is used only for operations on symbolic values (symbolic arithmetic, symbolic branch conditions) or calls to unknown externals not defined in the source

For programs with concrete inputs and no external dependencies, the entire execution is **deterministic with 0 LLM calls**.

## Setup

Requires Python >= 3.10 and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

Set your API key for the LLM backend (only needed for `--frontend llm` or when execution encounters symbolic values):

```bash
export ANTHROPIC_API_KEY=sk-...          # for Claude (default)
export OPENAI_API_KEY=sk-...             # for OpenAI
export HUGGING_FACE_API_TOKEN=hf_...     # for HuggingFace Inference Endpoints
# Ollama requires no API key (runs locally at localhost:11434)
```

## Usage

```bash
# Run the built-in demo (factorial function)
poetry run python interpreter.py -v

# Run on a file
poetry run python interpreter.py myfile.py -v

# Inspect IR only (no execution)
poetry run python interpreter.py myfile.py --ir-only

# Inspect CFG only (no execution)
poetry run python interpreter.py myfile.py --cfg-only

# Use OpenAI backend for LLM fallback
poetry run python interpreter.py myfile.py -b openai

# Limit execution steps
poetry run python interpreter.py myfile.py -n 50

# Use LLM frontend (LLM lowers source to IR instead of tree-sitter)
poetry run python interpreter.py myfile.py -f llm -v

# LLM frontend with a HuggingFace Inference Endpoint
poetry run python interpreter.py myfile.py -f llm -b huggingface -v

# LLM frontend with local Ollama
poetry run python interpreter.py myfile.py -f llm -b ollama -v

# Deterministic frontend on non-Python source (15 languages supported)
poetry run python interpreter.py example.js -l javascript -v

# LLM frontend for unsupported languages
poetry run python interpreter.py example.cob -l cobol -f llm -v

# Chunked LLM frontend (decomposes large files into per-function/class chunks)
poetry run python interpreter.py largefile.py -f chunked_llm -b claude -v
```

### CLI options

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Print IR, CFG, and step-by-step execution |
| `-l`, `--language` | Source language (default: `python`) |
| `-e`, `--entry` | Entry point label or function name |
| `-b`, `--backend` | LLM backend: `claude`, `openai`, `ollama`, or `huggingface` (default: `claude`) |
| `-n`, `--max-steps` | Maximum interpretation steps (default: 100) |
| `-f`, `--frontend` | Frontend type: `deterministic`, `llm`, or `chunked_llm` (default: `deterministic`) |
| `--ir-only` | Print the IR and exit |
| `--cfg-only` | Print the CFG and exit |

## Supported languages (deterministic frontends)

The deterministic frontend (`--frontend deterministic`, the default) supports 15 languages via tree-sitter. Each language has a dedicated frontend that maps tree-sitter AST node types to IR opcodes with 0 LLM calls and sub-millisecond latency.

| Language | Frontend class | Key constructs |
|----------|---------------|----------------|
| Python | `PythonFrontend` | list/dict comprehensions, decorators, with-statement, tuple unpacking |
| JavaScript | `JavaScriptFrontend` | arrow functions, template literals, destructuring, for-in/for-of |
| TypeScript | `TypeScriptFrontend` | extends JS frontend, skips type annotations, enum/interface |
| Java | `JavaFrontend` | method declarations, enhanced for, local variable declarations, interface/enum |
| Ruby | `RubyFrontend` | unless/until (inverted conditions), blocks, instance variables |
| Go | `GoFrontend` | short var declarations (:=), for-only loops, struct + methods via receiver |
| PHP | `PhpFrontend` | $-prefixed variables, echo, namespace handling, arrow functions |
| C# | `CSharpFrontend` | properties, using statements, LINQ as symbolic |
| C | `CFrontend` | struct definitions, pointer expressions, preprocessor directives |
| C++ | `CppFrontend` | extends C frontend, classes, namespaces, templates, lambdas |
| Rust | `RustFrontend` | let/let mut, match expressions, impl blocks, closures, reference/deref |
| Kotlin | `KotlinFrontend` | when expressions, data classes, null safety, property declarations |
| Scala | `ScalaFrontend` | val/var, match expressions, object singletons, for-comprehensions |
| Lua | `LuaFrontend` | tables, repeat-until, numeric/generic for, method calls via `:` |
| Pascal | `PascalFrontend` | begin/end blocks, procedures/functions, record types, `:=` assignment |

Unsupported language constructs emit a `SYMBOLIC` opcode with a descriptive hint rather than crashing, so partial lowering is always available.

For languages not listed above, use the LLM frontend (`--frontend llm`) which supports any language.

## IR opcodes

| Category | Opcodes |
|----------|---------|
| Value producers | `CONST`, `LOAD_VAR`, `LOAD_FIELD`, `LOAD_INDEX`, `NEW_OBJECT`, `NEW_ARRAY`, `BINOP`, `UNOP`, `CALL_FUNCTION`, `CALL_METHOD`, `CALL_UNKNOWN` |
| Consumers / control flow | `STORE_VAR`, `STORE_FIELD`, `STORE_INDEX`, `BRANCH_IF`, `BRANCH`, `RETURN`, `THROW` |
| Special | `SYMBOLIC` (declares an unknown value with optional type hint) |

## Example: factorial (0 LLM calls)

```python
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

result = factorial(5)
```

The VM dispatches into `factorial`, recurses 5 levels deep with concrete arguments, unwinds the call stack, and computes the result — entirely locally:

```
[step 4]  call_function factorial 5
  [local] call factorial(5), dispatch to func_factorial_0

[step 9]  binop <= 5 1
  [local] binop 5 <= 1 = False

[step 15] call_function factorial 4
  [local] call factorial(4), dispatch to func_factorial_0
  ...

[step 53] binop <= 1 1
  [local] binop 1 <= 1 = True        ← base case

[step 56] return 1                    ← unwind begins
[step 57] binop * 2 1 = 2
[step 59] binop * 3 2 = 6
[step 61] binop * 4 6 = 24
[step 63] binop * 5 24 = 120

[step 65] store_var result 120

(67 steps, 0 LLM calls)
```

Final state: `result = 120`.

## Example: classes, methods, heap (0 LLM calls)

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def distance_to(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        return (dx ** 2 + dy ** 2) ** 0.5

p1 = Point(3, 4)
p2 = Point(0, 0)
d = p1.distance_to(p2)
midpoint = Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
points = [p1, p2, midpoint]
count = len(points)
```

The VM allocates heap objects, steps into `__init__` and `distance_to`, resolves field accesses from the heap, and computes everything locally:

```
Final heap:
  obj_0 (Point): {x: 3, y: 4}
  obj_1 (Point): {x: 0, y: 0}
  obj_2 (Point): {x: 1.5, y: 2.0}
  arr_3 (list):  [obj_0, obj_1, obj_2]

Variables:
  d = 5.0
  count = 3

(115 steps, 0 LLM calls)
```

## Example: closures (0 LLM calls)

```python
def make_multiplier(factor):
    def multiply(x):
        return x * factor
    return multiply

double = make_multiplier(2)
triple = make_multiplier(3)
a = double(5)
b = triple(5)
total = a + b
```

The VM captures the enclosing scope's variables when a nested function is defined, and injects them when the closure is called. Each closure instance gets a unique capture — `double` carries `{factor: 2}` and `triple` carries `{factor: 3}`:

```
[step 8]  const <function:multiply@func_multiply_2#closure_0>
            captured {factor: 2} from make_multiplier's scope

[step 16] const <function:multiply@func_multiply_2#closure_1>
            captured {factor: 3} from make_multiplier's scope

[step 20] call multiply(5) with closure_0
            injected factor=2, x=5 → return 10

[step 26] call multiply(5) with closure_1
            injected factor=3, x=5 → return 15

Variables: a = 10, b = 15, total = 25

(31 steps, 0 LLM calls)
```

## LLM frontend

The LLM frontend (`--frontend llm`) sends raw source code to an LLM and receives back a JSON array of IR instructions. This enables multi-language support without writing per-language tree-sitter frontends.

The prompt (`interpreter/llm_frontend.py:LLMFrontendPrompts.SYSTEM_PROMPT`) teaches the LLM to act as a compiler frontend by providing:

1. **Instruction format** — JSON schema for each IR instruction (opcode, result_reg, operands, label)
2. **Opcode reference** — all 19 opcodes grouped by category (value producers, control flow, special)
3. **Critical patterns** — concrete IR patterns for function definitions (skip-over-body + `<function:name@label>` registration), class definitions, constructor calls, method calls, and if/elif/else
4. **Full worked example** — a complete fibonacci program lowered to 32 exact JSON instructions
5. **Rules** — sequential registers, entry label, implicit returns, literal encoding conventions

The key insight: providing **concrete patterns with exact JSON** produces IR that matches the deterministic frontend's output, while abstract opcode descriptions alone lead to structural errors (e.g., branching into function bodies instead of skipping over them).

### Supported LLM providers

| Provider | Flag | Model | Notes |
|----------|------|-------|-------|
| Claude | `-b claude` | claude-sonnet-4-20250514 | Best quality, requires `ANTHROPIC_API_KEY` |
| OpenAI | `-b openai` | gpt-4o | Requires `OPENAI_API_KEY` |
| HuggingFace | `-b huggingface` | auto-discovered | Inference Endpoints, requires `HUGGING_FACE_API_TOKEN` |
| Ollama | `-b ollama` | qwen2.5-coder:7b-instruct | Local, no API key needed |

Smaller models (7B) may produce malformed JSON. The frontend retries the LLM call up to 3 times on JSON parse failure before raising `IRParsingError`. For best results, use 32B+ parameter models (e.g., Qwen2.5-Coder-32B-Instruct via HuggingFace).

### Chunked LLM frontend

The chunked LLM frontend (`--frontend chunked_llm`) solves the context window limitation for large files. Instead of sending the entire file to the LLM in one call, it:

1. **Extracts chunks** — tree-sitter identifies top-level functions, classes, and statement blocks
2. **Groups adjacent top-level statements** — contiguous non-function/non-class statements are merged into a single chunk to minimise LLM calls
3. **Lowers each chunk independently** — each chunk is sent to the wrapped `LLMFrontend` as a self-contained source snippet
4. **Renumbers registers and labels** — a post-lowering pass offsets register numbers (`%0` → `%K`) and suffixes labels (`func_foo_0` → `func_foo_0_chunk0`) to avoid collisions across chunks
5. **Reassembles** — chunk entry labels are stripped, a single `entry` label is prepended, and all chunks are concatenated

Failed chunks produce a `SYMBOLIC "chunk_error:{name}"` placeholder and processing continues — partial results are always available.

## Deterministic symbolic data flow

The VM handles **all** cases deterministically — including incomplete programs with missing imports, unknown externals, and symbolic values. No LLM fallback is needed:

- **Unknown functions** — `process(items)` where `process` is an unresolved import → creates `sym_N [process(sym_M)]`
- **Unknown methods** — `conn.fetch_all("users")` on a symbolic object → creates `sym_N [sym_M.fetch_all('users')]`
- **Unknown fields** — `first.name` on a symbolic object → creates `sym_N` with hint `sym_M.name` (deduplicated: repeated access to the same field returns the same symbol)
- **Symbolic arithmetic** — `sym_0 + 1` → creates `sym_N [sym_0 + 1]` with the expression as a constraint
- **Symbolic branch conditions** — `branch_if sym_0` → takes the true branch and records `assuming sym_0 is True` as a path condition
- **Symbolic builtins** — `len(sym_0)` → creates `sym_N [len(sym_0)]`

This means the interpreter can trace data flow through programs with incomplete symbol definitions (missing imports, unavailable libraries) entirely deterministically with **0 LLM calls**.

## Dataflow analysis

The `interpreter.dataflow` module provides intraprocedural iterative dataflow analysis on the IR's control flow graph:

```python
from interpreter.cfg import build_cfg
from interpreter.dataflow import analyze

cfg = build_cfg(ir_instructions)
result = analyze(cfg)

# Reaching definitions per block
for label, facts in result.block_facts.items():
    print(f"{label}: {len(facts.reach_in)} defs reach entry")

# Def-use chains
for link in result.def_use_chains:
    print(f"{link.definition.variable} @ {link.definition.block_label} → {link.use.variable} @ {link.use.block_label}")

# Variable dependency graph (transitive)
for var, deps in result.dependency_graph.items():
    print(f"{var} depends on {deps}")
```

The analysis includes:
- **Reaching definitions** — classic worklist-based fixed-point solver (bounded by `DATAFLOW_MAX_ITERATIONS`)
- **Def-use chains** — links each use to the definition(s) that can reach it, handling both local and cross-block flows
- **Variable dependency graph** — traces register chains backward to named variables with transitive closure

All functions are pure (no mutation of inputs), calls are treated as opaque, and no type information is required.

## When the LLM is used

The LLM backend still exists but is now only invoked if the local executor encounters an opcode with no registered handler — which currently never happens since all opcodes are covered. The LLM can be used as an optional enhancement for richer symbolic reasoning (e.g., simplifying constraint expressions), but is not required for basic data flow tracking.

## Pipeline statistics

When run with `-v`, the interpreter reports per-stage timing and output statistics:

```
═══ Pipeline Statistics ═══
  Source: 7 lines, 121 bytes (python, deterministic frontend)

  Stage                      Time                          Output
  ──────────────────── ──────────   ──────────────────────────────
  Parse                    0.2ms
  Lower (frontend)         0.1ms              22 IR instructions
  Build CFG                0.0ms                 8 basic blocks
  Build registry           0.0ms          2 functions, 0 classes
  Execute (VM)             0.6ms           67 steps, 0 LLM calls
  ──────────────────── ──────────   ──────────────────────────────
  Total                   15.1ms

  Final state: 0 heap objects, 0 symbolic values, 0 closures
```

## Testing

```bash
poetry run pytest tests/ -v
```

Tests use dependency injection with fake API clients — no real LLM calls are made. The test suite (529 tests) covers:

- **Deterministic frontends** — 15 language frontends with unit tests covering declarations, expressions, control flow, functions, classes, and language-specific constructs, plus non-trivial integration tests (8-12 per language) exercising multi-statement programs with nested control flow, functions calling functions, classes with methods, and combined features
- **LLM client infrastructure** — client construction, DI, factory routing for all 4 providers
- **LLM frontend** — markdown fence stripping, JSON parsing, IR validation, prompt formatting, retry on parse failure
- **Chunked LLM frontend** — chunk extraction (functions, classes, top-level grouping), IR register/label renumbering, end-to-end chunked lowering with error resilience
- **Frontend factory** — `get_frontend()` routing for deterministic, LLM, and chunked LLM paths
- **Backend refactor** — backend construction and `get_backend()` factory
- **Closures** — simple closures, multiple closures from same factory, multi-var capture, non-closure regression
- **Dataflow analysis** — reaching definitions (linear, redefinition, branch merge, loops, empty), def-use chains (simple, redefinition shadowing, branch multi-chain, SYMBOLIC params), dependency graphs (direct, transitive, self-dependency via loops), integration (end-to-end Python→IR→CFG→dataflow), edge cases (SYMBOLIC passthrough)

## Presentation

A Reveal.js slide deck is included in `presentation/index.html`. Open it in a browser to navigate the slides. It covers the full architecture: IR design, 15 language frontends, the LLM frontend (prompt engineering, resilience pipeline, novelty vs. traditional compilers), the chunked LLM frontend with a worked example showing chunk extraction, register/label renumbering, and reassembled IR output, CFG building with CFG examples across all 15 supported languages, dataflow analysis with dependency graph visualizations, the symbolic VM, and design patterns.

## Symbolic values

When the interpreter encounters incomplete information, it creates symbolic values rather than erroring:

- **Unknown variables** — accessing an undefined variable produces a symbolic value
- **Unknown fields** — accessing a field on a heap object that doesn't have it creates a fresh symbolic value and caches it on the heap. Symbolic objects are materialised as synthetic heap entries on first access, so repeated field access (e.g., `user.profile` accessed twice) returns the same symbol
- **Unknown calls** — calling an external function returns a symbolic value with constraints describing the call (e.g., `process(sym_3)`)
- **Symbolic branches** — the VM takes the true branch and records the assumption as a path condition
