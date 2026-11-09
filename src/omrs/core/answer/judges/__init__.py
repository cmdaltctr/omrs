"""Claim-judge strategies (pre-exp35-harness-and-answer-fixes, design D10).

A strategy is one module here plus one ``register()`` line in
:mod:`omrs.core.answer.judges.registry`. Strategies take their transport
from the composition root (``omrs.compose_judges``) and import no provider.
"""
