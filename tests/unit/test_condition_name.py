"""Tests for ConditionValue and ConditionName dataclasses."""

from interpreter.cobol.condition_name import ConditionName, ConditionValue


class TestConditionValue:
    def test_discrete_value(self):
        cv = ConditionValue(from_val="A")
        assert cv.from_val == "A"
        assert cv.to_val == ""
        assert not cv.is_range

    def test_range_value(self):
        cv = ConditionValue(from_val="A", to_val="Z")
        assert cv.from_val == "A"
        assert cv.to_val == "Z"
        assert cv.is_range

    def test_from_dict_discrete(self):
        cv = ConditionValue.from_dict({"from": "42", "to": ""})
        assert cv.from_val == "42"
        assert cv.to_val == ""

    def test_from_dict_range(self):
        cv = ConditionValue.from_dict({"from": "1", "to": "99"})
        assert cv.from_val == "1"
        assert cv.to_val == "99"

    def test_round_trip(self):
        cv = ConditionValue(from_val="X", to_val="Z")
        assert ConditionValue.from_dict(cv.to_dict()) == cv

    def test_equality(self):
        cv1 = ConditionValue(from_val="A", to_val="Z")
        cv2 = ConditionValue(from_val="A", to_val="Z")
        cv3 = ConditionValue(from_val="A")
        assert cv1 == cv2
        assert cv1 != cv3


class TestConditionName:
    def test_single_value_condition(self):
        cn = ConditionName(
            name="STATUS-ACTIVE",
            values=[ConditionValue(from_val="A")],
        )
        assert cn.name == "STATUS-ACTIVE"
        assert len(cn.values) == 1
        assert cn.values[0].from_val == "A"

    def test_multi_value_condition(self):
        cn = ConditionName(
            name="STATUS-VALID",
            values=[
                ConditionValue(from_val="A"),
                ConditionValue(from_val="B"),
                ConditionValue(from_val="C"),
            ],
        )
        assert len(cn.values) == 3

    def test_range_condition(self):
        cn = ConditionName(
            name="STATUS-ALPHA",
            values=[ConditionValue(from_val="A", to_val="Z")],
        )
        assert cn.values[0].is_range

    def test_from_dict(self):
        data = {
            "name": "MY-COND",
            "values": [
                {"from": "1", "to": ""},
                {"from": "5", "to": "10"},
            ],
        }
        cn = ConditionName.from_dict(data)
        assert cn.name == "MY-COND"
        assert len(cn.values) == 2
        assert not cn.values[0].is_range
        assert cn.values[1].is_range

    def test_round_trip(self):
        cn = ConditionName(
            name="TEST-COND",
            values=[
                ConditionValue(from_val="A"),
                ConditionValue(from_val="X", to_val="Z"),
            ],
        )
        assert ConditionName.from_dict(cn.to_dict()) == cn

    def test_empty_values(self):
        cn = ConditionName(name="EMPTY-COND")
        assert cn.values == []
        assert cn.to_dict() == {"name": "EMPTY-COND"}
