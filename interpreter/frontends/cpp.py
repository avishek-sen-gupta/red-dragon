"""CppFrontend — tree-sitter C++ AST -> IR lowering (extends CFrontend)."""

from __future__ import annotations

import logging
from typing import Callable

from .c import CFrontend
from ..ir import Opcode
from .. import constants

logger = logging.getLogger(__name__)


class CppFrontend(CFrontend):
    """Lowers a C++ tree-sitter AST into flattened TAC IR.

    Extends CFrontend with C++-specific constructs: classes, namespaces,
    templates, new/delete, lambdas, and reference types.
    """

    def __init__(self):
        super().__init__()

        # -- Add C++-specific expression handlers ----------------------
        self._EXPR_DISPATCH.update(
            {
                "new_expression": self._lower_new_expr,
                "delete_expression": self._lower_delete_expr,
                "lambda_expression": self._lower_lambda,
                "template_function": self._lower_identifier,
                "qualified_identifier": self._lower_qualified_id,
                "scoped_identifier": self._lower_qualified_id,
                "scope_resolution": self._lower_qualified_id,
                "this": self._lower_identifier,
                "condition_clause": self._lower_condition_clause,
                "nullptr": self._lower_const_literal,
                "user_defined_literal": self._lower_const_literal,
                "raw_string_literal": self._lower_const_literal,
                "throw_expression": self._lower_throw_expr,
                "static_cast_expression": self._lower_cpp_cast,
                "dynamic_cast_expression": self._lower_cpp_cast,
                "reinterpret_cast_expression": self._lower_cpp_cast,
                "const_cast_expression": self._lower_cpp_cast,
                "condition_clause": self._lower_condition_clause,
            }
        )

        # -- Add C++-specific statement handlers -----------------------
        self._STMT_DISPATCH.update(
            {
                "class_specifier": self._lower_class_specifier,
                "namespace_definition": self._lower_namespace_def,
                "template_declaration": self._lower_template_decl,
                "using_declaration": lambda _: None,
                "access_specifier": lambda _: None,
                "alias_declaration": lambda _: None,
                "static_assert_declaration": lambda _: None,
                "friend_declaration": lambda _: None,
                "try_statement": self._lower_try,
                "throw_statement": self._lower_throw,
                "for_range_loop": self._lower_range_for,
            }
        )

    # -- C++: condition_clause (wraps if/while conditions) -------------

    def _lower_condition_clause(self, node) -> str:
        """Unwrap condition_clause to reach the inner expression."""
        for child in node.children:
            if child.is_named and child.type not in ("(", ")"):
                return self._lower_expr(child)
        return self._lower_const_literal(node)

    # -- C++: if override for condition_clause -------------------------

    def _lower_if(self, node):
        """Override if lowering to handle C++ condition_clause wrapper."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

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

    # -- C++: while override for condition_clause ----------------------

    def _lower_while(self, node):
        """Override while lowering to handle C++ condition_clause wrapper."""
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(
            Opcode.BRANCH_IF,
            operands=[cond_reg],
            label=f"{body_label},{end_label}",
            source_location=self._source_loc(node),
        )

        self._emit(Opcode.LABEL, label=body_label)
        self._push_loop(loop_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- C++: new expression -------------------------------------------

    def _lower_new_expr(self, node) -> str:
        """Lower new T(args) as CALL_FUNCTION."""
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

    # -- C++: delete expression ----------------------------------------

    def _lower_delete_expr(self, node) -> str:
        """Lower delete as SYMBOLIC."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"delete:{self._node_text(node)[:40]}"],
            source_location=self._source_loc(node),
        )
        return reg

    # -- C++: lambda ---------------------------------------------------

    def _lower_lambda(self, node) -> str:
        """Lower lambda_expression like an arrow function."""
        body_node = node.child_by_field_name("body")
        params_node = node.child_by_field_name("declarator")

        func_name = "__lambda"
        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_c_params(params_node)

        if body_node:
            if body_node.type == "compound_statement":
                self._lower_block(body_node)
            else:
                val_reg = self._lower_expr(body_node)
                self._emit(Opcode.RETURN, operands=[val_reg])

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
        return func_reg

    # -- C++: qualified / scoped identifier ----------------------------

    def _lower_qualified_id(self, node) -> str:
        """Lower qualified_identifier (e.g., std::cout) as LOAD_VAR."""
        reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=reg,
            operands=[self._node_text(node)],
            source_location=self._source_loc(node),
        )
        return reg

    # -- C++: throw expression -----------------------------------------

    def _lower_throw_expr(self, node) -> str:
        """Lower throw as an expression (C++ throw can appear in expressions)."""
        children = [c for c in node.children if c.type != "throw" and c.is_named]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(
                Opcode.CONST,
                result_reg=val_reg,
                operands=[self.DEFAULT_RETURN_VALUE],
            )
        self._emit(
            Opcode.THROW,
            operands=[val_reg],
            source_location=self._source_loc(node),
        )
        return val_reg

    # -- C++: C++-style casts ------------------------------------------

    def _lower_cpp_cast(self, node) -> str:
        """Lower static_cast<T>(expr) etc. -- pass through the value."""
        value_node = node.child_by_field_name("value")
        if value_node:
            return self._lower_expr(value_node)
        # Fallback: find the argument_list or last named child
        children = [c for c in node.children if c.is_named]
        if children:
            return self._lower_expr(children[-1])
        return self._lower_const_literal(node)

    # -- C++: class specifier ------------------------------------------

    def _lower_class_specifier(self, node):
        """Lower class_specifier (C++ class with field_declaration_list body)."""
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
            self._lower_cpp_class_body(body_node)
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

    def _lower_cpp_class_body(self, node):
        """Lower field_declaration_list (C++ class body)."""
        for child in node.children:
            if child.type == "function_definition":
                self._lower_function_def_c(child)
            elif child.type == "declaration":
                self._lower_declaration(child)
            elif child.type == "field_declaration":
                self._lower_struct_field(child)
            elif child.type == "template_declaration":
                self._lower_template_decl(child)
            elif child.type == "friend_declaration":
                continue
            elif child.type == "access_specifier":
                continue
            elif child.type == "field_initializer_list":
                self._lower_field_initializer_list(child)
            elif child.is_named and child.type not in ("{", "}"):
                self._lower_stmt(child)

    def _lower_field_initializer_list(self, node):
        """Lower field_initializer_list: : field(val), field2(val2).

        Emits: LOAD_VAR this → [lower_expr(arg) → STORE_FIELD this, field, val]×N
        """
        this_reg = self._fresh_reg()
        self._emit(
            Opcode.LOAD_VAR,
            result_reg=this_reg,
            operands=["this"],
            source_location=self._source_loc(node),
        )
        for child in node.children:
            if child.type == "field_initializer":
                field_node = next(
                    (c for c in child.children if c.type == "field_identifier"),
                    None,
                )
                args_node = next(
                    (c for c in child.children if c.type == "argument_list"),
                    None,
                )
                if field_node is None:
                    continue
                field_name = self._node_text(field_node)
                if args_node:
                    arg_children = [c for c in args_node.children if c.is_named]
                    val_reg = (
                        self._lower_expr(arg_children[0])
                        if arg_children
                        else self._fresh_reg()
                    )
                else:
                    val_reg = self._fresh_reg()
                    self._emit(
                        Opcode.CONST,
                        result_reg=val_reg,
                        operands=[self.DEFAULT_RETURN_VALUE],
                    )
                self._emit(
                    Opcode.STORE_FIELD,
                    operands=[this_reg, field_name, val_reg],
                    source_location=self._source_loc(child),
                )

    # -- C++: override function_def to handle field_initializer_list -----

    def _lower_function_def_c(self, node):
        """Override to detect and lower field_initializer_list in constructors."""
        declarator_node = node.child_by_field_name("declarator")
        body_node = node.child_by_field_name("body")
        init_list_node = next(
            (c for c in node.children if c.type == "field_initializer_list"),
            None,
        )

        func_name = "__anon"
        params_node = None

        if declarator_node:
            if declarator_node.type == "function_declarator":
                name_node = declarator_node.child_by_field_name("declarator")
                params_node = declarator_node.child_by_field_name("parameters")
                func_name = (
                    self._extract_declarator_name(name_node) if name_node else "__anon"
                )
            else:
                func_decl = self._find_function_declarator(declarator_node)
                if func_decl:
                    name_node = func_decl.child_by_field_name("declarator")
                    params_node = func_decl.child_by_field_name("parameters")
                    func_name = (
                        self._extract_declarator_name(name_node)
                        if name_node
                        else "__anon"
                    )
                else:
                    func_name = self._extract_declarator_name(declarator_node)

        func_label = self._fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        self._emit(
            Opcode.BRANCH, label=end_label, source_location=self._source_loc(node)
        )
        self._emit(Opcode.LABEL, label=func_label)

        if params_node:
            self._lower_c_params(params_node)

        # Emit field initializer list (C++ constructor initializer) before body
        if init_list_node:
            self._lower_field_initializer_list(init_list_node)

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

    # -- C++: namespace ------------------------------------------------

    def _lower_namespace_def(self, node):
        """Lower namespace_definition as a block -- descend into body."""
        body_node = node.child_by_field_name("body")
        if body_node:
            self._lower_block(body_node)

    # -- C++: template -------------------------------------------------

    def _lower_template_decl(self, node):
        """Lower template_declaration as SYMBOLIC, but try to lower the inner declaration."""
        # The actual declaration is a child of the template node
        inner_decls = [
            c
            for c in node.children
            if c.is_named
            and c.type
            not in ("template_parameter_list", "template_parameter_declaration")
        ]
        if inner_decls:
            self._lower_stmt(inner_decls[-1])
        else:
            reg = self._fresh_reg()
            self._emit(
                Opcode.SYMBOLIC,
                result_reg=reg,
                operands=[f"template:{self._node_text(node)[:60]}"],
                source_location=self._source_loc(node),
            )

    # -- C++: range-based for ------------------------------------------

    def _lower_range_for(self, node):
        """Lower for (auto x : container) { body }."""
        declarator_node = node.child_by_field_name("declarator")
        right_node = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        var_name = "__range_var"
        if declarator_node:
            var_name = self._extract_declarator_name(declarator_node)

        iter_reg = self._lower_expr(right_node) if right_node else self._fresh_reg()

        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", iter_reg])

        loop_label = self._fresh_label("range_for_cond")
        body_label = self._fresh_label("range_for_body")
        end_label = self._fresh_label("range_for_end")

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

        update_label = self._fresh_label("range_for_update")
        self._push_loop(update_label, end_label)
        if body_node:
            self._lower_block(body_node)
        self._pop_loop()

        self._emit(Opcode.LABEL, label=update_label)
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx, operands=["+", idx_reg, one_reg])
        self._emit(Opcode.STORE_VAR, operands=["__range_idx", new_idx])
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    # -- C++: throw statement ------------------------------------------

    def _lower_throw(self, node):
        self._lower_raise_or_throw(node, keyword="throw")

    # -- C++: try/catch ------------------------------------------------

    def _lower_try(self, node):
        body_node = node.child_by_field_name("body")
        catch_clauses = []
        for child in node.children:
            if child.type == "catch_clause":
                param_node = next(
                    (c for c in child.children if c.type == "catch_declarator"),
                    None,
                )
                exc_var = None
                exc_type = None
                if param_node:
                    # catch_declarator contains type and optional identifier
                    id_node = next(
                        (c for c in param_node.children if c.type == "identifier"),
                        None,
                    )
                    exc_var = self._node_text(id_node) if id_node else None
                    type_nodes = [
                        c for c in param_node.children if c.is_named and c != id_node
                    ]
                    if type_nodes:
                        exc_type = self._node_text(type_nodes[0])
                catch_body = child.child_by_field_name("body")
                catch_clauses.append(
                    {"body": catch_body, "variable": exc_var, "type": exc_type}
                )
        self._lower_try_catch(node, body_node, catch_clauses)
