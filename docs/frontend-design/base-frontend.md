# Base Frontend

> `interpreter/frontends/_base.py` + `interpreter/frontends/context.py` + `interpreter/frontends/common/`

## Overview

The base frontend infrastructure consists of three layers:

1. **`BaseFrontend`** (`_base.py`) -- abstract base class that all 15 deterministic frontends inherit from. Provides four `_build_*()` hook methods that subclasses override to return pure data (dispatch tables, grammar constants). Implements `lower()` which assembles a `TreeSitterEmitContext` and kicks off recursive descent.

2. **`TreeSitterEmitContext`** (`context.py`) -- mutable dataclass holding all lowering state (registers, labels, instructions, scopes, type info). All lowering functions receive `ctx` as their first argument. Provides recursive descent entry points (`lower_block`, `lower_stmt`, `lower_expr`) and code generation primitives.

3. **Common lowerers** (`common/`) -- shared pure-function lowerers used by multiple language frontends. Each function takes `(ctx: TreeSitterEmitContext, node)` and emits IR instructions via the context.

---

## Class Structure

### Inheritance

```
Frontend (ABC)                     # interpreter/frontend.py
  |
  +-- BaseFrontend                 # interpreter/frontends/_base.py
        |
        +-- PythonFrontend         # interpreter/frontends/python/frontend.py
        +-- JavaFrontend           # interpreter/frontends/java/frontend.py
        +-- ...                    # (15 language frontends total)
```

`Frontend` defines a single abstract method:

```python
class Frontend(ABC):
    @abstractmethod
    def lower(self, source: bytes) -> list[IRInstruction]: ...
```

### Constructor

```python
def __init__(self, parser_factory: ParserFactory, language: Language,
             observer: FrontendObserver = NullFrontendObserver()):
```

| Parameter | Type | Purpose |
|---|---|---|
| `parser_factory` | `ParserFactory` | Injected factory for creating tree-sitter parsers |
| `language` | `Language` | Language enum value (e.g., `Language.JAVA`) |
| `observer` | `FrontendObserver` | Observer for frontend events (default: no-op) |

### Subclass Hook Methods

```python
class BaseFrontend(Frontend):
    BLOCK_SCOPED: bool = False     # True for block-scoped languages

    def _build_constants(self) -> GrammarConstants: ...
    def _build_stmt_dispatch(self) -> dict[str, Callable]: ...
    def _build_expr_dispatch(self) -> dict[str, Callable]: ...
    def _build_type_map(self) -> dict[str, str]: ...
```

These return pure data -- a `GrammarConstants` dataclass, two dispatch dicts mapping tree-sitter node types to pure functions `(ctx, node) → str|None`, and a type normalization map.

---

## GrammarConstants

`GrammarConstants` (`context.py`) is a frozen dataclass that centralizes all language-specific grammar field names, node type sets, and literal values. Each frontend returns a customized instance from `_build_constants()`.

### Function Definition Fields

| Field | Default | Purpose |
|---|---|---|
| `func_name_field` | `"name"` | `child_by_field_name()` for function name |
| `func_params_field` | `"parameters"` | `child_by_field_name()` for parameter list |
| `func_body_field` | `"body"` | `child_by_field_name()` for function body |

### If Statement Fields

| Field | Default | Purpose |
|---|---|---|
| `if_condition_field` | `"condition"` | Condition expression |
| `if_consequence_field` | `"consequence"` | True branch body |
| `if_alternative_field` | `"alternative"` | False/elif branch |

### While/For Loop Fields

| Field | Default | Purpose |
|---|---|---|
| `while_condition_field` | `"condition"` | While condition |
| `while_body_field` | `"body"` | While body |
| `for_initializer_field` | `"initializer"` | For-loop init (Java overrides to `"init"`) |
| `for_condition_field` | `"condition"` | For condition |
| `for_body_field` | `"body"` | For body |
| `for_update_field` | `"update"` | For update expression |

### Call Expression Fields

| Field | Default | Purpose |
|---|---|---|
| `call_function_field` | `"function"` | Function/callee node |
| `call_arguments_field` | `"arguments"` | Argument list node |

