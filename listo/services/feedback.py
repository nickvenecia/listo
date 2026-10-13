"""Feedback: ideas and problems, sent to the people who make Listo.

Where it goes isn't set up yet. Until it is, every message waits in an outbox (feedback/ in the data
folder) and goes out once a sender is connected. To connect one, set ADDRESS to a support email (messages
then open in your email app, ready to send) or write a FeedbackSender and pass it to use().

What's in a message: what you typed, your email if you add it, and (only if you tick it) Listo's
version and the kind of computer. Never your files, their names or your settings.
"""

from __future__ import annotations

import json
import platform
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from listo import __version__
from listo.core.log import get_logger
from listo.core.paths import data_dir

log = get_logger(__name__)

ADDRESS = ""  # a support email; "" until there is one
KINDS = [("idea", "Idea"), ("problem", "Problem"), ("other", "Other")]
MAX_CHARS = 5000


class FeedbackError(OSError):
    pass


@dataclass
class Feedback:
    kind: str
    message: str
    email: str = ""
    details: dict = field(default_factory=dict)
    written: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M"))


def details() -> dict:
    """The app version and the kind of computer (nothing personal)."""
    return {
        "listo": __version__,
        "system": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
    }


class FeedbackSender:
    """Where feedback goes. This one isn't connected: messages wait in the outbox."""

    connected = False

    def send(self, fb: Feedback) -> None:
        raise FeedbackError("not connected")


_sender: FeedbackSender = FeedbackSender()


def sender() -> FeedbackSender:
    return _sender


def use(s: FeedbackSender) -> None:
    global _sender
    _sender = s


def make(kind: str, message: str, email: str = "", include_details: bool = True) -> Feedback:
    message = message.strip()
    if not message:
        raise FeedbackError("Write something first.")
    kind = kind if kind in dict(KINDS) else "other"
    return Feedback(kind, message[:MAX_CHARS], email.strip()[:200], details() if include_details else {})


def outbox() -> Path:
    return data_dir() / "feedback"


def send(fb: Feedback) -> bool:
    """Send it, or keep it in the outbox. True if it went out now."""
    if sender().connected:
        try:
            sender().send(fb)
            log.info("feedback sent")
            return True
        except OSError:
            log.info("feedback didn't send; keeping it in the outbox")
    keep(fb)
    return False


def keep(fb: Feedback) -> Path:
    from listo.core.store import write_json

    path = outbox() / f"{time.strftime('%Y%m%d-%H%M%S')}-{fb.kind}-{uuid.uuid4().hex[:6]}.json"
    write_json(path, asdict(fb))
    log.info("feedback kept in the outbox (%s)", path.name)
    return path


def waiting() -> list[Path]:
    folder = outbox()
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def send_waiting() -> int:
    """Send what's in the outbox (once a sender is connected). Returns how many went."""
    if not sender().connected:
        return 0
    n = 0
    for path in waiting():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            sender().send(
                Feedback(**{k: d[k] for k in ("kind", "message", "email", "details", "written") if k in d})
            )
            path.unlink()
            n += 1
        except (OSError, ValueError, TypeError, KeyError):
            log.info("a waiting feedback message didn't send")
            break
    return n


def mail_link(fb: Feedback) -> str:
    """A mailto: link for ADDRESS with the message filled in ("" if there's no address)."""
    from urllib.parse import quote

    if not ADDRESS:
        return ""
    body = fb.message + ("\n\n" + "\n".join(f"{k}: {v}" for k, v in fb.details.items()) if fb.details else "")
    subject = f"Listo {dict(KINDS).get(fb.kind, 'Feedback')}"
    return f"mailto:{quote(ADDRESS, safe='@')}?subject={quote(subject)}&body={quote(body)}"
