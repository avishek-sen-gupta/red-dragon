"""Tests for field initializer lowering in class bodies.

Field initializers (e.g., `int count = 0` in Java) must be emitted as
STORE_FIELD instructions inside the constructor body, not as top-level
STORE_VAR instructions. This ensures that when an object is constructed,
its heap fields are properly populated.

Tests cover four languages where field initializers were previously
lowered incorrectly: Java, C#, Kotlin, Scala.
"""

from __future__ import annotations

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.frontends.java import JavaFrontend
from interpreter.frontends.csharp import CSharpFrontend
from interpreter.frontends.kotlin import KotlinFrontend
from interpreter.frontends.scala import ScalaFrontend
from interpreter.parser import TreeSitterParserFactory


def _parse(language: str, source: str) -> list[IRInstruction]:
    frontends = {
        "java": JavaFrontend,
        "csharp": CSharpFrontend,
        "kotlin": KotlinFrontend,
        "scala": ScalaFrontend,
    }
    frontend = frontends[language](TreeSitterParserFactory(), language)
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


def _instructions_between_labels(
    instructions: list[IRInstruction], start_prefix: str, end_prefix: str
) -> list[IRInstruction]:
    """Extract instructions between a label matching start_prefix and one matching end_prefix."""
    result: list[IRInstruction] = []
    capturing = False
    for inst in instructions:
        if (
            inst.opcode == Opcode.LABEL
            and inst.label.is_present()
            and inst.label.value.startswith(start_prefix)
        ):
            capturing = True
            continue
        if (
            capturing
            and inst.opcode == Opcode.LABEL
            and inst.label.is_present()
            and inst.label.value.startswith(end_prefix)
        ):
            break
        if capturing:
            result.append(inst)
    return result


def _constructor_body(instructions: list[IRInstruction]) -> list[IRInstruction]:
    """Extract instructions inside the __init__ function body."""
    return _instructions_between_labels(instructions, "func___init__", "end___init__")


def _has_store_field_in_constructor(
    instructions: list[IRInstruction], field_name: str
) -> bool:
    """Check if the constructor body contains a STORE_FIELD for the given field."""
    body = _constructor_body(instructions)
    return any(
        inst.opcode == Opcode.STORE_FIELD and field_name in inst.operands
        for inst in body
    )


def _has_store_var_at_top_level_for_field(
    instructions: list[IRInstruction], field_name: str
) -> bool:
    """Check if there's a top-level STORE_VAR for a field name (outside any function)."""
    in_func = False
    for inst in instructions:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.value.startswith("func_"):
                in_func = True
            elif inst.label.value.startswith("end_"):
                in_func = False
        if (
            not in_func
            and inst.opcode == Opcode.STORE_VAR
            and field_name in inst.operands
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


class TestJavaFieldInitializers:
    def test_field_init_emitted_as_store_field_in_constructor(self):
        """int count = 0 inside a class should produce STORE_FIELD in __init__."""
        ir = _parse(
            "java",
            """\
class Counter {
    int count = 0;
}
""",
        )
        assert _has_store_field_in_constructor(ir, "count")

    def test_field_init_not_emitted_as_top_level_store_var(self):
        """Field initializers should NOT be top-level STORE_VAR."""
        ir = _parse(
            "java",
            """\
class Counter {
    int count = 0;
}
""",
        )
        assert not _has_store_var_at_top_level_for_field(ir, "count")

    def test_multiple_field_inits_all_in_constructor(self):
        """Multiple field initializers should all appear in __init__."""
        ir = _parse(
            "java",
            """\
class Point {
    int x = 1;
    int y = 2;
}
""",
        )
        assert _has_store_field_in_constructor(ir, "x")
        assert _has_store_field_in_constructor(ir, "y")

    def test_field_inits_prepended_to_explicit_constructor(self):
        """Field initializers should appear BEFORE the explicit constructor body."""
        ir = _parse(
            "java",
            """\
class Counter {
    int count = 0;
    Counter(int start) {
        this.count = start;
    }
}
""",
        )
        body = _constructor_body(ir)
        store_fields = [
            (i, inst)
            for i, inst in enumerate(body)
            if inst.opcode == Opcode.STORE_FIELD and "count" in inst.operands
        ]
        # Should have at least two STORE_FIELDs for count:
        # one from field init (count=0), one from constructor body (count=start)
        assert len(store_fields) >= 2
        # The field init (value=0) should come before the constructor body (value=start)
        init_idx = store_fields[0][0]
        body_idx = store_fields[1][0]
        assert init_idx < body_idx

    def test_field_without_initializer_not_emitted(self):
        """Field declarations without initializers (e.g., int count;) should not produce STORE_FIELD."""
        ir = _parse(
            "java",
            """\
class Counter {
    int count;
}
""",
        )
        body = _constructor_body(ir)
        store_fields = [
            inst
            for inst in body
            if inst.opcode == Opcode.STORE_FIELD and "count" in inst.operands
        ]
        assert len(store_fields) == 0


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------


class TestCSharpFieldInitializers:
    def test_field_init_emitted_as_store_field_in_constructor(self):
        ir = _parse(
            "csharp",
            """\
class Counter {
    int count = 0;
}
""",
        )
        assert _has_store_field_in_constructor(ir, "count")

    def test_field_init_not_emitted_as_top_level_store_var(self):
        ir = _parse(
            "csharp",
            """\
class Counter {
    int count = 0;
}
""",
        )
        assert not _has_store_var_at_top_level_for_field(ir, "count")

    def test_field_inits_prepended_to_explicit_constructor(self):
        ir = _parse(
            "csharp",
            """\
class Counter {
    int count = 0;
    Counter(int start) {
        this.count = start;
    }
}
""",
        )
        body = _constructor_body(ir)
        store_fields = [
            (i, inst)
            for i, inst in enumerate(body)
            if inst.opcode == Opcode.STORE_FIELD and "count" in inst.operands
        ]
        assert len(store_fields) >= 2
        assert store_fields[0][0] < store_fields[1][0]


# ---------------------------------------------------------------------------
# Kotlin
# ---------------------------------------------------------------------------


class TestKotlinFieldInitializers:
    def test_field_init_emitted_as_store_field_in_constructor(self):
        ir = _parse(
            "kotlin",
            """\
class Counter {
    var count: Int = 0
}
""",
        )
        assert _has_store_field_in_constructor(ir, "count")

    def test_field_init_not_emitted_as_top_level_store_var(self):
        ir = _parse(
            "kotlin",
            """\
class Counter {
    var count: Int = 0
}
""",
        )
        assert not _has_store_var_at_top_level_for_field(ir, "count")


# ---------------------------------------------------------------------------
# Scala
# ---------------------------------------------------------------------------


class TestScalaFieldInitializers:
    def test_field_init_emitted_as_store_field_in_constructor(self):
        ir = _parse(
            "scala",
            """\
class Counter {
    var count: Int = 0
}
""",
        )
        assert _has_store_field_in_constructor(ir, "count")

    def test_field_init_not_emitted_as_top_level_store_var(self):
        ir = _parse(
            "scala",
            """\
class Counter {
    var count: Int = 0
}
""",
        )
        assert not _has_store_var_at_top_level_for_field(ir, "count")
