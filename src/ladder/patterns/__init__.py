"""Pattern library: parameterized IR fragments.

Patterns shrink the LLM's job from "write the IR" to "pick a pattern and
fill in parameters". Invoke from the IR with `element: pattern`; expansion
into real elements happens before validation, so expanded logic is checked,
lowered, and simulated exactly like hand-written IR.

The library grows as real reference programs (SR PPS, the Studio 5000
project) are mined for recurring structures (M3).
"""

from ladder.patterns.expand import expand_project  # noqa: F401
from ladder.patterns.library import PATTERNS, PatternError  # noqa: F401
