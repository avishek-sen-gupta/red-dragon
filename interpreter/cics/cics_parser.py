"""Parse EXEC CICS text into (verb, options) using a Lark PEG grammar.

Each option value is carried as a :class:`CicsOperand`, which records the
literal-vs-data-name distinction STRUCTURALLY (from which grammar production
matched), so downstream consumers never have to re-sniff quote characters.
"""

from __future__ import annotations

from dataclasses import dataclass

from lark import Lark, Transformer
from lark.exceptions import UnexpectedInput

from interpreter.cobol.cobol_expression import ExprNode, FieldRefNode, LiteralNode
from interpreter.cobol.ref_mod import RefModExpr, RefModLiteral, RefModReference


@dataclass(frozen=True)
class CicsOperand:
    """A parsed EXEC CICS option value.

    is_literal=True  -> a quoted string literal (text is the inner content, no quotes).
    is_literal=False -> a bare operand: data-name, subscripted/reference-modified ref,
                        or numeric literal (text preserved verbatim, incl. nested parens).

    ``subscripts`` carries each index as a structured :class:`ExprNode`
    (red-dragon-l445): a bare data-name becomes a ``FieldRefNode``, an unsigned
    integer becomes a ``LiteralNode``. Arithmetic CICS subscripts are out of
    scope for the CICS grammar.
    """

    text: str
    is_literal: bool
    subscripts: tuple[ExprNode, ...] = ()
    ref_mod_start: RefModExpr | None = None
    ref_mod_length: RefModExpr | None = None


# Internal transformer markers for value parts. They carry whether the part came
# from a quoted STRING terminal (literal) or a bare CHARS/nested operand, plus the
# part's text. The `value` rule combines parts into a single CicsOperand.
@dataclass(frozen=True)
class _Part:
    text: str
    is_literal: bool


# Internal marker for a single subscript nested group (no COLON), e.g. TBL(I) or
# TBL(3). Carries the structured index ExprNode (red-dragon-l445). The `value`
# rule collects these into CicsOperand.subscripts.
@dataclass(frozen=True)
class _SubscriptPart:
    expr: ExprNode


# Internal marker for a reference-modification nested group: a base data-name
# followed by ``(start:length)``. Carries the structured start/length so the
# `value` rule can attach them to the resulting CicsOperand.
@dataclass(frozen=True)
class _RefModPart:
    start: RefModExpr
    length: RefModExpr


# Internal transformer marker for a recognized verb. `word` is the (uppercased)
# verb keyword, e.g. "SEND". For a compound-first keyword its optional trailing
# option is carried in `second`; the transformer/post-step decides whether that
# trailing option promotes the verb to a compound like "SEND MAP".
@dataclass(frozen=True)
class _Verb:
    word: str
    second: tuple[str, "CicsOperand | None"] | None


