# pyright: standard
"""COBOL ASG types — frozen dataclasses defining the JSON contract.

These dataclasses represent the Abstract Semantic Graph produced by
the ProLeap bridge (Java/ANTLR4). The bridge parses COBOL source and
emits JSON to stdout; these types consume that JSON via from_dict().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.alphabet import NATIVE_ALPHABET, Alphabet
from cobol_asg.cobol_statements import (
    CallUsingParam,
    CobolStatementType,
    FileControlEntry,
    FileDescription,
    parse_statement,
)
from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.condition_name import ConditionName, ConditionValue
from cobol_asg.class_definition import ClassDefinition
from cobol_asg.implementor_switch import ImplementorSwitch
from cobol_asg.edit_picture import (
    DEFAULT_CURRENCY,
    UnsupportedEditPictureError,
)
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.pic_parser import parse_pic
from cobol_asg.pointer_types import FULLWORD_POINTER
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan


def _currency_from_special_names(data: dict) -> str:
    """Read the program's currency symbol from the bridge's SPECIAL-NAMES.

    Refuses the multi-character form. IBM's
    ``CURRENCY SIGN IS 'EUR' WITH PICTURE SYMBOL '$'`` makes each picture
    symbol position occupy len(literal) BYTES, so it changes the field's
    width — and the bridge computes record offsets independently of Python's
    read lengths, with nothing reconciling them (see red-dragon-ilb6). Silently
    accepting it would mis-place every later field in the record, so refuse
    loudly instead (red-dragon-3o5f scoped it out).
    """
    special = data.get("special_names") or {}
    sign = special.get("currency_sign") or DEFAULT_CURRENCY
    if len(sign) != 1:
        raise UnsupportedEditPictureError(
            f"CURRENCY SIGN IS {sign!r} is a multi-character currency literal, "
            f"which RedDragon does not support: each picture symbol position "
            f"would occupy {len(sign)} bytes, changing every field's width. "
            f"Only a single-character currency sign is implemented."
        )
    if special.get("currency_picture_symbol"):
        raise UnsupportedEditPictureError(
            f"CURRENCY SIGN IS {sign!r} WITH PICTURE SYMBOL "
            f"{special['currency_picture_symbol']!r} is not supported: the "
            f"PICTURE SYMBOL form exists to allow a multi-character currency "
            f"literal, which changes field widths."
        )
    return sign


NOT_RENAMED = RefModOperand(name="")
NO_ODO_OBJECT = RefModOperand(name="")
NOT_COMPILED = datetime(1, 1, 1, tzinfo=UTC)


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
    value_is_figurative: bool = False
    value_is_all: bool = False
    value_is_numeric: bool = False
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
    occurs_depending_on: RefModOperand = NO_ODO_OBJECT
    occurs_min: int = 0
    # Compiler-allocated index names from OCCURS ... INDEXED BY, in declaration
    # order. Order is load-bearing: a Format 1 SEARCH advances the first one.
    indexed_by: list[str] = field(default_factory=list)
    renames_from: RefModOperand = NOT_RENAMED
    renames_thru: RefModOperand = NOT_RENAMED
    blank_when_zero: bool = False
    filler: bool = False
    # The program's currency symbol at the time this field was ingested — '$'
    # unless SPECIAL-NAMES declared CURRENCY SIGN IS otherwise. It is
    # program-scoped, not per-field, but __post_init__ computes the type
    # descriptor at construction, so it has to arrive as constructor state
    # (red-dragon-3o5f).
    currency_symbol: str = DEFAULT_CURRENCY
    # SPECIAL-NAMES DECIMAL-POINT IS COMMA, program-wide constructor state for
    # the same reason as the currency symbol.
    decimal_point_is_comma: bool = False
    span: SourceSpan | None = None
    # The addressing mode's pointer type, for a USAGE POINTER item. Like the
    # currency symbol it is program-wide but arrives as constructor state,
    # because __post_init__ computes the type descriptor.
    pointer_type: CobolTypeDescriptor = FULLWORD_POINTER
    type_descriptor: CobolTypeDescriptor = field(init=False)

    def __post_init__(self) -> None:
        # Parse the PIC clause exactly ONCE, at ingestion, into the canonical
        # type descriptor. Frozen dataclass -> set via object.__setattr__.
        try:
            descriptor = parse_pic(
                self.pic,
                self.usage,
                sign_leading=self.sign_leading,
                sign_separate=self.sign_separate,
                justified_right=self.justified_right,
                blank_when_zero=self.blank_when_zero,
                currency=self.currency_symbol,
                pointer_type=self.pointer_type,
                decimal_point_is_comma=self.decimal_point_is_comma,
            )
        except UnsupportedEditPictureError as exc:
            # parse_pic sees only the picture. This is a load-time abort, so
            # name the field too — otherwise the user has to grep the program
            # for the picture to find out what failed (red-dragon-0599).
            raise UnsupportedEditPictureError(f"field {self.name}: {exc}") from exc
        object.__setattr__(self, "type_descriptor", descriptor)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        currency: str = DEFAULT_CURRENCY,
        pointer_type: CobolTypeDescriptor = FULLWORD_POINTER,
        decimal_point_is_comma: bool = False,
    ) -> CobolField:
        sign_data = data.get("sign", {})
        return cls(
            name=data["name"],
            level=data["level"],
            pic=data.get("pic", ""),
            usage=data.get("usage", "DISPLAY"),
            offset=data.get("offset", 0),
            value=data.get("value", ""),
            value_is_figurative=data.get("value_is_figurative", False),
            value_is_all=data.get("value_is_all", False),
            value_is_numeric=data.get("value_is_numeric", False),
            redefines=data.get("redefines", ""),
            children=[
                CobolField.from_dict(c, currency, pointer_type, decimal_point_is_comma)
                for c in data.get("children", [])
            ],
            occurs=data.get("occurs", 0),
            element_size=data.get("element_size", 0),
            conditions=[ConditionName.from_dict(c) for c in data.get("conditions", [])],
            values=[ConditionValue.from_dict(v) for v in data.get("values", [])],
            sign_leading=sign_data.get("position", "") == "LEADING",
            sign_separate=sign_data.get("separate", False),
            justified_right=data.get("justified_right", False),
            synchronized=data.get("synchronized", False),
            occurs_depending_on=RefModOperand.from_dict(
                data.get("occurs_depending_on", {})
            ),
            occurs_min=data.get("occurs_min", 0),
            indexed_by=list(data.get("indexed_by", [])),
            renames_from=RefModOperand.from_dict(data.get("renames_from", {})),
            renames_thru=RefModOperand.from_dict(data.get("renames_thru", {})),
            blank_when_zero=data.get("blank_when_zero", False),
            filler=data.get("filler", False),
            currency_symbol=currency,
            pointer_type=pointer_type,
            decimal_point_is_comma=decimal_point_is_comma,
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        sign = {
            "position": "LEADING" if self.sign_leading else "TRAILING",
            "separate": self.sign_separate,
        }
        result: dict = {
            "name": self.name,
            "level": self.level,
            "pic": self.pic,
            "usage": self.usage,
            "offset": self.offset,
            **({"value_is_all": True} if self.value_is_all else {}),
            **({"value_is_numeric": True} if self.value_is_numeric else {}),
            **({"filler": True} if self.filler else {}),
            **({"value": self.value} if self.value else {}),
            **({"value_is_figurative": True} if self.value_is_figurative else {}),
            **({"redefines": self.redefines} if self.redefines else {}),
            **(
                {"children": [c.to_dict() for c in self.children]}
                if self.children
                else {}
            ),
            **({"occurs": self.occurs} if self.occurs else {}),
            **({"element_size": self.element_size} if self.element_size else {}),
            **(
                {"conditions": [c.to_dict() for c in self.conditions]}
                if self.conditions
                else {}
            ),
            **({"values": [v.to_dict() for v in self.values]} if self.values else {}),
            **({"sign": sign} if self.sign_leading or self.sign_separate else {}),
            **({"justified_right": True} if self.justified_right else {}),
            **({"synchronized": True} if self.synchronized else {}),
            **(
                {"occurs_depending_on": self.occurs_depending_on.to_dict()}
                if self.occurs_depending_on.name
                else {}
            ),
            **({"occurs_min": self.occurs_min} if self.occurs_min else {}),
            **({"indexed_by": list(self.indexed_by)} if self.indexed_by else {}),
            **(
                {"renames_from": self.renames_from.to_dict()}
                if self.renames_from.name
                else {}
            ),
            **(
                {"renames_thru": self.renames_thru.to_dict()}
                if self.renames_thru.name
                else {}
            ),
            **({"blank_when_zero": True} if self.blank_when_zero else {}),
        }
        if self.span is not None:
            self.span.write_into(result)
        return result


@dataclass(frozen=True)
class CobolParagraph:
    """A COBOL paragraph — a named block of statements.

    ``sentence_ends`` holds the position in ``statements`` of each sentence's last
    statement: where the period falls, which NEXT SENTENCE jumps past.
    """

    name: str
    statements: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None
    sentence_ends: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> CobolParagraph:
        return cls(
            name=data["name"],
            statements=[parse_statement(s) for s in data.get("statements", [])],
            span=SourceSpan.from_dict(data),
            sentence_ends=list(data.get("sentence_ends", [])),
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.span is not None:
            self.span.write_into(result)
        if self.statements:
            result["statements"] = [s.to_dict() for s in self.statements]
        return result | (
            {"sentence_ends": list(self.sentence_ends)} if self.sentence_ends else {}
        )


@dataclass(frozen=True)
class UseClause:
    """A declarative's USE AFTER ERROR/EXCEPTION targeting."""

    is_global: bool
    target: str  # "FILE" | "INPUT" | "OUTPUT" | "I-O" | "EXTEND"
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class CobolSection:
    """A COBOL PROCEDURE DIVISION section containing paragraphs and bare statements."""

    name: str
    paragraphs: list[CobolParagraph] = field(default_factory=list)
    statements: list[CobolStatementType] = field(default_factory=list)
    use: UseClause | None = None
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> CobolSection:
        use_d = data.get("use")
        return cls(
            name=data["name"],
            paragraphs=[
                CobolParagraph.from_dict(p) for p in data.get("paragraphs", [])
            ],
            statements=[parse_statement(s) for s in data.get("statements", [])],
            span=SourceSpan.from_dict(data),
            use=(
                UseClause(
                    is_global=bool(use_d.get("global", False)),
                    target=use_d.get("target", "FILE"),
                    files=tuple(f.upper() for f in use_d.get("files", [])),
                )
                if use_d
                else None
            ),
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.span is not None:
            self.span.write_into(result)
        if self.paragraphs:
            result["paragraphs"] = [p.to_dict() for p in self.paragraphs]
        if self.statements:
            result["statements"] = [s.to_dict() for s in self.statements]
        if self.use:
            use_dict: dict = {
                "global": self.use.is_global,
                "target": self.use.target,
            }
            if self.use.files:
                use_dict["files"] = list(self.use.files)
            result["use"] = use_dict
        return result


@dataclass(frozen=True)
class CobolASG:
    """Complete COBOL Abstract Semantic Graph.

    Attributes:
        data_fields: Working-Storage Section fields.
        linkage_fields: Linkage Section fields (subprogram parameters).
        procedure_using: PROCEDURE DIVISION USING, in order — the parameter each
            of a caller's CALL USING arguments binds to, by position.
        local_storage_fields: Local-Storage Section fields (per-call locals).
        file_fields: File Section (FD) record fields.
        file_descriptions: Each FD's RECORDING MODE and RECORD clause.
        sections: Procedure Division sections.
        paragraphs: Standalone paragraphs (no section).
        statements: Division-level bare statements (no paragraph or section).
    """

    program_id: str = ""
    file_control: list[FileControlEntry] = field(default_factory=list)
    data_fields: list[CobolField] = field(default_factory=list)
    linkage_fields: list[CobolField] = field(default_factory=list)
    procedure_using: list[CallUsingParam] = field(default_factory=list)
    local_storage_fields: list[CobolField] = field(default_factory=list)
    file_fields: list[CobolField] = field(default_factory=list)
    file_descriptions: list[FileDescription] = field(default_factory=list)
    sections: list[CobolSection] = field(default_factory=list)
    paragraphs: list[CobolParagraph] = field(default_factory=list)
    statements: list[CobolStatementType] = field(default_factory=list)
    file_record_to_select: dict[str, str] = field(default_factory=dict)
    declaratives: list[CobolSection] = field(default_factory=list)
    # SPECIAL-NAMES CURRENCY SIGN IS, '$' when the clause is absent. Held at
    # the ASG level so to_dict can round-trip it — without that, reviving a
    # serialised ASG silently reverts every edited field to '$'.
    currency_symbol: str = DEFAULT_CURRENCY
    # SPECIAL-NAMES DECIMAL-POINT IS COMMA, held here to round-trip like the
    # currency symbol.
    decimal_point_is_comma: bool = False
    # OBJECT-COMPUTER PROGRAM COLLATING SEQUENCE: the ALPHABET clause it names,
    # the native sequence when the clause is absent.
    collating_sequence: Alphabet = NATIVE_ALPHABET
    switches: list[ImplementorSwitch] = field(default_factory=list)
    classes: list[ClassDefinition] = field(default_factory=list)
    # When the bridge compiled this program; NOT_COMPILED for an ASG built
    # without it.
    compiled_at: datetime = NOT_COMPILED

    @classmethod
    def from_dict(
        cls, data: dict, addressing_mode: AddressingMode = LP32_MODE
    ) -> CobolASG:
        # Build FD-record-name → SELECT-file-name mapping from fd_name tags
        # (populated by bridge since the fd_name fix). Level-1 fields only.
        record_to_select: dict[str, str] = {
            f["name"].upper(): f["fd_name"].upper()
            for f in data.get("file_fields", [])
            if f.get("fd_name") and f.get("level") == 1
        }
        currency = _currency_from_special_names(data)
        collating = data.get("special_names", {}).get("program_collating_sequence", {})
        pointer = addressing_mode.pointer_type
        comma = bool(data.get("special_names", {}).get("decimal_point_is_comma", False))
        return cls(
            program_id=data.get("program_id", ""),
            file_control=[
                FileControlEntry.from_dict(e) for e in data.get("file_control", [])
            ],
            data_fields=[
                CobolField.from_dict(f, currency, pointer, comma)
                for f in data.get("data_fields", [])
            ],
            linkage_fields=[
                CobolField.from_dict(f, currency, pointer, comma)
                for f in data.get("linkage_fields", [])
            ],
            procedure_using=[
                CallUsingParam.from_dict(p) for p in data.get("procedure_using", [])
            ],
            local_storage_fields=[
                CobolField.from_dict(f, currency, pointer, comma)
                for f in data.get("local_storage_fields", [])
            ],
            file_fields=[
                CobolField.from_dict(f, currency, pointer, comma)
                for f in data.get("file_fields", [])
            ],
            file_descriptions=[
                FileDescription.from_dict(d) for d in data.get("file_descriptions", [])
            ],
            sections=[CobolSection.from_dict(s) for s in data.get("sections", [])],
            paragraphs=[
                CobolParagraph.from_dict(p) for p in data.get("paragraphs", [])
            ],
            statements=[parse_statement(s) for s in data.get("statements", [])],
            file_record_to_select=record_to_select,
            declaratives=[
                CobolSection.from_dict(s) for s in data.get("declaratives", [])
            ],
            currency_symbol=currency,
            decimal_point_is_comma=comma,
            collating_sequence=Alphabet.from_parts(
                collating.get("name", NATIVE_ALPHABET.name),
                collating.get("kind", NATIVE_ALPHABET.kind),
                collating.get("items", []),
            ),
            switches=[
                ImplementorSwitch.from_dict(s)
                for s in data.get("special_names", {}).get("switches", [])
            ],
            classes=[
                ClassDefinition.from_parts(c["name"], c["items"])
                for c in data.get("special_names", {}).get("classes", [])
            ],
            compiled_at=(
                datetime.fromisoformat(data["compiled_at"])
                if "compiled_at" in data
                else NOT_COMPILED
            ),
        )

    def to_dict(self) -> dict:
        special_names = self._special_names_dict()
        listed: dict[str, list[dict]] = {
            "file_control": [e.to_dict() for e in self.file_control],
            "data_fields": [f.to_dict() for f in self.data_fields],
            "linkage_fields": [f.to_dict() for f in self.linkage_fields],
            "local_storage_fields": [f.to_dict() for f in self.local_storage_fields],
            "file_fields": [f.to_dict() for f in self.file_fields],
            "sections": [s.to_dict() for s in self.sections],
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "statements": [s.to_dict() for s in self.statements],
            "declaratives": [s.to_dict() for s in self.declaratives],
        }
        return (
            ({"program_id": self.program_id} if self.program_id else {})
            | ({"special_names": special_names} if special_names else {})
            | {section: items for section, items in listed.items() if items}
            | self._procedure_using_dict()
            | self._file_descriptions_dict()
            | self._compiled_at_dict()
        )

    def _compiled_at_dict(self) -> dict:
        if self.compiled_at == NOT_COMPILED:
            return {}
        return {"compiled_at": self.compiled_at.isoformat(timespec="milliseconds")}

    def _special_names_dict(self) -> dict:
        currency = (
            {"currency_sign": self.currency_symbol}
            if self.currency_symbol != DEFAULT_CURRENCY
            else {}
        ) | ({"decimal_point_is_comma": True} if self.decimal_point_is_comma else {})
        clauses = (
            currency
            | (
                {"switches": [s.to_dict() for s in self.switches]}
                if self.switches
                else {}
            )
            | ({"classes": [c.to_dict() for c in self.classes]} if self.classes else {})
        )
        if self.collating_sequence == NATIVE_ALPHABET:
            return clauses
        return clauses | {
            "program_collating_sequence": self.collating_sequence.to_dict()
        }

    def _file_descriptions_dict(self) -> dict:
        if not self.file_descriptions:
            return {}
        return {"file_descriptions": [d.to_dict() for d in self.file_descriptions]}

    def _procedure_using_dict(self) -> dict:
        if not self.procedure_using:
            return {}
        return {"procedure_using": [p.to_dict() for p in self.procedure_using]}
