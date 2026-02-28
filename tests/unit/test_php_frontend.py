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


class TestPhpArrayCreation:
    def test_array_indexed(self):
        source = "<?php $a = array(1, 2, 3); ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_array_associative(self):
        source = "<?php $m = array('a' => 1, 'b' => 2); ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 2

    def test_array_bracket_syntax(self):
        source = "<?php $a = [10, 20, 30]; ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3


class TestPhpMatchExpression:
    def test_match_produces_branch_if_per_arm(self):
        source = (
            '<?php $r = match($x) { 1 => "one", 2 => "two", default => "other" }; ?>'
        )
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_match_compares_with_strict_equality(self):
        source = '<?php $r = match($x) { 1 => "one", default => "other" }; ?>'
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("===" in inst.operands for inst in binops)

    def test_match_stores_result(self):
        source = '<?php $r = match($x) { 1 => "one", default => "other" }; ?>'
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$r" in inst.operands for inst in stores)


class TestPhpArrowFunction:
    def test_arrow_function_produces_func_ref(self):
        source = "<?php $f = fn($x) => $x * 2; ?>"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        func_refs = [
            c for c in consts if any("function:" in str(op) for op in c.operands)
        ]
        assert len(func_refs) >= 1

    def test_arrow_function_has_param_and_return(self):
        source = "<?php $f = fn($x) => $x * 2; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 1
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1

    def test_arrow_function_body_has_binop(self):
        source = "<?php $f = fn($x) => $x + 1; ?>"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestPhpScopedCallExpression:
    def test_scoped_call_produces_call_function(self):
        source = "<?php Math::sqrt(4); ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("Math::sqrt" in inst.operands for inst in calls)

    def test_scoped_call_with_multiple_args(self):
        source = "<?php MyClass::create(1, 2, 3); ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("MyClass::create" in inst.operands for inst in calls)

    def test_scoped_call_result_stored(self):
        source = "<?php $r = Config::get('key'); ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("Config::get" in inst.operands for inst in calls)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$r" in inst.operands for inst in stores)


class TestPhpSwitchStatement:
    def test_switch_produces_branch_if_per_case(self):
        source = """<?php
switch ($x) {
    case 1: echo "one"; break;
    case 2: echo "two"; break;
    default: echo "other";
}
?>"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2

    def test_switch_end_label_for_break(self):
        source = """<?php
switch ($x) {
    case 1: echo "one"; break;
    default: echo "other";
}
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("switch_end" in lbl for lbl in labels)

    def test_switch_compares_discriminant(self):
        source = """<?php
switch ($x) {
    case 1: echo "one"; break;
}
?>"""
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("==" in inst.operands for inst in binops)


class TestPhpDoWhileStatement:
    def test_do_while_body_before_condition(self):
        source = """<?php
do {
    $x++;
} while ($x < 10);
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("do_body" in lbl for lbl in labels)
        assert any("do_cond" in lbl for lbl in labels)
        body_idx = next(i for i, l in enumerate(labels) if "do_body" in l)
        cond_idx = next(i for i, l in enumerate(labels) if "do_cond" in l)
        assert body_idx < cond_idx

    def test_do_while_has_branch_if(self):
        source = """<?php
do {
    $x++;
} while ($x < 10);
?>"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 1

    def test_do_while_break_targets_end(self):
        source = """<?php
do {
    if ($x > 5) { break; }
    $x++;
} while ($x < 10);
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("do_end" in lbl for lbl in labels)
        branches = _find_all(ir, Opcode.BRANCH)
        end_labels = [l for l in labels if "do_end" in l]
        assert any(b.label in end_labels for b in branches)


class TestPhpNamespaceDefinition:
    def test_namespace_lowers_body(self):
        source = """<?php
namespace App\\Models {
    class User {}
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("User" in inst.operands for inst in stores)