# Grammar for the FULL EXEC CICS command text, envelope included.
#
# The `EXEC CICS ... END-EXEC` wrapper is matched as grammar keyword terminals
# (case-insensitive via the `i` flag) — there is NO regex pre-surgery on the
# input. The command's VERB is recognized as a grammar construct: either a single
# word (READ/WRITE/XCTL/RETURN/...) or one of the small, known set of compound
# verbs (SEND MAP, SEND TEXT, RECEIVE MAP, HANDLE ABEND/CONDITION/AID). The
# compound second word may itself carry a value (e.g. SEND MAP('COSGN0A')); the
# transformer routes such a value into opts under the second word's key, exactly
# as the previous Python stitching did.
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
#
# Compound second words are kept as the generic NAME terminal (so they remain
# usable as ordinary option keys elsewhere); the compound first word is matched
# by a dedicated case-insensitive keyword terminal so the LALR contextual lexer
# can pick the compound verb alternatives at verb position.
_GRAMMAR = r"""
    start: EXEC_CICS command END_EXEC

    command: verb token*
           |                -> empty_command

    verb: SEND_KW second_word    -> compound_verb
        | RECEIVE_KW second_word -> compound_verb
        | HANDLE_KW second_word  -> compound_verb
        | SEND_KW                -> compound_verb_bare
        | RECEIVE_KW             -> compound_verb_bare
        | HANDLE_KW              -> compound_verb_bare
        | NAME "(" value ")"     -> single_verb_valued
        | NAME                   -> single_verb

    // The word following a compound-first keyword, optionally carrying a value.
    second_word: NAME "(" value ")" -> second_option
               | NAME               -> second_flag

    token: NAME "(" value ")" -> option
         | NAME               -> flag

    value: value_part*
    value_part: STRING                       -> vstring
              | CHARS                        -> vchars
              | "(" refmod_side COLON refmod_side ")" -> vrefmod
              | "(" NAME ")"                 -> vnested_name
              | "(" INT ")"                  -> vnested_int
              | "(" value ")"                -> vnested

    // A reference-modification side is an unsigned integer (→ RefModLiteral) or a
    // data-name (→ RefModReference). Anything more complex (arithmetic, LENGTH OF)
    // is out of scope here and will not match this production, leaving the old
    // subscript shape (no COLON ⇒ vnested) untouched.
    refmod_side: INT  -> refmod_int
               | NAME -> refmod_name

    // The envelope is anchored, exactly like the previous regexes:
    // EXEC_CICS only at the START, END_EXEC only at the END of the text. Any
    // inner "EXEC"/"CICS"/"END-EXEC" words (e.g. two CICS commands captured as
    // one block) therefore lex as ordinary NAME flags, preserving the historical
    // first-envelope / last-envelope peeling behavior of the regex implementation.
    EXEC_CICS.3: /\A\s*EXEC\s+CICS\s+/i
    END_EXEC.3: /\s*END-EXEC\s*\Z/i

    SEND_KW.2: "SEND"i
    RECEIVE_KW.2: "RECEIVE"i
    HANDLE_KW.2: "HANDLE"i

    STRING: /'[^']*'|"[^"]*"/
    COLON: ":"
    // INT.2 > NAME.1 so a numeric ref-mod side (e.g. (1:8)) lexes as INT, not NAME.
    INT.2: /[0-9]+/
    NAME.1: /[A-Za-z][A-Za-z0-9-]*/
    CHARS: /[^():'"]+/

    %ignore /\*>[^\n]*/
    %ignore /\s+/
"""

# Compound verbs: compound-first keyword → valid second words.
_COMPOUND_SECONDS: dict[str, frozenset[str]] = {
    "SEND": frozenset({"MAP", "TEXT"}),
    "RECEIVE": frozenset({"MAP"}),
    "HANDLE": frozenset({"ABEND", "CONDITION", "AID"}),
}

_parser = Lark(_GRAMMAR, parser="lalr")


