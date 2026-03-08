"""Named constants — eliminates magic strings across the codebase."""

from __future__ import annotations

from enum import StrEnum


class Language(StrEnum):
    """Bounded set of supported source languages.

    Each member's value is the tree-sitter language name string, so
    ``Language.PYTHON == "python"`` is ``True`` and members pass through
    directly to ``tree_sitter_language_pack.get_parser()``.
    """

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    RUBY = "ruby"
    GO = "go"
    PHP = "php"
    CSHARP = "csharp"
    C = "c"
    CPP = "cpp"
    RUST = "rust"
    KOTLIN = "kotlin"
    SCALA = "scala"
    LUA = "lua"
    PASCAL = "pascal"
    COBOL = "cobol"


PARAM_PREFIX = "param:"

FUNC_REF_PATTERN = r"<function:(\w+)@(\w+)(?:#(\w+))?>"
CLASS_REF_PATTERN = r"<class:(\w+)@(\w+)(?::([^>]+))?>"

FUNC_REF_TEMPLATE = "<function:{name}@{label}>"
CLASS_REF_TEMPLATE = "<class:{name}@{label}>"
CLASS_REF_WITH_PARENTS_TEMPLATE = "<class:{name}@{label}:{parents}>"

OBJ_ADDR_PREFIX = "obj_"
REGION_ADDR_PREFIX = "rgn_"
ARR_ADDR_PREFIX = "arr_"
ENV_ID_PREFIX = "env_"

FUNC_LABEL_PREFIX = "func_"
CLASS_LABEL_PREFIX = "class_"
END_CLASS_LABEL_PREFIX = "end_class_"

MAIN_FRAME_NAME = "<main>"
CFG_ENTRY_LABEL = "entry"

CAUGHT_EXCEPTION_PREFIX = "caught_exception"

DATAFLOW_MAX_ITERATIONS = 1000

MERMAID_MAX_NODE_LINES = 6

FRONTEND_DETERMINISTIC = "deterministic"
FRONTEND_LLM = "llm"
FRONTEND_CHUNKED_LLM = "chunked_llm"
FRONTEND_COBOL = "cobol"

SUPPORTED_DETERMINISTIC_LANGUAGES: tuple[str, ...] = tuple(
    lang.value for lang in Language if lang != Language.COBOL
)


class LLMProvider(StrEnum):
    """Supported LLM provider identifiers."""

    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"


class CanonicalLiteral:
    """Canonical string representations of Python literal values in IR."""

    NONE = "None"
    TRUE = "True"
    FALSE = "False"


DEFAULT_EXCEPTION_TYPE = "Exception"


PARAM_SELF = "self"
PARAM_THIS = "this"
PARAM_PHP_THIS = "$this"
SELF_PARAM_NAMES: frozenset[str] = frozenset({PARAM_SELF, PARAM_THIS, PARAM_PHP_THIS})


class Variance(StrEnum):
    """Variance annotation for parameterized type arguments."""

    COVARIANT = "covariant"
    CONTRAVARIANT = "contravariant"
    INVARIANT = "invariant"


class TypeName(StrEnum):
    """Canonical type names for the type ontology DAG."""

    ANY = "Any"
    NUMBER = "Number"
    INT = "Int"
    FLOAT = "Float"
    STRING = "String"
    BOOL = "Bool"
    OBJECT = "Object"
    ARRAY = "Array"
    POINTER = "Pointer"
    MAP = "Map"
    TUPLE = "Tuple"
    REGION = "Region"