### Class/Assignment/Attribute/Subscript Fields

| Field | Default | Purpose |
|---|---|---|
| `class_name_field` | `"name"` | Class name |
| `class_body_field` | `"body"` | Class body |
| `assign_left_field` | `"left"` | Assignment LHS |
| `assign_right_field` | `"right"` | Assignment RHS |
| `attr_object_field` | `"object"` | Attribute object |
| `attr_attribute_field` | `"attribute"` | Attribute name |
| `subscript_value_field` | `"value"` | Subscript object |
| `subscript_index_field` | `"index"` | Subscript index |

### Node Type Sets

| Field | Default | Purpose |
|---|---|---|
| `block_node_types` | `frozenset()` | Types iterated by `lower_block()` |
| `comment_types` | `frozenset({"comment"})` | Filtered out by `lower_stmt()` |
| `noise_types` | `frozenset({"newline", "\n"})` | Filtered out by `lower_stmt()` |

### Canonical Literals

| Field | Default | Languages that override |
|---|---|---|
| `none_literal` | `"None"` | -- (all canonicalize to this) |
| `true_literal` | `"True"` | -- |
| `false_literal` | `"False"` | -- |
| `default_return_value` | `"None"` | C: `"0"`, Rust/Scala: `"()"` |

### Special Node Types

| Field | Default | Languages that override |
|---|---|---|
| `paren_expr_type` | `"parenthesized_expression"` | -- |
| `attribute_node_type` | `"attribute"` | JS: `"member_expression"`, Java: `"field_access"`, Rust: `"field_expression"`, etc. |

---

## TreeSitterEmitContext

`TreeSitterEmitContext` (`context.py`) holds all mutable lowering state:

| Category | Fields |
|---|---|
| **Configuration** | `source`, `language`, `constants`, `type_map`, `stmt_dispatch`, `expr_dispatch`, `block_scoped` |
| **Counters** | `reg_counter`, `label_counter` |
| **Output** | `instructions: list[IRInstruction]` |
| **Loop tracking** | `loop_stack`, `break_target_stack` |
| **Type info** | `type_env_builder`, `_current_func_label`, `_current_class_name` |
| **Block scopes** | `_block_scope_stack`, `_scope_counter`, `_var_scope_metadata`, `_base_declared_vars` |

### Code Generation Primitives

| Method | Signature | Purpose |
|---|---|---|
| `fresh_reg()` | `→ str` | Generate `%0`, `%1`, ... (SSA-style, each call unique) |
| `fresh_label(prefix)` | `→ str` | Generate `if_true_0`, `while_cond_1`, ... |
| `emit(opcode, ...)` | `→ IRInstruction` | Emit instruction, auto-derive source location from AST node |
| `node_text(node)` | `→ str` | Extract source text from tree-sitter node |
| `source_loc(node)` | `→ SourceLocation` | Extract AST span (0-based rows → 1-based lines) |

### Recursive Descent Entry Points

| Method | Behaviour |
|---|---|
| `lower_block(node)` | If node type is in `stmt_dispatch` and not in `block_node_types`, dispatch directly. Otherwise iterate named children, calling `lower_stmt()` on each. Auto-enters/exits block scopes if `block_scoped=True` and node type is in `block_node_types`. |
| `lower_stmt(node)` | Filter comments/noise. Check `stmt_dispatch` first; if found, call handler. Else check `block_node_types` for redirect to `lower_block()`. Else fallback to `lower_expr()`. |
| `lower_expr(node) → str` | Check `expr_dispatch`; if found, call handler and return register. Else emit `SYMBOLIC "unsupported:type"` and return register. |

The **fallback to SYMBOLIC** is a critical design decision: unknown constructs produce a descriptive placeholder rather than crashing, enabling graceful degradation.

### Block Scope Management

| Method | Purpose |
|---|---|
| `enter_block_scope()` | Push a new scope onto `_block_scope_stack` |
| `exit_block_scope()` | Pop the current scope |
| `declare_block_var(name)` | Register a variable in the current scope; returns mangled name (`x$1`) if shadowing |
| `resolve_var(name)` | Walk the scope stack to find the correct (possibly mangled) variable name |

