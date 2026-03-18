# Technology Stack

**Analysis Date:** 2026-03-18

## Languages

**Primary:**
- Python 3.10+ - Core interpreter, frontends, VM execution engine, analysis tools
- COBOL - Legacy language support via ProLeap bridge (external dependency)

**Secondary:**
- Tree-Sitter (C/Rust) - 15 language parsing via `tree-sitter` bindings
- ANTLR4 Runtime (Java) - COBOL data type parsing via generated lexer/parser

## Runtime

**Environment:**
- Python 3.10+ (minimum), <4.0 (maximum)
- Poetry 2.1.3+ for dependency management
- No JavaScript/Node.js runtime (viz uses Textual TUI, not web)

**Package Manager:**
- Poetry for Python dependency management
- Lockfile: `poetry.lock` (present, maintained)

## Frameworks

**Core Interpreter:**
- Custom multi-language VM in `interpreter/vm.py` - 31-opcode universal IR execution engine
- Custom control flow graph builder in `interpreter/cfg.py` - TAC IR → CFG transformation
- Custom type system using TypeExpr ADT in `interpreter/type_expr.py` - no string roundtrips

**Parsing & Lowering:**
- Tree-Sitter (v0.25.2+) - Deterministic AST parsing for 15 languages
- tree-sitter-language-pack (v0.13.0+) - Pre-built language parsers (python, javascript, typescript, java, ruby, go, php, csharp, c, cpp, rust, kotlin, scala, lua, pascal)
- ANTLR4 Runtime (v4.13.2+) - COBOL data type grammar parsing
- Custom LLM-based frontend in `interpreter/llm_frontend.py` - Fallback for unparseable code

**TUI & Visualization:**
- Textual (v8.1.0+) - Interactive terminal UI for RedDragon Pipeline Visualizer (`viz/app.py`)
- Custom panel system (`viz/panels/`) - Source, AST, IR, VM State, CFG, Step panels

**Testing:**
- pytest (v8.0.0+) - Test runner
- pytest-xdist (v3.8.0+) - Parallel test execution (`-n auto` in pyproject.toml)

**Build/Dev:**
- black (v26.1.0+) - Code formatting (mandatory before commit)
- pylint (v3.0+) - Static analysis
- radon (v6.0+) - Code complexity analysis (exclude `tests/*`, min C)
- import-linter (v2.0+) - Dependency graph validation
- grimp (v3.0+) - Import graph analysis
- pydeps (v1.12+) - Dependency visualization

## Key Dependencies

**Critical:**
- litellm (v1.60.0+) - Unified LLM API client supporting Claude, OpenAI, Ollama, HuggingFace
  - Used by `interpreter/llm_client.py` for backend abstraction
  - Supports lazy import to avoid dependencies when not needed
  - Configured via `LLMProvider` enum in `interpreter/constants.py`
- pydantic (v2.12.5+) - Data validation and configuration models
- tree-sitter (v0.25.2+) - Low-level tree-sitter Python bindings
- tree-sitter-language-pack (v0.13.0+) - Pre-built language plugins for tree-sitter
- antlr4-python3-runtime (v4.13.2+) - ANTLR parser runtime for COBOL

**Infrastructure:**
- aiohttp (v3.13.3+) - Async HTTP client (dependency of litellm for API calls)

## Configuration

**Environment:**
- Environment variables for LLM API keys (read by litellm at runtime, not documented in code)
- `LLMProvider` enum in `interpreter/constants.py` for provider selection
- `VMConfig` dataclass in `interpreter/run_types.py` for runtime configuration (backend, max_steps, unresolved_call_strategy)
- No `.env` file in repo (not checked in)

**Build:**
- `pyproject.toml` - Poetry project metadata, dependencies, pytest configuration
- `poetry.lock` - Locked dependency versions

**Custom Configuration:**
- `interpreter/constants.py` - Named constants (Language enum with 16 languages, LLMProvider enum with 4 providers, opcode prefixes)
- Lazy configuration in `interpreter/llm_client.py` - `_PROVIDER_DEFAULTS` dict maps providers to model/base_url pairs
- Ollama defaults to `http://localhost:11434` with `qwen2.5-coder:7b-instruct`
- HuggingFace endpoints in `_HF_ENDPOINT_REGISTRY` (currently only `qwen2.5-coder-32b`)

## Platform Requirements

**Development:**
- Python 3.10+
- Poetry for dependency isolation
- Poetry environment activates with `poetry run` prefix
- Universal CTags (external, optional) - for code symbol extraction scripts
- Neo4j (optional) - graph persistence for future features

**Production:**
- Deployment target: anywhere Python 3.10+ runs
- No external services required for deterministic execution (complete code + known dependencies)
- LLM API credentials required only when using LLM frontends or LLM plausible-value resolver
  - Claude API key for `litellm` when `LLMProvider.CLAUDE` selected
  - OpenAI API key for `litellm` when `LLMProvider.OPENAI` selected
  - Local Ollama instance for `LLMProvider.OLLAMA` at `http://localhost:11434`
  - HuggingFace token and endpoint registration for `LLMProvider.HUGGINGFACE`

## Language Support Matrix

16 languages across 4 parsing strategies:

**Tree-Sitter Deterministic (15 languages):**
- Python, JavaScript, TypeScript, Java, Ruby, Go, PHP, C#, C, C++, Rust, Kotlin, Scala, Lua, Pascal

**ProLeap Bridge (1 language):**
- COBOL (external subprocess execution)

**LLM Frontends (any language):**
- Full LLM frontend in `interpreter/llm_frontend.py` - single LLM call per file
- Chunked LLM in `interpreter/chunked_llm_frontend.py` - per-function chunking + LLM calls per chunk

---

*Stack analysis: 2026-03-18*
