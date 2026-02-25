"""CFG Builder."""
from __future__ import annotations

from dataclasses import dataclass, field

from .ir import IRInstruction, Opcode


@dataclass
class BasicBlock:
    label: str
    instructions: list[IRInstruction] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)


@dataclass
class CFG:
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    entry: str = "entry"

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
        elif inst.opcode in (Opcode.BRANCH, Opcode.BRANCH_IF,
                             Opcode.RETURN, Opcode.THROW):
            if i + 1 < len(instructions):
                block_starts.add(i + 1)

    sorted_starts = sorted(block_starts)

    # Phase 2: create blocks
    for si, start in enumerate(sorted_starts):
        end = sorted_starts[si + 1] if si + 1 < len(sorted_starts) else len(instructions)
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


def _add_edge(cfg: CFG, src: str, dst: str):
    if dst not in cfg.blocks[src].successors:
        cfg.blocks[src].successors.append(dst)
    if src not in cfg.blocks[dst].predecessors:
        cfg.blocks[dst].predecessors.append(src)
