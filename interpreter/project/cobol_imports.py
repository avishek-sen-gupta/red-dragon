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

import re
from collections.abc import Sequence
from functools import reduce
from itertools import accumulate, groupby
from operator import itemgetter
from pathlib import Path

from lark import Lark
from lark import Transformer as LarkTransformer

from interpreter.project.import_types import ImportKind, ImportRef

# ── COBOL import extraction (light grammar, no tree-sitter) ──────
#
# STRING is a first-class terminal so any COPY or CALL keyword inside a
# quoted literal is consumed opaquely and never reaches the grammar rules.
# Source is folded and comment-stripped before the grammar runs, because
# %ignore /\s+/ erases positional whitespace, making column-7 anchoring
# impossible inside the tokeniser.
#
# COPY_STMT / CALL_STMT are full-pattern terminals (keyword + horizontal
# whitespace + name/literal) so a bare CALL without a string argument
# (e.g. CALL WS-VAR) falls through to WORD noise instead of causing a
# parse error.
#
# Every literal pattern excludes \n, and PUNCT admits a quote. Together those
# make the grammar tolerant of source folding cannot repair. A literal terminal
# that matched \n would pair an unterminated quote with the NEXT line's quote;
# the mispairing then cascades until no terminal matches at all, and the parse
# raises, taking every COPY in the rest of the file with it. That cost 328 of
# 3779 members on one corpus -- and in build_graph a member that raises is a
# member dropped from the graph, since the failure path returns before the
# program node is written. Excluding \n confines the damage to one line, and
# PUNCT gives the orphaned quote somewhere to go instead of killing the lex.
# This mirrors ProLeap's CobolPreprocessor.g4, whose STRINGLITERAL likewise
# excludes newlines and whose catch-all TEXT absorbs the leftover character.

_COBOL_IMPORT_GRAMMAR = r"""
    start: item*
    item: copy_stmt | call_stmt | noise

    copy_stmt: COPY_STMT
    call_stmt: CALL_STMT
    noise:     STRING | WORD | PUNCT

    COPY_STMT.3: /COPY[ \t]+[A-Za-z0-9][\w-]*/i
    CALL_STMT.3: /CALL[ \t]+(?:'(?:[^'\n]|'')*'|"(?:[^"\n]|"")*")/i
    STRING.2:    /'(?:[^'\n]|'')*'|"(?:[^"\n]|"")*"/
    WORD.1:      /[A-Za-z0-9][\w-]*/
    PUNCT:       /[^\sA-Za-z0-9]+/

    %ignore /\s+/
"""

_cobol_import_parser = Lark(_COBOL_IMPORT_GRAMMAR, parser="lalr")


_Ref = tuple[str, str, int]

# What ``noise`` returns: not a ref, and an empty tuple rather than None so the
# caller filters on emptiness instead of an identity check.
_NOT_A_REF: tuple[()] = ()


class _CobolImportTransformer(LarkTransformer):
    def start(self, items: Sequence) -> tuple[_Ref, ...]:
        return tuple(item for item in items if item)

    def item(self, items: Sequence) -> _Ref | tuple[()]:
        return items[0]

    def copy_stmt(self, items: Sequence) -> _Ref:
        # COPY_STMT token is e.g. "COPY CUSTOMER-RECORD" — name is the last word
        return ("COPY", str(items[0]).split()[-1], items[0].line)

    def call_stmt(self, items: Sequence) -> _Ref:
        # CALL_STMT token is e.g. "CALL 'SUBPROG'" — extract between quotes
        raw = str(items[0])
        quote = "'" if "'" in raw else '"'
        return ("CALL", raw[raw.index(quote) + 1 : raw.rindex(quote)], items[0].line)

    def noise(self, _: Sequence) -> tuple[()]:
        return _NOT_A_REF


# Fixed-format reference format, 0-based: 0-5 sequence number, 6 indicator,
# 7-71 areas A and B, 72-79 identification. Only areas A and B are program text;
# a sequence number is data and the identification area is a stamp, so scanning
# either invents COPY/CALL statements out of things that are not code.
#
# Fixed format is not an assumption here, it is what the corpus is: no caller
# sets the bridge's source format flag, so it always takes its FIXED default, and
# source_text decodes members as fixed-format 8-bit text. Free-format source
# would need a corpus config field and a bridge flag before it reached here.
_INDICATOR = 6
_PROGRAM_TEXT = slice(7, 72)


