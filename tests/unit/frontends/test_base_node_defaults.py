import inspect

from tests.covers import covers, NotLanguageFeature
from interpreter.frontends._base import BaseFrontend, NO_NODE


class TestBaseNodeDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_all_four_node_params_default_to_no_node(self):
        for method_name in ("_emit", "_emit_inst", "_emit_class_ref", "_emit_func_ref"):
            method = getattr(BaseFrontend, method_name)
            sig = inspect.signature(method)
            assert sig.parameters["node"].default is NO_NODE, method_name
