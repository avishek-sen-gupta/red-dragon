# Codebase Structure

**Analysis Date:** 2026-03-18

## Directory Layout

```
red-dragon/
├── interpreter/              # Core VM and language frontends
│   ├── frontends/            # Language-specific AST-to-IR lowering
│   │   ├── common/           # Shared lowering logic across languages
│   │   ├── python/           # Python language frontend
│   │   ├── java/             # Java language frontend
│   │   ├── javascript/       # JavaScript language frontend
│   │   ├── typescript.py     # TypeScript language frontend
│   │   ├── c/                # C language frontend
│   │   ├── cpp/              # C++ language frontend
│   │   ├── csharp/           # C# language frontend
│   │   ├── go/               # Go language frontend
│   │   ├── kotlin/           # Kotlin language frontend
│   │   ├── lua/              # Lua language frontend
│   │   ├── pascal/           # Pascal language frontend
│   │   ├── php/              # PHP language frontend
│   │   ├── ruby/             # Ruby language frontend
│   │   ├── rust/             # Rust language frontend
│   │   ├── scala/            # Scala language frontend
│   │   ├── base_node_types.py # Common AST node types
│   │   ├── context.py        # Lowering context and state
│   │   ├── type_extraction.py # Type inference from AST
│   │   └── _base.py          # Frontend base class
│   ├── cobol/                # COBOL-specific lowering (external language)
│   │   ├── grammars/         # COBOL grammar files
│   │   └── [40+ lowering files]
│   ├── ast_repair/           # AST syntax error repair for LLM frontends
│   ├── api.py                # Public API (lower_source, dump_ir, dump_cfg)
│   ├── frontend.py           # AST parser dispatcher for languages
│   ├── llm_frontend.py       # LLM-based AST parsing
│   ├── chunked_llm_frontend.py # Chunked LLM parsing for large files
│   ├── llm_client.py         # LLM API client wrapper
│   ├── vm.py                 # Virtual machine execution engine
│   ├── executor.py           # VM instruction executor
│   ├── ir.py                 # IR opcode definitions
│   ├── registry.py           # Function/class symbol registry
│   ├── type_expr.py          # Type system ADT (structured types)
│   ├── type_environment.py   # Type binding and scope tracking
│   ├── type_environment_builder.py # Type environment construction
│   ├── type_inference.py     # Type inference engine
│   ├── type_compatibility.py # Type compatibility checking
│   ├── type_resolver.py      # Type resolution from name strings
│   ├── type_graph.py         # Type dependency graph
│   ├── overload_resolver.py  # Function overload resolution
│   ├── resolution_strategy.py # Function call resolution strategies
│   ├── unresolved_call.py    # Unresolved call tracking
│   ├── builtins.py           # Built-in function implementations
│   ├── function_signature.py # Function signature representation
│   ├── function_kind.py      # Function classification (method/static/etc)
│   ├── cfg.py                # Control flow graph construction
│   ├── cfg_types.py          # CFG data structures
│   ├── run.py                # VM initialization and execution
│   ├── backend.py            # LLM backend selection
│   ├── binop_coercion.py     # Binary operator type coercion
│   ├── unop_coercion.py      # Unary operator type coercion
│   ├── conversion_rules.py   # Type conversion strategies
│   ├── default_conversion_rules.py # Default conversion implementations
│   ├── identity_conversion_rules.py # Identity conversion rules
│   ├── ambiguity_handler.py  # Ambiguous call resolution
│   ├── field_fallback.py     # Field access fallback logic
│   ├── dataflow.py           # Data flow analysis
│   ├── ir_stats.py           # IR statistics collection
│   ├── constants.py          # Global constants and configuration
│   ├── var_scope_info.py     # Variable scope tracking
│   ├── typed_value.py        # Runtime typed values
│   ├── null_type_resolver.py # Null type inference
│   ├── parser.py             # AST parsing utilities
│   └── [50+ total core files]
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests (isolated, no I/O)
│   │   ├── rosetta/          # Multi-language algorithm verification
│   │   ├── exercism/         # Programming exercise tests
│   │   ├── equivalence/      # Cross-language equivalence tests
│   │   ├── fixtures/         # Test data and fixtures
│   │   ├── demos/            # Demo code snippets
│   │   └── test_*.py         # Individual unit test files (150+)
│   ├── integration/          # Integration tests (VM execution)
│   │   └── test_*.py         # End-to-end execution tests
│   └── external/             # Tests requiring external services
├── docs/                     # Documentation
│   ├── frontend-design/      # Language-specific lowering design docs
│   ├── superpowers/          # Project specification directory
│   │   ├── specs/            # Point-in-time design specifications (immutable)
│   │   └── plans/            # Implementation plan documents (immutable)
│   ├── screenshots/          # UI visualization screenshots
│   ├── type-system.md        # Type system documentation
│   ├── architectural-design-decisions.md # ADR records
│   └── [other docs]
├── viz/                      # Textual UI visualization
│   ├── panels/               # UI panel implementations
│   │   ├── ast_panel.py      # AST visualization
│   │   ├── ir_panel.py       # IR visualization
│   │   ├── cfg_panel.py      # CFG visualization
│   │   ├── vm_state_panel.py # VM state inspector
│   │   ├── step_panel.py     # Step-by-step execution
│   │   ├── source_panel.py   # Source code display
│   │   └── [6+ more panels]
│   ├── app.py                # Main TUI application
│   ├── compare_app.py        # Comparison UI
│   ├── coverage_app.py       # Coverage visualization
│   ├── examples/             # UI example configurations
│   └── pipeline.py           # UI data pipeline
├── scripts/                  # CLI and utility scripts
│   ├── audit_*.py            # Frontend audit/validation scripts
│   ├── demo_*.py             # Demonstration scripts
│   ├── exercism_harvest.py   # Test data collection
│   └── paper-results-code/   # Research/paper result generation
├── interpreter.py           # CLI entry point
├── pyproject.toml           # Poetry configuration
├── poetry.lock              # Dependency lock file
├── README.md                # Project overview
├── CLAUDE.md                # Claude code instructions
└── PHILOSOPHY.md            # Design philosophy
```

