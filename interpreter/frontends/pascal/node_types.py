# pyright: standard
"""Tree-sitter node type strings used in Pascal frontend lowerers.

Centralises raw string literals so that typos are caught at import time
and grep/refactor is trivial.  Note: keyword noise tokens (kBegin, kEnd,
kVar, etc.) remain in pascal_constants.KEYWORD_NOISE.
"""


class PascalNodeType:
    """Tree-sitter node type strings used in Pascal frontend lowerers."""

    # -- Literals & atoms --------------------------------------------------
    IDENTIFIER = "identifier"
    LITERAL_NUMBER = "literalNumber"
    LITERAL_STRING = "literalString"

    # -- Expressions -------------------------------------------------------
    EXPR_BINARY = "exprBinary"
    EXPR_CALL = "exprCall"
    EXPR_PARENS = "exprParens"
    EXPR_DOT = "exprDot"
    EXPR_SUBSCRIPT = "exprSubscript"
    EXPR_UNARY = "exprUnary"
    EXPR_BRACKETS = "exprBrackets"
    EXPR_ARGS = "exprArgs"

    # -- Boolean / nil literals --------------------------------------------
    K_TRUE = "kTrue"
    K_FALSE = "kFalse"
    K_NIL = "kNil"

    # -- Statements --------------------------------------------------------
    ROOT = "root"
    PROGRAM = "program"
    BLOCK = "block"
    BLOCK_TR = "blockTr"
    STATEMENT = "statement"
    STATEMENTS = "statements"
    ASSIGNMENT = "assignment"
    DECL_VARS = "declVars"
    DECL_VAR = "declVar"
    IF_ELSE = "ifElse"
    IF = "if"
    WHILE = "while"
    FOR = "for"
    DEF_PROC = "defProc"
    DECL_PROC = "declProc"
    CASE = "case"
    REPEAT = "repeat"
    DECL_CONSTS = "declConsts"
    DECL_CONST = "declConst"
    DECL_TYPE = "declType"
    DECL_TYPES = "declTypes"
    DECL_USES = "declUses"
    TRY = "try"
    EXCEPTION_HANDLER = "exceptionHandler"
    RAISE = "raise"
    WITH = "with"
    INHERITED = "inherited"
    FOREACH = "foreach"
    GOTO = "goto"
    LABEL = "label"
    DECL_LABELS = "declLabels"

    # -- Declaration sub-nodes ---------------------------------------------
    DECL_ARGS = "declArgs"
    DECL_ARG = "declArg"
    DECL_ARRAY = "declArray"
    DECL_CLASS = "declClass"
    DECL_ENUM = "declEnum"
    DECL_ENUM_VALUE = "declEnumValue"
    DEFAULT_VALUE = "defaultValue"
    MODULE_NAME = "moduleName"
    CASE_CASE = "caseCase"
    CASE_LABEL = "caseLabel"

    # -- Type nodes --------------------------------------------------------
    TYPE = "type"
    TYPEREF = "typeref"
    RANGE = "range"

    # -- Keywords used as node type checks (not in KEYWORD_NOISE) ----------
    K_RECORD = "kRecord"
    K_DOWNTO = "kDownto"
    K_FUNCTION = "kFunction"
    K_EXCEPT = "kExcept"
    K_FINALLY = "kFinally"
    K_TRY = "kTry"
    K_END = "kEnd"
    K_ELSE = "kElse"
    K_CLASS = "kClass"

    # -- Property declaration nodes ----------------------------------------
    DECL_PROP = "declProp"
    K_PROPERTY = "kProperty"
    K_READ = "kRead"
    K_WRITE = "kWrite"
    DECL_SECTION = "declSection"
    K_PRIVATE = "kPrivate"
    K_PUBLIC = "kPublic"
    K_PROTECTED = "kProtected"
    DECL_FIELD = "declField"
    GENERIC_DOT = "genericDot"

    # -- Comment -----------------------------------------------------------
    COMMENT = "comment"

    # -- Punctuation tokens ------------------------------------------------
    OPEN_PAREN = "("
    CLOSE_PAREN = ")"
    SEMICOLON = ";"
