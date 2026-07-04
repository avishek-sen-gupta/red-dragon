import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.context import (
    TreeSitterEmitContext as EmitContext,
)
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_all_four_node_params_default_to_no_node():
    for method_name in (
        "emit_inst",
        "emit_decl_var",
        "emit_func_ref",
        "emit_class_ref",
    ):
        method = getattr(EmitContext, method_name)
        sig = inspect.signature(method)
        assert sig.parameters["node"].default is NO_NODE, method_name
