"""Page rules of the page unit (change local-ocr-backends, design D5 and D6).

A page rule decides, for one PDF, which flagged pages leave the OCR route and
which pages go straight to the OCR engine list. ``registry.py`` holds the lazy
registrations, ``pipeline.py`` runs them in order, and each built-in rule has
its own module (``blank``, ``maths``, ``non_latin``).

Importing this package imports no rule module.
"""
