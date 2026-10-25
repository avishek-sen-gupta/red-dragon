# pyright: standard
"""An object-module record the binder does not apply: a J-constant naming something that is not an external dummy section, or a QY offset beyond a long displacement."""


class UnsupportedBinding(Exception):
    def __init__(self, record: str, module: str, issue: str) -> None:
        super().__init__(f"{record} in module {module} is not bound yet ({issue})")
