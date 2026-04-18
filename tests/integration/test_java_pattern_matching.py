"""Integration tests: Java pattern matching through VM execution."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint
from interpreter.frontends.java.features import JavaFeature
from tests.covers import covers


def _run_java(source: str, max_steps: int = 1000) -> dict:
    vm = run(
        source,
        language=Language.JAVA,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaInstanceofTypePattern:
    @covers(JavaFeature.TYPE_PATTERN)
    def test_instanceof_binds_variable(self):
        local_vars = _run_java(
            """\
class M {
    static String result = "none";
    static void test(Object o) {
        if (o instanceof String s) {
            result = s;
        }
    }
}
M.test("hello");
""",
        )
        assert local_vars[VarName("result")] == "hello"

    @covers(JavaFeature.TYPE_PATTERN)
    def test_instanceof_no_match(self):
        local_vars = _run_java(
            """\
class M {
    static String result = "none";
    static void test(Object o) {
        if (o instanceof String s) {
            result = s;
        }
    }
}
M.test(42);
""",
        )
        assert local_vars[VarName("result")] == "none"


class TestJavaSwitchTypePattern:
    @covers(JavaFeature.TYPE_PATTERN)
    def test_switch_type_pattern_matches(self):
        local_vars = _run_java(
            """\
class M {
    static String classify(Object o) {
        return switch (o) {
            case String s -> "string:" + s;
            default -> "other";
        };
    }
    static String result = classify("hi");
}
""",
        )
        assert local_vars[VarName("result")] == "string:hi"

    @covers(JavaFeature.TYPE_PATTERN)
    def test_switch_type_pattern_default(self):
        local_vars = _run_java(
            """\
class M {
    static String classify(Object o) {
        return switch (o) {
            case String s -> "string";
            default -> "other";
        };
    }
    static String result = classify(42);
}
""",
        )
        assert local_vars[VarName("result")] == "other"


class TestJavaSwitchWildcard:
    @covers(JavaFeature.TYPE_PATTERN)
    def test_wildcard_matches_type_without_binding(self):
        local_vars = _run_java(
            """\
class M {
    static String classify(Object o) {
        return switch (o) {
            case String _ -> "string";
            default -> "other";
        };
    }
    static String result = classify("hi");
}
""",
        )
        assert local_vars[VarName("result")] == "string"


class TestJavaSwitchGuard:
    @covers(JavaFeature.TYPE_PATTERN)
    @covers(JavaFeature.PATTERN_GUARD)
    def test_guard_filters_match(self):
        local_vars = _run_java(
            """\
class M {
    static String classify(Object o) {
        return switch (o) {
            case String s when s.length() > 3 -> "long";
            case String s -> "short";
            default -> "other";
        };
    }
    static String result = classify("hi");
}
""",
        )
        assert local_vars[VarName("result")] == "short"

    @covers(JavaFeature.TYPE_PATTERN)
    @covers(JavaFeature.PATTERN_GUARD)
    def test_guard_passes(self):
        local_vars = _run_java(
            """\
class M {
    static String classify(Object o) {
        return switch (o) {
            case String s when s.length() > 3 -> "long";
            case String s -> "short";
            default -> "other";
        };
    }
    static String result = classify("hello");
}
""",
        )
        assert local_vars[VarName("result")] == "long"
