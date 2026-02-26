"""Tests for the composable API functions in interpreter.api."""

import pytest

from interpreter.api import (
    lower_source,
    dump_ir,
    build_cfg_from_source,
    dump_cfg,
    dump_mermaid,
    extract_function_source,
)
from interpreter.cfg import CFG
from interpreter.ir import IRInstruction, Opcode

SIMPLE_SOURCE = "x = 42\n"

FUNCTION_SOURCE = """\
def greet(name):
    return name

greet("world")
"""


class TestLowerSource:
    def test_returns_list_of_ir_instructions(self):
        result = lower_source(SIMPLE_SOURCE)
        assert isinstance(result, list)
        assert all(isinstance(inst, IRInstruction) for inst in result)

    def test_contains_expected_opcodes(self):
        result = lower_source(SIMPLE_SOURCE)
        opcodes = [inst.opcode for inst in result]
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_VAR in opcodes

    def test_language_parameter(self):
        js_source = "let x = 42;\n"
        result = lower_source(js_source, language="javascript")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_non_empty_result(self):
        result = lower_source(SIMPLE_SOURCE)
        assert len(result) > 0


class TestDumpIr:
    def test_returns_string(self):
        result = dump_ir(SIMPLE_SOURCE)
        assert isinstance(result, str)

    def test_contains_instruction_text(self):
        result = dump_ir(SIMPLE_SOURCE)
        assert "CONST" in result or "const" in result.lower()
        assert "42" in result

    def test_multiline_output(self):
        result = dump_ir(SIMPLE_SOURCE)
        lines = result.strip().split("\n")
        assert len(lines) >= 1


class TestBuildCfgFromSource:
    def test_returns_cfg(self):
        result = build_cfg_from_source(SIMPLE_SOURCE)
        assert isinstance(result, CFG)

    def test_cfg_has_entry_block(self):
        result = build_cfg_from_source(SIMPLE_SOURCE)
        assert "entry" in result.blocks

    def test_cfg_has_instructions(self):
        result = build_cfg_from_source(SIMPLE_SOURCE)
        total_instructions = sum(
            len(block.instructions) for block in result.blocks.values()
        )
        assert total_instructions > 0

    def test_function_name_scoping(self):
        result = build_cfg_from_source(FUNCTION_SOURCE, function_name="greet")
        assert isinstance(result, CFG)
        labels = list(result.blocks.keys())
        assert any("greet" in label for label in labels)

    def test_function_name_not_found_raises(self):
        with pytest.raises(ValueError, match="not found"):
            build_cfg_from_source(SIMPLE_SOURCE, function_name="nonexistent")


class TestDumpCfg:
    def test_returns_string(self):
        result = dump_cfg(SIMPLE_SOURCE)
        assert isinstance(result, str)

    def test_contains_block_info(self):
        result = dump_cfg(SIMPLE_SOURCE)
        assert "entry" in result

    def test_function_scoping(self):
        result = dump_cfg(FUNCTION_SOURCE, function_name="greet")
        assert isinstance(result, str)
        assert "greet" in result


class TestDumpMermaid:
    def test_returns_string(self):
        result = dump_mermaid(SIMPLE_SOURCE)
        assert isinstance(result, str)

    def test_starts_with_flowchart(self):
        result = dump_mermaid(SIMPLE_SOURCE)
        assert result.startswith("flowchart TD")

    def test_contains_entry_node(self):
        result = dump_mermaid(SIMPLE_SOURCE)
        assert "entry" in result

    def test_function_scoping(self):
        result = dump_mermaid(FUNCTION_SOURCE, function_name="greet")
        assert "flowchart TD" in result
        assert "greet" in result


CLASS_WITH_METHOD_SOURCE = """\
class Greeter:
    def hello(self, name):
        return f"Hello, {name}"
"""

NESTED_FUNCTION_SOURCE = """\
def outer():
    def inner():
        return 42
    return inner()
"""

JS_FUNCTION_SOURCE = """\
function add(a, b) {
    return a + b;
}
"""


class TestExtractFunctionSource:
    def test_top_level_function(self):
        result = extract_function_source(FUNCTION_SOURCE, "greet")
        assert "def greet(name):" in result
        assert "return name" in result

    def test_class_method(self):
        result = extract_function_source(CLASS_WITH_METHOD_SOURCE, "hello")
        assert "def hello(self, name):" in result
        assert 'return f"Hello, {name}"' in result

    def test_nested_function(self):
        result = extract_function_source(NESTED_FUNCTION_SOURCE, "inner")
        assert "def inner():" in result
        assert "return 42" in result

    def test_not_found_raises_value_error(self):
        with pytest.raises(ValueError, match="not found"):
            extract_function_source(SIMPLE_SOURCE, "nonexistent")

    def test_non_python_language(self):
        result = extract_function_source(
            JS_FUNCTION_SOURCE, "add", language="javascript"
        )
        assert "function add(a, b)" in result
        assert "return a + b" in result


class TestCompositionHierarchy:
    """Verify that functions compose correctly — dump_ir uses lower_source, etc."""

    def test_dump_ir_matches_lower_source(self):
        instructions = lower_source(SIMPLE_SOURCE)
        ir_text = dump_ir(SIMPLE_SOURCE)
        for inst in instructions:
            assert str(inst) in ir_text

    def test_dump_cfg_matches_build_cfg(self):
        cfg = build_cfg_from_source(SIMPLE_SOURCE)
        cfg_text = dump_cfg(SIMPLE_SOURCE)
        assert cfg_text == str(cfg)

    def test_dump_mermaid_matches_build_cfg(self):
        from interpreter.cfg import cfg_to_mermaid

        cfg = build_cfg_from_source(SIMPLE_SOURCE)
        mermaid_text = dump_mermaid(SIMPLE_SOURCE)
        assert mermaid_text == cfg_to_mermaid(cfg)
