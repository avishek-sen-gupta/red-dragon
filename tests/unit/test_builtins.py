"""Tests for built-in function implementations."""

import logging

from interpreter.builtins import _builtin_print
from interpreter.vm_types import VMState


class TestBuiltinPrint:
    def test_returns_none(self):
        vm = VMState()
        result = _builtin_print(["hello", 42], vm)
        assert result is None

    def test_logs_arguments(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.builtins"):
            _builtin_print(["hello", 42], vm)
        assert "[VM print] hello 42" in caplog.text

    def test_logs_empty_args(self, caplog):
        vm = VMState()
        with caplog.at_level(logging.INFO, logger="interpreter.builtins"):
            _builtin_print([], vm)
        assert "[VM print] " in caplog.text
