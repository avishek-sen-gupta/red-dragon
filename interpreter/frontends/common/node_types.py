"""Tree-sitter node type strings used in common frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class CommonNodeType:
    """Tree-sitter node type strings used in common frontend lowerers."""

    # ── Node types ────────────────────────────────────────────────────
    IDENTIFIER = "identifier"
    PAIR = "pair"
    SUBSCRIPT = "subscript"
    VARIABLE_DECLARATOR = "variable_declarator"

    # ── Member-access / attribute variants ────────────────────────────
    MEMBER_EXPRESSION = "member_expression"
    SELECTOR_EXPRESSION = "selector_expression"
    MEMBER_ACCESS_EXPRESSION = "member_access_expression"
    FIELD_ACCESS = "field_access"
    METHOD_INDEX_EXPRESSION = "method_index_expression"

    # ── Call argument wrappers ────────────────────────────────────────
    ARGUMENT = "argument"
    VALUE_ARGUMENT = "value_argument"

    # ── Control-flow clause types ─────────────────────────────────────
    ELIF_CLAUSE = "elif_clause"
    ELSE_CLAUSE = "else_clause"

    # ── Keywords (appear as node types in tree-sitter) ────────────────
    ELSE = "else"
    RETURN = "return"

    # ── Punctuation tokens ────────────────────────────────────────────
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    OPEN_BRACKET = "["
    CLOSE_BRACKET = "]"
    OPEN_BRACE = "{"
    CLOSE_BRACE = "}"
    COMMA = ","
    COLON = ":"
    SEMICOLON = ";"
    ARROW = "->"
