"""Tests for MCP tool handler functions."""

from __future__ import annotations

import json

from mcp_server.tools import (
    handle_analyze_program,
    handle_get_function_summary,
    handle_get_call_chain,
    handle_list_opcodes,
    handle_load_program,
    handle_step,
    handle_run_to_end,
    handle_get_state,
    handle_get_ir,
)
from mcp_server.session import clear_session


class TestAnalyzeProgram:
    SOURCE = "def f(x):\n    return x + 1\ndef g(y):\n    return f(y)\nresult = g(5)\n"

    def test_returns_functions(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert len(result["functions"]) >= 2
        labels = [f["label"] for f in result["functions"]]
        assert any("f" in l for l in labels)
        assert any("g" in l for l in labels)

    def test_returns_call_graph(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert len(result["call_graph"]) >= 1

    def test_returns_counts(self):
        result = handle_analyze_program(self.SOURCE, "python")
        assert result["ir_instruction_count"] > 0
        assert result["cfg_block_count"] > 0
        assert result["whole_program_edge_count"] >= 0

    def test_invalid_language_returns_error(self):
        result = handle_analyze_program("x = 1", "klingon")
        assert "error" in result


class TestGetFunctionSummary:
    SOURCE = "def add(a, b):\n    return a + b\nadd(1, 2)\n"

    def test_returns_flows(self):
        result = handle_get_function_summary(self.SOURCE, "python", "add")
        assert len(result["flows"]) == 2
        sources = {f["source"] for f in result["flows"]}
        assert sources == {"a", "b"}

    def test_unknown_function_returns_error(self):
        result = handle_get_function_summary(self.SOURCE, "python", "nonexistent")
        assert "error" in result


class TestGetCallChain:
    SOURCE = (
        "def add(a, b):\n    return a + b\n"
        "def double(x):\n    return add(x, x)\n"
        "result = double(5)\n"
    )

    def test_returns_tree(self):
        result = handle_get_call_chain(self.SOURCE, "python")
        assert "root" in result or "chains" in result


class TestLoadProgram:
    def setup_method(self):
        clear_session()

    def test_loads_and_returns_overview(self):
        result = handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        assert result["total_steps"] > 0
        assert result["ir_instruction_count"] > 0

    def test_invalid_language(self):
        result = handle_load_program("x = 1", "klingon")
        assert "error" in result


class TestStep:
    def setup_method(self):
        clear_session()

    def test_step_without_session_returns_error(self):
        result = handle_step(1)
        assert "error" in result

    def test_step_after_load(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(1)
        assert result["steps_executed"] == 1
        assert len(result["steps"]) == 1

    def test_step_multiple(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_step(3)
        assert result["steps_executed"] <= 3

    def test_step_after_exhausted(self):
        handle_load_program("x = 1\n", "python")
        handle_run_to_end()
        result = handle_step(1)
        assert result["steps_executed"] == 0
        assert result["done"] is True


class TestRunToEnd:
    def setup_method(self):
        clear_session()

    def test_run_to_end(self):
        handle_load_program("x = 1\ny = x + 1\n", "python")
        result = handle_run_to_end()
        assert result["done"] is True
        assert "variables" in result


class TestGetState:
    def setup_method(self):
        clear_session()

    def test_get_state_after_load(self):
        handle_load_program("x = 1\n", "python")
        result = handle_get_state()
        assert "step_index" in result
        assert "call_stack" in result


class TestGetIr:
    def setup_method(self):
        clear_session()

    def test_get_all_ir(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir()
        assert len(result["blocks"]) > 0

    def test_get_ir_for_function(self):
        handle_load_program("def f(x):\n    return x\nf(5)\n", "python")
        result = handle_get_ir("f")
        blocks = result["blocks"]
        assert len(blocks) >= 1
        assert any("f" in b["label"] for b in blocks)


class TestListOpcodes:
    def setup_method(self):
        self.result = handle_list_opcodes()
        self.opcodes = self.result["opcodes"]
        self.by_name = {o["name"]: o for o in self.opcodes}

    def test_returns_all_33_opcodes(self):
        assert len(self.opcodes) == 33

    def test_sorted_alphabetically(self):
        names = [o["name"] for o in self.opcodes]
        assert names == sorted(names)

    def test_every_entry_has_required_keys(self):
        for entry in self.opcodes:
            assert set(entry.keys()) == {
                "name",
                "category",
                "description",
                "fields",
                "notes",
            }

    def test_source_location_excluded_from_fields(self):
        for entry in self.opcodes:
            field_names = [f["name"] for f in entry["fields"]]
            assert "source_location" not in field_names

    def test_every_field_has_name_and_type(self):
        for entry in self.opcodes:
            for f in entry["fields"]:
                assert "name" in f
                assert "type" in f
                assert isinstance(f["name"], str)
                assert isinstance(f["type"], str)

    def test_binop_fields(self):
        binop = self.by_name["BINOP"]
        field_names = [f["name"] for f in binop["fields"]]
        assert "operator" in field_names
        assert "left" in field_names
        assert "right" in field_names
        assert "result_reg" in field_names

    def test_binop_category(self):
        assert self.by_name["BINOP"]["category"] == "arithmetic"

    def test_call_function_category(self):
        assert self.by_name["CALL_FUNCTION"]["category"] == "calls"

    def test_label_category(self):
        assert self.by_name["LABEL"]["category"] == "control_flow"

    def test_new_object_category(self):
        assert self.by_name["NEW_OBJECT"]["category"] == "heap"

    def test_alloc_region_category(self):
        assert self.by_name["ALLOC_REGION"]["category"] == "memory"

    def test_set_continuation_category(self):
        assert self.by_name["SET_CONTINUATION"]["category"] == "continuations"

    def test_const_category(self):
        assert self.by_name["CONST"]["category"] == "variables"

    def test_descriptions_are_non_empty_strings(self):
        for entry in self.opcodes:
            assert isinstance(entry["description"], str)
            assert len(entry["description"]) > 10

    def test_notes_are_non_empty_strings(self):
        for entry in self.opcodes:
            assert isinstance(entry["notes"], str)
            assert len(entry["notes"]) > 20

    def test_label_has_no_opcode_specific_fields(self):
        # LABEL only has base fields: result_reg, label, branch_targets
        label = self.by_name["LABEL"]
        field_names = [f["name"] for f in label["fields"]]
        assert set(field_names) == {"result_reg", "label", "branch_targets"}

    def test_try_push_has_exception_fields(self):
        tp = self.by_name["TRY_PUSH"]
        field_names = [f["name"] for f in tp["fields"]]
        assert "catch_labels" in field_names
        assert "finally_label" in field_names
        assert "end_label" in field_names

    def test_fields_and_indices_category(self):
        assert self.by_name["LOAD_FIELD"]["category"] == "fields_and_indices"

    def test_binop_operator_type_string(self):
        binop = self.by_name["BINOP"]
        op_field = next(f for f in binop["fields"] if f["name"] == "operator")
        assert "BinopKind" in op_field["type"]
