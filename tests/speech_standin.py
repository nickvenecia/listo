"""A stand-in speech model for tests. The real listening happens in a separate process
(core.captions_worker), so tests hand that process this module's `serve` instead."""

from __future__ import annotations

import types

from listo.core import captions, captions_worker


class FakeModel:
    def transcribe(self, audio, **kw):
        w = [
            types.SimpleNamespace(start=0.2, end=0.6, word=" Hello"),
            types.SimpleNamespace(start=0.7, end=1.1, word=" there."),
        ]
        return iter([types.SimpleNamespace(end=1.1, words=w)]), types.SimpleNamespace(language="en")


def serve(conn) -> None:
    captions._model = lambda name, on_status: FakeModel()
    captions_worker.serve(conn)


def serve_slowly(conn) -> None:
    """Never answers: for testing that Stop really ends the process."""
    import time

    captions._model = lambda name, on_status: time.sleep(3600)
    captions_worker.serve(conn)
