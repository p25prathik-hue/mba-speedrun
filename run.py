"""Run from the repository root without installing:  python run.py <command> [options]

Commands: audit | solve | exact | profiles | sensitivity | web | inspect
Example:  python run.py solve --data data/sample --skip M1,M2 --hours 6
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from speedrun.cli import main  # noqa: E402

if __name__ == "__main__":
    main(sys.argv[1:])