    def test_namespace_with_function(self):
        source = """<?php
namespace App\\Helpers {
    function helper() { return 1; }
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("helper" in inst.operands for inst in stores)


class TestPhpInterfaceDeclaration:
    def test_interface_produces_class_ref(self):
        source = """<?php
interface Printable {
    public function print();
}
?>"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1

    def test_interface_stored_by_name(self):
        source = """<?php
interface Printable {
    public function print();
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Printable" in inst.operands for inst in stores)

    def test_interface_has_labels(self):
        source = """<?php
interface Printable {
    public function print();
}
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("class_Printable" in lbl for lbl in labels)


class TestPhpTraitDeclaration:
    def test_trait_produces_class_ref(self):
        source = """<?php
trait Loggable {
    public function log() { echo "log"; }
}
?>"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1

    def test_trait_stored_by_name(self):
        source = """<?php
trait Loggable {
    public function log() { echo "log"; }
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Loggable" in inst.operands for inst in stores)

    def test_trait_body_methods_lowered(self):
        source = """<?php
trait Loggable {
    public function log() { echo "log"; }
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("log" in inst.operands for inst in stores)


class TestPhpFunctionStaticDeclaration:
    def test_static_var_with_value(self):
        source = """<?php
function counter() {
    static $count = 0;
    $count++;
    return $count;
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$count" in inst.operands for inst in stores)

    def test_static_var_without_value(self):
        source = """<?php
function f() {
    static $x;
    return $x;
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$x" in inst.operands for inst in stores)

    def test_static_var_produces_const(self):
        source = """<?php
function f() {
    static $x = 42;
}
?>"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("42" in inst.operands for inst in consts)


class TestPhpEnumDeclaration:
    def test_enum_produces_class_ref(self):
        source = """<?php
enum Color {
    case Red;
    case Blue;
}
?>"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1

    def test_enum_stored_by_name(self):
        source = """<?php
enum Color {
    case Red;
    case Blue;
}
?>"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("Color" in inst.operands for inst in stores)

    def test_enum_has_labels(self):
        source = """<?php
enum Color {
    case Red;
    case Blue;
}
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("class_Color" in lbl for lbl in labels)


class TestPhpNamedLabelStatement:
    def test_named_label_produces_label(self):
        source = "<?php start: echo 1; ?>"
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("user_start" in lbl for lbl in labels)

    def test_named_label_body_lowered(self):
        source = "<?php myLabel: $x = 1; ?>"
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("user_myLabel" in lbl for lbl in labels)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$x" in inst.operands for inst in stores)


class TestPhpGotoStatement:
    def test_goto_produces_branch(self):
        source = "<?php goto myLabel; ?>"
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(b.label == "user_myLabel" for b in branches)

    def test_goto_and_label_connected(self):
        source = """<?php
start:
echo "loop";
goto start;
?>"""
        ir = _parse_and_lower(source)
        labels = _labels_in_order(ir)
        assert any("user_start" in lbl for lbl in labels)
        branches = _find_all(ir, Opcode.BRANCH)
        assert any(b.label == "user_start" for b in branches)


class TestPhpAnonymousFunction:
    def test_anonymous_function_basic(self):
        source = "<?php $f = function($x) { return $x + 1; }; ?>"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any("function:" in str(inst.operands) for inst in consts)

    def test_anonymous_function_params(self):
        source = "<?php $f = function($a, $b) { return $a + $b; }; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    def test_anonymous_function_has_return(self):
        source = "<?php $f = function() { return 42; }; ?>"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes


class TestPhpNullsafeMemberAccess:
    def test_nullsafe_member_access(self):
        source = "<?php $x = $obj?->field; ?>"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("field" in inst.operands for inst in load_fields)

    def test_nullsafe_member_access_stores(self):
        source = "<?php $x = $obj?->name; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$x" in inst.operands for inst in stores)

    def test_nullsafe_member_access_chain(self):
        source = "<?php $x = $obj?->inner?->value; ?>"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 2


class TestPhpClassConstantAccess:
    def test_class_constant_access(self):
        source = "<?php $x = MyClass::MY_CONST; ?>"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("MY_CONST" in inst.operands for inst in load_fields)

    def test_class_constant_access_stores(self):
        source = "<?php $val = SomeClass::VERSION; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$val" in inst.operands for inst in stores)


class TestPhpScopedPropertyAccess:
    def test_scoped_property_access(self):
        source = "<?php $x = MyClass::$instance; ?>"
        ir = _parse_and_lower(source)
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("$instance" in inst.operands for inst in load_fields)

    def test_scoped_property_access_stores(self):
        source = "<?php $v = Config::$debug; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$v" in inst.operands for inst in stores)


class TestPhpPropertyDeclaration:
    def test_property_declaration_with_value(self):
        source = """<?php
class Foo {
    public $x = 10;
}
?>"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("$x" in inst.operands for inst in store_fields)

    def test_property_declaration_without_value(self):
        source = """<?php
class Bar {
    private $name;
}
?>"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("$name" in inst.operands for inst in store_fields)


class TestPhpYieldExpression:
    def test_yield_basic(self):
        source = "<?php function gen() { yield 42; } ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("yield" in inst.operands for inst in calls)

    def test_yield_stores_in_function(self):
        source = "<?php function gen() { yield 1; yield 2; } ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        yield_calls = [c for c in calls if "yield" in c.operands]
        assert len(yield_calls) >= 2


class TestPhpReferenceAssignment:
    def test_reference_assignment_basic(self):
        source = "<?php $x = &$y; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$x" in inst.operands for inst in stores)

    def test_reference_assignment_with_expression(self):
        source = "<?php $a = &$arr[0]; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$a" in inst.operands for inst in stores)


class TestPhpUseDeclaration:
    def test_use_declaration_in_class(self):
        source = """<?php
class Foo {
    use SomeTrait;
}
?>"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert any("use_trait:" in str(inst.operands) for inst in symbolics)


class TestPhpNamespaceUseDeclaration:
    def test_namespace_use_declaration(self):
        source = r"<?php use App\Models\User; ?>"
        ir = _parse_and_lower(source)
        # Should not crash — no-op
        assert ir[0].opcode == Opcode.LABEL

    def test_namespace_use_declaration_multiple(self):
        source = r"""<?php
use App\Models\User;
use App\Models\Post;
?>"""
        ir = _parse_and_lower(source)
        assert ir[0].opcode == Opcode.LABEL


class TestPhpEnumCase:
    def test_enum_case_basic(self):
        source = """<?php
enum Color {
    case Red;
    case Green;
    case Blue;
}
?>"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "Red" in field_names
        assert "Green" in field_names
        assert "Blue" in field_names

    def test_enum_case_with_value(self):
        source = """<?php
enum Suit: string {
    case Hearts = 'H';
    case Diamonds = 'D';
}
?>"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        field_names = [
            inst.operands[1] for inst in store_fields if len(inst.operands) > 1
        ]
        assert "Hearts" in field_names
        assert "Diamonds" in field_names


class TestPhpStringInterpolation:
    def test_interpolation_basic(self):
        """'Hello $name' should decompose into CONST + LOAD_VAR + BINOP '+'."""
        ir = _parse_and_lower('<?php $x = "Hello $name"; ?>')
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("$name" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_expression(self):
        """'Hello {$arr[0]}' should produce LOAD_INDEX + BINOP '+'."""
        ir = _parse_and_lower('<?php $x = "Hello {$arr[0]}"; ?>')
        assert any(inst.opcode == Opcode.LOAD_INDEX for inst in ir)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_multiple(self):
        """'$a and $b' should produce two LOAD_VAR and multiple BINOP '+'."""
        ir = _parse_and_lower('<?php $x = "$a and $b"; ?>')
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("$a" in inst.operands for inst in load_vars)
        assert any("$b" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 2

    def test_no_interpolation_is_const(self):
        """Single-quoted 'hello' has no interpolation — remains CONST."""
        ir = _parse_and_lower("<?php $x = 'hello'; ?>")
        consts = _find_all(ir, Opcode.CONST)
        assert any("'hello'" in inst.operands for inst in consts)
        # No concatenation binops for a plain string
        binops = _find_all(ir, Opcode.BINOP)
        assert not any("+" in inst.operands for inst in binops)


class TestPhpHeredoc:
    def test_heredoc_basic(self):
        source = "<?php $s = <<<EOT\nhello world\nEOT; ?>"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("$s" in inst.operands for inst in stores)

    def test_heredoc_interpolation_basic(self):
        """Heredoc with $var should decompose like encapsed_string."""
        source = "<?php $s = <<<EOT\nHello $name\nEOT; ?>"
        ir = _parse_and_lower(source)
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("$name" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_heredoc_interpolation_expression(self):
        """Heredoc with {$arr[0]} should produce LOAD_INDEX + BINOP '+'."""
        source = "<?php $s = <<<EOT\nHello {$arr[0]} world\nEOT; ?>"
        ir = _parse_and_lower(source)
        assert any(inst.opcode == Opcode.LOAD_INDEX for inst in ir)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_heredoc_interpolation_multiple(self):
        """Heredoc with multiple vars should concatenate all parts."""
        source = "<?php $s = <<<EOT\n$a and $b\nEOT; ?>"
        ir = _parse_and_lower(source)
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("$a" in inst.operands for inst in load_vars)
        assert any("$b" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 2

    def test_heredoc_no_interpolation_is_const(self):
        """Heredoc without variables should remain a single CONST."""
        source = "<?php $s = <<<EOT\nhello world\nEOT; ?>"
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert not any("+" in inst.operands for inst in binops)


class TestPhpRelativeScope:
    def test_relative_scope_no_symbolic(self):
        source = "<?php class Foo { public function bar() { return self::VALUE; } } ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("relative_scope" in str(inst.operands) for inst in symbolics)

    def test_static_scope_no_symbolic(self):
        source = (
            "<?php class Foo { public function bar() { return static::create(); } } ?>"
        )
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("relative_scope" in str(inst.operands) for inst in symbolics)


class TestPhpDynamicVariableName:
    def test_dynamic_variable_name_no_unsupported(self):
        """$$var should not produce unsupported SYMBOLIC."""
        source = "<?php $name = 'x'; $$name = 10; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_dynamic_variable_name_read(self):
        source = "<?php $x = $$name; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestPhpGlobalDeclaration:
    def test_global_declaration_no_unsupported(self):
        """global $x, $y; should not produce unsupported SYMBOLIC."""
        source = "<?php function f() { global $x, $y; return $x + $y; } ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)


class TestPhpIncludeExpression:
    def test_include_expression_no_unsupported(self):
        """include 'file.php' should not produce unsupported SYMBOLIC."""
        source = "<?php include 'helpers.php'; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_include_produces_call(self):
        source = "<?php include 'config.php'; ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("include" in inst.operands for inst in calls)


class TestPhpNullsafeMemberCallExpression:
    def test_nullsafe_member_call_no_unsupported(self):
        """$obj?->method() should not produce unsupported SYMBOLIC."""
        source = "<?php $x = $obj?->getName(); ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_nullsafe_member_call_produces_call_method(self):
        source = "<?php $result = $user?->getProfile(); ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any("getProfile" in inst.operands for inst in calls)


class TestPhpRequireOnceExpression:
    def test_require_once_no_unsupported(self):
        """require_once 'file.php' should not produce unsupported SYMBOLIC."""
        source = "<?php require_once 'autoload.php'; ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_require_once_produces_call(self):
        source = "<?php require_once 'bootstrap.php'; ?>"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("require_once" in inst.operands for inst in calls)


class TestPhpVariadicUnpacking:
    def test_variadic_unpacking_no_unsupported(self):
        """foo(...$args) should not produce unsupported SYMBOLIC."""
        source = "<?php $result = array_merge(...$arrays); ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_variadic_unpacking_in_call(self):
        source = "<?php foo(...$args); ?>"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)
