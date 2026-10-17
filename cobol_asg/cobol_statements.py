# pyright: standard
"""Typed COBOL statement hierarchy — discriminated union of frozen dataclasses.

Replaces the flat CobolStatement god class with specific types per
statement kind. Each type carries only the fields it needs, and a
top-level parse_statement() function dispatches on the JSON 'type'
discriminator.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Union

from cobol_asg.call_target import CallTarget
from cobol_asg.cobol_expression import (
    ExprNode,
    FieldRefNode,
    expr_from_dict,
    expr_to_dict,
    field_ref_from_dict,
)
from cobol_asg.evaluate_selection import (
    SelectionObject,
    SelectionSubject,
    selection_object_from_dict,
    selection_subject_from_dict,
)
from cobol_asg.exit_kind import ExitKind
from cobol_asg.file_enums import AccessMode, FileOrganization, OpenMode, RecordingMode
from cobol_asg.frontend_extension import DialectParser
from cobol_asg.initialize_category import InitializeCategory
from cobol_asg.initialize_replacing import InitializeReplacing
from cobol_asg.ref_mod import (
    FunctionCallOperand,
    RefModOperand,
    is_function_operand,
    ref_mod_expr_to_dict,
)
from cobol_asg.set_operand import SetOperand, set_operand_from_dict
from cobol_asg.source_span import SourceSpan

# ── Dialect parser injection ──────────────────────────────────────
# Set by CobolFrontend.lower() for the duration of each parse call. Cicada
# and Squall each inject their own DialectParser (interpreter.frontend)
# via CobolFrontend — see parse_statement()'s fallback below.
_dialect_parsers: ContextVar[Sequence[DialectParser]] = ContextVar(
    "_dialect_parsers", default=()
)


@contextmanager
def dialect_parsers_in_scope(parsers: Sequence[DialectParser]) -> Iterator[None]:
    """Decode statements with ``parsers`` as the dialect fallback until the block ends."""
    token = _dialect_parsers.set(tuple(parsers))
    try:
        yield
    finally:
        _dialect_parsers.reset(token)


# ── PERFORM specs ────────────────────────────────────────────────


@dataclass(frozen=True)
class PerformTimesSpec:
    """PERFORM ... TIMES loop specification."""

    times: ExprNode


@dataclass(frozen=True)
class PerformUntilSpec:
    """PERFORM ... UNTIL loop specification."""

    condition: dict
    test_before: bool = True  # TEST BEFORE (default) vs TEST AFTER


@dataclass(frozen=True)
class PerformVaryingSpec:
    """PERFORM ... VARYING loop specification."""

    varying_var: FieldRefNode
    varying_from: ExprNode
    varying_by: ExprNode
    condition: dict
    test_before: bool = True
    after_specs: tuple[PerformVaryingSpec, ...] = field(default_factory=tuple)


PerformSpec = Union[PerformTimesSpec, PerformUntilSpec, PerformVaryingSpec]


# Forward reference for recursive types — resolved after all classes defined.
CobolStatementType = Union[
    "MoveStatement",
    "MoveCorrespondingStatement",
    "ArithmeticStatement",
    "ComputeStatement",
    "IfStatement",
    "EvaluateStatement",
    "DisplayStatement",
    "GotoStatement",
    "StopRunStatement",
    "GobackStatement",
    "ExitProgramStatement",
    "PerformStatement",
    "WhenStatement",
    "WhenOtherStatement",
    "ContinueStatement",
    "ExitStatement",
    "NextSentenceStatement",
    "InitializeStatement",
    "ArithmeticCorrespondingStatement",
    "SetStatement",
    "StringStatement",
    "UnstringStatement",
    "InspectStatement",
    "SearchStatement",
    "CallStatement",
    "AlterStatement",
    "EntryStatement",
    "CancelStatement",
    "AcceptStatement",
    "OpenStatement",
    "CloseStatement",
    "ReadStatement",
    "WriteStatement",
    "RewriteStatement",
    "StartStatement",
    "DeleteStatement",
    "XmlGenerateStatement",
]


# ── Statement types ──────────────────────────────────────────────


def _phrases_to_dict(
    phrases: Mapping[str, Sequence[CobolStatementType]],
) -> dict[str, list[dict]]:
    return {
        name: [c.to_dict() for c in stmts] for name, stmts in phrases.items() if stmts
    }


@dataclass(frozen=True)
class MoveStatement:
    """MOVE source TO target.

    Operands can include reference modification (substring operations):
      MOVE WS-FIELD(2:3) TO WS-OUT
      MOVE WS-FIELD(WS-A:WS-B) TO WS-OUT
      MOVE WS-FIELD(WS-A + 1:WS-B - 1) TO WS-OUT
    """

    source: RefModOperand | FunctionCallOperand
    targets: list[RefModOperand]
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> MoveStatement:
        operands = data.get("operands", [])
        source_data = operands[0] if len(operands) > 0 else {}
        # COBOL `MOVE src TO a b c` distributes the source to every receiving
        # field; the bridge emits all of them as operands[1:].
        target_data = operands[1:]

        source: RefModOperand | FunctionCallOperand
        if is_function_operand(source_data):
            source = FunctionCallOperand.from_dict(source_data)
        else:
            source = RefModOperand.from_dict(source_data)
        targets = [RefModOperand.from_dict(t) for t in target_data]

        return cls(
            source=source,
            targets=targets,
            span=SourceSpan.from_dict(data),
        )

    def _operand_dict(self, operand: RefModOperand) -> dict:
        if operand.length_of:
            return {"kind": "length_of", "name": operand.length_of}
        d: dict = {"name": operand.name}
        if operand.ref_mod_start is not None:
            d["ref_mod_start"] = ref_mod_expr_to_dict(operand.ref_mod_start)
        if operand.ref_mod_length is not None:
            d["ref_mod_length"] = ref_mod_expr_to_dict(operand.ref_mod_length)
        if operand.qualifiers:
            d["qualifiers"] = list(operand.qualifiers)
        if operand.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in operand.subscripts]
        if operand.rounded:
            d["rounded"] = True
        return d

    def to_dict(self) -> dict:
        if isinstance(self.source, FunctionCallOperand):
            source_dict: dict = {
                "kind": "function",
                "name": self.source.name,
                "args": list(self.source.args),
            }
        else:
            source_dict = self._operand_dict(self.source)
        operands = [source_dict]
        operands.extend(self._operand_dict(t) for t in self.targets)
        result = {"type": "MOVE", "operands": operands}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class MoveCorrespondingStatement:
    """MOVE CORRESPONDING source TO target1 [TO target2 ...]."""

    source: RefModOperand
    targets: list[RefModOperand] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> MoveCorrespondingStatement:
        return cls(
            source=RefModOperand.from_dict(data["source"]),
            targets=[RefModOperand.from_dict(t) for t in data.get("targets", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "MOVE_CORRESPONDING",
            "source": self.source.to_dict(),
        }
        if self.targets:
            result["targets"] = [target.to_dict() for target in self.targets]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ArithmeticCorrespondingStatement:
    """ADD/SUBTRACT CORRESPONDING src TO/FROM dst."""

    op: str  # "ADD" | "SUBTRACT"
    source: RefModOperand
    target: RefModOperand
    on_size_error: list[CobolStatementType] = field(default_factory=list)
    not_on_size_error: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ArithmeticCorrespondingStatement:
        op = "ADD" if data.get("type") == "ADD_CORRESPONDING" else "SUBTRACT"
        return cls(
            op=op,
            source=RefModOperand.from_dict(data["source"]),
            target=RefModOperand.from_dict(data["target"]),
            on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
            not_on_size_error=[
                parse_statement(c) for c in data.get("not_on_size_error", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": f"{self.op}_CORRESPONDING",
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            **_phrases_to_dict(
                {
                    "on_size_error": self.on_size_error,
                    "not_on_size_error": self.not_on_size_error,
                }
            ),
        }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ArithmeticStatement:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE: sending operands, in-place targets or GIVING receivers."""

    op: str
    operands: list[RefModOperand]
    targets: list[RefModOperand] = field(default_factory=list)
    giving: list[RefModOperand] = field(default_factory=list)
    remainder: RefModOperand | None = None
    on_size_error: list[CobolStatementType] = field(default_factory=list)
    not_on_size_error: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ArithmeticStatement:
        remainder_data = data.get("remainder")
        remainder = (
            RefModOperand.from_dict(remainder_data)
            if isinstance(remainder_data, dict)
            else RefModOperand(name=remainder_data) if remainder_data else None
        )
        return cls(
            op=data["type"],
            operands=[RefModOperand.from_dict(o) for o in data.get("operands", [])],
            targets=[RefModOperand.from_dict(t) for t in data.get("targets", [])],
            giving=[RefModOperand.from_dict(g) for g in data.get("giving", [])],
            remainder=remainder,
            on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
            not_on_size_error=[
                parse_statement(c) for c in data.get("not_on_size_error", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": self.op,
            "operands": [o.to_dict() for o in self.operands],
        }
        if self.targets:
            result["targets"] = [t.to_dict() for t in self.targets]
        if self.giving:
            result["giving"] = [g.to_dict() for g in self.giving]
        if self.remainder is not None:
            result["remainder"] = self.remainder.to_dict()
        if self.on_size_error:
            result["on_size_error"] = [c.to_dict() for c in self.on_size_error]
        if self.not_on_size_error:
            result["not_on_size_error"] = [c.to_dict() for c in self.not_on_size_error]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ComputeTarget:
    """A single target variable in a COMPUTE statement, with optional ROUNDED."""

    name: str
    rounded: bool = False
    subscripts: tuple[ExprNode, ...] = ()
    qualifiers: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | str) -> ComputeTarget:
        if isinstance(data, str):
            return cls(name=data)
        return cls(
            name=data["name"],
            rounded=data.get("rounded", False),
            subscripts=tuple(expr_from_dict(s) for s in data.get("subscripts", [])),
            qualifiers=tuple(data.get("qualifiers", ())),
        )

    def to_dict(self) -> dict:
        d: dict = {"name": self.name}
        if self.rounded:
            d["rounded"] = True
        if self.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in self.subscripts]
        return d | ({"qualifiers": list(self.qualifiers)} if self.qualifiers else {})