def _is_comment(line: str) -> bool:
    """Fixed-format column-7 '*' or '/', or a free-format '*>' line."""
    if len(line) > _INDICATOR and line[_INDICATOR] in ("*", "/"):
        return True
    return line.lstrip().startswith("*>")


# A literal that is opened and closed on one line. Doubled quotes are matched
# inside it, so removing every match leaves at most the quote that opens a
# literal nothing closes -- which is the only thing _open_quote is asked about.
_COMPLETE_LITERAL = re.compile(r"'(?:[^'\n]|'')*'|\"(?:[^\"\n]|\"\")*\"")


def _open_quote(text: str) -> str:
    """The quote character ``text`` leaves unclosed, or '' when it closes them all.

    A doubled quote is an escaped quote, not a terminator. Reading '' as the end
    of a literal makes the rest of a continued literal look like program text,
    which is how prose becomes a COPY statement.
    """
    remainder = _COMPLETE_LITERAL.sub("", text)
    unclosed = tuple(char for char in remainder if char in "'\"")
    return unclosed[0] if unclosed else ""


def _is_continuation(line: str) -> bool:
    """Whether ``line`` continues the statement above it, per the indicator column."""
    return line[_INDICATOR : _INDICATOR + 1] == "-"


def _resumed(folded: str, line: str) -> str:
    """What ``line`` contributes to the statement it continues.

    Area B re-opens an unclosed literal with a quote that pairs with nothing: it
    is a resume marker, not a character of the literal, so it is dropped. A quote
    of the other kind is data inside the literal and is kept.
    """
    resumed = line[_PROGRAM_TEXT].lstrip()
    quote = _open_quote(folded)
    return resumed[1:] if quote and resumed[:1] == quote else resumed


def _splice(folded: str, line: str) -> str:
    """Append a continuation's contribution with no space between, as the standard
    specifies -- a space would be a different program, and is why continuation is
    only ever used mid-token."""
    return folded + _resumed(folded, line)


def _statement_lines(text: str) -> tuple[tuple[int, str], ...]:
    """Numbered source lines that carry program text.

    Comment lines are dropped rather than emptied, because an empty line would
    become a fold target: a comment is legal between a literal's first line and
    its continuation, and the continuation must attach to the line it continues,
    not to the comment that happens to sit between them.
    """
    return tuple(
        (number, line)
        for number, line in enumerate(text.splitlines(), 1)
        if not _is_comment(line)
    )


def _statements(text: str) -> tuple[tuple[tuple[int, str], ...], ...]:
    """``_statement_lines`` grouped into one group per statement.

    The group index only advances on a line that is not a continuation, so a run
    of continuations lands in the group of the line it continues. A continuation
    first in the file continues nothing and starts its own group.
    """
    lines = _statement_lines(text)
    starts = accumulate(
        0 if index and _is_continuation(line) else 1
        for index, (_, line) in enumerate(lines)
    )
    return tuple(
        tuple(line for _, line in group)
        for _, group in groupby(zip(starts, lines), itemgetter(0))
    )


def _fold_group(group: Sequence[tuple[int, str]]) -> str:
    """One statement's lines folded into one line of program text."""
    (_, head), *rest = group
    return reduce(_splice, (line for _, line in rest), head[_PROGRAM_TEXT])


def _start_line(group: Sequence[tuple[int, str]]) -> int:
    """The source line a statement's group of lines starts on."""
    return group[0][0]


def _fold_continuations(text: str) -> tuple[str, tuple[int, ...]]:
    """Join fixed-format continuation lines; drop comment lines.

    Returns the folded text and, per folded line, the source line it starts on.
    Folding joins lines, so a token's position in the folded text is no longer
    its position in the file; without the map every ref after the first
    continuation would be reported against the wrong line.
    """
    statements = _statements(text)
    return (
        "\n".join(map(_fold_group, statements)),
        tuple(map(_start_line, statements)),
    )


def extract_cobol_imports(source: bytes, source_file: Path) -> list[ImportRef]:
    """Extract COPY and CALL statements from COBOL source.

    Uses a light Lark grammar so keywords inside string literals are
    consumed as opaque STRING tokens and never produce false imports.
    """
    text, origins = _fold_continuations(source.decode("utf-8", errors="replace"))
    found: tuple[_Ref, ...] = _CobolImportTransformer().transform(
        _cobol_import_parser.parse(text)
    )
    return [
        ImportRef(
            source_file=source_file,
            module_path=name,
            kind=ImportKind.INCLUDE if kind == "COPY" else ImportKind.REQUIRE,
            line=origins[line - 1],
        )
        for kind, name, line in found
    ]
