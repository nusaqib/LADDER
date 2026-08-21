"""Backend contract and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type

from ladder.ir.lower import LoweredProgram
from ladder.ir.model import Project

if TYPE_CHECKING:
    from ladder.iomap import IoMap


class BackendError(ValueError):
    """A project uses something this backend cannot express yet."""


class Backend(ABC):
    #: registry key, e.g. 'siemens'
    name: str = ""
    #: one-line description shown by `ladder targets`
    description: str = ""
    #: tool/version the emitted artifacts target by default
    target: str = ""
    #: requested tool version ('19', '21', '36', ...) - set by the
    #: `name@version` target syntax; None = the backend's default. Version
    #: quirks live in the backend keyed on this, which is what lets one
    #: backend serve several tool generations without forking.
    version: Optional[str] = None

    @abstractmethod
    def emit(self, project: Project, lowered: dict[str, LoweredProgram],
             outdir: Path, iomap: Optional["IoMap"] = None) -> list[Path]:
        """Write vendor artifacts under outdir; return the files written.

        iomap (optional) binds IO tags to this vendor's addresses/aliases;
        backends consume only their own section and ignore other vendors'
        syntax entirely.
        """

    def hints(self, project: Project) -> dict:
        """Per-backend section of project.vendor (may be empty)."""
        return project.vendor.get(self.name, {})


registry: dict[str, Type[Backend]] = {}


def register(cls: Type[Backend]) -> Type[Backend]:
    registry[cls.name] = cls
    return cls


def split_target(spec: str) -> tuple[str, Optional[str]]:
    """'siemens@21' -> ('siemens', '21'); 'siemens' -> ('siemens', None)."""
    name, _, version = spec.strip().partition("@")
    return name, (version or None)


def get_backend(spec: str) -> Backend:
    """Instantiate a backend from 'name' or 'name@version'."""
    name, version = split_target(spec)
    try:
        b = registry[name]()
    except KeyError:
        raise BackendError(
            f"unknown backend {name!r}; available: {', '.join(sorted(registry))}"
        ) from None
    b.version = version
    return b
