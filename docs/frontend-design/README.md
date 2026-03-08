# Frontend Design Documentation

This directory contains exhaustive per-language documentation for the RedDragon frontend subsystem -- the pipeline that lowers language-specific tree-sitter ASTs into a common, language-agnostic IR consumed by the VM, CFG builder, and dataflow analysis.

---

## Architecture Overview

The frontend subsystem converts source code in any of 15 supported languages into a universal flattened three-address code IR ([27 opcodes](../ir-reference.md)). The deterministic frontend strategy uses tree-sitter to parse source into an AST, then performs recursive descent over that AST to emit IR instructions.

The architecture follows a **context-mode** pattern: `BaseFrontend` subclasses return pure data (dispatch tables, grammar constants) via `_build_*()` hooks, and all lowering is performed by pure functions that receive a shared `TreeSitterEmitContext` as their first argument.

```
Frontend (ABC)                          interpreter/frontend.py
  |
  +-- BaseFrontend                      interpreter/frontends/_base.py
  |     |
  |     +-- PythonFrontend              interpreter/frontends/python/frontend.py
  |     +-- JavaScriptFrontend          interpreter/frontends/javascript/frontend.py
  |     +-- TypeScriptFrontend          interpreter/frontends/typescript.py  (extends JS)
  |     +-- JavaFrontend                interpreter/frontends/java/frontend.py
  |     +-- KotlinFrontend              interpreter/frontends/kotlin/frontend.py
  |     +-- ScalaFrontend               interpreter/frontends/scala/frontend.py
  |     +-- CFrontend                   interpreter/frontends/c/frontend.py
  |     +-- CppFrontend                 interpreter/frontends/cpp/frontend.py  (extends C)
  |     +-- CSharpFrontend              interpreter/frontends/csharp/frontend.py
  |     +-- GoFrontend                  interpreter/frontends/go/frontend.py
  |     +-- RustFrontend                interpreter/frontends/rust/frontend.py
  |     +-- RubyFrontend                interpreter/frontends/ruby/frontend.py
  |     +-- LuaFrontend                 interpreter/frontends/lua/frontend.py
  |     +-- PhpFrontend                 interpreter/frontends/php/frontend.py
  |     +-- PascalFrontend              interpreter/frontends/pascal/frontend.py
  |
  +-- TreeSitterEmitContext             interpreter/frontends/context.py
  |     (mutable lowering state: registers, labels, instructions, scopes)
  |
  +-- GrammarConstants                  interpreter/frontends/context.py
  |     (frozen dataclass of per-language field names and literal tokens)
  |
  +-- common/                           interpreter/frontends/common/
        (shared pure-function lowerers: expressions, control_flow, declarations, assignments, exceptions)
```

Each language frontend is a **directory** with a standard module layout:

```
interpreter/frontends/<language>/
├── frontend.py          # BaseFrontend subclass — _build_*() hooks return dispatch tables
├── node_types.py        # Frozen dataclass of tree-sitter node type constants
├── expressions.py       # Pure-function expression lowerers: (ctx, node) → str
├── control_flow.py      # Pure-function control flow lowerers: (ctx, node) → None
├── declarations.py      # Pure-function declaration lowerers: (ctx, node) → None
└── (optional extras)    # e.g. assignments.py (Python, Ruby), pascal_constants.py
```

---

## Document Index