Block scoping produces `VarScopeInfo(original_name, scope_depth)` metadata for each mangled variable, propagated through `TypeEnvironmentBuilder` to the final `TypeEnvironment.var_scope_metadata`. See the [Type System Design Document](../type-system.md#block-scope-tracking-llvm-style).

### Loop Stack Management

| Method | Purpose |
|---|---|
| `push_loop(continue_label, end_label)` | Push onto both `loop_stack` and `break_target_stack` |
| `pop_loop()` | Pop from both stacks |

Two parallel stacks exist because `break` can target non-loop constructs (switch statements push onto `break_target_stack` but not `loop_stack`), while `continue` only targets loops.

### Type Seeding Methods

| Method | Seeds |
|---|---|
| `seed_register_type(reg, type_name)` | Register type (e.g., `"%3" → Int`) |
| `seed_var_type(var_name, type_name)` | Variable type (e.g., `"x" → Int`) |
| `seed_param_type(param_name, type_hint)` | Parameter type for current function |
| `seed_func_return_type(func_label, return_type)` | Function return type |
| `seed_type_alias(alias_name, target_type)` | Type alias (e.g., `UserId → Int`) |
| `seed_interface_impl(class_name, interface_name)` | Interface implementation |

Each method calls `parse_type()` at the boundary to convert raw strings to `TypeExpr`. See the [Type System Design Document](../type-system.md#phase-1-frontend-type-extraction).

---

## Common Lowerers (`interpreter/frontends/common/`)

Shared pure-function lowerers used by multiple language frontends. Each function takes `(ctx: TreeSitterEmitContext, node)`.

### `common/expressions.py` (~434 lines)

| Function | Opcode(s) | Description |
|---|---|---|
| `lower_const_literal` | `CONST` | Number, string literals (raw text) |
| `lower_canonical_none` | `CONST "None"` | Null/nil/undefined → canonical `"None"` |
| `lower_canonical_true` | `CONST "True"` | Boolean true → canonical `"True"` |
| `lower_canonical_false` | `CONST "False"` | Boolean false → canonical `"False"` |
| `lower_canonical_bool` | `CONST "True"` or `"False"` | Combined handler for languages with single `boolean` node type |
| `lower_identifier` | `LOAD_VAR` | Variable references (uses `ctx.resolve_var()` for block scoping) |
| `lower_paren` | (delegates) | Unwrap parenthesised expression |
| `lower_binop` | `BINOP` | Binary operators |
| `lower_comparison` | `BINOP` | Comparisons as binary ops |
| `lower_unop` | `UNOP` | Unary operators |
| `lower_update_expr` | `BINOP` + store | `i++`, `i--` → load, binop +/- 1, store |
| `lower_call` | `CALL_FUNCTION` / `CALL_METHOD` / `CALL_UNKNOWN` | Three-way call dispatch |
| `lower_attribute` | `LOAD_FIELD` | `obj.field` access |
| `lower_subscript` | `LOAD_INDEX` | `arr[i]` access |
| `lower_list_literal` | `NEW_ARRAY` + `STORE_INDEX` | List/array construction |
| `lower_dict_literal` | `NEW_OBJECT` + `STORE_INDEX` | Dictionary construction |
| `lower_store_target` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` | Assignment target dispatch |

**Call lowering -- three-way split:** `lower_call()` distinguishes three call patterns by inspecting the function node's AST type:
- **Method call** (attribute/member_expression/selector_expression/field_access) → `CALL_METHOD`
- **Plain function call** (identifier) → `CALL_FUNCTION`
- **Dynamic/unknown call** (anything else) → `CALL_UNKNOWN`

### `common/assignments.py` (~71 lines)

| Function | Pattern | Description |
|---|---|---|
| `lower_assignment` | `STORE_VAR` / `STORE_FIELD` / `STORE_INDEX` | Simple assignment |
| `lower_augmented_assignment` | `BINOP` + store | `x += 1` → load, binop, store |
| `lower_return` | `RETURN` | Return with optional value |
| `lower_expression_statement` | (delegates) | Unwrap expression statement |

### `common/control_flow.py` (~198 lines)

| Function | Pattern | Description |
|---|---|---|
| `lower_if` | `BRANCH_IF` + labels | If/elif/else chains |
| `lower_while` | Labels + `BRANCH_IF` loop | While loops |
| `lower_c_style_for` | Init + condition + body + update | C-style for loops; wraps in block scope when `block_scoped=True` so init vars (e.g. `for(int i=0;...)`) are scoped to the loop |
| `lower_break` | `BRANCH` | Break via `break_target_stack` |
| `lower_continue` | `BRANCH` | Continue via `loop_stack` |

### `common/declarations.py` (~177 lines)

| Function | Description |
|---|---|
| `lower_function_def` | Function definitions with type extraction and parameter seeding |
| `lower_params` / `lower_param` | Parameter lowering with type seeding |
| `lower_class_def` | Class definitions with interface extraction |

### `common/exceptions.py` (~114 lines)

| Function | Description |
|---|---|
| `lower_raise_or_throw` | Raise/throw statements |
| `lower_try_catch` | Try/catch/finally with block-scoped catch variables |

### `common/node_types.py` (~46 lines)

`CommonNodeType` class with universal constants shared across grammars (parentheses, commas, semicolons, etc.).

---

## Entry Point: `BaseFrontend.lower()`

```python
def lower(self, source: bytes) -> list[IRInstruction]:
    tree = self._parser_factory.get_parser(self._language).parse(source)
    constants = self._build_constants()
    return self._lower_with_context(tree.root_node, source, constants)

def _lower_with_context(self, root, source, constants):
    ctx = TreeSitterEmitContext(
        source=source,
        constants=constants,
        stmt_dispatch=self._build_stmt_dispatch(),
        expr_dispatch=self._build_expr_dispatch(),
        type_map=self._build_type_map(),
        block_scoped=self.BLOCK_SCOPED,
        ...
    )
    ctx.emit(Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
    ctx.lower_block(root)
    self._type_env_builder.var_scope_metadata = dict(ctx.var_scope_metadata)
    return ctx.instructions
```

All mutable state lives in the `TreeSitterEmitContext` instance, which is created fresh for each `lower()` call.

---

## Design Notes

### Context Mode vs. Legacy

The codebase previously used instance methods (`self._lower_*`) and class-level constant overrides. The current architecture uses pure functions `(ctx, node)` and a frozen `GrammarConstants` dataclass. `BaseFrontend._base.py` still contains legacy lowering methods that serve as the implementation behind the common lowerers -- the common modules delegate to these methods through the context.

### Dispatch Table Pattern

The dispatch table pattern was chosen over visitor pattern or if/elif chains because:
- **Extensibility**: adding a new node type is a single dict entry
- **Transparency**: the full mapping is visible in one place in each `_build_*_dispatch()` method
- **Reusability**: common lowerer functions can be referenced by any frontend without adapter code

### Graceful Degradation via SYMBOLIC

Unknown node types produce `SYMBOLIC "unsupported:<type>"` rather than raising exceptions. This means:
- Partial lowering always succeeds
- The VM can still execute the known portions of the program
- Unsupported constructs are visible in the IR for debugging

### Canonical Literals

All null/boolean literals are canonicalized to Python-form (`"None"`, `"True"`, `"False"`) in the IR so downstream analysis (VM, dataflow, CFG) does not need language-specific logic for basic constant values. The canonicalization happens at the frontier -- in the frontend dispatch tables -- so it is zero-cost at analysis time.

### Separation of Expression and Statement Dispatch

Two separate dispatch tables exist because:
- Expression handlers **return a register** (the value they computed)
- Statement handlers **return nothing** (they emit instructions as side effects)
- Some node types are valid as both (e.g., assignment), and having separate tables allows explicit control over which path is taken

### Implicit Return

Every function definition ends with an implicit `CONST default_return_value` + `RETURN` pair. This ensures the CFG has a single exit path even for functions that fall through without an explicit return. The value used (`"None"`, `"0"`, or `"()"`) is language-appropriate via the `GrammarConstants.default_return_value` field.
