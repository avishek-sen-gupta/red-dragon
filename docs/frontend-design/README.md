# Frontend Design Documentation

This directory contains exhaustive per-file documentation for the RedDragon frontend subsystem -- the pipeline that lowers language-specific tree-sitter ASTs into a common, language-agnostic IR consumed by the VM, CFG builder, and dataflow analysis.

---

## Architecture Overview

The frontend subsystem converts source code in any of 15 supported languages into a universal flattened three-address code IR (~20 opcodes). The deterministic frontend strategy uses tree-sitter to parse source into an AST, then performs recursive descent over that AST to emit IR instructions.

The architecture follows a classic **base class + per-language subclass** pattern:

```
Frontend (ABC)                          interpreter/frontend.py
  |
  +-- BaseFrontend                      interpreter/frontends/_base.py
        |
        +-- PythonFrontend              interpreter/frontends/python.py
        +-- JavaScriptFrontend          interpreter/frontends/javascript.py
        +-- TypeScriptFrontend          interpreter/frontends/typescript.py  (extends JS)
        +-- JavaFrontend                interpreter/frontends/java.py
        +-- KotlinFrontend              interpreter/frontends/kotlin.py
        +-- ScalaFrontend               interpreter/frontends/scala.py
        +-- CFrontend                   interpreter/frontends/c.py
        +-- CppFrontend                 interpreter/frontends/cpp.py         (extends C)
        +-- CSharpFrontend              interpreter/frontends/csharp.py
        +-- GoFrontend                  interpreter/frontends/go.py
        +-- RubyFrontend                interpreter/frontends/ruby.py
        +-- LuaFrontend                 interpreter/frontends/lua.py
        +-- PhpFrontend                 interpreter/frontends/php.py
        +-- PascalFrontend              interpreter/frontends/pascal.py
        +-- RustFrontend                interpreter/frontends/rust.py
```

`BaseFrontend` provides:
- Two dispatch tables (`_STMT_DISPATCH`, `_EXPR_DISPATCH`) mapping tree-sitter node type strings to handler methods
- Overridable class-level constants for field names and literal tokens where grammars differ
- A library of ~30 reusable lowering methods (expressions, statements, control flow, function/class definitions)
- Code generation primitives: register allocation, label generation, instruction emission

Each language subclass populates the dispatch tables with its grammar's node types, overrides constants where the grammar diverges from Python defaults, and adds handlers for language-specific constructs.

---

## Document Index

| Document | Source File | Lines | Description |
|---|---|---|---|
| [base-frontend.md](base-frontend.md) | `interpreter/frontends/_base.py` | 985 | Shared lowering infrastructure, dispatch tables, all reusable methods |
| [python.md](python.md) | `interpreter/frontends/python.py` | 1138 | Python frontend -- the reference implementation |
| [javascript.md](javascript.md) | `interpreter/frontends/javascript.py` | 1006 | JavaScript frontend -- destructuring, arrow functions, template strings |
| [typescript.md](typescript.md) | `interpreter/frontends/typescript.py` | 172 | TypeScript frontend -- extends JavaScript, strips type annotations |
| [java.md](java.md) | `interpreter/frontends/java.py` | 1109 | Java frontend -- records, instanceof, method references |
| [kotlin.md](kotlin.md) | `interpreter/frontends/kotlin.py` | 1115 | Kotlin frontend -- companion objects, elvis operator, when expressions |
| [scala.md](scala.md) | `interpreter/frontends/scala.py` | 849 | Scala frontend -- for-comprehensions, case classes, pattern matching |
| [c.md](c.md) | `interpreter/frontends/c.py` | 821 | C frontend -- pointers, sizeof, struct/union, goto |
| [cpp.md](cpp.md) | `interpreter/frontends/cpp.py` | 612 | C++ frontend -- extends C, adds namespaces, templates, classes |
| [csharp.md](csharp.md) | `interpreter/frontends/csharp.py` | 1454 | C# frontend -- LINQ, properties, events, using statements |
| [go.md](go.md) | `interpreter/frontends/go.py` | 1116 | Go frontend -- goroutines, channels, multiple returns, short declarations |
| [ruby.md](ruby.md) | `interpreter/frontends/ruby.py` | 1150 | Ruby frontend -- symbols, ranges, blocks, heredocs |
| [lua.md](lua.md) | `interpreter/frontends/lua.py` | 787 | Lua frontend -- goto/labels, table constructors, `..` concat |
| [php.md](php.md) | `interpreter/frontends/php.py` | 1404 | PHP frontend -- namespaces, traits, match expressions |
| [pascal.md](pascal.md) | `interpreter/frontends/pascal.py` | 914 | Pascal frontend -- begin/end blocks, procedure/function distinction |
| [rust.md](rust.md) | `interpreter/frontends/rust.py` | 944 | Rust frontend -- let bindings, match, closures, impl blocks, macros |

**Total**: 15,576 lines across 16 source files (base + 15 languages).

---

## How Subclasses Customise Behaviour

Each language frontend customises `BaseFrontend` through four mechanisms:

1. **Override class-level constants** -- field names (`FUNC_PARAMS_FIELD`, `ATTR_ATTRIBUTE_FIELD`, etc.), literal tokens (`NONE_LITERAL`, `TRUE_LITERAL`), and node type sets (`BLOCK_NODE_TYPES`, `COMMENT_TYPES`).

2. **Populate dispatch tables** -- in `__init__`, map tree-sitter node type strings (e.g., `"if_statement"`, `"binary_expression"`) to handler methods (e.g., `self._lower_if`, `self._lower_binop`).

3. **Canonical literal mapping** -- map language-specific null/boolean node types to the canonical lowering methods (`_lower_canonical_none`, `_lower_canonical_true`, `_lower_canonical_false`) so that all languages produce `CONST "None"`, `CONST "True"`, `CONST "False"` in the IR.

4. **Add language-specific lowerers** -- implement new methods for constructs unique to that language (e.g., Python list comprehensions, JavaScript destructuring, Go goroutines).

---

## Related Resources

- [Frontend design notes](../notes-on-frontend-design.md) -- high-level architecture overview, LLM frontend, chunked LLM frontend, worked examples
- `interpreter/ir.py` -- IR instruction set definition (Opcode enum, IRInstruction, SourceLocation)
- `interpreter/constants.py` -- shared constant strings used across frontends
- `interpreter/frontend.py` -- `Frontend` ABC and `get_frontend()` factory
- `interpreter/frontends/__init__.py` -- lazy-loading registry mapping language names to frontend classes
