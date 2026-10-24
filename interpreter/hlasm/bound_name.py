# pyright: standard
"""What a name in an image resolves to: a place in a module, a stub, or zero."""

from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.stub_name import StubName
from interpreter.hlasm.weak_zero import WeakZero

type BoundName = PlacedName | StubName | WeakZero
