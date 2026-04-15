"""Ruby language features for @covers decorator annotation."""

from __future__ import annotations

from enum import Enum, auto


class RubyFeature(Enum):
    """Ruby language features covered by tests."""

    # Literals and basic expressions
    INTEGER_LITERAL = auto()
    STRING_LITERAL = auto()
    SYMBOL = auto()
    REGEX = auto()
    ARRAY_LITERAL = auto()
    HASH_LITERAL = auto()
    RANGE = auto()
    LAMBDA = auto()
    STRING_ARRAY = auto()  # %w[...] and %i[...]
    HEREDOC = auto()
    HEREDOC_INTERPOLATION = auto()

    # Variables
    VARIABLE_ASSIGNMENT = auto()
    INSTANCE_VARIABLE = auto()
    GLOBAL_VARIABLE = auto()
    CLASS_VARIABLE = auto()
    AUGMENTED_ASSIGNMENT = auto()

    # Control flow
    IF_ELSIF_ELSE = auto()
    UNLESS = auto()
    WHILE_LOOP = auto()
    UNTIL_LOOP = auto()
    IF_MODIFIER = auto()
    UNLESS_MODIFIER = auto()
    WHILE_MODIFIER = auto()
    UNTIL_MODIFIER = auto()
    CONDITIONAL_TERNARY = auto()
    CASE_WHEN = auto()

    # Methods and functions
    METHOD_DEFINITION = auto()
    METHOD_CALL = auto()
    METHOD_CHAINING = auto()
    RETURN_STATEMENT = auto()
    IMPLICIT_RETURN = auto()
    YIELD = auto()
    SUPER = auto()

    # Classes and modules
    CLASS_DEFINITION = auto()
    CLASS_CONSTRUCTOR = auto()
    MODULE_DEFINITION = auto()
    SINGLETON_CLASS = auto()
    SINGLETON_METHOD = auto()

    # Expressions
    ARITHMETIC = auto()
    UNARY_OPERATOR = auto()
    SELF_KEYWORD = auto()
    SCOPE_RESOLUTION = auto()

    # Block and closure
    BLOCK_DO_END = auto()
    BLOCK_CURLY = auto()
    BLOCK_WITH_PARAMS = auto()

    # Exception handling
    RESCUE_MODIFIER = auto()
    RETRY = auto()

    # String interpolation
    STRING_INTERPOLATION = auto()

    # Patterns (Ruby 3+)
    PATTERN_MATCHING = auto()
    LITERAL_PATTERN = auto()
    WILDCARD_PATTERN = auto()
    CAPTURE_PATTERN = auto()
    OR_PATTERN = auto()
    ARRAY_PATTERN = auto()
    HASH_PATTERN = auto()
    CLASS_PATTERN = auto()
    AS_PATTERN = auto()

    # For loops
    FOR_IN_LOOP = auto()

    # Advanced features
    RANGE_SLICE = auto()
    HASH_WITH_SYMBOL_KEYS = auto()
    DELIMITED_SYMBOL = auto()
    BEGIN_END_BLOCK = auto()
    SPLAT_ARGUMENT = auto()
    HASH_SPLAT_ARGUMENT = auto()
    BLOCK_ARGUMENT = auto()

    # Execution tests
    CLASS_EXECUTION = auto()
    LOGICAL_OPERATOR = auto()
