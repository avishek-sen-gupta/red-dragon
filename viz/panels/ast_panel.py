"""AST panel — collapsible tree view of the tree-sitter AST with current node highlighted."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Tree

from viz.pipeline import ASTNode


class ASTPanel(Tree):
    """Displays the tree-sitter AST as a collapsible tree widget."""

    current_instruction: reactive[IRInstruction | None] = reactive(None)

    def __init__(self, ast: ASTNode | None = None, **kwargs) -> None:
        super().__init__("AST", **kwargs)
        self._ast = ast
        self._node_map: dict[str, ASTNode] = {}

    def set_ast(self, ast: ASTNode) -> None:
        """Replace the AST tree with a new one and rebuild the widget tree."""
        self._ast = ast
        self._node_map.clear()
        self.root.remove_children()
        if self._ast:
            self._populate_tree(self.root, self._ast)
            self.root.expand()
            for child in self.root.children:
                child.expand()

    def on_mount(self) -> None:
        if self._ast:
            self._populate_tree(self.root, self._ast)
            self.root.expand()
            # Expand first level
            for child in self.root.children:
                child.expand()

    def _populate_tree(self, parent, ast_node: ASTNode) -> None:
        """Recursively add AST nodes to the tree widget."""
        label = self._make_label(ast_node)
        node_id = f"{ast_node.start_line}:{ast_node.start_col}-{ast_node.end_line}:{ast_node.end_col}"

        if ast_node.children:
            tree_node = parent.add(label, data=ast_node)
            for child in ast_node.children:
                self._populate_tree(tree_node, child)
        else:
            parent.add_leaf(label, data=ast_node)

    def _make_label(self, ast_node: ASTNode) -> str:
        """Build a display label for an AST node."""
        type_part = ast_node.node_type
        # For leaf nodes, show the text preview
        if not ast_node.children:
            text = ast_node.text.replace("\n", "\\n")
            if len(text) > 40:
                text = text[:37] + "..."
            return f"{type_part}: {text}"
        return type_part

    def watch_current_instruction(self, inst: InstructionBase | None) -> None:
        """When the current instruction changes, highlight the matching AST node."""
        if not inst or inst.source_location.is_unknown():
            return

        target_line = inst.source_location.start_line
        target_col = inst.source_location.start_col

        best_node = self._find_best_match(self.root, target_line, target_col)
        if best_node:
            best_node.expand()
            self.select_node(best_node)
            self.scroll_to_node(best_node)

    def _find_best_match(self, tree_node, target_line: int, target_col: int):
        """Find the tree node whose AST span best matches the target location."""
        best = None
        best_size = float("inf")

        for child in tree_node.children:
            ast_node = child.data
            if ast_node is None:
                continue

            # Check if target is within this node's span
            if self._contains(ast_node, target_line, target_col):
                span_size = (
                    (ast_node.end_line - ast_node.start_line) * 1000
                    + ast_node.end_col
                    - ast_node.start_col
                )
                if span_size < best_size:
                    best = child
                    best_size = span_size

                # Recurse into children for a tighter match
                deeper = self._find_best_match(child, target_line, target_col)
                if deeper and deeper.data:
                    deeper_ast = deeper.data
                    deeper_size = (
                        (deeper_ast.end_line - deeper_ast.start_line) * 1000
                        + deeper_ast.end_col
                        - deeper_ast.start_col
                    )
                    if deeper_size < best_size:
                        best = deeper
                        best_size = deeper_size

        return best

    def _contains(self, ast_node: ASTNode, line: int, col: int) -> bool:
        """Check if line:col is within the AST node's span."""
        if line < ast_node.start_line or line > ast_node.end_line:
            return False
        if line == ast_node.start_line and col < ast_node.start_col:
            return False
        if line == ast_node.end_line and col > ast_node.end_col:
            return False
        return True
