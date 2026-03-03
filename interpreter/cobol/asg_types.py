"""COBOL ASG types — frozen dataclasses defining the JSON contract.

These dataclasses represent the Abstract Semantic Graph produced by
the ProLeap bridge (Java/ANTLR4). The bridge parses COBOL source and
emits JSON to stdout; these types consume that JSON via from_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interpreter.cobol.cobol_statements import CobolStatementType, parse_statement
from interpreter.cobol.condition_name import ConditionName, ConditionValue


@dataclass(frozen=True)
class CobolField:
    """A COBOL DATA DIVISION field (elementary or group item).

    Attributes:
        name: Field name (e.g. "WS-DATE").
        level: Level number (01, 05, 77, 88, etc.).
        pic: PIC clause string (e.g. "9(4)", "X(8)", "S9(5)V99").
        usage: USAGE clause ("DISPLAY", "COMP-3", "COMP").
        offset: Byte offset within parent group.
        value: Initial VALUE clause content, or empty string.
        redefines: Name of field being redefined, or empty string.
        children: Child fields for group items.
    """

    name: str
    level: int
    pic: str
    usage: str
    offset: int
    value: str = ""
    redefines: str = ""
    children: list[CobolField] = field(default_factory=list)
    occurs: int = 0
    element_size: int = 0
    conditions: list[ConditionName] = field(default_factory=list)
    values: list[ConditionValue] = field(default_factory=list)
    sign_leading: bool = False
    sign_separate: bool = False
    justified_right: bool = False
    synchronized: bool = False
    occurs_depending_on: str = ""
    occurs_min: int = 0
    renames_from: str = ""
    renames_thru: str = ""
    blank_when_zero: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> CobolField:
        sign_data = data.get("sign", {})
        return cls(
            name=data["name"],
            level=data["level"],
            pic=data.get("pic", ""),
            usage=data.get("usage", "DISPLAY"),
            offset=data.get("offset", 0),
            value=data.get("value", ""),
            redefines=data.get("redefines", ""),
            children=[CobolField.from_dict(c) for c in data.get("children", [])],
            occurs=data.get("occurs", 0),
            element_size=data.get("element_size", 0),
            conditions=[ConditionName.from_dict(c) for c in data.get("conditions", [])],
            values=[ConditionValue.from_dict(v) for v in data.get("values", [])],
            sign_leading=sign_data.get("position", "") == "LEADING",
            sign_separate=sign_data.get("separate", False),
            justified_right=data.get("justified_right", False),
            synchronized=data.get("synchronized", False),
            occurs_depending_on=data.get("occurs_depending_on", ""),
            occurs_min=data.get("occurs_min", 0),
            renames_from=data.get("renames_from", ""),
            renames_thru=data.get("renames_thru", ""),
            blank_when_zero=data.get("blank_when_zero", False),
        )

    def to_dict(self) -> dict:
        result: dict = {
            "name": self.name,
            "level": self.level,
            "pic": self.pic,
            "usage": self.usage,
            "offset": self.offset,
        }
        if self.value:
            result["value"] = self.value
        if self.redefines:
            result["redefines"] = self.redefines
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.occurs:
            result["occurs"] = self.occurs
        if self.element_size:
            result["element_size"] = self.element_size
        if self.conditions:
            result["conditions"] = [c.to_dict() for c in self.conditions]
        if self.values:
            result["values"] = [v.to_dict() for v in self.values]
        if self.sign_leading or self.sign_separate:
            result["sign"] = {
                "position": "LEADING" if self.sign_leading else "TRAILING",
                "separate": self.sign_separate,
            }
        if self.justified_right:
            result["justified_right"] = True
        if self.synchronized:
            result["synchronized"] = True
        if self.occurs_depending_on:
            result["occurs_depending_on"] = self.occurs_depending_on
        if self.occurs_min:
            result["occurs_min"] = self.occurs_min
        if self.renames_from:
            result["renames_from"] = self.renames_from
        if self.renames_thru:
            result["renames_thru"] = self.renames_thru
        if self.blank_when_zero:
            result["blank_when_zero"] = True
        return result


@dataclass(frozen=True)
class CobolParagraph:
    """A COBOL paragraph — a named block of statements."""

    name: str
    statements: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CobolParagraph:
        return cls(
            name=data["name"],
            statements=[parse_statement(s) for s in data.get("statements", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.statements:
            result["statements"] = [s.to_dict() for s in self.statements]
        return result


@dataclass(frozen=True)
class CobolSection:
    """A COBOL PROCEDURE DIVISION section containing paragraphs."""

    name: str
    paragraphs: list[CobolParagraph] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CobolSection:
        return cls(
            name=data["name"],
            paragraphs=[
                CobolParagraph.from_dict(p) for p in data.get("paragraphs", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.paragraphs:
            result["paragraphs"] = [p.to_dict() for p in self.paragraphs]
        return result


@dataclass(frozen=True)
class CobolASG:
    """Complete COBOL Abstract Semantic Graph.

    Attributes:
        data_fields: Working-Storage Section fields.
        sections: Procedure Division sections.
        paragraphs: Standalone paragraphs (no section).
    """

    data_fields: list[CobolField] = field(default_factory=list)
    sections: list[CobolSection] = field(default_factory=list)
    paragraphs: list[CobolParagraph] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CobolASG:
        return cls(
            data_fields=[CobolField.from_dict(f) for f in data.get("data_fields", [])],
            sections=[CobolSection.from_dict(s) for s in data.get("sections", [])],
            paragraphs=[
                CobolParagraph.from_dict(p) for p in data.get("paragraphs", [])
            ],
        )

    def to_dict(self) -> dict:
        result: dict = {}
        if self.data_fields:
            result["data_fields"] = [f.to_dict() for f in self.data_fields]
        if self.sections:
            result["sections"] = [s.to_dict() for s in self.sections]
        if self.paragraphs:
            result["paragraphs"] = [p.to_dict() for p in self.paragraphs]
        return result
