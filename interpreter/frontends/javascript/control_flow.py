"""JavaScript-specific control flow lowerers — pure functions taking (ctx, node)."""

from __future__ import annotations

from typing import Any

from interpreter.frontends.context import TreeSitterEmitContext

from interpreter.frontends.common.exceptions import (
    lower_raise_or_throw,
    lower_try_catch,
)
from interpreter.frontends.javascript.node_types import JavaScriptNodeType as JSN
from interpreter.operator_kind import resolve_binop
from interpreter.var_name import VarName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Const,
    LoadVar,
    DeclVar,
    StoreVar,
    Binop,
    CallFunction,
    LoadIndex,
    Label_,
    Branch,
    BranchIf,
    ImportModule,
    LoadField,
)
from interpreter.path_name import NO_PATH_NAME
from interpreter.field_name import FieldName


def lower_js_alternative(ctx: TreeSitterEmitContext, alt_node, end_label: str) -> None:
    alt_type = alt_node.type
    if alt_type == JSN.ELSE_CLAUSE:
        for child in alt_node.children:
            if child.type not in (JSN.ELSE,):
                ctx.lower_stmt(child)
    elif alt_type == JSN.IF_STATEMENT:
        lower_js_if(ctx, alt_node)
    else:
        ctx.lower_block(alt_node)


