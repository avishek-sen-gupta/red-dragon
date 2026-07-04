import inspect

from interpreter.frontends.context import NO_NODE
from interpreter.frontends.rust.expressions import (
    lower_rust_default_return_const,
    lower_rust_int_const,
    lower_rust_none_const,
)
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_node_defaults_to_no_node():
    for fn in (
        lower_rust_int_const,
        lower_rust_none_const,
        lower_rust_default_return_const,
    ):
        sig = inspect.signature(fn)
        assert sig.parameters["node"].default is NO_NODE, fn.__name__
