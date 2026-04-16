"""Java language features for @covers decorator annotation."""

from __future__ import annotations

from enum import Enum


class JavaFeature(Enum):
    """Java language features covered by tests."""

    # Literals
    INTEGER_LITERALS = "int and long integer literals"
    HEX_INTEGER_LITERAL = "0x-prefixed hexadecimal integer literals"
    OCTAL_INTEGER_LITERAL = "0-prefixed octal integer literals"
    BINARY_INTEGER_LITERAL = "0b-prefixed binary integer literals"
    HEX_FLOAT_LITERAL = "0x-prefixed hexadecimal floating-point literals"
    CHARACTER_LITERAL = "single-character literals enclosed in single quotes"
    CLASS_LITERAL = "Foo.class expressions"
    TEXT_BLOCK = "multi-line string literals (Java 15+)"

    # Variables and fields
    LOCAL_VARIABLE = "local variable declarations inside method bodies"
    FIELD_ACCESS = "instance and static field reads via dot notation"
    FIELD_INITIALIZATION = "field declarations with inline initializer expressions"
    CONSTANT_DECLARATION = "static final field declarations"

    # Operators and expressions
    ASSIGNMENT = "simple and compound assignment operators"
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    UNARY = "unary !, ~, +, - and prefix/postfix ++/-- operators"
    TERNARY = "conditional (a ? b : c) expressions"
    INSTANCEOF = "instanceof type-check expression"
    CAST = "explicit type cast expressions"
    PARENTHESIZED_EXPRESSION = "expressions wrapped in parentheses"

    # Collections
    ARRAY_CREATION = "new T[n] and new T[]{...} array creation"
    ARRAY_ACCESS = "array element access via subscript operator"
    ARRAY_LENGTH = ".length field access on array types"

    # Method and function calls
    METHOD_CALL = "instance method invocations"
    FUNCTION_CALL = "static method / free function calls"
    METHOD_REFERENCE = "Foo::bar and obj::method references"

    # Control flow
    IF_ELSE = "if / else if / else branching"
    WHILE_LOOP = "while (cond) { } loops"
    DO_WHILE_LOOP = "do { } while (cond) loops"
    FOR_LOOP = "traditional for (init; cond; update) loops"
    ENHANCED_FOR_LOOP = "for (T x : collection) loops"
    BREAK_CONTINUE = "break and continue statements"
    LABELED_STATEMENT = "labeled statements for targeted break/continue"
    SWITCH_STATEMENT = "traditional switch (expr) { case: } statements"
    SWITCH_EXPRESSION = "switch expressions yielding a value (Java 14+)"
    SWITCH_RULE = "arrow-form case labels in switch expressions"
    YIELD = "yield statement inside switch expressions"
    RETURN = "return statements from methods"

    # Exception handling
    TRY_CATCH = "try / catch exception handling blocks"
    TRY_WITH_RESOURCES = "try-with-resources automatic resource management"
    THROW = "throw statement to raise exceptions"
    FINALLY = "finally block in try/catch/finally"

    # Classes and objects
    CLASS = "class declarations including inner classes"
    CONSTRUCTOR = "constructor declarations"
    COMPACT_CONSTRUCTOR = "compact constructors in records (Java 16+)"
    OBJECT_CREATION = "new Foo() object instantiation expressions"
    METHOD_DECLARATION = "method declarations in classes and interfaces"
    FIELD_DECLARATION = "field declarations in class bodies"

    # Advanced features
    LAMBDA = "lambda expressions (x) -> expr"
    GENERIC_TYPES = "generic type parameters and arguments"
    INTERFACE = "interface declarations"
    ENUM = "enum type declarations"
    ANNOTATION_TYPE = "@interface annotation type declarations"
    ANNOTATIONS = "annotation usages on declarations and expressions"
    MODIFIERS = "access and non-access modifiers (public, static, final, etc.)"
    STATIC_INITIALIZER = "static { } initializer blocks"
    SYNCHRONIZED = "synchronized blocks and method modifiers"
    SUPER = "super keyword for parent class access"
    EXPLICIT_CONSTRUCTOR_INVOCATION = "this(...) and super(...) constructor calls"
    FORMAL_PARAMETERS = "formal parameter lists in method declarations"
    INFERRED_PARAMETERS = "type-inferred parameters in lambda expressions"
    SPREAD_PARAMETER = "varargs T... parameters"

    # Pattern matching (Java 16+)
    RECORD = "record class declarations"
    RECORD_PATTERN = "record deconstruction patterns in instanceof and switch"
    TYPE_PATTERN = "instanceof T t pattern bindings"
    PATTERN_GUARD = "when guards in switch pattern cases (Java 21+)"

    # Scoping and resolution
    SCOPED_IDENTIFIER = "package-qualified and nested type identifiers"
    NAMESPACE_RESOLUTION = "qualified name resolution across packages"

    # Module system (Java 9+)
    MODULE_DECLARATION = "module-info.java module declarations"
    IMPORT_DECLARATION = "import statements"
    PACKAGE_DECLARATION = "package declarations"

    # Statements and assertions
    ASSERT = "assert expression and assert expression : message"
    COMMENT_HANDLING = "comment preservation or annotation in the IR"