def lower_js_if(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    cond_reg = ctx.lower_expr(cond_node)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    if alt_node:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, false_label)),
            node=node,
        )
    else:
        ctx.emit_inst(
            BranchIf(cond_reg=cond_reg, branch_targets=(true_label, end_label)),
            node=node,
        )

    ctx.emit_inst(Label_(label=true_label))
    ctx.lower_block(body_node)
    ctx.emit_inst(Branch(label=end_label))

    if alt_node:
        ctx.emit_inst(Label_(label=false_label))
        lower_js_alternative(ctx, alt_node, end_label)
        ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_for_in(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    # for (let x in/of obj) { body }
    operator_node = node.child_by_field_name("operator")
    is_for_of = operator_node is not None and ctx.node_text(operator_node) == "of"

    if is_for_of:
        lower_for_of(ctx, node)
        return

    # for...in — model as: keys(obj) -> index-based loop over keys array
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    obj_reg = ctx.lower_expr(right)
    keys_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=keys_reg, func_name=FuncName("keys"), args=(obj_reg,)),
        node=node,
    )

    is_destructure = left is not None and _is_destructuring_pattern(left)
    raw_name = (
        "__for_in_destructure"
        if is_destructure
        else (_extract_var_name(ctx, left) if left else "__for_in_var")
    )

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name=VarName("__for_idx"), value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=len_reg, func_name=FuncName("len"), args=(keys_reg,))
    )

    loop_label = ctx.fresh_label("for_in_cond")
    body_label = ctx.fresh_label("for_in_body")
    end_label = ctx.fresh_label("for_in_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name=VarName("__for_idx")))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=keys_reg, index_reg=idx_reg))

    if is_destructure:
        _lower_for_destructure(ctx, left, elem_reg)
    else:
        var_name = ctx.declare_block_var(raw_name)
        if var_name:
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=elem_reg))

    update_label = ctx.fresh_label("for_in_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__for_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_for_of(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower for (const x of iterable) as index-based iteration.

    Handles destructuring patterns: ``for (const [k, v] of arr)`` and
    ``for (const {x, y} of arr)`` by delegating to the existing
    array/object destructure helpers.
    """
    left = node.child_by_field_name(ctx.constants.assign_left_field)
    right = node.child_by_field_name(ctx.constants.assign_right_field)
    body_node = node.child_by_field_name(ctx.constants.for_body_field)

    iter_reg = ctx.lower_expr(right)
    is_destructure = left is not None and _is_destructuring_pattern(left)
    raw_name = (
        "__for_of_destructure"
        if is_destructure
        else (_extract_var_name(ctx, left) if left else "__for_of_var")
    )

    init_idx = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=init_idx, value="0"))
    ctx.emit_inst(DeclVar(name=VarName("__for_idx"), value_reg=init_idx))
    len_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(result_reg=len_reg, func_name=FuncName("len"), args=(iter_reg,))
    )

    loop_label = ctx.fresh_label("for_of_cond")
    body_label = ctx.fresh_label("for_of_body")
    end_label = ctx.fresh_label("for_of_end")

    ctx.emit_inst(Label_(label=loop_label))
    idx_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=idx_reg, name=VarName("__for_idx")))
    cond_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=cond_reg,
            operator=resolve_binop("<"),
            left=idx_reg,
            right=len_reg,
        )
    )
    ctx.emit_inst(BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)))

    ctx.emit_inst(Label_(label=body_label))
    ctx.enter_block_scope()
    elem_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadIndex(result_reg=elem_reg, arr_reg=iter_reg, index_reg=idx_reg))

    if is_destructure:
        _lower_for_destructure(ctx, left, elem_reg)
    else:
        var_name = ctx.declare_block_var(raw_name)
        if var_name:
            ctx.emit_inst(DeclVar(name=VarName(var_name), value_reg=elem_reg))

    update_label = ctx.fresh_label("for_of_update")
    ctx.push_loop(update_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()
    ctx.exit_block_scope()

    ctx.emit_inst(Label_(label=update_label))
    one_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=one_reg, value="1"))
    new_idx = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=new_idx, operator=resolve_binop("+"), left=idx_reg, right=one_reg
        )
    )
    ctx.emit_inst(StoreVar(name=VarName("__for_idx"), value_reg=new_idx))
    ctx.emit_inst(Branch(label=loop_label))

    ctx.emit_inst(Label_(label=end_label))


def _extract_var_name(
    ctx: TreeSitterEmitContext, node: Any
) -> str | None:  # Any: tree-sitter node — untyped at Python boundary
    """Extract variable name from a declaration or identifier."""
    if node.type == JSN.IDENTIFIER:
        return ctx.node_text(node)
    if node.type in (JSN.LEXICAL_DECLARATION, JSN.VARIABLE_DECLARATION):
        for child in node.children:
            if child.type == JSN.VARIABLE_DECLARATOR:
                name_node = child.child_by_field_name(ctx.constants.func_name_field)
                if name_node:
                    return ctx.node_text(name_node)
    return None


def _is_destructuring_pattern(node) -> bool:
    """Check if node is an array_pattern or object_pattern."""
    return node.type in (JSN.ARRAY_PATTERN, JSN.OBJECT_PATTERN)


def _lower_for_destructure(
    ctx: TreeSitterEmitContext, pattern_node, elem_reg: str
) -> None:
    """Lower destructuring in a for-of/for-in loop body.

    Delegates to the existing array/object destructure helpers from
    ``javascript.declarations``.
    """
    from interpreter.frontends.javascript.declarations import (
        _lower_array_destructure,
        _lower_object_destructure,
    )

    if pattern_node.type == JSN.ARRAY_PATTERN:
        _lower_array_destructure(ctx, pattern_node, elem_reg, pattern_node)
    elif pattern_node.type == JSN.OBJECT_PATTERN:
        _lower_object_destructure(ctx, pattern_node, elem_reg, pattern_node)


def lower_js_try(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    body_node = node.child_by_field_name("body")
    handler = node.child_by_field_name("handler")
    finalizer = node.child_by_field_name("finalizer")
    catch_clauses = []
    if handler:
        param_node = handler.child_by_field_name("parameter")
        exc_var = ctx.node_text(param_node) if param_node else None
        catch_body = handler.child_by_field_name("body")
        catch_clauses.append({"body": catch_body, "variable": exc_var, "type": None})
    finally_node = finalizer.child_by_field_name("body") if finalizer else None
    lower_try_catch(ctx, node, body_node, catch_clauses, finally_node)


def lower_js_throw(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    lower_raise_or_throw(ctx, node, keyword="throw")


def lower_switch_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower switch(x) { case a: ... default: ... } as if/else chain."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    disc_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    if body_node:
        cases = [
            c
            for c in body_node.children
            if c.type in (JSN.SWITCH_CASE, JSN.SWITCH_DEFAULT)
        ]
        for case_node in cases:
            if case_node.type == JSN.SWITCH_CASE:
                value_child = case_node.child_by_field_name("value")
                if value_child:
                    case_reg = ctx.lower_expr(value_child)
                    cond_reg = ctx.fresh_reg()
                    ctx.emit_inst(
                        Binop(
                            result_reg=cond_reg,
                            operator=resolve_binop("==="),
                            left=disc_reg,
                            right=case_reg,
                        ),
                        node=case_node,
                    )
                    body_label = ctx.fresh_label("case_body")
                    next_label = ctx.fresh_label("case_next")
                    ctx.emit_inst(
                        BranchIf(
                            cond_reg=cond_reg,
                            branch_targets=(body_label, next_label),
                        )
                    )
                    ctx.emit_inst(Label_(label=body_label))
                    _lower_switch_case_body(ctx, case_node)
                    ctx.emit_inst(Branch(label=end_label))
                    ctx.emit_inst(Label_(label=next_label))
            elif case_node.type == JSN.SWITCH_DEFAULT:
                _lower_switch_case_body(ctx, case_node)

    ctx.break_target_stack.pop()
    ctx.emit_inst(Label_(label=end_label))


def _lower_switch_case_body(ctx: TreeSitterEmitContext, case_node) -> None:
    """Lower the body statements of a switch case/default clause."""
    for child in case_node.children:
        if child.is_named and child.type not in (JSN.SWITCH_CASE, JSN.SWITCH_DEFAULT):
            ctx.lower_stmt(child)


def lower_do_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower do { body } while (cond)."""
    body_node = node.child_by_field_name(ctx.constants.while_body_field)
    cond_node = node.child_by_field_name(ctx.constants.while_condition_field)

    body_label = ctx.fresh_label("do_body")
    cond_label = ctx.fresh_label("do_cond")
    end_label = ctx.fresh_label("do_end")

    ctx.emit_inst(Label_(label=body_label))

    ctx.push_loop(cond_label, end_label)
    if body_node:
        ctx.lower_block(body_node)
    ctx.pop_loop()

    ctx.emit_inst(Label_(label=cond_label))
    cond_reg = ctx.lower_expr(cond_node) if cond_node else ctx.fresh_reg()
    ctx.emit_inst(
        BranchIf(cond_reg=cond_reg, branch_targets=(body_label, end_label)),
        node=node,
    )
    ctx.emit_inst(Label_(label=end_label))


def lower_labeled_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `label: stmt` -> LABEL(name) + lower body."""
    label_node = node.child_by_field_name("label")
    body_node = node.child_by_field_name("body")

    label_name = ctx.node_text(label_node) if label_node else "unknown_label"
    label = ctx.fresh_label(label_name)
    ctx.emit_inst(Label_(label=label))

    if body_node:
        ctx.lower_stmt(body_node)


def lower_with_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower `with (obj) { body }` — lower object then body."""
    object_node = node.child_by_field_name(ctx.constants.attr_object_field)
    body_node = node.child_by_field_name("body")
    if object_node:
        ctx.lower_expr(object_node)
    if body_node:
        ctx.lower_block(body_node)


def lower_import_statement(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower import_statement: handle both CommonJS require and ESM imports.

    - require('y')                    → CALL_FUNCTION require
    - var x = require('y')            → CALL_FUNCTION require + STORE_VAR x
    - import { a, b } from "./m"      → IMPORT_MODULE + LOAD_FIELD + DECL_VAR
    - import foo from "./m"           → IMPORT_MODULE + DECL_VAR
    - import * as ns from "./m"       → IMPORT_MODULE + DECL_VAR
    """
    # Check for various import patterns by looking at the node's structure
    # JavaScript import_statement can have different child structures

    # Extract the module path from the import_statement
    module_path = None
    for child in node.children:
        if child.type == "string":
            raw = ctx.node_text(child)
            module_path = raw.strip("'\"")
            break

    if module_path is None:
        # No module path found, skip this import
        return

    # Emit IMPORT_MODULE to load the module
    mod_reg = ctx.fresh_reg()
    resolved = ctx.resolved_imports.get(module_path, NO_PATH_NAME)
    ctx.emit_inst(
        ImportModule(
            result_reg=mod_reg,
            module_path=module_path,
            resolved_path=resolved,
        ),
        node=node,
    )

    # Find the import_clause to determine what to bind
    import_clause = None
    for child in node.children:
        if child.type == "import_clause":
            import_clause = child
            break

    if import_clause is None:
        return

    # Process the import_clause to bind imported names
    _lower_import_clause(ctx, import_clause, mod_reg, node)


def _lower_import_clause(
    ctx: TreeSitterEmitContext,
    clause: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower import_clause: process named_imports, namespace_import, or default_import."""
    for child in clause.children:
        if child.type == "named_imports":
            # import { a, b, c } from "./module"
            _lower_named_imports(ctx, child, mod_reg, parent)
        elif child.type == "namespace_import":
            # import * as ns from "./module"
            _lower_namespace_import(ctx, child, mod_reg, parent)
        elif child.type == "identifier":
            # Default import: import foo from "./module"
            # In an import_clause, a bare identifier is the default import
            import_name = ctx.node_text(child)
            ctx.emit_inst(
                DeclVar(name=VarName(import_name), value_reg=mod_reg), node=parent
            )


def _lower_named_imports(
    ctx: TreeSitterEmitContext,
    named_imports: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower named_imports: { a, b, c } or { a as x, b as y }."""
    for child in named_imports.children:
        if child.type == "import_specifier":
            _lower_import_specifier(ctx, child, mod_reg, parent)


def _lower_import_specifier(
    ctx: TreeSitterEmitContext,
    specifier: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower import_specifier: a or a as b."""
    # import_specifier has children: [name] or [name, 'as', alias]
    named_children = [c for c in specifier.children if c.is_named]
    if len(named_children) == 1:
        # Simple name: import { a } from "./module"
        import_name = ctx.node_text(named_children[0])
        field_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=field_reg,
                obj_reg=mod_reg,
                field_name=FieldName(import_name),
            ),
            node=parent,
        )
        ctx.emit_inst(
            DeclVar(name=VarName(import_name), value_reg=field_reg), node=parent
        )
    elif len(named_children) == 2:
        # Aliased import: import { a as b } from "./module"
        import_name = ctx.node_text(named_children[0])
        alias_name = ctx.node_text(named_children[1])
        field_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=field_reg,
                obj_reg=mod_reg,
                field_name=FieldName(import_name),
            ),
            node=parent,
        )
        ctx.emit_inst(
            DeclVar(name=VarName(alias_name), value_reg=field_reg), node=parent
        )


def _lower_namespace_import(
    ctx: TreeSitterEmitContext,
    namespace_import: Any,
    mod_reg: Any,
    parent: Any,
) -> None:
    """Lower namespace_import: import * as ns from "./module"."""
    # namespace_import: * as identifier
    for child in namespace_import.children:
        if child.type == "identifier":
            ns_name = ctx.node_text(child)
            ctx.emit_inst(
                DeclVar(name=VarName(ns_name), value_reg=mod_reg), node=parent
            )
            break
