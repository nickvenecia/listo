"""Captions: speech-to-text on this computer (faster-whisper), saved per clip for review and editing.

Flow: transcribe() -> Transcript (words with timings + cues) -> the caption editor changes cue text ->
store.save(). At conversion time the cues are drawn into the video (burnin.caption_track) and can
also be written as an .srt file next to it.

Nothing leaves the computer: the speech model is downloaded once into Listo's data folder and the
audio is read with Listo's own ffmpeg.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .log import get_logger
from .paths import data_dir
from .probe import MediaInfo
from .tools import capabilities, popen_kwargs

log = get_logger(__name__)

# Settings key -> (faster-whisper model, download size shown to people)
MODELS = {
    "fast": ("base", "150 MB"),
    "balanced": ("small", "470 MB"),
    "best": ("large-v3-turbo", "1.6 GB"),
}
LANGUAGES = (
    ("auto", "Detect the language"),
    ("en", "English"),
    ("es", "Spanish"),
    ("pt", "Portuguese"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
)
SAMPLE_RATE = 16000


class CaptionError(Exception):
    """A readable reason captions couldn't be made."""


class Canceled(Exception):
    pass


# ---------------------------------------------------------------------------- data
@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    source: str
    model: str = ""
    language: str = ""
    words: list[Word] = field(default_factory=list)
    cues: list[Cue] = field(default_factory=list)
    edited: bool = False  # someone changed the text: keep these cues, don't re-split from words
    reviewed: bool = False
    layout: tuple[int, int] = (0, 0)  # (words per line, lines) the cues were split with

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> Transcript:
        d = json.loads(text)
        return cls(
            source=d.get("source", ""),
            model=d.get("model", ""),
            language=d.get("language", ""),
            words=[Word(**w) for w in d.get("words", [])],
            cues=[Cue(**c) for c in d.get("cues", [])],
            edited=bool(d.get("edited")),
            reviewed=bool(d.get("reviewed")),
            layout=tuple(d.get("layout", (0, 0))),
        )

    def cues_for(self, words_per_line: int, lines: int) -> list[Cue]:
        """The cues to show with this layout (re-split from the words unless they were edited)."""
        if self.edited or not self.words:
            return [c for c in self.cues if c.text.strip()]
        if self.layout != (words_per_line, lines):
            self.cues = split_cues(self.words, words_per_line, lines)
            self.layout = (words_per_line, lines)
        return self.cues


# ---------------------------------------------------------------------------- storage
def _store_dir() -> Path:
    return data_dir() / "captions"


def store_key(src: str | Path) -> str:
    """Same file (path, size, modified time) -> same key; a re-recorded or edited file gets a new one."""
    p = Path(src)
    try:
        st = p.stat()
        ident = f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        ident = str(p)
    return hashlib.sha1(ident.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]


def load(src: str | Path) -> Transcript | None:
    f = _store_dir() / f"{store_key(src)}.json"
    try:
        return Transcript.from_json(f.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, KeyError):
        return None


def save(t: Transcript) -> None:
    d = _store_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{store_key(t.source)}.json"
    tmp = f.with_suffix(".part")
    tmp.write_text(t.to_json(), encoding="utf-8")
    tmp.replace(f)


# ---------------------------------------------------------------------------- layout
_SENTENCE_END = (".", "?", "!", "…", "。", "？", "！")