## Directory Purposes

**interpreter/**
Core VM implementation and language frontends. This is the main application code.
- `frontends/`: Multi-language AST parsing and IR lowering (18 languages supported)
- `cobol/`: COBOL-specific lowering (40+ files for complex dialects)
- `ast_repair/`: Syntax error repair for LLM-based parsing
- Root files: VM, IR, type system, execution, and registry

**tests/**
Comprehensive test suite separated by test type and focus area.
- `unit/`: Fast, isolated tests (no I/O, 11,800+ tests)
- `integration/`: Full VM execution tests (real language code)
- `external/`: Tests requiring LLM APIs (marked with `@pytest.mark.external`)

**docs/**
Living documentation plus immutable spec/plan records.
- `superpowers/specs/` and `superpowers/plans/`: Point-in-time designs (read-only)
- `type-system.md`: Type system reference (updated as system evolves)
- `architectural-design-decisions.md`: ADR log (append-only)

**viz/**
Textual User Interface (TUI) for interactive code analysis.
- `panels/`: Individual UI components (AST, IR, CFG, VM state, etc.)
- `app.py`: Main interactive viewer
- `coverage_app.py`: Coverage analysis tool

**scripts/**
Operational and research utilities.
- `audit_*.py`: Frontend validation against language specs
- `demo_*.py`: Feature demonstrations
- `paper-results-code/`: Research result generation

## Key File Locations

**Entry Points:**
- `interpreter.py`: CLI entry point; parses args and calls `run()` or `dump_ir()`
- `interpreter/api.py`: Public Python API (`lower_source()`, `dump_ir()`, `dump_cfg()`)
- `interpreter/run.py`: VM initialization and execution orchestration

**Core IR and VM:**
- `interpreter/ir.py`: Opcode definitions (STORE_VAR, LOAD_VAR, CALL_FUNC, etc.)
- `interpreter/vm.py`: Virtual machine state and instruction execution
- `interpreter/executor.py`: VM instruction dispatch and execution logic

**Type System:**
- `interpreter/type_expr.py`: TypeExpr ADT (structured type representation)
- `interpreter/type_environment.py`: Type bindings and scope chain
- `interpreter/type_inference.py`: Type inference engine

**Language Frontends:**
- `interpreter/frontend.py`: AST parser dispatcher; selects parser by language
- `interpreter/frontends/[language]/frontend.py`: Language-specific entry point
- `interpreter/frontends/[language]/declarations.py`: Function/class lowering
- `interpreter/frontends/[language]/expressions.py`: Expression lowering
- `interpreter/frontends/[language]/control_flow.py`: Loop/branch lowering
- `interpreter/frontends/[language]/node_types.py`: Language-specific AST types

**Common Patterns (used by all frontends):**
- `interpreter/frontends/common/`: Shared lowering logic (assignments, expressions, control flow)

**Execution and Resolution:**
- `interpreter/registry.py`: Function/class symbol table
- `interpreter/overload_resolver.py`: Function overload resolution
- `interpreter/builtins.py`: Built-in function implementations

**Configuration:**
- `interpreter/constants.py`: Global constants (FRONTEND_DETERMINISTIC, FRONTEND_LLM, etc.)
- `interpreter/backend.py`: LLM backend selection

## Naming Conventions

**Files:**
- `test_*.py`: Unit tests in `tests/unit/`
- `test_*.py`: Integration tests in `tests/integration/`
- `*_frontend.py`: Language frontend entry point (e.g., `java_frontend.py`)
- `demo_*.py`: Demonstration scripts in `scripts/`

**Directories:**
- Language names in lowercase: `python/`, `java/`, `cpp/`, `csharp/`
- Feature areas: `cobol/`, `ast_repair/`, `frontends/`
- Test categories: `unit/`, `integration/`, `external/`

**Python Modules:**
- Class names: PascalCase (e.g., `TypeEnvironment`, `VirtualMachine`)
- Function names: snake_case (e.g., `lower_function_def()`, `emit_opcode()`)
- Private functions: prefix with `_` (e.g., `_handle_new_object()`)
- Constants: UPPER_SNAKE_CASE (e.g., `FRONTEND_DETERMINISTIC`)

**Enums and Type ADTs:**
- Enum variants: PascalCase in code (e.g., `TypeExpr.Primitive`, `TypeExpr.Function`)
- String representations: lowercase with underscores (e.g., `"primitive"`, `"function"`)

## Where to Add New Code

**New Language Frontend:**
1. Create `interpreter/frontends/[language]/` directory
2. Implement required modules:
   - `frontend.py`: Main entry point inheriting from `_base.Frontend`
   - `declarations.py`: Function/class lowering
   - `expressions.py`: Expression lowering
   - `control_flow.py`: Loop/branch lowering
   - `node_types.py`: Language-specific AST node types (can inherit from common)
3. Add tests in `tests/unit/test_[language]_frontend.py`
4. Add integration tests in `tests/integration/test_[language]_*_execution.py`

**New Built-in Function:**
- Add implementation in `interpreter/builtins.py` as a class method
- Register in the `BUILTIN_REGISTRY` dict
- Add unit tests in `tests/unit/test_builtins.py`

**New Opcode:**
- Define in `interpreter/ir.py` as a class with opcode string constant
- Implement handler in `interpreter/executor.py`
- Add integration tests exercising the opcode path

**New Type System Feature:**
- Add to `TypeExpr` ADT in `interpreter/type_expr.py`
- Update type inference in `interpreter/type_inference.py`
- Update type compatibility in `interpreter/type_compatibility.py`
- Add unit tests in `tests/unit/test_type_*.py`
- Document in `docs/type-system.md`

**Shared Lowering Logic:**
- Add to `interpreter/frontends/common/` (used by all language frontends)
- Example: `assignments.py`, `control_flow.py`, `expressions.py`

**VM/Execution Features:**
- Core VM logic: `interpreter/vm.py`
- Instruction execution: `interpreter/executor.py`
- Built-in operations: `interpreter/builtins.py`

**Utilities and Helpers:**
- Shared across frontends: `interpreter/frontends/common/`
- Type utilities: `interpreter/type_*.py`
- Execution utilities: `interpreter/run.py`, `interpreter/registry.py`

## Special Directories

**interpreter/cobol/**
COBOL frontend (40+ files). Special structure due to COBOL complexity:
- `cobol_frontend.py`: Entry point
- `ir_encoders.py`: Complex IR emission for COBOL semantics
- `byte_builtins.py`: Byte/binary operation implementations
- `lower_*.py`: Statement/expression-specific lowering modules
- `grammars/`: COBOL dialect grammar files
- `asg_types.py`, `asg_graph.py`: Abstract semantic graph types

**tests/unit/rosetta/**
Multi-language verification tests. Each test exercises the same algorithm across multiple languages to verify cross-language correctness.

**tests/unit/fixtures/**
Reusable test data: code snippets, expected IR outputs, type definitions.

**docs/superpowers/specs/ and docs/superpowers/plans/**
Point-in-time design records. NEVER modify these directly. Newer specs supersede older ones by convention. Update living docs instead (README, `type-system.md`, etc.).

**viz/panels/**
Modular UI components for the Textual TUI visualization. Each panel handles one aspect (AST view, IR view, CFG view, etc.).

---

*Structure analysis: 2026-03-18*
