"""Pattern library: parameterized IR fragments.

Patterns shrink the LLM's job from "write the IR" to "pick a pattern and
fill in parameters". A pattern is a plain function returning IR pieces
(tags and logic elements) that the caller splices into a Program.

v0.1 ships the shape with one worked pattern; the library grows as real
reference programs (SR PPS, the Studio 5000 project) are mined for
recurring structures. IR-level pattern invocation (element: pattern) is
on the roadmap.
"""

from ladder.patterns.library import motor_starter  # noqa: F401
