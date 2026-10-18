# pyright: standard
"""COBOL ASG types — frozen dataclasses defining the JSON contract.

These dataclasses represent the Abstract Semantic Graph produced by
the ProLeap bridge (Java/ANTLR4). The bridge parses COBOL source and
emits JSON to stdout; these types consume that JSON via from_dict().
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import groupby

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.alphabet import NATIVE_ALPHABET, Alphabet
from cobol_asg.class_definition import ClassDefinition
from cobol_asg.cobol_field import CobolField
from cobol_asg.cobol_statements import (
    CallUsingParam,
    CobolStatementType,
    FileControlEntry,
    FileDescription,
    parse_statement,
)
from cobol_asg.collating_sequence_phrase import CollatingSequencePhrase
from cobol_asg.decimal_point import DecimalPoint
from cobol_asg.edit_picture import (
    DEFAULT_CURRENCY,
    UnsupportedEditPictureError,
)
from cobol_asg.implementor_switch import ImplementorSwitch
from cobol_asg.lp32 import LP32_MODE
from cobol_asg.nonnumeric_literal import literal_characters, written_literal
from cobol_asg.program_conventions import ProgramConventions
from cobol_asg.source_span import SourceSpan
from cobol_asg.storage_layout import file_section_layout, section_layout


def _program_collation(special: Mapping, alphabets: Sequence[Alphabet]) -> Alphabet:
    """The alphabet PROGRAM COLLATING SEQUENCE names, the native one when absent."""
    if "program_collating_sequence" not in special:
        return NATIVE_ALPHABET
    phrase = CollatingSequencePhrase.from_dict(special["program_collating_sequence"])
    return phrase.alphanumeric_alphabet(alphabets)


def _fd_name(record: Mapping) -> str:
    return record.get("fd_name", "")


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
    sign = literal_characters(special.get("currency_sign", "")) or DEFAULT_CURRENCY
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
    # Every format-1 ALPHABET clause of SPECIAL-NAMES, which a COLLATING
    # SEQUENCE phrase names.
    alphabets: list[Alphabet] = field(default_factory=list)
    switches: list[ImplementorSwitch] = field(default_factory=list)
    classes: list[ClassDefinition] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls, written: dict, addressing_mode: AddressingMode = LP32_MODE
    ) -> CobolASG:
        comma = bool(
            written.get("special_names", {}).get("decimal_point_is_comma", False)
        )
        data = DecimalPoint(comma).program(written)
        # Build FD-record-name → SELECT-file-name mapping from fd_name tags
        # (populated by bridge since the fd_name fix). Level-1 fields only.
        record_to_select: dict[str, str] = {
            f["name"].upper(): f["fd_name"].upper()
            for f in data.get("file_fields", [])
            if f.get("fd_name") and f.get("level") == 1
        }
        currency = _currency_from_special_names(data)
        alphabets = [
            Alphabet.from_parts(a["name"], a["kind"], a.get("items", []))
            for a in data.get("special_names", {}).get("alphabets", [])
        ]
        conventions = ProgramConventions(
            currency=currency,
            pointer_type=addressing_mode.pointer_type,
            decimal_point_is_comma=comma,
        )
        return cls(
            program_id=data.get("program_id", ""),
            file_control=[
                FileControlEntry.from_dict(e) for e in data.get("file_control", [])
            ],
            data_fields=section_layout(
                [
                    CobolField.from_dict(f, conventions)
                    for f in data.get("data_fields", [])
                ]
            ),
            linkage_fields=section_layout(
                [
                    CobolField.from_dict(f, conventions)
                    for f in data.get("linkage_fields", [])
                ]
            ),
            procedure_using=[
                CallUsingParam.from_dict(p) for p in data.get("procedure_using", [])
            ],
            local_storage_fields=section_layout(
                [
                    CobolField.from_dict(f, conventions)
                    for f in data.get("local_storage_fields", [])
                ]
            ),
            file_fields=file_section_layout(
                [
                    [CobolField.from_dict(f, conventions) for f in records]
                    for _, records in groupby(data.get("file_fields", []), _fd_name)
                ]
            ),
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
            alphabets=alphabets,
            collating_sequence=_program_collation(
                data.get("special_names", {}), alphabets
            ),
            switches=[
                ImplementorSwitch.from_dict(s)
                for s in data.get("special_names", {}).get("switches", [])
            ],
            classes=[
                ClassDefinition.from_parts(c["name"], c["items"])
                for c in data.get("special_names", {}).get("classes", [])
            ],
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
        )

    def _special_names_dict(self) -> dict:
        currency = (
            {"currency_sign": written_literal(self.currency_symbol)}
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
        alphabets = (
            {"alphabets": [a.to_dict() for a in self.alphabets]}
            if self.alphabets
            else {}
        )
        if self.collating_sequence == NATIVE_ALPHABET:
            return clauses | alphabets
        return (
            clauses
            | alphabets
            | {
                "program_collating_sequence": CollatingSequencePhrase(
                    alphabet_names=(self.collating_sequence.name,)
                ).to_dict()
            }
        )

    def _file_descriptions_dict(self) -> dict:
        if not self.file_descriptions:
            return {}
        return {"file_descriptions": [d.to_dict() for d in self.file_descriptions]}

    def _procedure_using_dict(self) -> dict:
        if not self.procedure_using:
            return {}
        return {"procedure_using": [p.to_dict() for p in self.procedure_using]}
