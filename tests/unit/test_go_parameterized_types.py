"""Tests for Go frontend emitting parameterized types for slices and maps."""

from interpreter.frontends.go.frontend import GoFrontend
from interpreter.instructions import NewArray, NewObject
from interpreter.types.type_expr import ParameterizedType, ScalarType, scalar


def _parse_go(code: str):
    """Parse Go code and return the instruction list."""
    from interpreter.parser import TreeSitterParserFactory

    frontend = GoFrontend(TreeSitterParserFactory(), "go")
    return frontend.lower(code.encode() if isinstance(code, str) else code)


class TestGoSliceParameterizedType:
    def test_make_slice_int(self):
        instructions = _parse_go("package main\nfunc main() { x := make([]int, 5) }")
        new_arrays = [i for i in instructions if isinstance(i, NewArray)]
        assert len(new_arrays) >= 1
        arr = new_arrays[0]
        assert isinstance(arr.type_hint, ParameterizedType)
        assert arr.type_hint.constructor == "Array"
        assert arr.type_hint.arguments == (scalar("int"),)

    def test_make_slice_string(self):
        instructions = _parse_go("package main\nfunc main() { x := make([]string, 3) }")
        new_arrays = [i for i in instructions if isinstance(i, NewArray)]
        assert len(new_arrays) >= 1
        assert new_arrays[0].type_hint == ParameterizedType(
            "Array", (scalar("string"),)
        )


class TestGoMapParameterizedType:
    def test_make_map(self):
        instructions = _parse_go(
            "package main\nfunc main() { x := make(map[string]bool) }"
        )
        new_objs = [i for i in instructions if isinstance(i, NewObject)]
        assert len(new_objs) >= 1
        obj = new_objs[0]
        assert isinstance(obj.type_hint, ParameterizedType)
        assert obj.type_hint.constructor == "Map"
        assert obj.type_hint.arguments == (scalar("string"), scalar("bool"))
