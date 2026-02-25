# LLM Symbolic Interpreter

A symbolic interpreter that parses source code, lowers it to a three-address code IR, builds a control flow graph, and executes it via a deterministic VM — falling back to an LLM only when the program references externals or operates on symbolic values.

## Project structure

```
interpreter.py           # CLI entry point (argparse + main)
interpreter/
├── __init__.py          # re-exports run
├── constants.py         # Named constants (eliminates magic strings)
├── ir.py                # Opcode, IRInstruction
├── parser.py            # ParserFactory (DI), TreeSitterParserFactory, Parser
├── frontend.py          # Frontend ABC, PythonFrontend (dispatch table), get_frontend()
├── llm_client.py        # LLMClient ABC, ClaudeLLMClient, OpenAILLMClient (shared)
├── llm_frontend.py      # LLMFrontend — LLM-based source-to-IR lowering
├── cfg.py               # BasicBlock, CFG, build_cfg()
├── registry.py          # FunctionRegistry, LocalExecutor (dispatch table), builtins
├── vm.py                # SymbolicValue, VMState, StateUpdate, ExecutionResult, Operators
├── backend.py           # LLMBackend (DI for clients), ClaudeBackend, OpenAIBackend
└── run.py               # run() orchestrator (decomposed helpers)
```

## How it works

```
Source Code
    │
    ├──── deterministic path ──── tree-sitter ──── PythonFrontend ────┐
    │                                                                 │
    └──── LLM path (--frontend llm) ──── LLMFrontend ────────────────┤
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

1. **Parse** — Tree-sitter (via `tree-sitter-language-pack`) parses source into an AST (deterministic path), or the LLM lowers source directly to IR (LLM path)
2. **Lower** — A language-specific frontend converts the AST into a flattened three-address code IR (~19 opcodes). With `--frontend llm`, the LLM performs this lowering step directly from source code, enabling multi-language support without per-language frontends
3. **Build CFG** — IR instructions are partitioned into basic blocks with control flow edges
4. **Build registry** — Function and class definitions are indexed from the IR, mapping names to CFG labels and extracting parameter lists
5. **Execute** — The VM walks the CFG deterministically:
   - **Local execution** handles constants, loads, stores, arithmetic, branches, function/method calls (by stepping into the body), constructor dispatch (`__init__`), heap field access, and builtins (`len`, `range`, `print`, `int`, `str`, etc.)
   - **LLM fallback** is used only for operations on symbolic values (symbolic arithmetic, symbolic branch conditions) or calls to unknown externals not defined in the source

For programs with concrete inputs and no external dependencies, the entire execution is **deterministic with 0 LLM calls**.

## Setup

Requires Python >= 3.10 and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

Set your API key for the LLM fallback backend (only needed if execution encounters symbolic values):

```bash
export ANTHROPIC_API_KEY=sk-...   # for Claude (default)
export OPENAI_API_KEY=sk-...      # for OpenAI
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

# LLM frontend on non-Python source (multi-language support)
poetry run python interpreter.py example.js -l javascript -f llm -v
```

### CLI options

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Print IR, CFG, and step-by-step execution |
| `-l`, `--language` | Source language (default: `python`) |
| `-e`, `--entry` | Entry point label or function name |
| `-b`, `--backend` | LLM backend: `claude`, `openai`, `ollama`, or `huggingface` (default: `claude`) |
| `-n`, `--max-steps` | Maximum interpretation steps (default: 100) |
| `-f`, `--frontend` | Frontend type: `deterministic` (tree-sitter) or `llm` (default: `deterministic`) |
| `--ir-only` | Print the IR and exit |
| `--cfg-only` | Print the CFG and exit |

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

## Deterministic symbolic data flow

The VM handles **all** cases deterministically — including incomplete programs with missing imports, unknown externals, and symbolic values. No LLM fallback is needed:

- **Unknown functions** — `process(items)` where `process` is an unresolved import → creates `sym_N [process(sym_M)]`
- **Unknown methods** — `conn.fetch_all("users")` on a symbolic object → creates `sym_N [sym_M.fetch_all('users')]`
- **Unknown fields** — `first.name` on a symbolic object → creates `sym_N` with hint `sym_M.name` (deduplicated: repeated access to the same field returns the same symbol)
- **Symbolic arithmetic** — `sym_0 + 1` → creates `sym_N [sym_0 + 1]` with the expression as a constraint
- **Symbolic branch conditions** — `branch_if sym_0` → takes the true branch and records `assuming sym_0 is True` as a path condition
- **Symbolic builtins** — `len(sym_0)` → creates `sym_N [len(sym_0)]`

This means the interpreter can trace data flow through programs with incomplete symbol definitions (missing imports, unavailable libraries) entirely deterministically with **0 LLM calls**.

## When the LLM is used

The LLM backend still exists but is now only invoked if the local executor encounters an opcode with no registered handler — which currently never happens since all opcodes are covered. The LLM can be used as an optional enhancement for richer symbolic reasoning (e.g., simplifying constraint expressions), but is not required for basic data flow tracking.

## Symbolic values

When the interpreter encounters incomplete information, it creates symbolic values rather than erroring:

- **Unknown variables** — accessing an undefined variable produces a symbolic value
- **Unknown fields** — accessing a field on a heap object that doesn't have it creates a fresh symbolic value and caches it on the heap. Symbolic objects are materialised as synthetic heap entries on first access, so repeated field access (e.g., `user.profile` accessed twice) returns the same symbol
- **Unknown calls** — calling an external function returns a symbolic value with constraints describing the call (e.g., `process(sym_3)`)
- **Symbolic branches** — the VM takes the true branch and records the assumption as a path condition
