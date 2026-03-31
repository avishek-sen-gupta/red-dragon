"""Tests for EntryPoint type."""

import pytest

from interpreter.func_name import FuncName
from interpreter.project.entry_point import EntryPoint
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel


def _make_func_ref(name: str) -> FuncRef:
    return FuncRef(name=FuncName(name), label=CodeLabel(f"func_{name}"))


class TestEntryPointTopLevel:
    def test_is_top_level(self):
        ep = EntryPoint.top_level()
        assert ep.is_top_level is True

    def test_is_not_function(self):
        ep = EntryPoint.top_level()
        assert ep.is_function is False

    def test_resolve_on_top_level_raises(self):
        ep = EntryPoint.top_level()
        candidates = [_make_func_ref("main")]
        with pytest.raises(ValueError, match="No function matched"):
            ep.resolve(candidates)


class TestEntryPointFunction:
    def test_is_function(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        assert ep.is_function is True

    def test_is_not_top_level(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        assert ep.is_top_level is False

    def test_resolve_single_match(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("main"), _make_func_ref("helper")]
        result = ep.resolve(candidates)
        assert result.name == FuncName("main")

    def test_resolve_no_match_raises(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("helper")]
        with pytest.raises(ValueError, match="No function matched"):
            ep.resolve(candidates)

    def test_resolve_multiple_matches_raises(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("main"), _make_func_ref("main")]
        with pytest.raises(ValueError, match="Multiple functions matched"):
            ep.resolve(candidates)

    def test_resolve_empty_candidates_raises(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        with pytest.raises(ValueError, match="No function matched"):
            ep.resolve([])
