"""Semantic analysis of a COBOL PICTURE parse tree.

The grammar in picture.lark decides the data *category*. Everything the spec
states that is not context-free lives here: sizes, digit counts, scale, and the
validations that depend on a repeat count or on a run's length.

Spec references are to IBM Enterprise COBOL for z/OS 6.4 Language Reference
(igy6lr40.pdf).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from lark import Lark, Token, Tree

_TEMPLATE = (Path(__file__).with_name("picture.lark")).read_text(encoding="utf-8")

# Table 12, p. 208-210: "The heading Size indicates how the item is counted in
# determining the number of character positions in the item."  Values are
# (character positions, digit positions) per occurrence.  The entries that are
# not constant -- cs, and any symbol inside a floating run -- are handled in
# _walk instead.
_SIZE = {
    "A": (1, 0),  # "Each 'A' is counted as one character position"
    "X": (1, 0),
    "B": (1, 0),
    "0": (1, 0),
    "/": (1, 0),
    ",": (1, 0),
    ".": (1, 0),  # "Each period is counted as one character position"
    "9": (1, 1),  # "Each nine specifies one decimal digit"
    "Z": (1, 1),  # "A leading numeric character position"
    "*": (1, 1),  # "A check protect symbol: a leading numeric character position"
    "P": (0, 1),  # "Not counted in the size of the data item. Scaling position
    #                characters are counted in determining the maximum number of
    #                digit positions"
    "V": (0, 0),  # "Not counted in the size of the elementary item."
    "S": (0, 0),  # "Not counted ... unless an associated SIGN clause specifies
    #                the SEPARATE CHARACTER phrase" -- see sign_separate below.
    "E": (1, 0),
    "CR": (2, 0),  # "Each character used in the editing sign symbol is counted"
    "DB": (2, 0),
    "+": (1, 0),
    "-": (1, 0),
}

_POSITION_RULES = {
    "a_pos": "A",
    "x_pos": "X",
    "nine_pos": "9",
    "b_pos": "B",
    "zero_pos": "0",
    "slash_pos": "/",
    "comma_pos": ",",
    "p_pos": "P",
    "z_pos": "Z",
    "star_pos": "*",
    "cs_pos": "cs",
    "plus_pos": "+",
    "minus_pos": "-",
}

# Symbols the grammar reaches as bare terminals rather than through a *_pos
# rule, so they carry no repeat count: S and V in a numeric picture, E and the
# two exponent nines in an external floating-point picture, the decimal point,
# and the two-character sign symbols. PLUS/MINUS/COMMA are deliberately absent:
# they are always reached through plus_pos/minus_pos/comma_pos, which do carry a
# count, and listing them here would double-count.
_BARE_TOKENS = {
    "SYM_S": "S",
    "SYM_V": "V",
    "SYM_E": "E",
    "CR": "CR",
    "DB": "DB",
    "NINE": "9",
    "DOT": ".",
}

# A run rule maps to the symbol it repeats. cs/+/- are *insertion* runs: the
# leftmost symbol is the insertion character and only the remaining ones are
# digit positions ("The second leftmost floating insertion symbol in the
# character-string represents the leftmost limit at which numeric data can
# appear", p. 223). Z/* are *replacement* runs: every symbol is itself "a
# leading numeric character position" (Table 12), so all of them count.
_INSERTION_RUNS = {"cs_run": "cs", "plus_float": "+", "minus_float": "-"}
_REPLACEMENT_RUNS = {"z_run": "Z", "star_run": "*"}


@dataclass(frozen=True)
class Atom:
    """One picture symbol with its repeat count and its run context."""

    sym: str
    count: int
    run: int | None  # index into the run list, or None
    first_in_run: bool
    char: str  # the source character, for currency-symbol identity
    mantissa: bool = False  # inside an external floating-point mantissa


@dataclass(frozen=True)
class Run:
    kind: str  # "cs" | "+" | "-" | "Z" | "*"
    length: int  # total repeat count across the run's symbols

    @property
    def floating(self) -> bool:
        """True when this is floating insertion / zero suppression proper.

        "Floating insertion editing is specified by using a string of at least
        two of the allowable floating insertion symbols" (p. 222). A single cs,
        + or - is fixed insertion instead. A Z/* run of one is already
        suppression: "a string of one or more of the allowable symbols" (p. 224).
        """
        return self.length >= 2 if self.kind in ("cs", "+", "-") else True


@dataclass(frozen=True)
class PictureAnalysis:
    category: str
    char_positions: int  # size of the item, in character positions
    digit_positions: int
    # P positions, which are digit positions that occupy no storage. Reported
    # separately because a USAGE DISPLAY item stores one byte per character
    # position, so digit_positions - scaling_positions is what its bytes hold,
    # while COMP-3 and binary storage covers all of digit_positions.
    scaling_positions: int
    scale: int  # digit positions to the right of the (assumed) decimal point
    signed: bool
    run: Run | None
    errors: tuple[str, ...]


def build_parser(
    currency_symbols: str = "$",
    decimal_point_is_comma: bool = False,
) -> Lark:
    """Instantiate the grammar for one compilation unit's SPECIAL-NAMES.

    currency_symbols holds the PICTURE-clause currency symbols in effect --
    "$" unless CURRENCY SIGN clauses or the CURRENCY compiler option say
    otherwise (p. 212). Several are legal: "The SPECIAL-NAMES paragraph can
    contain multiple CURRENCY SIGN clauses. Each CURRENCY SIGN clause must
    specify a different currency symbol" (p. 129).

    decimal_point_is_comma reflects the DECIMAL-POINT IS COMMA clause, which
    "exchanges the functions of the period and the comma in PICTURE
    character-strings" (p. 130).
    """
    if not currency_symbols:
        raise ValueError("at least one currency symbol is required")
    if len(set(currency_symbols)) != len(currency_symbols):
        # "Each CURRENCY SIGN clause must specify a different currency symbol"
        # (p. 129).
        raise ValueError(f"duplicate currency symbol in {currency_symbols!r}")
    for ch in currency_symbols:
        _check_currency_symbol(ch)
    point, group = (",", ".") if decimal_point_is_comma else (".", ",")
    grammar = (
        _TEMPLATE.replace("%%DOT%%", _literal(point))
        .replace("%%COMMA%%", _literal(group))
        .replace("%%CS%%", " | ".join(_literal(c) for c in currency_symbols))
    )
    return Lark(grammar, parser="earley", ambiguity="explicit")


# "literal-7 must be an alphanumeric literal consisting of one single-byte
# character. literal-7 must not contain any of the following digits or
# characters: a figurative constant; digits 0 through 9; alphabetic characters
# A, B, C, D, E, G, N, P, R, S, U, V, X, Z, their lowercase equivalents, or the
# space; special characters + - , . * / ; ( ) " = '" (p. 129).
#
# That list is exactly the set of characters this grammar already uses for other
# picture symbols, which is why substituting a legal currency symbol can never
# make the grammar ambiguous. Rejecting an illegal one here keeps that invariant
# from being broken silently. Grouped below as the spec groups them: digits, the
# barred letters, their lowercase equivalents, the space, the special characters.
_CURRENCY_BARRED = frozenset(
    "0123456789" + "ABCDEGNPRSUVXZ" + "abcdegnprsuvxz" + " " + "+-,.*/;()\"='"
)


