"""Typed COBOL statement hierarchy — discriminated union of frozen dataclasses.

Replaces the flat CobolStatement god class with specific types per
statement kind. Each type carries only the fields it needs, and a
top-level parse_statement() function dispatches on the JSON 'type'
discriminator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

# ── PERFORM specs ────────────────────────────────────────────────


@dataclass(frozen=True)
class PerformTimesSpec:
    """PERFORM ... TIMES loop specification."""

    times: str  # count literal or field name


@dataclass(frozen=True)
class PerformUntilSpec:
    """PERFORM ... UNTIL loop specification."""

    condition: str  # until condition string
    test_before: bool = True  # TEST BEFORE (default) vs TEST AFTER


@dataclass(frozen=True)
class PerformVaryingSpec:
    """PERFORM ... VARYING loop specification."""

    varying_var: str  # loop variable name
    varying_from: str  # FROM value
    varying_by: str  # BY step value
    condition: str  # UNTIL condition
    test_before: bool = True


PerformSpec = Union[PerformTimesSpec, PerformUntilSpec, PerformVaryingSpec]


# Forward reference for recursive types — resolved after all classes defined.
CobolStatementType = Union[
    "MoveStatement",
    "ArithmeticStatement",
    "ComputeStatement",
    "IfStatement",
    "EvaluateStatement",
    "DisplayStatement",
    "GotoStatement",
    "StopRunStatement",
    "PerformStatement",
    "WhenStatement",
    "WhenOtherStatement",
    "ContinueStatement",
    "ExitStatement",
    "InitializeStatement",
    "SetStatement",
    "StringStatement",
    "UnstringStatement",
    "InspectStatement",
]


# ── Statement types ──────────────────────────────────────────────


@dataclass(frozen=True)
class MoveStatement:
    """MOVE source TO target."""

    source: str
    target: str

    @classmethod
    def from_dict(cls, data: dict) -> MoveStatement:
        operands = data.get("operands", [])
        return cls(
            source=operands[0] if len(operands) > 0 else "",
            target=operands[1] if len(operands) > 1 else "",
        )

    def to_dict(self) -> dict:
        return {"type": "MOVE", "operands": [self.source, self.target]}


@dataclass(frozen=True)
class ArithmeticStatement:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE source TO/FROM/BY/INTO target."""

    op: str  # "ADD" | "SUBTRACT" | "MULTIPLY" | "DIVIDE"
    source: str
    target: str

    @classmethod
    def from_dict(cls, data: dict) -> ArithmeticStatement:
        operands = data.get("operands", [])
        return cls(
            op=data["type"],
            source=operands[0] if len(operands) > 0 else "",
            target=operands[1] if len(operands) > 1 else "",
        )

    def to_dict(self) -> dict:
        return {"type": self.op, "operands": [self.source, self.target]}


@dataclass(frozen=True)
class ComputeStatement:
    """COMPUTE target = arithmetic-expression."""

    expression: str  # e.g. "WS-A + WS-B * 2"
    targets: list[str] = field(default_factory=list)  # target variable names

    @classmethod
    def from_dict(cls, data: dict) -> ComputeStatement:
        return cls(
            expression=data.get("expression", ""),
            targets=data.get("targets", []),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "COMPUTE", "expression": self.expression}
        if self.targets:
            result["targets"] = list(self.targets)
        return result


