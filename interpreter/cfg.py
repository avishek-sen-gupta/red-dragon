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


def _extract_name(label: str, prefix: str) -> str:
    """Extract the base name from a label like ``func_foo_3`` → ``foo``.

    The label format is ``<prefix><name>_<counter>``.  We strip the
    prefix and the trailing ``_<digits>`` to recover the name.
    """
    import re

    suffix = label[len(prefix) :]
    match = re.match(r"^(.+)_(\d+)$", suffix)
    return match.group(1) if match else suffix


def _build_subgraph_ranges(
    labels: list[str],
) -> list[tuple[str, int, int]]:
    """Identify function/class subgraph ranges from block label ordering.

    Returns a list of (display_name, start_index, end_index) where
    start_index is inclusive and end_index is exclusive.  The range
    covers all blocks from the opening label (e.g. ``func_foo_0``)
    up to *but not including* the closing label (``end_foo_1``).

    Matching is by *name*, not by counter — ``func_foo_0`` pairs with
    the first ``end_foo_*`` that appears after it in label order.
    """
    func_prefix = constants.FUNC_LABEL_PREFIX
    class_prefix = constants.CLASS_LABEL_PREFIX
    end_class_prefix = constants.END_CLASS_LABEL_PREFIX

    ranges: list[tuple[str, int, int]] = []

    for i, lbl in enumerate(labels):
        if lbl.startswith(func_prefix):
            name = _extract_name(lbl, func_prefix)
            end_prefix = f"end_{name}_"
            # Find the first end_NAME_* label appearing after this block
            end_idx = next(
                (
                    j
                    for j in range(i + 1, len(labels))
                    if labels[j].startswith(end_prefix)
                ),
                -1,
            )
            if end_idx > 0:
                ranges.append((f"fn {name}", i, end_idx))

        elif lbl.startswith(class_prefix) and not lbl.startswith(end_class_prefix):
            name = _extract_name(lbl, class_prefix)
            end_prefix = f"{end_class_prefix}{name}_"
            end_idx = next(
                (
                    j
                    for j in range(i + 1, len(labels))
                    if labels[j].startswith(end_prefix)
                ),
                -1,
            )
            if end_idx > 0:
                ranges.append((f"class {name}", i, end_idx))

    return ranges


def _reachable_blocks(cfg: CFG) -> set[str]:
    """Return the set of block labels reachable from the entry and function roots via BFS.

    Function entry blocks (labels starting with ``FUNC_LABEL_PREFIX``) are
    treated as additional BFS roots so that function bodies remain visible
    even though the frontend emits a ``BRANCH end_foo`` that skips over them.
    """
    func_prefix = constants.FUNC_LABEL_PREFIX
    roots = [cfg.entry] + [lbl for lbl in cfg.blocks if lbl.startswith(func_prefix)]
    visited: set[str] = set()
    queue = list(roots)
    while queue:
        label = queue.pop(0)
        if label in visited:
            continue
        visited.add(label)
        if label in cfg.blocks:
            queue.extend(cfg.blocks[label].successors)
    return visited


def _build_call_target_map(block_labels: list[str]) -> dict[str, str]:
    """Map function name → entry label for all ``func_<name>_<counter>`` labels.

    Example: ``["func_foo_0", "func_bar_2"]`` → ``{"foo": "func_foo_0", "bar": "func_bar_2"}``.
    Only the *first* matching label per name is kept (there should be exactly one).
    """
    func_prefix = constants.FUNC_LABEL_PREFIX
    result: dict[str, str] = {}
    for lbl in block_labels:
        if not lbl.startswith(func_prefix):
            continue
        name = _extract_name(lbl, func_prefix)
        if name not in result:
            result[name] = lbl
    return result


def _node_shape(block: BasicBlock, is_entry: bool) -> tuple[str, str]:
    """Return (open_delim, close_delim) for the Mermaid node shape."""
    if is_entry:
        return '(["', '"])'
    last = block.instructions[-1] if block.instructions else None
    if last and last.opcode == Opcode.BRANCH_IF:
        return '{"', '"}'
    if last and last.opcode in (Opcode.RETURN, Opcode.THROW):
        return '(["', '"])'
    return '["', '"]'


