"""LADDER - LLM-Assisted Design & Deployment of Engineering Routines.

Vendor-agnostic PLC program generation:

    LLM / human  ->  LADDER IR (this package, validated)
                 ->  deterministic lowering to a neutral statement AST
                 ->  vendor backends (Siemens TIA, Rockwell Studio 5000,
                     PLCopen XML / IEC 61131-10, Beckhoff TwinCAT)
"""

__version__ = "0.2.0"

from ladder.ir.model import Project  # noqa: F401
