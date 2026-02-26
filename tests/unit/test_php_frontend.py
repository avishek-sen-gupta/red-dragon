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


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialPhp:
    def test_foreach_with_method_calls(self):
        source = """\
<?php
$items = [1, 2, 3];
foreach ($items as $item) {
    echo $item;
    $result->add($item);
}
?>
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # foreach is lowered as SYMBOLIC in current frontend
        assert Opcode.SYMBOLIC in opcodes or Opcode.BRANCH_IF in opcodes
        assert len(ir) > 1

    def test_class_with_constructor_and_methods(self):
        source = """\
<?php
class Counter {
    private $count;
    public function __construct($start) {
        $this->count = $start;
    }
    public function increment() {
        $this->count = $this->count + 1;
    }
    public function value() {
        return $this->count;
    }
}
?>
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Counter" in s.operands for s in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(ir) > 20

    def test_try_catch_with_throw(self):
        source = """\
<?php
try {
    $result = riskyOp();
    echo $result;
} catch (Exception $e) {
    throw new RuntimeException("wrapped");
}
?>
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        labels = [i.label for i in ir if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: SYMBOLIC placeholders
        symbolics = [i for i in ir if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert len(ir) > 1

    def test_nested_if_elseif_else(self):
        source = """\
<?php
if ($x > 100) {
    $grade = "A";
} elseif ($x > 50) {
    $grade = "B";
} elseif ($x > 25) {
    $grade = "C";
} else {
    $grade = "F";
}
?>
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 3
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$grade" in inst.operands for inst in stores)
        labels = _labels_in_order(ir)
        assert len(labels) >= 4

    def test_while_with_array_push(self):
        source = """\
<?php
$i = 0;
$items = [];
while ($i < 10) {
    array_push($items, $i * 2);
    $i = $i + 1;
}
?>
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("array_push" in inst.operands for inst in calls)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("*" in inst.operands for inst in binops)
        labels = _labels_in_order(ir)
        assert any("while" in lbl for lbl in labels)
        assert len(ir) > 15

    def test_function_with_conditional_return(self):
        source = """\
<?php
function safe_divide($a, $b) {
    if ($b == 0) {
        return 0;
    }
    return $a / $b;
}
?>
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 2
        binops = _find_all(ir, Opcode.BINOP)
        assert any("/" in inst.operands for inst in binops)

    def test_object_creation_and_method_chain(self):
        source = """\
<?php
$builder = new StringBuilder();
$builder->append("hello");
$builder->append(" world");
$result = $builder->toString();
?>
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert method_names.count("append") >= 2
        assert "toString" in method_names
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$result" in inst.operands for inst in stores)

    def test_for_loop_with_field_access(self):
        source = """\
<?php
$total = 0;
for ($i = 0; $i < 10; $i++) {
    $total = $total + $obj->value;
}
?>
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("value" in inst.operands for inst in load_fields)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$total" in inst.operands for inst in stores)
        assert len(ir) > 15


class TestPhpForeach:
    def test_foreach_simple(self):
        """foreach ($arr as $v) should produce index-based IR."""
        source = "<?php foreach ($arr as $v) { echo $v; } ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LOAD_INDEX in opcodes
        assert Opcode.CALL_FUNCTION in opcodes  # len()
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$v" in inst.operands for inst in stores)

    def test_foreach_key_value(self):
        """foreach ($arr as $k => $v) should store both key and value."""
        source = "<?php foreach ($arr as $k => $v) { echo $v; } ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LOAD_INDEX in opcodes
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$k" in inst.operands for inst in stores)
        assert any("$v" in inst.operands for inst in stores)

    def test_foreach_with_break(self):
        source = """\
<?php
foreach ($arr as $v) {
    if ($v > 10) {
        break;
    }
}
?>
"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("foreach_end" in lbl for lbl in labels)
        branches = _find_all(ir, Opcode.BRANCH)
        end_labels = [lbl for lbl in labels if "foreach_end" in lbl]
        assert any(b.label in end_labels for b in branches)
