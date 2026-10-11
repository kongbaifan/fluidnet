"""Development and portable entrypoint. No global Python installation changes."""
import multiprocessing
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".runtime" / "python"))
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from fluidnet.cli import main
    main()
