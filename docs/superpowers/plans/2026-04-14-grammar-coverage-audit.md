# Grammar Coverage Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `scripts/audit_all_frontends.py` with a deterministic grammar-enumeration script that diffs all 15 language grammars against their dispatch tables and emits JSON + a terminal summary.

**Architecture:** Enumerate every named node type in each tree-sitter grammar via the Language API (no source samples). Extract handled types by calling `_build_expr_dispatch()` / `_build_stmt_dispatch()` (context-mode) or reading `_EXPR_DISPATCH` / `_STMT_DISPATCH` (legacy). Diff and emit JSON to stdout plus summary to stderr.

**Tech Stack:** `tree_sitter_language_pack`, `interpreter.frontends`, `interpreter.constants.Language`, Python `argparse`, `json`, `datetime`.

---

### Task 1: Write the new grammar coverage audit script

**Files:**
- Create: `scripts/grammar_coverage_audit.py`

- [ ] **Step 1: Create the script**

```python
"""Deterministic grammar coverage audit across all 15 language frontends.

Enumerates every named node type from each tree-sitter grammar and diffs
it against the union of types handled by the corresponding frontend's
dispatch tables, noise types, and comment types.

Usage:
    poetry run python scripts/grammar_coverage_audit.py
    poetry run python scripts/grammar_coverage_audit.py --output results.json

With no --output flag: JSON to stdout, summary to stderr.
With --output FILE: JSON to file, summary to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date

import tree_sitter_language_pack

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend

# Languages with deterministic frontends (COBOL is excluded — no deterministic frontend).
AUDIT_LANGUAGES: tuple[Language, ...] = (
    Language.PYTHON,
    Language.JAVA,
    Language.JAVASCRIPT,
    Language.TYPESCRIPT,
    Language.CSHARP,
    Language.KOTLIN,
    Language.SCALA,
    Language.GO,
    Language.RUST,
    Language.C,
    Language.CPP,
    Language.RUBY,
    Language.PHP,
    Language.LUA,
    Language.PASCAL,
)

# Language enum values are tree-sitter language pack names (Language is a StrEnum).
# Exception: no overrides needed — Language.CSHARP == "csharp" matches the pack name.


@dataclass(frozen=True)
class LanguageResult:
    language: str
    total_grammar_nodes: int
    handled_count: int
    gap_count: int
    covered: list[str]
    gaps: list[str]


def enumerate_grammar_nodes(ts_language_name: str) -> set[str]:
    """Return all named node type strings defined in the grammar."""
    lang = tree_sitter_language_pack.get_language(ts_language_name)
    return {
        lang.node_kind_for_id(i)
        for i in range(lang.node_kind_count)
        if lang.node_kind_is_named(i)
    }


def extract_handled_types(language: Language) -> set[str]:
    """Return the union of all node type strings a frontend explicitly handles.

    Covers context-mode frontends (_build_expr_dispatch / _build_stmt_dispatch)
    and legacy frontends (_EXPR_DISPATCH / _STMT_DISPATCH), plus noise and
    comment types from GrammarConstants.
    """
    frontend = get_deterministic_frontend(language)
    handled: set[str] = set()

    # Context-mode dispatch (preferred)
    if hasattr(frontend, "_build_expr_dispatch"):
        handled |= set(frontend._build_expr_dispatch().keys())
    if hasattr(frontend, "_build_stmt_dispatch"):
        handled |= set(frontend._build_stmt_dispatch().keys())

    # Legacy dispatch fallback
    if hasattr(frontend, "_EXPR_DISPATCH"):
        handled |= set(frontend._EXPR_DISPATCH.keys())
    if hasattr(frontend, "_STMT_DISPATCH"):
        handled |= set(frontend._STMT_DISPATCH.keys())

    # GrammarConstants: noise and comment types are intentionally ignored, not gaps
    if hasattr(frontend, "_build_constants"):
        constants = frontend._build_constants()
        handled |= constants.noise_types
        handled |= constants.comment_types

    return handled


def audit_language(language: Language) -> LanguageResult:
    """Run the grammar coverage audit for a single language."""
    grammar_nodes = enumerate_grammar_nodes(str(language))
    handled = extract_handled_types(language)

    covered = sorted(grammar_nodes & handled)
    gaps = sorted(grammar_nodes - handled)

    return LanguageResult(
        language=str(language),
        total_grammar_nodes=len(grammar_nodes),
        handled_count=len(covered),
        gap_count=len(gaps),
        covered=covered,
        gaps=gaps,
    )


def build_json(results: list[LanguageResult]) -> dict:
    """Build the full JSON output structure."""
    languages_json = {}
    for r in results:
        languages_json[r.language] = {
            "total_grammar_nodes": r.total_grammar_nodes,
            "handled_count": r.handled_count,
            "gap_count": r.gap_count,
            "covered": r.covered,
            "gaps": r.gaps,
        }

    total_gaps = sum(r.gap_count for r in results)
    languages_with_gaps = [r.language for r in results if r.gap_count > 0]

    return {
        "generated": str(date.today()),
        "languages": languages_json,
        "summary": {
            "total_gap_count": total_gaps,
            "languages_with_gaps": languages_with_gaps,
        },
    }


def print_summary(results: list[LanguageResult], output_stream) -> None:
    """Print a human-readable summary table."""
    col_width = max(len(r.language) for r in results) + 2
    for r in results:
        label = f"{r.language:<{col_width}}"
        print(
            f"  {label}: {r.handled_count:4d} / {r.total_grammar_nodes:4d} handled"
            f"  ({r.gap_count} gaps)",
            file=output_stream,
        )

    total_gaps = sum(r.gap_count for r in results)
    print("  " + "─" * 50, file=output_stream)
    print(
        f"  TOTAL: {total_gaps} gaps across {len(results)} languages",
        file=output_stream,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic grammar coverage audit for all RedDragon frontends."
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON to FILE instead of stdout (summary then goes to stdout).",
    )
    args = parser.parse_args()

    results: list[LanguageResult] = []
    for language in AUDIT_LANGUAGES:
        print(f"Auditing {language}...", file=sys.stderr)
        result = audit_language(language)
        results.append(result)

    payload = build_json(results)
    json_text = json.dumps(payload, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(json_text)
            f.write("\n")
        summary_stream = sys.stdout
    else:
        print(json_text)
        summary_stream = sys.stderr

    print("", file=summary_stream)
    print_summary(results, summary_stream)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script and verify basic output**

```bash
poetry run python scripts/grammar_coverage_audit.py --output /tmp/audit_out.json 2>&1
```

Expected: progress lines like `Auditing python...` for all 15 languages, then a summary table. No tracebacks.

- [ ] **Step 3: Validate JSON and sanity-check counts**

```bash
poetry run python -c "
import json
with open('/tmp/audit_out.json') as f:
    d = json.load(f)
