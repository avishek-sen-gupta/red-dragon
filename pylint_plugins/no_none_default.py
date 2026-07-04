"""Pylint plugin: flag `= None` parameter defaults.

Project convention (.claude/conditional/design-principles.md):
    No `None` as a default parameter. Use empty structures (`{}`, `[]`, `()`).
    No `None` returns from non-None return types. Use null object pattern.

A parameter default of literal `None` is flagged regardless of its type
annotation — this is a mechanical check of an already-decided convention, not
a style opinion being introduced here.
"""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker


class NoNoneDefaultChecker(BaseChecker):
    name = "no-none-default"
    msgs = {
        "C9701": (
            "Parameter '%s' defaults to None; use an empty structure "
            "({}, [], ()) or a null-object sentinel instead",
            "no-none-default",
            "Project convention forbids `None` as a parameter default — "
            "see .claude/conditional/design-principles.md.",
        ),
    }

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        args = node.args

        positional = list(args.posonlyargs) + list(args.args)
        defaults = args.defaults or []
        offset = len(positional) - len(defaults)
        for param, default in zip(positional[offset:], defaults):
            if _is_none_constant(default):
                self.add_message("no-none-default", node=node, args=(param.name,))

        kw_defaults = args.kw_defaults or []
        for param, default in zip(args.kwonlyargs, kw_defaults):
            if default is not None and _is_none_constant(default):
                self.add_message("no-none-default", node=node, args=(param.name,))

    visit_asyncfunctiondef = visit_functiondef


def _is_none_constant(node: nodes.NodeNG) -> bool:
    return isinstance(node, nodes.Const) and node.value is None


def register(linter) -> None:
    linter.register_checker(NoNoneDefaultChecker(linter))
