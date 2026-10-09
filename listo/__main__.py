import multiprocessing
import sys


def _run() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from listo.cli import main as cli_main

        return cli_main(sys.argv[2:])
    from listo.app import main

    return main()


# The guard matters: background processes (captions) re-import this module and must not open a window.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(_run())
