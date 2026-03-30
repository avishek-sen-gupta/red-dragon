## Code Search and Analysis Tools

### ast-grep (structural code search)

Use the `/ast-grep` skill for structural code searches instead of regex grep. ast-grep matches AST patterns and handles multi-line constructs, indentation variations, and nested expressions that regex misses.

**When to use ast-grep:**
- Searching for constructor/function call patterns (e.g., `FuncRef(name=$X)`, `DeclVar(name=$N, value_reg=$R)`)
- Finding all call sites of a specific function with certain argument shapes
- Migrating field types: finding all constructions that pass a specific field
- Any search where the pattern spans multiple lines or has variable whitespace

**When plain grep is sufficient:**
- Simple keyword/string searches (`SELF_PARAM_NAMES`, `def _handle_const`)
- Import statements
- Constant definitions

### code-review-graph (knowledge graph)

Use the code-review-graph MCP tools before scanning files manually for codebase understanding:

- `semantic_search_nodes_tool` — find classes, functions, or types by name or keyword
- `query_graph_tool` — explore relationships: `callers_of`, `callees_of`, `imports_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`
- `get_impact_radius_tool` — understand blast radius before making changes
- `get_review_context_tool` — token-efficient review context for PRs

These save significant tokens by avoiding full codebase scans. Fall back to grep/glob/read only when the graph doesn't cover what you need.
