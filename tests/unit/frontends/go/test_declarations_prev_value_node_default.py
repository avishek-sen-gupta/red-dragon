import inspect

from interpreter.frontends.context import NO_NODE
from interpreter.frontends.go.declarations import _lower_const_spec
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_prev_value_node_defaults_to_no_node_and_is_annotated():
    sig = inspect.signature(_lower_const_spec)
    assert sig.parameters["prev_value_node"].default is NO_NODE
    assert sig.parameters["prev_value_node"].annotation is not inspect.Parameter.empty
