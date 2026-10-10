"""Join: every video clip in a batch becomes one long video.

How: each clip is converted on its own (so every clip shows its own progress and gets its own
burn-ins, captions and trim) into a hidden parts folder, all made to match the first clip
(video.Conform: same frame size, frame rate and sound). Then ffmpeg's concat reader glues the
parts together without re-encoding, so there is no second loss of quality. The parts are deleted.

Rewrap doesn't re-encode, so it can only join clips that already match (same camera settings);
anything else gets a readable reason instead of a broken file.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from . import naming, tape, video
from .engine import Result, _plan_lock
from .fileutil import copy_dates
from .log import get_logger
from .presets import AUDIO_BY_KEY, Settings
from .probe import MediaInfo, Shot, fmt_duration, probe, recorded
from .runner import Canceled, FFmpegFailed, FFmpegRun
from .tools import Capabilities

log = get_logger(__name__)

MUXERS = {"mov": "mov", "mp4": "mp4", "webm": "webm"}
MUXERS.update({f.ext: f.muxer for f in AUDIO_BY_KEY.values()})


def can_join(s: Settings) -> bool:
    """A GIF can't be glued from parts (each has its own palette); everything else can."""
    return s.video_preset != "gif"


def joins(s: Settings, kind: str) -> bool:
    """Does a file of this kind become part of the joined video with these settings?"""
    return s.join and can_join(s) and kind == "video"


def conform_for(info: MediaInfo, s: Settings) -> video.Conform:
    """What every part must match: taken from the first clip."""
    sr = info.audio[0].sample_rate if info.audio and info.audio[0].sample_rate else 48000
    if s.video_preset == "audio":
        ch = 1 if info.audio and info.audio[0].channels == 1 else 2
        return video.Conform(sample_rate=sr, channels=ch)
    w, h = naming.output_size(info, s, "video")
    doubled = info.interlaced and s.deinterlace == "smooth"
    rate = video._out_rate(info, s, doubled) or "30000/1001"
    return video.Conform(w, h, rate, 48000, 2)


def running_timecodes(clips: list[tuple[MediaInfo, float]], start: float = 0.0) -> list[str]:
    """Continuous Timecode: where each clip's timecode starts, (info, kept length) in list order,
    `start` seconds into the tape. Used for a joined video and for separate files alike.

    One Convert = one tape: clips without their own timecode (camcorder .MOD, phones) get a counter
    that keeps running from clip to clip, from 00:00:00:00 (even across days: it's often one event).
    Clips with real timecode (pro cameras) keep it (""); the counter runs on through them."""
    from .probe import tc_add, zero_tc

    out: list[str] = []
    running = start
    for info, length in clips:
        out.append("" if info.timecode or not info.rate else tc_add(zero_tc(info.rate), running, info.rate))
        running += max(0.0, length)
    return out


def concat_args(
    parts: list[Path], lst: Path, out: Path, muxer: str, timecode: str = "", shot: Shot | None = None
) -> list[str]:
    """ffmpeg args that glue parts (same size, frame rate, sound, encoder) into out without
    re-encoding. Writes the list file `lst`. Used for joined videos and the tape blue screen.
    shot: when the video was shot (stored in the file, see video.mux_args)."""
    lines = ["ffconcat version 1.0"]
    for p in parts:
        lines.append("file '" + str(p).replace("'", "'\\''") + "'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args = [
        "-hide_banner", "-nostdin", "-y", "-nostats", "-progress", "pipe:1",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-map", "0:v?", "-map", "0:a?", "-c", "copy",
    ]  # fmt: skip
    if muxer in ("mov", "mp4") and timecode:
        args += ["-timecode", timecode]
    return [*args, *video.mux_args(muxer, shot), "-f", muxer, str(out)]


def parts_folder(first_src: str, s: Settings) -> Path:
    """Hidden, next to where the joined video goes (same disk, so the final rename is instant)."""
    return naming.output_dir(first_src, s, "video") / f".listo-join-{uuid.uuid4().hex[:8]}"


def part_path(folder: Path, n: int, s: Settings) -> Path:
    return folder / f"part{n:04d}.{naming.output_ext('video', s)}"


