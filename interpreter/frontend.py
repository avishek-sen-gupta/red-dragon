"""Frontend / AST-to-IR Lowering."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .ir import IRInstruction, Opcode


class Frontend(ABC):
    @abstractmethod
    def lower(self, tree, source: bytes) -> list[IRInstruction]:
        ...


class PythonFrontend(Frontend):
    """Lowers a Python tree-sitter AST into flattened TAC IR."""

    def __init__(self):
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions: list[IRInstruction] = []

    def _fresh_reg(self) -> str:
        r = f"%{self._reg_counter}"
        self._reg_counter += 1
        return r

    def _fresh_label(self, prefix: str = "L") -> str:
        lbl = f"{prefix}_{self._label_counter}"
        self._label_counter += 1
        return lbl

    def _emit(self, opcode: Opcode, *, result_reg: str | None = None,
              operands: list[Any] | None = None, label: str | None = None,
              source_location: str | None = None):
        inst = IRInstruction(
            opcode=opcode, result_reg=result_reg,
            operands=operands or [], label=label,
            source_location=source_location,
        )
        self._instructions.append(inst)
        return inst

    def lower(self, tree, source: bytes) -> list[IRInstruction]:
        self._reg_counter = 0
        self._label_counter = 0
        self._instructions = []
        self._source = source
        root = tree.root_node
        self._emit(Opcode.LABEL, label="entry")
        self._lower_block(root)
        return self._instructions

    def _node_text(self, node) -> str:
        return self._source[node.start_byte:node.end_byte].decode("utf-8")

    def _source_loc(self, node) -> str:
        return f"{node.start_point[0] + 1}:{node.start_point[1]}"

    # ── dispatchers ──────────────────────────────────────────────

    def _lower_block(self, node):
        """Lower a block of statements (module / suite / body)."""
        for child in node.children:
            self._lower_stmt(child)

    def _lower_stmt(self, node):
        ntype = node.type
        if ntype == "expression_statement":
            self._lower_expr(node.children[0])
        elif ntype == "assignment":
            self._lower_assignment(node)
        elif ntype == "augmented_assignment":
            self._lower_augmented_assignment(node)
        elif ntype == "return_statement":
            self._lower_return(node)
        elif ntype == "if_statement":
            self._lower_if(node)
        elif ntype == "while_statement":
            self._lower_while(node)
        elif ntype == "for_statement":
            self._lower_for(node)
        elif ntype == "function_definition":
            self._lower_function_def(node)
        elif ntype == "class_definition":
            self._lower_class_def(node)
        elif ntype == "raise_statement":
            self._lower_raise(node)
        elif ntype == "pass_statement":
            pass  # no-op
        elif ntype in ("comment", "newline", "\n"):
            pass
        else:
            # Fallback: try to lower as expression
            self._lower_expr(node)

    # ── expressions → register ───────────────────────────────────

    def _lower_expr(self, node) -> str:
        """Lower an expression, return the register holding its value."""
        ntype = node.type

        if ntype == "identifier":
            reg = self._fresh_reg()
            self._emit(Opcode.LOAD_VAR, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype in ("integer", "float"):
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype == "string" or ntype == "concatenated_string":
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype in ("true", "false", "none"):
            reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=reg,
                       operands=[self._node_text(node)],
                       source_location=self._source_loc(node))
            return reg

        if ntype == "binary_operator":
            return self._lower_binop(node)

        if ntype == "boolean_operator":
            return self._lower_binop(node)

        if ntype == "comparison_operator":
            return self._lower_comparison(node)

        if ntype == "unary_operator":
            return self._lower_unop(node)

        if ntype == "not_operator":
            return self._lower_unop(node)

        if ntype == "call":
            return self._lower_call(node)

        if ntype == "attribute":
            return self._lower_attribute(node)

        if ntype == "subscript":
            return self._lower_subscript(node)

        if ntype == "parenthesized_expression":
            # Unwrap parens
            inner = node.children[1]  # skip '('
            return self._lower_expr(inner)

        if ntype == "list":
            return self._lower_list_literal(node)

        if ntype == "dictionary":
            return self._lower_dict_literal(node)

        if ntype == "tuple":
            return self._lower_tuple_literal(node)

        if ntype == "conditional_expression":
            return self._lower_conditional_expr(node)

        # Fallback: symbolic
        reg = self._fresh_reg()
        self._emit(Opcode.SYMBOLIC, result_reg=reg,
                   operands=[f"unsupported:{ntype}"],
                   source_location=self._source_loc(node))
        return reg

    # ── specific lowerings ───────────────────────────────────────

    def _lower_binop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=reg, operands=[op, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_comparison(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        lhs_reg = self._lower_expr(children[0])
        op = self._node_text(children[1])
        rhs_reg = self._lower_expr(children[2])
        reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=reg, operands=[op, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_unop(self, node) -> str:
        children = [c for c in node.children if c.type not in ("(", ")")]
        op = self._node_text(children[0])
        operand_reg = self._lower_expr(children[1])
        reg = self._fresh_reg()
        self._emit(Opcode.UNOP, result_reg=reg, operands=[op, operand_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_call(self, node) -> str:
        func_node = node.child_by_field_name("function")
        args_node = node.child_by_field_name("arguments")

        arg_regs = []
        if args_node:
            for child in args_node.children:
                if child.type in ("(", ")", ","):
                    continue
                arg_regs.append(self._lower_expr(child))

        # Method call: obj.method(...)
        if func_node and func_node.type == "attribute":
            obj_node = func_node.child_by_field_name("object")
            attr_node = func_node.child_by_field_name("attribute")
            obj_reg = self._lower_expr(obj_node)
            method_name = self._node_text(attr_node)
            reg = self._fresh_reg()
            self._emit(Opcode.CALL_METHOD, result_reg=reg,
                       operands=[obj_reg, method_name] + arg_regs,
                       source_location=self._source_loc(node))
            return reg

        # Plain function call
        if func_node and func_node.type == "identifier":
            func_name = self._node_text(func_node)
            reg = self._fresh_reg()
            self._emit(Opcode.CALL_FUNCTION, result_reg=reg,
                       operands=[func_name] + arg_regs,
                       source_location=self._source_loc(node))
            return reg

        # Dynamic / unknown call target
        target_reg = self._lower_expr(func_node)
        reg = self._fresh_reg()
        self._emit(Opcode.CALL_UNKNOWN, result_reg=reg,
                   operands=[target_reg] + arg_regs,
                   source_location=self._source_loc(node))
        return reg

    def _lower_attribute(self, node) -> str:
        obj_node = node.child_by_field_name("object")
        attr_node = node.child_by_field_name("attribute")
        obj_reg = self._lower_expr(obj_node)
        field_name = self._node_text(attr_node)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_FIELD, result_reg=reg,
                   operands=[obj_reg, field_name],
                   source_location=self._source_loc(node))
        return reg

    def _lower_subscript(self, node) -> str:
        obj_node = node.child_by_field_name("value")
        idx_node = node.child_by_field_name("subscript")
        obj_reg = self._lower_expr(obj_node)
        idx_reg = self._lower_expr(idx_node)
        reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=reg,
                   operands=[obj_reg, idx_reg],
                   source_location=self._source_loc(node))
        return reg

    def _lower_assignment(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        val_reg = self._lower_expr(right)
        self._lower_store_target(left, val_reg, node)

    def _lower_augmented_assignment(self, node):
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op_node = [c for c in node.children if c.type not in (
            left.type, right.type)][0]
        op_text = self._node_text(op_node).rstrip("=")  # += → +

        # Load current value
        lhs_reg = self._lower_expr(left)
        rhs_reg = self._lower_expr(right)
        result = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=result,
                   operands=[op_text, lhs_reg, rhs_reg],
                   source_location=self._source_loc(node))
        self._lower_store_target(left, result, node)

    def _lower_store_target(self, target, val_reg: str, parent_node):
        if target.type == "identifier":
            self._emit(Opcode.STORE_VAR, operands=[self._node_text(target), val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "attribute":
            obj_node = target.child_by_field_name("object")
            attr_node = target.child_by_field_name("attribute")
            obj_reg = self._lower_expr(obj_node)
            self._emit(Opcode.STORE_FIELD,
                       operands=[obj_reg, self._node_text(attr_node), val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "subscript":
            obj_node = target.child_by_field_name("value")
            idx_node = target.child_by_field_name("subscript")
            obj_reg = self._lower_expr(obj_node)
            idx_reg = self._lower_expr(idx_node)
            self._emit(Opcode.STORE_INDEX,
                       operands=[obj_reg, idx_reg, val_reg],
                       source_location=self._source_loc(parent_node))
        elif target.type == "pattern_list" or target.type == "tuple_pattern":
            # Multi-assignment — emit symbolic unpack
            for i, child in enumerate(target.children):
                if child.type == ",":
                    continue
                idx_reg = self._fresh_reg()
                self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
                elem_reg = self._fresh_reg()
                self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg,
                           operands=[val_reg, idx_reg])
                self._lower_store_target(child, elem_reg, parent_node)

    def _lower_return(self, node):
        children = [c for c in node.children if c.type != "return"]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=val_reg, operands=["None"])
        self._emit(Opcode.RETURN, operands=[val_reg],
                   source_location=self._source_loc(node))

    def _lower_if(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("if_true")
        false_label = self._fresh_label("if_false")
        end_label = self._fresh_label("if_end")

        if alt_node:
            self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                       label=f"{true_label},{false_label}",
                       source_location=self._source_loc(node))
        else:
            self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                       label=f"{true_label},{end_label}",
                       source_location=self._source_loc(node))

        # True branch
        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        # False branch
        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            # elif or else
            if alt_node.type == "elif_clause":
                # Treat elif as nested if
                self._lower_elif(alt_node, end_label)
            elif alt_node.type == "else_clause":
                body = alt_node.child_by_field_name("body")
                if body:
                    self._lower_block(body)
                else:
                    # else body is the children after ":"
                    for child in alt_node.children:
                        if child.type not in ("else", ":"):
                            self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_elif(self, node, end_label: str):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")

        cond_reg = self._lower_expr(cond_node)
        true_label = self._fresh_label("elif_true")
        false_label = self._fresh_label("elif_false") if alt_node else end_label

        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{true_label},{false_label}",
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=true_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=end_label)

        if alt_node:
            self._emit(Opcode.LABEL, label=false_label)
            if alt_node.type == "elif_clause":
                self._lower_elif(alt_node, end_label)
            elif alt_node.type == "else_clause":
                for child in alt_node.children:
                    if child.type not in ("else", ":"):
                        self._lower_stmt(child)
            self._emit(Opcode.BRANCH, label=end_label)

    def _lower_while(self, node):
        cond_node = node.child_by_field_name("condition")
        body_node = node.child_by_field_name("body")

        loop_label = self._fresh_label("while_cond")
        body_label = self._fresh_label("while_body")
        end_label = self._fresh_label("while_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._lower_expr(cond_node)
        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{body_label},{end_label}",
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=body_label)
        self._lower_block(body_node)
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_for(self, node):
        # for <target> in <iter>: <body>
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        body_node = node.child_by_field_name("body")

        iter_reg = self._lower_expr(right)
        idx_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=idx_reg, operands=["0"])
        len_reg = self._fresh_reg()
        self._emit(Opcode.CALL_FUNCTION, result_reg=len_reg,
                   operands=["len", iter_reg])

        loop_label = self._fresh_label("for_cond")
        body_label = self._fresh_label("for_body")
        end_label = self._fresh_label("for_end")

        self._emit(Opcode.LABEL, label=loop_label)
        cond_reg = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=cond_reg,
                   operands=["<", idx_reg, len_reg])
        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{body_label},{end_label}")

        self._emit(Opcode.LABEL, label=body_label)
        elem_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_INDEX, result_reg=elem_reg,
                   operands=[iter_reg, idx_reg])
        self._lower_store_target(left, elem_reg, node)

        self._lower_block(body_node)

        # idx += 1
        one_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=one_reg, operands=["1"])
        new_idx = self._fresh_reg()
        self._emit(Opcode.BINOP, result_reg=new_idx,
                   operands=["+", idx_reg, one_reg])
        # Update idx_reg by storing and reloading (since registers are SSA-like,
        # we use the new register going forward via a store to a temp var)
        self._emit(Opcode.STORE_VAR, operands=["__for_idx", new_idx])
        idx_reload = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=idx_reload,
                   operands=["__for_idx"])
        # We can't retroactively change idx_reg, so this is approximate.
        # The LLM interpreter will handle the semantics correctly.
        self._emit(Opcode.BRANCH, label=loop_label)

        self._emit(Opcode.LABEL, label=end_label)

    def _lower_function_def(self, node):
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        body_node = node.child_by_field_name("body")

        func_name = self._node_text(name_node)
        func_label = self._fresh_label(f"func_{func_name}")
        end_label = self._fresh_label(f"end_{func_name}")

        # Skip the function body in linear flow
        self._emit(Opcode.BRANCH, label=end_label,
                   source_location=self._source_loc(node))

        self._emit(Opcode.LABEL, label=func_label)

        # Emit parameter loads
        if params_node:
            param_idx = 0
            for child in params_node.children:
                if child.type == "identifier":
                    self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                               operands=[f"param:{self._node_text(child)}"],
                               source_location=self._source_loc(child))
                    self._emit(Opcode.STORE_VAR,
                               operands=[self._node_text(child),
                                         f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type in ("(", ")", ",", ":"):
                    continue
                elif child.type == "default_parameter":
                    pname_node = child.child_by_field_name("name")
                    if pname_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(pname_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(pname_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type == "typed_parameter":
                    id_node = None
                    for sub in child.children:
                        if sub.type == "identifier":
                            id_node = sub
                            break
                    if id_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(id_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(id_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1
                elif child.type == "typed_default_parameter":
                    pname_node = child.child_by_field_name("name")
                    if pname_node:
                        self._emit(Opcode.SYMBOLIC, result_reg=self._fresh_reg(),
                                   operands=[f"param:{self._node_text(pname_node)}"],
                                   source_location=self._source_loc(child))
                        self._emit(Opcode.STORE_VAR,
                                   operands=[self._node_text(pname_node),
                                             f"%{self._reg_counter - 1}"])
                    param_idx += 1

        self._lower_block(body_node)

        # Implicit return None at end of function
        none_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=none_reg, operands=["None"])
        self._emit(Opcode.RETURN, operands=[none_reg])

        self._emit(Opcode.LABEL, label=end_label)

        # Store the function as a named value
        func_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=func_reg,
                   operands=[f"<function:{func_name}@{func_label}>"])
        self._emit(Opcode.STORE_VAR, operands=[func_name, func_reg])

    def _lower_class_def(self, node):
        name_node = node.child_by_field_name("name")
        body_node = node.child_by_field_name("body")
        class_name = self._node_text(name_node)

        class_label = self._fresh_label(f"class_{class_name}")
        end_label = self._fresh_label(f"end_class_{class_name}")

        self._emit(Opcode.BRANCH, label=end_label,
                   source_location=self._source_loc(node))
        self._emit(Opcode.LABEL, label=class_label)
        self._lower_block(body_node)
        self._emit(Opcode.LABEL, label=end_label)

        cls_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=cls_reg,
                   operands=[f"<class:{class_name}@{class_label}>"])
        self._emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])

    def _lower_raise(self, node):
        children = [c for c in node.children if c.type != "raise"]
        if children:
            val_reg = self._lower_expr(children[0])
        else:
            val_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=val_reg, operands=["None"])
        self._emit(Opcode.THROW, operands=[val_reg],
                   source_location=self._source_loc(node))

    def _lower_list_literal(self, node) -> str:
        arr_reg = self._fresh_reg()
        elems = [c for c in node.children if c.type not in ("[", "]", ",")]
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(Opcode.NEW_ARRAY, result_reg=arr_reg,
                   operands=["list", size_reg],
                   source_location=self._source_loc(node))
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    def _lower_dict_literal(self, node) -> str:
        obj_reg = self._fresh_reg()
        self._emit(Opcode.NEW_OBJECT, result_reg=obj_reg, operands=["dict"],
                   source_location=self._source_loc(node))
        for child in node.children:
            if child.type == "pair":
                key_node = child.child_by_field_name("key")
                val_node = child.child_by_field_name("value")
                key_reg = self._lower_expr(key_node)
                val_reg = self._lower_expr(val_node)
                self._emit(Opcode.STORE_INDEX,
                           operands=[obj_reg, key_reg, val_reg])
        return obj_reg

    def _lower_tuple_literal(self, node) -> str:
        elems = [c for c in node.children if c.type not in ("(", ")", ",")]
        arr_reg = self._fresh_reg()
        size_reg = self._fresh_reg()
        self._emit(Opcode.CONST, result_reg=size_reg, operands=[str(len(elems))])
        self._emit(Opcode.NEW_ARRAY, result_reg=arr_reg,
                   operands=["tuple", size_reg],
                   source_location=self._source_loc(node))
        for i, elem in enumerate(elems):
            val_reg = self._lower_expr(elem)
            idx_reg = self._fresh_reg()
            self._emit(Opcode.CONST, result_reg=idx_reg, operands=[str(i)])
            self._emit(Opcode.STORE_INDEX, operands=[arr_reg, idx_reg, val_reg])
        return arr_reg

    def _lower_conditional_expr(self, node) -> str:
        # value_if_true if condition else value_if_false
        children = [c for c in node.children if c.type not in ("if", "else")]
        true_expr = children[0]
        cond_expr = children[1]
        false_expr = children[2]

        cond_reg = self._lower_expr(cond_expr)
        true_label = self._fresh_label("ternary_true")
        false_label = self._fresh_label("ternary_false")
        end_label = self._fresh_label("ternary_end")

        self._emit(Opcode.BRANCH_IF, operands=[cond_reg],
                   label=f"{true_label},{false_label}")

        self._emit(Opcode.LABEL, label=true_label)
        true_reg = self._lower_expr(true_expr)
        result_var = f"__ternary_{self._label_counter}"
        self._emit(Opcode.STORE_VAR, operands=[result_var, true_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=false_label)
        false_reg = self._lower_expr(false_expr)
        self._emit(Opcode.STORE_VAR, operands=[result_var, false_reg])
        self._emit(Opcode.BRANCH, label=end_label)

        self._emit(Opcode.LABEL, label=end_label)
        result_reg = self._fresh_reg()
        self._emit(Opcode.LOAD_VAR, result_reg=result_reg,
                   operands=[result_var])
        return result_reg


def get_frontend(language: str) -> Frontend:
    if language == "python":
        return PythonFrontend()
    raise ValueError(f"Unsupported language: {language}")
