import inspect

import pytest

from interpreter.run import (
    execute_cfg,
    execute_cfg_traced,
    run_linked,
    run_linked_resumable,
    run_resumable,
)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "fn,param_name",
    [
        (execute_cfg, "vm"),
        (run_resumable, "vm"),
        (execute_cfg_traced, "vm"),
        (run_linked_resumable, "initial_vm"),
        (run_linked, "initial_vm"),
    ],
)
def test_vm_param_has_no_default(fn, param_name):
    sig = inspect.signature(fn)
    assert sig.parameters[param_name].default is inspect.Parameter.empty
