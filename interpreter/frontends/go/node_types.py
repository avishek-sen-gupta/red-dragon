"""Tree-sitter node type strings used in Go frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class GoNodeType:
    """Tree-sitter node type strings used in Go frontend lowerers."""

    # -- Literals & atoms -----------------------------------------------------
    IDENTIFIER = "identifier"
    INT_LITERAL = "int_literal"
    FLOAT_LITERAL = "float_literal"
    INTERPRETED_STRING_LITERAL = "interpreted_string_literal"
    RAW_STRING_LITERAL = "raw_string_literal"
    TRUE = "true"
    FALSE = "false"
    NIL = "nil"
    TYPE_IDENTIFIER = "type_identifier"
    FIELD_IDENTIFIER = "field_identifier"

    # -- Expressions ----------------------------------------------------------
    BINARY_EXPRESSION = "binary_expression"
    UNARY_EXPRESSION = "unary_expression"
    CALL_EXPRESSION = "call_expression"
    SELECTOR_EXPRESSION = "selector_expression"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    INDEX_EXPRESSION = "index_expression"
    COMPOSITE_LITERAL = "composite_literal"
    TYPE_ASSERTION_EXPRESSION = "type_assertion_expression"
    SLICE_EXPRESSION = "slice_expression"
    FUNC_LITERAL = "func_literal"
    CHANNEL_TYPE = "channel_type"
    SLICE_TYPE = "slice_type"
    EXPRESSION_LIST = "expression_list"
    LITERAL_VALUE = "literal_value"
    KEYED_ELEMENT = "keyed_element"
    LITERAL_ELEMENT = "literal_element"

    # -- Declarations ---------------------------------------------------------
    FUNCTION_DECLARATION = "function_declaration"
    METHOD_DECLARATION = "method_declaration"
    TYPE_DECLARATION = "type_declaration"
    VAR_DECLARATION = "var_declaration"
    CONST_DECLARATION = "const_declaration"
    SHORT_VAR_DECLARATION = "short_var_declaration"
    PARAMETER_DECLARATION = "parameter_declaration"
    TYPE_SPEC = "type_spec"
    STRUCT_TYPE = "struct_type"
    VAR_SPEC = "var_spec"
    VAR_SPEC_LIST = "var_spec_list"
    CONST_SPEC = "const_spec"

    # -- Statements -----------------------------------------------------------
    EXPRESSION_STATEMENT = "expression_statement"
    ASSIGNMENT_STATEMENT = "assignment_statement"
    RETURN_STATEMENT = "return_statement"
    IF_STATEMENT = "if_statement"
    FOR_STATEMENT = "for_statement"
    INC_STATEMENT = "inc_statement"
    DEC_STATEMENT = "dec_statement"
    BREAK_STATEMENT = "break_statement"
    CONTINUE_STATEMENT = "continue_statement"
    DEFER_STATEMENT = "defer_statement"
    GO_STATEMENT = "go_statement"
    SEND_STATEMENT = "send_statement"
    GOTO_STATEMENT = "goto_statement"
    RECEIVE_STATEMENT = "receive_statement"
    LABELED_STATEMENT = "labeled_statement"

    # -- Switch / select ------------------------------------------------------
    EXPRESSION_SWITCH_STATEMENT = "expression_switch_statement"
    TYPE_SWITCH_STATEMENT = "type_switch_statement"
    SELECT_STATEMENT = "select_statement"
    EXPRESSION_CASE = "expression_case"
    DEFAULT_CASE = "default_case"
    TYPE_SWITCH_HEADER = "type_switch_header"
    TYPE_CASE = "type_case"
    COMMUNICATION_CASE = "communication_case"

    # -- Control-flow clause types --------------------------------------------
    FOR_CLAUSE = "for_clause"
    RANGE_CLAUSE = "range_clause"
    LABEL_NAME = "label_name"

    # -- Block / source containers --------------------------------------------
    BLOCK = "block"
    STATEMENT_LIST = "statement_list"
    SOURCE_FILE = "source_file"

    # -- Noise / comments -----------------------------------------------------
    COMMENT = "comment"
    PACKAGE_CLAUSE = "package_clause"
    IMPORT_DECLARATION = "import_declaration"
    NEWLINE = "\n"

    # -- Keywords (appear as node types in tree-sitter) -----------------------
    RETURN = "return"
    FOR = "for"
    DEFER = "defer"
    GO = "go"
    CASE = "case"

    # -- Punctuation tokens ---------------------------------------------------
    COMMA = ","
    COLON = ":"