def _collapse_inst_lines(
    lines: list[str], max_lines: int = constants.MERMAID_MAX_NODE_LINES
) -> list[str]:
    """Collapse long instruction lists, preserving the terminator (last line).

    If *lines* has more than *max_lines* entries, return the first
    ``max_lines - 2`` lines, an ``... (N more)`` placeholder, and the
    last line.  Otherwise return *lines* unchanged.
    """
    if len(lines) <= max_lines:
        return lines
    head_count = max_lines - 2
    hidden = len(lines) - head_count - 1
    return lines[:head_count] + [f"... ({hidden} more)"] + [lines[-1]]


def _render_node(
    label: str, block: BasicBlock, indent: str, is_entry: bool = False
) -> str:
    """Render a single Mermaid node definition."""
    nid = _node_id(label)
    inst_lines = _collapse_inst_lines(
        [_instruction_summary(inst) for inst in block.instructions]
    )
    body = "<br/>".join(inst_lines) if inst_lines else "(empty)"
    node_label = f"<b>{_escape_mermaid(label)}</b><br/>{body}"
    open_delim, close_delim = _node_shape(block, is_entry)
    return f"{indent}{nid}{open_delim}{node_label}{close_delim}"


def cfg_to_mermaid(cfg: CFG) -> str:
    """Convert a CFG to a Mermaid flowchart TD diagram."""
    lines: list[str] = ["flowchart TD"]
    entry_node_id = ""

    reachable = _reachable_blocks(cfg)
    block_labels = [lbl for lbl in cfg.blocks if lbl in reachable]

    # Detect function / class subgraph ranges
    sg_ranges = _build_subgraph_ranges(block_labels)
    # Set of indices that belong to a subgraph
    in_subgraph: set[int] = set()
    for _name, start, end in sg_ranges:
        in_subgraph.update(range(start, end))

    # Emit top-level (non-subgraph) nodes first
    for i, label in enumerate(block_labels):
        is_entry = label == cfg.entry
        if is_entry:
            entry_node_id = _node_id(label)
        if i not in in_subgraph:
            lines.append(
                _render_node(label, cfg.blocks[label], "    ", is_entry=is_entry)
            )

    # Emit subgraphs
    for sg_name, start, end in sg_ranges:
        sg_id = _node_id(sg_name)
        lines.append(f'    subgraph {sg_id}["{_escape_mermaid(sg_name)}"]')
        for i in range(start, end):
            label = block_labels[i]
            is_entry = label == cfg.entry
            if is_entry:
                entry_node_id = _node_id(label)
            lines.append(
                _render_node(label, cfg.blocks[label], "        ", is_entry=is_entry)
            )
        lines.append("    end")

    # Emit edges (only for reachable blocks)
    for label in block_labels:
        block = cfg.blocks[label]
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

    # Emit dashed call edges for CALL_FUNCTION instructions
    call_target_map = _build_call_target_map(block_labels)
    for label in block_labels:
        block = cfg.blocks[label]
        src = _node_id(label)
        for inst in block.instructions:
            if inst.opcode != Opcode.CALL_FUNCTION or not inst.operands:
                continue
            func_name = inst.operands[0]
            target_label = call_target_map.get(func_name, "")
            if target_label:
                lines.append(f'    {src} -.->|"call"| {_node_id(target_label)}')

    if entry_node_id:
        lines.append(f"    style {entry_node_id} fill:#28a745,color:#fff")

    return "\n".join(lines)


def _add_edge(cfg: CFG, src: str, dst: str):
    if dst not in cfg.blocks[src].successors:
        cfg.blocks[src].successors.append(dst)
    if src not in cfg.blocks[dst].predecessors:
        cfg.blocks[dst].predecessors.append(src)
