import inspect

from interpreter.frontends._base import NO_NODE, BaseFrontend
from tests.covers import NotLanguageFeature, covers


class TestBaseNodeDefaults:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_all_four_node_params_default_to_no_node(self):
        for method_name in ("_emit", "_emit_inst", "_emit_class_ref", "_emit_func_ref"):
            method = getattr(BaseFrontend, method_name)
            sig = inspect.signature(method)
            assert sig.parameters["node"].default is NO_NODE, method_name
