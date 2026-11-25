"""Where you are in the list: the places (All Files, Videos, Photos, Audio; To Convert, Done, Need a Look) the
title's menu offers, which files each holds (in_place), and who's using this computer (the initials' button).
"""

from __future__ import annotations

PLACES = {  # key -> (name, icon, section)
    "all": ("All Files", "file", "files"),
    "video": ("Videos", "film", "files"),
    "photo": ("Photos", "image", "files"),
    "audio": ("Audio", "audio", "files"),
    "todo": ("To Convert", "clock", "progress"),
    "done": ("Done", "check", "progress"),
    "attention": ("Need a Look", "alert", "progress"),
}
TODO = ("probing", "ready", "waiting", "converting", "paused", "downloading", "linked", "transcribing")
ATTENTION = ("failed", "warning", "unsupported", "canceled", "skipped")


def in_place(place: str, kind: str, state: str) -> bool:
    """Whether a file of this kind and state shows in this place."""
    if place in ("video", "photo", "audio"):
        return kind == place
    if place == "todo":
        return state in TODO
    if place == "done":
        return state == "done"
    if place == "attention":
        return state in ATTENTION
    return True


def computer_user() -> str:
    """The name of whoever is signed in to this computer ("Your Computer" if it can't tell)."""
    import getpass
    import sys

    try:
        user = getpass.getuser()
    except Exception:
        return "Your Computer"
    if sys.platform != "win32":
        try:
            import pwd

            full = pwd.getpwnam(user).pw_gecos.split(",")[0].strip()
            if full:
                return full
        except (KeyError, ImportError, OSError):
            pass  # no full name on file: the account name will do
    return user or "Your Computer"
