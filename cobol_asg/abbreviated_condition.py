# pyright: standard
"""A condition as the bridge writes it, resolved into the AND/OR tree lowering walks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import reduce

_NEGATED = {"==": "!=", "!=": "==", ">": "<=", "<=": ">", "<": ">=", ">=": "<"}


@dataclass(frozen=True)
class _Subject:
    """The last stated subject and relational operator, which an abbreviation implies."""

    stated: bool
    left: Mapping
    op: str

    def stating(self, atom: Mapping) -> _Subject:
        if not _states_subject(atom):
            return self
        relation = atom["relation"]
        return _Subject(stated=True, left=relation["left"], op=relation["op"])

    def with_op(self, op: str) -> _Subject:
        return _Subject(stated=self.stated, left=self.left, op=op)


def _states_subject(atom: Mapping) -> bool:
    return "left" in atom.get("relation", {})


_UNSTATED = _Subject(stated=False, left={}, op="==")


@dataclass(frozen=True)
class _Chain:
    """The fold state: the finished OR terms, the open AND run, and the subject."""

    or_terms: tuple[Mapping, ...]
    and_run: Mapping
    subject: _Subject

    def joined(self, bool_op: str, right: Mapping, subject: _Subject) -> _Chain:
        if bool_op == "AND":
            return _Chain(self.or_terms, _compound("AND", self.and_run, right), subject)
        return _Chain((*self.or_terms, self.and_run), right, subject)

    def tree(self) -> dict:
        return dict(
            reduce(
                lambda left, right: _compound("OR", left, right),
                (*self.or_terms, self.and_run),
            )
        )


def _compound(bool_op: str, left: Mapping, right: Mapping) -> dict:
    return {"op": bool_op, "left": left, "right": right}


def _relation(left: Mapping, op: str, right: Mapping, negated: bool) -> dict:
    return {"not": negated, "relation": {"left": left, "op": op, "right": right}}


def resolve_condition(written: Mapping) -> dict:
    """The condition tree: AND binds tighter than OR, and each abbreviation is expanded.

    A bare identifier after a relation parses as a condition name; it carries
    the implied subject and operator under ``"abbreviation"`` so lowering can
    expand it when the name is a data item rather than a level-88. A tree
    already resolved is returned unchanged.
    """
    if "first" not in written:
        return dict(written)
    first = _atom(written["first"])
    start = _Chain((), first, _UNSTATED.stating(written["first"]))
    return reduce(_link, written["rest"], start).tree()


def _link(chain: _Chain, link: Mapping) -> _Chain:
    if "atom" in link:
        return _atom_link(chain, link["bool"], link["atom"])
    return _abbreviation_link(chain, link["bool"], link["abbreviations"])


def _atom_link(chain: _Chain, bool_op: str, written: Mapping) -> _Chain:
    if _states_subject(written):
        return chain.joined(bool_op, _atom(written), chain.subject.stating(written))
    return chain.joined(bool_op, _implied(chain.subject, _atom(written)), chain.subject)


def _implied(subject: _Subject, atom: Mapping) -> Mapping:
    """A condition name after a stated relation may be an abbreviated operand."""
    if not subject.stated or "condition_name" not in atom:
        return atom
    return {**atom, "abbreviation": {"left": subject.left, "op": subject.op}}


def _abbreviation_link(
    chain: _Chain, bool_op: str, abbreviations: Sequence[Mapping]
) -> _Chain:
    subject = reduce(
        lambda s, a: s.with_op(_stated_op(a, s.op)), abbreviations, chain.subject
    )
    if not chain.subject.stated or not abbreviations:
        return chain.joined(bool_op, {"text": ""}, subject)
    atoms = _abbreviation_atoms(chain.subject, abbreviations)
    right = reduce(lambda left, atom: _compound(bool_op, left, atom), atoms)
    return chain.joined(bool_op, right, subject)


def _abbreviation_atoms(
    subject: _Subject, abbreviations: Sequence[Mapping]
) -> tuple[dict, ...]:
    ops = reduce(
        lambda acc, a: (*acc, _stated_op(a, acc[-1])), abbreviations, (subject.op,)
    )
    return tuple(
        _relation(subject.left, op, a["right"], a["not"] and "op" not in a)
        for op, a in zip(ops[1:], abbreviations, strict=True)
    )


def _stated_op(abbreviation: Mapping, implied: str) -> str:
    """A NOT immediately before a relational operator is part of that operator."""
    if "op" not in abbreviation:
        return implied
    op = abbreviation["op"]
    return _NEGATED[op] if abbreviation["not"] else op


def _atom(written: Mapping) -> dict:
    if "condition" in written:
        return dict(written) | {"condition": resolve_condition(written["condition"])}
    if "combined" in written:
        return {k: v for k, v in written.items() if k != "combined"} | {
            "condition": _combined(written["combined"])
        }
    return dict(written)


def _combined(written: Mapping) -> dict:
    atoms = (
        _relation(written["left"], written["op"], operand, False)
        for operand in written["operands"]
    )
    return reduce(lambda left, atom: _compound(written["bool"], left, atom), atoms)