def _check_currency_symbol(ch: str) -> None:
    if len(ch) != 1:
        raise ValueError(f"currency symbol must be one character: {ch!r}")
    if ch in _CURRENCY_BARRED:
        raise ValueError(f"{ch!r} cannot be used as a currency symbol (p. 129)")


def _literal(ch: str) -> str:
    return '"' + ch.replace("\\", "\\\\").replace('"', '\\"') + '"'


def analyse(
    tree: Tree,
    currency_values: Mapping[str, str] | None = None,
    sign_separate: bool = False,
    blank_when_zero: bool = False,
    max_digits: int = 18,
) -> PictureAnalysis:
    """Reduce a picture parse tree to sizes, counts and rule violations.

    currency_values maps each currency symbol to its currency sign *value*,
    which is what determines size: "The first occurrence of a currency symbol
    adds the number of characters in the currency sign value to the size of the
    data item. Each subsequent occurrence adds one character position"
    (Table 12, p. 210). Without a PICTURE SYMBOL phrase the symbol and the value
    are the same single character (p. 129), which is the default here.

    max_digits is 18 under ARITH(COMPAT) and 31 under ARITH(EXTEND) (p. 217).
    """
    currency_values = dict(currency_values or {})
    category = _category(tree)
    atoms, runs = _walk(tree)
    errors: list[str] = []

    chars = 0
    digits = 0
    digits_before_point = None
    seen_cs = False
    cs_chars = set()
    # An external floating-point picture's digit count and scale describe its
    # mantissa; the exponent is always "the symbol 99" (p. 215) and its two
    # digits are not part of the value's precision.
    mantissa_digits = 0
    mantissa_before_point = None

    for atom in atoms:
        if atom.sym == "cs":
            cs_chars.add(atom.char)
            value = currency_values.get(atom.char, atom.char)
            # First occurrence contributes the whole sign value, the rest one
            # character each (Table 12, p. 210).
            if seen_cs:
                chars += atom.count
            else:
                chars += len(value) + atom.count - 1
                seen_cs = True
            contributed = _run_digits(atom)
        else:
            char_size, digit_size = _SIZE[atom.sym]
            if atom.sym == "S" and sign_separate:
                char_size = 1
            if atom.sym in ("+", "-") and atom.run is not None:
                # An insertion run's leftmost symbol is the insertion character,
                # not a digit position. Z/* runs fall through to the Table 12
                # sizes, where every symbol is already "a leading numeric
                # character position".
                contributed = _run_digits(atom)
            else:
                contributed = digit_size * atom.count
            chars += char_size * atom.count

        digits += contributed
        if atom.mantissa:
            mantissa_digits += contributed

        if atom.sym in (".", "V"):
            if digits_before_point is None:
                digits_before_point = digits
            if atom.mantissa and mantissa_before_point is None:
                mantissa_before_point = mantissa_digits

    signed = any(a.sym in ("S", "+", "-", "CR", "DB") for a in atoms)

    if category == "external_float":
        digits = mantissa_digits
        digits_before_point = mantissa_before_point
    if digits_before_point is None:
        digits_before_point = _implied_point(atoms, digits)
    scale = digits - digits_before_point

    if blank_when_zero and category == "numeric":
        # "Either the BLANK WHEN ZERO clause must be specified for the item, or
        # the string must contain at least one of the following symbols: B / Z 0
        # , . * + - CR DB cs" (p. 218). BLANK WHEN ZERO is a clause of the data
        # description entry, so the grammar cannot see it; a picture that is
        # numeric on its own becomes numeric-edited once it is present.
        category = "numeric_edited"

    errors.extend(
        _validate(
            category=category,
            atoms=atoms,
            runs=runs,
            chars=chars,
            digits=digits,
            cs_chars=cs_chars,
            max_digits=max_digits,
        )
    )
    return PictureAnalysis(
        category=category,
        char_positions=chars,
        digit_positions=digits,
        scaling_positions=sum(a.count for a in atoms if a.sym == "P"),
        scale=scale,
        signed=signed,
        run=runs[0] if runs else None,
        errors=tuple(errors),
    )


