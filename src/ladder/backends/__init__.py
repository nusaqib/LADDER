"""Vendor backends. Each consumes the lowered statement AST, never raw IR logic."""

from __future__ import annotations

from ladder.backends.base import Backend, BackendError, get_backend, registry  # noqa: F401


def _register_all() -> None:
    # imported lazily so `import ladder` stays cheap and backend deps stay isolated
    from ladder.backends import beckhoff, iec, plcopen, rockwell, siemens  # noqa: F401


_register_all()
