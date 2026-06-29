# pyright: standard
"""Typed COBOL statement hierarchy — discriminated union of frozen dataclasses.

Replaces the flat CobolStatement god class with specific types per
statement kind. Each type carries only the fields it needs, and a
top-level parse_statement() function dispatches on the JSON 'type'
discriminator.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable, Union

from interpreter.cobol.ref_mod import (
    RefModOperand,
    FunctionCallOperand,
    is_function_operand,
)
from interpreter.cobol.cobol_expression import ExprNode, expr_from_dict, expr_to_dict
from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode

# ── CICS text parser injection ────────────────────────────────────
# Set by CobolFrontend.lower() for the duration of each parse call.
# Cicada injects parse_exec_cics_text from cics.cics_visitor via CobolFrontend.
CicsTextParserFn = Callable[[str], "tuple[str, dict[str, CicsOperand | None]]"]
_cics_text_parser: ContextVar[CicsTextParserFn | None] = ContextVar(
    "_cics_text_parser", default=None
)


@dataclass(frozen=True)
class CicsOperand:
    """A parsed EXEC CICS option value.

    is_literal=True  -> a quoted string literal (text is the inner content, no quotes).
    is_literal=False -> a bare operand: data-name, subscripted/reference-modified ref,
                        or numeric literal (text preserved verbatim).

    ``subscripts`` carries each index as a structured :class:`ExprNode`:
    a bare data-name becomes a ``FieldRefNode``, an unsigned integer becomes a
    ``LiteralNode``. Arithmetic CICS subscripts raise ValueError at parse time.
    """

    text: str
    is_literal: bool
    subscripts: tuple[ExprNode, ...] = ()
    ref_mod_start: ExprNode | None = None
    ref_mod_length: ExprNode | None = None


# ── PERFORM specs ────────────────────────────────────────────────


@dataclass(frozen=True)
class PerformTimesSpec:
    """PERFORM ... TIMES loop specification."""

    times: str  # count literal or field name


@dataclass(frozen=True)
class PerformUntilSpec:
    """PERFORM ... UNTIL loop specification."""

    condition: dict
    test_before: bool = True  # TEST BEFORE (default) vs TEST AFTER


@dataclass(frozen=True)
class PerformVaryingSpec:
    """PERFORM ... VARYING loop specification."""

    varying_var: str  # loop variable name
    varying_from: "str | dict"  # FROM value (structured expr dict, or legacy text)
    varying_by: str  # BY step value
    condition: dict
    test_before: bool = True
    after_specs: "tuple[PerformVaryingSpec, ...]" = field(default_factory=tuple)


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
    "ExecCicsStatement",
    "ExecSqlStatement",
]


# ── Statement types ──────────────────────────────────────────────


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

        return cls(source=source, targets=targets)

    def _operand_dict(self, operand: RefModOperand) -> dict:
        d: dict = {"name": operand.name}
        if operand.ref_mod_start is not None:
            d["ref_mod_start"] = self._serialize_ref_mod_expr(operand.ref_mod_start)
        if operand.ref_mod_length is not None:
            d["ref_mod_length"] = self._serialize_ref_mod_expr(operand.ref_mod_length)
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
        return {"type": "MOVE", "operands": operands}

    @staticmethod
    def _serialize_ref_mod_expr(expr) -> dict:
        """Serialize RefModExpr back to JSON dict format."""
        from interpreter.cobol.ref_mod import (
            RefModLiteral,
            RefModReference,
            RefModBinOp,
        )

        if isinstance(expr, RefModLiteral):
            return {"kind": "lit", "value": expr.value}
        elif isinstance(expr, RefModReference):
            return {"kind": "ref", "name": expr.name}
        elif isinstance(expr, RefModBinOp):
            return {
                "kind": "binop",
                "op": expr.op,
                "left": MoveStatement._serialize_ref_mod_expr(expr.left),
                "right": MoveStatement._serialize_ref_mod_expr(expr.right),
            }
        else:
            return {}


@dataclass(frozen=True)
class MoveCorrespondingStatement:
    """MOVE CORRESPONDING source TO target1 [TO target2 ...]."""

    source: str
    targets: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> MoveCorrespondingStatement:
        return cls(
            source=data.get("source", ""),
            targets=data.get("targets", []),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "MOVE_CORRESPONDING", "source": self.source}
        if self.targets:
            result["targets"] = list(self.targets)
        return result


@dataclass(frozen=True)
class ArithmeticCorrespondingStatement:
    """ADD/SUBTRACT CORRESPONDING src TO/FROM dst."""

    op: str  # "ADD" | "SUBTRACT"
    source: str  # source group name
    target: str  # target group name

    @classmethod
    def from_dict(cls, data: dict) -> "ArithmeticCorrespondingStatement":
        op = "ADD" if data.get("type") == "ADD_CORRESPONDING" else "SUBTRACT"
        return cls(
            op=op,
            source=data.get("source", ""),
            target=data.get("target", ""),
        )

    def to_dict(self) -> dict:
        return {
            "type": f"{self.op}_CORRESPONDING",
            "source": self.source,
            "target": self.target,
        }


@dataclass(frozen=True)
class ArithmeticStatement:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE source TO/FROM/BY/INTO target.

    For GIVING forms (MULTIPLY X BY Y GIVING Z), operands holds [X, Y]
    and giving holds [Z].  The result (X * Y) is stored in Z, not in Y.

    Source can be a field name with optional reference modification (1-based slice).
    """

    op: str  # "ADD" | "SUBTRACT" | "MULTIPLY" | "DIVIDE"
    source: RefModOperand
    target: RefModOperand
    giving: list[RefModOperand] = field(default_factory=list)
    on_size_error: list[CobolStatementType] = field(default_factory=list)
    not_on_size_error: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ArithmeticStatement:
        operands = data.get("operands", [])

        # Parse source operand: can be a dict with ref_mod or a plain string
        source_data = operands[0] if len(operands) > 0 else {"name": ""}
        if isinstance(source_data, str):
            source = RefModOperand(name=source_data)
        else:
            source = RefModOperand.from_dict(source_data)

        # Target operand: a structured ref object (name + subscripts + ref-mod)
        # from the bridge, or a plain string from legacy/test fixtures. Carrying
        # the full operand keeps subscripts for in-place targets like
        # `ADD X TO WS-TBL(I)` (red-dragon-6ddr).
        target_data = operands[1] if len(operands) > 1 else ""
        if isinstance(target_data, str):
            target = RefModOperand(name=target_data)
        else:
            target = RefModOperand.from_dict(target_data)

        # GIVING targets: each may be a structured ref object (carrying its own
        # subscripts, e.g. `... GIVING WS-TBL(I)`) or a plain name string.
        giving: list[RefModOperand] = []
        for g in data.get("giving", []):
            if isinstance(g, str):
                giving.append(RefModOperand(name=g))
            else:
                giving.append(RefModOperand.from_dict(g))

        return cls(
            op=data["type"],
            source=source,
            target=target,
            giving=giving,
            on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
            not_on_size_error=[
                parse_statement(c) for c in data.get("not_on_size_error", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": self.op,
            "operands": [self.source.to_dict(), self.target.to_dict()],
        }
        if self.giving:
            result["giving"] = [g.to_dict() for g in self.giving]
        if self.on_size_error:
            result["on_size_error"] = [c.to_dict() for c in self.on_size_error]
        if self.not_on_size_error:
            result["not_on_size_error"] = [c.to_dict() for c in self.not_on_size_error]
        return result


@dataclass(frozen=True)
class ComputeTarget:
    """A single target variable in a COMPUTE statement, with optional ROUNDED."""

    name: str
    rounded: bool = False

    @classmethod
    def from_dict(cls, data: dict | str) -> "ComputeTarget":
        if isinstance(data, str):
            return cls(name=data)
        return cls(name=data["name"], rounded=data.get("rounded", False))

    def to_dict(self) -> dict:
        d: dict = {"name": self.name}
        if self.rounded:
            d["rounded"] = True
        return d


@dataclass(frozen=True)
class ComputeStatement:
    """COMPUTE target = arithmetic-expression."""

    expression: ExprNode  # structured expression tree
    targets: list[ComputeTarget] = field(default_factory=list)  # target variable names
    on_size_error: list[CobolStatementType] = field(default_factory=list)
    not_on_size_error: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ComputeStatement:
        return cls(
            expression=expr_from_dict(data["expression"]),
            targets=[ComputeTarget.from_dict(t) for t in data.get("targets", [])],
            on_size_error=[parse_statement(c) for c in data.get("on_size_error", [])],
            not_on_size_error=[
                parse_statement(c) for c in data.get("not_on_size_error", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "COMPUTE", "expression": expr_to_dict(self.expression)}
        if self.targets:
            result["targets"] = [t.to_dict() for t in self.targets]
        if self.on_size_error:
            result["on_size_error"] = [c.to_dict() for c in self.on_size_error]
        if self.not_on_size_error:
            result["not_on_size_error"] = [c.to_dict() for c in self.not_on_size_error]
        return result


@dataclass(frozen=True)
class IfStatement:
    """IF condition ... [ELSE ...] END-IF."""

    condition: dict
    children: list[CobolStatementType] = field(default_factory=list)
    else_children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> IfStatement:
        return cls(
            condition=data.get("condition", {}),
            children=[parse_statement(c) for c in data.get("children", [])],
            else_children=[parse_statement(c) for c in data.get("else_children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "IF", "condition": self.condition}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.else_children:
            result["else_children"] = [c.to_dict() for c in self.else_children]
        return result


@dataclass(frozen=True)
class WhenStatement:
    """EVALUATE / SEARCH WHEN branch.

    ``condition`` is a structured condition dict (from ``serializeConditionNode``)
    for full conditional expressions (e.g. ``EVALUATE TRUE WHEN A = SPACES``), or a
    plain string for ``EVALUATE <subject> WHEN <value>`` (the value is prefixed
    with ``subject = `` during lowering) and ``WHEN ANY``.

    ``also_conditions`` holds additional ALSO conditions from multi-subject
    EVALUATE (e.g. ``WHEN x ALSO y`` → condition="x", also_conditions=("y",)).
    """

    condition: dict | str
    also_conditions: tuple[dict | str, ...] = ()
    children: list[CobolStatementType] = field(default_factory=list)
    condition_thru: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> WhenStatement:
        raw_also = data.get("also_conditions", [])
        return cls(
            condition=data.get("condition", ""),
            also_conditions=tuple(raw_also),
            children=[parse_statement(c) for c in data.get("children", [])],
            condition_thru=data.get("condition_thru"),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WHEN", "condition": self.condition}
        if self.condition_thru is not None:
            result["condition_thru"] = self.condition_thru
        if self.also_conditions:
            result["also_conditions"] = list(self.also_conditions)
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass(frozen=True)
class WhenOtherStatement:
    """EVALUATE WHEN OTHER branch."""

    children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WhenOtherStatement:
        return cls(
            children=[parse_statement(c) for c in data.get("children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WHEN_OTHER"}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass(frozen=True)
class EvaluateStatement:
    """EVALUATE subject [ALSO also_subject ...] WHEN ... END-EVALUATE.

    ``also_subjects`` holds additional ALSO subjects for multi-subject EVALUATE
    (e.g. ``EVALUATE a ALSO b`` → subject="a", also_subjects=("b",)).
    """

    subject: str = ""
    also_subjects: tuple[str, ...] = ()
    children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> EvaluateStatement:
        return cls(
            subject=data.get("subject", ""),
            also_subjects=tuple(data.get("also_subjects", [])),
            children=[parse_statement(c) for c in data.get("children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "EVALUATE"}
        if self.subject:
            result["subject"] = self.subject
        if self.also_subjects:
            result["also_subjects"] = list(self.also_subjects)
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass(frozen=True)
class DisplayStatement:
    """DISPLAY operand [operand ...] — operands are concatenated onto one line."""

    operands: tuple[RefModOperand, ...]

    @classmethod
    def from_dict(cls, data: dict) -> DisplayStatement:
        return cls(
            operands=tuple(
                RefModOperand.from_dict({"name": raw} if isinstance(raw, str) else raw)
                for raw in data.get("operands", [])
            )
        )

    def to_dict(self) -> dict:
        return {"type": "DISPLAY", "operands": [op.to_dict() for op in self.operands]}


@dataclass(frozen=True)
class ProcedureRef:
    """A COBOL procedure-name: a paragraph, optionally qualified by a section.
    A bare name has section="". Procedure-names are never subscripted or
    reference-modified, so the surface is deliberately small."""

    paragraph: str
    section: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ProcedureRef":
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

    @classmethod
    def from_dict(cls, data: dict) -> GotoStatement:
        form_kind = data.get("form")
        if form_kind == "computed":
            targets = tuple(ProcedureRef.from_dict(t) for t in data.get("targets", []))
            index = RefModOperand.from_dict(data.get("index", {}))
            return cls(form=ComputedGoto(targets=targets, index=index))
        if form_kind == "altered":
            return cls(form=AlteredGoto())
        return cls(
            form=SimpleGoto(target=ProcedureRef.from_dict(data.get("target", {})))
        )

    def to_dict(self) -> dict:
        form = self.form
        if isinstance(form, ComputedGoto):
            return {
                "type": "GOTO",
                "form": "computed",
                "targets": [t.to_dict() for t in form.targets],
                "index": form.index.to_dict(),
            }
        if isinstance(form, AlteredGoto):
            return {"type": "GOTO", "form": "altered"}
        return {"type": "GOTO", "form": "simple", "target": form.target.to_dict()}


@dataclass(frozen=True)
class StopRunStatement:
    """STOP RUN."""

    @classmethod
    def from_dict(cls, data: dict) -> StopRunStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "STOP_RUN"}


@dataclass(frozen=True)
class GobackStatement:
    """GOBACK — return control to the caller (or terminate if called as main program)."""

    @classmethod
    def from_dict(cls, data: dict) -> GobackStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "GOBACK"}


@dataclass(frozen=True)
class ExitProgramStatement:
    """EXIT PROGRAM — return control to the caller (no-op in main program)."""

    @classmethod
    def from_dict(cls, data: dict) -> ExitProgramStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "EXIT_PROGRAM"}


@dataclass(frozen=True)
class ContinueStatement:
    """CONTINUE — no-op sentinel."""

    @classmethod
    def from_dict(cls, data: dict) -> ContinueStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "CONTINUE"}


@dataclass(frozen=True)
class ExitStatement:
    """EXIT — no-op sentinel at paragraph end."""

    @classmethod
    def from_dict(cls, data: dict) -> ExitStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "EXIT"}


@dataclass(frozen=True)
class InitializeStatement:
    """INITIALIZE field1 field2 ... — reset fields to type-appropriate defaults."""

    operands: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> InitializeStatement:
        return cls(operands=data.get("operands", []))

    def to_dict(self) -> dict:
        return {"type": "INITIALIZE", "operands": list(self.operands)}


@dataclass(frozen=True)
class SetStatement:
    """SET target TO value / SET target UP|DOWN BY value."""

    set_type: str  # "TO" or "BY"
    targets: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    by_type: str = ""  # "UP" or "DOWN" (only for BY)

    @classmethod
    def from_dict(cls, data: dict) -> SetStatement:
        return cls(
            set_type=data.get("set_type", ""),
            targets=data.get("targets", []),
            values=(
                data.get("values", [data.get("value", "")])
                if data.get("set_type") == "TO"
                else [data.get("value", "")]
            ),
            by_type=data.get("by_type", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "SET",
            "set_type": self.set_type,
            "targets": list(self.targets),
        }
        if self.set_type == "TO":
            result["values"] = list(self.values)
        else:
            result["by_type"] = self.by_type
            result["value"] = self.values[0] if self.values else ""
        return result


# ── String operation nested types ─────────────────────────────────


@dataclass(frozen=True)
class StringSending:
    """A single sending phrase in a STRING statement.

    The sending operand is usually a field reference / literal (``value``), but
    it may also be an intrinsic ``FUNCTION`` call — e.g.
    ``STRING FUNCTION TRIM(WS-VAR) ' ...' INTO WS-MSG`` — in which case
    ``function`` is populated and lowering evaluates the call (red-dragon-zuhj).
    """

    value: RefModOperand
    delimited_by: str  # e.g. "SIZE", "SPACES", or a literal
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
            delimited_by=data.get("delimited_by", "SIZE"),
            function=function,
        )

    def to_dict(self) -> dict:
        result = {"value": self.value.to_dict(), "delimited_by": self.delimited_by}
        if self.function is not None:
            result["value"] = {
                "kind": "function",
                "name": self.function.name,
                "args": list(self.function.args),
            }
        return result


@dataclass(frozen=True)
class StringStatement:
    """STRING ... DELIMITED BY ... INTO target."""

    sendings: list[StringSending] = field(default_factory=list)
    into: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> StringStatement:
        return cls(
            sendings=[StringSending.from_dict(s) for s in data.get("sendings", [])],
            into=data.get("into", ""),
        )

    def to_dict(self) -> dict:
        return {
            "type": "STRING",
            "sendings": [s.to_dict() for s in self.sendings],
            "into": self.into,
        }


@dataclass(frozen=True)
class UnstringStatement:
    """UNSTRING source DELIMITED BY ... INTO targets."""

    source: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    delimited_by: str = ""
    into: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> UnstringStatement:
        return cls(
            source=RefModOperand.from_dict(data.get("source", {})),
            delimited_by=data.get("delimited_by", ""),
            into=data.get("into", []),
        )

    def to_dict(self) -> dict:
        return {
            "type": "UNSTRING",
            "source": self.source.to_dict(),
            "delimited_by": self.delimited_by,
            "into": list(self.into),
        }


@dataclass(frozen=True)
class TallyingFor:
    """A single tallying pattern in INSPECT TALLYING."""

    mode: str  # "ALL", "LEADING", "CHARACTERS"
    pattern: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> TallyingFor:
        return cls(mode=data.get("mode", ""), pattern=data.get("pattern", ""))

    def to_dict(self) -> dict:
        return {"mode": self.mode, "pattern": self.pattern}


@dataclass(frozen=True)
class Replacing:
    """A single replacing item in INSPECT REPLACING."""

    mode: str  # "ALL", "LEADING", "FIRST"
    from_pattern: str = ""
    to_pattern: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Replacing:
        return cls(
            mode=data.get("mode", ""),
            from_pattern=data.get("from", ""),
            to_pattern=data.get("to", ""),
        )

    def to_dict(self) -> dict:
        return {"mode": self.mode, "from": self.from_pattern, "to": self.to_pattern}


@dataclass(frozen=True)
class InspectStatement:
    """INSPECT source TALLYING|REPLACING ..."""

    inspect_type: str = ""  # "TALLYING", "REPLACING", or "CONVERTING"
    source: RefModOperand = field(default_factory=lambda: RefModOperand(name=""))
    tallying_target: str = ""
    tallying_for: list[TallyingFor] = field(default_factory=list)
    replacings: list[Replacing] = field(default_factory=list)
    converting_from: str = ""  # INSPECT ... CONVERTING <from> TO <to>
    converting_to: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> InspectStatement:
        return cls(
            inspect_type=data.get("inspect_type", ""),
            source=RefModOperand.from_dict(data.get("source", {})),
            tallying_target=data.get("tallying_target", ""),
            tallying_for=[
                TallyingFor.from_dict(t) for t in data.get("tallying_for", [])
            ],
            replacings=[Replacing.from_dict(r) for r in data.get("replacings", [])],
            converting_from=data.get("converting_from", ""),
            converting_to=data.get("converting_to", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "INSPECT",
            "inspect_type": self.inspect_type,
            "source": self.source.to_dict(),
        }
        if self.inspect_type == "TALLYING":
            result["tallying_target"] = self.tallying_target
            result["tallying_for"] = [t.to_dict() for t in self.tallying_for]
        elif self.inspect_type == "REPLACING":
            result["replacings"] = [r.to_dict() for r in self.replacings]
        elif self.inspect_type == "CONVERTING":
            result["converting_from"] = self.converting_from
            result["converting_to"] = self.converting_to
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
    """SEARCH table [VARYING index] WHEN condition ... [AT END ...]."""

    table: str = ""
    varying: str = ""
    whens: list[SearchWhen] = field(default_factory=list)
    at_end: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SearchStatement:
        return cls(
            table=data.get("table", ""),
            varying=data.get("varying", ""),
            whens=[SearchWhen.from_dict(w) for w in data.get("whens", [])],
            at_end=[parse_statement(c) for c in data.get("at_end", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "SEARCH", "table": self.table}
        if self.varying:
            result["varying"] = self.varying
        result["whens"] = [w.to_dict() for w in self.whens]
        if self.at_end:
            result["at_end"] = [c.to_dict() for c in self.at_end]
        return result


@dataclass(frozen=True)
class CallUsingParam:
    """A single USING parameter in a CALL statement."""

    name: str
    param_type: str = "REFERENCE"  # REFERENCE, CONTENT, or VALUE
    omitted: bool = False
    is_literal: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> CallUsingParam:
        return cls(
            name=data.get("name", ""),
            param_type=data.get("type", "REFERENCE"),
            omitted=data.get("omitted", False),
            is_literal=data.get("is_literal", False),
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name, "type": self.param_type}
        if self.omitted:
            result["omitted"] = True
        if self.is_literal:
            result["is_literal"] = True
        return result


@dataclass(frozen=True)
class CallStatement:
    """CALL 'program' [USING params] [GIVING target]."""

    program: str = ""
    using: list[CallUsingParam] = field(default_factory=list)
    giving: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> CallStatement:
        return cls(
            program=data.get("program", ""),
            using=[CallUsingParam.from_dict(p) for p in data.get("using", [])],
            giving=data.get("giving", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "CALL", "program": self.program}
        if self.using:
            result["using"] = [p.to_dict() for p in self.using]
        if self.giving:
            result["giving"] = self.giving
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

    @classmethod
    def from_dict(cls, data: dict) -> AlterStatement:
        return cls(
            proceed_tos=[
                AlterProceedTo.from_dict(p) for p in data.get("proceed_tos", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ALTER"}
        if self.proceed_tos:
            result["proceed_tos"] = [p.to_dict() for p in self.proceed_tos]
        return result


@dataclass(frozen=True)
class EntryStatement:
    """ENTRY 'name' [USING params]."""

    entry_name: str = ""
    using: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> EntryStatement:
        return cls(
            entry_name=data.get("entry_name", ""),
            using=data.get("using", []),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ENTRY", "entry_name": self.entry_name}
        if self.using:
            result["using"] = self.using
        return result


@dataclass(frozen=True)
class CancelStatement:
    """CANCEL program-name(s)."""

    programs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CancelStatement:
        return cls(programs=data.get("programs", []))

    def to_dict(self) -> dict:
        return {"type": "CANCEL", "programs": self.programs}


# ── I/O Statement types ─────────────────────────────────────────


@dataclass(frozen=True)
class AcceptStatement:
    """ACCEPT target [FROM device]."""

    target: str = ""
    from_device: str = "CONSOLE"

    @classmethod
    def from_dict(cls, data: dict) -> AcceptStatement:
        return cls(
            target=data.get("target", ""),
            from_device=data.get("from_device", "CONSOLE"),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "ACCEPT", "target": self.target}
        if self.from_device != "CONSOLE":
            result["from_device"] = self.from_device
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
class OpenStatement:
    """OPEN [mode file1 file2 ...] ... — one or more mode groups."""

    mode_groups: list[tuple[OpenMode, list[str]]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> OpenStatement:
        groups = [
            (OpenMode(g["mode"]), list(g["files"])) for g in data.get("mode_groups", [])
        ]
        return cls(mode_groups=groups)

    def to_dict(self) -> dict:
        return {
            "type": "OPEN",
            "mode_groups": [
                {"mode": mode.value, "files": list(files)}
                for mode, files in self.mode_groups
            ],
        }


@dataclass(frozen=True)
class CloseStatement:
    """CLOSE file1 file2 ..."""

    files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CloseStatement:
        return cls(files=data.get("files", []))

    def to_dict(self) -> dict:
        return {"type": "CLOSE", "files": list(self.files)}


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
        return result


@dataclass(frozen=True)
class WriteStatement:
    """WRITE record-name [FROM field] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    record_name: str = ""
    from_field: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result


@dataclass(frozen=True)
class RewriteStatement:
    """REWRITE record-name [FROM field] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    record_name: str = ""
    from_field: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> RewriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "REWRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result


@dataclass(frozen=True)
class StartStatement:
    """START file-name [KEY relop key] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    file_name: str = ""
    key: str = ""
    relop: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

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
        return result


@dataclass(frozen=True)
class DeleteStatement:
    """DELETE file-name [RECORD] [INVALID KEY ...] [NOT INVALID KEY ...]."""

    file_name: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> DeleteStatement:
        return cls(
            file_name=data.get("file_name", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[
                parse_statement(c) for c in data.get("not_invalid_key", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "DELETE", "file_name": self.file_name}
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result


@dataclass(frozen=True)
class ExecCicsStatement:
    """EXEC CICS verb-with-options block."""

    verb: str
    options: dict[str, "CicsOperand | None"]

    @classmethod
    def from_dict(cls, data: dict) -> "ExecCicsStatement":
        parser = _cics_text_parser.get()
        if parser is None:
            raise RuntimeError(
                "No CICS text parser injected — pass cics_text_parser= to CobolFrontend"
            )
        text = data.get("exec_cics_text", "")
        verb, options = parser(text)
        return cls(verb=verb, options=options)

    def to_dict(self) -> dict:
        # Serialise each operand structurally so the ASG export stays JSON-safe;
        # a bare flag (None) is preserved. (Roundtrip is via exec_cics_text, not
        # this options view, so this is informational only.)
        serialised = {
            key: (
                None
                if operand is None
                else {"text": operand.text, "is_literal": operand.is_literal}
            )
            for key, operand in self.options.items()
        }
        return {"type": "EXEC_CICS", "verb": self.verb, "options": serialised}


@dataclass(frozen=True)
class ExecSqlStatement:
    """EXEC SQL block. Carries the raw EXEC SQL text verbatim — including the
    ``EXEC SQL``/``END-EXEC`` envelope — exactly as the ProLeap bridge emits it.
    The COBOL frontend treats the SQL body as opaque text: envelope removal and
    SQL parsing are done later by the injected SQL strategy's grammar-based parser
    (squall), never by string surgery here."""

    text: str  # raw EXEC SQL text verbatim, envelope included

    @classmethod
    def from_dict(cls, data: dict) -> "ExecSqlStatement":
        return cls(text=data.get("exec_sql_text", "") or "")

    def to_dict(self) -> dict:
        return {"type": "EXEC_SQL", "text": self.text}


def _parse_perform_spec(
    data: dict,
) -> PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None:
    """Parse the perform_type field into a typed spec, or None if absent."""
    perform_type = data.get("perform_type", "")
    if perform_type == "TIMES":
        return PerformTimesSpec(times=data.get("times", ""))
    if perform_type == "UNTIL":
        return PerformUntilSpec(
            condition=data.get("until", {}),
            test_before=data.get("test_before", True),
        )
    if perform_type == "VARYING":
        raw_afters = data.get("after_specs", [])
        after_specs: tuple[PerformVaryingSpec, ...] = tuple(
            PerformVaryingSpec(
                varying_var=a.get("varying_var", ""),
                varying_from=a.get("varying_from", ""),
                varying_by=a.get("varying_by", ""),
                condition=a.get("until", {}),
            )
            for a in raw_afters
        )
        return PerformVaryingSpec(
            varying_var=data.get("varying_var", ""),
            varying_from=data.get("varying_from", ""),
            varying_by=data.get("varying_by", ""),
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
        return {"perform_type": "TIMES", "times": spec.times}
    if isinstance(spec, PerformUntilSpec):
        return {
            "perform_type": "UNTIL",
            "until": spec.condition,
            "test_before": spec.test_before,
        }
    if isinstance(spec, PerformVaryingSpec):
        d: dict = {
            "perform_type": "VARYING",
            "varying_var": spec.varying_var,
            "varying_from": spec.varying_from,
            "varying_by": spec.varying_by,
            "until": spec.condition,
            "test_before": spec.test_before,
        }
        if spec.after_specs:
            d["after_specs"] = [
                {
                    "varying_var": a.varying_var,
                    "varying_from": a.varying_from,
                    "varying_by": a.varying_by,
                    "until": a.condition,
                }
                for a in spec.after_specs
            ]
        return d
    return {}


@dataclass(frozen=True)
class PerformStatement:
    """PERFORM [target] [THRU target] [TIMES|UNTIL|VARYING] [inline body]."""

    target: str = ""
    thru: str = ""
    children: list[CobolStatementType] = field(default_factory=list)
    spec: PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None = None

    @classmethod
    def from_dict(cls, data: dict) -> PerformStatement:
        operands = data.get("operands", [])
        return cls(
            target=operands[0] if operands else "",
            thru=data.get("thru", ""),
            children=[parse_statement(c) for c in data.get("children", [])],
            spec=_parse_perform_spec(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "PERFORM"}
        if self.target:
            result["operands"] = [self.target]
        if self.thru:
            result["thru"] = self.thru
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        result.update(_spec_to_dict(self.spec))
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
    "EXEC_CICS": ExecCicsStatement,
    "EXEC_SQL": ExecSqlStatement,
}


def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement."""
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is None:
        raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
    return cls.from_dict(data)
