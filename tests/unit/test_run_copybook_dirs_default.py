import inspect

from interpreter.run import run
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(run)
    assert sig.parameters["copybook_dirs"].default == []
    # llm_client and io_provider stay untouched in this task
    assert sig.parameters["llm_client"].default is None
    assert sig.parameters["io_provider"].default is None
