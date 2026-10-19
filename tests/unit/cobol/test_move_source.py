"""What each MOVE receiver takes from the sender: its value, its digit image, its de-edited value, its stored bytes, or its characters as a group."""

from __future__ import annotations

from dataclasses import replace

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.ref_mod import RefModLiteral, RefModOperand
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.move_source import MoveSource, plain_move_source
from interpreter.register import Register
from tests.covers import covers

_VALUE = Register("%value")
_IMAGE = Register("%image")
_NUMBER = Register("%number")
_STORED = Register("%stored")
_WHOLE = RefModOperand(name="DEST")
_SLICED = RefModOperand(name="DEST", ref_mod_start=RefModLiteral(value="2"))


def _field(category: CobolDataCategory) -> FieldLayout:
    return FieldLayout(
        name="DEST",
        type_descriptor=CobolTypeDescriptor(category=category, total_digits=4),
        offset=0,
        byte_length=4,
    )


_CHARACTERS = _field(CobolDataCategory.ALPHANUMERIC)
_NUMERIC = _field(CobolDataCategory.ZONED_DECIMAL)
_EDITED = _field(CobolDataCategory.ALPHANUMERIC_EDITED)
_GROUP = replace(_field(CobolDataCategory.ALPHANUMERIC), is_group=True)


@covers(CobolFeature.MOVE)
def test_each_receiver_takes_the_sender_form_its_category_and_reference_need():
    numeric = MoveSource(
        value=_VALUE, characters=_IMAGE, number=_VALUE, stored=_STORED, group=False
    )
    edited = MoveSource(
        value=_VALUE, characters=_VALUE, number=_NUMBER, stored=_STORED, group=False
    )
    group = MoveSource(
        value=_VALUE, characters=_VALUE, number=_VALUE, stored=_VALUE, group=True
    )
    plain = plain_move_source(_VALUE)
    taken = [
        source.value_for(target, fl)
        for source in (numeric, edited, plain)
        for target in (_WHOLE, _SLICED)
        for fl in (_CHARACTERS, _NUMERIC, _GROUP)
    ]
    assert taken == [
        _IMAGE,
        _VALUE,
        _STORED,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _NUMBER,
        _STORED,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
        _VALUE,
    ]
    stored = [
        source.storage_for(target, fl).type_descriptor.category
        for source in (group, plain)
        for target in (_WHOLE, _SLICED)
        for fl in (_CHARACTERS, _NUMERIC, _EDITED)
    ]
    assert stored == [
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.ALPHANUMERIC_EDITED,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.ALPHANUMERIC_EDITED,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.ALPHANUMERIC_EDITED,
    ]
