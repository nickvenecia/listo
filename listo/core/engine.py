"""One conversion, start to finish. Shared by the app and the command line."""

from __future__ import annotations

import os
import shlex
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import naming, photo, tape, video
from .fileutil import copy_dates
from .log import get_logger
from .presets import Settings
from .probe import MediaInfo
from .runner import Canceled, FFmpegFailed, FFmpegRun
from .tools import Capabilities

log = get_logger(__name__)

_plan_lock = threading.Lock()  # two conversions at once must not pick the same output name


@dataclass
class Result:
    status: str  # done | skipped | failed | canceled
    output: Path | None = None
    message: str = ""
    notes: list[str] = field(default_factory=list)
    log: str = ""
    command: list[str] = field(default_factory=list)
    warning: str = ""


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
        trim: tuple[float, float] | None = None,
        captions: list | None = None,
        target: Path | None = None,
        conform: video.Conform | None = None,
        timecode: str = "",
        cut: bool = False,
        marks=None,
    ):
        self.captions = captions
        self.target = target  # a fixed output path (one part of a joined video), else from the naming rules
        self.conform = conform
        self.timecode = timecode  # start the burned-in / stored timecode here (joined videos)
        self.cut = cut  # this clip follows another in a joined video (tape glitch at the cut)
        self.marks = marks  # burnin.Marks: PLAY / STOP timing around a tape blue screen
        # tape blue screen around a single video (a joined video gets one around the whole thing)
        self.blue_added = 0.0  # seconds of blue screen at each end, once added
        self.blue = (
            target is None and info.kind == "video" and tape.wants_blue(settings)
        )  # reviewed caption cues for this clip (captions.Cue), or None
        self.src = src
        self.info = info
        self.s = settings
        self.caps = caps
        self.reserved = reserved
        self.counter = counter
        self.trim = trim if (trim and info.kind in ("video", "audio") and trim[1] > trim[0]) else None
        self._ff: FFmpegRun | None = None
        self._canceled = False

    def _write_srt(self, target: Path, notes: list[str]) -> None:
        """Captions as an .srt next to the video (same name), for players and editing apps."""
        from .captions import for_output, to_srt

        srt = target.with_suffix(".srt")
        if srt.exists() or naming.reserve_key(srt) in self.reserved:
            notes.append(f"{srt.name} is already there, so the caption file wasn't replaced.")
            return
        start, length = (self.trim[0], self.trim[1] - self.trim[0]) if self.trim else (0.0, None)
        tmp = srt.with_name(f".{srt.name}.part")
        cues = for_output(self.captions, start, length)
        if self.blue_added:  # the blue screen comes first
            from .captions import Cue

            cues = [Cue(c.start + self.blue_added, c.end + self.blue_added, c.text) for c in cues]
        tmp.write_text(to_srt(cues, self.s.caption_words), encoding="utf-8")
        os.replace(tmp, srt)
        notes.append(f"Caption file saved: {srt.name}.")

    def _length(self) -> float:
        return (self.trim[1] - self.trim[0]) if self.trim else self.info.duration

    def _wrap_blue(self, tmp: Path, conform, muxer: str, notes: list[str]) -> None:
        """Tape effect: VCR blue screen before and after the video, joined on without re-encoding."""
        import shutil

        from .join import concat_args

        folder = tmp.with_name(f".listo-blue-{uuid.uuid4().hex[:6]}")
        folder.mkdir()
        try:
            pieces = []
            area = tape.picture_area(self.info, self.s)
            for name in ("start", "end"):
                out = folder / f"{name}{tmp.suffix}"
                r = tape.make_blue(out, conform, self.s, self.caps, tape.blue_badge(self.s, name), area)
                if r.status != "done":
                    notes.append("Blue screen skipped (couldn't make it).")
                    log.warning("blue screen failed: %s", r.message)
                    return
                pieces.append(out)
            wrapped = folder / f"wrapped{tmp.suffix}"
            self._ff = FFmpegRun(
                self.caps.ffmpeg,
                concat_args([pieces[0], tmp, pieces[1]], folder / "list.ffconcat", wrapped, muxer),
            )
            self._ff.run(None)
            os.replace(wrapped, tmp)
            self.blue_added = tape.BLUE_SECONDS
            notes.append("Blue screen added at the start and end.")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

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
        if self.target is not None:
            return self.target, ""
        kind = self.info.kind
        out_dir = naming.output_dir(self.src, self.s, kind)
        name = naming.planned_name(self.src, self.info, self.s, kind, self.counter)
        return naming.resolve_output(self.src, out_dir / name, self.s.collision, self.reserved)

    def _verify(self, out: Path, notes: list[str]) -> str:
        """Re-read the new file and compare it to the original. Returns a warning or ''."""
        from .probe import fmt_duration, probe

        got = probe(out, as_media=True)
        if got.error:
            return f"Couldn't read the new file back: {got.error}"
        audio_only = self.info.kind == "audio" or self.s.video_preset == "audio"
        if not audio_only and got.kind != "video":
            return "The new file has no picture."
        if self.info.audio and not got.audio and (audio_only or self.s.video_preset != "gif"):
            return "The new file has no sound, but the original does."
        want = ((self.trim[1] - self.trim[0]) if self.trim else self.info.duration) + 2 * self.blue_added
        if audio_only and self.info.audio and not self.trim:
            if self.info.audio[0].codec == "mp3":
                notes.append("Length not checked (MP3 files only estimate their length).")
                return ""
            want = self.info.audio[0].duration or want
        if self.trim and self.s.video_preset == "rewrap":
            want = 0  # keyframe cuts make the length legitimately differ a little
        if self.s.video_preset == "gif" and not audio_only:
            want = min(want, 30.0)
        if want > 0 and got.duration > 0:
            diff = abs(got.duration - want)
            if diff > max(0.5, want * 0.01):
                return f"Length doesn't match: original {fmt_duration(want)}, new file {fmt_duration(got.duration)}."
        notes.append("Checked — length matches.")
        return ""

    def run(self, on_progress: Callable[[float, float], None] | None = None) -> Result:
        kind = self.info.kind
        if kind == "unknown":
            return Result("failed", message=self.info.error or "Listo can't read this file.")
        with _plan_lock:
            target, note = self.plan_target()
            if target is None:
                return Result("skipped", message=note)
            key = naming.reserve_key(target)
            self.reserved.add(key)
        notes = [note] if note else []
        started = time.monotonic()
        log.info("converting %s -> %s", self.src, target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.reserved.discard(key)
            return Result("failed", message=f"Couldn't create the folder: {e}")

        # Write to a hidden temp file and only rename once it's complete:
        # no half-written files if something fails or you cancel.
        tmp = target.with_name(f".{target.stem}.listo-{uuid.uuid4().hex[:6]}{target.suffix}")
        cmd: list[str] = []
        plan = None
        try:
            if self._canceled:
                raise Canceled()
            if kind == "photo":
                notes += photo.convert(self.src, str(tmp), self.s)
            else:
                if not self.caps.ffmpeg:
                    return Result("failed", message="ffmpeg is missing.")
                conform = self.conform
                if self.blue and conform is None:  # the blue screen must match the video exactly
                    from .join import conform_for

                    conform = conform_for(self.info, self.s)
                marks = self.marks
                if self.blue and marks is None:  # PLAY carries on from the blue screen, STOP before the end
                    marks = tape.marks(self.s, self._length(), first=True, last=True)
                plan = video.build(
                    self.src, str(tmp), self.info, self.s, self.caps, self.trim, self.captions,
                    conform, self.timecode, self.cut, marks,
                )  # fmt: skip
                notes += plan.notes
                cmd = [self.caps.ffmpeg, *plan.args]
                log.info("ffmpeg command: %s", shlex.join(cmd))
                self._ff = FFmpegRun(self.caps.ffmpeg, plan.args)
                if self._canceled:
                    raise Canceled()
                self._ff.run(on_progress)
            if not tmp.exists() or tmp.stat().st_size == 0:
                raise FFmpegFailed("The output came out empty.", "")
            if self.blue and kind == "video":
                self._wrap_blue(tmp, conform, plan.muxer, notes)
            os.replace(tmp, target)
            if self.s.keep_dates:
                copy_dates(self.src, target)
            if self.s.captions and self.s.caption_srt and self.captions and kind == "video":
                self._write_srt(target, notes)
            warning = self._verify(target, notes) if (self.s.verify and kind != "photo") else ""
            log.info(
                "done in %.1f s: %s%s",
                time.monotonic() - started,
                target.name,
                f" (check: {warning})" if warning else "",
            )
            return Result("done", output=target, notes=notes, command=cmd, warning=warning)
        except Canceled:
            log.info("canceled: %s", self.src)
            return Result("canceled", message="Canceled", command=cmd)
        except video.PlanError as e:
            log.warning("can't convert %s: %s", self.src, e)
            return Result("failed", message=str(e), command=cmd)
        except FFmpegFailed as e:
            log.warning("ffmpeg failed on %s: %s\nffmpeg said:\n%s", self.src, e, (e.log or "")[-3000:])
            return Result("failed", message=str(e), log=e.log, command=cmd)
        except Exception as e:
            log.exception("conversion crashed on %s", self.src)
            return Result("failed", message=f"{e.__class__.__name__}: {e}", command=cmd)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if plan is not None:
                try:
                    plan.cleanup()  # burn-in images
                except OSError:
                    pass
            if not target.exists():
                self.reserved.discard(key)