def _category(tree: Tree) -> str:
    for child in tree.children:
        if isinstance(child, Tree):
            return str(child.data)
    raise ValueError("picture tree has no category")


def _run_digits(atom: Atom) -> int:
    """Digit positions contributed by one symbol of an insertion run.

    The leftmost symbol of a cs/+/- run is the insertion character and is not a
    digit position; every later one is. Counting per symbol rather than per run
    keeps this right when a decimal point sits inside the run ("$$.$$").
    """
    if atom.first_in_run:
        return atom.count - 1
    return atom.count


def _implied_point(atoms: list[Atom], digits: int) -> int:
    """Digit positions left of the point when no . or V is written.

    "The symbol P specifies a scaling position and implies an assumed decimal
    point (to the left of the Ps if the Ps are leftmost PICTURE characters; to
    the right of the Ps if the Ps are rightmost PICTURE characters)" (p. 211).
    """
    digit_bearing = ("9", "Z", "*", "P", "cs", "+", "-")
    counted = [a for a in atoms if a.sym in digit_bearing]
    if counted and counted[0].sym == "P":
        return 0
    return digits


def _walk(tree: Tree) -> tuple[list[Atom], list[Run]]:
    atoms: list[Atom] = []
    runs: list[Run] = []
    # Run indices whose leading symbol has already been emitted. The leftmost
    # symbol of an insertion run is the insertion character rather than a digit
    # position, so it has to be told apart from the rest of the run.
    run_opened: set[int] = set()

    def visit(node, run: int | None, run_sym: str | None, ctx: frozenset) -> None:
        if isinstance(node, Token):
            sym = _BARE_TOKENS.get(node.type)
            if sym is not None:
                atoms.append(Atom(sym, 1, None, False, str(node), "mantissa" in ctx))
            return
        data = str(node.data)
        if data == "_ambig":
            raise ValueError("ambiguous picture parse")
        if data in _POSITION_RULES:
            sym = _POSITION_RULES[data]
            char = str(node.children[0])
            count = _count_of(node)
            in_run = run if run is not None and sym == run_sym else None
            first = in_run is not None and in_run not in run_opened
            if (
                in_run is None
                and sym in ("+", "-")
                and count >= 2
                and "trail" not in ctx
            ):
                # "Floating insertion editing is specified by using a string of
                # at least two of the allowable floating insertion symbols"
                # (p. 222). A repeat count IS such a string -- "+(4)" is the
                # same picture as "++++" -- but it reaches the grammar as one
                # token, so the run is recognised here instead.
                in_run = len(runs)
                runs.append(Run(sym, count))
                first = True
            if first and in_run is not None:
                run_opened.add(in_run)
            atoms.append(Atom(sym, count, in_run, first, char, "mantissa" in ctx))
            return
        if data in _INSERTION_RUNS or data in _REPLACEMENT_RUNS:
            kind = _INSERTION_RUNS.get(data) or _REPLACEMENT_RUNS[data]
            index = len(runs)
            runs.append(Run(kind, 0))
            for child in node.children:
                visit(child, index, kind, ctx)
            length = sum(a.count for a in atoms if a.run == index and a.sym == kind)
            runs[index] = Run(kind, length)
            return
        if data == "ne_trail":
            ctx = ctx | {"trail"}
        elif data == "ef_mantissa":
            ctx = ctx | {"mantissa"}
        for child in node.children:
            visit(child, run, run_sym, ctx)

    visit(tree, None, None, frozenset())
    return atoms, runs


