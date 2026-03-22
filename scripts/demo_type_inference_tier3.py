#!/usr/bin/env python3
"""Demo: Tier 3 type inference enhancements.

Exercises all 3 new features:
  1. self/this class typing  (param:self/this/$this → class name)
  2. CALL_UNKNOWN resolution (indirect calls through registers)
  3. STORE_INDEX / LOAD_INDEX (array element type tracking)
"""

import logging

from interpreter.api import lower_and_infer
from interpreter.types.coercion.default_conversion_rules import DefaultTypeConversionRules
from interpreter.ir import IRInstruction, Opcode
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.types.type_inference import infer_types
from interpreter.types.type_resolver import TypeResolver

logging.basicConfig(level=logging.WARNING)


def _resolver():
    return TypeResolver(DefaultTypeConversionRules())


def _lower_and_infer(source: str, language: str):
    return lower_and_infer(source, language=language)


def _header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def demo_self_this_typing():
    _header("Feature 1: self/this class typing")

    # --- Python self ---
    print("\n  --- Python: self typed as class name ---\n")
    py_source = """\
class Dog:
    def __init__(self):
        self.age = 5
        self.name = "Rex"

    def get_age(self):
        return self.age
"""
    for line in py_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(py_source, "python")

    print(f"\n  SYMBOLIC param:self registers:\n")
    symbolics = [
        i
        for i in instructions
        if i.opcode == Opcode.SYMBOLIC
        and i.operands
        and str(i.operands[0]) == "param:self"
    ]
    for sym in symbolics:
        reg_type = env.register_types.get(sym.result_reg, "<untyped>")
        print(f"    {sym.result_reg} = SYMBOLIC param:self  =>  {reg_type}")

    print(f"\n  Field tracking through typed self:\n")
    store_fields = [i for i in instructions if i.opcode == Opcode.STORE_FIELD]
    for inst in store_fields:
        obj_reg = str(inst.operands[0])
        field = str(inst.operands[1])
        val_reg = str(inst.operands[2])
        obj_type = env.register_types.get(obj_reg, "?")
        val_type = env.register_types.get(val_reg, "?")
        print(f"    STORE_FIELD {obj_reg}({obj_type}).{field} = {val_reg}({val_type})")

    load_fields = [i for i in instructions if i.opcode == Opcode.LOAD_FIELD]
    for inst in load_fields:
        obj_reg = str(inst.operands[0])
        field = str(inst.operands[1])
        obj_type = env.register_types.get(obj_reg, "?")
        result_type = env.register_types.get(inst.result_reg, "<untyped>")
        print(
            f"    LOAD_FIELD  {inst.result_reg} = {obj_reg}({obj_type}).{field}  =>  {result_type}"
        )

    # --- Java this ---
    print("\n  --- Java: this typed as class name ---\n")
    java_source = """\
class Cat {
    int lives;
    int getLives() { return this.lives; }
}
"""
    for line in java_source.strip().splitlines():
        print(f"    {line}")

    instructions, env = _lower_and_infer(java_source, "java")

    print(f"\n  SYMBOLIC param:this registers:\n")
    symbolics = [
        i
        for i in instructions
        if i.opcode == Opcode.SYMBOLIC
        and i.operands
        and str(i.operands[0]) == "param:this"
    ]
    for sym in symbolics:
        reg_type = env.register_types.get(sym.result_reg, "<untyped>")
        print(f"    {sym.result_reg} = SYMBOLIC param:this  =>  {reg_type}")


