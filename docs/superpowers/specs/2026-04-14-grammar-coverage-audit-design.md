---
title: Grammar Coverage Audit — Design Spec
date: 2026-04-14
status: approved
---

# Grammar Coverage Audit

## Context

RedDragon supports 15 language frontends. Each frontend lowers tree-sitter AST nodes into IR via two dispatch tables (`_build_expr_dispatch` / `_build_stmt_dispatch`). A node type that is not in any dispatch table falls through to `SYMBOLIC("unsupported:X")`, representing a gap.

A script `scripts/audit_all_frontends.py` existed but was broken in two ways:
1. It only covered 7 of 15 languages.
2. It read legacy `_EXPR_DISPATCH` / `_STMT_DISPATCH` instance attributes, missing the context-mode frontends that define `_build_expr_dispatch()` / `_build_stmt_dispatch()` methods — so most dispatch tables appeared empty.
3. It was sample-driven: gaps only appeared if the construct occurred in a curated source string.

This script replaces it.

## Goal

A deterministic, sample-free audit that enumerates **all named node types in each tree-sitter grammar** and diffs them against what each frontend handles. Output is JSON (machine-readable) plus a terminal summary.

## Design

### Language registry

A static mapping from RedDragon language name → tree-sitter language pack name, covering all 15 frontends:

| RedDragon key | `tree_sitter_language_pack` name |
|---------------|----------------------------------|
| python        | python                           |
| java          | java                             |
| javascript    | javascript                       |
| typescript    | typescript                       |
| csharp        | csharp                           |
| kotlin        | kotlin                           |
| scala         | scala                            |
| go            | go                               |
| rust          | rust                             |
| c             | c                                |
| cpp           | cpp                              |
| ruby          | ruby                             |
| php           | php                              |
| lua           | lua                              |
| pascal        | pascal                           |

### Step 1 — Enumerate grammar named nodes

For each language, call `tree_sitter_language_pack.get_language(ts_name)` to get a `Language` object, then:

```python
named_nodes = {
    lang.node_kind_for_id(i)
    for i in range(lang.node_kind_count)
    if lang.node_kind_is_named(i)
}
```

This returns every named node type the grammar defines, independent of any source sample.

### Step 2 — Extract handled types from the frontend

Instantiate each frontend via `get_deterministic_frontend(lang_key)`. Then collect:

- `_build_expr_dispatch().keys()` — if the method exists (context-mode frontend)
- `_build_stmt_dispatch().keys()` — if the method exists
- `_EXPR_DISPATCH.keys()` — fallback for legacy frontends
- `_STMT_DISPATCH.keys()` — fallback for legacy frontends
- `constants.noise_types` and `constants.comment_types` from `_build_constants()` — these are intentionally unhandled but not gaps

All of the above are unioned into `handled_types: set[str]`.

### Step 3 — Diff

```python
gaps = named_grammar_nodes - handled_types
covered = named_grammar_nodes & handled_types
```

No block-reachability classification. No filtering by construct category. All gaps are reported; triaging is the human's job.

### Step 4 — JSON output

Written to stdout (or a `--output FILE` path):

```json
{
  "generated": "2026-04-14",
  "languages": {
    "python": {
      "total_grammar_nodes": 123,
      "handled_count": 42,
      "gap_count": 81,
      "covered": ["assignment", "call", ...],
      "gaps": ["assert_statement", "match_statement", ...]
    },
    ...
  },
  "summary": {
    "total_gap_count": 912,
    "languages_with_gaps": ["python", "java", ...]
  }
}
```

Both `covered` and `gaps` lists are sorted alphabetically.

### Step 5 — Terminal summary

Always printed to stderr (so it doesn't pollute JSON stdout):

```
python    :  42 / 123 handled  (81 gaps)
java      :  55 / 142 handled  (87 gaps)
...
─────────────────────────────────────────
TOTAL     : 912 gaps across 15 languages
```

### CLI interface

```
poetry run python scripts/grammar_coverage_audit.py [--output FILE]
```

- No `--output`: JSON to stdout, summary to stderr.
- `--output FILE`: JSON to file, summary to stdout.

## What is replaced / deleted

`scripts/audit_all_frontends.py` is deleted. It is superseded entirely by this script.

## What this does NOT do

- No runtime SYMBOLIC check (sample-driven, not deterministic).
- No severity classification (P0/P1/P2).
- No filtering of "uninteresting" node types (error recovery, comments, noise) — noise/comment types are excluded via the frontend's `GrammarConstants`, not by the script.

## Verification

Run the script and confirm:
1. All 15 languages produce output with non-zero grammar node counts.
2. Python `handled_count` is greater than 20 (sanity check against the broken old script that showed 0–1).
3. JSON is valid (parseable by `json.loads`).
