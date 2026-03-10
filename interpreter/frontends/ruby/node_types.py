"""Tree-sitter node type strings used in Ruby frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.
"""


class RubyNodeType:
    """Tree-sitter node type strings used in the Ruby frontend."""

    # ── Literals / atoms ─────────────────────────────────────────────
    IDENTIFIER = "identifier"
    INSTANCE_VARIABLE = "instance_variable"
    CONSTANT = "constant"
    GLOBAL_VARIABLE = "global_variable"
    CLASS_VARIABLE = "class_variable"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    SIMPLE_SYMBOL = "simple_symbol"
    HASH_KEY_SYMBOL = "hash_key_symbol"
    DELIMITED_SYMBOL = "delimited_symbol"
    REGEX = "regex"
    TRUE = "true"
    FALSE = "false"
    NIL = "nil"
    SELF = "self"
    HEREDOC_BEGINNING = "heredoc_beginning"
    HEREDOC_BODY = "heredoc_body"
    HEREDOC_CONTENT = "heredoc_content"

    # ── String internals ─────────────────────────────────────────────
    INTERPOLATION = "interpolation"
    STRING_CONTENT = "string_content"

    # ── Operators ────────────────────────────────────────────────────
    BINARY = "binary"
    UNARY = "unary"
    CONDITIONAL = "conditional"

    # ── Expressions ──────────────────────────────────────────────────
    SCOPE_RESOLUTION = "scope_resolution"
    CALL = "call"
    PARENTHESIZED_EXPRESSION = "parenthesized_expression"
    PARENTHESIZED_STATEMENTS = "parenthesized_statements"
    ELEMENT_REFERENCE = "element_reference"
    ARGUMENT_LIST = "argument_list"
    RIGHT_ASSIGNMENT_LIST = "right_assignment_list"

    # ── Collection literals ──────────────────────────────────────────
    ARRAY = "array"
    HASH = "hash"
    STRING_ARRAY = "string_array"
    SYMBOL_ARRAY = "symbol_array"
    PAIR = "pair"
    RANGE = "range"

    # ── Lambda / blocks ──────────────────────────────────────────────
    LAMBDA = "lambda"
    LAMBDA_PARAMETERS = "lambda_parameters"
    BLOCK = "block"
    DO_BLOCK = "do_block"
    BLOCK_PARAMETERS = "block_parameters"
    BLOCK_BODY = "block_body"

    # ── Pattern matching ─────────────────────────────────────────────
    PATTERN = "pattern"
    IN = "in"

    # ── Statements ───────────────────────────────────────────────────
    EXPRESSION_STATEMENT = "expression_statement"
    ASSIGNMENT = "assignment"
    OPERATOR_ASSIGNMENT = "operator_assignment"
    RETURN = "return"
    RETURN_STATEMENT = "return_statement"
    BREAK = "break"
    NEXT = "next"
    RETRY = "retry"
    SUPER = "super"
    YIELD = "yield"

    # ── Control flow ─────────────────────────────────────────────────
    IF = "if"
    IF_MODIFIER = "if_modifier"
    ELSIF = "elsif"
    ELSE = "else"
    ELSE_CLAUSE = "else_clause"
    UNLESS = "unless"
    UNLESS_MODIFIER = "unless_modifier"
    WHILE = "while"
    WHILE_MODIFIER = "while_modifier"
    UNTIL = "until"
    UNTIL_MODIFIER = "until_modifier"
    FOR = "for"
    CASE = "case"
    WHEN = "when"
    BEGIN = "begin"

    # ── Exception handling ───────────────────────────────────────────
    RESCUE = "rescue"
    EXCEPTIONS = "exceptions"
    EXCEPTION_VARIABLE = "exception_variable"
    ENSURE = "ensure"

    # ── Definitions ──────────────────────────────────────────────────
    METHOD = "method"
    SINGLETON_METHOD = "singleton_method"
    CLASS = "class"
    SUPERCLASS = "superclass"
    SINGLETON_CLASS = "singleton_class"
    MODULE = "module"

    # ── Structural ───────────────────────────────────────────────────
    PROGRAM = "program"
    BODY_STATEMENT = "body_statement"
    COMMENT = "comment"

    # ── Keyword tokens ───────────────────────────────────────────────
    THEN = "then"
    DO = "do"
    END = "end"
    ARROW = "->"

    # ── Punctuation tokens ───────────────────────────────────────────
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    OPEN_BRACKET = "["
    CLOSE_BRACKET = "]"
    OPEN_BRACE = "{"
    CLOSE_BRACE = "}"
    COMMA = ","
    COLON = ":"
    PIPE = "|"
    NEWLINE_CHAR = "\n"