class _Transformer(Transformer):
    def start(self, items: list) -> tuple[str, dict[str, CicsOperand | None]]:
        # items: [EXEC_CICS token, command_result, END_EXEC token]; the envelope
        # terminals are kept (they are named), so pick out the command result.
        return items[1]

    def command(self, items: list) -> tuple[str, dict[str, CicsOperand | None]]:
        verb: _Verb = items[0]
        rest: list[tuple[str, CicsOperand | None]] = items[1:]

        # A compound-first keyword (SEND/RECEIVE/HANDLE) promotes to a compound
        # verb only when its trailing word is a recognized second word. Otherwise
        # the trailing word is an ordinary option/flag of the single-word verb.
        if verb.second is not None:
            second_key, second_val = verb.second
            if second_key in _COMPOUND_SECONDS.get(verb.word, frozenset()):
                compound = f"{verb.word} {second_key}"
                if second_val is not None:
                    # Second word carried a value (e.g. MAP('name')) — keep it.
                    return compound, {second_key: second_val, **dict(rest)}
                # Bare second word — purely part of the verb name.
                return compound, dict(rest)
            # Not a compound: the trailing word is a normal option/flag.
            return verb.word, dict([verb.second, *rest])

        return verb.word, dict(rest)

    def empty_command(self, items: list) -> tuple[str, dict[str, CicsOperand | None]]:
        # `EXEC CICS END-EXEC` with no verb — matches the previous empty-body case.
        return "", {}

    def single_verb(self, items: list) -> _Verb:
        return _Verb(word=str(items[0]).upper(), second=None)

    def single_verb_valued(self, items: list) -> _Verb:
        # First token carried a value (unusual). The previous implementation
        # treated it as a single-word verb and DROPPED the value (it returned
        # dict(tokens[1:])). Preserve that exactly.
        return _Verb(word=str(items[0]).upper(), second=None)

    def compound_verb(self, items: list) -> _Verb:
        # items: [<keyword token>, (second_key, second_val)]
        return _Verb(word=str(items[0]).upper(), second=items[1])

    def compound_verb_bare(self, items: list) -> _Verb:
        return _Verb(word=str(items[0]).upper(), second=None)

    def second_option(self, items: list) -> tuple[str, CicsOperand | None]:
        return (str(items[0]).upper(), items[1])

    def second_flag(self, items: list) -> tuple[str, CicsOperand | None]:
        return (str(items[0]).upper(), None)

    def option(self, items: list) -> tuple[str, CicsOperand | None]:
        key = str(items[0]).upper()
        return (key, items[1])

    def flag(self, items: list) -> tuple[str, CicsOperand | None]:
        return (str(items[0]).upper(), None)

    def value(self, items: list) -> CicsOperand:
        # Reference modification: a bare CHARS base followed by a single
        # (start:length) nested group, e.g. WS-MSG(1:8). The base part is the
        # data-name; the _RefModPart carries the structured start/length. This
        # is distinct from a subscript (a nested group WITHOUT a ':').
        if (
            len(items) == 2
            and isinstance(items[0], _Part)
            and not items[0].is_literal
            and not items[0].text.startswith("(")
            and isinstance(items[1], _RefModPart)
        ):
            return CicsOperand(
                text=items[0].text,
                is_literal=False,
                ref_mod_start=items[1].start,
                ref_mod_length=items[1].length,
            )
        # A string literal is the case of exactly ONE quoted-string part.
        if len(items) == 1 and items[0].is_literal:
            return CicsOperand(text=items[0].text, is_literal=True)
        # Subscripted reference: a leading CHARS base (a _Part, not literal, not a
        # nested group) followed by one or more _SubscriptPart nested groups. Each
        # _SubscriptPart carries a structured index ExprNode (red-dragon-l445).
        if (
            len(items) >= 2
            and isinstance(items[0], _Part)
            and not items[0].is_literal
            and not items[0].text.startswith("(")
            and all(isinstance(p, _SubscriptPart) for p in items[1:])
        ):
            base = items[0].text
            subs = tuple(p.expr for p in items[1:])
            return CicsOperand(text=base, is_literal=False, subscripts=subs)
        # Any other shape (a bare data-name, ref-mod operand built from CHARS +
        # nested parts, or a numeric) is a non-literal operand whose verbatim
        # text is the concatenation of its parts.
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

    def vnested_name(self, items: list) -> _SubscriptPart:
        # A nested group holding a single bare NAME (no COLON) — an ordinary
        # data-name subscript like TBL(I) or PGM(WS-OPTION). The NAME lexes as its
        # own terminal (it shares the value-position lexer with refmod sides), so
        # the index is a structured FieldRefNode (red-dragon-l445).
        return _SubscriptPart(expr=FieldRefNode(name=str(items[0])))

    def vnested_int(self, items: list) -> _SubscriptPart:
        # A nested group holding a single unsigned integer (no COLON) — a numeric
        # subscript like TBL(3). The index is a structured LiteralNode.
        return _SubscriptPart(expr=LiteralNode(value=str(items[0])))

    def vrefmod(self, items: list) -> _RefModPart:
        # items: [start_expr, COLON token, length_expr]; the COLON terminal is
        # named, so the two structured sides are at indices 0 and 2.
        assert len(items) == 3
        return _RefModPart(start=items[0], length=items[2])

    def refmod_int(self, items: list) -> RefModExpr:
        return RefModLiteral(value=str(items[0]))

    def refmod_name(self, items: list) -> RefModExpr:
        return RefModReference(name=str(items[0]))


def parse_exec_cics_text(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
    """Parse 'EXEC CICS VERB OPT(val) FLAG END-EXEC' → (verb, {OPT: CicsOperand, FLAG: None}).

    Each option value is a :class:`CicsOperand` carrying the structural
    literal-vs-data-name distinction; a bare flag maps to ``None``.

    Compound verbs (SEND MAP, RECEIVE MAP, HANDLE ABEND, etc.) are detected and
    their second word is excluded from opts when it is a bare keyword.
    When the second word carries a value (e.g. MAP('COSGN0A')), that value is
    included in opts under the second word's key.
    """
    # Empty / whitespace-only input has no command at all (not even an envelope).
    # The previous implementation returned ("", {}) for this; preserve it. This is
    # the absence-of-input case, not envelope stripping — the EXEC CICS / END-EXEC
    # wrappers themselves are consumed by the grammar.
    if not text.strip():
        return "", {}

    try:
        tree = _parser.parse(text)
    except UnexpectedInput as exc:
        raise ValueError(f"Cannot parse EXEC CICS text: {text!r}") from exc
    verb, opts = _Transformer().transform(tree)
    return verb, opts