| Document | Source Directory | Description |
|---|---|---|
| [base-frontend.md](base-frontend.md) | `_base.py` + `context.py` + `common/` | BaseFrontend, TreeSitterEmitContext, GrammarConstants, common lowerers |
| [python.md](python.md) | `frontends/python/` | Python frontend -- the reference implementation |
| [javascript.md](javascript.md) | `frontends/javascript/` | JavaScript frontend -- destructuring, arrow functions, template strings |
| [typescript.md](typescript.md) | `frontends/typescript.py` | TypeScript frontend -- extends JavaScript, type extraction |
| [java.md](java.md) | `frontends/java/` | Java frontend -- records, instanceof, method references |
| [kotlin.md](kotlin.md) | `frontends/kotlin/` | Kotlin frontend -- companion objects, elvis operator, when expressions |
| [scala.md](scala.md) | `frontends/scala/` | Scala frontend -- for-comprehensions, case classes, pattern matching |
| [c.md](c.md) | `frontends/c/` | C frontend -- pointers, sizeof, struct/union, goto |
| [cpp.md](cpp.md) | `frontends/cpp/` | C++ frontend -- extends C, adds namespaces, templates, classes |
| [csharp.md](csharp.md) | `frontends/csharp/` | C# frontend -- LINQ, properties, events, using statements |
| [go.md](go.md) | `frontends/go/` | Go frontend -- goroutines, channels, multiple returns, short declarations |
| [ruby.md](ruby.md) | `frontends/ruby/` | Ruby frontend -- symbols, ranges, blocks, heredocs |
| [lua.md](lua.md) | `frontends/lua/` | Lua frontend -- goto/labels, table constructors, `..` concat |
| [php.md](php.md) | `frontends/php/` | PHP frontend -- namespaces, traits, match expressions |
| [pascal.md](pascal.md) | `frontends/pascal/` | Pascal frontend -- begin/end blocks, procedure/function distinction |
| [rust.md](rust.md) | `frontends/rust/` | Rust frontend -- let bindings, match, closures, impl blocks, macros |
| [cobol.md](cobol.md) | `interpreter/cobol/cobol_frontend.py` | COBOL frontend -- ProLeap bridge, byte-addressed regions, PIC encoding |

---

## How Subclasses Customise Behaviour

Each language frontend customises `BaseFrontend` through four `_build_*()` hook methods:

1. **`_build_constants() → GrammarConstants`** -- returns a frozen dataclass specifying tree-sitter field names (e.g., `attr_attribute_field="field"` for Java), node type sets (`block_node_types`, `comment_types`, `noise_types`), and canonical literal tokens (`none_literal="null"`, `true_literal="true"`, `default_return_value="()"`, etc.).

2. **`_build_stmt_dispatch() → dict[str, Callable]`** -- returns a mapping of tree-sitter statement node types to pure-function handlers `(ctx, node) → None`. Handlers come from `common/` modules (e.g., `common_cf.lower_if`), language-specific modules (e.g., `java_cf.lower_enhanced_for`), or inline lambdas for no-ops.

3. **`_build_expr_dispatch() → dict[str, Callable]`** -- returns a mapping of tree-sitter expression node types to pure-function handlers `(ctx, node) → str` (returning the result register). Canonical literal handlers (e.g., `common_expr.lower_canonical_none`) canonicalize language-native null/boolean node types to Python-form IR constants.

4. **`_build_type_map() → dict[str, str]`** -- returns a mapping from language-native type names to canonical forms (e.g., `"int" → "Int"`, `"String" → "String"`). Used for type seeding during lowering.

Additionally, block-scoped frontends set the class attribute `BLOCK_SCOPED = True`, which enables LLVM-style variable name mangling in `TreeSitterEmitContext`.

---

## Related Resources

- [Frontend design notes](../notes-on-frontend-design.md) -- high-level architecture overview, LLM frontend, chunked LLM frontend, worked examples
- [Type system design](../type-system.md) -- type extraction pipeline, block-scope tracking algorithm
- `interpreter/ir.py` -- IR instruction set definition (Opcode enum, IRInstruction, SourceLocation)
- `interpreter/frontend.py` -- `Frontend` ABC and `get_frontend()` factory
- `interpreter/frontends/__init__.py` -- lazy-loading registry mapping Language enum to frontend classes
- `interpreter/frontends/context.py` -- `TreeSitterEmitContext` and `GrammarConstants` definitions
- `interpreter/frontends/common/` -- shared pure-function lowerers
