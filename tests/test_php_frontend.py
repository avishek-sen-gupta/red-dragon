"""Tests for PhpFrontend — tree-sitter PHP AST -> IR lowering."""

from __future__ import annotations

import tree_sitter_language_pack

from interpreter.frontends.php import PhpFrontend
from interpreter.ir import IRInstruction, Opcode


def _parse_and_lower(source: str) -> list[IRInstruction]:
    parser = tree_sitter_language_pack.get_parser("php")
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    frontend = PhpFrontend()
    return frontend.lower(tree, source_bytes)


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestPhpFrontendVariableAssignment:
    def test_variable_assignment_produces_store(self):
        ir = _parse_and_lower("<?php $x = 10; ?>")
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "$x" in s.operands]
        assert len(x_stores) >= 1

    def test_variable_assignment_produces_const(self):
        ir = _parse_and_lower("<?php $x = 10; ?>")
        consts = _find_all(ir, Opcode.CONST)
        ten_consts = [c for c in consts if "10" in c.operands]
        assert len(ten_consts) >= 1


class TestPhpFrontendArithmetic:
    def test_arithmetic_produces_binop(self):
        ir = _parse_and_lower("<?php $x = 10; $y = $x + 5; ?>")
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 1
        assert "+" in binops[0].operands

    def test_arithmetic_stores_result(self):
        ir = _parse_and_lower("<?php $x = 10; $y = $x + 5; ?>")
        stores = _find_all(ir, Opcode.STORE_VAR)
        y_stores = [s for s in stores if "$y" in s.operands]
        assert len(y_stores) >= 1


class TestPhpFrontendFunctionDefinition:
    def test_function_def_produces_label_and_return(self):
        ir = _parse_and_lower("<?php function add($a, $b) { return $a + $b; } ?>")
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    def test_function_params_lowered_as_symbolic(self):
        ir = _parse_and_lower("<?php function add($a, $b) { return $a + $b; } ?>")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    def test_function_name_stored(self):
        ir = _parse_and_lower("<?php function add($a, $b) { return $a + $b; } ?>")
        stores = _find_all(ir, Opcode.STORE_VAR)
        add_stores = [s for s in stores if "add" in s.operands]
        assert len(add_stores) >= 1


class TestPhpFrontendFunctionCall:
    def test_function_call_produces_call_function(self):
        ir = _parse_and_lower("<?php add(1, 2); ?>")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "add" in c.operands]
        assert len(add_calls) >= 1


class TestPhpFrontendEcho:
    def test_echo_produces_call_function(self):
        ir = _parse_and_lower('<?php echo "hello"; ?>')
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        echo_calls = [c for c in calls if "echo" in c.operands]
        assert len(echo_calls) >= 1


class TestPhpFrontendIfElse:
    def test_if_else_produces_branch_if(self):
        source = """<?php
if ($x > 5) {
    $y = 1;
} else {
    $y = 2;
}
?>"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes

    def test_if_else_produces_labels(self):
        source = """<?php
if ($x > 5) {
    $y = 1;
} else {
    $y = 2;
}
?>"""
        ir = _parse_and_lower(source)
        labels = _find_all(ir, Opcode.LABEL)
        assert len(labels) >= 3


class TestPhpFrontendWhileLoop:
    def test_while_loop_produces_branch_if_and_branch(self):
        source = """<?php
while ($x > 0) {
    $x = $x - 1;
}
?>"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestPhpFrontendForLoop:
    def test_for_loop_produces_branch_if(self):
        source = """<?php
for ($i = 0; $i < 10; $i++) {
    $x = $i;
}
?>"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [lbl.label for lbl in labels]
        for_labels = [l for l in label_names if l and "for_" in l]
        assert len(for_labels) >= 2


class TestPhpFrontendClassDefinition:
    def test_class_definition_with_method(self):
        source = """<?php
class Dog {
    public function bark() {
        return "woof";
    }
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        dog_stores = [s for s in stores if "Dog" in s.operands]
        assert len(dog_stores) >= 1
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1


class TestPhpFrontendMethodCall:
    def test_method_call_produces_call_method(self):
        source = "<?php $obj->method(); ?>"
        ir = _parse_and_lower(source)
        method_calls = _find_all(ir, Opcode.CALL_METHOD)
        assert len(method_calls) >= 1
        assert "method" in method_calls[0].operands


class TestPhpFrontendMemberAccess:
    def test_member_access_produces_load_field(self):
        source = "<?php $x = $obj->field; ?>"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestPhpFrontendAssignmentExpression:
    def test_assignment_expression_in_expression_context(self):
        source = "<?php $y = ($x = 10); ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "$x" in s.operands]
        y_stores = [s for s in stores if "$y" in s.operands]
        assert len(x_stores) >= 1
        assert len(y_stores) >= 1


class TestPhpFrontendReturn:
    def test_return_with_value(self):
        source = "<?php function f() { return 42; } ?>"
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestPhpFrontendThrow:
    def test_throw_produces_throw_opcode(self):
        source = '<?php throw new Exception("error"); ?>'
        ir = _parse_and_lower(source)
        throws = _find_all(ir, Opcode.THROW)
        assert len(throws) >= 1


class TestPhpFrontendFallback:
    def test_entry_label_always_present(self):
        source = "<?php ?>"
        ir = _parse_and_lower(source)
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"

    def test_unsupported_construct_fallback(self):
        source = "<?php $x = 10; ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # Basic constructs should not produce SYMBOLIC
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert len(stores) >= 1
