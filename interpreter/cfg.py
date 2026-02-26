"""CFG Builder."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ir import IRInstruction, Opcode
from . import constants


@dataclass
class BasicBlock:
    label: str
    instructions: list[IRInstruction] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)


@dataclass
class CFG:
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    entry: str = constants.CFG_ENTRY_LABEL

    def __str__(self) -> str:
        lines = []
        for label, block in self.blocks.items():
            preds = ", ".join(block.predecessors) if block.predecessors else "(none)"
            succs = ", ".join(block.successors) if block.successors else "(none)"
            lines.append(f"[{label}]  preds={preds}  succs={succs}")
            for inst in block.instructions:
                lines.append(f"  {inst}")
            lines.append("")
        return "\n".join(lines)


def build_cfg(instructions: list[IRInstruction]) -> CFG:
    """Partition instructions into basic blocks and wire edges."""
    cfg = CFG()

    # Phase 1: identify block starts
    label_to_idx: dict[str, int] = {}
    block_starts: set[int] = {0}

    for i, inst in enumerate(instructions):
        if inst.opcode == Opcode.LABEL:
            block_starts.add(i)
            label_to_idx[inst.label] = i
        elif inst.opcode in (
            Opcode.BRANCH,
            Opcode.BRANCH_IF,
            Opcode.RETURN,
            Opcode.THROW,
        ):
            if i + 1 < len(instructions):
                block_starts.add(i + 1)

    sorted_starts = sorted(block_starts)

    # Phase 2: create blocks
    for si, start in enumerate(sorted_starts):
        end = (
            sorted_starts[si + 1] if si + 1 < len(sorted_starts) else len(instructions)
        )
        block_insts = instructions[start:end]

        # Determine label
        if block_insts and block_insts[0].opcode == Opcode.LABEL:
            label = block_insts[0].label
            block_insts = block_insts[1:]  # don't include LABEL pseudo-inst
        else:
            label = f"__block_{start}"

        cfg.blocks[label] = BasicBlock(label=label, instructions=block_insts)

    # Phase 3: wire edges
    block_labels = list(cfg.blocks.keys())
    for i, label in enumerate(block_labels):
        block = cfg.blocks[label]
        if not block.instructions:
            # Empty block falls through
            if i + 1 < len(block_labels):
                _add_edge(cfg, label, block_labels[i + 1])
            continue

        last = block.instructions[-1]

        if last.opcode == Opcode.BRANCH:
            target = last.label
            if target in cfg.blocks:
                _add_edge(cfg, label, target)

        elif last.opcode == Opcode.BRANCH_IF:
            targets = last.label.split(",")
            for t in targets:
                t = t.strip()
                if t in cfg.blocks:
                    _add_edge(cfg, label, t)

        elif last.opcode in (Opcode.RETURN, Opcode.THROW):
            pass  # no successors

        else:
            # Fall through
            if i + 1 < len(block_labels):
                _add_edge(cfg, label, block_labels[i + 1])

    # Set entry
    if block_labels:
        cfg.entry = block_labels[0]

    return cfg


def _escape_mermaid(text: str) -> str:
    """Escape characters that break Mermaid node labels."""
    return text.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


def _instruction_summary(inst: IRInstruction, max_len: int = 60) -> str:
    """Return a truncated, Mermaid-safe string for an instruction."""
    raw = str(inst)
    truncated = raw[:max_len] + "..." if len(raw) > max_len else raw
    return _escape_mermaid(truncated)


def _node_id(label: str) -> str:
    """Sanitise a block label into a valid Mermaid node ID."""
    return label.replace(" ", "_").replace("-", "_")


def _build_subgraph_ranges(
    labels: list[str],
) -> list[tuple[str, int, int]]:
    """Identify function/class subgraph ranges from block label ordering.

    Returns a list of (display_name, start_index, end_index) where
    start_index is inclusive and end_index is exclusive.  The range
    covers all blocks from the opening label (e.g. ``func_foo_0``)
    up to *but not including* the closing label (``end_foo_0``).
    """
    import re

    func_prefix = constants.FUNC_LABEL_PREFIX
    class_prefix = constants.CLASS_LABEL_PREFIX
    end_class_prefix = constants.END_CLASS_LABEL_PREFIX

    # Map label -> index for fast lookup
    idx_of = {lbl: i for i, lbl in enumerate(labels)}

    ranges: list[tuple[str, int, int]] = []

    for i, lbl in enumerate(labels):
        if lbl.startswith(func_prefix):
            # func_NAME_N  →  end_NAME_N
            # Strip "func_" prefix, keep NAME_N suffix
            suffix = lbl[len(func_prefix) :]
            end_label = f"end_{suffix}"
            if end_label in idx_of:
                ranges.append((f"fn {suffix}", i, idx_of[end_label]))
        elif lbl.startswith(class_prefix) and not lbl.startswith(end_class_prefix):
            # class_NAME_N  →  end_class_NAME_N
            suffix = lbl[len(class_prefix) :]
            end_label = f"{end_class_prefix}{suffix}"
            if end_label in idx_of:
                ranges.append((f"class {suffix}", i, idx_of[end_label]))

    return ranges


def _render_node(label: str, block: BasicBlock, indent: str) -> str:
    """Render a single Mermaid node definition."""
    nid = _node_id(label)
    inst_lines = [_instruction_summary(inst) for inst in block.instructions]
    body = "<br/>".join(inst_lines) if inst_lines else "(empty)"
    node_label = f"<b>{_escape_mermaid(label)}</b><br/>{body}"
    return f'{indent}{nid}["{node_label}"]'


def cfg_to_mermaid(cfg: CFG) -> str:
    """Convert a CFG to a Mermaid flowchart TD diagram."""
    lines: list[str] = ["flowchart TD"]
    entry_node_id = ""
    block_labels = list(cfg.blocks.keys())

    # Detect function / class subgraph ranges
    sg_ranges = _build_subgraph_ranges(block_labels)
    # Set of indices that belong to a subgraph
    in_subgraph: set[int] = set()
    for _name, start, end in sg_ranges:
        in_subgraph.update(range(start, end))

    # Emit top-level (non-subgraph) nodes first
    for i, label in enumerate(block_labels):
        if label == cfg.entry:
            entry_node_id = _node_id(label)
        if i not in in_subgraph:
            lines.append(_render_node(label, cfg.blocks[label], "    "))

    # Emit subgraphs
    for sg_name, start, end in sg_ranges:
        sg_id = _node_id(sg_name)
        lines.append(f'    subgraph {sg_id}["{_escape_mermaid(sg_name)}"]')
        for i in range(start, end):
            label = block_labels[i]
            if label == cfg.entry:
                entry_node_id = _node_id(label)
            lines.append(_render_node(label, cfg.blocks[label], "        "))
        lines.append("    end")

    # Emit edges
    for label, block in cfg.blocks.items():
        src = _node_id(label)
        last = block.instructions[-1] if block.instructions else None
        is_branch_if = last is not None and last.opcode == Opcode.BRANCH_IF

        if is_branch_if and len(block.successors) == 2:
            true_target = block.successors[0]
            false_target = block.successors[1]
            lines.append(f'    {src} -->|"T"| {_node_id(true_target)}')
            lines.append(f'    {src} -->|"F"| {_node_id(false_target)}')
        else:
            for succ in block.successors:
                lines.append(f"    {src} --> {_node_id(succ)}")

    if entry_node_id:
        lines.append(f"    style {entry_node_id} fill:#28a745,color:#fff")

    return "\n".join(lines)


def _add_edge(cfg: CFG, src: str, dst: str):
    if dst not in cfg.blocks[src].successors:
        cfg.blocks[src].successors.append(dst)
    if src not in cfg.blocks[dst].predecessors:
        cfg.blocks[dst].predecessors.append(src)
