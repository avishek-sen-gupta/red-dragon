# Coding Conventions

**Analysis Date:** 2026-03-18

## Naming Patterns

**Files:**
- `snake_case` for all module files: `type_expr.py`, `vm_types.py`, `executor.py`
- Test files: `test_<feature>.py` pattern: `test_class_instantiation.py`, `test_builtins.py`
- Frontend subdirectory per language: `interpreter/frontends/<language>/` (e.g., `interpreter/frontends/java/`, `interpreter/frontends/pascal/`)
- Constant files: `<language>_constants.py` for language-specific constants

**Functions:**
- `snake_case` for all function names, including public and private
- Private functions/methods prefixed with single underscore: `_helper_func()`, `_coerce_value()`
- Built-in functions prefixed with `_builtin_`: `_builtin_len()`, `_builtin_print()`, `_builtin_slice()`
- Helper functions in test files prefixed with underscore: `_run_program()`, `_apply_builtin_result()`

**Variables:**
- `snake_case` for all variable names
- Short names allowed per `.pylintrc` for compiler idioms: `i`, `j`, `k` (indices), `v` (value), `e` (element), `f` (field), `n` (count), `x` (generic), `r` (register), `op` (opcode), `ir` (instructions), `fn` (function), `vm` (virtual machine), `bb` (basic block), `pc` (program counter), `lhs`/`rhs` (left/right operand), `cfg` (control flow graph), `src`/`dst` (source/destination)
- Register names in IR: `%0`, `%1`, `%result`, `%arr` (register-like identifiers)

**Types/Classes:**
- `PascalCase` for all class names: `VMState`, `TypeExpr`, `HeapObject`, `StackFrame`, `FunctionSignature`
- Dataclass naming follows class pattern: `@dataclass class TypeEnvironment`
- Exception classes: `PascalCase` with `Error` or `Exception` suffix: `AmbiguousOverloadError`, `IRParsingError`
- Abstract base classes or protocols: `PascalCase` (e.g., `Frontend`, `UnresolvedCallResolver`, `FieldFallbackStrategy`)

**Constants:**
- `UPPER_SNAKE_CASE` for module-level constants: `_EMPTY_TYPE_ENV`, `_IDENTITY_RULES`, `_DEFAULT_RESOLVER`
- Sentinel objects: `UNKNOWN`, `UNBOUND`, `VOID_RETURN`
- Language frozensets: `_IMPLICIT_THIS_LANGS`, `_JAVA_LIKE`

## Code Style

**Formatting:**
- Black formatting enforced: run `poetry run python -m black .` before committing
- Max line length: 120 characters per `.pylintrc`
- Fully qualified imports: `from interpreter.vm import VMState` (never relative)

**Linting:**
- Pylint configured via `.pylintrc` with exceptions for compiler patterns
- Disabled rules: too-few-public-methods, no-self-use, missing-docstrings, too-many-arguments, too-many-branches, too-many-statements, too-many-return-statements, duplicate-code, broad-except, unnecessary-lambda

**Docstrings:**
- Module-level docstrings required for all `.py` files
- Format: triple-quoted `"""Summary. Detailed info."""`
- Class docstrings for major types: `VMState`, `TypeExpr`, `StackFrame`
- Function docstrings for public APIs and complex logic (not strictly enforced)
- ReStructuredText inline code: ``` ``code`` ```
- Type hints in docstrings: `"*val* to the type declared for *reg*"`

## Import Organization

**Order:**
1. `from __future__ import annotations`
2. Standard library: `from types import MappingProxyType`, `import logging`
3. Third-party: `from pydantic import BaseModel`, `from dataclasses import dataclass`
4. Internal `interpreter` module: `from interpreter.vm import VMState`
5. Lazy imports inside functions (for optional deps)

**Path Aliases:**
- All imports fully qualified: `from interpreter.vm import VMState`
- No relative imports anywhere

**Re-exports:**
- Comment with `# noqa: F401 — re-exported for backwards compatibility`
- Example: `from interpreter.vm_types import StateUpdate  # noqa: F401`

## Error Handling

**Patterns:**
- Custom exception types: `AmbiguousOverloadError`, `IRParsingError`
- Broad exceptions caught only at orchestration layers (executor, run.py)
- No defensive programming: avoid `if x is not None` checks in normal paths
- Validation via type level (TypeExpr, TypeEnvironment) or explicit `isinstance()` checks
- Error information in return values: `BuiltinResult`, `ExecutionResult`
- Guard patterns for null object pattern: check empty/unknown types, not None

**ValueError/TypeError:**
- Caught in builtin functions: `_builtin_int()`, `_builtin_float()` on conversion failure
- Allowed in try-except blocks for fallible operations (list conversion, arithmetic)

## Logging

**Framework:** Python's built-in `logging` module

**Setup:**
- Each module: `logger = logging.getLogger(__name__)` at module level
- Not in functions or classes

