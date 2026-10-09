"""One conversion, start to finish. Shared by the app and the command line."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import naming, photo, video
from .fileutil import copy_dates
from .presets import Settings
from .probe import MediaInfo
from .runner import Canceled, FFmpegFailed, FFmpegRun
from .tools import Capabilities


@dataclass
class Result:
    status: str  # done | skipped | failed | canceled
    output: Path | None = None
    message: str = ""
    notes: list[str] = field(default_factory=list)
    log: str = ""
    command: list[str] = field(default_factory=list)


class Conversion:
    """Converts one file. Call run() from a worker thread; pause/resume/cancel from anywhere."""

    def __init__(
        self,
        src: str,
        info: MediaInfo,
        settings: Settings,
        caps: Capabilities,
        reserved: set[str],
        counter: int = 1,
    ):
        self.src = src
        self.info = info
        self.s = settings
        self.caps = caps
        self.reserved = reserved
        self.counter = counter
        self._ff: FFmpegRun | None = None
        self._canceled = False

    def pause(self) -> bool:
        return self._ff.pause() if self._ff else False

    def resume(self) -> None:
        if self._ff:
            self._ff.resume()

    @property
    def canceled(self) -> bool:
        return self._canceled

    def cancel(self) -> None:
        self._canceled = True
        if self._ff:
            self._ff.cancel()

    def plan_target(self) -> tuple[Path | None, str]:
        kind = self.info.kind
        out_dir = naming.output_dir(self.src, self.s, kind)
        name = naming.planned_name(self.src, self.info, self.s, kind, self.counter)
        return naming.resolve_output(self.src, out_dir / name, self.s.collision, self.reserved)

    def run(self, on_progress: Callable[[float, float], None] | None = None) -> Result:
        kind = self.info.kind
        if kind == "unknown":
            return Result("failed", message=self.info.error or "Listo can't read this file.")
        target, note = self.plan_target()
        if target is None:
            return Result("skipped", message=note)
        key = naming.reserve_key(target)
        self.reserved.add(key)
        notes = [note] if note else []
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.reserved.discard(key)
            return Result("failed", message=f"Couldn't create the folder: {e}")

        # Write to a hidden temp file and only rename once it's complete:
        # no half-written files if something fails or you cancel.
        tmp = target.with_name(f".{target.stem}.listo-{uuid.uuid4().hex[:6]}{target.suffix}")
        cmd: list[str] = []
        try:
            if self._canceled:
                raise Canceled()
            if kind == "photo":
                notes += photo.convert(self.src, str(tmp), self.s)
            else:
                if not self.caps.ffmpeg:
                    return Result("failed", message="ffmpeg is missing.")
                plan = video.build(self.src, str(tmp), self.info, self.s, self.caps)
                notes += plan.notes
                cmd = [self.caps.ffmpeg, *plan.args]
                self._ff = FFmpegRun(self.caps.ffmpeg, plan.args)
                if self._canceled:
                    raise Canceled()
                self._ff.run(on_progress)
            if not tmp.exists() or tmp.stat().st_size == 0:
                raise FFmpegFailed("The output came out empty.", "")
            os.replace(tmp, target)
            if self.s.keep_dates:
                copy_dates(self.src, target)
            return Result("done", output=target, notes=notes, command=cmd)
        except Canceled:
            return Result("canceled", message="Canceled", command=cmd)
        except video.PlanError as e:
            return Result("failed", message=str(e), command=cmd)
        except FFmpegFailed as e:
            return Result("failed", message=str(e), log=e.log, command=cmd)
        except Exception as e:  # noqa: BLE001 — surface anything else readably
            return Result("failed", message=f"{e.__class__.__name__}: {e}", command=cmd)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if not target.exists():
                self.reserved.discard(key)
