"""CSharpFrontend — tree-sitter C# AST -> IR lowering."""

from __future__ import annotations

import logging
from typing import Callable

from ._base import BaseFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class CSharpFrontend(BaseFrontend):
    """Lowers a C# tree-sitter AST into flattened TAC IR."""

    NONE_LITERAL = "null"
    TRUE_LITERAL = "true"
    FALSE_LITERAL = "false"
    DEFAULT_RETURN_VALUE = "null"

    ATTRIBUTE_NODE_TYPE = "member_access_expression"
    ATTR_OBJECT_FIELD = "expression"
    ATTR_ATTRIBUTE_FIELD = "name"

    COMMENT_TYPES = frozenset({"comment"})
    NOISE_TYPES = frozenset({"\n", "using_directive"})

    BLOCK_NODE_TYPES = frozenset({"block"})

    def __init__(self):
        super().__init__()
        self._EXPR_DISPATCH: dict[str, Callable] = {
            "identifier": self._lower_identifier,
            "integer_literal": self._lower_const_literal,
            "real_literal": self._lower_const_literal,
            "string_literal": self._lower_const_literal,
            "character_literal": self._lower_const_literal,
            "boolean_literal": self._lower_const_literal,
            "null_literal": self._lower_const_literal,
            "this_expression": self._lower_identifier,
            "binary_expression": self._lower_binop,
            "prefix_unary_expression": self._lower_unop,
            "postfix_unary_expression": self._lower_update_expr,
            "parenthesized_expression": self._lower_paren,
            "invocation_expression": self._lower_invocation,
            "object_creation_expression": self._lower_object_creation,
            "member_access_expression": self._lower_member_access,
            "element_access_expression": self._lower_element_access,
            "assignment_expression": self._lower_assignment_expr,
            "cast_expression": self._lower_cast_expr,
            "conditional_expression": self._lower_ternary,
            "interpolated_string_expression": self._lower_const_literal,
            "type_identifier": self._lower_identifier,
            "predefined_type": self._lower_identifier,
            "typeof_expression": self._lower_typeof,
            "is_expression": self._lower_is_expr,
            "as_expression": self._lower_as_expr,
            "lambda_expression": self._lower_lambda,
            "array_creation_expression": self._lower_array_creation,
            "implicit_array_creation_expression": self._lower_array_creation,
        }
        self._STMT_DISPATCH: dict[str, Callable] = {
            "expression_statement": self._lower_expression_statement,
            "local_declaration_statement": self._lower_local_decl_stmt,
            "return_statement": self._lower_return,
            "if_statement": self._lower_if,
            "while_statement": self._lower_while,
            "for_statement": self._lower_c_style_for,
            "foreach_statement": self._lower_foreach,
            "method_declaration": self._lower_method_decl,
            "class_declaration": self._lower_class_def,
            "struct_declaration": self._lower_class_def,
            "interface_declaration": self._lower_interface_decl,
            "enum_declaration": self._lower_enum_decl,
            "namespace_declaration": self._lower_namespace,
            "throw_statement": self._lower_throw,
            "block": self._lower_block,
            "global_statement": self._lower_global_statement,
            "compilation_unit": self._lower_block,
            "declaration_list": self._lower_block,
            "using_directive": lambda _: None,
            "do_statement": self._lower_do_while,
            "switch_statement": self._lower_switch,
            "try_statement": self._lower_try,
            "constructor_declaration": self._lower_constructor_decl,
            "field_declaration": self._lower_field_decl,
            "property_declaration": self._lower_property_decl,
            "break_statement": self._lower_break,
            "continue_statement": self._lower_continue,
        }

    # -- C#: global_statement unwrapper --------------------------------

    def _lower_global_statement(self, node):
        """Unwrap global_statement and lower the inner statement."""
        for child in node.children:
            if child.is_named:
                self._lower_stmt(child)

    # -- C#: local declaration statement -------------------------------

    def _lower_local_decl_stmt(self, node):
        """Lower local_declaration_statement -> variable_declaration -> variable_declarator."""
        for child in node.children:
            if child.type == "variable_declaration":
                self._lower_variable_declaration(child)

    def _lower_variable_declaration(self, node):
        """Lower a variable_declaration node with one or more declarators."""
        for child in node.children:
            if child.type == "variable_declarator":
                self._lower_csharp_declarator(child)

    def _lower_csharp_declarator(self, node):
        """Lower a C# variable_declarator.

        The name is the first named child (identifier).
        The initializer value is the named child after the '=' token.
        """
        name_node = None
        value_node = None
        found_equals = False
        for child in node.children:
            if child.type == "identifier" and name_node is None:
                name_node = child
            elif child.type == "=" or self._node_text(child) == "=":
                found_equals = True
            elif found_equals and child.is_named and value_node is None:
                value_node = child

        if name_node is None:
            return

        var_name = self._node_text(name_node)
        if value_node:
            val_reg = self._lower_expr(value_node)
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.NONE_LITERAL],
            )
        self._emit(
            Opcode.STORE_VAR,
            operands=[var_name, val_reg],
            source_location=self._source_loc(node),
        )

    # -- C#: invocation expression -------------------------------------

    def _lower_invocation(self, node) -> str:
        """Lower invocation_expression (function field, arguments field)."""
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []

        if func_node and func_node.type == "member_access_expression":
            obj_node = func_node.child_by_field_name("expression")
            name_node = func_node.child_by_field_name("name")
            if obj_node and name_node:
                obj_reg = self._lower_expr(obj_node)
                method_name = self._node_text(name_node)
                reg = self._fresh_reg()
                self._emit(
                    Opcode.CALL_METHOD,
                    result_reg=reg,
                    operands=[obj_reg, method_name] + arg_regs,
                    source_location=self._source_loc(node),
                )
                return reg

        if func_node and func_node.type == "identifier":
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(
                Opcode.CALL_FUNCTION,
                result_reg=reg,
                operands=[func_name] + arg_regs,
                source_location=self._source_loc(node),
            )
            return reg

        # Dynamic / unknown call target
        if func_node:
            target_reg = self._lower_expr(func_node)
        else:
            target_reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=target_reg,
                operands=["unknown_call_target"],
            )
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_UNKNOWN,
            result_reg=reg,
            operands=[target_reg] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # -- C#: object creation -------------------------------------------

    def _lower_object_creation(self, node) -> str:
        type_node = node.child_by_field_name("type")
        args_node = node.child_by_field_name("arguments")
        arg_regs = self._extract_call_args_unwrap(args_node) if args_node else []
        type_name = self._node_text(type_node) if type_node else "Object"
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=[type_name] + arg_regs,
            source_location=self._source_loc(node),
        )
        return reg

    # -- C#: member access ---------------------------------------------

    def _lower_member_access(self, node) -> str:
        obj_node = node.child_by_field_name("expression")
        name_node = node.child_by_field_name("name")
        if obj_node is None or name_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(name_node)
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[obj_reg, field_name],
            source_location=self._source_loc(node),
        )
        return reg

    # -- C#: element access (indexing) ---------------------------------

    def _lower_element_access(self, node) -> str:
        obj_node = node.child_by_field_name("expression")
        bracket_node = node.child_by_field_name("subscript")
        if obj_node is None:
            return self._lower_const_literal(node)
        obj_reg = self._lower_expr(obj_node)
        if bracket_node:
            idx_reg = self._lower_expr(bracket_node)
        else:
            # Fallback: find the bracketed argument list child
            idx_children = [
                c
                for c in node.children
                if c.is_named and c.type == "bracketed_argument_list"
            ]
            if idx_children:
                inner = [c for c in idx_children[0].children if c.is_named]
                idx_reg = self._lower_expr(inner[0]) if inner else self._fresh_reg()
            else:
                idx_reg = self._fresh_reg()
                self._emit(
                    Opcode.SYMBOLIC,
                    result_reg=idx_reg,
                    operands=["unknown_index"],
                )
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_INDEX,
            result_reg=reg,
            operands=[obj_reg, idx_reg],
            source_location=self._source_loc(node),
        )
        return reg

    # -- C#: assignment expression -------------------------------------

    def _lower_assignment_expr(self, node) -> str:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)
        return val_reg

    # -- C#: cast expression -------------------------------------------

    def _lower_cast_expr(self, node) -> str:
        value_node = node.child_by_field_name("value")
        if value_node:
            return self._lower_expr(value_node)
        children = [c for c in node.children if c.is_named]
        if len(children) >= 2:
            return self._lower_expr(children[-1])
        return self._lower_const_literal(node)

    # -- C#: ternary (conditional_expression) --------------------------

    def _lower_ternary(self, node) -> str:
        cond_node = node.child_by_field_name("condition")
        true_node = node.child_by_field_name("consequence")
        false_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("ternary_true")
        false_label = self._fresh_label("ternary_false")
        end_label = self._fresh_label("ternary_end")

        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{true_label},{false_label}",
        )
        self._emit(Opcode.LABEL, label=true_label)
        true_reg = self._lower_expr(true_node)
        result_var = f"__ternary_{self._label_counter}"
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=false_label)
        false_reg = self._lower_expr(false_node)
        self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg, operands=[result_var])
        return result_reg

    # -- C#: typeof / is / as ------------------------------------------

    def _lower_typeof(self, node) -> str:
        """Lower typeof_expression: typeof(Type).

        Emits: CONST type_name -> CALL_FUNCTION typeof(type_reg)
        """
        named_children = [c for c in node.children if c.is_named]
        type_node = next(
            (c for c in named_children if c.type != "typeof"),
            named_children[0] if named_children else None,
        )
        type_name = self._node_text(type_node) if type_node else "Object"
        type_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["typeof", type_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_is_expr(self, node) -> str:
        """Lower is_expression: operand is Type.

        Emits: lower_expr(operand) -> CONST type_name -> CALL_FUNCTION is_check(obj, type)
        """
        named_children = [c for c in node.children if c.is_named]
        operand_node = named_children[0] if named_children else None
        type_node = named_children[1] if len(named_children) > 1 else None

        obj_reg = self._lower_expr(operand_node) if operand_node else self._fresh_reg()
        type_reg = self._fresh_reg()
        type_name = self._node_text(type_node) if type_node else "Object"
        self._emit(Opcode.CONST, result_reg=type_reg, operands=[type_name])
        reg = self._fresh_reg()
        self._emit(
            Opcode.CALL_FUNCTION,
            result_reg=reg,
            operands=["is_check", obj_reg, type_reg],
            source_location=self._source_loc(node),
        )
        return reg

    def _lower_as_expr(self, node) -> str:
        # 'as' cast -- lower the left operand, treat the cast as passthrough
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[0])
        return self._lower_const_literal(node)

    # -- C#: lambda ----------------------------------------------------

    def _lower_lambda(self, node) -> str:
        """Lower C# lambda: (params) => expr or (params) => { body }."""
        func_label = self._fresh_label("lambda")
        end_label = self._fresh_label("lambda_end")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        # Lower parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            self._lower_csharp_params(params_node)

        # Lower body
        body_node = node.child_by_field_name("body")
        if body_node and body_node.type == "block":
            self._lower_block(body_node)
        elif body_node:
            # Expression body — evaluate and return
            body_reg = self._lower_expr(body_node)
            self._emit(Opcode.RETURN, operands=[body_reg])

        # Implicit return for block bodies (if no explicit return)
        if body_node and body_node.type == "block":
            none_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=none_reg,
                operands=[self.DEFAULT_RETURN_VALUE],
            )
            self._emit(Opcode.RETURN, operands=[none_reg])

        self._emit(Opcode.LABEL, label=end_label)

        ref_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=ref_reg,
            operands=[f"func:{func_label}"],
            source_location=self._source_loc(node),
        )
        return ref_reg

    # -- C#: array creation --------------------------------------------

    def _lower_array_creation(self, node) -> str:
        """Lower array_creation_expression / implicit_array_creation_expression.

        With initializer: NEW_ARRAY + STORE_INDEX per element.
        Without initializer (sized): just NEW_ARRAY with size.
        """
        # Find initializer: initializer_expression for both explicit and implicit
        init_node = node.child_by_field_name("initializer")
        if init_node is None:
            init_node = next(
                (c for c in node.children if c.type == "initializer_expression"),
                None,
            )

        if init_node is not None:
            elements = [c for c in init_node.children if c.is_named]
            size_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elements))])
            arr_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_ARRAY,
                result_reg=arr_reg,
                operands=["array", size_reg],
                source_location=self._source_loc(node),
            )
            for i, elem in enumerate(elements):
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                val_reg = self._lower_expr(elem)
                self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
            return arr_reg

        # Sized array without initializer: new int[5]
        # Extract the size from rank_specifier or bracketed children
        size_children = [
            c
            for c in node.children
            if c.is_named
            and c.type not in ("predefined_type", "type_identifier", "array_type")
        ]
        size_node = size_children[0] if size_children else None
        if size_node and size_node.type not in ("initializer_expression",):
            size_reg = self._lower_expr(size_node)
        else:
            size_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=size_reg, operands=["0"])
        arr_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_ARRAY,
            result_reg=arr_reg,
            operands=["array", size_reg],
            source_location=self._source_loc(node),
        )
        return arr_reg

    # -- C#: foreach ---------------------------------------------------

    def _lower_foreach(self, node):
        """Lower foreach (Type var in collection) { body }."""
        left_node = node.child_by_field_name("left")
        right_node = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(right_node) if right_node else self._fresh_reg()
        var_name = self._node_text(left_node) if left_node else "__foreach_var"

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("foreach_cond")
        body_label = self._fresh_label("foreach_body")
        end_label = self._fresh_label("foreach_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg, operands=["<", idx_reg, len_reg])
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
        )

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[iter_reg, idx_reg])
        self._emit(Opcode.STORE_VAR, operands=[var_name, elem_reg])

        update_label = self._fresh_label("foreach_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__foreach_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- C#: method declaration ----------------------------------------

    def _lower_method_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node) if name_node else "__anon"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_csharp_params(params_node)

        if body_node:
            self._lower_block(body_node)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=none_reg, operands=[self.DEFAULT_RETURN_VALUE]
        )
        self._emit(Opcode.RETURN, operands=[none_reg])
        self._emit(Opcode.LABEL, label=end_label)

        func_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=func_reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[func_name, func_reg])

    def _lower_csharp_params(self, params_node):
        """Lower C# formal parameters (parameter nodes)."""
        for child in params_node.children:
            if child.type == "parameter":
                name_node = child.child_by_field_name("name")
                if name_node:
                    pname = self._node_text(name_node)
                    self._emit(
                        Opcode.SYMBOLIC,
                        result_reg=self._fresh_reg(),
                        operands=[f"{constants.PARAM_PREFIX}{pname}"],
                        source_location=self._source_loc(child),
                    )
                    self._emit(
                        Opcode.STORE_VAR,
                        operands=[pname, f"%{self._reg_counter - 1}"],
                    )

    # -- C#: constructor -----------------------------------------------

    def _lower_constructor_decl(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = "__init__"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(Opcode.BRANCH, label=end_label)
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_csharp_params(params_node)

        if body_node:
            self._lower_block(body_node)

        none_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST, result_reg=none_reg, operands=[self.DEFAULT_RETURN_VALUE]
        )
        self._emit(Opcode.RETURN, operands=[none_reg])
        self._emit(Opcode.LABEL, label=end_label)

        func_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=func_reg,
            operands=[
                constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[func_name, func_reg])

    # -- C#: class / struct / interface / enum -------------------------

    def _lower_class_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node) if name_node else "__anon_class"

        class_label = self._fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
        end_label = self._fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=class_label)
        if body_node:
            self._lower_class_body(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(
            Opcode.CONST,
            result_reg=cls_reg,
            operands=[
                constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)
            ],
        )
        self._emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    def _lower_class_body(self, node):
        """Lower declaration_list (C# class body)."""
        for child in node.children:
            if child.type == "method_declaration":
                self._lower_method_decl(child)
            elif child.type == "constructor_declaration":
                self._lower_constructor_decl(child)
            elif child.type == "field_declaration":
                self._lower_field_decl(child)
            elif child.type == "property_declaration":
                self._lower_property_decl(child)
            elif child.is_named and child.type not in (
                "modifier",
                "attribute_list",
                "{",
                "}",
            ):
                self._lower_stmt(child)

    def _lower_field_decl(self, node):
        """Lower a field declaration inside a class body."""
        for child in node.children:
            if child.type == "variable_declaration":
                self._lower_variable_declaration(child)

    def _lower_property_decl(self, node):
        """Lower a property declaration as STORE_FIELD on this.

        Auto-properties (``get; set;``) emit a backing-field store:
        ``LOAD_VAR this → CONST default → STORE_FIELD this, name, default``.
        If the property has an initializer (``= value``), the initializer
        expression is used instead of the default.  Accessor bodies with
        explicit ``block`` children are lowered as statements.
        """
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        prop_name = self._node_text(name_node)

        this_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])

        # Check for an initializer (e.g. ``= 42``)
        initializer_node = self._find_property_initializer(node)
        if initializer_node:
            val_reg = self._lower_expr(initializer_node)
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.NONE_LITERAL],
                source_location=self._source_loc(node),
            )

        self._emit(
            Opcode.STORE_FIELD,
            operands=[this_reg, prop_name, val_reg],
            source_location=self._source_loc(node),
        )

        # Lower accessor bodies (get { ... } / set { ... }) if present
        accessor_list = next(
            (c for c in node.children if c.type == "accessor_list"), None
        )
        if accessor_list:
            for accessor in (
                c for c in accessor_list.children if c.type == "accessor_declaration"
            ):
                body_block = next(
                    (b for b in accessor.children if b.type == "block"), None
                )
                if body_block:
                    self._lower_block(body_block)

    def _find_property_initializer(self, node):
        """Find the initializer expression after ``=`` in a property_declaration."""
        found_eq = False
        for child in node.children:
            if not child.is_named and self._node_text(child) == "=":
                found_eq = True
                continue
            if found_eq and child.is_named and child.type != "accessor_list":
                return child
        return None

    def _lower_interface_decl(self, node):
        """Lower interface_declaration as NEW_OBJECT with STORE_INDEX per member."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        iface_name = self._node_text(name_node)
        obj_reg = self._fresh_reg()
        self._emit(
            Opcode.NEW_OBJECT,
            result_reg=obj_reg,
            operands=[f"interface:{iface_name}"],
            source_location=self._source_loc(node),
        )
        body_node = node.child_by_field_name("body")
        if body_node:
            for i, child in enumerate(c for c in body_node.children if c.is_named):
                member_name_node = child.child_by_field_name("name")
                member_name = (
                    self._node_text(member_name_node)
                    if member_name_node
                    else self._node_text(child)[:40]
                )
                key_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                val_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
        self._emit(Opcode.STORE_VAR, operands=[iface_name, obj_reg])

    def _lower_enum_decl(self, node):
        """Lower enum_declaration as NEW_OBJECT with STORE_INDEX per member."""
        name_node = node.child_by_field_name("name")
        body_node = next(
            (c for c in node.children if c.type == "enum_member_declaration_list"),
            None,
        )
        if name_node:
            enum_name = self._node_text(name_node)
            obj_reg = self._fresh_reg()
            self._emit(
                Opcode.NEW_OBJECT,
                result_reg=obj_reg,
                operands=[f"enum:{enum_name}"],
                source_location=self._source_loc(node),
            )
            if body_node:
                for i, child in enumerate(
                    c for c in body_node.children if c.type == "enum_member_declaration"
                ):
                    member_name_node = child.child_by_field_name("name")
                    member_name = (
                        self._node_text(member_name_node)
                        if member_name_node
                        else self._node_text(child)
                    )
                    key_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=key_reg, operands=[member_name])
                    val_reg = self._fresh_reg()
                    self._emit(Opcode.CONST, result_reg=val_reg, operands=[str(i)])
                    self._emit(Opcode.STORE_INDEX, operands=[obj_reg, key_reg, val_reg])
            self._emit(Opcode.STORE_VAR, operands=[enum_name, obj_reg])

    # -- C#: namespace -------------------------------------------------

    def _lower_namespace(self, node):
        """Lower namespace as a block -- descend into its body."""
        body_node = node.child_by_field_name("body")
        if body_node:
            self._lower_block(body_node)

    # -- C#: if --------------------------------------------------------

    def _lower_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        # If consequence field is not present, find the first block child
        if body_node is None:
            body_node = next((c for c in node.children if c.type == "block"), None)

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")

        if alt_node:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{false_label}",
                source_location=self._source_loc(node),
            )
        else:
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{true_label},{end_label}",
                source_location=self._source_loc(node),
            )

        self._emit(Opcode.LABEL, label=true_label)
        if body_node:
            self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            for child in alt_node.children:
                if child.type not in ("else",) and child.is_named:
                    self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- C#: throw -----------------------------------------------------

    def _lower_throw(self, node):
        self._lower_raise_or_throw(node, keyword="throw")

    # -- C#: do-while --------------------------------------------------

    def _lower_do_while(self, node):
        body_node = node.child_by_field_name("body")
        cond_node = node.child_by_field_name("condition")

        body_label = self._fresh_label("do_body")
        cond_label = self._fresh_label("do_cond")
        end_label = self._fresh_label("do_end")

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(cond_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=cond_label)
        if cond_node:
            cond_reg = self._lower_expr(cond_node)
            self._emit(
                Opcode.BRANCH_IF,
                operands=[cond_reg],
                label=f"{body_label},{end_label}",
                source_location=self._source_loc(node),
            )
        else:
            self._emit(Opcode.BRANCH, label=body_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- C#: switch (SYMBOLIC) -----------------------------------------

    def _lower_switch(self, node):
        """Lower switch as if/else chain.

        C# tree-sitter: switch_statement has 'value' field (subject) and
        'body' field (switch_body containing switch_section children).
        Each switch_section has constant_pattern for case values (absent for default).
        """
        value_node = node.child_by_field_name("value")
        body_node = node.child_by_field_name("body")

        subject_reg = self._lower_expr(value_node) if value_node else self._fresh_reg()
        end_label = self._fresh_label("switch_end")

        self._break_target_stack.append(end_label)

        sections = (
            [c for c in body_node.children if c.type == "switch_section"]
            if body_node
            else []
        )

        for section in sections:
            pattern_node = next(
                (c for c in section.children if c.type == "constant_pattern"), None
            )
            body_stmts = [
                c
                for c in section.children
                if c.is_named and c.type != "constant_pattern"
            ]

            arm_label = self._fresh_label("case_arm")
            next_label = self._fresh_label("case_next")

            if pattern_node:
                # Extract the literal from constant_pattern
                inner = next((c for c in pattern_node.children if c.is_named), None)
                if inner:
                    case_reg = self._lower_expr(inner)
                else:
                    case_reg = self._lower_expr(pattern_node)
                cmp_reg = self._fresh_reg()
                self._emit(
                    Opcode.BINOP,
                    result_reg=cmp_reg,
                    operands=["==", subject_reg, case_reg],
                    source_location=self._source_loc(section),
                )
                self._emit(
                    Opcode.BRANCH_IF,
                    operands=[cmp_reg],
                    label=f"{arm_label},{next_label}",
                )
            else:
                # default case
                self._emit(Opcode.BRANCH, label=arm_label)

            self._emit(Opcode.LABEL, label=arm_label)
            for stmt in body_stmts:
                self._lower_stmt(stmt)
            self._emit(Opcode.BRANCH, label=end_label)
            self._emit(Opcode.LABEL, label=next_label)

        self._break_target_stack.pop()
        self._emit(Opcode.LABEL, label=end_label)

    # -- C#: try/catch/finally -----------------------------------------

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        finally_node = None
        for child in node.children:
            if child.type == "catch_clause":
                decl_node = next(
                    (c for c in child.children if c.type == "catch_declaration"),
                    None,
                )
                exc_var = None
                exc_type = None
                if decl_node:
                    type_node = next(
                        (
                            c
                            for c in decl_node.children
                            if c.type == "identifier"
                            or c.type == "qualified_name"
                            or c.type == "generic_name"
                        ),
                        None,
                    )
                    name_node = next(
                        (
                            c
                            for c in decl_node.children
                            if c.type == "identifier" and c != type_node
                        ),
                        None,
                    )
                    if type_node:
                        exc_type = self._node_text(type_node)
                    if name_node:
                        exc_var = self._node_text(name_node)
                catch_body = child.child_by_field_name("body") or next(
                    (c for c in child.children if c.type == "block"),
                    None,
                )
                catch_clauses.append(
                    {"body": catch_body, "variable": exc_var, "type": exc_type}
                )
            elif child.type == "finally_clause":
                finally_node = next(
                    (c for c in child.children if c.type == "block"),
                    None,
                )
        self._lower_try_catch(node, body_node, catch_clauses, finally_node)

    # -- C#: store target override -------------------------------------

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
        elif target.type == "member_access_expression":
            obj_node = target.child_by_field_name("expression")
            name_node = target.child_by_field_name("name")
            if obj_node and name_node:
                obj_reg = self._lower_expr(obj_node)
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[obj_reg, self._node_text(name_node), val_reg],
                    source_location=self._source_loc(parent_node),
                )
        elif target.type == "element_access_expression":
            obj_node = target.child_by_field_name("expression")
            bracket_node = target.child_by_field_name("subscript")
            if obj_node:
                obj_reg = self._lower_expr(obj_node)
                idx_reg = (
                    self._lower_expr(bracket_node)
                    if bracket_node
                    else self._fresh_reg()
                )
                self._emit(
                    Opcode.STORE_INDEX,
                    operands=[obj_reg, idx_reg, val_reg],
                    source_location=self._source_loc(parent_node),
                )
        else:
            self._emit(
                Opcode.STORE_VAR,
                operands=[self._node_text(target), val_reg],
                source_location=self._source_loc(parent_node),
            )
