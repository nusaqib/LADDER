"""Reverse adoption: vendor project -> LADDER IR (M2).

Adopters lift an existing vendor project into IR so real plants can enter
the LADDER workflow. v0.1 fidelity: tags map to IR tags; SCL/ST logic is
carried as `st` escape-hatch elements (structure-element inference from
existing code is a later phase). Every adopter also writes a STRUCTURE.md
report - the raw material for encoding project conventions in an engine.
"""

from ladder.adopt.rockwell import adopt_rockwell_l5x  # noqa: F401
from ladder.adopt.siemens import adopt_siemens_spec  # noqa: F401
