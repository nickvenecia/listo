"""Undo / redo (⌘Z / ⇧⌘Z) for what you change in the window: the Convert To settings, which files are in the
list and in what order, and a file's own format and trim. Each step knows how to go back and forward; a
change taken straight back leaves no step (the window drops it).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

LIMIT = 200  # steps kept; the oldest go first


@dataclass
class Step:
    what: str  # said in the toast: "Undid the change to the settings."
    undo: Callable[[], None]
    redo: Callable[[], None]
    kind: str = ""  # "settings" steps can be merged or dropped by the window
    data: object = field(default=None, repr=False)


class History:
    def __init__(self) -> None:
        self.undos: list[Step] = []
        self.redos: list[Step] = []

    def push(self, step: Step) -> None:
        self.undos.append(step)
        del self.undos[:-LIMIT]
        self.redos.clear()

    def last(self) -> Step | None:
        return self.undos[-1] if self.undos else None

    def drop_last(self) -> None:
        if self.undos:
            self.undos.pop()

    def can_undo(self) -> bool:
        return bool(self.undos)

    def can_redo(self) -> bool:
        return bool(self.redos)

    def undo(self) -> str | None:
        if not self.undos:
            return None
        step = self.undos.pop()
        step.undo()
        self.redos.append(step)
        return step.what

    def redo(self) -> str | None:
        if not self.redos:
            return None
        step = self.redos.pop()
        step.redo()
        self.undos.append(step)
        return step.what