def split_cues(words: list[Word], words_per_line: int, lines: int) -> list[Cue]:
    """Group words into on-screen captions: at most words_per_line × lines words, breaking early
    at sentence ends and pauses so a caption never runs across a long silence."""
    max_words = max(1, words_per_line) * max(1, lines)
    cues: list[Cue] = []
    group: list[Word] = []

    def flush() -> None:
        if group:
            text = " ".join(w.text.strip() for w in group).strip()
            if text:
                cues.append(Cue(group[0].start, group[-1].end, text))
            group.clear()

    for w in words:
        if group:
            pause = w.start - group[-1].end
            sentence_done = group[-1].text.strip().endswith(_SENTENCE_END)
            if len(group) >= max_words or pause > 0.8 or (sentence_done and len(group) >= max_words // 2):
                flush()
        group.append(w)
    flush()
    # Readable timing: at least 0.7 s on screen, a little linger, never overlapping the next one.
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else math.inf
        c.end = min(max(c.end + 0.2, c.start + 0.7), nxt)
    return cues


def wrap(text: str, words_per_line: int) -> list[str]:
    """Split a caption into balanced lines of at most words_per_line words."""
    words = text.split()
    if not words:
        return []
    n_lines = math.ceil(len(words) / max(1, words_per_line))
    per = math.ceil(len(words) / n_lines)
    return [" ".join(words[i : i + per]) for i in range(0, len(words), per)]


def for_output(cues: list[Cue], start: float, length: float | None) -> list[Cue]:
    """Cues shifted to a trimmed output that starts `start` seconds into the clip."""
    end = start + length if length else math.inf
    out = []
    for c in cues:
        if c.end <= start or c.start >= end:
            continue
        out.append(Cue(max(c.start, start) - start, min(c.end, end) - start, c.text))
    return out


def to_srt(cues: list[Cue], words_per_line: int) -> str:
    def ts(t: float) -> str:
        ms = max(0, round(t * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(
            f"{i}\n{ts(c.start)} --> {ts(c.end)}\n" + "\n".join(wrap(c.text, words_per_line)) + "\n"
        )
    return "\n".join(blocks)


# ---------------------------------------------------------------------------- speech to text
def models_dir() -> Path:
    return data_dir() / "models"


_model_lock = threading.Lock()
_loaded: dict[str, object] = {}


def _without_pyav() -> None:
    """faster-whisper imports PyAV (a 120 MB audio decoder) at start-up, but Listo hands it audio
    already decoded by its own ffmpeg, so the packaged app leaves PyAV out and uses this stand-in."""
    import importlib.util
    import sys
    import types

    if "av" not in sys.modules and importlib.util.find_spec("av") is None:
        stub = types.ModuleType("av")
        stub.__doc__ = "Stand-in: Listo decodes audio with ffmpeg."
        sys.modules["av"] = stub


def _model(name: str, on_status: Callable[[str], None]):
    with _model_lock:
        if name in _loaded:
            return _loaded[name]
        _without_pyav()
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise CaptionError("Captions aren't installed in this copy of Listo.") from e
        size = next((sz for _, (m, sz) in MODELS.items() if m == name), "")
        try:  # already downloaded?
            model = WhisperModel(name, device="auto", compute_type="int8", download_root=str(models_dir()),
                                 local_files_only=True)  # fmt: skip
        except Exception:
            on_status(f"Downloading the speech model (one time{', ' + size if size else ''})…")
            try:
                model = WhisperModel(
                    name, device="auto", compute_type="int8", download_root=str(models_dir())
                )
            except Exception as e:
                log.warning("speech model download failed", exc_info=True)
                raise CaptionError(
                    "Couldn't download the speech model. Check the internet connection."
                ) from e
        _loaded[name] = model
        return model


def _audio(src: str, info: MediaInfo, cancel: threading.Event | None):
    """The clip's first audio track as 16 kHz mono float samples, read with Listo's ffmpeg."""
    import numpy as np

    caps = capabilities()
    if not caps.ffmpeg:
        raise CaptionError("ffmpeg is missing.")
    if not info.audio:
        raise CaptionError("This clip has no sound to caption.")
    proc = subprocess.Popen(
        [caps.ffmpeg, "-nostdin", "-v", "error", "-i", src, "-map", f"0:{info.audio[0].index}",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **popen_kwargs(),
    )  # fmt: skip
    chunks = []
    if proc.stdout is None:
        raise CaptionError("Couldn't read this clip's sound.")
    while True:
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise Canceled()
        b = proc.stdout.read(1 << 20)
        if not b:
            break
        chunks.append(b)
    proc.wait()
    data = b"".join(chunks)
    if not data:
        raise CaptionError("Couldn't read this clip's sound.")
    return np.frombuffer(data[: len(data) // 4 * 4], dtype=np.float32)


def transcribe(
    src: str,
    info: MediaInfo,
    model_key: str = "balanced",
    language: str = "auto",
    words_per_line: int = 7,
    lines: int = 2,
    on_progress: Callable[[float], None] = lambda _f: None,
    on_status: Callable[[str], None] = lambda _s: None,
    cancel: threading.Event | None = None,
) -> Transcript:
    """Listen to a clip and return its words with timings (and first-draft captions)."""
    name = MODELS.get(model_key, MODELS["balanced"])[0]
    model = _model(name, on_status)
    on_status("Reading the sound…")
    audio = _audio(src, info, cancel)
    duration = max(len(audio) / SAMPLE_RATE, 0.001)
    on_status("Listening…")
    auto = language == "auto"
    segments, meta = model.transcribe(
        audio,
        language=None if auto else language,
        multilingual=auto,  # mixed Spanish / English stays in each speaker's language
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,  # fewer runaway repeats on long clips
    )
    words: list[Word] = []
    for seg in segments:
        if cancel is not None and cancel.is_set():
            raise Canceled()
        for w in seg.words or []:
            if w.word.strip():
                words.append(Word(round(w.start, 3), round(w.end, 3), w.word.strip()))
        on_progress(min(1.0, seg.end / duration))
    t = Transcript(source=str(src), model=name, language=getattr(meta, "language", "") or "", words=words)
    t.cues = split_cues(words, words_per_line, lines)
    t.layout = (words_per_line, lines)
    return t
