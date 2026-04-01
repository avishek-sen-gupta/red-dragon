# pyright: standard
"""Tree-sitter node type strings used in Lua frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class LuaNodeType:
    """Tree-sitter node type strings used in Lua frontend lowerers."""

    # -- Literals & atoms --------------------------------------------------
    IDENTIFIER = "identifier"
    NUMBER = "number"
    STRING = "string"
    TRUE = "true"
    FALSE = "false"
    NIL = "nil"
    STRING_CONTENT = "string_content"
    ESCAPE_SEQUENCE = "escape_sequence"

    # -- Expressions -------------------------------------------------------
    BINARY_EXPRESSION = "binary_expression"
    UNARY_EXPRESSION = "unary_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    FUNCTION_CALL = "function_call"
    DOT_INDEX_EXPRESSION = "dot_index_expression"
    BRACKET_INDEX_EXPRESSION = "bracket_index_expression"
    TABLE_CONSTRUCTOR = "table_constructor"
    EXPRESSION_LIST = "expression_list"
    FUNCTION_DEFINITION = "function_definition"
    VARARG_EXPRESSION = "vararg_expression"
    METHOD_INDEX_EXPRESSION = "method_index_expression"

    # -- Statements --------------------------------------------------------
    VARIABLE_DECLARATION = "variable_declaration"
    ASSIGNMENT_STATEMENT = "assignment_statement"
    FUNCTION_DECLARATION = "function_declaration"
    IF_STATEMENT = "if_statement"
    WHILE_STATEMENT = "while_statement"
    FOR_STATEMENT = "for_statement"
    REPEAT_STATEMENT = "repeat_statement"
    RETURN_STATEMENT = "return_statement"
    DO_STATEMENT = "do_statement"
    EXPRESSION_STATEMENT = "expression_statement"
    BREAK_STATEMENT = "break_statement"
    GOTO_STATEMENT = "goto_statement"
    LABEL_STATEMENT = "label_statement"

    # -- Control-flow clause types -----------------------------------------
    ELSEIF_STATEMENT = "elseif_statement"
    ELSE_STATEMENT = "else_statement"
    FOR_NUMERIC_CLAUSE = "for_numeric_clause"
    FOR_GENERIC_CLAUSE = "for_generic_clause"
    VARIABLE_LIST = "variable_list"

    # -- Table constructor -------------------------------------------------
    FIELD = "field"

    # -- Block / program containers ----------------------------------------
    BLOCK = "block"
    CHUNK = "chunk"

    # -- Comment / noise ---------------------------------------------------
    COMMENT = "comment"
    HASH_BANG_LINE = "hash_bang_line"
    NEWLINE = "\n"

    # -- Keywords (appear as node types) -----------------------------------
    RETURN = "return"
    ELSE = "else"
    DO = "do"
    END = "end"
