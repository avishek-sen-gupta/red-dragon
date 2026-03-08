"""Tests for Tier 1 + Tier 2 type inference enhancements.

Converted from scripts/demo_type_inference_tier2.py.
Exercises 6 features:
  1. Builtin return types  (len→Int, range→Array, abs→Number, str→String, float→Float, bool→Bool)
  2. RETURN backfill       (unannotated functions get return types)
  3. UNOP refinement       (not→Bool, #→Int)
  4. CALL_METHOD return types (class method dispatch)
  5. Field type table      (STORE_FIELD/LOAD_FIELD tracking)
  6. ALLOC_REGION / LOAD_REGION tagging
"""

from interpreter.api import lower_and_infer
from interpreter.default_conversion_rules import DefaultTypeConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


def _lower_and_infer(source: str, language: str):
    return lower_and_infer(source, language=language)


class TestBuiltinReturnTypes:
    def test_builtin_return_types(self):
        source = """\
names = ["alice", "bob", "charlie"]
n = len(names)
r = range(10)
x = abs(-42)
s = str(123)
f = float(7)
b = bool(0)
"""
        _instructions, env = _lower_and_infer(source, "python")

        assert env.var_types["n"] == "Int"
        assert env.var_types["r"] == "Array"
        assert env.var_types["x"] == "Number"
        assert env.var_types["s"] == "String"
        assert env.var_types["f"] == "Float"
        assert env.var_types["b"] == "Bool"


class TestReturnBackfill:
    def test_return_backfill_python(self):
        source = """\
def double(x):
    return 42

def greet():
    return "hello"
"""
        _instructions, env = _lower_and_infer(source, "python")

        assert env.func_signatures["double"].return_type == "Int"
        assert env.func_signatures["greet"].return_type == "String"

    def test_return_backfill_javascript(self):
        source = """\
function double(n) {
    return n * 2;
}

function greet() {
    return "hi";
}
"""
        _instructions, env = _lower_and_infer(source, "javascript")

        assert env.func_signatures["double"].return_type == "Int"
        assert env.func_signatures["greet"].return_type == "String"

    def test_return_backfill_ruby(self):
        source = """\
def double(x)
  return 42
end

def greet()
  return "hello"
end
"""
        _instructions, env = _lower_and_infer(source, "ruby")

        assert env.func_signatures["double"].return_type == "Int"
        assert env.func_signatures["greet"].return_type == "String"


class TestUnopRefinement:
    def test_unop_python_not(self):
        source = """\
x = 42
y = not x
"""
        _instructions, env = _lower_and_infer(source, "python")

        assert env.var_types["x"] == "Int"
        assert env.var_types["y"] == "Bool"

    def test_unop_javascript_bang(self):
        source = """\
let flag = true;
let negated = !flag;
"""
        _instructions, env = _lower_and_infer(source, "javascript")

        assert env.var_types["flag"] == "Bool"
        assert env.var_types["negated"] == "Bool"

    def test_unop_lua_hash(self):
        source = """\
local t = {1, 2, 3}
local n = #t
"""
        instructions, env = _lower_and_infer(source, "lua")

        unops = [i for i in instructions if i.opcode == Opcode.UNOP]
        assert len(unops) == 1
        assert env.register_types[unops[0].result_reg] == "Int"


class TestCallMethodReturnTypes:
    def test_call_method_return_types(self):
        source = """\
class Dog {
    String name;
    int age;

    String getName() { return this.name; }
    int getAge() { return this.age; }

    static void main() {
        Dog d = new Dog();
        String n = d.getName();
        int a = d.getAge();
    }
}
"""
        instructions, env = _lower_and_infer(source, "java")

        call_methods = [i for i in instructions if i.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) >= 2
        # Verify return types were actually inferred for the method calls
        inferred_regs = [
            cm.result_reg
            for cm in call_methods
            if cm.result_reg and cm.result_reg in env.register_types
        ]
        assert (
            len(inferred_regs) >= 2
        ), "CALL_METHOD result registers should have inferred types"


class TestFieldTypeTable:
    def test_field_type_table(self):
        source = """\
class Dog:
    def __init__(self, name, age):
        self.name = name
        self.age = 5

    def describe(self):
        n = self.name
        a = self.age
        return a
"""
        instructions, env = _lower_and_infer(source, "python")

        store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
        load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]

        assert len(store_fields) >= 2
        assert len(load_fields) >= 2

        # LOAD_FIELD for self.age should resolve to Int (stored as literal 5)
        age_loads = [
            i
            for i in load_fields
            if len(i.operands) >= 2 and str(i.operands[1]) == "age"
        ]
        assert len(age_loads) >= 1
        assert env.register_types[age_loads[0].result_reg] == "Int"


class TestRegionTagging:
    def test_region_tagging(self):
        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label="entry"),
            IRInstruction(
                opcode=Opcode.ALLOC_REGION,
                result_reg="%0",
                operands=["100"],
            ),
            IRInstruction(
                opcode=Opcode.LOAD_REGION,
                result_reg="%1",
                operands=["%0", "0", "10"],
            ),
        ]

        env = infer_types(instructions, _resolver())

        assert env.register_types["%0"] == "Region"
        assert env.register_types["%1"] == "Array"
