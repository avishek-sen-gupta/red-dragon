# Remove the single-file surfaces — design

**Date:** 2026-10-13
**Status:** approved in conversation; first of three specs

## Context

RedDragon compiles non-COBOL code two ways. `run()` lowers one source string and
hand-builds a single-module `LinkedProgram`; `compile_directory` compiles every file
through `compile_module` and `link_modules`. The two disagree on labels and function
names for the same program. The goal across three specs:

1. **This spec** — remove the surfaces built on single-file lowering: `interpreter/api.py`,
   `mcp_server/`, `viz/`, and the CLI's dump flags.
2. One compile core taking a list of source files (path and bytes, already read); the
   shell turns a directory or a single file into that list. `run()`'s hand-built
   `LinkedProgram` goes.
3. COBOL compiles only through `compile_cobol`; `compile_directory` stops accepting it.

Removing these surfaces first means spec 2 has one caller to rewire (`run()`), not six.
IR, CFG and Mermaid dumps come back later, built on the fully linked program only.

## Removed

| Surface | What it did |
|---|---|
| `interpreter/api.py` | Single-string helpers: `lower_source` (string → IR), `lower_and_infer` (IR plus type environment), `dump_ir`, `build_cfg_from_source` (CFG, optionally one function), `dump_cfg`, `dump_mermaid`, `ir_stats` (opcode counts), `execute_traced` (one-module traced run), `extract_function_source` (one function's source via tree-sitter); and `run_project` (directory → `compile_directory` → `execute_cfg`) |
| `interpreter/__init__.py` re-exports | The eight `api` names above, importable from `interpreter` |
| `interpreter/ir_stats.py` | `count_opcodes`; its only caller was `api.ir_stats` |
| `mcp_server/` | MCP server: `load_program` (one source string → stepping session), `step`, `run_to_end`, `get_state`, `get_ir`, `load_project` (directory → `compile_directory` summary), `list_opcodes` |
| `viz/` | Textual TUI: single-file pipeline view (source → AST → IR → CFG → execution), side-by-side language compare, lowering trace, frontend coverage matrix, and project mode over `compile_directory` |
| CLI `--ir-only`, `--cfg-only`, `--mermaid`, `--function` | Print one file's IR, CFG, or Mermaid CFG (optionally one function) and exit without running |
| `scripts/demo_type_inference_tier2.py`, `scripts/demo_type_inference_tier3.py`, `scripts/demo_multifile_project.py` | Demos over `lower_and_infer` and `run_project` |
| `docs/pipeline-viz.cast`, `docs/pipeline-viz.gif` | Recordings of the TUI |
| `mcp`, `textual` dependencies; `mcp_server` in `pyrightconfig.json` | Only the removed packages used them |

The record of the removal is an ADR in `docs/architectural-design-decisions.md` carrying
this table and the commit to restore from. A bead tracks rebuilding the IR, CFG and
Mermaid dumps on the fully linked program.

## Kept

- `interpreter.py`, the CLI: runs a file through `run()`, with `--language`, `--entry`,
  `--backend`, `--max-steps`, `--verbose`, `--frontend`.
- `interpreter/__main__.py`, the COBOL CLI.
- `run_linked_traced` and `execute_cfg_traced` in `interpreter/run.py`, while
  `scripts/symbolic_trace_harness.py` uses them. Anything in `run.py` left with no caller
  after the removal goes too.

## Tests

- Deleted with their subject: `tests/unit/test_api.py`, `tests/unit/test_ir_stats.py`,
  `tests/unit/test_mcp_tools.py`, `tests/unit/test_mcp_formatting.py`,
  `tests/unit/project/test_mcp_tool.py`, `tests/integration/test_mcp_server.py`,
  `tests/integration/project/test_api_integration.py`, `tests/unit/viz/` except
  `test_run_linked_traced.py`, `tests/integration/viz/`, and the two
  `tests/unit/demos/test_type_inference_tier*.py`.
- Kept by moving: `tests/unit/viz/test_run_linked_traced.py` tests `run.py`, not viz; it
  moves to `tests/unit/`.
- Rewritten, because they use `api` only to reach something else, which keeps its
  coverage: `tests/unit/test_c_frontend.py` (CFG of one C function),
  `tests/unit/test_pattern_index_registers.py` (lowering and a traced run),
  `tests/unit/test_step_budget_exhausted.py` (step-budget warning). They call
  `get_frontend`, `build_cfg` and `run()` directly, with the same assertions.

## Living documentation

Same commit as the removal: `README.md` (the TUI, MCP server, CLI dump flags and Python
API sections; API examples rewritten on `run()`), `docs/linker-design.md` (the MCP rows),
`docs/notes-on-vm-design.md` (the `dump_ir` reference), `guidelines/project-context.md`
(`mcp_server` in the pyright scope; textual). `guidelines/code-search-tools.md` names a
different MCP server and stays. Point-in-time plans under `docs/design/` and
`docs/superpowers/` stay as written.

## Done when

- No module, test, script, doc example or config entry imports or names `interpreter.api`,
  `mcp_server`, `viz`, `interpreter.ir_stats`, or the four CLI flags.
- red-dragon's gate is green: Black, import-linter, the fp-lint ratchet, the full suite.
- The forge, bumped to the result, is green under `make test-all`.
