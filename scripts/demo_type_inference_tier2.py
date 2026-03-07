#!/usr/bin/env python3
"""Demo: Tier 1 + Tier 2 type inference enhancements.

Exercises all 6 new features:
  1. Builtin return types  (len→Int, range→Array, abs→Number)
  2. RETURN backfill       (unannotated functions get return types)
  3. UNOP refinement       (not→Bool, #→Int)
  4. CALL_METHOD return types (class method dispatch)
  5. Field type table      (STORE_FIELD/LOAD_FIELD tracking)
  6. ALLOC_REGION / LOAD_REGION tagging
"""

import logging
import sys

from interpreter.api import lower_and_infer
from interpreter.constants import Language
from interpreter.default_conversion_rules import DefaultTypeConversionRules
from interpreter.ir import Opcode
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver

logging.basicConfig(level=logging.WARNING)


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


def _lower_and_infer(source: str, language: str):
    return lower_and_infer(source, language=language)


def _header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _show_ir(instructions, limit=30):
    for inst in instructions[:limit]:
        print(f"    {inst}")
    if len(instructions) > limit:
        print(f"    ... ({len(instructions) - limit} more)")


def demo_builtin_return_types():
    _header("Feature 1: Builtin return types")

    source = """\
names = ["alice", "bob", "charlie"]
n = len(names)
r = range(10)
x = abs(-42)
s = str(123)
f = float(7)
b = bool(0)
"""
    print(f"\n  Source (Python):\n")
    for line in source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(source, "python")

    print(f"\n  IR ({len(instructions)} instructions):\n")
    _show_ir(instructions)

    print(f"\n  Inferred variable types:\n")
    for var in ["n", "r", "x", "s", "f", "b"]:
        vtype = env.var_types.get(var, "<untyped>")
        print(f"    {var} : {vtype}")


def demo_return_backfill():
    _header("Feature 2: RETURN backfill (unannotated functions)")

    print("\n  --- Python (no return annotation) ---\n")
    py_source = """\
def double(x):
    return 42

def greet():
    return "hello"
"""
    for line in py_source.strip().splitlines():
        print(f"    {line}")

    _instructions, env = _lower_and_infer(py_source, "python")
    print(f"\n  Inferred function signatures:\n")
    for name, sig in sorted(env.func_signatures.items()):
        print(
            f"    {name}({', '.join(f'{p}: {t or "?"}' for p, t in sig.params)}) -> {sig.return_type or '?'}"
        )

    print("\n  --- JavaScript (never has return annotations) ---\n")
    js_source = """\
function factorial(n) {
    if (n <= 1) { return 1; }
    return n * factorial(n - 1);
}
"""
    for line in js_source.strip().splitlines():
        print(f"    {line}")

    _instructions, env = _lower_and_infer(js_source, "javascript")
    print(f"\n  Inferred function signatures:\n")
    for name, sig in sorted(env.func_signatures.items()):
        print(
            f"    {name}({', '.join(f'{p}: {t or "?"}' for p, t in sig.params)}) -> {sig.return_type or '?'}"
        )

    print("\n  --- Ruby (never has return annotations) ---\n")
    rb_source = """\
def square(x)
  return x * x
end
"""
    for line in rb_source.strip().splitlines():
        print(f"    {line}")

    _instructions, env = _lower_and_infer(rb_source, "ruby")
    print(f"\n  Inferred function signatures:\n")
    for name, sig in sorted(env.func_signatures.items()):
        print(
            f"    {name}({', '.join(f'{p}: {t or "?"}' for p, t in sig.params)}) -> {sig.return_type or '?'}"
        )


