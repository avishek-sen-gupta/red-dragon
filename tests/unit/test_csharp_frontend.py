"""Tests for CSharpFrontend — tree-sitter C# AST -> IR lowering."""

from __future__ import annotations

from interpreter.frontends.csharp import CSharpFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_environment_builder import TypeEnvironmentBuilder


def _parse_and_lower(source: str) -> list[IRInstruction]:
    frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
    return frontend.lower(source.encode("utf-8"))


def _parse_csharp_with_types(
    source: str,
) -> tuple[list[IRInstruction], TypeEnvironmentBuilder]:
    frontend = CSharpFrontend(TreeSitterParserFactory(), "csharp")
    instructions = frontend.lower(source.encode("utf-8"))
    return instructions, frontend.type_env_builder


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


def _find_all(instructions: list[IRInstruction], opcode: Opcode) -> list[IRInstruction]:
    return [inst for inst in instructions if inst.opcode == opcode]


class TestCSharpFrontendVariableDeclaration:
    def test_variable_decl_produces_const_and_store(self):
        ir = _parse_and_lower("int x = 10;")
        opcodes = _opcodes(ir)
        assert Opcode.CONST in opcodes
        assert Opcode.DECL_VAR in opcodes
        stores = _find_all(ir, Opcode.DECL_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1

    def test_variable_decl_without_initializer(self):
        ir = _parse_and_lower("int x;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCSharpFrontendArithmetic:
    def test_arithmetic_produces_binop(self):
        ir = _parse_and_lower("int x = 10; int y = x + 5;")
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 1
        assert "+" in binops[0].operands

    def test_arithmetic_stores_result(self):
        ir = _parse_and_lower("int x = 10; int y = x + 5;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        y_stores = [s for s in stores if "y" in s.operands]
        assert len(y_stores) >= 1


class TestCSharpFrontendMethodDeclaration:
    def test_method_decl_produces_label_and_return(self):
        source = """
class Calc {
    int Add(int a, int b) {
        return a + b;
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.LABEL in opcodes
        assert Opcode.RETURN in opcodes

    def test_method_params_lowered_as_symbolic(self):
        source = """
class Calc {
    int Add(int a, int b) {
        return a + b;
    }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2


class TestCSharpFrontendMethodCall:
    def test_simple_function_call(self):
        ir = _parse_and_lower("Add(1, 2);")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        add_calls = [c for c in calls if "Add" in c.operands]
        assert len(add_calls) >= 1


class TestCSharpFrontendIfElse:
    def test_if_else_produces_branch_if(self):
        source = """
if (x > 5) {
    y = 1;
} else {
    y = 2;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes

    def test_if_else_produces_labels(self):
        source = """
if (x > 5) {
    y = 1;
} else {
    y = 2;
}
"""
        ir = _parse_and_lower(source)
        labels = _find_all(ir, Opcode.LABEL)
        assert len(labels) >= 3

    def test_if_elseif_chain_all_branches_produce_ir(self):
        """All branches of if/else-if/else-if/else must produce IR."""
        source = """\
if (x == 1) { y = 10; }
else if (x == 2) { y = 20; }
else if (x == 3) { y = 30; }
else { y = 40; }
"""
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_values = [op for inst in consts for op in inst.operands]
        assert "10" in const_values, "if-branch value missing"
        assert "20" in const_values, "first else-if-branch value missing"
        assert "30" in const_values, "second else-if-branch value missing"
        assert "40" in const_values, "else-branch value missing"

        branch_ifs = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branch_ifs) == 3

        labels = _labels_in_order(ir)
        branch_targets = {
            target for inst in branch_ifs for target in inst.label.split(",")
        }
        label_set = set(labels)
        assert branch_targets.issubset(
            label_set
        ), f"Unreachable targets: {branch_targets - label_set}"


class TestCSharpFrontendWhileLoop:
    def test_while_loop_produces_branch_if_and_branch(self):
        source = """
while (x > 0) {
    x = x - 1;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        assert Opcode.BRANCH in opcodes


class TestCSharpFrontendForLoop:
    def test_for_loop_produces_branch_if(self):
        source = """
for (int i = 0; i < 10; i++) {
    x = i;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [lbl.label for lbl in labels]
        for_labels = [l for l in label_names if l and "for_" in l]
        assert len(for_labels) >= 2


class TestCSharpFrontendClassDeclaration:
    def test_class_declaration(self):
        source = """
class Dog {
    void Bark() {
        return;
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        dog_stores = [s for s in stores if "Dog" in s.operands]
        assert len(dog_stores) >= 1
        consts = _find_all(ir, Opcode.CONST)
        class_refs = [
            c for c in consts if any("class:" in str(op) for op in c.operands)
        ]
        assert len(class_refs) >= 1


class TestCSharpFrontendInvocationExpression:
    def test_console_writeline_produces_call_method(self):
        source = 'Console.WriteLine("hello");'
        ir = _parse_and_lower(source)
        method_calls = _find_all(ir, Opcode.CALL_METHOD)
        assert len(method_calls) >= 1
        assert "WriteLine" in method_calls[0].operands


class TestCSharpFrontendMemberAccess:
    def test_member_access_produces_load_field(self):
        ir = _parse_and_lower("var z = obj.field;")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 1
        assert "field" in load_fields[0].operands


class TestCSharpFrontendObjectCreation:
    def test_object_creation_produces_call_function(self):
        source = 'var dog = new Dog("Rex");'
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        dog_calls = [c for c in calls if "Dog" in c.operands]
        assert len(dog_calls) >= 1


class TestCSharpFrontendReturn:
    def test_return_with_value(self):
        source = """
class C {
    int F() { return 42; }
}
"""
        ir = _parse_and_lower(source)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        # The return value 42 must be present as a CONST
        consts = _find_all(ir, Opcode.CONST)
        assert any("42" in str(inst.operands) for inst in consts)


class TestCSharpFrontendAssignmentExpression:
    def test_assignment_expression(self):
        ir = _parse_and_lower("x = 10;")
        stores = _find_all(ir, Opcode.STORE_VAR)
        x_stores = [s for s in stores if "x" in s.operands]
        assert len(x_stores) >= 1


class TestCSharpFrontendFallback:
    def test_entry_label_always_present(self):
        ir = _parse_and_lower("")
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"

    def test_lambda_produces_func_ref(self):
        # A lambda expression is now lowered as an inline function
        source = "var f = (x) => x + 1;"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )


def _labels_in_order(instructions: list[IRInstruction]) -> list[str]:
    return [inst.label for inst in instructions if inst.opcode == Opcode.LABEL]


class TestNonTrivialCSharp:
    def test_foreach_with_method_calls(self):
        source = """\
foreach (var item in items) {
    Console.WriteLine(item);
    result.Add(item);
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        calls = _find_all(ir, Opcode.CALL_METHOD)
        method_names = [inst.operands[1] for inst in calls if len(inst.operands) > 1]
        assert "WriteLine" in method_names
        assert "Add" in method_names
        assert len(ir) > 10

    def test_do_while_loop(self):
        source = """\
int x = 10;
do {
    x = x - 1;
} while (x > 0);
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        labels = _labels_in_order(ir)
        assert any("do_" in lbl for lbl in labels)
        assert len(ir) > 8

    def test_class_with_constructor_and_property(self):
        source = """\
class Counter {
    int count;
    Counter(int start) {
        this.count = start;
    }
    int Value() {
        return this.count;
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Counter" in s.operands for s in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("class:" in str(inst.operands) for inst in consts)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("count" in inst.operands for inst in store_fields)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1
        assert len(ir) > 15

    def test_try_catch_with_throw(self):
        source = """\
try {
    int result = RiskyOp();
    Console.WriteLine(result);
} catch (Exception e) {
    throw new InvalidOperationException("failed");
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        labels = [i.label for i in ir if i.opcode == Opcode.LABEL]
        # try/catch body and catch block are lowered with LABEL/BRANCH
        assert any("try_body" in l for l in labels)
        assert any("catch_0" in l for l in labels)
        assert any("try_end" in l for l in labels)
        assert Opcode.THROW in opcodes
        # No catch_clause: or finally_clause: SYMBOLIC placeholders
        symbolics = [i for i in ir if i.opcode == Opcode.SYMBOLIC]
        assert not any("catch_clause:" in str(s.operands) for s in symbolics)
        assert not any("finally_clause:" in str(s.operands) for s in symbolics)
        assert len(ir) > 10

    def test_nested_if_else_chain(self):
        source = """\
if (x > 100) {
    grade = "A";
} else if (x > 50) {
    grade = "B";
} else {
    grade = "F";
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("grade" in inst.operands for inst in stores)
        binops = _find_all(ir, Opcode.BINOP)
        assert len(binops) >= 2
        labels = _labels_in_order(ir)
        assert len(labels) >= 3

    def test_lambda_in_declaration(self):
        source = "var square = (x) => x * x;"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("square" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )

    def test_for_loop_with_nested_if(self):
        source = """\
int total = 0;
for (int i = 0; i < 20; i++) {
    if (i % 2 == 0) {
        total = total + i;
    }
    Console.WriteLine(i);
}
"""
        ir = _parse_and_lower(source)
        branches = _find_all(ir, Opcode.BRANCH_IF)
        assert len(branches) >= 2
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("total" in inst.operands for inst in stores)
        calls = _find_all(ir, Opcode.CALL_METHOD)
        assert any("WriteLine" in inst.operands for inst in calls)
        assert len(ir) > 20

    def test_switch_produces_if_else_chain(self):
        source = """\
switch (x) {
    case 1: y = 10; break;
    case 2: y = 20; break;
    default: y = 0; break;
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        # Switch is now lowered as if/else chain with BINOP ==
        binops = _find_all(ir, Opcode.BINOP)
        eq_ops = [b for b in binops if "==" in b.operands]
        assert len(eq_ops) == 2
        assert Opcode.BRANCH_IF in opcodes


class TestCSharpLambda:
    def test_lambda_expr_body(self):
        source = "var f = (int x) => x + 1;"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("f" in inst.operands for inst in stores)

    def test_lambda_block_body(self):
        source = "var f = (int x) => { return x + 1; };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes
        assert Opcode.BINOP in opcodes
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            str(inst.operands[0]).startswith("func_")
            for inst in consts
            if inst.operands
        )


class TestCSharpArrayCreation:
    def test_array_creation_with_initializer(self):
        source = "int[] a = new int[] { 1, 2, 3 };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_implicit_array_creation(self):
        source = "var a = new[] { 1, 2, 3 };"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes

    def test_array_creation_sized(self):
        source = "int[] a = new int[5];"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes


class TestCSharpEnumDeclaration:
    def test_enum_declaration(self):
        source = "enum Color { Red, Green, Blue }"
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.NEW_OBJECT in opcodes
        new_objs = _find_all(ir, Opcode.NEW_OBJECT)
        assert any("enum:Color" in str(inst.operands) for inst in new_objs)
        stores = _find_all(ir, Opcode.STORE_INDEX)
        assert len(stores) >= 3

    def test_enum_with_values(self):
        source = "enum Priority { Low, Medium, High }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "Low" in const_vals
        assert "Medium" in const_vals
        assert "High" in const_vals


class TestCSharpTypeofAndIsCheck:
    def test_typeof_expression(self):
        source = "class C { void M() { var t = typeof(int); } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("typeof" in inst.operands for inst in calls)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "int" in const_vals

    def test_typeof_with_class_type(self):
        source = "class C { void M() { var t = typeof(string); } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("typeof" in inst.operands for inst in calls)

    def test_is_check_expression(self):
        source = "class C { void M(object x) { bool b = x is string; } }"
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("is_check" in inst.operands for inst in calls)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "string" in const_vals

    def test_is_check_in_condition(self):
        source = """\
class C {
    void M(object x) {
        if (x is int) {
            int y = 1;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("is_check" in inst.operands for inst in calls)
        opcodes = _opcodes(ir)
        assert Opcode.BRANCH_IF in opcodes


class TestCSharpInterfaceDeclaration:
    def test_interface_emits_class_block(self):
        """Interface lowered as CLASS block with method defs (not NEW_OBJECT)."""
        source = "interface IShape { void Draw(); }"
        ir = _parse_and_lower(source)
        consts = _find_all(ir, Opcode.CONST)
        assert any(
            "<class:" in str(c.operands) and "IShape" in str(c.operands) for c in consts
        )
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("IShape" in inst.operands for inst in stores)
        labels = [inst.label for inst in ir if inst.opcode == Opcode.LABEL]
        assert any("func_" in l and "Draw" in l for l in labels)

    def test_interface_methods_produce_func_labels(self):
        source = "interface IAnimal { void Speak(); string Name(); }"
        ir = _parse_and_lower(source)
        labels = [inst.label for inst in ir if inst.opcode == Opcode.LABEL]
        func_labels = [l for l in labels if "func_" in l]
        assert any("Speak" in l for l in func_labels)
        assert any("Name" in l for l in func_labels)

    def test_interface_methods_seed_return_types(self):
        source = "interface ICalc { int Compute(int x); string Describe(); }"
        ir, type_builder = _parse_csharp_with_types(source)
        func_return_types = type_builder.func_return_types
        compute_entries = {k: v for k, v in func_return_types.items() if "Compute" in k}
        describe_entries = {
            k: v for k, v in func_return_types.items() if "Describe" in k
        }
        assert (
            len(compute_entries) >= 1
        ), f"Expected return type for 'Compute', got: {func_return_types}"
        assert (
            len(describe_entries) >= 1
        ), f"Expected return type for 'Describe', got: {func_return_types}"


class TestCSharpPropertyDeclaration:
    def test_auto_property(self):
        source = "class C { public int X { get; set; } }"
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("X" in inst.operands for inst in store_fields)
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("this" in inst.operands for inst in load_vars)

    def test_property_with_initializer(self):
        source = "class C { public int X { get; set; } = 42; }"
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("X" in inst.operands for inst in store_fields)
        consts = _find_all(ir, Opcode.CONST)
        const_vals = [inst.operands[0] for inst in consts if inst.operands]
        assert "42" in const_vals

    def test_property_with_accessor_body(self):
        source = """\
class C {
    int count;
    public int Count {
        get { return count; }
        set { count = value; }
    }
}
"""
        ir = _parse_and_lower(source)
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("Count" in inst.operands for inst in store_fields)
        returns = _find_all(ir, Opcode.RETURN)
        assert len(returns) >= 1


class TestCSharpAwaitExpression:
    def test_await_produces_call_function(self):
        source = """\
class C {
    async void M() {
        var result = await GetDataAsync();
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)

    def test_await_in_assignment(self):
        source = """\
class C {
    async void M() {
        var x = await Task.Run(() => 42);
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("await" in inst.operands for inst in calls)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCSharpSwitchExpression:
    def test_switch_expression_basic(self):
        source = """\
class C {
    void M() {
        var x = 1;
        var result = x switch {
            1 => 10,
            2 => 20,
            _ => 0
        };
    }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert (
            Opcode.BINOP in opcodes
        ), "switch expression must produce BINOP for arm comparisons"
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("result" in inst.operands for inst in stores)

    def test_switch_expression_with_default(self):
        source = """\
class C {
    void M(int x) {
        var y = x switch {
            0 => "zero",
            _ => "other"
        };
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)


class TestCSharpYieldStatement:
    def test_yield_return(self):
        source = """\
class C {
    System.Collections.Generic.IEnumerable<int> GetNumbers() {
        yield return 1;
        yield return 2;
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        yield_calls = [c for c in calls if "yield" in c.operands]
        assert len(yield_calls) >= 2

    def test_yield_break(self):
        source = """\
class C {
    System.Collections.Generic.IEnumerable<int> GetNumbers() {
        yield break;
    }
}
"""
        ir = _parse_and_lower(source)
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        yield_break_calls = [c for c in calls if "yield_break" in c.operands]
        assert len(yield_break_calls) >= 1


class TestCSharpLockStatement:
    def test_lock_lowers_body(self):
        source = """\
class C {
    void M() {
        lock (obj) {
            x = 10;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.STORE_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_lock_with_expression(self):
        source = """\
class C {
    object syncRoot = new object();
    void M() {
        lock (syncRoot) {
            count = count + 1;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestCSharpUsingStatement:
    def test_using_with_declaration(self):
        source = """\
class C {
    void M() {
        using (var stream = new MemoryStream()) {
            stream.Write(data);
        }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("stream" in inst.operands for inst in stores)

    def test_using_lowers_body(self):
        source = """\
class C {
    void M() {
        using (var r = new Resource()) {
            r.DoWork();
        }
    }
}
"""
        ir = _parse_and_lower(source)
        calls = (
            _find_all(ir, Opcode.CALL_METHOD)
            + _find_all(ir, Opcode.CALL_FUNCTION)
            + _find_all(ir, Opcode.CALL_UNKNOWN)
        )
        assert len(calls) >= 1


class TestCSharpCheckedStatement:
    def test_checked_lowers_body(self):
        source = """\
class C {
    void M() {
        checked {
            int x = 10;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_checked_with_arithmetic(self):
        source = """\
class C {
    void M() {
        checked {
            int y = int.MaxValue + 1;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("y" in inst.operands for inst in stores)
        # The arithmetic (+) must be lowered as a BINOP
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestCSharpFixedStatement:
    def test_fixed_lowers_body(self):
        source = """\
class C {
    unsafe void M() {
        fixed (int* p = arr) {
            int v = 42;
        }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("v" in inst.operands for inst in stores)


class TestCSharpEventFieldDeclaration:
    def test_event_field_declaration(self):
        source = """\
class C {
    event EventHandler OnClick;
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("OnClick" in inst.operands for inst in stores)

    def test_event_field_with_initializer(self):
        source = """\
class C {
    event EventHandler OnChange = null;
    event EventHandler OnReset = null;
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("OnChange" in inst.operands for inst in stores)
        assert any("OnReset" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("None" in str(inst.operands) for inst in consts)


class TestCSharpEventDeclaration:
    def test_event_declaration_with_accessors(self):
        source = """\
class C {
    event EventHandler OnClick {
        add { }
        remove { }
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("OnClick" in inst.operands for inst in stores)
        consts = _find_all(ir, Opcode.CONST)
        assert any("event:" in str(inst.operands) for inst in consts)


class TestCSharpConditionalAccess:
    def test_conditional_access_basic(self):
        ir = _parse_and_lower("var x = obj?.Field;")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("Field" in inst.operands for inst in load_fields)

    def test_conditional_access_stores(self):
        ir = _parse_and_lower("var x = obj?.Name;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)

    def test_conditional_access_nested(self):
        ir = _parse_and_lower("var x = a?.b?.c;")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert len(load_fields) >= 2


class TestCSharpLocalFunction:
    def test_local_function_basic(self):
        source = """\
void Main() {
    int Add(int a, int b) { return a + b; }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Add" in inst.operands for inst in stores)

    def test_local_function_params(self):
        source = """\
void Main() {
    int Multiply(int x, int y) { return x * y; }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        param_symbolics = [
            s for s in symbolics if any("param:" in str(op) for op in s.operands)
        ]
        assert len(param_symbolics) >= 2

    def test_local_function_has_return(self):
        source = """\
void Main() {
    int Square(int n) { return n * n; }
}
"""
        ir = _parse_and_lower(source)
        opcodes = _opcodes(ir)
        assert Opcode.RETURN in opcodes


class TestCSharpTupleExpression:
    def test_tuple_basic(self):
        ir = _parse_and_lower("var t = (1, 2, 3);")
        opcodes = _opcodes(ir)
        assert Opcode.NEW_ARRAY in opcodes
        assert Opcode.STORE_INDEX in opcodes

    def test_tuple_stores_result(self):
        ir = _parse_and_lower("var t = (1, 2);")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("t" in inst.operands for inst in stores)

    def test_tuple_element_count(self):
        ir = _parse_and_lower("var t = (10, 20, 30);")
        store_indices = _find_all(ir, Opcode.STORE_INDEX)
        assert len(store_indices) >= 3


class TestCSharpStringInterpolation:
    def test_interpolation_basic(self):
        """$"Hello {name}" should decompose into CONST + LOAD_VAR + BINOP '+'."""
        ir = _parse_and_lower('var x = $"Hello {name}";')
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("name" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)

    def test_interpolation_expression(self):
        """$"Hello {x + 1}" should produce BINOP for the expression and BINOP '+' for concatenation."""
        ir = _parse_and_lower('var y = $"Hello {x + 1}";')
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 2  # one for x+1, one for string concat

    def test_interpolation_multiple(self):
        """$"{a} and {b}" should produce two LOAD_VAR and multiple BINOP '+'."""
        ir = _parse_and_lower('var x = $"{a} and {b}";')
        load_vars = _find_all(ir, Opcode.LOAD_VAR)
        assert any("a" in inst.operands for inst in load_vars)
        assert any("b" in inst.operands for inst in load_vars)
        binops = _find_all(ir, Opcode.BINOP)
        plus_ops = [b for b in binops if "+" in b.operands]
        assert len(plus_ops) >= 2

    def test_no_interpolation_is_const(self):
        """Plain "hello" remains CONST — no interpolation."""
        ir = _parse_and_lower('var x = "hello";')
        consts = _find_all(ir, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)


class TestCSharpIsPatternExpression:
    def test_is_pattern_basic(self):
        ir = _parse_and_lower("var r = x is int y;")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("is_check" in inst.operands for inst in calls)

    def test_is_pattern_stores(self):
        ir = _parse_and_lower("var r = obj is string s;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("r" in inst.operands for inst in stores)

    def test_is_pattern_has_type_const(self):
        ir = _parse_and_lower("var r = x is int y;")
        consts = _find_all(ir, Opcode.CONST)
        # Should have a CONST with the pattern type text
        assert any("int" in str(inst.operands) for inst in consts)


class TestCSharpRecordDeclaration:
    def test_record_no_symbolic(self):
        source = "record Person { public string Name { get; set; } }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("record_declaration" in str(inst.operands) for inst in symbolics)

    def test_record_stores_class_name(self):
        source = "record Point(int X, int Y);"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Point" in inst.operands for inst in stores)


class TestCSharpVariableDeclaration:
    def test_variable_declaration_no_symbolic(self):
        ir = _parse_and_lower("for (int i = 0; i < 10; i++) { }")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "variable_declaration" in str(inst.operands) for inst in symbolics
        )


class TestCSharpDeclarationPattern:
    def test_declaration_pattern_no_symbolic(self):
        ir = _parse_and_lower("var r = x switch { int i => i, _ => 0 };")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "declaration_pattern" in str(inst.operands) for inst in symbolics
        )

    def test_declaration_pattern_stores_var(self):
        ir = _parse_and_lower("var r = x switch { int n => n, _ => 0 };")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("n" in inst.operands for inst in stores)


class TestCSharpVerbatimStringLiteral:
    def test_verbatim_string_no_symbolic(self):
        ir = _parse_and_lower('var p = @"C:\\Users\\test";')
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "verbatim_string_literal" in str(inst.operands) for inst in symbolics
        )

    def test_verbatim_string_as_const(self):
        ir = _parse_and_lower('var p = @"hello";')
        consts = _find_all(ir, Opcode.CONST)
        assert any("hello" in str(inst.operands) for inst in consts)


class TestCSharpConstantPattern:
    def test_constant_pattern_no_symbolic(self):
        ir = _parse_and_lower("var r = x switch { null => 0, _ => 1 };")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("constant_pattern" in str(inst.operands) for inst in symbolics)


class TestCSharpDelegateDeclaration:
    def test_delegate_declaration_no_unsupported(self):
        """delegate int Transform(int x); should not produce unsupported SYMBOLIC."""
        source = "delegate int Transform(int x);"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_delegate_declaration_stores(self):
        source = "delegate void Action();"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Action" in inst.operands for inst in stores)


class TestCSharpImplicitObjectCreationExpression:
    def test_implicit_object_creation_no_unsupported(self):
        """Point p = new(1, 2); should not produce unsupported SYMBOLIC."""
        source = "class C { void M() { Point p = new(1, 2); } }"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_implicit_object_creation_stores(self):
        source = "class C { void M() { List<int> items = new(); } }"
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("items" in inst.operands for inst in stores)


class TestCSharpQueryExpression:
    def test_query_expression_no_unsupported(self):
        """LINQ query expression should not produce unsupported SYMBOLIC."""
        source = """\
class C {
    void M() {
        var result = from x in items
                     where x > 0
                     select x;
    }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("unsupported:" in str(inst.operands) for inst in symbolics)

    def test_query_expression_stores_result(self):
        source = """\
class C {
    void M() {
        var result = from n in numbers
                     select n * 2;
    }
}
"""
        ir = _parse_and_lower(source)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("result" in inst.operands for inst in stores)


class TestCSharpGenericTypeSeeding:
    """Verify that C# generic types (List<string>, Dictionary<K,V>) are extracted
    as parameterised bracket-notation strings in the TypeEnvironmentBuilder."""

    def test_local_var_list_of_string(self):
        """List<string> items = ... should seed var_types['items'] = 'List[String]'."""
        source = "class M { void m() { List<string> items = new List<string>(); } }"
        _, builder = _parse_csharp_with_types(source)
        assert builder.var_types["items"] == "List[String]"

    def test_local_var_dictionary(self):
        """Dictionary<string, int> d = ... should seed 'Dictionary[String, Int]'."""
        source = "class M { void m() { Dictionary<string, int> d = new Dictionary<string, int>(); } }"
        _, builder = _parse_csharp_with_types(source)
        assert builder.var_types["d"] == "Dictionary[String, Int]"

    def test_nested_generic_type(self):
        """List<Dictionary<string, int>> should produce 'List[Dictionary[String, Int]]'."""
        source = "class M { void m() { List<Dictionary<string, int>> x = null; } }"
        _, builder = _parse_csharp_with_types(source)
        assert builder.var_types["x"] == "List[Dictionary[String, Int]]"

    def test_method_return_generic_type(self):
        """Method returning List<string> should seed func_return_types with 'List[String]'."""
        source = "class M { List<string> GetNames() { return null; } }"
        _, builder = _parse_csharp_with_types(source)
        return_types = builder.func_return_types
        assert any(v == "List[String]" for v in return_types.values())

    def test_param_generic_type(self):
        """Parameter List<string> items should seed param type 'List[String]'."""
        source = "class M { void Process(List<string> items) { } }"
        _, builder = _parse_csharp_with_types(source)
        param_types = builder.func_param_types
        assert any(
            any(ptype == "List[String]" for _, ptype in params)
            for params in param_types.values()
        )

    def test_non_generic_type_unchanged(self):
        """Plain int x = 42; should still seed 'Int' (regression check)."""
        source = "class M { void m() { int x = 42; } }"
        _, builder = _parse_csharp_with_types(source)
        assert builder.var_types["x"] == "Int"


class TestCSharpEmptyStatement:
    """Bare `;` (empty_statement) must be a no-op — no SYMBOLIC fallthrough."""

    def test_empty_statement_produces_no_symbolic(self):
        """A bare `;` should not produce any SYMBOLIC instructions."""
        ir = _parse_and_lower(";")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("empty_statement" in str(inst.operands) for inst in symbolics)

    def test_multiple_empty_statements_no_symbolic(self):
        """Multiple bare `;` should not produce any SYMBOLIC instructions."""
        ir = _parse_and_lower(";;;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("empty_statement" in str(inst.operands) for inst in symbolics)

    def test_empty_statement_among_real_statements(self):
        """Empty statements mixed with real code should not affect IR output."""
        source = "int x = 10; ; int y = 20; ;"
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("empty_statement" in str(inst.operands) for inst in symbolics)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)

    def test_empty_statement_in_method_body(self):
        """Empty statement inside a method body should be silently skipped."""
        source = """\
class C {
    void M() {
        int x = 1;
        ;
        int y = 2;
    }
}
"""
        ir = _parse_and_lower(source)
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("empty_statement" in str(inst.operands) for inst in symbolics)
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)
        assert any("y" in inst.operands for inst in stores)


class TestCSharpDefaultExpression:
    def test_default_no_symbolic(self):
        """default should not produce SYMBOLIC fallthrough."""
        ir = _parse_and_lower("int x = default;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("default_expression" in str(inst.operands) for inst in symbolics)

    def test_default_emits_const(self):
        """default expression should emit a CONST."""
        ir = _parse_and_lower("int x = default;")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1

    def test_default_stored(self):
        """default expression should be stored to a variable."""
        ir = _parse_and_lower("int x = default;")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("x" in inst.operands for inst in stores)


class TestCSharpSizeofExpression:
    def test_sizeof_no_symbolic(self):
        """sizeof(int) should not produce SYMBOLIC fallthrough."""
        ir = _parse_and_lower("int x = sizeof(int);")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("sizeof_expression" in str(inst.operands) for inst in symbolics)

    def test_sizeof_emits_const(self):
        """sizeof(int) should emit a CONST."""
        ir = _parse_and_lower("int x = sizeof(int);")
        consts = _find_all(ir, Opcode.CONST)
        assert len(consts) >= 1


class TestCSharpCheckedExpression:
    def test_checked_no_symbolic(self):
        """checked(1 + 2) should not produce SYMBOLIC fallthrough."""
        ir = _parse_and_lower("int x = checked(1 + 2);")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("checked_expression" in str(inst.operands) for inst in symbolics)

    def test_checked_lowers_inner_expr(self):
        """checked(1 + 2) should lower the inner expression (1 + 2)."""
        ir = _parse_and_lower("int x = checked(1 + 2);")
        binops = _find_all(ir, Opcode.BINOP)
        assert any("+" in inst.operands for inst in binops)


class TestCSharpFileScopedNamespace:
    def test_file_scoped_ns_no_symbolic(self):
        """namespace Foo; should not produce SYMBOLIC."""
        ir = _parse_and_lower("""\
namespace Foo;
class Bar {
  int x = 42;
}""")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any(
            "file_scoped_namespace_declaration" in str(inst.operands)
            for inst in symbolics
        )

    def test_file_scoped_ns_body_lowered(self):
        """Declarations inside file-scoped namespace should be lowered."""
        ir = _parse_and_lower("""\
namespace Foo;
class Bar {
  int x = 42;
}""")
        stores = _find_all(ir, Opcode.DECL_VAR)
        assert any("Bar" in inst.operands for inst in stores)


class TestCSharpRangeExpression:
    def test_range_no_symbolic(self):
        """0..5 should not produce SYMBOLIC."""
        ir = _parse_and_lower("var r = 0..5;")
        symbolics = _find_all(ir, Opcode.SYMBOLIC)
        assert not any("range_expression" in str(inst.operands) for inst in symbolics)

    def test_range_produces_call(self):
        """0..5 should produce a CALL_FUNCTION for range."""
        ir = _parse_and_lower("var r = 0..5;")
        calls = _find_all(ir, Opcode.CALL_FUNCTION)
        assert any("range" in inst.operands for inst in calls)