def _count_of(node: Tree) -> int:
    for child in node.children:
        if isinstance(child, Tree) and str(child.data) == "count":
            return int(str(child.children[0]))
    return 1


def _validate(
    *,
    category: str,
    atoms: list[Atom],
    runs: list[Run],
    chars: int,
    digits: int,
    cs_chars: set[str],
    max_digits: int,
) -> list[str]:
    errors: list[str] = []

    if category in ("numeric", "numeric_edited"):
        # "the number of digit positions represented in the character-string
        # must be in the range 1 through 18, inclusive [ARITH(COMPAT)] ... 1
        # through 31 ... [ARITH(EXTEND)]" (pp. 217-218).
        if not 1 <= digits <= max_digits:
            errors.append(f"{digits} digit positions, must be 1 to {max_digits}")

    if category == "numeric_edited":
        # "The total number of character positions in the string (including
        # editing-character positions) must not exceed 249." (p. 218)
        if chars > 249:
            errors.append(f"{chars} character positions, must not exceed 249")

    if category == "external_float":
        # "The mantissa can contain from 1 to 16 numeric characters." (p. 214).
        # digits already excludes the exponent for this category.
        if not 1 <= digits <= 16:
            errors.append(f"mantissa has {digits} digits, must be 1 to 16")

    if len(cs_chars) > 1:
        # "only one currency symbol ... can be specified in a PICTURE
        # character-string" (p. 221).
        errors.append("more than one currency symbol: " + " ".join(sorted(cs_chars)))

    floating = [r for r in runs if r.floating]
    if len(floating) > 1:
        # "The following symbols are mutually exclusive as floating replacement
        # symbols in one PICTURE character-string: Z * + - cs" (p. 224).
        kinds = " ".join(r.kind for r in floating)
        errors.append(f"floating symbols are mutually exclusive: {kinds}")

    signs = [a for a in atoms if a.sym in ("+", "-", "CR", "DB") and a.run is None]
    float_sign = any(r.kind in ("+", "-") and r.floating for r in runs)
    # "Only one of the following symbols can be written in a given PICTURE
    # character-string: + - CR DB" (p. 218). In external floating-point the two
    # signs are part of the format, not editing sign control.
    if category != "external_float":
        if len(signs) + (1 if float_sign else 0) > 1:
            errors.append("more than one of + - CR DB")

    return errors