**Patterns:**
- `logger.debug()` for low-level details: register loads, symbolic values
- `logger.info()` for high-level progress: VM steps, execution complete, LLM calls
- `logger.warning()` for recoverable issues: mismatches, missing signatures
- Format: `"[description] %s", variable` with string interpolation
- Include context: register names, object descriptions, function names

**Examples:**
- `logger.debug("address_of: promoted %s=%r to heap %s", name, current_val, mem_addr)`
- `logger.info("[VM print] %s", " ".join(str(a.value) for a in args))`
- `logger.warning("sig/label count mismatch for %s.__init__", class_name)`

## Comments

**When to Comment:**
- Explain *why*, not *what* — code shows what, comments show intent
- Algorithm complexity or non-obvious trade-offs before the block
- Cross-language differences: e.g., "Lua uses 1-based indexing"
- Design decisions: e.g., "Reuse existing variable store instead of new dict"

**JSDoc/TSDoc:**
- Not used (Python project)
- Docstrings provide equivalent documentation

**Inline Comments:**
- Sparingly for complex type coercion, lowering logic
- Example: `# Prelude ends at last prelude STORE_VAR after the last prelude label`

## Function Design

**Size:**
- Small, composable functions preferred per CLAUDE.md
- Lowering functions in frontends large due to structural transformation (accepted)
- Executor opcode handlers: medium-sized with early returns for errors

**Parameters:**
- Explicit parameters over configuration objects (except `VMConfig`)
- Dependency injection: pass `vm` (VMState), `type_env`, `conversion_rules` as dependencies
- No mutable argument defaults: use `field(default_factory=list)`
- Avoid optional `None` defaults — use empty structures or sentinels

**Return Values:**
- Structured types: `BuiltinResult`, `StateUpdate`, `ExecutionResult`, `TypedValue`
- Never return bare `None` from non-None return types
- Symbolic/unknown values explicit: `Operators.UNCOMPUTABLE`, `UNKNOWN`
- Multiple returns via dataclass or tuple: `(vm, stats) = execute_cfg(...)`

**Early Return Pattern:**
- Early returns for error/exceptional cases
- Main happy path at end of function
- From `_builtin_len()`:
```python
if not args:
    return BuiltinResult(value=_UNCOMPUTABLE)
val = args[0].value
addr = _heap_addr(val)
if addr and addr in vm.heap:
    fields = vm.heap[addr].fields
    if "length" in fields:
        return BuiltinResult(value=fields["length"].value)
    return BuiltinResult(value=len(fields))
if isinstance(val, (list, tuple, str)):
    return BuiltinResult(value=len(val))
return BuiltinResult(value=_UNCOMPUTABLE)
```

## Module Design

**Exports:**
- Public API functions/classes exported at module level
- Private functions/classes use leading underscore
- Barrel files (`__init__.py`) aggregate related exports

**Barrel Files:**
- Simplify imports: `from interpreter.frontends import get_deterministic_frontend`
- Via explicit imports and `__all__` lists

**File Organization:**
- One primary class per file: `TypeExpr` in `type_expr.py`, `VMState` in `vm_types.py`
- Helper functions/types in same file if tightly coupled
- Domain-split utilities: `type_expr.py`, `typed_value.py`, `type_environment.py`

## Data Structures

**Dataclasses:**
- Immutable data records: `@dataclass(frozen=True)` for immutable types
- `@dataclass` (mutable) for VM state accumulating during execution
- Mutable field defaults: `field(default_factory=...)`
- Immutable example: `@dataclass(frozen=True) class TypeExpr`
- Mutable example: `@dataclass class VMState`

**Pydantic Models:**
- Configuration objects: `VMConfig`, `run_types.py` models
- Validation via Pydantic validators

**TypeExpr ADT:**
- Algebraic data type for type representations
- Classes: `UnknownType`, `ScalarType`, `ParameterizedType` (all inherit `TypeExpr`)
- End-to-end typed IR without string roundtrips

**Sentinel Values:**
- Instead of `None`: `UNKNOWN`, `UNBOUND`, `VOID_RETURN`
- Implement boolean conversion: `if type_expr:` checks if type known

## Design Principles Applied

**Use Existing Infrastructure:**
- TypeExpr reuses variable store for pointer aliasing (not new dict)
- DECL_VAR/STORE_VAR split: DECL_VAR for frame, STORE_VAR walks scope chain
- Field initializers collect in arrays, prepend to constructors

**Prefer Equivalent IR:**
- Rest parameters: `slice(arguments, N)` using existing `slice` builtin
- Method chaining: generated IR with LOAD_ATTR + CALL_FUNCTION

**No Untested Code Paths:**
- All paths exercised by tests
- Xfail for gaps, issues filed (not silently skipped)

**Pass Decisions Through Data:**
- `is_ctor` flag on `StackFrame` (not re-detected from function name)
- `kind` field on `FunctionSignature` (UNBOUND, INSTANCE, STATIC)
- `FuncRef`/`BoundFuncRef` structured references (not regex patterns)

---

*Convention analysis: 2026-03-18*