@dataclass(frozen=True)
class IfStatement:
    """IF condition ... [ELSE ...] END-IF."""

    condition: str
    children: list[CobolStatementType] = field(default_factory=list)
    else_children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> IfStatement:
        return cls(
            condition=data.get("condition", ""),
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
    """EVALUATE WHEN branch."""

    condition: str
    children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WhenStatement:
        return cls(
            condition=data.get("condition", ""),
            children=[parse_statement(c) for c in data.get("children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WHEN", "condition": self.condition}
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
    """EVALUATE ... WHEN ... END-EVALUATE."""

    children: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> EvaluateStatement:
        return cls(
            children=[parse_statement(c) for c in data.get("children", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "EVALUATE"}
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


@dataclass(frozen=True)
class DisplayStatement:
    """DISPLAY operand."""

    operand: str

    @classmethod
    def from_dict(cls, data: dict) -> DisplayStatement:
        operands = data.get("operands", [])
        return cls(operand=operands[0] if operands else "")

    def to_dict(self) -> dict:
        return {"type": "DISPLAY", "operands": [self.operand]}


@dataclass(frozen=True)
class GotoStatement:
    """GO TO target."""

    target: str

    @classmethod
    def from_dict(cls, data: dict) -> GotoStatement:
        operands = data.get("operands", [])
        return cls(target=operands[0] if operands else "")

    def to_dict(self) -> dict:
        return {"type": "GOTO", "operands": [self.target]}


@dataclass(frozen=True)
class StopRunStatement:
    """STOP RUN."""

    @classmethod
    def from_dict(cls, data: dict) -> StopRunStatement:
        return cls()

    def to_dict(self) -> dict:
        return {"type": "STOP_RUN"}


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
    """A single sending phrase in a STRING statement."""

    value: str
    delimited_by: str  # e.g. "SIZE", "SPACES", or a literal

    @classmethod
    def from_dict(cls, data: dict) -> StringSending:
        return cls(
            value=data.get("value", ""),
            delimited_by=data.get("delimited_by", "SIZE"),
        )

    def to_dict(self) -> dict:
        return {"value": self.value, "delimited_by": self.delimited_by}


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

    source: str = ""
    delimited_by: str = ""
    into: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> UnstringStatement:
        return cls(
            source=data.get("source", ""),
            delimited_by=data.get("delimited_by", ""),
            into=data.get("into", []),
        )

    def to_dict(self) -> dict:
        return {
            "type": "UNSTRING",
            "source": self.source,
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

    inspect_type: str = ""  # "TALLYING" or "REPLACING"
    source: str = ""
    tallying_target: str = ""
    tallying_for: list[TallyingFor] = field(default_factory=list)
    replacings: list[Replacing] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> InspectStatement:
        return cls(
            inspect_type=data.get("inspect_type", ""),
            source=data.get("source", ""),
            tallying_target=data.get("tallying_target", ""),
            tallying_for=[
                TallyingFor.from_dict(t) for t in data.get("tallying_for", [])
            ],
            replacings=[Replacing.from_dict(r) for r in data.get("replacings", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {
            "type": "INSPECT",
            "inspect_type": self.inspect_type,
            "source": self.source,
        }
        if self.inspect_type == "TALLYING":
            result["tallying_target"] = self.tallying_target
            result["tallying_for"] = [t.to_dict() for t in self.tallying_for]
        elif self.inspect_type == "REPLACING":
            result["replacings"] = [r.to_dict() for r in self.replacings]
        return result


def _parse_perform_spec(
    data: dict,
) -> PerformTimesSpec | PerformUntilSpec | PerformVaryingSpec | None:
    """Parse the perform_type field into a typed spec, or None if absent."""
    perform_type = data.get("perform_type", "")
    if perform_type == "TIMES":
        return PerformTimesSpec(times=data.get("times", ""))
    if perform_type == "UNTIL":
        return PerformUntilSpec(
            condition=data.get("until", ""),
            test_before=data.get("test_before", True),
        )
    if perform_type == "VARYING":
        return PerformVaryingSpec(
            varying_var=data.get("varying_var", ""),
            varying_from=data.get("varying_from", ""),
            varying_by=data.get("varying_by", ""),
            condition=data.get("until", ""),
            test_before=data.get("test_before", True),
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
        return {
            "perform_type": "VARYING",
            "varying_var": spec.varying_var,
            "varying_from": spec.varying_from,
            "varying_by": spec.varying_by,
            "until": spec.condition,
            "test_before": spec.test_before,
        }
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
}


def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement."""
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is None:
        raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
    return cls.from_dict(data)
