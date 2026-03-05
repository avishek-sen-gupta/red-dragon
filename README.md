<p align="center">
  <img src="banner.svg" alt="RedDragon — Multi-language code analysis and execution" width="900">
</p>

# RedDragon

![CI](https://github.com/avishek-sen-gupta/red-dragon/actions/workflows/ci.yml/badge.svg) [![Technical Presentation](https://img.shields.io/badge/Technical-slides-blue)](presentation/technical-presentation.html) [![Overview Presentation](https://img.shields.io/badge/Overview-slides-green)](presentation/overview-presentation.html) [![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE.md)

**RedDragon** is an experiment in building infrastructure for **reverse-engineering frequently-incomplete code** — the kind found in legacy migrations, decompiled binaries, partial extracts, and codebases with missing dependencies. It explores three ideas:

1. **Deterministic language frontends with LLM-assisted repair** — tree-sitter frontends (15 languages) and a ProLeap bridge (COBOL) handle well-formed source deterministically. When tree-sitter hits malformed syntax, an optional **LLM repair loop** fixes only the broken fragments and re-parses, maximising deterministic coverage for real-world incomplete code. All paths produce the same universal [27-opcode IR](docs/ir-reference.md).
2. **Full LLM frontends for unsupported languages** — for languages without a tree-sitter frontend, an LLM lowers source to IR entirely — supporting any language without new parser code. A chunked variant splits large files into per-function chunks via tree-sitter, lowering each independently. Both produce the same [27-opcode IR](docs/ir-reference.md).
3. **A VM that integrates LLMs to produce plausible state changes** when execution hits missing dependencies, unresolved imports, or unknown externals — keeping execution moving through incomplete programs instead of halting at the first unknown.

When source is complete and all dependencies are present, the entire pipeline (parse → lower → execute) is **deterministic with 0 LLM calls**. LLMs are only invoked at the boundaries where information is genuinely missing.

Concretely, RedDragon:

- **Parses and lowers** source in 15 languages via tree-sitter (with optional LLM-assisted repair of malformed syntax), COBOL via ProLeap parser bridge, or **any language** via full LLM-based lowering (including chunked lowering for large files) — each frontend owns its parsing internally; callers only provide `source: bytes`
- **Produces** a universal flattened three-address code IR ([27 opcodes](docs/ir-reference.md), including 3 byte-addressed memory region opcodes and 2 named continuation opcodes) with structured source location traceability (every IR instruction from deterministic frontends carries its originating AST span; LLM frontends lack AST nodes and produce `NO_SOURCE_LOCATION`); each instruction carries an optional `type_hint` field for future type-aware execution — the LLM frontend uses the LLM as a **compiler frontend**, constrained by a formal IR schema with concrete patterns
- **Builds** control flow graphs from IR instructions
- **Analyses** data flow via iterative reaching definitions, def-use chains, and variable dependency graphs
- **Executes** programs via a deterministic VM — tracking data flow through incomplete programs with missing imports or unknown externals entirely without LLM calls — with a configurable **LLM plausible-value resolver** that can replace symbolic placeholders with concrete values for unresolved function/method calls

## How it works

```mermaid
flowchart TD
    SRC[Source Code] --> DET["tree-sitter<br>15 languages"]
    SRC --> COBOL["ProLeap Bridge<br>COBOL"]
    SRC --> LLM["LLM Frontend<br>any language"]
    SRC --> CHUNK["Chunked LLM<br>chunk → LLM × N → renumber → reassemble"]

    DET --> REPAIR["AST Repair (optional)<br>LLM fixes ERROR/MISSING nodes"]
    REPAIR --> IR[Flattened TAC IR]
    DET -->|no errors| IR
    COBOL --> IR
    LLM --> IR
    CHUNK --> IR

    IR --> CFG[Control Flow Graph]
    CFG --> DF["Dataflow Analysis<br>reaching defs · def-use chains · dependency graphs"]
    CFG --> VM[Deterministic VM Execution]
    VM -->|symbolic values only| ORACLE[LLM Oracle]
```

For programs with concrete inputs and no external dependencies, the entire execution is **deterministic with 0 LLM calls**.

### Execution replay in Rev-Eng TUI

![Execute Screen](docs/screenshots/execute-screen.png)
> Step-by-step execution replay via [Rev-Eng TUI](https://github.com/avishek-sen-gupta/reddragon-codescry-tui) — IR with current instruction highlighted, Frame (registers + locals) and Heap (objects + path conditions) in side-by-side panes.

## Setup

### Prerequisites

| Dependency | Required for | Install |
|------------|-------------|---------|
| Python >= 3.10 | Core | [python.org](https://www.python.org/) or your package manager |
| [Poetry](https://python-poetry.org/) | Dependency management | `pipx install poetry` |
| JDK 17+ | COBOL frontend only | [adoptium.net](https://adoptium.net/) or `brew install openjdk@17` |
| [Maven](https://maven.apache.org/) | Building ProLeap bridge | `brew install maven` or [maven.apache.org](https://maven.apache.org/install.html) |

### Full build (including COBOL)

```bash
git clone --recurse-submodules https://github.com/avishek-sen-gupta/red-dragon.git
cd red-dragon

# 1. Python dependencies
poetry install

# 2. ProLeap COBOL bridge (requires JDK 17+ and Maven)
cd proleap-bridge && ./build.sh && cd ..
# Produces: proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar

# 3. Verify
poetry run python -m pytest tests/unit/ -x -q       # unit tests (no external deps)
poetry run python -m pytest tests/integration/ -x -q # integration tests (needs ProLeap JAR)
```

### Minimal build (without COBOL)

```bash
git clone https://github.com/avishek-sen-gupta/red-dragon.git
cd red-dragon
poetry install
poetry run python -m pytest tests/unit/ -x -q
```

All 15 tree-sitter frontends and the LLM frontends work without JDK/Maven. COBOL integration tests skip gracefully when the ProLeap JAR is not present.

### ProLeap bridge standalone usage

```bash
cat myprogram.cbl | java -jar proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
java -jar proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar myprogram.cbl
java -jar proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar -format TANDEM myprogram.cbl
```

### LLM API keys (optional)

Only needed for `--frontend llm` or when execution encounters symbolic values:

```bash
export ANTHROPIC_API_KEY=sk-...          # for Claude (default)
export OPENAI_API_KEY=sk-...             # for OpenAI
export HUGGING_FACE_API_TOKEN=hf_...     # for HuggingFace Inference Endpoints
# Ollama requires no API key (runs locally at localhost:11434)
```

## Usage

```bash
poetry run python interpreter.py myfile.py -v            # run on a file
poetry run python interpreter.py myfile.py --ir-only      # inspect IR only
poetry run python interpreter.py myfile.py --cfg-only     # inspect CFG only
poetry run python interpreter.py example.js -l javascript  # non-Python source
poetry run python interpreter.py myfile.py -f llm -v       # LLM frontend
poetry run python interpreter.py myfile.py -f chunked_llm  # chunked LLM frontend
poetry run python interpreter.py example.cob -l cobol         # COBOL via ProLeap bridge
export PROLEAP_BRIDGE_JAR=/path/to/bridge.jar                 # optional: custom bridge JAR path
poetry run python interpreter.py myfile.py --mermaid        # output CFG as Mermaid flowchart
poetry run python interpreter.py myfile.py --mermaid --function foo  # CFG for a single function
```

| Flag | Description |
|------|-------------|
| `-v` | Print IR, CFG, and step-by-step execution |
| `-l` | Source language (default: `python`) |
| `-b` | LLM backend: `claude`, `openai`, `ollama`, `huggingface` (default: `claude`) |
| `-n` | Maximum interpretation steps (default: 100) |
| `-f` | Frontend: `deterministic`, `llm`, `chunked_llm`, `cobol` (default: `deterministic`) |
| `--ir-only` | Print the IR and exit |
| `--cfg-only` | Print the CFG and exit |
| `--mermaid` | Output CFG as a Mermaid flowchart diagram and exit |
| `--function` | Extract CFG for a single function (use with `--mermaid` or `--cfg-only`) |

### Programmatic API

All CLI pipelines are available as composable functions — no argparse required.

#### Deterministic (no LLM calls)

```python
from interpreter import lower_source, dump_ir, build_cfg_from_source, dump_cfg, dump_mermaid, extract_function_source, ir_stats, run
from interpreter.constants import Language

source = """
def factorial(n):
    if n <= 1:
        return n
    return n * factorial(n - 1)
result = factorial(6)
"""

# Parse and lower to IR via tree-sitter (0 LLM calls)
instructions = lower_source(source, language=Language.PYTHON)
instructions = lower_source(source, language="javascript")  # strings still accepted

# Get IR as text
ir_text = dump_ir(source, language=Language.PYTHON)

# Build a CFG (optionally scoped to a single function)
cfg = build_cfg_from_source(source, function_name="factorial")

# Get CFG or Mermaid text
cfg_text = dump_cfg(source)
mermaid = dump_mermaid(source, function_name="factorial")

# Extract raw source text of a named function (recursive — finds methods and nested functions)
fn_source = extract_function_source(source, "factorial", language=Language.PYTHON)

# Get opcode frequency counts
stats = ir_stats(source, language=Language.PYTHON)  # e.g. {"CONST": 3, "STORE_VAR": 2, ...}

# Full pipeline: parse → lower → CFG → execute (deterministic, 0 LLM calls)
vm = run(source, language=Language.PYTHON, verbose=True)
frame = vm.call_stack[0]
print(frame.local_vars["result"])  # 720
```

#### With LLM calls

```python
from interpreter import lower_source, run
from interpreter.constants import Language
from interpreter import constants
from interpreter.run_types import UnresolvedCallStrategy

# LLM frontend: the LLM acts as a compiler frontend, lowering source to IR
# Works for any language, even those without a tree-sitter frontend
instructions = lower_source(
    "x = math.sqrt(16)\ny = x + 1\n",
    language=Language.PYTHON,
    frontend_type=constants.FRONTEND_LLM,       # or "chunked_llm" for large files
    backend="claude",                            # or "openai", "ollama", "huggingface"
)

# LLM resolver: deterministic frontend + LLM resolves external/missing dependencies
# math.sqrt and math.floor are external — the LLM provides plausible concrete values
vm = run(
    "import math\nx = math.sqrt(16)\ny = math.floor(7.8)\n",
    language=Language.PYTHON,
    unresolved_call_strategy=UnresolvedCallStrategy.LLM,
    backend="claude",
)
frame = vm.call_stack[0]
print(frame.local_vars["x"])  # 4.0 (resolved by LLM)
print(frame.local_vars["y"])  # 7   (resolved by LLM)

# LLM frontend for an unsupported language (no tree-sitter frontend needed)
from interpreter.llm_client import get_llm_client
from interpreter.llm_frontend import LLMFrontend
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter import execute_cfg, VMConfig

haskell_source = "factorial 0 = 1\nfactorial n = n * factorial (n - 1)\nx = factorial 5\n"
llm_client = get_llm_client(provider="claude")
frontend = LLMFrontend(llm_client=llm_client, language="haskell")
instructions = frontend.lower(haskell_source.encode("utf-8"))

cfg = build_cfg(instructions)
registry = build_registry(instructions, cfg)
vm, stats = execute_cfg(cfg, cfg.entry, registry, VMConfig(max_steps=200))
```

#### Standalone VM execution

`execute_cfg` runs a pre-built CFG without re-running the full parse → lower → build pipeline — useful for programmatic use where you build/customize the CFG and registry independently:

```python
from interpreter import lower_source, execute_cfg, VMConfig
from interpreter.constants import Language
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry

instructions = lower_source(source, language=Language.PYTHON)
cfg = build_cfg(instructions)
registry = build_registry(instructions, cfg)

vm, stats = execute_cfg(cfg, "entry", registry, VMConfig(max_steps=200))
# stats.steps, stats.llm_calls, stats.final_heap_objects, ...
```

| Function | Returns | Purpose |
|---|---|---|
| `lower_source(source, language, frontend_type, backend)` | `list[IRInstruction]` | Parse + lower source to IR |
| `dump_ir(source, language, frontend_type, backend)` | `str` | IR text output |
| `build_cfg_from_source(source, language, frontend_type, backend, function_name)` | `CFG` | Parse → lower → optionally slice → build CFG |
| `dump_cfg(source, language, frontend_type, backend, function_name)` | `str` | CFG text output |
| `dump_mermaid(source, language, frontend_type, backend, function_name)` | `str` | Mermaid flowchart output |
| `ir_stats(source, language, frontend_type, backend)` | `dict[str, int]` | Opcode frequency counts |
| `extract_function_source(source, function_name, language)` | `str` | Raw source text of a named function (recursive AST walk) |
| `execute_cfg(cfg, entry_point, registry, config)` | `(VMState, ExecutionStats)` | Execute a pre-built CFG from a given entry point |
| `execute_traced(source, language, function_name, entry_point, frontend_type, backend, max_steps)` | `ExecutionTrace` | Parse → lower → CFG → execute with per-step VMState snapshots for replay |

Functions compose hierarchically: `dump_ir` calls `lower_source`; `dump_cfg` and `dump_mermaid` call `build_cfg_from_source`, which calls `lower_source`. Full execution is available via `interpreter.run()`, via `execute_cfg()` for standalone VM execution with a pre-built CFG, or via `execute_traced()` for step-by-step replay with VMState snapshots at each instruction.

## Supported languages

15 deterministic tree-sitter frontends (0 LLM calls):

Python, JavaScript, TypeScript, Java, Ruby, Go, PHP, C#, C, C++, Rust, Kotlin, Scala, Lua, Pascal

Control flow constructs (if/else, while, for, for-of/foreach, switch, break/continue, try/catch/finally, do-while) are lowered into real LABEL+BRANCH IR rather than `SYMBOLIC` placeholders.

<details>
<summary><strong>Language-specific features</strong> (click to expand)</summary>

| Language | Supported constructs |
|----------|---------------------|
| **Python** | list/dict/set comprehensions (including nested), generator expressions, with statements, decorators, lambdas, yield/await, assert, import/from-import, walrus operator (`:=`), match statements (3.10+), delete, slicing, f-string interpolation, list/dict/splat patterns, ellipsis (`...`), splat/spread (`*args`, `**kwargs` in expressions), expression lists, dotted names |
| **JS/TS** | destructuring, for-of/for-in loops, switch, do-while, new expressions, template string substitutions, regex literals, spread/sequence/yield/await expressions, function expressions, class static blocks, labeled statements, abstract classes (TS), import/export statements, public field definitions (TS), class field definitions (`#private = 0`), export clauses (`export { a, b }`), with statements, abstract method signatures (TS), namespaces/internal modules (TS) |
| **Ruby** | symbols, ranges, regex, lambdas, string/symbol arrays (`%w`/`%i`), case/when, case/in pattern matching, modules, global/class variables, heredocs, if/unless/while/until modifiers, ternary operator, unary operators, `self`, singleton classes/methods, element reference (array indexing), string interpolation (`"Hello #{expr}"`), heredoc interpolation (`<<~HEREDOC\nHello #{expr}\nHEREDOC`), hash key symbols, `super`, `yield`, delimited symbols (`:"dynamic"`), `retry`, class instantiation (`Counter.new()`), instance variable field semantics (`@var` → `LOAD_FIELD`/`STORE_FIELD`), `initialize` → `__init__` constructor mapping |
| **PHP** | switch, do-while, match expressions, arrow functions, scoped calls (`Class::method`), namespaces, interfaces, traits, enums, static variables, goto/labels, anonymous functions (closures), null-safe access (`?->`), null-safe method calls (`?->method()`), class constant access, property declarations, yield, heredoc/nowdoc, string interpolation (`"Hello $name"` / `"Hello {$expr}"` / heredoc interpolation), relative scope (`self::`/`static::`), dynamic variable names (`$$x`), global declarations, include/require_once expressions, variadic unpacking (`...$arr`) |
| **Java** | records, instanceof, method references (`Type::method`), lambdas, class literals (`Type.class`), do-while, assert, labeled statements, synchronized blocks, static initializers, explicit constructor invocations (`super()`/`this()`), annotation type declarations, scoped identifiers (`java.lang.System`), switch expressions (Java 14+, including expression_statement and throw in arms) |
| **C#** | await, yield, switch expressions (C# 8), lock, using statements, checked/fixed blocks, events, typeof, is-check, property declarations, lambdas, null-conditional access (`?.`), local functions, tuples, is-pattern expressions, declaration patterns, array initializer expressions, string interpolation (`$"Hello {expr}"` — format specifiers and alignment clauses are discarded as presentation-only), record declarations, verbatim strings (`@"..."`), constant patterns, delegate declarations, implicit object creation (`new()`), LINQ query expressions (`from...where...select`) |
| **C** | pointer dereference/address-of, sizeof, compound literals, struct/union/enum definitions, initializer lists, designated initializers (`.field = value`), goto/labels, typedef, char literals, function-like macros (`#define MAX(a, b) ...`) |
| **C++** | lambda expressions (closures), field initializer lists, delete expressions, enum class, array subscript expressions, C++20 concepts |
| **Kotlin** | do-while, object declarations (singletons), companion objects, enum classes, not-null assertion (`!!`), is-check, type tests (`is Type` in `when`), type aliases, elvis operator (`?:`), infix expressions, indexing expressions, type casts (`as`), conjunction/disjunction expressions, hex literals, character literals, string interpolation (`"$name"` / `"${expr}"`), multi-variable destructuring (`val (a, b) = pair`), range expressions (`1..10`), anonymous object literals (`object : Type { ... }`), labels (`outer@`) |
| **Go** | defer, go, switch/type-switch/select, channel send/receive (including `select` receive statements), slices, type assertions, func literals, labeled statements, const declarations, goto, multi-name var declarations (`var a, b = 1, 2`), var blocks (`var (...)`) |
| **Rust** | closures (`\|x\| expr`), traits, enums, const/static/type items, try (`?`), await, async blocks, mod/unsafe blocks, type casts (`as`), scoped identifiers (`HashMap::new`), tuple destructuring (`let (a, b) = expr`), struct destructuring (`let Point { x, y } = p`), range expressions (`0..10`, `0..=n`), match pattern unwrap, tuple struct patterns (`Some(v)`), struct patterns in match, generic/turbofish syntax (`parse::<i32>()`), `if let`/`while let` conditions, trait function signatures (`fn area(&self) -> f64;`) |
| **Scala** | for-comprehensions, traits, case classes, lazy vals, do-while, type definitions, `new` expressions, throw expressions, string interpolation (`s"$name"` / `s"${expr}"`), tuple destructuring (`val (a, b) = expr`), operator identifiers, case class patterns (`Circle(r)`), typed patterns (`i: Int`), guards (`if condition`), tuple patterns in match, abstract function declarations, infix patterns (`head :: tail`), case blocks |
| **Lua** | anonymous functions, varargs, goto/labels |
| **Pascal** | nested functions, field access, array indexing, unary operators, case-of, repeat-until, set literals, const/type/uses declarations, parenthesized expressions, try/except/finally, exception handlers (`on E: Exception do`), raise, ranges (`4..10`), with statements, inherited calls |

</details>

## Example: CFG

```python
def classify(x):
    if x > 0:
        label = "positive"
    else:
        label = "negative"
    return label
```

```mermaid
flowchart TD
    entry(["<b>entry</b><br>LOAD x · CONST 0 · BINOP ><br>BRANCH_IF"])
    if_true["<b>if_true</b><br>CONST &quot;positive&quot;<br>STORE_VAR label"]
    if_false["<b>if_false</b><br>CONST &quot;negative&quot;<br>STORE_VAR label"]
    merge(["<b>merge</b><br>LOAD_VAR label<br>RETURN"])

    entry -- T --> if_true
    entry -- F --> if_false
    if_true --> merge
    if_false --> merge
```

Function bodies appear as subgraphs with dashed call edges (`-.->|"call"|`) connecting `CALL_FUNCTION` sites to function entry blocks. Blocks with more than 6 instructions are collapsed to show the first 4 lines, an `... (N more)` placeholder, and the terminator — keeping CFG diagrams readable without hiding critical branch/return instructions. All 15 frontends produce the same CFG shape for equivalent logic.

## Example: deterministic execution (0 LLM calls)

```python
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

result = factorial(5)
```

```
[step 4]  call factorial(5) → dispatch to func_factorial_0
[step 53] binop 1 <= 1 = True   ← base case
[step 56] return 1               ← unwind begins
[step 57] 2 * 1 = 2 → 3 * 2 = 6 → 4 * 6 = 24 → 5 * 24 = 120
[step 65] store_var result 120

Final state: result = 120  (67 steps, 0 LLM calls)
```

The VM also handles classes with heap allocation, method dispatch, field access, closures with shared mutable environments (capture-by-reference — mutations inside closures persist across calls and are visible to sibling closures from the same scope), byte-addressed memory regions (`ALLOC_REGION`/`WRITE_REGION`/`LOAD_REGION` for COBOL-style REDEFINES overlays), named continuations (`SET_CONTINUATION`/`RESUME_CONTINUATION` for COBOL PERFORM return semantics), **data layout preservation** (COBOL field names, offsets, lengths, and type metadata are attached to `VMState.data_layout` after execution — enabling field-name-based memory inspection instead of raw byte offsets), and builtins (`len`, `range`, `print`, `int`, `str`, byte-manipulation primitives, etc.) — all deterministically. The interpreter's execution engine is split into focused modules: `interpreter/vm_types.py` (VM data types), `interpreter/cfg_types.py` (CFG data types), `interpreter/run_types.py` (pipeline config/stats types), `interpreter/registry.py` (function/class registry), `interpreter/builtins.py` (built-in function table), `interpreter/executor.py` (opcode handlers and dispatch), and `interpreter/cobol/` (COBOL type system, EBCDIC tables, and IR encoder/decoder builders).

## Handling incomplete programs

When the interpreter encounters incomplete information (missing imports, unknown externals), it creates symbolic placeholder values rather than erroring:

- `process(items)` where `process` is unresolved → `sym_N [process(sym_M)]`
- `obj.method(arg)` on a symbolic object → `sym_N [sym_M.method(arg)]`
- `obj.field` on a symbolic object → `sym_N` (deduplicated across repeated accesses)
- `sym_0 + 1` → `sym_N [sym_0 + 1]` (symbolic arithmetic with constraints)
- `branch_if sym_0` → takes true branch, records path condition

This means data flow through programs with missing dependencies is traced entirely deterministically with **0 LLM calls**.

### Configurable unresolved call resolution

When the VM encounters a call to an unresolved function (e.g., `math.sqrt(16)`), the default behavior creates symbolic values that propagate through subsequent computation. The `UnresolvedCallStrategy` enum controls this:

- **`SYMBOLIC`** (default) — creates symbolic placeholders: `math.sqrt(16) → sym_N`, subsequent `sym_N + 1 → sym_M` (precision death)
- **`LLM`** — makes a lightweight LLM call to get a plausible concrete value: `math.sqrt(16) → 4.0`, subsequent `4.0 + 1 = 5.0` (precision preserved), with support for side effects via `heap_writes`/`var_writes`

```python
from interpreter.run import run
from interpreter.run_types import UnresolvedCallStrategy

vm = run(source, language="python", unresolved_call_strategy=UnresolvedCallStrategy.LLM)
```

## Dataflow analysis

Iterative intraprocedural analysis on the CFG: **reaching definitions**, **def-use chains**, and **variable dependency graphs** (both direct and transitive closure). Covers all value-producing opcodes including byte-addressed memory region operations (`ALLOC_REGION`, `LOAD_REGION`, `WRITE_REGION`), ensuring complete dataflow tracking for COBOL programs.

### Example: dependency graph

```python
a = 1
b = 2
c = a + b
d = a * b
e = c + d
f = e - a

def square(x):
    return x * x

g = square(c)
h = g + f
total = h + e + b
```

Diamond dependencies (`c` and `d` both depend on `a` and `b`), function calls (`g = square(c)`), and multi-operand expressions (`total = h + e + b`). The direct dependency graph ([docs/graph.md](docs/graph.md)):

```mermaid
flowchart BT
    a["a"]
    b["b"]
    c["c"]
    d["d"]
    e["e"]
    f["f"]
    g["g"]
    h["h"]
    total["total"]
    a --> c
    b --> c
    a --> d
    b --> d
    c --> e
    d --> e
    a --> f
    e --> f
    c --> g
    f --> h
    g --> h
    b --> total
    e --> total
    h --> total
```

`total` directly depends on `h`, `e`, and `b`. The transitive closure adds `a`, `c`, `d`, `f`, and `g`. See [`scripts/demo_dataflow.py`](scripts/demo_dataflow.py) for the full pipeline (lowering → CFG → reaching definitions → dependency graph → Mermaid visualisation).

## LLM frontend

The LLM frontend (`--frontend llm`) sends source to an LLM constrained by a formal [IR schema](docs/ir-reference.md) — the LLM acts as a **compiler frontend**, not a reasoning engine. The prompt provides all 27 opcode schemas, concrete patterns for functions/classes/control flow, and a full worked example. On malformed JSON, the call is retried up to 3 times.

The **chunked LLM frontend** (`--frontend chunked_llm`) handles large files by decomposing them into per-function/class chunks via tree-sitter, lowering each independently, then renumbering registers/labels and reassembling. Failed chunks produce `SYMBOLIC` placeholders.

All providers are accessed through [LiteLLM](https://github.com/BerriAI/litellm), a unified completion interface that routes to provider-specific APIs internally.

| Provider | Flag | Notes |
|----------|------|-------|
| Claude | `-b claude` | Requires `ANTHROPIC_API_KEY` |
| OpenAI | `-b openai` | Requires `OPENAI_API_KEY` |
| HuggingFace | `-b huggingface` | Inference Endpoints, requires `HUGGING_FACE_API_TOKEN` |
| Ollama | `-b ollama` | Local, no API key needed |

Demo scripts exercising the LLM integration:

```bash
poetry run python scripts/demo_llm_e2e.py             # LLM frontend + LLM resolver (Python)
poetry run python scripts/demo_unsupported_language.py  # LLM frontend for Haskell (no tree-sitter)
poetry run python scripts/run_chunked_demo.py           # chunked LLM frontend
poetry run python scripts/demo_ast_repair.py            # LLM-assisted AST repair for malformed source
```

## LLM-assisted AST repair

When tree-sitter parses malformed source, it produces ERROR/MISSING nodes that fall through to `SYMBOLIC "unsupported:ERROR"`. The **AST repair** feature uses an LLM to fix broken syntax before deterministic lowering, maximising deterministic IR coverage for real-world incomplete code.

```python
from interpreter.frontend import get_frontend
from interpreter.llm_client import get_llm_client

repair_llm = get_llm_client(provider="claude")
frontend = get_frontend("python", repair_client=repair_llm)
ir = frontend.lower(malformed_source)
```

The repair is:
- **Optional** — enabled only when `repair_client` is provided to `get_frontend()`
- **Centralised** — wraps any deterministic frontend via decorator; all 15 languages get it for free
- **Retry-capable** — configurable max attempts (`RepairConfig(max_retries=3)`)
- **Safe** — if all retries fail, falls back to the original source (ERROR nodes become SYMBOLIC as before)

## Testing

```bash
poetry run pytest tests/ -v          # all tests (parallel by default via pytest-xdist)
poetry run pytest tests/unit/ -v     # unit tests only
poetry run pytest tests/integration/ -v  # integration tests only
poetry run pytest tests/ -n 0 -v     # disable parallel execution
```

Tests are organised into `tests/unit/` (pure logic, no I/O) and `tests/integration/` (LLM calls, databases, external repos). Unit tests use dependency injection (no real LLM calls). Covers all 15 language frontends, LLM client/frontend/chunked frontend, CFG building, dataflow analysis, closures (including mutation persistence and accumulator semantics, cross-language via Rosetta — both nested-function and lambda/arrow-function forms), class/struct instantiation with method dispatch (12 languages: Python, Java, C#, Kotlin, Scala, JS, TS, PHP, Go, C++, Rust, Ruby) and field access (cross-language), exception handling structure (cross-language), VM execution, factory routing, and the composable API layer.

### Rosetta cross-language suite

The **Rosetta suite** (`tests/unit/rosetta/`) implements 14 cross-language test sets (8 algorithms + closures + closures-lambda + classes + exceptions + destructuring + nested functions) and verifies they produce clean, structurally consistent IR. 11 sets cover all 15 languages; the closures-lambda set covers the 5 languages with lambda/arrow-function closure syntax (Python, JavaScript, TypeScript, Kotlin, Scala); the destructuring set covers the 6 languages with dedicated destructuring lowering (Python, JavaScript, TypeScript, Rust, Scala, Kotlin); the nested functions set covers the 10 languages with genuine nested function syntax (Python, JavaScript, TypeScript, Rust, Lua, Ruby, Go, Kotlin, Scala, PHP). Each problem tests:

- Entry label presence and minimum instruction count
- Zero unsupported `SYMBOLIC` nodes
- Required opcode presence and operator spot-checks
- Aggregate cross-language variance

**VM execution verification** runs 7 algorithms plus closures, classes, exceptions, destructuring, and nested functions through the VM and asserts correct computed results (factorial=120, fib(10)=55, gcd(48,18)=6, sorted arrays, interprocedural double_add(3,4)=14, closure make_adder(10)(5)=15, counter=3, try-body=-1, destructured a+b=15, nested outer(3)=11) with zero LLM calls. Additionally, **inner function scoping** is verified for 7 languages (Python, JavaScript, TypeScript, Rust, Go, Kotlin, Scala) — confirming that inner functions are inaccessible outside the enclosing function's scope (the VM produces a symbolic value instead of a concrete result).

All frontends emit **canonical Python-form literals** (`"None"`, `"True"`, `"False"`) — language-native forms (`nil`, `null`, `undefined`, `NULL`, `true`, `false`) are canonicalized at lowering time.

### Equivalence suite

The **equivalence suite** (`tests/unit/equivalence/`) verifies that all 15 frontends produce **structurally identical IR** for the same algorithm. Function bodies are extracted, LABEL pseudo-instructions stripped, and raw opcode sequences compared across all languages. Currently covers recursive and iterative factorial. Iterative factorial achieves full 15-language equivalence; recursive factorial has 4 frontends (kotlin, pascal, rust, scala) with minor redundant instructions pending cleanup.

### Exercism integration suite

The **Exercism suite** (`tests/unit/exercism/`) pulls canonical test data from [Exercism's problem-specifications](https://github.com/exercism/problem-specifications) and runs solutions in all 15 languages. Each exercise is parametrized across all canonical test cases.

<details>
<summary><strong>Exercism exercise breakdown</strong> (click to expand)</summary>

| Exercise | Constructs tested | Cases | Execution | Total |
|----------|-------------------|-------|-----------|-------|
| **leap** | modulo, boolean logic, short-circuit eval | 9 | 270 | **287** |
| **collatz-conjecture** | while loop, conditional, integer division | 4 | 120 | **137** |
| **difference-of-squares** | while loop, accumulator, function composition | 9 | 270 | **287** |
| **two-fer** | string concatenation, string literals | 3 | 90 | **107** |
| **hamming** | string indexing, character comparison, while loop | 5 | 150 | **167** |
| **reverse-string** | backward iteration, string building | 5 | 150 | **167** |
| **rna-transcription** | multi-branch if, char mapping | 6 | 180 | **197** |
| **perfect-numbers** | divisor loop, three-way return | 9 | 270 | **287** |
| **triangle** | nested ifs, validity guards, float sides | 21 | 630 | **647** |
| **space-age** | float division, string-to-number mapping | 8 | 240 | **257** |
| **grains** | exponentiation, large integers (2^63) | 8 | 240 | **257** |
| **isogram** | nested while loops, case-insensitive comparison | 14 | 420 | **437** |
| **nth-prime** | nested loops, trial division, primality testing | 3 | 90 | **107** |
| **resistor-color** | string-to-integer mapping, string equality | 3 | 90 | **107** |
| **pangram** | nested loops, letter search, toLowerChar helper | 11 | 330 | **347** |
| **bob** | string classification, multi-branch return | 22 | 616 | **633** |
| **luhn** | charToDigit helper, right-to-left traversal, modulo | 22 | 660 | **677** |
| **acronym** | toUpperChar helper, word boundary detection | 9 | 252 | **269** |
| **Total** | | **171** | **5068** | **5374** |

</details>

## Code quality

Static analysis tools run in CI as a report-only job (non-blocking). To run locally:

```bash
poetry run radon cc interpreter/ -s -n C       # cyclomatic complexity (grade C and above)
poetry run radon mi interpreter/ -s -n B        # maintainability index (grade B and below)
poetry run pylint interpreter/ --exit-zero      # linting (report only)
poetry run lint-imports                         # architectural import contracts
poetry run pydeps interpreter --no-show -T png  # dependency graph (requires graphviz)
```

| Tool | Purpose |
|------|---------|
| [radon](https://radon.readthedocs.io/) | Cyclomatic complexity and maintainability index |
| [pylint](https://pylint.readthedocs.io/) | Static linting (configured in `.pylintrc`) |
| [import-linter](https://import-linter.readthedocs.io/) | Architectural boundary contracts (configured in `.importlinter`) |
| [pydeps](https://github.com/thebjorn/pydeps) | Module dependency visualization |

Import-linter enforces two architectural contracts: the VM/executor/run layer must not import frontends, and the IR module must remain a leaf with no imports from other interpreter modules.

## Documentation

- **[VM Design Document](docs/notes-on-vm-design.md)** — Comprehensive technical deep-dive into the VM architecture: IR design, CFG construction, state model, execution engine, call dispatch, best-effort execution, closures, LLM fallback, dataflow analysis, and end-to-end worked examples with code references
- **[Frontend Design Document](docs/notes-on-frontend-design.md)** — Frontend subsystem architecture: Frontend ABC contract, tree-sitter parser layer, BaseFrontend dispatch table engine, all 15 language-specific frontends, LLM frontend with prompt engineering, chunked LLM frontend with register renumbering, factory routing, and lowering patterns reference
- **[Per-Language Frontend Design](docs/frontend-design/)** — Exhaustive per-language documentation of all 15 deterministic frontends and the COBOL frontend: dispatch tables, overridden constants, language-specific lowering methods, canonical literal handling, and worked examples for each language
- **[COBOL Frontend Design](docs/frontend-design/cobol.md)** — ProLeap bridge architecture, PIC-driven encoding, 20-statement coverage matrix, PERFORM continuation semantics, SEARCH/STRING/INSPECT lowering patterns
- **[Dataflow Design Document](docs/notes-on-dataflow-design.md)** — Dataflow analysis architecture: reaching definitions via GEN/KILL worklist fixpoint, def-use chain extraction, variable dependency graph construction with transitive closure, integration with IR/CFG, worked examples, and complexity analysis
- **[Architectural Decision Records](docs/architectural-design-decisions.md)** — Chronological log of key architectural decisions: IR design, deterministic VM, best-effort execution, closure semantics, LLM frontend strategy, dataflow analysis, modular package structure, and more

## Limitations

This is an experimental project. Key limitations to be aware of:

- **No standard library implementations.** Language standard libraries are not implemented. The VM provides a small set of builtins (string operations, basic I/O, arithmetic) but calls to standard library functions (e.g., `Collections.sort()` in Java, `itertools` in Python) will produce symbolic values or fall back to the LLM oracle.
- **Language feature coverage is evolving.** Frontend support for each language is tested through [Exercism](#exercism-integration-suite) and [Rosetta](#rosetta-cross-language-suite) cross-language suites, but not every language construct is covered. Edge cases in complex features (e.g., advanced pattern matching, generator expressions, async/await) may lower incorrectly or produce `SYMBOLIC` nodes.
- **LLM frontends are non-deterministic.** The LLM and chunked-LLM frontends produce valid IR in most cases, but outputs can vary between runs and may occasionally generate structurally incorrect IR despite schema constraints and retries.
- **No concurrency or I/O modelling.** The VM is single-threaded and does not model file I/O, network calls, or concurrency primitives. Programs relying on these will hit symbolic boundaries.
- **COBOL frontend requires external tooling.** The ProLeap bridge needs JDK 17+ and a separately-built JAR. It is not included in the default Poetry install.

## See Also

- **[Codescry](https://github.com/avishek-sen-gupta/codescry)** — Repo surveying, integration detection, symbol resolution, and embedding-based signal classification
- **[Rev-Eng TUI](https://github.com/avishek-sen-gupta/reddragon-codescry-tui)** — Terminal UI that integrates Red Dragon and Codescry for interactive top-down reverse engineering of codebases