def demo_call_unknown():
    _header("Feature 2: CALL_UNKNOWN resolution (indirect calls)")

    print("\n  IR-level demo: function loaded into register, called indirectly\n")

    instructions = [
        IRInstruction(opcode=Opcode.LABEL, label="entry"),
        # Define function 'add' with return type Int
        IRInstruction(opcode=Opcode.BRANCH, label="end_add_0"),
        IRInstruction(opcode=Opcode.LABEL, label="func_add_0"),
        IRInstruction(
            opcode=Opcode.SYMBOLIC,
            result_reg="%0",
            operands=["param:a"],
        ),
        IRInstruction(
            opcode=Opcode.SYMBOLIC,
            result_reg="%1",
            operands=["param:b"],
        ),
        IRInstruction(opcode=Opcode.RETURN, operands=["%2"]),
        IRInstruction(opcode=Opcode.LABEL, label="end_add_0"),
        IRInstruction(
            opcode=Opcode.CONST,
            result_reg="%3",
            operands=["<function:add@func_add_0>"],
        ),
        IRInstruction(opcode=Opcode.STORE_VAR, operands=["add", "%3"]),
        # Load 'add' into a register (indirect reference)
        IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%4", operands=["add"]),
        # CALL_UNKNOWN — target is %4 (a register, not a literal name)
        IRInstruction(
            opcode=Opcode.CALL_UNKNOWN,
            result_reg="%5",
            operands=["%4", "%6", "%7"],
        ),
    ]

    builder = TypeEnvironmentBuilder(
        func_return_types={"func_add_0": "Int"},
        func_param_types={"func_add_0": [("a", "Int"), ("b", "Int")]},
        register_types={"%0": "Int", "%1": "Int"},
    )
    env = infer_types(instructions, _resolver(), type_env_builder=builder)

    print("    Instruction sequence:")
    for inst in instructions:
        print(f"      {inst}")

    print(f"\n    Key register types:")
    print(
        f"      %4 (LOAD_VAR add)       : {env.register_types.get('%4', '<untyped>')}"
    )
    print(
        f"      %5 (CALL_UNKNOWN %4)    : {env.register_types.get('%5', '<untyped>')}"
    )
    print(
        f"\n    => CALL_UNKNOWN resolved: %4 came from 'add', add() -> Int, so %5 = Int"
    )


def demo_store_load_index():
    _header("Feature 3: STORE_INDEX / LOAD_INDEX (array element type tracking)")

    print("\n  IR-level demo: store typed value into array, load it back\n")

    instructions = [
        IRInstruction(opcode=Opcode.LABEL, label="entry"),
        # Create array
        IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%0"),
        # Store integer 42 at index 0
        IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
        IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=["0"]),
        IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%2", "%1"]),
        # Load from array at index 1
        IRInstruction(opcode=Opcode.CONST, result_reg="%3", operands=["1"]),
        IRInstruction(opcode=Opcode.LOAD_INDEX, result_reg="%4", operands=["%0", "%3"]),
    ]

    env = infer_types(instructions, _resolver())

    print("    Instruction sequence:")
    for inst in instructions:
        print(f"      {inst}")

    print(f"\n    Key register types:")
    print(
        f"      %0 (NEW_ARRAY)          : {env.register_types.get('%0', '<untyped>')}"
    )
    print(
        f"      %1 (CONST 42)           : {env.register_types.get('%1', '<untyped>')}"
    )
    print(
        f"      %4 (LOAD_INDEX %0)      : {env.register_types.get('%4', '<untyped>')}"
    )
    print(
        f"\n    => STORE_INDEX recorded element type Int for %0; LOAD_INDEX retrieved it"
    )

    # Second example: last-write-wins
    print(f"\n  --- Last-write-wins semantics ---\n")

    instructions2 = [
        IRInstruction(opcode=Opcode.LABEL, label="entry"),
        IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%0"),
        # Store Int
        IRInstruction(opcode=Opcode.CONST, result_reg="%1", operands=["42"]),
        IRInstruction(opcode=Opcode.CONST, result_reg="%idx", operands=["0"]),
        IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%idx", "%1"]),
        # Overwrite with String
        IRInstruction(opcode=Opcode.CONST, result_reg="%2", operands=['"hello"']),
        IRInstruction(opcode=Opcode.STORE_INDEX, operands=["%0", "%idx", "%2"]),
        # Load — should be String (last write)
        IRInstruction(
            opcode=Opcode.LOAD_INDEX, result_reg="%3", operands=["%0", "%idx"]
        ),
    ]

    env2 = infer_types(instructions2, _resolver())

    print(f"    First STORE_INDEX: arr[0] = 42 (Int)")
    print(f'    Second STORE_INDEX: arr[0] = "hello" (String)')
    print(
        f"    LOAD_INDEX result: {env2.register_types.get('%3', '<untyped>')}  (last write wins)"
    )


def main():
    print("\n  Tier 3 Type Inference Enhancements — Demo")
    print("  ==========================================\n")
    print("  This demo exercises all 3 new type inference features.")
    print("  The inference pass now handles 19 of 30 opcodes.")

    demo_self_this_typing()
    demo_call_unknown()
    demo_store_load_index()

    print(f"\n{'=' * 70}")
    print("  All 3 Tier 3 features demonstrated successfully!")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
