"""Exact COBOL numeric values, importable without the interpreter.

Every conversion between a COBOL representation (stored digits, literals,
text, IEEE floats) and the exact value, every IBM ARITH(COMPAT) scale rule,
and every exact arithmetic operation lives in this package. It is the only
code that imports ``decimal``; replacing the representation means editing this
package alone. It is a sibling of ``cobol_asg`` for the same reason as
``cobol_memory``: ``interpreter.anything`` loads the VM. See ``.importlinter``.
"""
