# pyright: standard
"""The callee of an inter-program CALL.

``Cobol.g4:1241`` is ``callStatement : CALL (identifier | literal) ...``, so a
callee is one of two things, and they behave differently:

  * a **literal** names the program outright — ``CALL 'DSNTIAC'``;
  * an **identifier** names a data item whose *contents at run time* are the
    program name — ``CALL WS-PROG``, ``CALL WS-PROGS(I)``, ``CALL WS-PROG(1:8)``,
    ``CALL WS-INNER OF WS-GRP``.

``CallTarget`` names that distinction once so no consumer has to re-derive it.
Carrying the alternatives as a bare ``str | RefModOperand`` would push the
literal-versus-resolve-at-run-time decision out to every call site; carrying a
flag beside a string would do the same and lose the identifier's subscripts and
reference-modification bounds along the way.

The identifier arm is a plain ``RefModOperand`` — the operand model MOVE, STRING
and the arithmetic verbs already use — so subscripts, ref-mod bounds and
``OF``/``IN`` qualifiers come for free rather than being modelled a second time.
"""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.ref_mod import RefModOperand


@dataclass(frozen=True)
class CallTarget:
    """Which program a CALL dispatches to, and how that is decided."""

    literal: str = ""
    identifier: RefModOperand | None = None

    @classmethod
    def of_literal(cls, program: str) -> CallTarget:
        return cls(literal=program)

    @classmethod
    def of_identifier(cls, operand: RefModOperand) -> CallTarget:
        return cls(identifier=operand)

    @classmethod
    def from_dict(cls, data: dict) -> CallTarget:
        """Read a callee out of a bridge CALL node.

        ``program_ref`` (a structured reference) is the identifier arm;
        ``program`` (a bare string) is the literal arm. The bridge emits exactly
        one of them.
        """
        ref = data.get("program_ref")
        if isinstance(ref, dict):
            return cls.of_identifier(RefModOperand.from_dict(ref))
        return cls.of_literal(data.get("program", ""))

    def write_into(self, out: dict) -> None:
        if self.identifier is not None:
            out["program_ref"] = self.identifier.to_dict()
        else:
            out["program"] = self.literal

    @property
    def resolved_at_runtime(self) -> bool:
        """True when the program name must be read out of storage to be known."""
        return self.identifier is not None

    def describe(self) -> str:
        """A source-shaped rendering for logs and diagnostics."""
        if self.identifier is None:
            return f"'{self.literal}'"
        operand = self.identifier
        text = operand.name
        if operand.qualifiers:
            text += "".join(f" OF {q}" for q in operand.qualifiers)
        if operand.subscripts:
            text += f"({len(operand.subscripts)} subscript(s))"
        if operand.ref_mod_start is not None:
            text += "(ref-mod)"
        return text
