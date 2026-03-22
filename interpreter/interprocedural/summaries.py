"""Function summary extraction for interprocedural dataflow analysis.

Builds FunctionSummary objects that capture which inputs (params, field reads)
flow to which outputs (return value, field writes) for a single function.
"""

from __future__ import annotations

import logging
from functools import reduce

from interpreter.cfg_types import BasicBlock, CFG
from interpreter.dataflow import DataflowResult, Definition, analyze
from interpreter.ir import Opcode
from interpreter import constants
from interpreter.interprocedural.types import (
    CallContext,
    FieldEndpoint,
    FlowEndpoint,
    FunctionEntry,
    FunctionSummary,
    InstructionLocation,
    NO_DEFINITION,
    ReturnEndpoint,
    VariableEndpoint,
)

logger = logging.getLogger(__name__)


def extract_sub_cfg(cfg: CFG, function_entry: FunctionEntry) -> CFG:
    """Extract the sub-CFG for a single function.

    Collects all blocks whose labels start with the function's entry label
    (e.g., func__foo, func__foo_if_true_1, etc.).
    """
    prefix = function_entry.label
    matching_blocks = {
        label: block
        for label, block in cfg.blocks.items()
        if label == prefix or label.startswith(prefix + "_")
    }

    # Rebuild with predecessors/successors filtered to only included blocks
    filtered_blocks = {
        label: BasicBlock(
            label=block.label,
            instructions=block.instructions,
            successors=[s for s in block.successors if s in matching_blocks],
            predecessors=[p for p in block.predecessors if p in matching_blocks],
        )
        for label, block in matching_blocks.items()
    }

    logger.info("Extracted sub-CFG for %s: %d blocks", prefix, len(filtered_blocks))

    return CFG(blocks=filtered_blocks, entry=prefix)


def _find_param_names(cfg: CFG) -> frozenset[str]:
    """Find all parameter names declared via SYMBOLIC param:x → STORE_VAR x patterns."""
    return frozenset(
        inst.operands[0]
        for block in cfg.blocks.values()
        for inst in block.instructions
        if inst.opcode == Opcode.STORE_VAR
        and len(inst.operands) >= 2
        and _is_param_store(cfg, block, inst)
    )


def _is_param_store(cfg: CFG, block: BasicBlock, store_inst) -> bool:
    """Check if a STORE_VAR's RHS register was produced by a SYMBOLIC param: instruction."""
    rhs_reg = store_inst.operands[1]
    return any(
        inst.opcode == Opcode.SYMBOLIC
        and inst.result_reg == rhs_reg
        and len(inst.operands) >= 1
        and str(inst.operands[0]).startswith(constants.PARAM_PREFIX)
        for inst in block.instructions
    )


def _find_return_operands(cfg: CFG) -> list[tuple[str, str, int]]:
    """Find all RETURN instructions and their operand registers.

    Returns list of (block_label, operand_register, instruction_index).
    """
    return [
        (label, str(inst.operands[0]), idx)
        for label, block in cfg.blocks.items()
        for idx, inst in enumerate(block.instructions)
        if inst.opcode == Opcode.RETURN and len(inst.operands) >= 1
    ]


def _find_store_fields(cfg: CFG) -> list[tuple[str, int, str, str, str]]:
    """Find all STORE_FIELD instructions.

    Returns list of (block_label, instruction_index, obj_reg, field_name, val_reg).
    STORE_FIELD operands: [obj_reg, field_name, val_reg]
    """
    return [
        (
            label,
            idx,
            str(inst.operands[0]),
            str(inst.operands[1]),
            str(inst.operands[2]),
        )
        for label, block in cfg.blocks.items()
        for idx, inst in enumerate(block.instructions)
        if inst.opcode == Opcode.STORE_FIELD and len(inst.operands) >= 3
    ]


