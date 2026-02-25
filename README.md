# LLM Symbolic Interpreter

A symbolic interpreter where an LLM steps through IR instructions, maintaining a symbolic heap that handles incomplete information — unknown types, unseen fields, and symbolic values.

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
    │  LLM + local execution
    ▼
Symbolic VM State (heap, call stack, registers)
```

1. **Parse** — Tree-sitter (via `tree-sitter-language-pack`) parses source into an AST
2. **Lower** — A language-specific frontend converts the AST into a flattened three-address code IR (~19 opcodes)
3. **Build CFG** — IR instructions are partitioned into basic blocks with control flow edges
4. **Interpret** — The interpreter walks the CFG. Mechanical operations (constants, loads, stores, branches on concrete values, arithmetic) execute locally. Semantic operations (function calls, symbolic arithmetic, symbolic branches) are sent to the LLM, which returns a JSON state delta applied to the VM

## Setup

Requires Python >= 3.10 and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

Set your API key for the chosen backend:

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

# Inspect IR only (no LLM calls)
poetry run python interpreter.py myfile.py --ir-only

# Inspect CFG only (no LLM calls)
poetry run python interpreter.py myfile.py --cfg-only

# Use OpenAI backend
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

## Example output

```
$ poetry run python interpreter.py -v

[step 0] entry:0  branch end_factorial_1
  [local] branch → end_factorial_1

[step 1] end_factorial_1:0  %12 = const <function:factorial@func_factorial_0>
  [local] const '<function:factorial@func_factorial_0>' → %12

[step 2] end_factorial_1:1  store_var factorial %12
  [local] store factorial = '<function:factorial@func_factorial_0>'

[step 3] end_factorial_1:2  %13 = const 5
  [local] const '5' → %13

[step 4] end_factorial_1:3  %14 = call_function factorial %13
  [LLM] recursive call to user-defined function factorial with argument 5
    %14 = sym_0 [factorial(5)]

[step 5] end_factorial_1:4  store_var result %14
  [local] store result = sym_0 [factorial(5)]

(7 steps, 1 LLM calls)
```

Mechanical operations run locally (`[local]`). Only the call to user-defined `factorial` requires the LLM (`[LLM]`), which returns a symbolic value `sym_0` with constraint `factorial(5)`.

## Symbolic values

When the interpreter encounters incomplete information, it creates symbolic values rather than erroring:

- **Unknown variables** — accessing an undefined variable produces a symbolic value
- **Unknown fields** — accessing a field on a heap object that doesn't have it creates a fresh symbolic value and adds the field
- **Unknown calls** — calling a user-defined or unknown function returns a symbolic value with constraints describing the call
- **Symbolic branches** — the LLM chooses a path and records the assumption as a path condition
