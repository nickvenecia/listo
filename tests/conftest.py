"""Shared test setup: an offscreen Qt app and a throwaway data folder for every test.

Qt's player, sound and window objects made during the UI tests can crash while Python tears itself
down after the last test ("malloc_consolidate ... Aborted"), turning a green run red in CI. Once
every test has finished and the summary is printed, leave straight away with pytest's own result.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    if "PySide6.QtWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_status["code"])


@pytest.fixture(autouse=True)
def data_folder(tmp_path):
    """Never touch the real settings, captions or tools: every test gets its own empty data folder."""
    from listo.core.paths import use_data_dir

    use_data_dir(tmp_path / "data")
    yield tmp_path / "data"
    use_data_dir(None)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    from listo.app import setup_app

    setup_app(app)
    return app
