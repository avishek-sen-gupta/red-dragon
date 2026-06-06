"""Parse EXEC CICS text into (verb, options) using a Lark PEG grammar."""

from __future__ import annotations

import re

from lark import Lark, Transformer

# Grammar for the CICS command body (after stripping EXEC CICS / END-EXEC wrappers).
# Each token is either KEYWORD(value) or a bare KEYWORD flag.
_BODY_GRAMMAR = r"""
    start: token+

    token: NAME "(" value ")" -> option
         | NAME               -> flag

    value: /[^)]+/

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

_body_parser = Lark(_BODY_GRAMMAR, parser="earley")


class _Transformer(Transformer):
    def start(self, items: list) -> list[tuple[str, str | None]]:
        return items

    def option(self, items: list) -> tuple[str, str | None]:
        key = str(items[0]).upper()
        val = str(items[1]).strip().strip("'\"")
        return (key, val)

    def flag(self, items: list) -> tuple[str, str | None]:
        return (str(items[0]).upper(), None)

    def value(self, items: list) -> str:
        return str(items[0])


def parse_exec_cics_text(text: str) -> tuple[str, dict[str, str | None]]:
    """Parse 'EXEC CICS VERB OPT(val) FLAG END-EXEC' → (verb, {OPT: val, FLAG: None}).

    Compound verbs (SEND MAP, RECEIVE MAP, HANDLE ABEND, etc.) are detected and
    their second word is excluded from opts when it is a bare keyword.
    When the second word carries a value (e.g. MAP('COSGN0A')), that value is
    included in opts under the second word's key.
    """
    body = _EXEC_CICS_RE.sub("", text.strip())
    body = _END_EXEC_RE.sub("", body).strip()

    if not body:
        return "", {}

    tree = _body_parser.parse(body)
    tokens: list[tuple[str, str | None]] = _Transformer().transform(tree)

    if not tokens:
        return "", {}

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
