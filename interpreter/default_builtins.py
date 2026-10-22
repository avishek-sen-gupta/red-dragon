# pyright: standard
"""The builtins table run() resolves builtin calls through when its caller passes none."""

from interpreter.vm.builtins import core_builtins

DEFAULT_BUILTINS = core_builtins()
