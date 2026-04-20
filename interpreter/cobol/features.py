# pyright: standard
"""Semantic feature enumeration for the COBOL language frontend."""

from __future__ import annotations

from enum import Enum


class CobolFeature(Enum):
    """Semantic features of the COBOL language."""

    # ---------------------------------------------------------------------------
    # Arithmetic verbs
    # ---------------------------------------------------------------------------
    ADD = "ADD a TO b arithmetic addition verb"
    SUBTRACT = "SUBTRACT a FROM b arithmetic subtraction verb"
    MULTIPLY = "MULTIPLY a BY b arithmetic multiplication verb"
    DIVIDE = "DIVIDE a INTO b arithmetic division verb"
    COMPUTE = "COMPUTE x = expr arithmetic expression assignment verb"
    GIVING_CLAUSE = "GIVING target clause in arithmetic statements"
    ROUNDED_CLAUSE = "ROUNDED modifier on arithmetic result fields"
    ON_SIZE_ERROR = "ON SIZE ERROR / NOT ON SIZE ERROR overflow handlers"
    ARITHMETIC_REF_MOD = "ADD/SUBTRACT/MULTIPLY/DIVIDE WS-FIELD(start:length) reference modification on source operands"

    # ---------------------------------------------------------------------------
    # Control flow
    # ---------------------------------------------------------------------------
    IF_ELSE = "IF cond ... ELSE ... END-IF conditional statements"
    EVALUATE = "EVALUATE expr WHEN val ... END-EVALUATE multi-branch statements"
    EVALUATE_WHEN_OTHER = "WHEN OTHER default clause in EVALUATE statements"
    PERFORM = "PERFORM paragraph procedure invocation"
    PERFORM_TIMES = "PERFORM n TIMES loop statements"
    PERFORM_UNTIL = "PERFORM UNTIL cond loop statements"
    PERFORM_VARYING = "PERFORM VARYING x FROM ... BY ... UNTIL ... loop statements"
    PERFORM_TEST_BEFORE = "PERFORM WITH TEST BEFORE pre-condition loop variant"
    PERFORM_TEST_AFTER = "PERFORM WITH TEST AFTER post-condition loop variant"
    PERFORM_THRU = "PERFORM para THRU para2 paragraph range execution"
    PERFORM_INLINE = "PERFORM ... END-PERFORM inline procedure body"
    GO_TO = "GO TO paragraph unconditional control transfer"
    ALTER = "ALTER paragraph TO PROCEED TO other paragraph redirection"
    STOP_RUN = "STOP RUN program termination"
    CONTINUE = "CONTINUE no-operation placeholder statement"
    EXIT = "EXIT and EXIT PROGRAM section/program exit statements"

    # ---------------------------------------------------------------------------
    # Data manipulation
    # ---------------------------------------------------------------------------
    MOVE = "MOVE src TO dest data transfer statements"
    MOVE_CORRESPONDING = (
        "MOVE CORRESPONDING source TO target group item matching transfer"
    )
    INITIALIZE = "INITIALIZE field data initialization statements"
    SET_TO = "SET index TO value index setting statements"
    SET_UP_BY = "SET index UP BY n index increment statements"
    SET_DOWN_BY = "SET index DOWN BY n index decrement statements"
    DISPLAY = "DISPLAY expr output display statements"
    DISPLAY_REF_MOD = "DISPLAY WS-FIELD(start:length) reference modification on operand"

    # ---------------------------------------------------------------------------
    # String operations
    # ---------------------------------------------------------------------------
    STRING_VERB = "STRING ... INTO dest string concatenation verb"
    STRING_DELIMITED_BY = "DELIMITED BY clause in STRING statements"
    STRING_REF_MOD = "STRING ... (start:length) reference modification on sending items"
    UNSTRING_VERB = "UNSTRING src INTO dest string splitting verb"
    UNSTRING_DELIMITED_BY = "DELIMITED BY clause in UNSTRING statements"
    UNSTRING_REF_MOD = "UNSTRING ... (start:length) reference modification on source"
    INSPECT_REF_MOD = "INSPECT x(start:length) reference modification on subject"
    INSPECT_TALLYING = "INSPECT x TALLYING count FOR pattern character inspection"
    INSPECT_REPLACING = (
        "INSPECT x REPLACING pattern BY replacement character replacement"
    )
    INSPECT_CONVERTING = "INSPECT x CONVERTING from TO to character conversion"

    # ---------------------------------------------------------------------------
    # Table operations
    # ---------------------------------------------------------------------------
    SEARCH_LINEAR = "SEARCH table WHEN cond linear table search statements"
    SEARCH_BINARY = "SEARCH ALL table WHEN cond binary table search statements"
    SEARCH_WHEN_CONDITIONS = "WHEN condition clauses in SEARCH statements"
    SEARCH_AT_END = "AT END clause in SEARCH statements"
    SEARCH_VARYING = "VARYING index clause in SEARCH statements"

    # ---------------------------------------------------------------------------
    # Inter-program communication
    # ---------------------------------------------------------------------------
    CALL = "CALL 'program' subprogram call statements"
    CALL_USING = "CALL 'program' USING args parameter passing in CALL"
    CALL_GIVING = "CALL 'program' GIVING result return value capture in CALL"
    USING_BY_REFERENCE = "USING BY REFERENCE pass-by-reference parameter mode"
    USING_BY_CONTENT = "USING BY CONTENT pass-by-copy parameter mode"
    USING_BY_VALUE = "USING BY VALUE pass-by-value parameter mode"
    CANCEL = "CANCEL 'program' program cancellation statements"
    ENTRY = "ENTRY 'name' USING alternate entry point declarations"

    # ---------------------------------------------------------------------------
    # I/O statements
    # ---------------------------------------------------------------------------
    ACCEPT = "ACCEPT field FROM source user input and environment accept statements"
    OPEN = "OPEN INPUT/OUTPUT/I-O/EXTEND file file opening statements"
    CLOSE = "CLOSE file file closing statements"
    READ = "READ file INTO dest file record read statements"
    READ_INTO = "INTO dest clause on READ statements"
    READ_AT_END = "AT END clause on READ statements"
    WRITE = "WRITE record file record write statements"
    WRITE_FROM = "FROM src clause on WRITE statements"
    REWRITE = "REWRITE record file record update statements"
    START = "START file KEY relop field file positioning statements"
    DELETE_RECORD = "DELETE file RECORD file record deletion statements"

    # ---------------------------------------------------------------------------
    # Data Division — PIC clause and types
    # ---------------------------------------------------------------------------
    PIC_CLAUSE = "PIC/PICTURE clause defining field format and size"
    VALUE_CLAUSE = "VALUE literal initial value clause on data items"
    VALUE_THRU_RANGE = "VALUE x THRU y range initial value clause"
    REDEFINES_CLAUSE = "REDEFINES other-field overlay type reuse"
    OCCURS_FIXED = "OCCURS n TIMES fixed-size table declarations"
    OCCURS_DEPENDING_ON = (
        "OCCURS ... DEPENDING ON field variable-length table declarations"
    )
    FILLER_FIELD = "FILLER anonymous padding field declarations"
    SIGN_CLAUSE = "SIGN IS LEADING/TRAILING sign position clause"
    JUSTIFIED_CLAUSE = "JUSTIFIED RIGHT right-justification clause"
    SYNCHRONIZED_CLAUSE = "SYNCHRONIZED LEFT/RIGHT memory alignment clause"
    BLANK_WHEN_ZERO = "BLANK WHEN ZERO display blank instead of zero clause"
    RENAMES_CLAUSE = "Level-66 RENAMES field THRU field alias declarations"

    # ---------------------------------------------------------------------------
    # Data Division — USAGE types
    # ---------------------------------------------------------------------------
    USAGE_DISPLAY = "USAGE DISPLAY character-mode storage type"
    USAGE_COMP = "USAGE COMP / COMP-4 / COMP-5 binary integer storage type"
    USAGE_COMP_3 = "USAGE COMP-3 packed decimal storage type"
    USAGE_COMP_1 = "USAGE COMP-1 single-precision floating-point storage type"
    USAGE_COMP_2 = "USAGE COMP-2 double-precision floating-point storage type"
    USAGE_INDEX = "USAGE INDEX table index storage type"

    # ---------------------------------------------------------------------------
    # Data Division — structure
    # ---------------------------------------------------------------------------
    GROUP_ITEM = "Level 01–49 group record items containing subordinate fields"
    LEVEL_88_CONDITION = "Level-88 condition name declarations"
    CONDITION_VALUES_THRU = "88-level VALUE x THRU y range condition name clauses"
    SECTION_WORKING_STORAGE = "WORKING-STORAGE SECTION persistent data declarations"
    SECTION_LOCAL_STORAGE = "LOCAL-STORAGE SECTION per-call local data declarations"
    SECTION_LINKAGE = "LINKAGE SECTION parameter and return data declarations"
    SECTION_FILE = "FILE SECTION file record layout declarations"

    # ---------------------------------------------------------------------------
    # Figurative constants
    # ---------------------------------------------------------------------------
    FIGURATIVE_SPACES = "SPACES figurative constant for blank characters"
    FIGURATIVE_ZEROS = "ZEROS / ZEROES figurative constant for numeric zero"
    FIGURATIVE_HIGH_VALUES = "HIGH-VALUES figurative constant for maximum binary value"
    FIGURATIVE_LOW_VALUES = "LOW-VALUES figurative constant for minimum binary value"
    FIGURATIVE_QUOTES = "QUOTES figurative constant for quotation characters"

    # ---------------------------------------------------------------------------
    # Expressions and conditions
    # ---------------------------------------------------------------------------
    ARITHMETIC_EXPRESSION = "arithmetic expressions in COMPUTE and conditions"
    COMPARISON_OPERATORS = "=, >, <, >=, <=, <> relational comparison operators"
    LOGICAL_AND = "AND logical conjunction in conditions"
    LOGICAL_OR = "OR logical disjunction in conditions"
    LOGICAL_NOT = "NOT logical negation in conditions"
    PARENTHESIZED_EXPRESSION = "(expr) parenthesized condition and arithmetic grouping"
    SUBSCRIPT_ACCESS = "TABLE-FIELD(INDEX) subscript table element access"
    REFERENCE_MODIFICATION = (
        "FIELD(start:length) reference modification substring access"
    )

    # ---------------------------------------------------------------------------
    # Infrastructure / runtime
    # ---------------------------------------------------------------------------
    PROLEAP_BRIDGE = "ProLEAP AST parsing bridge for COBOL source files"
    IO_PROVIDER = "pluggable I/O abstraction for ACCEPT and DISPLAY"
    MULTI_FILE_IMPORTS = "COPY book and multi-compilation-unit linking"
    DATA_LAYOUT_ENGINE = "memory layout engine for Data Division declarations"
    NUMERIC_EXECUTION = "decimal arithmetic runtime for COBOL numeric types"
    FRONTEND_IDEMPOTENCY = "re-entrant lowering producing the same IR on repeated calls"
    BARE_STATEMENTS = "statements without an enclosing PROGRAM-ID structure"