def joined_name(first_src: str, info: MediaInfo | None, s: Settings, last_src: str = "") -> str:
    """The naming rules applied to the first clip, with {name} = "FIRST-LAST" (the range it covers),
    e.g. MOV001-MOV014.mov. Same names (PRG folders) or no last clip: "FIRST_joined"."""
    ctx = naming.make_context(first_src, info, s, "video", 1)
    first, last = Path(first_src).stem, Path(last_src).stem if last_src else ""
    ctx["name"] = f"{first}-{last}" if last and last.lower() != first.lower() else f"{first}_joined"
    return f"{naming.render(s.naming or '{name}', ctx)}.{naming.output_ext('video', s)}"


def _rate(r: str) -> float:
    try:
        return float(Fraction(r))
    except (ValueError, ZeroDivisionError):
        return 0.0


def mismatch(infos: list[MediaInfo]) -> str:
    """Why these parts can't be glued as they are ('' if they can)."""
    first = infos[0]
    for i in infos[1:]:
        if first.video_index is not None:
            if (i.vcodec, i.width, i.height) != (first.vcodec, first.width, first.height):
                return "they don't all have the same picture size and format"
            if abs(_rate(i.rate) - _rate(first.rate)) > 0.01:
                return "they don't all have the same frame rate"
        a, b = (first.audio[:1], i.audio[:1])
        if bool(a) != bool(b):
            return "some have sound and some don't"
        if a and (a[0].codec, a[0].sample_rate, a[0].channels) != (
            b[0].codec,
            b[0].sample_rate,
            b[0].channels,
        ):
            return "their sound isn't all in the same format"
    return ""