def _find_load_fields(cfg: CFG) -> list[tuple[str, int, str, str, str]]:
    """Find all LOAD_FIELD instructions.

    Returns list of (block_label, instruction_index, obj_reg, field_name, result_reg).
    LOAD_FIELD operands: [obj_reg, field_name], result_reg = result
    """
    return [
        (label, idx, str(inst.operands[0]), str(inst.operands[1]), inst.result_reg)
        for label, block in cfg.blocks.items()
        for idx, inst in enumerate(block.instructions)
        if inst.opcode == Opcode.LOAD_FIELD
        and len(inst.operands) >= 2
        and inst.result_reg is not None
    ]


def _trace_register_to_params(
    register: str,
    dependency_graph: dict[str, set[str]],
    raw_dependency_graph: dict[str, set[str]],
    param_names: frozenset[str],
) -> frozenset[str]:
    """Trace a register back through the dependency graph to find which params it depends on.

    Checks both the transitive dependency graph (for named variables) and
    traces registers through raw dependencies.
    """
    # If the register itself is a param name, return it directly
    if register in param_names:
        return frozenset({register})

    # Check transitive dependency graph for named variable dependencies
    deps = dependency_graph.get(register, set())
    return frozenset(d for d in deps if d in param_names)


def _trace_register_to_named_var(
    register: str,
    dataflow: DataflowResult,
) -> str | None:
    """Trace a register back to the named variable it loaded from.

    Looks for def-use chains where the register was defined by a LOAD_VAR.
    Returns the variable name, or None if not traceable.
    """
    for defn in dataflow.definitions:
        if defn.variable == register and defn.instruction.opcode == Opcode.LOAD_VAR:
            return str(defn.instruction.operands[0])
    return None


def _find_register_source_var(
    register: str,
    cfg: CFG,
) -> str | None:
    """Find the named variable that a register was loaded from via LOAD_VAR."""
    for block in cfg.blocks.values():
        for inst in block.instructions:
            if (
                inst.opcode == Opcode.LOAD_VAR
                and inst.result_reg == register
                and len(inst.operands) >= 1
            ):
                return str(inst.operands[0])
    return None


def _make_var_endpoint(name: str, dataflow: DataflowResult) -> VariableEndpoint:
    """Create a VariableEndpoint for a named variable using its definition from dataflow."""
    matching_defs = [d for d in dataflow.definitions if d.variable == name]
    defn = matching_defs[0] if matching_defs else NO_DEFINITION
    return VariableEndpoint(name=name, definition=defn)


def _build_return_flows(
    cfg: CFG,
    dataflow: DataflowResult,
    param_names: frozenset[str],
    function_entry: FunctionEntry,
) -> list[tuple[FlowEndpoint, FlowEndpoint]]:
    """Build flows from params/fields to RETURN instructions."""
    returns = _find_return_operands(cfg)
    load_fields = _find_load_fields(cfg)

    flows: list[tuple[FlowEndpoint, FlowEndpoint]] = []

    for block_label, ret_operand, ret_idx in returns:
        location = InstructionLocation(
            block_label=block_label, instruction_index=ret_idx
        )
        ret_endpoint = ReturnEndpoint(function=function_entry, location=location)

        # Trace the return operand to find which variable it was loaded from
        source_var = _find_register_source_var(ret_operand, cfg)

        if source_var is not None and source_var in param_names:
            # Direct param → return
            flows.append((_make_var_endpoint(source_var, dataflow), ret_endpoint))
        elif source_var is not None:
            # Indirect: check if this variable depends on any params
            param_deps = _trace_register_to_params(
                source_var,
                dataflow.dependency_graph,
                dataflow.raw_dependency_graph,
                param_names,
            )
            flows.extend(
                (_make_var_endpoint(p, dataflow), ret_endpoint) for p in param_deps
            )

            # Check if the variable was loaded from a field (field → return flow)
            _add_field_to_return_flows(
                source_var, cfg, dataflow, param_names, ret_endpoint, load_fields, flows
            )

    return flows