def demo_unop_refinement():
    _header("Feature 3: UNOP refinement (not/! -> Bool, # -> Int)")

    print("\n  --- Python `not` ---\n")
    py_source = """\
x = 42
y = not x
"""
    for line in py_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(py_source, "python")
    print(f"\n  Inferred variable types:")
    print(f"    x : {env.var_types.get('x', '<untyped>')}")
    print(f"    y : {env.var_types.get('y', '<untyped>')}")

    print("\n  --- JavaScript `!` ---\n")
    js_source = """\
let flag = true;
let negated = !flag;
"""
    for line in js_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(js_source, "javascript")
    print(f"\n  Inferred variable types:")
    print(f"    flag    : {env.var_types.get('flag', '<untyped>')}")
    print(f"    negated : {env.var_types.get('negated', '<untyped>')}")

    print("\n  --- Lua `#` (length operator) ---\n")
    lua_source = """\
local t = {1, 2, 3}
local n = #t
"""
    for line in lua_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(lua_source, "lua")
    unops = [i for i in instructions if i.opcode == Opcode.UNOP]
    print(f"\n  UNOP instructions and their result types:")
    for inst in unops:
        reg_type = env.register_types.get(inst.result_reg, "<untyped>")
        print(f"    {inst}  =>  {inst.result_reg} : {reg_type}")


def demo_call_method_return_types():
    _header("Feature 4: CALL_METHOD return types (class method dispatch)")

    java_source = """\
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
    print(f"\n  Source (Java):\n")
    for line in java_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(java_source, "java")

    print(f"\n  CALL_METHOD instructions and their inferred types:\n")
    call_methods = [i for i in instructions if i.opcode == Opcode.CALL_METHOD]
    for inst in call_methods:
        method_name = inst.operands[1] if len(inst.operands) >= 2 else "?"
        reg_type = env.register_types.get(inst.result_reg, "<untyped>")
        print(f"    {inst.result_reg} = call_method {method_name}  =>  {reg_type}")

    print(f"\n  Function signatures:\n")
    for name, sig in sorted(env.func_signatures.items()):
        print(f"    {name}() -> {sig.return_type or '?'}")


def demo_field_type_table():
    _header("Feature 5: Field type table (STORE_FIELD / LOAD_FIELD)")

    py_source = """\
class Dog:
    def __init__(self, name, age):
        self.name = name
        self.age = 5

    def describe(self):
        n = self.name
        a = self.age
        return a
"""
    print(f"\n  Source (Python):\n")
    for line in py_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(py_source, "python")

    print(f"\n  STORE_FIELD instructions:\n")
    store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
    for inst in store_fields:
        obj_reg = inst.operands[0] if inst.operands else "?"
        field = inst.operands[1] if len(inst.operands) >= 2 else "?"
        val_reg = inst.operands[2] if len(inst.operands) >= 3 else "?"
        obj_type = env.register_types.get(str(obj_reg), "?")
        val_type = env.register_types.get(str(val_reg), "?")
        print(f"    {obj_reg}({obj_type}).{field} = {val_reg}({val_type})")

    print(f"\n  LOAD_FIELD instructions:\n")
    load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
    for inst in load_fields:
        obj_reg = inst.operands[0] if inst.operands else "?"
        field = inst.operands[1] if len(inst.operands) >= 2 else "?"
        obj_type = env.register_types.get(str(obj_reg), "?")
        result_type = env.register_types.get(inst.result_reg, "<untyped>")
        print(
            f"    {inst.result_reg} = {obj_reg}({obj_type}).{field}  =>  {result_type}"
        )


def demo_region_tagging():
    _header("Feature 6: ALLOC_REGION / LOAD_REGION tagging")

    print("\n  (Regions are used for COBOL-style byte-addressed memory)")
    print("  Showing IR-level demo with manual instructions:\n")

    from interpreter.ir import IRInstruction

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

    for inst in instructions:
        print(f"    {inst}")

    print(f"\n  Inferred register types:\n")
    print(f"    %0 (ALLOC_REGION result) : {env.register_types.get('%0', '<untyped>')}")
    print(f"    %1 (LOAD_REGION result)  : {env.register_types.get('%1', '<untyped>')}")


def main():
    print("\n  Tier 1 + Tier 2 Type Inference Enhancements — Demo")
    print("  ===================================================\n")
    print("  This demo exercises all 6 new type inference features.")

    demo_builtin_return_types()
    demo_return_backfill()
    demo_unop_refinement()
    demo_call_method_return_types()
    demo_field_type_table()
    demo_region_tagging()

    print(f"\n{'=' * 70}")
    print("  All 6 features demonstrated successfully!")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
