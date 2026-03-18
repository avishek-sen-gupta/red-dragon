# External Integrations

**Analysis Date:** 2026-03-18

## APIs & External Services

**LLM Services (conditional):**
- Claude (Anthropic) - LLM lowering and plausible value generation
  - SDK/Client: `litellm` (v1.60.0+)
  - Auth: API key read by litellm at runtime (environment variable managed externally)
  - Default model: `claude-sonnet-4-20250514`
  - Usage: Optional LLM frontend for unsupported languages, AST repair for malformed parse trees, unresolved call resolution
  - Implementation: `interpreter/llm_client.py` → `LiteLLMClient.complete()`

- OpenAI (GPT-4) - Alternative LLM backend
  - SDK/Client: `litellm`
  - Auth: API key via environment
  - Default model: `gpt-4o`
  - Usage: Switchable alternative to Claude via `LLMProvider.OPENAI`
  - Implementation: `interpreter/llm_client.py` → factory function `get_llm_client(provider="openai")`

- Ollama (Local) - Self-hosted LLM inference
  - SDK/Client: `litellm` with Ollama protocol
  - Auth: None (local instance)
  - Default model: `qwen2.5-coder:7b-instruct`
  - Default endpoint: `http://localhost:11434`
  - Usage: Offline alternative for isolated environments
  - Implementation: `interpreter/llm_client.py` → `_PROVIDER_DEFAULTS[LLMProvider.OLLAMA]`

- HuggingFace (Inference API) - Cloud-hosted model endpoints
  - SDK/Client: `litellm` with HuggingFace protocol
  - Auth: HuggingFace token via environment
  - Registered endpoints: `_HF_ENDPOINT_REGISTRY` in `interpreter/llm_client.py` (currently `qwen2.5-coder-32b`)
  - Usage: Fine-tuned or proprietary models via HuggingFace endpoints
  - Implementation: Dynamic endpoint registration, configurable at runtime

## Data Storage

**Databases:**
- None in active use
- Neo4j (optional future integration) - documented in README as optional for graph persistence

**File Storage:**
- Local filesystem only - no cloud storage integration
- Temp files in standard Python temp directories for test fixtures

**Caching:**
- None (deterministic execution = no cache needed for complete code)
- Memoization: `@functools.lru_cache` in `interpreter/builtins.py` for builtin functions (pure functions only)

## Authentication & Identity

**Auth Provider:**
- Custom / None - No authentication layer in RedDragon itself
- LLM credential management: Delegated to `litellm` (reads env vars, manages API keys externally)
- Access control: None (single-user analysis tool)

## Monitoring & Observability

**Error Tracking:**
- None (no external error tracking service)

**Logs:**
- Standard Python `logging` module throughout
- Logger hierarchy: `logging.getLogger(__name__)` in every module
- Log levels: `INFO` (progress), `DEBUG` (detailed), `WARNING` (issues)
- Output: Sent to stderr by default, configurable at application startup
- Key logged operations:
  - `interpreter/llm_client.py`: LLM completion calls, model/max_tokens
  - `interpreter/api.py`: Lowering operations, language/frontend selection
  - `interpreter/run.py`: VM execution, step counts, stats
  - `interpreter/executor.py`: Call dispatch, symbolic value resolution

## CI/CD & Deployment

**Hosting:**
- No deployment pipeline configured
- GitHub Actions CI (`.github/workflows/ci.yml` badge shown in README)

**CI Pipeline:**
- GitHub Actions for testing (implied by CI badge)
- Black formatting enforced in CI
- Test suite runs on every PR/push
- No deployment automation

## Environment Configuration

**Required env vars (for LLM features):**
- When using Claude: `ANTHROPIC_API_KEY` (read by litellm)
- When using OpenAI: `OPENAI_API_KEY` (read by litellm)
- When using HuggingFace: `HF_TOKEN` (read by litellm)
- When using Ollama: None (local, no auth)

**Provider selection at runtime:**
- `LLMProvider` enum in `interpreter/constants.py` determines which backend to use
- Default: `LLMProvider.CLAUDE`
- Passed to `get_llm_client(provider=...)` in `interpreter/llm_client.py`
- Also configurable via `VMConfig.backend` in `interpreter/run_types.py`

**Secrets location:**
- Not stored in repo (no `.env` file checked in)
- Managed entirely by `litellm` lazy-import mechanism
- Expected at environment level (shell, Docker, k8s secrets, CI/CD platform)

## Tree-Sitter Language Plugins

**External dependency:**
- tree-sitter-language-pack (v0.13.0+) provides pre-built language parsers
- Languages included: python, javascript, typescript, java, ruby, go, php, csharp, c, cpp, rust, kotlin, scala, lua, pascal
- COBOL excluded (uses ProLeap bridge instead)
- Implementation: `interpreter/parser.py` → `TreeSitterParserFactory` → `tree_sitter_language_pack.get_parser(language_name)`

## COBOL Bridge

**External subprocess:**
- ProLeap (Java-based COBOL parser) - invoked as subprocess
- Implementation: `interpreter/cobol/subprocess_runner.py` → `SubprocessRunner`
- Data flow: COBOL source → subprocess → AST JSON → RedDragon ASG (`interpreter/cobol/asg_types.py`)
- No direct integration (subprocess-based isolation)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## LLM Client Architecture

**Factory pattern:**
```python
def get_llm_client(
    provider: str = LLMProvider.CLAUDE,  # "claude", "openai", "ollama", "huggingface"
    model: str = "",                      # Empty = use default per provider
    completion_fn: Callable = _LAZY_IMPORT,
    base_url: str = ""
) -> LLMClient
```

**Model resolution logic in `_resolve_model()`:**
- Checks `_PROVIDER_DEFAULTS` dict for model/base_url
- Ollama: prepends `ollama/` prefix, uses localhost:11434 by default
- HuggingFace: looks up endpoint in `_HF_ENDPOINT_REGISTRY` or accepts custom base_url
- Claude/OpenAI: pass through to litellm (it manages auth)

**Lazy import pattern:**
- `litellm` not imported until `LiteLLMClient.complete()` is called
- Enables deterministic execution paths without LLM (no import overhead)
- Used by: `interpreter/llm_frontend.py`, `interpreter/unresolved_call.py`, AST repair loop

## Runtime Resolver Strategies

**Unresolved call handling in `interpreter/unresolved_call.py`:**
- `SymbolicResolver` - Returns symbolic placeholders (deterministic, no API calls)
- `LLMPlausibleResolver` - Queries LLM for plausible values (non-deterministic)
- Configurable via `VMConfig.unresolved_call_strategy` enum in `interpreter/run_types.py`
- Options: `SYMBOLIC` (default) or `LLM`

**Type inference integration:**
- TypeExpr ADT in `interpreter/type_expr.py` drives type-aware value coercion
- `DefaultTypeConversionRules` in `interpreter/default_conversion_rules.py` implements write-time coercion
- No external type service; all rules embedded in code

---

*Integration audit: 2026-03-18*
