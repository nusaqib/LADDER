"""Vendor backends. Each consumes the lowered statement AST, never raw IR logic."""

from __future__ import annotations

from ladder.backends.base import Backend, BackendError, get_backend, registry  # noqa: F401


def _register_all() -> None:
    # imported lazily so `import ladder` stays cheap and backend deps stay isolated
    from ladder.backends import beckhoff, iec, plcopen, rockwell, siemens  # noqa: F401


def _register_plugins() -> None:
    """Third-party backends live in their own packages and register through
    the 'ladder.backends' entry-point group: each entry point resolves to a
    Backend subclass (or a module whose import registers one). A broken
    plugin must never take the core down - it is reported, not raised."""
    import sys
    from importlib.metadata import entry_points

    try:
        eps = entry_points(group="ladder.backends")
    except TypeError:  # Python 3.11 compat path
        eps = entry_points().get("ladder.backends", [])
    for ep in eps:
        try:
            obj = ep.load()
            if isinstance(obj, type) and issubclass(obj, Backend):
                registry[obj.name] = obj
        except Exception as e:  # noqa: BLE001 - isolate plugin failures
            print(f"ladder: backend plugin {ep.name!r} failed to load: {e}",
                  file=sys.stderr)


_register_all()
_register_plugins()
