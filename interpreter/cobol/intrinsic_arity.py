"""Centralised intrinsic-function argument disambiguation.

ProLeap's ``functionCall`` grammar separates arguments with an *optional* comma
and carries no per-function arity, so an arithmetic argument ``F(a - b)`` is
over-split into two arguments ``[a, neg(b)]`` — the ``- b`` is lost
(red-dragon-zgwl). Real compilers (e.g. GnuCOBOL's ``cb_intrinsic_table``)
disambiguate using each intrinsic's known argument count.

``resolve_intrinsic_args`` is the SINGLE place that repair happens. Every code
path that turns a bridge function node's raw argument dicts into structured
arguments MUST route through it — that is the invariant. Keeping the decision in
one function means the arity knowledge lives in exactly one table.
"""

from __future__ import annotations

# Maximum argument count per COBOL intrinsic, mirroring the ``args`` field of
# GnuCOBOL's cb_intrinsic_table (cobc/reserved.c). A function ABSENT from this
# table is treated as variadic — its arguments are left exactly as ProLeap gave
# them (we cannot disambiguate without knowing the arity). Variadic intrinsics
# (MAX/MIN/SUM/MEAN/...) are intentionally omitted for the same reason.
_INTRINSIC_MAX_ARITY: dict[str, int] = {
    "CURRENT-DATE": 0,
    # single-argument
    "DATE-OF-INTEGER": 1,
    "INTEGER-OF-DATE": 1,
    "DAY-OF-INTEGER": 1,
    "INTEGER-OF-DAY": 1,
    "UPPER-CASE": 1,
    "LOWER-CASE": 1,
    "REVERSE": 1,
    "NUMVAL": 1,
    "ORD": 1,
    "CHAR": 1,
    "INTEGER": 1,
    "INTEGER-PART": 1,
    "FRACTION-PART": 1,
    "SQRT": 1,
    "FACTORIAL": 1,
    # two-argument (max; some carry an optional 2nd arg, hence max 2)
    "LENGTH": 2,
    "TRIM": 2,
    "NUMVAL-C": 2,
    "TEST-NUMVAL": 2,
    "TEST-NUMVAL-C": 2,
    "MOD": 2,
    "REM": 2,
}


def _is_signed_continuation(arg: dict) -> bool:
    """True if ``arg`` is a signed term (``neg``/``pos``) — the shape ProLeap
    produces for the ``± term`` tail of an over-split arithmetic argument."""
    return arg.get("kind") in ("neg", "pos")


def _fold_continuation(base: dict, cont: dict) -> dict:
    """Reattach a signed continuation ``cont`` to ``base`` as a binary op.

    Unwrap the sign into a real ``-``/``+`` binop (``base - x`` / ``base + x``)
    — the same shape ProLeap produces for a non-split ``a - x``, which the
    expression lowering already evaluates correctly — rather than the
    ``base + neg(x)`` form (which the lowering mishandles for a nested
    function-call left operand)."""
    kind = cont.get("kind")
    if kind == "neg":
        return {"kind": "binop", "op": "-", "left": base, "right": cont["expr"]}
    if kind == "pos":
        return {"kind": "binop", "op": "+", "left": base, "right": cont["expr"]}
    return {"kind": "binop", "op": "+", "left": base, "right": cont}


def resolve_intrinsic_args(name: str, raw_args: list[dict]) -> list[dict]:
    """Disambiguate an intrinsic FUNCTION's raw argument dicts (the invariant entry point).

    When a fixed-arity function received more arguments than its arity, ProLeap
    over-split a single arithmetic argument ``F(a - b)`` into ``[a, neg(b)]``.
    Fold each surplus signed continuation back into the argument it continues
    (as a real ``a - b`` / ``a + b`` binop) until the count matches the
    function's arity. Variadic or unknown functions are returned unchanged.
    """
    max_arity = _INTRINSIC_MAX_ARITY.get(name.upper())
    if max_arity is None or max_arity < 0 or len(raw_args) <= max_arity:
        return raw_args

    if max_arity == 1:
        # Exactly one argument: everything after the first is a signed
        # continuation of the single arithmetic expression — fold them all in.
        folded = raw_args[0]
        for cont in raw_args[1:]:
            folded = _fold_continuation(folded, cont)
        return [folded]

    # Fixed arity >= 2: fold each trailing signed continuation into its immediate
    # predecessor (right to left) until the count matches the arity. This keeps
    # an arithmetic term with whichever argument it trails (MOD(A - 1, B) and
    # MOD(A, B - 1) both resolve correctly).
    out = list(raw_args)
    i = len(out) - 1
    while len(out) > max_arity and i >= 1:
        if _is_signed_continuation(out[i]):
            out[i - 1] = _fold_continuation(out[i - 1], out[i])
            del out[i]
        i -= 1
    return out
