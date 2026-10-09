"""Add a link.

Run all tests with:  python -m pytest   (tests that need ffmpeg skip themselves without it)
"""

from __future__ import annotations

import pytest

from listo.core import links


def test_is_link():
    from listo.core.links import is_link

    assert is_link("https://youtu.be/abc123xyz")
    assert not is_link("hello world") and not is_link("/Users/nick/a.mov")


def test_checksum_lines():
    h1, h2 = "a" * 64, "b" * 64
    sums = f"{h1}  yt-dlp\n{h2}  yt-dlp_macos\n"
    assert links.expected_sha256(sums, "yt-dlp_macos") == h2
    assert links.expected_sha256(sums, "yt-dlp") == h1
    assert links.expected_sha256(sums, "yt-dlp.exe") is None


def test_checksum_single_hash_files():
    h = "C" * 64
    unix = f"{h.lower()}  deno-x86_64-unknown-linux-gnu.zip\n"
    powershell = (
        "\r\nAlgorithm       Hash      Path\r\n---------       ----      ----\r\n"
        f"SHA256          {h}      D:\\a\\deno\\target\\deno-x86_64-pc-windows-msvc.zip\r\n"
    )
    assert links.expected_sha256(unix) == h.lower()
    assert links.expected_sha256(powershell) == h.lower()


def test_verified_rejects_tampered_download():
    import hashlib

    good = b"real tool"
    sums = f"{hashlib.sha256(good).hexdigest()}  tool\n".encode()
    assert links._verified(good, sums, "tool") == good
    with pytest.raises(links.LinkError):
        links._verified(b"something else", sums, "tool")
    with pytest.raises(links.LinkError):
        links._verified(good, b"no hashes here", "tool")
