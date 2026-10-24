# pyright: standard
"""A relocation naming a target that is neither a section of its module, a name in the image, nor an external symbol it declares."""


class UnknownRelocationTarget(Exception):
    def __init__(self, target: str, module: str) -> None:
        super().__init__(f"relocation target {target!r} in module {module} is unknown")
