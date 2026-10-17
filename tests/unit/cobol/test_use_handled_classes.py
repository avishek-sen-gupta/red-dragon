"""An AT END phrase handles status class 1 and an INVALID KEY phrase class 2."""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_io import handled_classes
from interpreter.cobol.status_class import StatusClass
from tests.covers import covers


@covers(CobolFeature.DECLARATIVES)
def test_each_phrase_handles_only_its_own_status_class() -> None:
    assert [
        handled_classes(False, False),
        handled_classes(True, False),
        handled_classes(False, True),
        handled_classes(True, True),
    ] == [
        (),
        (StatusClass.AT_END,),
        (StatusClass.INVALID_KEY,),
        (StatusClass.AT_END, StatusClass.INVALID_KEY),
    ]
