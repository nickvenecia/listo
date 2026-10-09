"""Entry point used by the packaged app (PyInstaller)."""

import multiprocessing
import os
import sys

if __name__ == "__main__":
    # Background processes (captions) start as copies of this program; this sends them to their work
    # instead of opening another window.
    multiprocessing.freeze_support()
    # Windowed builds have no console; keep print() from crashing in CLI mode.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115 — lives as long as the process
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from listo.cli import main as cli_main

        sys.exit(cli_main(sys.argv[2:]))
    from listo.app import main

    sys.exit(main())
