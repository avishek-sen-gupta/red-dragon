# pyright: standard
"""z/Architecture floating-point arithmetic (BFP, HFP, DFP), importable without the interpreter.

Values are typed (sign, exponent, significand) records: bit images are encoded and decoded
in IR, never here. Every result is computed exactly and rounded once, and carries the
conditions it raised; the caller applies the FPC and PSW masks. See ``.importlinter``.
"""
