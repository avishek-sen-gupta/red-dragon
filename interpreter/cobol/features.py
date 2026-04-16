# pyright: standard
"""Semantic feature enumeration for the COBOL language frontend."""

from __future__ import annotations

from enum import Enum, auto


class CobolFeature(Enum):
    """Semantic features of the COBOL language."""

    # ---------------------------------------------------------------------------
    # Arithmetic verbs
    # ---------------------------------------------------------------------------
    ADD = auto()
    SUBTRACT = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    COMPUTE = auto()
    GIVING_CLAUSE = auto()  # GIVING target in arithmetic statements
    ROUNDED_CLAUSE = auto()  # ROUNDED modifier on arithmetic results
    ON_SIZE_ERROR = auto()  # SIZE ERROR / NOT SIZE ERROR handlers

    # ---------------------------------------------------------------------------
    # Control flow
    # ---------------------------------------------------------------------------
    IF_ELSE = auto()
    EVALUATE = auto()
    EVALUATE_WHEN_OTHER = auto()
    PERFORM = auto()
    PERFORM_TIMES = auto()
    PERFORM_UNTIL = auto()
    PERFORM_VARYING = auto()
    PERFORM_TEST_BEFORE = auto()
    PERFORM_TEST_AFTER = auto()
    PERFORM_THRU = auto()
    PERFORM_INLINE = auto()
    GO_TO = auto()
    ALTER = auto()
    STOP_RUN = auto()
    CONTINUE = auto()
    EXIT = auto()

    # ---------------------------------------------------------------------------
    # Data manipulation
    # ---------------------------------------------------------------------------
    MOVE = auto()
    INITIALIZE = auto()
    SET_TO = auto()
    SET_UP_BY = auto()
    SET_DOWN_BY = auto()
    DISPLAY = auto()

    # ---------------------------------------------------------------------------
    # String operations
    # ---------------------------------------------------------------------------
    STRING_VERB = auto()  # STRING ... INTO
    STRING_DELIMITED_BY = auto()
    UNSTRING_VERB = auto()  # UNSTRING ... INTO
    UNSTRING_DELIMITED_BY = auto()
    INSPECT_TALLYING = auto()
    INSPECT_REPLACING = auto()
    INSPECT_CONVERTING = auto()

    # ---------------------------------------------------------------------------
    # Table operations
    # ---------------------------------------------------------------------------
    SEARCH_LINEAR = auto()  # SEARCH statement
    SEARCH_BINARY = auto()  # SEARCH ALL statement
    SEARCH_WHEN_CONDITIONS = auto()
    SEARCH_AT_END = auto()
    SEARCH_VARYING = auto()

    # ---------------------------------------------------------------------------
    # Inter-program communication
    # ---------------------------------------------------------------------------
    CALL = auto()
    CALL_USING = auto()
    CALL_GIVING = auto()
    USING_BY_REFERENCE = auto()
    USING_BY_CONTENT = auto()
    USING_BY_VALUE = auto()
    CANCEL = auto()
    ENTRY = auto()

    # ---------------------------------------------------------------------------
    # I/O statements
    # ---------------------------------------------------------------------------
    ACCEPT = auto()
    OPEN = auto()
    CLOSE = auto()
    READ = auto()
    READ_INTO = auto()
    READ_AT_END = auto()
    WRITE = auto()
    WRITE_FROM = auto()
    REWRITE = auto()
    START = auto()
    DELETE_RECORD = auto()

    # ---------------------------------------------------------------------------
    # Data Division — PIC clause and types
    # ---------------------------------------------------------------------------
    PIC_CLAUSE = auto()
    VALUE_CLAUSE = auto()
    VALUE_THRU_RANGE = auto()  # VALUE x THRU y
    REDEFINES_CLAUSE = auto()
    OCCURS_FIXED = auto()
    OCCURS_DEPENDING_ON = auto()
    FILLER_FIELD = auto()
    SIGN_CLAUSE = auto()
    JUSTIFIED_CLAUSE = auto()
    SYNCHRONIZED_CLAUSE = auto()
    BLANK_WHEN_ZERO = auto()
    RENAMES_CLAUSE = auto()  # Level-66 RENAMES

    # ---------------------------------------------------------------------------
    # Data Division — USAGE types
    # ---------------------------------------------------------------------------
    USAGE_DISPLAY = auto()
    USAGE_COMP = auto()  # COMP / COMP-4 / COMP-5 (binary)
    USAGE_COMP_3 = auto()  # Packed decimal
    USAGE_COMP_1 = auto()  # Single-precision float
    USAGE_COMP_2 = auto()  # Double-precision float
    USAGE_INDEX = auto()

    # ---------------------------------------------------------------------------
    # Data Division — structure
    # ---------------------------------------------------------------------------
    GROUP_ITEM = auto()  # Level 01–49 group records
    LEVEL_88_CONDITION = auto()  # Condition names
    CONDITION_VALUES_THRU = auto()  # 88-level THRU ranges
    SECTION_WORKING_STORAGE = auto()
    SECTION_LOCAL_STORAGE = auto()
    SECTION_LINKAGE = auto()
    SECTION_FILE = auto()

    # ---------------------------------------------------------------------------
    # Figurative constants
    # ---------------------------------------------------------------------------
    FIGURATIVE_SPACES = auto()
    FIGURATIVE_ZEROS = auto()
    FIGURATIVE_HIGH_VALUES = auto()
    FIGURATIVE_LOW_VALUES = auto()
    FIGURATIVE_QUOTES = auto()

    # ---------------------------------------------------------------------------
    # Expressions and conditions
    # ---------------------------------------------------------------------------
    ARITHMETIC_EXPRESSION = auto()
    COMPARISON_OPERATORS = auto()
    LOGICAL_AND = auto()
    LOGICAL_OR = auto()
    LOGICAL_NOT = auto()
    PARENTHESIZED_EXPRESSION = auto()
    SUBSCRIPT_ACCESS = auto()  # TABLE-FIELD(INDEX)
    REFERENCE_MODIFICATION = auto()  # FIELD(start:length)

    # ---------------------------------------------------------------------------
    # Infrastructure / runtime
    # ---------------------------------------------------------------------------
    PROLEAP_BRIDGE = auto()  # ProLEAP AST parsing bridge
    IO_PROVIDER = auto()  # Pluggable I/O abstraction
    MULTI_FILE_IMPORTS = auto()  # COPY / multi-compilation-unit linking
    DATA_LAYOUT_ENGINE = auto()  # Memory layout for data divisions
    NUMERIC_EXECUTION = auto()  # Decimal arithmetic runtime
    FRONTEND_IDEMPOTENCY = auto()  # Re-entrant lowering
    BARE_STATEMENTS = auto()  # Statements without enclosing program structure