@dataclass(frozen=True)
class ComputeStatement:
    """COMPUTE target = arithmetic-expression."""

    expression: ExprNode  # structured expression tree
    targets: list[ComputeTarget] = field(default_factory=list)  # target variable names
    on_size_error: list[CobolStatementType] = field(default_factory=list)
    not_on_size_error: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ComputeStatement:
        return cls(
            expression=expr_from_dict(data["expression"]),
            targets=[ComputeTarget.from_dict(t) for t in data.get("targets", [])],
            on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
            not_on_size_error=[
                parse_statement(c) for c in data.get("not_on_size_error", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "COMPUTE", "expression": expr_to_dict(self.expression)}
        if self.targets:
            result["targets"] = [t.to_dict() for t in self.targets]
        if self.on_size_error:
            result["on_size_error"] = [c.to_dict() for c in self.on_size_error]
        if self.not_on_size_error:
            result["not_on_size_error"] = [c.to_dict() for c in self.not_on_size_error]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class IfStatement:
    """IF condition ... [ELSE ...] END-IF."""

    condition: dict
    children: list[CobolStatementType] = field(default_factory=list)
    else_children: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> IfStatement:
        return cls(
            condition=data.get("condition", {}),
            children=[parse_statement(c) for c in data.get("children", [])],
            else_children=[parse_statement(c) for c in data.get("else_children", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "IF", "condition": self.condition}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.else_children:
            result["else_children"] = [c.to_dict() for c in self.else_children]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class WhenStatement:
    """One WHEN of an EVALUATE: a selection object per subject, first then ALSO.

    ``alternatives`` are the further WHENs of a stacked ``WHEN o1 WHEN o2
    <body>``, each body-less; any one of them, or this WHEN's own objects,
    selects ``children``.
    """

    objects: tuple[SelectionObject, ...]
    children: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None
    alternatives: list[WhenStatement] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WhenStatement:
        return cls(
            objects=tuple(selection_object_from_dict(o) for o in data["objects"]),
            children=[parse_statement(c) for c in data.get("children", [])],
            span=SourceSpan.from_dict(data),
            alternatives=[
                WhenStatement.from_dict(a) for a in data.get("alternatives", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "WHEN",
            "objects": [o.to_dict() for o in self.objects],
        }
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.span is not None:
            self.span.write_into(result)
        return result | (
            {"alternatives": [a.to_dict() for a in self.alternatives]}
            if self.alternatives
            else {}
        )


@dataclass(frozen=True)
class WhenOtherStatement:
    """EVALUATE WHEN OTHER branch."""

    children: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> WhenOtherStatement:
        return cls(
            children=[parse_statement(c) for c in data.get("children", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WHEN_OTHER"}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class EvaluateStatement:
    """EVALUATE subject [ALSO subject ...] WHEN ... END-EVALUATE.

    ``subjects`` are the selection subjects, the first then each ALSO one; a
    WHEN's objects answer them position by position.
    """

    subjects: tuple[SelectionSubject, ...]
    children: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> EvaluateStatement:
        return cls(
            subjects=tuple(selection_subject_from_dict(s) for s in data["subjects"]),
            children=[parse_statement(c) for c in data.get("children", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "EVALUATE",
            "subjects": [s.to_dict() for s in self.subjects],
        }
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class DisplayStatement:
    """DISPLAY operand [operand ...] — operands are concatenated onto one line."""

    operands: tuple[RefModOperand, ...]
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DisplayStatement:
        return cls(
            operands=tuple(
                RefModOperand.from_dict({"name": raw} if isinstance(raw, str) else raw)
                for raw in data.get("operands", [])
            ),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "DISPLAY", "operands": [op.to_dict() for op in self.operands]}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ProcedureRef:
    """A COBOL procedure-name: a paragraph, optionally qualified by a section.
    A bare name has section="". Procedure-names are never subscripted or
    reference-modified, so the surface is deliberately small."""

    paragraph: str
    section: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> ProcedureRef:
        return cls(paragraph=data.get("paragraph", ""), section=data.get("section", ""))

    def to_dict(self) -> dict:
        return {"paragraph": self.paragraph, "section": self.section}


@dataclass(frozen=True)
class SimpleGoto:
    """GO TO single-paragraph."""

    target: ProcedureRef


@dataclass(frozen=True)
class ComputedGoto:
    """GO TO p1 … pN DEPENDING ON index (1-based selection)."""

    targets: tuple[ProcedureRef, ...]
    index: RefModOperand


@dataclass(frozen=True)
class AlteredGoto:
    """GO TO. with no operand — target supplied by ALTER at runtime."""


@dataclass(frozen=True)
class GotoStatement:
    """GO TO — one of three mutually exclusive forms."""

    form: SimpleGoto | ComputedGoto | AlteredGoto
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> GotoStatement:
        form_kind = data.get("form")
        if form_kind == "computed":
            targets = tuple(ProcedureRef.from_dict(t) for t in data.get("targets", []))
            index = RefModOperand.from_dict(data.get("index", {}))
            return cls(
                form=ComputedGoto(targets=targets, index=index),
                span=SourceSpan.from_dict(data),
            )
        if form_kind == "altered":
            return cls(form=AlteredGoto(), span=SourceSpan.from_dict(data))
        return cls(
            form=SimpleGoto(target=ProcedureRef.from_dict(data.get("target", {}))),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        form = self.form
        result: dict
        if isinstance(form, ComputedGoto):
            result = {
                "type": "GOTO",
                "form": "computed",
                "targets": [t.to_dict() for t in form.targets],
                "index": form.index.to_dict(),
            }
        elif isinstance(form, AlteredGoto):
            result = {"type": "GOTO", "form": "altered"}
        else:
            result = {
                "type": "GOTO",
                "form": "simple",
                "target": form.target.to_dict(),
            }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class StopRunStatement:
    """STOP RUN."""

    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> StopRunStatement:
        return cls(
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "STOP_RUN"}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class GobackStatement:
    """GOBACK — return control to the caller (or terminate if called as main program)."""

    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> GobackStatement:
        return cls(
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "GOBACK"}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ExitProgramStatement:
    """EXIT PROGRAM — return control to the caller (no-op in main program)."""

    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ExitProgramStatement:
        return cls(
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "EXIT_PROGRAM"}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ContinueStatement:
    """CONTINUE — no-op sentinel."""

    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ContinueStatement:
        return cls(
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "CONTINUE"}
        match self.span:
            case SourceSpan() as span:
                span.write_into(result)
        return result


@dataclass(frozen=True)
class NextSentenceStatement:
    """NEXT SENTENCE -- control goes past the period that ends the enclosing
    sentence, which an END-IF before that period does not stop."""

    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> NextSentenceStatement:
        return cls(span=SourceSpan.from_dict(data))

    def to_dict(self) -> dict:
        result = {"type": "NEXT_SENTENCE"}
        match self.span:
            case SourceSpan() as span:
                span.write_into(result)
        return result


@dataclass(frozen=True)
class ExitStatement:
    """EXIT -- a no-op sentinel at paragraph end, or, with a kind, an exit from the
    current paragraph, section or inline PERFORM."""

    kind: ExitKind = ExitKind.PLAIN
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ExitStatement:
        return cls(
            kind=ExitKind(data.get("kind", "")),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "EXIT"} | (
            {} if self.kind is ExitKind.PLAIN else {"kind": self.kind.value}
        )
        match self.span:
            case SourceSpan() as span:
                span.write_into(result)
        return result


@dataclass(frozen=True)
class InitializeStatement:
    """INITIALIZE field1 field2 ... — reset fields to type-appropriate defaults."""

    operands: list[RefModOperand] = field(default_factory=list)
    replacing: list[InitializeReplacing] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> InitializeStatement:
        return cls(
            operands=[RefModOperand.from_dict(o) for o in data.get("operands", [])],
            replacing=[
                InitializeReplacing(
                    category=InitializeCategory(r["category"]),
                    by=RefModOperand.from_dict(r["by"]),
                )
                for r in data.get("replacing", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {
            "type": "INITIALIZE",
            "operands": [operand.to_dict() for operand in self.operands],
            **(
                {
                    "replacing": [
                        {"category": r.category.value, "by": r.by.to_dict()}
                        for r in self.replacing
                    ]
                }
                if self.replacing
                else {}
            ),
        }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class SetStatement:
    """SET target TO value / SET target UP|DOWN BY value."""

    set_type: str  # "TO" or "BY"
    targets: list[SetOperand] = field(default_factory=list)
    values: list[SetOperand] = field(default_factory=list)
    by_type: str = ""  # "UP" or "DOWN" (only for BY)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> SetStatement:
        values = (
            data.get("values", [])
            if data.get("set_type") == "TO"
            else [data["value"]] if "value" in data else []
        )
        return cls(
            set_type=data.get("set_type", ""),
            targets=[set_operand_from_dict(t) for t in data.get("targets", [])],
            values=[set_operand_from_dict(v) for v in values],
            by_type=data.get("by_type", ""),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "SET",
            "set_type": self.set_type,
            "targets": [t.to_dict() for t in self.targets],
        }
        if self.set_type == "TO":
            result["values"] = [v.to_dict() for v in self.values]
        else:
            result["by_type"] = self.by_type
            result["value"] = self.values[0].to_dict()
        if self.span is not None:
            self.span.write_into(result)
        return result


# ── String operation nested types ─────────────────────────────────


@dataclass(frozen=True)
class StringSending:
    """A single sending phrase in a STRING statement.

    The sending operand is usually a field reference / literal (``value``), but
    it may also be an intrinsic ``FUNCTION`` call — e.g.
    ``STRING FUNCTION TRIM(WS-VAR) ' ...' INTO WS-MSG`` — in which case
    ``function`` is populated and lowering evaluates the call (red-dragon-zuhj).
    ``delimiter`` is the DELIMITED BY operand; DELIMITED BY SIZE leaves it unwritten.
    """

    value: RefModOperand
    delimiter: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    function: FunctionCallOperand | None = None

    @classmethod
    def from_dict(cls, data: dict) -> StringSending:
        raw_value = data.get("value", {})
        function = (
            FunctionCallOperand.from_dict(raw_value)
            if is_function_operand(raw_value)
            else None
        )
        return cls(
            value=RefModOperand.from_dict(raw_value),
            delimiter=_operand(data, "delimiter"),
            function=function,
        )

    def to_dict(self) -> dict:
        result = {
            "value": self.value.to_dict(),
            **({"delimiter": self.delimiter.to_dict()} if self.delimiter.name else {}),
        }
        if self.function is not None:
            result["value"] = {
                "kind": "function",
                "name": self.function.name,
                "args": list(self.function.args),
            }
        return result


@dataclass(frozen=True)
class StringStatement:
    """STRING ... DELIMITED BY ... INTO target.

    ``into`` may carry reference modification (``INTO dest(start:length)``,
    red-dragon-2fxq) — a bare receiving field is ``RefModOperand(name=...)``
    with no ref-mod set, same as any other RefModOperand-typed operand.
    """

    sendings: list[StringSending] = field(default_factory=list)
    into: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    pointer: str = ""
    on_overflow: list[CobolStatementType] = field(default_factory=list)
    not_on_overflow: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> StringStatement:
        return cls(
            sendings=[StringSending.from_dict(s) for s in data.get("sendings", [])],
            into=RefModOperand.from_dict(data.get("into", {})),
            pointer=data.get("pointer", ""),
            on_overflow=[parse_statement(c) for c in data.get("on_overflow", [])],
            not_on_overflow=[
                parse_statement(c) for c in data.get("not_on_overflow", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {
            "type": "STRING",
            "sendings": [s.to_dict() for s in self.sendings],
            "into": self.into.to_dict(),
            **_phrases_to_dict(
                {
                    "on_overflow": self.on_overflow,
                    "not_on_overflow": self.not_on_overflow,
                }
            ),
        }
        if self.pointer:
            result["pointer"] = self.pointer
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class UnstringStatement:
    """UNSTRING source DELIMITED BY ... INTO targets.

    Each entry in ``into`` may carry reference modification (``INTO
    dest(start:length)``, red-dragon-2fxq) — a bare receiving field is
    ``RefModOperand(name=...)`` with no ref-mod set.
    """

    source: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    delimiters: list[str] = field(default_factory=list)
    into: list[RefModOperand] = field(default_factory=list)
    tallying_target: str = ""
    pointer: str = ""
    on_overflow: list[CobolStatementType] = field(default_factory=list)
    not_on_overflow: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> UnstringStatement:
        return cls(
            source=RefModOperand.from_dict(data.get("source", {})),
            delimiters=list(data.get("delimiters", [])),
            into=[RefModOperand.from_dict(i) for i in data.get("into", [])],
            tallying_target=data.get("tallying_target", ""),
            pointer=data.get("pointer", ""),
            on_overflow=[parse_statement(c) for c in data.get("on_overflow", [])],
            not_on_overflow=[
                parse_statement(c) for c in data.get("not_on_overflow", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {
            "type": "UNSTRING",
            "source": self.source.to_dict(),
            "delimiters": list(self.delimiters),
            "into": [i.to_dict() for i in self.into],
            **_phrases_to_dict(
                {
                    "on_overflow": self.on_overflow,
                    "not_on_overflow": self.not_on_overflow,
                }
            ),
        }
        if self.tallying_target:
            result["tallying_target"] = self.tallying_target
        if self.pointer:
            result["pointer"] = self.pointer
        if self.span is not None:
            self.span.write_into(result)
        return result


_NO_OPERAND = RefModOperand(name="")


def _operand(data: dict, field_name: str) -> RefModOperand:
    return (
        RefModOperand.from_dict(data[field_name]) if field_name in data else _NO_OPERAND
    )


def _bounds_to_dict(after: RefModOperand, before: RefModOperand) -> dict:
    return {
        **({"after": after.to_dict()} if after.name else {}),
        **({"before": before.to_dict()} if before.name else {}),
    }


@dataclass(frozen=True)
class TallyingFor:
    """A single tallying phrase in INSPECT TALLYING.

    ``after`` / ``before`` are the AFTER and BEFORE INITIAL operands; one with
    an empty name was not written. A phrase may carry both.
    """

    mode: str  # "ALL", "LEADING", "CHARACTERS"
    pattern: RefModOperand = _NO_OPERAND
    after: RefModOperand = _NO_OPERAND
    before: RefModOperand = _NO_OPERAND

    @classmethod
    def from_dict(cls, data: dict) -> TallyingFor:
        return cls(
            mode=data.get("mode", ""),
            pattern=_operand(data, "pattern"),
            after=_operand(data, "after"),
            before=_operand(data, "before"),
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            **({"pattern": self.pattern.to_dict()} if self.pattern.name else {}),
            **_bounds_to_dict(self.after, self.before),
        }


@dataclass(frozen=True)
class TallyingGroup:
    """One TALLYING target and the phrases counted into it.

    INSPECT allows multiple independent targets in one statement:
    ``INSPECT src TALLYING cnt1 FOR ALL 'A' cnt2 FOR ALL 'B'`` — this mirrors
    the ProLeap ASG's own ``List<For>`` shape, where each ``For`` already
    carries its own tally target.
    """

    target: RefModOperand = _NO_OPERAND
    patterns: list[TallyingFor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> TallyingGroup:
        return cls(
            target=_operand(data, "target"),
            patterns=[TallyingFor.from_dict(p) for p in data.get("patterns", [])],
        )

    def to_dict(self) -> dict:
        return {
            "target": self.target.to_dict(),
            "patterns": [p.to_dict() for p in self.patterns],
        }


@dataclass(frozen=True)
class Replacing:
    """A single replacing phrase in INSPECT REPLACING."""

    mode: str  # "ALL", "LEADING", "FIRST", "CHARACTERS"
    from_pattern: RefModOperand = _NO_OPERAND
    to_pattern: RefModOperand = _NO_OPERAND
    after: RefModOperand = _NO_OPERAND
    before: RefModOperand = _NO_OPERAND

    @classmethod
    def from_dict(cls, data: dict) -> Replacing:
        return cls(
            mode=data.get("mode", ""),
            from_pattern=_operand(data, "from"),
            to_pattern=_operand(data, "to"),
            after=_operand(data, "after"),
            before=_operand(data, "before"),
        )

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            **({"from": self.from_pattern.to_dict()} if self.from_pattern.name else {}),
            "to": self.to_pattern.to_dict(),
            **_bounds_to_dict(self.after, self.before),
        }


@dataclass(frozen=True)
class InspectStatement:
    """INSPECT source TALLYING|REPLACING|TALLYING ... REPLACING|CONVERTING ..."""

    inspect_type: str = ""  # TALLYING, REPLACING, TALLYING_REPLACING, CONVERTING
    source: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    tallying_groups: list[TallyingGroup] = field(default_factory=list)
    replacings: list[Replacing] = field(default_factory=list)
    converting_from: RefModOperand = _NO_OPERAND
    converting_to: RefModOperand = _NO_OPERAND
    converting_after: RefModOperand = _NO_OPERAND
    converting_before: RefModOperand = _NO_OPERAND
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> InspectStatement:
        return cls(
            inspect_type=data.get("inspect_type", ""),
            source=RefModOperand.from_dict(data.get("source", {})),
            tallying_groups=[
                TallyingGroup.from_dict(g) for g in data.get("tallying_groups", [])
            ],
            replacings=[Replacing.from_dict(r) for r in data.get("replacings", [])],
            converting_from=_operand(data, "converting_from"),
            converting_to=_operand(data, "converting_to"),
            converting_after=_operand(data, "after"),
            converting_before=_operand(data, "before"),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "INSPECT",
            "inspect_type": self.inspect_type,
            "source": self.source.to_dict(),
            **(
                {"tallying_groups": [g.to_dict() for g in self.tallying_groups]}
                if self.tallying_groups
                else {}
            ),
            **(
                {"replacings": [r.to_dict() for r in self.replacings]}
                if self.replacings
                else {}
            ),
            **(
                {
                    "converting_from": self.converting_from.to_dict(),
                    "converting_to": self.converting_to.to_dict(),
                    **_bounds_to_dict(self.converting_after, self.converting_before),
                }
                if self.inspect_type == "CONVERTING"
                else {}
            ),
        }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class SearchWhen:
    """A WHEN clause inside a SEARCH statement."""

    condition: str
    children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SearchWhen:
        return cls(
            condition=data.get("condition", ""),
            children=[parse_statement(c) for c in data.get("children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"condition": self.condition}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass(frozen=True)
class SearchStatement:
    """SEARCH [ALL] table [VARYING index] WHEN condition ... [AT END ...].

    ``search_all`` is SEARCH ALL: the whole table is searched, whatever its
    index holds on entry.
    """

    table: str = ""
    varying: str = ""
    whens: list[SearchWhen] = field(default_factory=list)
    at_end: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None
    search_all: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> SearchStatement:
        return cls(
            table=data.get("table", ""),
            search_all=data.get("all", False),
            varying=data.get("varying", ""),
            whens=[SearchWhen.from_dict(w) for w in data.get("whens", [])],
            at_end=[parse_statement(c) for c in data.get("at_end", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "SEARCH", "table": self.table} | (
            {"all": True} if self.search_all else {}
        )
        if self.varying:
            result["varying"] = self.varying
        result["whens"] = [w.to_dict() for w in self.whens]
        if self.at_end:
            result["at_end"] = [c.to_dict() for c in self.at_end]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class CallUsingParam:
    """A single USING parameter in a CALL statement."""

    name: str
    param_type: str = "REFERENCE"  # REFERENCE, CONTENT, or VALUE
    omitted: bool = False
    is_literal: bool = False
    address_of: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> CallUsingParam:
        return cls(
            name=data.get("name", ""),
            param_type=data.get("type", "REFERENCE"),
            omitted=data.get("omitted", False),
            is_literal=data.get("is_literal", False),
            address_of=data.get("address_of", False),
        )

    def to_dict(self) -> dict:
        flags = {
            "omitted": self.omitted,
            "is_literal": self.is_literal,
            "address_of": self.address_of,
        }
        return {
            "name": self.name,
            "type": self.param_type,
            **{flag: True for flag, on in flags.items() if on},
        }


@dataclass(frozen=True)
class CallStatement:
    """CALL (identifier | literal) [USING params] [GIVING target].

    ``target`` carries the callee. It is a ``CallTarget`` rather than a program
    name because COBOL lets the callee be a data item whose runtime contents
    name the program; see ``cobol_asg.call_target``.
    """

    target: CallTarget = field(default_factory=CallTarget)
    using: list[CallUsingParam] = field(default_factory=list)
    giving: str = ""
    on_exception: list[CobolStatementType] = field(default_factory=list)
    not_on_exception: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> CallStatement:
        return cls(
            target=CallTarget.from_dict(data),
            using=[CallUsingParam.from_dict(p) for p in data.get("using", [])],
            giving=data.get("giving", ""),
            on_exception=[parse_statement(c) for c in data.get("on_exception", [])],
            not_on_exception=[
                parse_statement(c) for c in data.get("not_on_exception", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "CALL",
            **_phrases_to_dict(
                {
                    "on_exception": self.on_exception,
                    "not_on_exception": self.not_on_exception,
                }
            ),
        }
        self.target.write_into(result)
        if self.using:
            result["using"] = [p.to_dict() for p in self.using]
        if self.giving:
            result["giving"] = self.giving
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class AlterProceedTo:
    """A single source → target mapping in ALTER."""

    source: str
    target: str

    @classmethod
    def from_dict(cls, data: dict) -> AlterProceedTo:
        return cls(
            source=data.get("source", ""),
            target=data.get("target", ""),
        )

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target}


@dataclass(frozen=True)
class AlterStatement:
    """ALTER para-1 TO PROCEED TO para-2."""

    proceed_tos: list[AlterProceedTo] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> AlterStatement:
        return cls(
            proceed_tos=[
                AlterProceedTo.from_dict(p) for p in data.get("proceed_tos", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ALTER"}
        if self.proceed_tos:
            result["proceed_tos"] = [p.to_dict() for p in self.proceed_tos]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class EntryStatement:
    """ENTRY 'name' [USING params]."""

    entry_name: str = ""
    using: list[str] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> EntryStatement:
        return cls(
            entry_name=data.get("entry_name", ""),
            using=data.get("using", []),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ENTRY", "entry_name": self.entry_name}
        if self.using:
            result["using"] = self.using
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class CancelStatement:
    """CANCEL program-name(s)."""

    programs: list[str] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> CancelStatement:
        return cls(
            programs=data.get("programs", []),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "CANCEL", "programs": self.programs}
        if self.span is not None:
            self.span.write_into(result)
        return result


# ── I/O Statement types ─────────────────────────────────────────


@dataclass(frozen=True)
class AcceptStatement:
    """ACCEPT target [FROM device]."""

    target: RefModOperand
    from_device: str = "CONSOLE"
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> AcceptStatement:
        return cls(
            target=RefModOperand.from_dict(data["target"]),
            from_device=data.get("from_device", "CONSOLE"),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ACCEPT", "target": self.target.to_dict()}
        if self.from_device != "CONSOLE":
            result["from_device"] = self.from_device
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class FileControlEntry:
    """FILE-CONTROL entry from the ENVIRONMENT DIVISION."""

    file_name: str
    assign_to: str = ""
    organization: FileOrganization = FileOrganization.SEQUENTIAL
    access_mode: AccessMode = AccessMode.SEQUENTIAL
    record_key: str = ""
    relative_key: str = ""
    file_status_var: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> FileControlEntry:
        return cls(
            file_name=data["file_name"],
            assign_to=data.get("assign_to", ""),
            organization=FileOrganization(data.get("organization", "SEQUENTIAL")),
            access_mode=AccessMode(data.get("access_mode", "SEQUENTIAL")),
            record_key=data.get("record_key", ""),
            relative_key=data.get("relative_key", ""),
            file_status_var=data.get("file_status_var", ""),
        )

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "assign_to": self.assign_to,
            "organization": self.organization.value,
            "access_mode": self.access_mode.value,
            "record_key": self.record_key,
            "relative_key": self.relative_key,
            "file_status_var": self.file_status_var,
        }


@dataclass(frozen=True)
class NoRecordClause:
    """An FD with no RECORD clause."""

    def to_dict(self) -> dict:
        return {"kind": "none"}


@dataclass(frozen=True)
class RecordContains:
    """RECORD CONTAINS n CHARACTERS."""

    size: int

    def to_dict(self) -> dict:
        return {"kind": "contains", "size": self.size}


@dataclass(frozen=True)
class RecordContainsRange:
    """RECORD CONTAINS m TO n CHARACTERS."""

    minimum: int
    maximum: int

    def to_dict(self) -> dict:
        return {"kind": "range", "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class RecordVarying:
    """RECORD IS VARYING [FROM m] [TO n] [DEPENDING ON data-name]; 0 and "" where omitted."""

    minimum: int
    maximum: int
    depending_on: str

    def to_dict(self) -> dict:
        return {
            "kind": "varying",
            "minimum": self.minimum,
            "maximum": self.maximum,
            "depending_on": self.depending_on,
        }


RecordClause = NoRecordClause | RecordContains | RecordContainsRange | RecordVarying

_RECORD_CLAUSES: dict[str, Callable[[Mapping], RecordClause]] = {
    "none": lambda d: NoRecordClause(),
    "contains": lambda d: RecordContains(d["size"]),
    "range": lambda d: RecordContainsRange(d["minimum"], d["maximum"]),
    "varying": lambda d: RecordVarying(d["minimum"], d["maximum"], d["depending_on"]),
}


@dataclass(frozen=True)
class FileDescription:
    """An FD's RECORDING MODE and RECORD clause, from the FILE SECTION."""

    fd_name: str
    recording_mode: RecordingMode
    record_clause: RecordClause

    @classmethod
    def from_dict(cls, data: Mapping) -> FileDescription:
        clause = data["record_clause"]
        return cls(
            fd_name=data["fd_name"],
            recording_mode=RecordingMode(data["recording_mode"]),
            record_clause=_RECORD_CLAUSES[clause["kind"]](clause),
        )

    def to_dict(self) -> dict:
        return {
            "fd_name": self.fd_name,
            "recording_mode": self.recording_mode.value,
            "record_clause": self.record_clause.to_dict(),
        }


@dataclass(frozen=True)
class OpenStatement:
    """OPEN [mode file1 file2 ...] ... — one or more mode groups."""

    mode_groups: list[tuple[OpenMode, list[str]]] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> OpenStatement:
        groups = [
            (OpenMode(g["mode"]), list(g["files"])) for g in data.get("mode_groups", [])
        ]
        return cls(
            mode_groups=groups,
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {
            "type": "OPEN",
            "mode_groups": [
                {"mode": mode.value, "files": list(files)}
                for mode, files in self.mode_groups
            ],
        }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class CloseStatement:
    """CLOSE file1 file2 ..."""

    files: list[str] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> CloseStatement:
        return cls(
            files=data.get("files", []),
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result = {"type": "CLOSE", "files": list(self.files)}
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class ReadStatement:
    """READ file-name [INTO target] [KEY key] [AT END ...] [INVALID KEY ...]."""

    file_name: str = ""
    into: str = ""
    key: str = ""
    at_end: list[CobolStatementType] = field(default_factory=list)
    not_at_end: list[CobolStatementType] = field(default_factory=list)
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ReadStatement:
        return cls(
            file_name=data.get("file_name", ""),
            into=data.get("into", ""),
            key=data.get("key", ""),
            at_end=[parse_statement(c) for c in data.get("at_end", [])],
            not_at_end=[parse_statement(c) for c in data.get("not_at_end", [])],
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "READ", "file_name": self.file_name}
        if self.into:
            result["into"] = self.into
        if self.key:
            result["key"] = self.key
        if self.at_end:
            result["at_end"] = [c.to_dict() for c in self.at_end]
        if self.not_at_end:
            result["not_at_end"] = [c.to_dict() for c in self.not_at_end]
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class WriteStatement:
    """WRITE record-name [FROM field] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    record_name: str = ""
    from_field: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> WriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class RewriteStatement:
    """REWRITE record-name [FROM field] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    record_name: str = ""
    from_field: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> RewriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "REWRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class StartStatement:
    """START file-name [KEY relop key] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    file_name: str = ""
    key: str = ""
    relop: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> StartStatement:
        return cls(
            file_name=data.get("file_name", ""),
            key=data.get("key", ""),
            relop=data.get("relop", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "START", "file_name": self.file_name}
        if self.key:
            result["key"] = self.key
        if self.relop:
            result["relop"] = self.relop
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class DeleteStatement:
    """DELETE file-name [RECORD] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    file_name: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DeleteStatement:
        return cls(
            file_name=data.get("file_name", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "DELETE", "file_name": self.file_name}
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class XmlGenerateStatement:
    """XML GENERATE xml-document FROM record [COUNT IN n] [ON EXCEPTION ...].

    Data serialisation, so it moves no control and touches no file, queue or
    map: the flow graph reads nothing from it. It is modelled because the type
    is one the bridge emits, and an unmodelled type takes the whole program's
    ASG down.
    """

    xml_document: str = ""
    from_record: str = ""
    count_in: str = ""
    on_exception: list[CobolStatementType] = field(default_factory=list)
    not_on_exception: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> XmlGenerateStatement:
        return cls(
            xml_document=data.get("xml_document", ""),
            from_record=data.get("from_record", ""),
            count_in=data.get("count_in", ""),
            on_exception=[parse_statement(c) for c in data.get("on_exception", [])],
            not_on_exception=[
                parse_statement(c) for c in data.get("not_on_exception", [])
            ],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "XML_GENERATE",
            "xml_document": self.xml_document,
            "from_record": self.from_record,
        }
        if self.count_in:
            result["count_in"] = self.count_in
        if self.on_exception:
            result["on_exception"] = [c.to_dict() for c in self.on_exception]
        if self.not_on_exception:
            result["not_on_exception"] = [c.to_dict() for c in self.not_on_exception]
        if self.span is not None:
            self.span.write_into(result)
        return result


def _parse_perform_spec(
    data: dict,
) -> PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None:
    """Parse the perform_type field into a typed spec, or None if absent."""
    perform_type = data.get("perform_type", "")
    if perform_type == "TIMES":
        return PerformTimesSpec(times=expr_from_dict(data["times"]))
    if perform_type == "UNTIL":
        return PerformUntilSpec(
            condition=data.get("until", {}),
            test_before=data.get("test_before", True),
        )
    if perform_type == "VARYING":
        raw_afters = data.get("after_specs", [])
        after_specs: tuple[PerformVaryingSpec, ...] = tuple(
            PerformVaryingSpec(
                varying_var=field_ref_from_dict(a["varying_var"]),
                varying_from=expr_from_dict(a["varying_from"]),
                varying_by=expr_from_dict(a["varying_by"]),
                condition=a.get("until", {}),
            )
            for a in raw_afters
        )
        return PerformVaryingSpec(
            varying_var=field_ref_from_dict(data["varying_var"]),
            varying_from=expr_from_dict(data["varying_from"]),
            varying_by=expr_from_dict(data["varying_by"]),
            condition=data.get("until", {}),
            test_before=data.get("test_before", True),
            after_specs=after_specs,
        )
    return None


def _spec_to_dict(
    spec: PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None,
) -> dict:
    """Serialize a perform spec to dict fields."""
    if spec is None:
        return {}
    if isinstance(spec, PerformTimesSpec):
        return {"perform_type": "TIMES", "times": expr_to_dict(spec.times)}
    if isinstance(spec, PerformUntilSpec):
        return {
            "perform_type": "UNTIL",
            "until": spec.condition,
            "test_before": spec.test_before,
        }
    if isinstance(spec, PerformVaryingSpec):
        d: dict = {
            "perform_type": "VARYING",
            "varying_var": expr_to_dict(spec.varying_var),
            "varying_from": expr_to_dict(spec.varying_from),
            "varying_by": expr_to_dict(spec.varying_by),
            "until": spec.condition,
            "test_before": spec.test_before,
        }
        if spec.after_specs:
            d["after_specs"] = [
                {
                    "varying_var": expr_to_dict(a.varying_var),
                    "varying_from": expr_to_dict(a.varying_from),
                    "varying_by": expr_to_dict(a.varying_by),
                    "until": a.condition,
                }
                for a in spec.after_specs
            ]
        return d
    return {}


@dataclass(frozen=True)
class PerformStatement:
    """PERFORM [p [OF s]] [THRU p [OF s]] [TIMES|UNTIL|VARYING] [inline body]."""

    target: str = ""
    thru: str = ""
    children: list[CobolStatementType] = field(default_factory=list)
    spec: PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None = None
    span: SourceSpan | None = None
    target_section: str = ""
    thru_section: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> PerformStatement:
        operands = data.get("operands", [])
        return cls(
            target=operands[0] if operands else "",
            thru=data.get("thru", ""),
            children=[parse_statement(c) for c in data.get("children", [])],
            spec=_parse_perform_spec(data),
            span=SourceSpan.from_dict(data),
            target_section=data.get("target_section", ""),
            thru_section=data.get("thru_section", ""),
        )

    def to_dict(self) -> dict:
        present = {
            name: value
            for name, value, written in (
                ("operands", [self.target], self.target),
                ("thru", self.thru, self.thru),
                ("target_section", self.target_section, self.target_section),
                ("thru_section", self.thru_section, self.thru_section),
                ("children", [c.to_dict() for c in self.children], self.children),
            )
            if written
        }
        result: dict = {"type": "PERFORM", **present, **_spec_to_dict(self.spec)}
        if self.span is not None:
            self.span.write_into(result)
        return result


# ── Dispatch ─────────────────────────────────────────────────────

_ARITHMETIC_TYPES = frozenset({"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"})

_DISPATCH_TABLE: dict[str, type] = {
    "MOVE": MoveStatement,
    "MOVE_CORRESPONDING": MoveCorrespondingStatement,
    "ADD_CORRESPONDING": ArithmeticCorrespondingStatement,
    "SUBTRACT_CORRESPONDING": ArithmeticCorrespondingStatement,
    "ADD": ArithmeticStatement,
    "SUBTRACT": ArithmeticStatement,
    "MULTIPLY": ArithmeticStatement,
    "DIVIDE": ArithmeticStatement,
    "COMPUTE": ComputeStatement,
    "IF": IfStatement,
    "EVALUATE": EvaluateStatement,
    "DISPLAY": DisplayStatement,
    "GOTO": GotoStatement,
    "STOP_RUN": StopRunStatement,
    "GOBACK": GobackStatement,
    "EXIT_PROGRAM": ExitProgramStatement,
    "PERFORM": PerformStatement,
    "WHEN": WhenStatement,
    "WHEN_OTHER": WhenOtherStatement,
    "CONTINUE": ContinueStatement,
    "EXIT": ExitStatement,
    "NEXT_SENTENCE": NextSentenceStatement,
    "INITIALIZE": InitializeStatement,
    "SET": SetStatement,
    "STRING": StringStatement,
    "UNSTRING": UnstringStatement,
    "INSPECT": InspectStatement,
    "SEARCH": SearchStatement,
    "CALL": CallStatement,
    "ALTER": AlterStatement,
    "ENTRY": EntryStatement,
    "CANCEL": CancelStatement,
    "ACCEPT": AcceptStatement,
    "OPEN": OpenStatement,
    "CLOSE": CloseStatement,
    "READ": ReadStatement,
    "WRITE": WriteStatement,
    "REWRITE": RewriteStatement,
    "START": StartStatement,
    "DELETE": DeleteStatement,
    "XML_GENERATE": XmlGenerateStatement,
}


def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement.

    A type recognized by _DISPATCH_TABLE is never second-guessed against a
    dialect parser. A type NOT in _DISPATCH_TABLE falls back to the injected
    dialect parsers (interpreter.frontend.DialectParser), in order — the first
    whose applies(data) is True gets parse(data) called.
    """
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is not None:
        return cls.from_dict(data)
    for dialect_parser in _dialect_parsers.get():
        if dialect_parser.applies(data):
            return dialect_parser.parse(data)
    raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