py = d['languages']['python']
print('Python handled:', py['handled_count'], '/ total:', py['total_grammar_nodes'])
assert py['handled_count'] > 20, f'Expected >20 handled for Python, got {py[\"handled_count\"]}'
assert len(d['languages']) == 15, f'Expected 15 languages, got {len(d[\"languages\"])}'
print('All sanity checks pass.')
print('Total gaps:', d['summary']['total_gap_count'])
"
```

Expected output:
```
Python handled: <N> / total: <M>   (N should be > 20)
All sanity checks pass.
Total gaps: <some large number>
```

- [ ] **Step 4: Clean up temp file**

```bash
rm /tmp/audit_out.json
```

---

### Task 2: Delete the old broken script and commit

**Files:**
- Delete: `scripts/audit_all_frontends.py`

- [ ] **Step 1: Delete the old script**

```bash
git rm scripts/audit_all_frontends.py
```

- [ ] **Step 2: Stage the new script and commit**

```bash
git add scripts/grammar_coverage_audit.py
git commit -m "feat(audit): replace broken audit_all_frontends with deterministic grammar coverage audit

New script enumerates all named tree-sitter grammar node types and diffs
against frontend dispatch tables. Covers all 15 languages, handles both
context-mode and legacy frontends, outputs JSON + terminal summary.

Deletes scripts/audit_all_frontends.py which only covered 7/15 languages
and failed to read context-mode dispatch tables.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
