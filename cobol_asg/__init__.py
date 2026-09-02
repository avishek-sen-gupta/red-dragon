# pyright: standard
"""Read COBOL source into an ASG, and describe the data it declares.

Parsing and data description only -- nothing here evaluates a program. The
lowering half of COBOL support stays in ``interpreter.cobol``, which imports
this package; the dependency never runs the other way, and the
``cobol-asg-is-a-leaf`` contract in .importlinter enforces that.

The package exists so a consumer that only reads COBOL -- cobble's
knowledge-graph extractor is the one driving this -- does not import the VM.
That is also why this file is empty of imports and must stay that way: a
convenience re-export here runs on every ``cobol_asg.*`` import, which is
exactly how ``interpreter/__init__.py`` came to load the whole VM for a caller
that wanted one PICTURE parser.
"""
