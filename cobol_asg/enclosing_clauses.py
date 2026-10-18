"""The clauses a data description entry takes from the groups it is subordinate to."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.sign_clause import NO_SIGN_CLAUSE, SignClause


@dataclass(frozen=True)
class EnclosingClauses:
    """The nearest enclosing SIGN clause, and the USAGE an entry without its own takes."""

    sign: SignClause
    usage: str


TOP_LEVEL = EnclosingClauses(sign=NO_SIGN_CLAUSE, usage="DISPLAY")
