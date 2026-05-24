"""Allow running as ``python -m videodubber``."""

from videodubber.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
