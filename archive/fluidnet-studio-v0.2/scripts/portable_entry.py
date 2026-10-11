import multiprocessing
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).parent)
    from fluidnet.cli import main
    main()
