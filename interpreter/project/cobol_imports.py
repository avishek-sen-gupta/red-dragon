# pyright: standard
"""COBOL COPY/CALL import extraction — a light Lark grammar over raw bytes.

A leaf module: COBOL is parsed by ProLeap (not tree-sitter), and COPY/CALL are
recovered from the raw source, so this path shares nothing with the tree-sitter
extractors in interpreter.project.imports. Lifted here so static-analysis
consumers (and the fat imports.extract_imports dispatcher) can use it without
the tree-sitter parser factory. Imports only stdlib + Lark + the import
vocabulary leaf.
"""

from __future__ import annotations

from pathlib import Path

from lark import Lark, Transformer as LarkTransformer

from interpreter.project.import_types import ImportKind, ImportRef

# ── COBOL import extraction (light grammar, no tree-sitter) ──────
#
# STRING is a first-class terminal so any COPY or CALL keyword inside a
# quoted literal is consumed opaquely and never reaches the grammar rules.
# Column-7 comment lines are stripped before the grammar runs because
# %ignore /\s+/ erases positional whitespace, making column-7 anchoring
# impossible inside the tokeniser.
#
# COPY_STMT / CALL_STMT are full-pattern terminals (keyword + horizontal
# whitespace + name/literal) so a bare CALL without a string argument
# (e.g. CALL WS-VAR) falls through to WORD noise instead of causing a
# parse error.

_COBOL_IMPORT_GRAMMAR = r"""
    start: item*
    item: copy_stmt | call_stmt | noise

    copy_stmt: COPY_STMT
    call_stmt: CALL_STMT
    noise:     STRING | WORD | PUNCT

    COPY_STMT.3: /COPY[ \t]+[A-Za-z0-9][\w-]*/i
    CALL_STMT.3: /CALL[ \t]+(?:'[^']*'|"[^"]*")/i
    STRING.2:    /'[^']*'|"[^"]*"/
    WORD.1:      /[A-Za-z0-9][\w-]*/
    PUNCT:       /[^\s'"A-Za-z0-9]+/

    %ignore /\s+/
"""

_cobol_import_parser = Lark(_COBOL_IMPORT_GRAMMAR, parser="lalr")


class _CobolImportTransformer(LarkTransformer):
    def start(self, items: list) -> list[tuple[str, str]]:
        return [item for item in items if item is not None]

    def item(self, items: list) -> tuple[str, str] | None:
        return items[0]

    def copy_stmt(self, items: list) -> tuple[str, str]:
        # COPY_STMT token is e.g. "COPY CUSTOMER-RECORD" — name is the last word
        return ("COPY", str(items[0]).split()[-1])

    def call_stmt(self, items: list) -> tuple[str, str]:
        # CALL_STMT token is e.g. "CALL 'SUBPROG'" — extract between quotes
        raw = str(items[0])
        q = "'" if "'" in raw else '"'
        return ("CALL", raw[raw.index(q) + 1 : raw.rindex(q)])

    def noise(self, _: list) -> None:
        return None


def _strip_cobol_comment_lines(text: str) -> str:
    """Remove COBOL comment lines before grammar tokenisation.

    - Fixed-format: column-7 indicator '*' or '/' (index 6).
    - Free-format: trimmed line starts with '*>'.

    Must run before the grammar because %ignore /\\s+/ strips positional
    whitespace, making column-7 anchoring impossible inside the tokeniser.
    """
    clean: list[str] = []
    for line in text.splitlines():
        if len(line) > 6 and line[6] in ("*", "/"):
            continue
        if line.lstrip().startswith("*>"):
            continue
        clean.append(line)
    return "\n".join(clean)


def extract_cobol_imports(source: bytes, source_file: Path) -> list[ImportRef]:
    """Extract COPY and CALL statements from COBOL source.

    Uses a light Lark grammar so keywords inside string literals are
    consumed as opaque STRING tokens and never produce false imports.
    """
    text = _strip_cobol_comment_lines(source.decode("utf-8", errors="replace"))
    pairs: list[tuple[str, str]] = _CobolImportTransformer().transform(
        _cobol_import_parser.parse(text)
    )
    return [
        ImportRef(
            source_file=source_file,
            module_path=name,
            kind=ImportKind.INCLUDE if kind == "COPY" else ImportKind.REQUIRE,
        )
        for kind, name in pairs
    ]
