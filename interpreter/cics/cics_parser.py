"""Parse EXEC CICS text into (verb, options) using a Lark PEG grammar.

Each option value is carried as a :class:`CicsOperand`, which records the
literal-vs-data-name distinction STRUCTURALLY (from which grammar production
matched), so downstream consumers never have to re-sniff quote characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lark import Lark, Transformer
from lark.exceptions import UnexpectedInput


@dataclass(frozen=True)
class CicsOperand:
    """A parsed EXEC CICS option value.

    is_literal=True  -> a quoted string literal (text is the inner content, no quotes).
    is_literal=False -> a bare operand: data-name, subscripted/reference-modified ref,
                        or numeric literal (text preserved verbatim, incl. nested parens).
    """

    text: str
    is_literal: bool


# Internal transformer markers for value parts. They carry whether the part came
# from a quoted STRING terminal (literal) or a bare CHARS/nested operand, plus the
# part's text. The `value` rule combines parts into a single CicsOperand.
@dataclass(frozen=True)
class _Part:
    text: str
    is_literal: bool


# Grammar for the CICS command body (after stripping EXEC CICS / END-EXEC wrappers).
# Each token is either KEYWORD(value) or a bare KEYWORD flag.
#
# An option value can itself contain balanced, nested parentheses — e.g. a
# subscripted data-name PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION)) or a
# reference-modified operand FROM(WS-MSG(1:8)). Nesting is handled structurally
# by the recursive `value`/`value_part` rules (the contextual LALR lexer scopes
# CHARS/STRING/parens to value position) — NOT by regex paren-balancing.
#
# The STRING vs CHARS distinction in the grammar is the SOLE source of the
# literal-vs-data-name flag carried by CicsOperand; it is never re-derived by
# inspecting quote characters downstream.
_BODY_GRAMMAR = r"""
    start: token+

    token: NAME "(" value ")" -> option
         | NAME               -> flag

    value: value_part*
    value_part: STRING           -> vstring
              | CHARS            -> vchars
              | "(" value ")"    -> vnested

    STRING: /'[^']*'|"[^"]*"/
    CHARS: /[^()'"]+/
    NAME: /[A-Za-z][A-Za-z0-9-]*/

    %ignore /\s+/
"""

# Compound verbs: first word → valid second words
_COMPOUND: dict[str, frozenset[str]] = {
    "SEND": frozenset({"MAP", "TEXT"}),
    "RECEIVE": frozenset({"MAP"}),
    "HANDLE": frozenset({"ABEND", "CONDITION", "AID"}),
}

_EXEC_CICS_RE = re.compile(r"^\s*EXEC\s+CICS\s+", re.IGNORECASE)
_END_EXEC_RE = re.compile(r"\s*END-EXEC\s*$", re.IGNORECASE)

_body_parser = Lark(_BODY_GRAMMAR, parser="lalr")


class _Transformer(Transformer):
    def start(self, items: list) -> list[tuple[str, CicsOperand | None]]:
        return items

    def option(self, items: list) -> tuple[str, CicsOperand | None]:
        key = str(items[0]).upper()
        return (key, items[1])

    def flag(self, items: list) -> tuple[str, CicsOperand | None]:
        return (str(items[0]).upper(), None)

    def value(self, items: list[_Part]) -> CicsOperand:
        # A string literal is the case of exactly ONE quoted-string part.
        if len(items) == 1 and items[0].is_literal:
            return CicsOperand(text=items[0].text, is_literal=True)
        # Any other shape (a bare data-name, subscripted/ref-mod operand built
        # from CHARS + nested parts, or a numeric) is a non-literal operand whose
        # verbatim text is the concatenation of its parts.
        return CicsOperand(text="".join(p.text for p in items), is_literal=False)

    def vstring(self, items: list) -> _Part:
        # The STRING terminal's regex is /'[^']*'|"[^"]*"/, so the token is
        # GUARANTEED to have matching surrounding quotes — unwrap structurally
        # (this is justified by the terminal, NOT ad-hoc quote stripping).
        token = str(items[0])
        return _Part(text=token[1:-1], is_literal=True)

    def vchars(self, items: list) -> _Part:
        return _Part(text=str(items[0]), is_literal=False)

    def vnested(self, items: list) -> _Part:
        inner = items[0].text if items else ""
        return _Part(text=f"({inner})", is_literal=False)


def parse_exec_cics_text(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
    """Parse 'EXEC CICS VERB OPT(val) FLAG END-EXEC' → (verb, {OPT: CicsOperand, FLAG: None}).

    Each option value is a :class:`CicsOperand` carrying the structural
    literal-vs-data-name distinction; a bare flag maps to ``None``.

    Compound verbs (SEND MAP, RECEIVE MAP, HANDLE ABEND, etc.) are detected and
    their second word is excluded from opts when it is a bare keyword.
    When the second word carries a value (e.g. MAP('COSGN0A')), that value is
    included in opts under the second word's key.
    """
    body = _EXEC_CICS_RE.sub("", text.strip())
    body = _END_EXEC_RE.sub("", body).strip()

    if not body:
        return "", {}

    try:
        tree = _body_parser.parse(body)
    except UnexpectedInput as exc:
        raise ValueError(f"Cannot parse EXEC CICS text: {body!r}") from exc
    tokens: list[tuple[str, CicsOperand | None]] = _Transformer().transform(tree)

    first_key, first_val = tokens[0]

    # Single-word verb (first token has a value — unusual but safe)
    if first_val is not None:
        return first_key, dict(tokens[1:])

    # Check for compound verb
    if first_key in _COMPOUND and len(tokens) > 1:
        second_key, second_val = tokens[1]
        if second_key in _COMPOUND[first_key]:
            verb = f"{first_key} {second_key}"
            rest = list(tokens[2:])
            if second_val is not None:
                # Second word carried a value (e.g. MAP('name')) — include it
                opts = {second_key: second_val, **dict(rest)}
            else:
                # Second word was bare — it is purely part of the verb name
                opts = dict(rest)
            return verb, opts

    return first_key, dict(tokens[1:])
