"""Orchestrator — run() entry point."""
from __future__ import annotations

from typing import Any

from .ir import Opcode
from .parser import Parser
from .frontend import get_frontend
from .cfg import build_cfg
from .registry import build_registry, _parse_class_ref
from .vm import (
    VMState, SymbolicValue, StackFrame,
    StateUpdate, apply_update, _deserialize_value,
    _serialize_value,
)
from .backend import get_backend
from .registry import _try_execute_locally


def run(source: str, language: str = "python",
        entry_point: str | None = None, backend: str = "claude",
        max_steps: int = 100, verbose: bool = False) -> VMState:
    """End-to-end: parse → lower → CFG → LLM interpret."""
    # 1. Parse
    tree = Parser().parse(source, language)

    # 2. Lower to IR
    frontend = get_frontend(language)
    instructions = frontend.lower(tree, source.encode("utf-8"))

    if verbose:
        print("═══ IR ═══")
        for inst in instructions:
            print(f"  {inst}")
        print()

    # 3. Build CFG
    cfg = build_cfg(instructions)

    if verbose:
        print("═══ CFG ═══")
        print(cfg)

    # 4. Pick entry
    entry = entry_point or cfg.entry
    if entry not in cfg.blocks:
        # Try to find a function label matching the entry point
        for label in cfg.blocks:
            if entry in label:
                entry = label
                break
        else:
            raise ValueError(f"Entry point '{entry}' not found in CFG. "
                             f"Available: {list(cfg.blocks.keys())}")

    # 4b. Build function registry
    registry = build_registry(instructions, cfg)

    # 5. Initialize VM
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<main>"))

    # 6. Execute
    llm = get_backend(backend)
    current_label = entry
    ip = 0  # instruction pointer within current block
    llm_calls = 0

    for step in range(max_steps):
        block = cfg.blocks[current_label]

        if ip >= len(block.instructions):
            # End of block — follow successor or stop
            if block.successors:
                current_label = block.successors[0]
                ip = 0
                continue
            else:
                if verbose:
                    print(f"[step {step}] End of '{current_label}', "
                          "no successors. Stopping.")
                break

        instruction = block.instructions[ip]

        if verbose:
            print(f"[step {step}] {current_label}:{ip}  {instruction}")

        # Skip pseudo-instructions
        if instruction.opcode == Opcode.LABEL:
            ip += 1
            continue

        # Try local execution first, fall back to LLM
        update = _try_execute_locally(instruction, vm, cfg=cfg,
                                       registry=registry,
                                       current_label=current_label, ip=ip)
        used_llm = False
        if update is None:
            update = llm.interpret_instruction(instruction, vm)
            used_llm = True
            llm_calls += 1

        if verbose:
            tag = "LLM" if used_llm else "local"
            print(f"  [{tag}] {update.reasoning}")
            if update.register_writes:
                for reg, val in update.register_writes.items():
                    print(f"    {reg} = {_format_val(val)}")
            if update.var_writes:
                for var, val in update.var_writes.items():
                    print(f"    ${var} = {_format_val(val)}")
            if update.heap_writes:
                for hw in update.heap_writes:
                    print(f"    heap[{hw.obj_addr}].{hw.field} = "
                          f"{_format_val(hw.value)}")
            if update.new_objects:
                for obj in update.new_objects:
                    print(f"    new {obj.type_hint} @ {obj.addr}")
            if update.next_label:
                print(f"    → {update.next_label}")
            if update.path_condition:
                print(f"    path: {update.path_condition}")
            print()

        # For RETURN: save frame info BEFORE applying (which may pop it)
        is_return = instruction.opcode == Opcode.RETURN
        is_throw = instruction.opcode == Opcode.THROW
        return_frame = vm.current_frame if (is_return or is_throw) else None

        # For CALL with dispatch: set up the new frame's return info
        is_call_dispatch = (update.call_push is not None and
                            update.next_label is not None)
        if is_call_dispatch:
            # Save where to resume after the call returns
            call_result_reg = instruction.result_reg
            call_return_label = current_label
            call_return_ip = ip + 1

        apply_update(vm, update)

        if is_call_dispatch:
            # The new frame was just pushed — set its return info
            new_frame = vm.current_frame
            new_frame.return_label = call_return_label
            new_frame.return_ip = call_return_ip
            new_frame.result_reg = call_result_reg
            # For class constructors, the result_reg was already written
            # (the object address), so we mark it to not overwrite on return
            if instruction.opcode == Opcode.CALL_FUNCTION:
                func_val = vm.call_stack[-2].local_vars.get(instruction.operands[0])
                if func_val and _parse_class_ref(func_val):
                    new_frame.result_reg = None  # don't overwrite on return

        # Handle control flow
        if is_return or is_throw:
            if len(vm.call_stack) < 1:
                if verbose:
                    print(f"[step {step}] Top-level return/throw. Stopping.")
                break

            if return_frame and return_frame.function_name == "<main>":
                # Top-level return
                if verbose:
                    print(f"[step {step}] Top-level return/throw. Stopping.")
                break

            # Return to caller — write return value to caller's result register
            caller_frame = vm.current_frame
            if return_frame and return_frame.result_reg and update.return_value is not None:
                caller_frame.registers[return_frame.result_reg] = \
                    _deserialize_value(update.return_value, vm)

            if (return_frame and return_frame.return_label and
                    return_frame.return_label in cfg.blocks):
                current_label = return_frame.return_label
                ip = return_frame.return_ip if return_frame.return_ip is not None else 0
            else:
                if verbose:
                    print(f"[step {step}] No return label. Stopping.")
                break

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1

    if verbose:
        print(f"\n({step + 1} steps, {llm_calls} LLM calls)")

    return vm


def _format_val(v: Any) -> str:
    """Format a value for verbose display."""
    if isinstance(v, dict) and v.get("__symbolic__"):
        name = v.get("name", "?")
        constraints = v.get("constraints", [])
        if constraints:
            return f"{name} [{', '.join(str(c) for c in constraints)}]"
        hint = v.get("type_hint", "")
        return f"{name}" + (f" ({hint})" if hint else "")
    if isinstance(v, SymbolicValue):
        if v.constraints:
            return f"{v.name} [{', '.join(v.constraints)}]"
        return f"{v.name}" + (f" ({v.type_hint})" if v.type_hint else "")
    return repr(v)