class Join:
    """Glue converted parts into one file. Call run() from a worker thread; cancel() from anywhere."""

    def __init__(
        self,
        parts: list[Path],
        first_src: str,
        first_info: MediaInfo,
        settings: Settings,
        caps: Capabilities,
        reserved: set[str],
        captions: list[list | None] | None = None,
        last_src: str = "",
        conform: video.Conform | None = None,
    ):
        """captions: for each part, its cues on the part's own timeline (already trimmed), or None."""
        self.parts = parts
        self.first_src = first_src
        self.first_info = first_info
        self.s = settings
        self.caps = caps
        self.reserved = reserved
        self.captions = captions or [None] * len(parts)
        self.last_src = last_src
        self.conform = conform  # what every part matches (needed to make the tape blue screen)
        self._ff: FFmpegRun | None = None
        self._canceled = False
        self.length = 0.0  # total, known once the parts are read

    def cancel(self) -> None:
        self._canceled = True
        if self._ff:
            self._ff.cancel()

    def _add_blue(self) -> None:
        """Tape effect: VCR blue screen before the first clip and after the last."""
        folder = self.parts[0].parent
        ext = self.parts[0].suffix
        area = tape.picture_area(self.first_info, self.s)
        made = []
        for name in ("start", "end"):
            out = folder / f"blue-{name}{ext}"
            r = tape.make_blue(out, self.conform, self.s, self.caps, tape.blue_badge(self.s, name), area)
            if r.status != "done":
                log.warning("blue screen failed: %s", r.message)
                return
            made.append(out)
        self.parts = [made[0], *self.parts, made[1]]
        self.captions = [None, *self.captions, None]

    def cleanup(self) -> None:
        """Delete the parts (they were only a step on the way)."""
        folders = {p.parent for p in self.parts}
        for f in folders:
            if f.name.startswith(".listo-join-"):
                shutil.rmtree(f, ignore_errors=True)

    def _write_srt(self, target: Path, lengths: list[float], notes: list[str]) -> None:
        from .captions import Cue, to_srt

        srt = target.with_suffix(".srt")
        if srt.exists() or naming.reserve_key(srt) in self.reserved:
            notes.append(f"{srt.name} is already there, so the caption file wasn't replaced.")
            return
        cues, offset = [], 0.0
        for part_cues, length in zip(self.captions, lengths, strict=True):
            for c in part_cues or []:
                cues.append(Cue(c.start + offset, min(c.end, length) + offset, c.text))
            offset += length
        if not cues:
            return
        tmp = srt.with_name(f".{srt.name}.part")
        tmp.write_text(to_srt(cues, self.s.caption_words), encoding="utf-8")
        os.replace(tmp, srt)
        notes.append(f"Caption file saved: {srt.name}.")

    def run(self, on_progress: Callable[[float, float], None] | None = None) -> Result:
        target: Path | None = None
        key = ""
        tmp: Path | None = None
        try:
            if not self.parts:
                return Result("failed", message="Nothing to join: none of the clips converted.")
            if not self.caps.ffmpeg:
                return Result("failed", message="ffmpeg is missing.")
            first_part = self.parts[0]
            if tape.wants_blue(self.s) and self.conform is not None:
                self._add_blue()
            infos = [probe(p, as_media=True) for p in self.parts]
            bad = next((i for i in infos if i.error), None)
            if bad is not None:
                return Result("failed", message=f"Couldn't read a converted part: {bad.error}")
            why = mismatch(infos)
            if why:
                hint = (
                    " Rewrap can't change them; pick a format that converts (like ProRes or H.264)."
                    if self.s.video_preset == "rewrap"
                    else ""
                )
                return Result("failed", message=f"These clips can't be joined: {why}.{hint}")
            lengths = [i.duration for i in infos]
            self.length = sum(lengths)

            with _plan_lock:
                out_dir = naming.output_dir(self.first_src, self.s, "video")
                name = joined_name(self.first_src, self.first_info, self.s, self.last_src)
                target, note = naming.resolve_output(
                    self.first_src, out_dir / name, self.s.collision, self.reserved
                )
                if target is None:
                    return Result("skipped", message=note)
                key = naming.reserve_key(target)
                self.reserved.add(key)
            notes = [note] if note else []
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.stem}.listo-{uuid.uuid4().hex[:6]}{target.suffix}")

            muxer = MUXERS.get(target.suffix.lstrip(".").lower(), "mov")
            # When it was shot: the first clip's time, as its part already carries it (trim included)
            first = infos[self.parts.index(first_part)]
            shot = recorded(first_part, first) if first.created else recorded(self.first_src, self.first_info)
            # (the edit starts at the first clip's timecode)
            args = concat_args(
                self.parts, self.parts[0].parent / "join.ffconcat", tmp, muxer, infos[0].timecode, shot
            )
            if self._canceled:
                raise Canceled()
            log.info("joining %d clips into %s", len(self.parts), target)
            log.info("ffmpeg command: %s", " ".join([self.caps.ffmpeg, *args]))
            self._ff = FFmpegRun(self.caps.ffmpeg, args)
            self._ff.run(on_progress)
            if not tmp.exists() or tmp.stat().st_size == 0:
                raise FFmpegFailed("The joined video came out empty.", "")
            os.replace(tmp, target)
            if shot and muxer in ("mov", "mp4", "webm"):
                log.info("recording time stored in %s: %s", target.name, video.date_tags(shot))
            if self.s.keep_dates:
                copy_dates(self.first_src, target)
            if self.s.captions and self.s.caption_srt:
                self._write_srt(target, lengths, notes)
            warning = ""
            if self.s.verify:
                got = probe(target, as_media=True)
                if got.error:
                    warning = f"Couldn't read the joined video back: {got.error}"
                elif self.length > 0 and abs(got.duration - self.length) > max(0.5, self.length * 0.01):
                    warning = (
                        f"Length doesn't match: the clips add up to {fmt_duration(self.length)}, "
                        f"the joined video is {fmt_duration(got.duration)}."
                    )
                else:
                    notes.append("Checked — length matches.")
            n = len(self.parts)
            notes.insert(0, f"{n} clips joined into one video ({fmt_duration(self.length)}).")
            return Result(
                "done", output=target, notes=notes, command=[self.caps.ffmpeg, *args], warning=warning
            )
        except Canceled:
            return Result("canceled", message="Canceled")
        except FFmpegFailed as e:
            return Result("failed", message=f"Couldn't join the clips: {e}", log=e.log)
        except Exception as e:
            log.warning("join failed", exc_info=True)
            return Result("failed", message=f"Couldn't join the clips ({e.__class__.__name__}: {e}).")
        finally:
            if tmp is not None and tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if key and (target is None or not target.exists()):
                self.reserved.discard(key)
            self.cleanup()
