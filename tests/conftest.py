"""Shared test setup.

Qt's player, sound and window objects made during the UI tests can crash while Python tears itself
down after the last test ("malloc_consolidate ... Aborted"), turning a green run red in CI. Once
every test has finished and the summary is printed, leave straight away with pytest's own result.
"""

from __future__ import annotations

import os
import sys

import pytest

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if "PySide6.QtWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_status["code"])
