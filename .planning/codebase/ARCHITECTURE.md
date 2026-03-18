# Architecture

**Analysis Date:** 2026-03-18

## Pattern Overview

**Overall:** Multi-stage symbolic interpreter with language-agnostic IR intermediate representation. The architecture implements a traditional compiler pipeline (Frontend → IR → CFG → VM Execution) with support for 15+ language frontends and fallback to LLM-guided execution.

**Key Characteristics:**
- **Language-agnostic IR**: All language-specific logic compiled to unified Three-Address Code (TAC) IR with 50+ opcodes
- **Deterministic + Symbolic**: Local opcode handlers for deterministic execution; LLM fallback for unresolved symbolic operations
- **Trait-based coercion**: Type conversion strategies (BinopCoercionStrategy, UnopCoercionStrategy, FieldFallbackStrategy) selected per-language
- **Registry-driven function resolution**: Pre-scan IR/CFG to build function/class metadata, enabling call dispatch and inheritance chains

## Layers

**Language Frontends:**
- Purpose: Parse language-specific AST (via tree-sitter) and lower to IR instructions
- Location: `interpreter/frontends/` with 15 language modules (python, java, c, cpp, rust, go, javascript, typescript, kotlin, scala, php, ruby, c#, lua, pascal)
- Contains: Language-specific parsers, node type mappings, expression/statement/declaration lowerers
- Depends on: tree-sitter parser, `interpreter/parser.py`, common lowering utilities
- Used by: `Frontend.lower()` API consumed by `interpreter/run.py`
- Pattern: Each frontend inherits `BaseFrontend` and overrides `_build_expr_dispatch()`, `_build_stmt_dispatch()`, `_build_constants()` to compose language-specific lowering functions
- Example: `interpreter/frontends/python/frontend.py` composes PythonFrontend from dispatch tables returning pure lowering functions

**IR Generation (Three-Address Code):**
- Purpose: Flatten language constructs into flattened instructions with explicit register allocation and control flow
- Location: `interpreter/ir.py` (opcode definitions), `interpreter/frontends/` (lowering logic)
- Contains: 50+ opcodes (CONST, LOAD_VAR, CALL_FUNCTION, BRANCH_IF, STORE_FIELD, NEW_OBJECT, etc.), source location tracking
- Pattern: Frontends emit instructions via `BaseFrontend._emit()`, accumulating to `_instructions` list
- Key opcodes:
  - **Value producers**: CONST, LOAD_VAR, LOAD_FIELD, LOAD_INDEX, NEW_OBJECT, BINOP, CALL_FUNCTION
  - **Value consumers**: STORE_VAR, STORE_FIELD, STORE_INDEX, DECL_VAR
  - **Control flow**: BRANCH, BRANCH_IF, RETURN, THROW, LABEL
  - **Special**: SYMBOLIC (for type hints), ALLOC_REGION/WRITE_REGION/LOAD_REGION (byte-addressed memory), ADDRESS_OF/LOAD_INDIRECT/STORE_INDIRECT (pointer ops)
- Output: `list[IRInstruction]` consumed by CFG builder and type inference

**Control Flow Graph (CFG):**
- Purpose: Partition flat IR into basic blocks and wire control edges (predecessor/successor relationships)
- Location: `interpreter/cfg.py`, `interpreter/cfg_types.py`
- Contains: `BasicBlock` (list of instructions with label), edges (adjacency dict), entry point
- Pattern: Built in 3 phases (identify block starts, create blocks, wire edges from branch targets)
- Used by: VM executor for label-based instruction pointer navigation, type inference, mermaid visualization

**Type Inference & Environment:**
- Purpose: Static type inference pass over IR instructions, building register-to-type and variable-to-type mappings
- Location: `interpreter/type_inference.py`, `interpreter/type_environment.py`, `interpreter/type_expr.py`
- Contains: TypeEnvironment (frozen maps of register_types, var_types), TypeExpr ADT (ScalarType, ParameterizedType, FunctionType), inference rules
- Pattern: Walk IR, accumulate type information from CONST, CALL_FUNCTION, NEW_OBJECT, STORE_VAR instructions
- Key abstractions: `TypeExpr` end-to-end pipeline (no string parsing after seeding from frontend)
- Used by: VM executor for register coercion, overload resolution, type compatibility checks

**Symbol Tables:**
- Purpose: Map function/class labels to metadata (FuncRef, ClassRef) for dispatch, inheritance resolution
- Location: `interpreter/registry.py`, `interpreter/func_ref.py`, `interpreter/class_ref.py`
- Contains: FunctionRegistry (func_params, class_methods, class_parents), FuncRef (label, signature, kind), ClassRef (name, label, parents)
- Pattern: Frontends populate `func_symbol_table` and `class_symbol_table` during lowering; registry scans IR/CFG to extract parameter names
- Used by: VM executor for CALL_FUNCTION/CALL_METHOD dispatch, constructor matching

**VM Executor (Imperative Shell):**
- Purpose: Step-by-step execution with state mutations (heap, call stack, registers, variables)
- Location: `interpreter/executor.py` (opcode handlers), `interpreter/vm.py` (state definition, update application)
- Contains: 50+ opcode handlers, each returning `ExecutionResult` (StateUpdate + used_llm flag)
- Pattern: `execute_cfg()` runs step loop: fetch instruction → dispatch to handler → apply update → move IP
- State: `VMState` (registers dict, variables dict, heap dict, call_stack, return values)
- Handlers use dependency injection for strategies (FieldFallbackStrategy, BinopCoercionStrategy, TypeConversionRules)
- Key handlers:
  - `_handle_const`: Produce constant values, resolve function/class references from symbol tables
  - `_handle_call_function`: Dispatch by arity/type, fall back to LLM for unresolved calls
  - `_handle_new_object`: Allocate heap object, dereference variables for anonymous class aliases
  - `_handle_store_field`/`_handle_store_index`: Mutate heap or native Python lists
  - Control flow: BRANCH/BRANCH_IF update next_label (handled by step loop)
- Local-only handlers execute deterministically; uncertain operations (CALL_UNKNOWN) defer to LLM

**Type Coercion Strategies:**
- Purpose: Language-specific type conversion rules for operations
- Location: `interpreter/binop_coercion.py`, `interpreter/unop_coercion.py`, `interpreter/field_fallback.py`
- Pattern: Strategy objects injected into executor; implement `coerce_*` methods returning transformed values
- Examples:
  - `JavaBinopCoercion`: int + int → int (not float); string + int → string concatenation
  - `ImplicitThisFieldFallback`: In C#/Java methods, bare field names resolve to this.field
  - `DefaultUnopCoercion`: -"hello" fails (type mismatch), !"true" → false

**LLM Fallback (Symbolic Execution):**
- Purpose: Fallback for operations that cannot be resolved locally (unresolved function calls, symbolic values)
- Location: `interpreter/unresolved_call.py`, `interpreter/llm_client.py`
- Contains: UnresolvedCallResolver interface, LLMPlausibleResolver (uses Claude/OpenAI), SymbolicResolver (returns SymbolicValue objects)
- Pattern: When CALL_UNKNOWN encountered or local handler returns None, create plausible call result via LLM
- Used by: `_handle_call_unknown()` in executor, type inference for uncertain binops

## Data Flow

**Parse → Lowering → Type Inference → Execution:**

1. **Input**: Source code (string)
2. **Parse**: `Frontend.lower(source.encode())` → tree-sitter AST via `interpreter/parser.py`
3. **Lower**: Depth-first walk of AST, emitting IR instructions. Accumulates type seeds and symbol tables.
   - Expression lowering: `lower_binop()`, `lower_call()`, etc. → register-tagged instructions
   - Statement lowering: `lower_assignment()`, `lower_if()`, `lower_while()` → BRANCH/LABEL pairs
   - Declarations: `lower_function_def()` → LABEL-wrapped function body, CONST reference
4. **Type Inference**: Walk IR, merge type information from CONST operands, CALL results, NEW_OBJECT constructors
   - Type environment builder seeds initialized from frontend (Java's int → Int, Python's List → Array)
   - Infers types for registers and variables by scanning instruction operands and results
5. **CFG Build**: Partition instructions by LABEL and branch targets; wire control edges
6. **Registry**: Scan IR/CFG for CONST (function labels) and CLASS_LABEL opcodes; extract func params
7. **Execution**: Step loop from entry point:
   - Fetch instruction at current (label, ip)
   - Dispatch to handler via opcode
   - Handler applies local logic or defers to LLM
   - Apply StateUpdate to VM (registers, variables, heap)
   - Update instruction pointer (linear or branching)

**State Management:**

- **Register state**: `VMState.registers` dict (string → TypedValue), frame-local in `StackFrame.registers`
- **Variable state**: `VMState.variables` dict (string → TypedValue), scope-chained via `StackFrame.enclosing_scope`
- **Heap state**: `VMState.heap` dict (addr → HeapObject with fields dict), persistent across calls
- **Call stack**: `VMState.call_stack` list of StackFrame, each tracking function_name, return_label, return_ip
- **DECL_VAR vs STORE_VAR**: DECL_VAR creates in current frame; STORE_VAR walks enclosing scopes to find existing binding (closure support)

## Key Abstractions

**IRInstruction (Three-Address Code):**
- Purpose: Flattened representation of all language constructs
- Example: `%0 = call_function max [%1, %2]` (binary call), `branch_if %0 then_label else_label` (conditional)
- Pattern: Each instruction is independent; no nested expressions (flattened to register assignments)
- Enables: Easy CFG construction, register allocation, symbolic value tracking

**TypeExpr (Type System ADT):**
- Purpose: Structured type representation (no string serialization)
- Hierarchy: UnknownType, ScalarType (name), ParameterizedType (base, args), FunctionType (params, return), UnionType
- Pattern: Created via `scalar(name)`, `array_of(elem_type)`, `fn_type(params, ret)` constructors; used end-to-end
- Key property: Falsy (is_falsy() method) so `if type_expr:` checks still work with UNKNOWN

**VMState & StateUpdate:**
- Purpose: Immutable snapshots of execution state for trace recording and update application
- StateUpdate: Declared as `register_writes` dict, `var_writes` dict, `heap_writes` list, `new_objects` list, control flow flags (next_label, path_condition)
- Pattern: Handlers return StateUpdate without mutating VM; `apply_update()` applies writes
- Enables: Deterministic replay, LLM-guided exploration, execution traces

**StackFrame:**
- Purpose: Call frame with local register/variable state
- Contains: function_name, return_label, return_ip, result_reg, registers dict, enclosing_scope (for STORE_VAR chain walk)
- Pattern: Push on CALL_FUNCTION, pop on RETURN; enclosing_scope enables closure variable access
- Key decision: return_label and return_ip stored on frame after call dispatch (passed through data, not re-derived downstream)

**Symbol Tables (FuncRef, ClassRef):**
- Purpose: Structured references to enable dispatch without string parsing
- FuncRef: label (e.g., "func_add_0"), name, signature (params + return type), kind (BUILTIN, USER, CONSTRUCTOR)
- ClassRef: name, label, parents (linearized MRO)
- Pattern: Frontends populate during lowering; registry validates against IR; executor dereferences via CONST lookup
- Replaces: Old FUNC_REF_PATTERN (regex-based) and CLASS_REF_PATTERN strings

## Entry Points

**CLI (`interpreter.py`):**
- Location: `/Users/asgupta/code/red-dragon/interpreter.py`
- Triggers: `python interpreter.py <file> --language python --ir-only` etc.
- Responsibilities: Parse CLI args, dispatch to api.py functions (dump_ir, dump_cfg, run)
- Options: `--language`, `--entry`, `--ir-only`, `--cfg-only`, `--mermaid`, `--verbose`, `--frontend` (deterministic/llm/chunked_llm), `--backend` (claude/openai)

**API (`interpreter/api.py`):**
- Location: `interpreter/api.py`
- Functions:
  - `lower_source()`: Frontend → IR instructions
  - `lower_and_infer()`: Frontend → IR + TypeEnvironment
  - `build_cfg_from_source()`: Frontend → IR → CFG
  - `execute_traced()`: Frontend → IR → CFG → Registry → execute_cfg_traced() → ExecutionTrace
  - `dump_ir()`, `dump_cfg()`, `dump_mermaid()`: Convenience text formatters
- Pattern: Composable functions, each corresponding to a workflow (no monolithic runner)

**Programmatic (`interpreter/run.py`):**
- Location: `interpreter/run.py`
- Main function: `run(source, language, entry_point, backend, max_steps, verbose, frontend_type)`
- Returns: `VMState` (final state after execution)
- Used by: CLI, tests, external tools
- Responsibilities: Orchestrate frontend → CFG → registry → execute_cfg, handling type inference and strategy selection
- Helper: `execute_cfg()` executes a pre-built CFG with all strategies injected
- Helper: `execute_cfg_traced()` records execution trace for TUI replay

**Tests:**
- Unit tests: `tests/unit/` - test isolated components (builtins, type inference, frontends)
- Integration tests: `tests/integration/` - test full pipelines via `run()` or `lower_and_infer()`
- Rosetta/Exercism: `tests/unit/rosetta/`, `tests/unit/exercism/` - multi-language program validation

## Error Handling

**Strategy:** Deterministic error propagation where possible; LLM fallback for unresolved cases

**Patterns:**

- **Frontend errors**: Parser exceptions bubble up (tree-sitter parse failures); repair_client can fix malformed AST before lowering
- **Type errors**: Type inference warnings logged; handlers use conservative coercion rules (e.g., DefaultBinopCoercion returns None for int + string)
- **Call resolution**: Unresolved function calls (no matching signature) trigger CALL_UNKNOWN → LLM fallback
- **Symbolic values**: Operations on SymbolicValue objects deferred to LLM (e.g., "foo" + symbolic_x)
- **Heap access**: Missing field on HeapObject returns None (not error) — lets symbolic execution continue
- **Stack underflow**: Top-level RETURN/THROW stops execution (natural halt, not error)

## Cross-Cutting Concerns

**Logging:**
- `interpreter.py`, `interpreter/parser.py`, `interpreter/frontend.py`, `interpreter/run.py` use logger for pipeline phases
- `executor.py` logs opcode dispatch if verbose
- Configured via Python logging module; see `CLAUDE.md` for pytest caplog usage

**Validation:**
- Type inference validates CFG block references in instruction jumps
- Registry validates func_symbol_table and class_symbol_table entries against IR
- No explicit validation errors; issues logged and execution continues

**Authentication:**
- LLM backends configured via env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
- `interpreter/backend.py` factory selects client by provider name
- `interpreter/llm_client.py` wraps API calls with retry/timeout logic

---

*Architecture analysis: 2026-03-18*
