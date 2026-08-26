"""Entry point: `python run_demo.py` from the project root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from abl_agents.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
