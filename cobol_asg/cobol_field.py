# pyright: standard
"""A COBOL DATA DIVISION item as the ASG reader takes it in."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from cobol_asg.cobol_types import CobolTypeDescriptor
from cobol_asg.condition_name import ConditionName, ConditionValue
from cobol_asg.decimal_point import DecimalPoint
from cobol_asg.edit_picture import DEFAULT_CURRENCY, UnsupportedEditPictureError
from cobol_asg.pic_parser import parse_pic
from cobol_asg.pointer_types import FULLWORD_POINTER
from cobol_asg.program_conventions import DEFAULT_CONVENTIONS, ProgramConventions
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.sign_clause import NO_SIGN_CLAUSE, SignClause
from cobol_asg.source_span import SourceSpan

NOT_RENAMED = RefModOperand(name="")
NO_ODO_OBJECT = RefModOperand(name="")
_DISPLAY = "DISPLAY"


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
    sign_written: bool = field(default=False, compare=False)
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
        conventions: ProgramConventions = DEFAULT_CONVENTIONS,
        enclosing_sign: SignClause = NO_SIGN_CLAUSE,
    ) -> CobolField:
        """The entry, a signed numeric DISPLAY item taking the nearest SIGN clause.

        "The SIGN clause specified at group level applies to each signed numeric
        data description entry subordinate to that group; one specified at a
        subordinate level takes precedence" (ANSI X3.23-1985 SIGN clause).
        """
        own_sign = SignClause.from_dict(data)
        written = cls._written(data, conventions, own_sign.nearest(enclosing_sign))
        if own_sign.written or not written.is_signed_display_numeric:
            return written
        return replace(
            written,
            sign_leading=enclosing_sign.leading,
            sign_separate=enclosing_sign.separate,
        )

    @property
    def is_signed_display_numeric(self) -> bool:
        return self.usage == _DISPLAY and self.type_descriptor.signed

    @classmethod
    def _written(
        cls, data: Mapping, conventions: ProgramConventions, children_sign: SignClause
    ) -> CobolField:
        own_sign = SignClause.from_dict(data)
        decimal_point = DecimalPoint(conventions.decimal_point_is_comma)
        value = data.get("value", "")
        return cls(
            name=data["name"],
            level=data["level"],
            pic=data.get("pic", ""),
            usage=data.get("usage", "DISPLAY"),
            offset=data.get("offset", 0),
            value=(
                decimal_point.numeric_literal(value)
                if data.get("value_is_numeric", False)
                else value
            ),
            value_is_figurative=data.get("value_is_figurative", False),
            value_is_all=data.get("value_is_all", False),
            value_is_numeric=data.get("value_is_numeric", False),
            redefines=data.get("redefines", ""),
            children=[
                CobolField.from_dict(c, conventions, children_sign)
                for c in data.get("children", [])
            ],
            occurs=data.get("occurs", 0),
            element_size=data.get("element_size", 0),
            conditions=[
                ConditionName.from_dict(c, decimal_point)
                for c in data.get("conditions", [])
            ],
            values=[
                ConditionValue.from_dict(v, decimal_point)
                for v in data.get("values", [])
            ],
            sign_leading=own_sign.leading,
            sign_separate=own_sign.separate,
            sign_written=own_sign.written,
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
            currency_symbol=conventions.currency,
            pointer_type=conventions.pointer_type,
            decimal_point_is_comma=conventions.decimal_point_is_comma,
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
            **(
                {"sign": sign}
                if self.sign_leading
                or self.sign_separate
                or (self.sign_written and self.children)
                else {}
            ),
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
