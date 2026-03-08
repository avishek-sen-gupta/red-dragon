"""Tree-sitter node type strings used in Python frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class PythonNodeType:
    """Tree-sitter node type strings used in the Python frontend."""

    # ── Literals / atoms ─────────────────────────────────────────────
    IDENTIFIER = "identifier"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    CONCATENATED_STRING = "concatenated_string"
    TRUE = "true"
    FALSE = "false"
    NONE = "none"
    ELLIPSIS = "ellipsis"

    # ── String internals (f-strings) ─────────────────────────────────
    INTERPOLATION = "interpolation"
    FORMAT_SPECIFIER = "format_specifier"
    STRING_CONTENT = "string_content"
    STRING_START = "string_start"
    STRING_END = "string_end"
    TYPE_CONVERSION = "type_conversion"

    # ── Operators ────────────────────────────────────────────────────
    BINARY_OPERATOR = "binary_operator"
    BOOLEAN_OPERATOR = "boolean_operator"
    COMPARISON_OPERATOR = "comparison_operator"
    UNARY_OPERATOR = "unary_operator"
    NOT_OPERATOR = "not_operator"

    # ── Expressions ──────────────────────────────────────────────────
    CALL = "call"
    ATTRIBUTE = "attribute"
    SUBSCRIPT = "subscript"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    CONDITIONAL_EXPRESSION = "conditional_expression"
    NAMED_EXPRESSION = "named_expression"
    GENERATOR_EXPRESSION = "generator_expression"
    EXPRESSION_LIST = "expression_list"
    SLICE = "slice"

    # ── Collection literals ──────────────────────────────────────────
    LIST = "list"
    DICTIONARY = "dictionary"
    TUPLE = "tuple"
    SET = "set"

    # ── Comprehensions ───────────────────────────────────────────────
    LIST_COMPREHENSION = "list_comprehension"
    DICTIONARY_COMPREHENSION = "dictionary_comprehension"
    SET_COMPREHENSION = "set_comprehension"
    FOR_IN_CLAUSE = "for_in_clause"
    IF_CLAUSE = "if_clause"

    # ── Splat / spread ───────────────────────────────────────────────
    LIST_SPLAT = "list_splat"
    DICTIONARY_SPLAT = "dictionary_splat"
    SPLAT_PATTERN = "splat_pattern"

    # ── Lambda ───────────────────────────────────────────────────────
    LAMBDA = "lambda"
    LAMBDA_PARAMETERS = "lambda_parameters"

    # ── Yield / await ────────────────────────────────────────────────
    YIELD = "yield"
    AWAIT = "await"

    # ── Parameter types ──────────────────────────────────────────────
    DEFAULT_PARAMETER = "default_parameter"
    TYPED_PARAMETER = "typed_parameter"
    TYPED_DEFAULT_PARAMETER = "typed_default_parameter"
    KEYWORD_SEPARATOR = "keyword_separator"
    POSITIONAL_SEPARATOR = "positional_separator"

    # ── Statements ───────────────────────────────────────────────────
    EXPRESSION_STATEMENT = "expression_statement"
    ASSIGNMENT = "assignment"
    AUGMENTED_ASSIGNMENT = "augmented_assignment"
    RETURN_STATEMENT = "return_statement"
    PASS_STATEMENT = "pass_statement"
    BREAK_STATEMENT = "break_statement"
    CONTINUE_STATEMENT = "continue_statement"
    GLOBAL_STATEMENT = "global_statement"
    NONLOCAL_STATEMENT = "nonlocal_statement"
    DELETE_STATEMENT = "delete_statement"
    ASSERT_STATEMENT = "assert_statement"
    TYPE_ALIAS_STATEMENT = "type_alias_statement"

    # ── Control flow ─────────────────────────────────────────────────
    IF_STATEMENT = "if_statement"
    ELIF_CLAUSE = "elif_clause"
    ELSE_CLAUSE = "else_clause"
    WHILE_STATEMENT = "while_statement"
    FOR_STATEMENT = "for_statement"
    WITH_STATEMENT = "with_statement"
    WITH_CLAUSE = "with_clause"
    WITH_ITEM = "with_item"

    # ── Exception handling ───────────────────────────────────────────
    RAISE_STATEMENT = "raise_statement"
    TRY_STATEMENT = "try_statement"
    EXCEPT_CLAUSE = "except_clause"
    FINALLY_CLAUSE = "finally_clause"
    AS_PATTERN = "as_pattern"

    # ── Definitions ──────────────────────────────────────────────────
    FUNCTION_DEFINITION = "function_definition"
    ARGUMENT_LIST = "argument_list"
    CLASS_DEFINITION = "class_definition"
    DECORATED_DEFINITION = "decorated_definition"
    DECORATOR = "decorator"

    # ── Import ───────────────────────────────────────────────────────
    IMPORT_STATEMENT = "import_statement"
    IMPORT_FROM_STATEMENT = "import_from_statement"
    DOTTED_NAME = "dotted_name"

    # ── Match / case ─────────────────────────────────────────────────
    MATCH_STATEMENT = "match_statement"
    CASE_CLAUSE = "case_clause"
    CASE_PATTERN = "case_pattern"
    LIST_PATTERN = "list_pattern"
    DICT_PATTERN = "dict_pattern"
    PATTERN_LIST = "pattern_list"
    TUPLE_PATTERN = "tuple_pattern"

    # ── Containers / structural ──────────────────────────────────────
    BLOCK = "block"
    MODULE = "module"
    PAIR = "pair"
    COMMENT = "comment"
    NEWLINE = "newline"

    # ── Keyword tokens (appear as node types in tree-sitter) ────────
    IF_KEYWORD = "if"
    ELSE_KEYWORD = "else"

    # ── Punctuation tokens ───────────────────────────────────────────
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    OPEN_BRACKET = "["
    CLOSE_BRACKET = "]"
    OPEN_BRACE = "{"
    CLOSE_BRACE = "}"
    COMMA = ","
    COLON = ":"
    NEWLINE_CHAR = "\n"
