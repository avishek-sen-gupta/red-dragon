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

    @classmethod
    def from_dict(cls, data: dict) -> CallUsingParam:
        return cls(
            name=data.get("name", ""),
            param_type=data.get("type", "REFERENCE"),
        )

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.param_type}


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
class OpenStatement:
    """OPEN mode file1 file2 ..."""

    mode: str = ""  # INPUT, OUTPUT, I-O, EXTEND
    files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> OpenStatement:
        return cls(
            mode=data.get("mode", ""),
            files=data.get("files", []),
        )

    def to_dict(self) -> dict:
        return {"type": "OPEN", "mode": self.mode, "files": list(self.files)}


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
    """READ file-name [INTO target]."""

    file_name: str = ""
    into: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> ReadStatement:
        return cls(
            file_name=data.get("file_name", ""),
            into=data.get("into", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "READ", "file_name": self.file_name}
        if self.into:
            result["into"] = self.into
        return result


@dataclass(frozen=True)
class WriteStatement:
    """WRITE record-name [FROM field]."""

    record_name: str = ""
    from_field: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> WriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        return result


@dataclass(frozen=True)
class RewriteStatement:
    """REWRITE record-name [FROM field]."""

    record_name: str = ""
    from_field: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> RewriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "REWRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        return result


@dataclass(frozen=True)
class StartStatement:
    """START file-name [KEY condition]."""

    file_name: str = ""
    key: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> StartStatement:
        return cls(
            file_name=data.get("file_name", ""),
            key=data.get("key", ""),
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "START", "file_name": self.file_name}
        if self.key:
            result["key"] = self.key
        return result


@dataclass(frozen=True)
class DeleteStatement:
    """DELETE file-name [RECORD]."""

    file_name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> DeleteStatement:
        return cls(file_name=data.get("file_name", ""))

    def to_dict(self) -> dict:
        return {"type": "DELETE", "file_name": self.file_name}


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
}


def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement."""
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is None:
        raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
    return cls.from_dict(data)
