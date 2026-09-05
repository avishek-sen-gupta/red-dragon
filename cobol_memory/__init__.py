"""Byte-extent algebra for COBOL storage, importable without the interpreter.

A COBOL field is a slice of a section's region buffer, so two fields alias
exactly when their byte ranges intersect within one region. Stating that here,
as a sibling of ``cobol_asg`` rather than under ``interpreter``, is what lets a
static-only consumer use it: an import of ``interpreter.anything`` runs
``interpreter/__init__.py``, which loads the VM. See ``.importlinter``.
"""
