# pyright: standard
"""Semantic feature enumeration for the C++ language frontend.

Each member represents a distinct language-level feature that the C++
frontend can lower to IR.  Use these with the @covers decorator in test
methods to document which feature each test exercises.
"""

from __future__ import annotations

from enum import Enum


class CppFeature(Enum):
    """Semantic features of the C++ language."""

    # Basic declarations
    VARIABLE_DECLARATION = "local and global variable declarations with initializers"
    DECLARATION_WITHOUT_INITIALIZER = "declarations without an initializer expression"

    # Functions
    FUNCTION_DEFINITION = "function definitions with body"
    FUNCTION_CALL = "f(...) function call expressions"
    RETURN_STATEMENT = "return and return expr statements"

    # Control flow
    IF_ELSE = "if / else if / else conditional branching"
    IF_INIT = "C++17: if (init; cond) with initializer"
    WHILE_LOOP = "while (cond) loops"
    FOR_LOOP = "for (init; cond; update) loops"
    DO_WHILE = "do { } while (cond) loops"
    BREAK_CONTINUE = "break and continue statements"
    SWITCH = "switch / case / default statements"
    DEFAULT_CASE = "default: case label in switch statements"
    LABELED_STATEMENTS = "label: statement labels for goto targets"
    GOTO = "goto label unconditional jumps"
    IF_ELSEIF_CHAIN = "chained if / else if conditional branches"

    # Classes and objects
    CLASS_DEFINITION = "class declarations with members"
    CLASS_WITH_METHODS = "class declarations that include method definitions"
    CLASS_WITH_CONSTRUCTOR = "class declarations with explicit constructors"
    CLASS_WITH_FIELD_INITIALIZERS = "constructors using member initializer lists"
    FIELD_INITIALIZER_LIST = "constructor member initializer lists with multiple fields"
    FIELD_INITIALIZER_SINGLE = "constructor member initializer list with one field"
    INHERITANCE = "class B : public A inheritance declarations"
    STRUCT_DEFINITION = "struct declarations (equivalent to class with public default)"

    # Namespaces
    NAMESPACE = "namespace declarations and using directives"

    # Expressions
    NEW_EXPRESSION = "new T(...) heap allocation expressions"
    DELETE_EXPRESSION = "delete ptr heap deallocation"
    DELETE_ARRAY = "delete[] ptr array deallocation"
    LAMBDA_EXPRESSION = "[...](params) -> T { } lambda expressions"
    LAMBDA_CAPTURE = "capture lists [=], [&], [x] in lambdas"
    BINARY_EXPRESSION = "binary operator expressions"
    UNARY_OPERATORS = "unary +, -, ~, ! operators"
    INCREMENT_DECREMENT = "x++, x--, ++x, --x operators"
    TERNARY_OPERATOR = "cond ? a : b ternary expressions"
    COMMA_OPERATOR = "a, b sequential evaluation comma operator"
    ARITHMETIC = "+, -, *, /, % arithmetic expressions"
    LOGICAL_OPERATORS = "&& and || logical short-circuit operators"

    # Field/pointer access
    FIELD_ACCESS = "obj.field dot access"
    ARROW_OPERATOR = "ptr->field pointer member access"
    ADDRESS_OF = "&expr address-of operator"
    POINTER_DEREFERENCE = "*ptr dereference operator"
    POINTER_LOAD = "loading a value through a pointer"
    POINTER_STORE = "storing a value through a pointer"

    # Templates
    TEMPLATE_DECLARATION = "template<typename T> declarations"
    TEMPLATE_FUNCTION = "template function definitions and instantiations"

    # Type casts
    STATIC_CAST = "static_cast<T>(expr) safe compile-time cast"
    DYNAMIC_CAST = "dynamic_cast<T>(expr) runtime polymorphic cast"
    REINTERPRET_CAST = "reinterpret_cast<T>(expr) bit-level reinterpretation"
    CONST_CAST = "const_cast<T>(expr) const qualifier removal"
    CAST = "(T)expr C-style casts inherited from C"

    # Literals and constants
    EMPTY_PROGRAM = "minimal program with no statements (smoke test)"
    UNSUPPORTED_FALLBACK = "fallback path for unsupported syntax nodes"
    STRING_LITERAL = '"..." string literals'
    CHAR_LITERAL = "'c' character literals"
    NUMBER_LITERAL = "integer and floating-point numeric literals"
    RAW_STRING_LITERAL = 'R"(...)" raw string literals'
    USER_DEFINED_LITERAL = '42_km operator"" user-defined literals'
    NULLPTR = "nullptr null pointer constant"

    # Method calls
    METHOD_CALL = "obj.method(...) instance method calls"
    STATIC_METHOD_CALL = "Class::method(...) static method calls"

    # Enums
    C_STYLE_ENUM = "unscoped C-style enum declarations"
    ENUM_CLASS = "scoped enum class declarations"
    ENUM_CLASS_WITH_VALUES = "scoped enum class with explicit enumerator values"

    # Exception handling
    TRY_CATCH = "try / catch exception handling blocks"
    THROW_STATEMENT = "throw expr; exception throwing statements"
    THROW_EXPRESSION = "throw expr used as an expression"

    # Range-based for
    RANGE_FOR = "for (auto x : collection) range-based for loops"
    STRUCTURED_BINDING = "auto [a, b] = pair; C++17 structured bindings"

    # Concepts
    CONCEPT_DEFINITION = "concept Name = constraint; C++20 concept definitions"

    # Dereferencing and this
    DEREFERENCE_THIS = "*this dereference of the current object"
    DEREFERENCE_POINTER = "(*ptr) explicit pointer dereference in expressions"
    THIS_POINTER = "this pointer keyword in member functions"

    # Array and container operations
    ARRAY_ACCESS = "a[i] array element access"
    SUBSCRIPT_EXPRESSION = "overloaded operator[] subscript calls"

    # Other features
    ASSIGNMENT = "= and compound assignment operators"
    COMPOUND_LITERAL = "(T){...} C-style compound literal expressions"
    SIZEOF = "sizeof(T) and sizeof expr size queries"
    INITIALIZER_LIST = "{a, b, c} brace-enclosed initializer lists"
    DESIGNATED_INITIALIZER = ".field = val C++20 designated initializers"
    ARRAY_LITERALS = "array declarations with initializer lists"
    FUNCTION_POINTER = "function pointer declarations and calls"
    POINTER_TYPE = "T* pointer type declarations"

    # Infrastructure
    ENTRY_LABEL = "synthetic entry point label at function start"
    EXTERN_C = 'extern "C" linkage specification blocks'
