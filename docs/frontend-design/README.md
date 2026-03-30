# Frontend Design Documentation

This directory contains per-language documentation for the RedDragon frontend subsystem. For the comprehensive architecture overview (deterministic, LLM, and chunked LLM frontends), see [notes-on-frontend-design.md](../notes-on-frontend-design.md).

For the `BaseFrontend` class, `TreeSitterEmitContext`, and common lowerer infrastructure, see [base-frontend.md](base-frontend.md).

---

## Per-Language Documents

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

## Directory Layout

Each language frontend is a directory with a standard module layout:

```
interpreter/frontends/<language>/
├── frontend.py          # BaseFrontend subclass — _build_*() hooks return dispatch tables
├── node_types.py        # Frozen dataclass of tree-sitter node type constants
├── expressions.py       # Pure-function expression lowerers: (ctx, node) → Register
├── control_flow.py      # Pure-function control flow lowerers: (ctx, node) → None
├── declarations.py      # Pure-function declaration lowerers: (ctx, node) → None
└── (optional extras)    # e.g. assignments.py (Python, Ruby), pascal_constants.py
```

## Key Files

- `interpreter/ir.py` -- IR types (Opcode enum, Register, CodeLabel, SourceLocation, IRInstruction factory)
- `interpreter/instructions.py` -- 33 per-opcode frozen dataclasses with typed fields and `reads()`/`writes()` methods
- `interpreter/frontend.py` -- `Frontend` ABC and `get_frontend()` factory
- `interpreter/frontends/__init__.py` -- lazy-loading registry mapping Language enum to frontend classes
- `interpreter/frontends/context.py` -- `TreeSitterEmitContext` and `GrammarConstants` definitions
- `interpreter/frontends/common/` -- shared pure-function lowerers
