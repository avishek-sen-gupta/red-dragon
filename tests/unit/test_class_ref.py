"""Unit tests for ClassRef dataclass and NO_CLASS_REF sentinel."""

from __future__ import annotations

import pytest

from interpreter.refs.class_ref import ClassRef, NO_CLASS_REF
from interpreter.ir import CodeLabel
from interpreter.class_name import ClassName


class TestClassRef:
    def test_construction_no_parents(self):
        ref = ClassRef(
            name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=()
        )
        assert ref.name == ClassName("Dog")
        assert ref.label == "class_Dog_0"
        assert ref.parents == ()

    def test_construction_with_parents(self):
        ref = ClassRef(
            name=ClassName("Dog"),
            label=CodeLabel("class_Dog_0"),
            parents=(ClassName("Animal"),),
        )
        assert ref.parents == (ClassName("Animal"),)

    def test_multiple_parents(self):
        ref = ClassRef(
            name=ClassName("C"),
            label=CodeLabel("class_C_0"),
            parents=(ClassName("A"), ClassName("B")),
        )
        assert ref.parents == (ClassName("A"), ClassName("B"))

    def test_frozen(self):
        ref = ClassRef(
            name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=()
        )
        with pytest.raises(AttributeError):
            ref.name = "Cat"

    def test_equality(self):
        a = ClassRef(
            name=ClassName("Dog"),
            label=CodeLabel("class_Dog_0"),
            parents=(ClassName("Animal"),),
        )
        b = ClassRef(
            name=ClassName("Dog"),
            label=CodeLabel("class_Dog_0"),
            parents=(ClassName("Animal"),),
        )
        assert a == b

    def test_different_labels_not_equal(self):
        a = ClassRef(name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=())
        b = ClassRef(name=ClassName("Dog"), label=CodeLabel("class_Dog_1"), parents=())
        assert a != b

    def test_hashable(self):
        """Frozen dataclasses should be usable as dict keys."""
        ref = ClassRef(
            name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=()
        )
        d = {ref: True}
        assert d[ref] is True

    def test_parents_is_tuple(self):
        """Parents must be a tuple, not a list, for immutability."""
        ref = ClassRef(
            name=ClassName("Dog"),
            label=CodeLabel("class_Dog_0"),
            parents=(ClassName("Animal"),),
        )
        assert isinstance(ref.parents, tuple)


class TestNoClassRef:
    def test_sentinel_fields(self):
        assert NO_CLASS_REF.name == ClassName("")
        assert NO_CLASS_REF.label == ""
        assert NO_CLASS_REF.parents == ()

    def test_name_is_falsy(self):
        """Consumer sites check ref.name truthiness for failed lookups."""
        assert not NO_CLASS_REF.name

    def test_is_class_ref_instance(self):
        assert isinstance(NO_CLASS_REF, ClassRef)

    def test_lookup_pattern(self):
        """Verify the .get(label, NO_CLASS_REF) pattern works."""
        table: dict[str, ClassRef] = {
            "class_Dog_0": ClassRef(
                name=ClassName("Dog"), label=CodeLabel("class_Dog_0"), parents=()
            )
        }
        found = table.get("class_Dog_0", NO_CLASS_REF)
        assert found.name == ClassName("Dog")

        missing = table.get("class_Cat_0", NO_CLASS_REF)
        assert not missing.name
