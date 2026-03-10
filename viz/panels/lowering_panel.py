"""Lowering trace panel — collapsible tree of handler invocations with emitted IR."""

from __future__ import annotations

from textual.widgets import Tree

from viz.lowering_trace import LoweringEvent


class LoweringPanel(Tree):
    """Displays the lowering event tree — which handler processed which AST node."""

    def __init__(self, events: list[LoweringEvent] | None = None, **kwargs) -> None:
        super().__init__("Lowering Trace", **kwargs)
        self._events = events or []

    def on_mount(self) -> None:
        if self._events:
            for event in self._events:
                self._add_event(self.root, event)
            self.root.expand()
            # Expand first level
            for child in self.root.children:
                child.expand()

    def _add_event(self, parent, event: LoweringEvent) -> None:
        label = self._make_label(event)

        if event.children or event.instructions_emitted:
            node = parent.add(label, data=event)

            # Add emitted instructions as leaves
            for inst in event.instructions_emitted:
                inst_label = f"→ {inst}"
                node.add_leaf(inst_label, data=inst)

            # Recurse into children
            for child in event.children:
                self._add_event(node, child)
        else:
            parent.add_leaf(label, data=event)

    def _make_label(self, event: LoweringEvent) -> str:
        # Node type and handler
        type_part = event.ast_node_type
        handler_part = event.handler_name

        # Module indicator
        if event.is_shared:
            module_tag = "common"
        elif event.handler_module:
            # Extract language-specific part
            parts = event.handler_module.split(".")
            lang_parts = [
                p for p in parts if p not in ("interpreter", "frontends", "common")
            ]
            module_tag = (
                ".".join(lang_parts[-2:])
                if len(lang_parts) >= 2
                else lang_parts[-1] if lang_parts else "?"
            )
        else:
            module_tag = "fallback"

        # Dispatch type indicator
        dispatch_icon = {
            "expr": "E",
            "stmt": "S",
            "block": "B",
            "fallback": "?",
        }.get(event.dispatch_type, "?")

        # Short text preview
        text = event.ast_text.replace("\n", "\\n")
        if len(text) > 40:
            text = text[:37] + "..."

        inst_count = len(event.instructions_emitted)
        child_count = len(event.children)
        counts = ""
        if inst_count:
            counts += f" [{inst_count} IR]"
        if child_count:
            counts += f" [{child_count} sub]"

        return f'[{dispatch_icon}] {type_part} → {handler_part} ({module_tag}){counts}  "{text}"'
