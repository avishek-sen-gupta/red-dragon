# LLM Symbolic Interpreter

A symbolic interpreter that parses source code, lowers it to a three-address code IR, builds a control flow graph, and executes it via a deterministic VM — falling back to an LLM only when the program references externals or operates on symbolic values.

## Project structure

```
interpreter.py           # CLI entry point (argparse + main)
interpreter/
├── __init__.py          # re-exports run
├── ir.py                # Opcode, IRInstruction
├── parser.py            # Tree-sitter parsing layer
├── frontend.py          # Frontend ABC, PythonFrontend, get_frontend()
├── cfg.py               # BasicBlock, CFG, build_cfg()
├── registry.py          # FunctionRegistry, build_registry(), builtins, local execution
├── vm.py                # SymbolicValue, HeapObject, StackFrame, VMState, StateUpdate
├── backend.py           # LLM backends (Claude, OpenAI)
└── run.py               # run() orchestrator
```

## How it works

```
Source Code
    │  tree-sitter
    ▼
Language-Specific AST
    │  Frontend (per language)
    ▼
Flattened High-Level TAC (IR)
    │  CFG builder
    ▼
Control Flow Graph
    │  VM + function registry
    ▼
Deterministic Execution (heap, call stack, registers)
    │  fallback on symbolic values / unknown externals
    ▼
LLM Oracle (only when needed)
```

1. **Parse** — Tree-sitter (via `tree-sitter-language-pack`) parses source into an AST
2. **Lower** — A language-specific frontend converts the AST into a flattened three-address code IR (~19 opcodes)
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
```

### CLI options

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Print IR, CFG, and step-by-step execution |
| `-l`, `--language` | Source language (default: `python`) |
| `-e`, `--entry` | Entry point label or function name |
| `-b`, `--backend` | LLM backend: `claude` or `openai` (default: `claude`) |
| `-n`, `--max-steps` | Maximum interpretation steps (default: 100) |
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

## When the LLM is used

The LLM is only invoked as an oracle when the VM encounters something it cannot resolve mechanically:

- **Symbolic arithmetic** — `sym_0 + 1` where `sym_0` is an unknown value
- **Symbolic branch conditions** — `branch_if sym_0` requires the LLM to choose a path and record a path condition
- **Unknown externals** — calls to functions not defined in the source (e.g., library functions beyond the builtin table)

For fully concrete programs, the interpreter is a deterministic VM. The LLM extends it to handle incomplete information gracefully.

## Symbolic values

When the interpreter encounters incomplete information, it creates symbolic values rather than erroring:

- **Unknown variables** — accessing an undefined variable produces a symbolic value
- **Unknown fields** — accessing a field on a heap object that doesn't have it creates a fresh symbolic value and adds the field
- **Unknown calls** — calling an external function returns a symbolic value with constraints describing the call
- **Symbolic branches** — the LLM chooses a path and records the assumption as a path condition