def _add_field_to_return_flows(
    var_name: str,
    cfg: CFG,
    dataflow: DataflowResult,
    param_names: frozenset[str],
    ret_endpoint: ReturnEndpoint,
    load_fields: list[tuple[str, int, str, str, str]],
    flows: list[tuple[FlowEndpoint, FlowEndpoint]],
) -> None:
    """Check if a variable was defined by a LOAD_FIELD and add field→return flows."""
    # Find STORE_VAR instructions for this variable where the RHS comes from a LOAD_FIELD
    for block in cfg.blocks.values():
        for inst in block.instructions:
            if (
                inst.opcode == Opcode.STORE_VAR
                and len(inst.operands) >= 2
                and inst.operands[0] == var_name
            ):
                rhs_reg = inst.operands[1]
                # Check if rhs_reg was produced by a LOAD_FIELD
                for lf_label, lf_idx, lf_obj_reg, lf_field, lf_result in load_fields:
                    if lf_result == rhs_reg:
                        # Found: field read feeds into this variable
                        obj_var = _find_register_source_var(lf_obj_reg, cfg)
                        if obj_var is not None and obj_var in param_names:
                            lf_location = InstructionLocation(
                                block_label=lf_label,
                                instruction_index=lf_idx,
                            )
                            field_src = FieldEndpoint(
                                base=_make_var_endpoint(obj_var, dataflow),
                                field=lf_field,
                                location=lf_location,
                            )
                            flows.append((field_src, ret_endpoint))


def _build_field_write_flows(
    cfg: CFG,
    dataflow: DataflowResult,
    param_names: frozenset[str],
) -> list[tuple[FlowEndpoint, FlowEndpoint]]:
    """Build flows from params to STORE_FIELD instructions."""
    store_fields = _find_store_fields(cfg)
    flows: list[tuple[FlowEndpoint, FlowEndpoint]] = []

    for sf_label, sf_idx, sf_obj_reg, sf_field, sf_val_reg in store_fields:
        location = InstructionLocation(block_label=sf_label, instruction_index=sf_idx)

        # Find which named variable the obj register was loaded from
        obj_var = _find_register_source_var(sf_obj_reg, cfg)
        if obj_var is None or obj_var not in param_names:
            continue

        obj_endpoint = _make_var_endpoint(obj_var, dataflow)
        field_endpoint = FieldEndpoint(
            base=obj_endpoint, field=sf_field, location=location
        )

        # Trace value register back to params
        val_var = _find_register_source_var(sf_val_reg, cfg)
        if val_var is not None and val_var in param_names:
            flows.append((_make_var_endpoint(val_var, dataflow), field_endpoint))
        elif val_var is not None:
            param_deps = _trace_register_to_params(
                val_var,
                dataflow.dependency_graph,
                dataflow.raw_dependency_graph,
                param_names,
            )
            flows.extend(
                (_make_var_endpoint(p, dataflow), field_endpoint) for p in param_deps
            )

    return flows


def build_summary(
    cfg: CFG, function_entry: FunctionEntry, context: CallContext
) -> FunctionSummary:
    """Run intraprocedural analysis on a function and extract flow endpoints.

    1. Extract the sub-CFG for the function
    2. Run dataflow analysis on it
    3. Map dependency graph to FlowEndpoint pairs
    """
    sub_cfg = extract_sub_cfg(cfg, function_entry)

    logger.info("Running dataflow analysis for %s", function_entry.label)
    dataflow = analyze(sub_cfg)

    param_names = _find_param_names(sub_cfg)
    logger.info("Function %s has params: %s", function_entry.label, param_names)

    return_flows = _build_return_flows(sub_cfg, dataflow, param_names, function_entry)
    field_write_flows = _build_field_write_flows(sub_cfg, dataflow, param_names)

    all_flows = frozenset(return_flows + field_write_flows)

    logger.info("Built summary for %s: %d flows", function_entry.label, len(all_flows))

    return FunctionSummary(
        function=function_entry,
        context=context,
        flows=all_flows,
    )
