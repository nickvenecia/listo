"""Entry point used by the packaged app (PyInstaller)."""
import os
import sys

if __name__ == "__main__":
    # Windowed builds have no console; keep print() from crashing in CLI mode.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from listo.cli import main as cli_main

        sys.exit(cli_main(sys.argv[2:]))
    from listo.app import main

    sys.exit(main())
