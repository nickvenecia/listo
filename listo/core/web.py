"""The one test of "is this a web link" (a pasted or dropped video link, before it goes to the downloader).

Listo never reads web pages itself: a video link goes to yt-dlp (core/links.py), and Listo's own downloads
(updates, yt-dlp) come only from fixed GitHub addresses and are checked against their published SHA-256.
"""

from __future__ import annotations

from urllib.parse import urlparse

MAX_LINK = 2048


def web_link(text: str) -> str:
    """A link as pasted or dropped -> the link, or "" if it isn't a plain web link.

    It must start with http:// or https:// (Listo scans pasted text word by word, and "clip.mov" is a file,
    not a website). "file://…", "javascript:…", "smb://…", a link with a name@ in front of its address
    ("https://youtube.com@evil.example" really goes to evil.example), or a malformed one give ""."""
    s = (text or "").strip()
    if not s or any(c.isspace() for c in s) or len(s) > MAX_LINK:
        return ""
    try:
        u = urlparse(s)
        host, _port = u.hostname, u.port  # .port raises for ":abc" or ":99999"
    except ValueError:
        return ""
    if u.scheme.lower() not in ("http", "https") or not host or "." not in host:
        return ""
    if "@" in u.netloc or "%" in u.netloc:
        return ""
    return s


def is_web_link(text: str) -> bool:
    return bool(web_link(text))
