"""Run the complete baseline; use --download to acquire source data first."""
import _bootstrap  # noqa: F401
from auriscore.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
