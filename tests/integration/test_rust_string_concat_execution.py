"""Integration tests for Rust string concat patterns: String::from, .to_string(), + operator."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from tests.integration.exec_helpers import run_locals


def _run_rust(source: str, max_steps: int = 300):
    return run_locals(source, Language.RUST, max_steps)


class TestRustStringFromExecution:
    def test_string_from_is_pass_through(self):
        """String::from("hello") returns "hello" directly."""
        locals_ = _run_rust('let a = String::from("hello");')
        assert locals_[VarName("a")] == "hello"

    def test_string_from_concat(self):
        """String::from("hello") + " world" produces "hello world"."""
        locals_ = _run_rust('let a = String::from("hello"); let answer = a + " world";')
        assert locals_[VarName("answer")] == "hello world"


class TestRustToStringExecution:
    def test_to_string_on_literal(self):
        """\"hello\".to_string() returns "hello"."""
        locals_ = _run_rust('let a = "hello".to_string();')
        assert locals_[VarName("a")] == "hello"

    def test_to_string_concat(self):
        """\"hello\".to_string() + \" world\" produces "hello world"."""
        locals_ = _run_rust('let a = "hello".to_string(); let answer = a + " world";')
        assert locals_[VarName("answer")] == "hello world"
