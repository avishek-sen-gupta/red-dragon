# pyright: standard
"""An RLD record whose target does not fit its kind: PR_TOTAL without a name, every other kind with one."""

from interpreter.project.relocation_kind import RelocationKind


class RelocationTargetMismatch(Exception):
    def __init__(self, kind: RelocationKind, untargeted: bool) -> None:
        wanted = "no target" if kind == RelocationKind.PR_TOTAL else "a named target"
        given = "none" if untargeted else "a name"
        super().__init__(f"a {kind.value} relocation takes {wanted}, not {given}")
